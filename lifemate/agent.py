"""Agent loop for LifeMate — observation after EVERY call.

Generator protocol (the model, or a test double): a callable
``gen(prompt: str, tools: dict) -> dict | None`` returning one tool
call ``{"name": ..., "arguments": {...}}`` or ``None`` to stop. The
loop owns everything else: prompt construction, pre-call validation,
execution, observation injection, loop guard, termination.

Loop semantics (same as deep-dives/01, now with the 2026-10-27 review
fix applied here and there):

- After EVERY executed call, the next prompt is rebuilt with ALL
  observations so far (``name(args) -> ok/error/output``, complete
  compact JSON). Previously observation only entered the
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
from .loader import Sample, catalog_tools_for_sample
from .grounding import ground_arguments
from .llm import is_stop_signal


ACTION_POLICY = """Action policy (apply to the CURRENT request, not old requests in history):
1. Identify the user's final intent, corrections, cancellations and each requested action. Do not add follow-up actions the user did not request. A cancelled sole request, chat, or an unavailable capability needs no tool call; output {"stop":true}.
2. Evaluate conditions BEFORE their dependent writes. Resolve the target date/location using current_time and context. Reuse a still-valid matching observation in history; otherwise read the needed fact first. Do not execute both branches. If the selected branch requests no action, stop.
3. Resolve entities BEFORE acting. Use catalog x-ref IDs from matching observed collections or an ID explicitly provided by the user. Names are not IDs. Read/search when an entity is not yet resolved. One returned entity is not proof of user intent: check name/relation/room and the request. Several candidates require a unique explicit discriminator or sys.ask_missing_info; do not pick the first.
4. Every argument needs evidence: the user's request/context, applicable history, a tool result, a schema default, or a calculation from those facts. Never invent phone numbers, amounts or dates/times. Read a bill/balance/event when the request refers to its value. Missing required information that cannot be obtained by a relevant read must be asked using sys.ask_missing_info with the exact tool_name and missing params. Do not assume the current time is a requested reminder time.
5. Tool results with done:false did NOT complete the requested action even if ok:true. Change the plan using evidence; do not repeat the same failed call. A created reminder is not a completed reminder: do not mark it done unless the user requested completion. A condition written into a label does not make an immediate write conditional.
6. After all requested actions of the selected branch succeed, output {"stop":true}. Do not undo, mark complete, recreate or verify writes without a separate need in this request. Repeat an identical action only if the user explicitly requested multiple instances; otherwise avoid duplicate calls. sys.ask_missing_info ends this turn while waiting for the user.
Output exactly one tool-call JSON or {"stop":true}; no invented tool named stop, no narrative, no list of calls."""


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
        outcome = ("not_done" if result.get("ok") and result.get("done") is False else
                   "ok" if result.get("ok") else f"error: {result.get('error')}")
        # All fields remain available, including phone/relation/amount/text.
        # The LLM backend enforces the prompt+output cap; never silently clip.
        output = json.dumps(result, ensure_ascii=False, separators=(",", ":"))
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
        "previous tool results in this conversation or explicit user input.",
        ACTION_POLICY,
        f"Current time: {ctx.get('current_time')} ({ctx.get('timezone')}).",
        f"User: {profile.get('name', '')}, city {profile.get('city', '')}.",
        "User-provided context: " + json.dumps(ctx, ensure_ascii=False),
        "Tools you may call (this sample only):",
    ]
    for name, spec in sorted(tools.items()):
        lines.append(json.dumps({"name": name, "kind": spec["kind"],
                                 "description": spec.get("description", ""),
                                 "parameters": spec["parameters"],
                                 "returns": spec.get("returns", "")}, ensure_ascii=False))
    lines.append("Conversation history:")
    for turn in sample.history:
        if turn.role == "user":
            text = turn.audio_text if turn.audio_text is not None else "[audio, no transcript available]"
            lines.append(f"user: {text}")
        else:
            lines.append(f"assistant: {turn.text or ''} calls={json.dumps(turn.tool_calls, ensure_ascii=False)} "
                         f"results={turn.tool_results!r}")
    lines.append(f"Current user request (transcript): {transcript}")
    return "\n".join(lines)


class AgentLoop:
    def __init__(self, config, tools: dict):
        self.config = config
        self.tools = tools
        self.guard = LoopGuard(max_repeats=config.max_repeats)

    def run(
        self,
        sample: Sample,
        transcript: str,
        env: ZaicEnv,
        generator: Callable[[str, dict], dict | None],
        completion=None,
        *, protocol=None,
    ) -> dict:
        """Run one sample. Returns the submission line (env material)."""
        base = build_base_prompt(sample, transcript, self.tools)
        if self.config.selective_reads:
            base += "\nRead only to resolve a missing entity or precondition; reuse still-valid observations."
        if not self.config.verification_read_after_write:
            base += "\nDo not add a verification read after a write unless the next action needs its result."
        if protocol is not None:
            base = protocol.base(base, self.tools)
        def observe(calls, outputs, replan=False):
            if protocol is not None:
                return protocol.render(base, calls, outputs, replan)
            return render_observation_prompt(base, calls, outputs, replan)
        prompt = base
        executed: list[dict] = []
        results: list[dict] = []
        steps = 0
        while steps < self.config.max_steps:
            steps += 1
            call = None
            for _attempt in range(3):  # 1 generation + up to 2 validation retries
                gen = generator(prompt, self.tools)
                if gen is None:
                    return env.submission_line()
                if is_stop_signal(gen):
                    return env.submission_line()
                if not isinstance(gen, dict) or "name" not in gen:
                    prompt = observe(executed, results)
                    error = "Your last output was not a valid tool call JSON. Output one tool call or {\"stop\": true}."
                    prompt = protocol.feedback(prompt, error) if protocol is not None else prompt + "\n\n" + error
                    continue
                call = {"name": gen["name"], "arguments": gen.get("arguments", {}) or {}}
                if self.config.grounding:
                    call, errors = ground_arguments(call, self.tools, executed, results,
                                                    history=sample.history, transcript=transcript,
                                                    context=sample.context)
                else:
                    errors = []
                check = ({"ok": False, "error": "; ".join(errors)} if errors else
                         env.validate(call["name"], call["arguments"]))
                if check.get("ok"):
                    break
                prompt = observe(
                    executed + [call],
                    results + [{"ok": False, "error": f"validation failed (NOT executed, NOT submitted): {check.get('error')}"}],
                )
                call = None
            if call is None:
                return env.submission_line()
            if self.guard.repeat_count(call) >= self.guard.max_repeats:
                if self.guard._replanned:
                    return env.submission_line()
                self.guard._replanned = True
                prompt = observe(executed, results, replan=True)
                continue
            result = env.call(call["name"], call["arguments"])
            executed.append(call)
            results.append(result)
            if call["name"] == "sys.ask_missing_info" and result.get("ok"):
                return env.submission_line()
            if completion is not None and completion(result, executed):
                return env.submission_line()
            action = self.guard.record(call, state_progress=bool(result.get("ok")))
            if action == "continue":
                prompt = observe(executed, results)
                continue
            if action == "replan_once":
                self.guard._replanned = True
                prompt = observe(executed, results, replan=True)
                continue
            return env.submission_line()
        return env.submission_line()
