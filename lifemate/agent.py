"""Agent loop for LifeMate — observation after EVERY call.

Generator protocol (the model, or a test double): a callable
``gen(prompt: str, tools: dict) -> dict | None`` returning one tool
call ``{"name": ..., "arguments": {...}}`` or ``None`` to stop. The
loop owns everything else: prompt construction, pre-call validation,
execution, observation injection, loop guard, termination.

Loop semantics (same as deep-dives/01, now with the 2026-10-27 review
fix applied here and there):

- After EVERY executed call, the next prompt is rebuilt with ALL
  observations so far (``name(args) -> ok/error/output``, output
  truncated to 300 chars). Previously observation only entered the
  prompt on a guard-triggered replan, which meant the normal
  "continue" path ran blind — a read result could not feed the next
  call at all.
- Validation runs BEFORE every call via ``env.validate`` (not logged,
  no state change). A validation failure is an observation for the
  next generation, not a submitted call: up to 2 generation attempts
  per step, then the trace ends as-is.
- Loop guard: a call already executed ``max_repeats`` times is NEVER
  executed again (pre-block); the first trigger replans once (prompt
  + "choose a different action"), the second trigger stops the trace
  as-is. No append of ask/[] on stopping, no filtering of executed
  calls, no cleanup writes — the trace is submission material.
- Termination: generator returns None, ``max_steps`` reached, or the
  guard stops the loop. The caller owns any task-specific completion
  predicate via ``completion`` (called after each execution).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Callable

from .adapter import ZaicEnv
from .lifemate_grounding import ground_tool_call
from .loader import Sample, catalog_tools_for_sample


@dataclass
class LoopGuard:
    max_repeats: int = 2
    _counts: dict = field(default_factory=dict)
    _replanned: bool = False

    def _key(self, call: dict) -> str:
        return json.dumps(call, sort_keys=True, ensure_ascii=False)

    def repeat_count(self, call: dict) -> int:
        return self._counts.get(self._key(call), 0)

    def record(self, call: dict, state_progress: bool) -> str:
        key = self._key(call)
        self._counts[key] = self._counts.get(key, 0) + 1
        if self._counts[key] >= self.max_repeats:
            return "replan_once" if not self._replanned else "stop"
        return "continue"


def render_observation_prompt(base_prompt: str, executed: list[dict], results: list[dict], replan: bool = False) -> str:
    lines = []
    for call, result in zip(executed, results):
        outcome = "ok" if result.get("ok") else f"error: {result.get('error')}"
        output = repr(result)
        if len(output) > 300:
            output = output[:300] + "..."
        lines.append(f"- {call['name']}({call['arguments']}) -> {outcome}; output={output}")
    text = (
        f"{base_prompt}\n\nPrevious calls and their OBSERVED results "
        "(use these, do not repeat failed calls, do not guess new ids):\n"
        + "\n".join(lines)
    )
    if replan:
        text += "\nChoose a different, evidence-backed action or stop."
    return text


def build_base_prompt(sample: Sample, transcript: str, tools: dict) -> str:
    """Prompt for one sample: context + history + transcript + the
    sample's filtered tool list. History user turns without a
    transcript (public_test) are marked as audio-only so the model
    cannot hallucinate their content; assistant texts are always
    included."""
    ctx = sample.context
    profile = ctx.get("user_profile", {})
    lines = [
        "You are a Vietnamese voice assistant. Output exactly one JSON "
        "object per turn: {\"name\": \"<tool>\", \"arguments\": {...}} or "
        "{\"stop\": true} when done. Never invent ids: use only ids from "
        "previous tool results in this conversation.",
        f"Current time: {ctx.get('current_time')} ({ctx.get('timezone')}).",
        f"User: {profile.get('name', '')}, city {profile.get('city', '')}.",
        "Tools you may call (this sample only):",
    ]
    for name, spec in sorted(tools.items()):
        req = spec["parameters"].get("required", [])
        lines.append(f"- {name} ({spec['kind']}): {spec.get('description', '')} required={req}")
    lines.append("Conversation history:")
    for turn in sample.history:
        if turn.role == "user":
            text = turn.audio_text if turn.audio_text is not None else "[audio, no transcript available]"
            lines.append(f"user: {text}")
        else:
            lines.append(f"assistant: {turn.text or ''} calls={json.dumps(turn.tool_calls, ensure_ascii=False)}")
    lines.append(f"Current user request (transcript): {transcript}")
    return "\n".join(lines)


def _has_leftover_name(call: dict) -> bool:
    """True if a contact-name key survived grounding: ``contact_name``
    always, or ``to`` without an '@' (an email address is not a name).
    Such keys MUST NOT be executed: validate() ignores unknown args, so
    the tool would run without the contact instead of failing."""
    args = call.get("arguments", {}) or {}
    if isinstance(args.get("contact_name"), str):
        return True
    to = args.get("to")
    return isinstance(to, str) and "@" not in to


def _needs_to_params(needs: list, tool_name: str) -> list:
    """Map adapter needs (e.g. 'time:hour', 'contact:ambiguous') to the
    ask call's params, mirroring gold ask traces. Empty needs (the
    leftover-name path) default to the contact slot."""
    slot = {
        "amount": "amount",
        "contact": "to" if tool_name == "email.create_draft" else "contact_id",
        "time": "time",
        "date": "date",
        "start": "start",
        "end": "end",
    }
    params = []
    for need in needs or []:
        head = str(need).split(":", 1)[0]
        param = slot.get(head, head)
        if param not in params:
            params.append(param)
    if not params:
        params.append("to" if tool_name == "email.create_draft" else "contact_id")
    return params


class AgentLoop:
    def __init__(self, config, tools: dict):
        self.config = config
        self.tools = tools
        self.guard = LoopGuard(max_repeats=config.max_repeats)
        self.grounding_log: list[dict] = []
        self._roster: list | None = None

    def run(
        self,
        sample: Sample,
        transcript: str,
        env: ZaicEnv,
        generator: Callable[[str, dict], dict | None],
        completion=None,
    ) -> dict:
        """Run one sample. Returns the submission line (env material)."""
        base = build_base_prompt(sample, transcript, self.tools)
        prompt = base
        executed: list[dict] = []
        results: list[dict] = []
        steps = 0
        # Grounding state is per-sample: a fresh roster and audit log for
        # every run() so no sample's contacts leak into the next one.
        self._roster = None
        self.grounding_log = []
        while steps < self.config.max_steps:
            steps += 1
            call = None
            for _attempt in range(3):  # 1 generation + up to 2 validation retries
                gen = generator(prompt, self.tools)
                if gen is None:
                    return env.submission_line()
                if isinstance(gen, dict) and gen.get("stop"):
                    return env.submission_line()
                if not isinstance(gen, dict) or "name" not in gen:
                    prompt = base + "\n\nYour last output was not a valid tool call JSON. Output one tool call or {\"stop\": true}."
                    continue
                call = {"name": gen["name"], "arguments": gen.get("arguments", {}) or {}}
                if getattr(self.config, "grounding", False):
                    # Grounding hook (round 8): normalise the proposal
                    # BEFORE validation. The adapter never guesses: a
                    # NEEDS_ASK, or a contact-name key left over because
                    # no roster exists yet, becomes an ask call instead
                    # of executing an ungrounded value. validate() is
                    # known to ignore unknown args, so the leftover-name
                    # check must live here, not in validation.
                    grounded = ground_tool_call(
                        call,
                        {"current_time": sample.context.get("current_time")},
                        roster=self._roster,
                    )
                    self.grounding_log.append({"raw": call, "grounded": grounded})
                    if grounded.status == "NEEDS_ASK" or _has_leftover_name(grounded.call):
                        call = {"name": "sys.ask_missing_info",
                                "arguments": {"tool_name": call["name"],
                                              "params": _needs_to_params(grounded.needs, call["name"])}}
                    else:
                        call = grounded.call
                check = env.validate(call["name"], call["arguments"])
                if check.get("ok"):
                    break
                prompt = render_observation_prompt(
                    base, executed + [call],
                    results + [{"ok": False, "error": f"validation failed (NOT executed, NOT submitted): {check.get('error')}"}],
                )
                call = None
            if call is None:
                return env.submission_line()
            if self.guard.repeat_count(call) >= self.guard.max_repeats:
                if self.guard._replanned:
                    return env.submission_line()
                self.guard._replanned = True
                prompt = render_observation_prompt(base, executed, results, replan=True)
                continue
            result = env.call(call["name"], call["arguments"])
            executed.append(call)
            results.append(result)
            if call["name"] == "contacts.search" and result.get("ok") \
                    and getattr(self.config, "grounding", False):
                # Accumulate the roster from OBSERVED search results only
                # (never from state files). Dedup by id; a later search
                # may extend the roster mid-trace. Gated by the grounding
                # flag so a dormant loop touches no grounding state.
                contacts = result.get("contacts")
                if isinstance(contacts, list):
                    roster = self._roster if self._roster is not None else []
                    seen = {c.get("id") for c in roster}
                    for c in contacts:
                        if isinstance(c, dict) and c.get("id") not in seen:
                            roster.append(c)
                            seen.add(c.get("id"))
                    self._roster = roster
            if completion is not None and completion(result, executed):
                return env.submission_line()
            action = self.guard.record(call, state_progress=bool(result.get("ok")))
            if action == "continue":
                prompt = render_observation_prompt(base, executed, results)
                continue
            if action == "replan_once":
                self.guard._replanned = True
                prompt = render_observation_prompt(base, executed, results, replan=True)
                continue
            return env.submission_line()
        return env.submission_line()
