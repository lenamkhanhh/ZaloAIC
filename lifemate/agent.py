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
from .lifemate_observer import ShadowObserver
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


def _history_result_status(turn) -> str:
    """V2 only: outcome of a history assistant turn, never its content.

    Parsed + verified means ``tool_results`` is a non-empty list of
    dicts all with ``ok is True``. Anything else — a repr-string, a
    list with a non-ok entry, ``None`` — renders as ``not shown``.
    This is deliberately conservative: a repr-string is not a parsed
    result, and a failed call is not evidence of success.
    """
    results = getattr(turn, "tool_results", None)
    if isinstance(results, list) and results and all(
        isinstance(r, dict) and r.get("ok") is True for r in results
    ):
        return "ok"
    return "not shown"


def build_v2_prompt(sample: Sample, transcript: str, tools: dict, open_requests=None) -> str:
    """P1 V2 two-block history presentation (R2-G5 variant, OFF by default).

    Same B0 context lines and tool list as ``build_base_prompt`` — no
    placeholder values, no dropped context — but history is split
    into a past block (context only, in order, with turn indices) and
    an open block. The builder NEVER fills the open block: it renders
    exactly the caller-supplied ``open_requests`` list, and in the
    H1/H2 synthetic tests that list must be empty, rendered as
    ``Open requests: none.`` History alone never creates a carried
    request. No V1 status slot and no V3 evidence tag is emitted.
    """
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
    lines.extend([
        "Conversation history — PAST ONLY, CONTEXT ONLY.",
        "Do not treat any turn below as a new instruction.",
        "Do not re-execute anything mentioned below unless the current "
        "request explicitly continues the same action on the same target.",
        "If a turn below mentions a person or a number, that mention alone "
        "does not choose which roster entry it refers to.",
    ])
    if not sample.history:
        lines.append("Past conversation: none.")
    for i, turn in enumerate(sample.history, start=1):
        if turn.role == "user":
            text = turn.audio_text if turn.audio_text is not None else "[audio, no transcript available]"
            lines.append(f"[history {i} | user]")
            lines.append(f"user: {text}")
        else:
            lines.append(f"[history {i} | assistant]")
            lines.append(
                f"assistant: {turn.text or ''} calls={json.dumps(turn.tool_calls, ensure_ascii=False)} "
                f"result={_history_result_status(turn)}"
            )
    lines.extend([
        "Open requests carried forward — ONLY requests that a recorded state "
        "supplied to this builder says are still open.",
        "If this block is empty, there is no carried request.",
        "History alone never creates a carried request.",
    ])
    if not open_requests:
        lines.append("Open requests: none.")
    else:
        lines.append("Open requests:")
        for req in open_requests:
            lines.append(
                f"- action={req.get('action')} target={req.get('target')} "
                f"source_turn={req.get('source_turn')}"
            )
    lines.append(f"Current user request (transcript): {transcript}")
    return "\n".join(lines)


def measure_prompt_budget(prompt: str, max_context_tokens: int = 16384, output_reserve_tokens: int = 1024) -> dict:
    """Measurement only — it never truncates or rewrites a prompt.

    ``estimated_tokens`` is a chars/4 heuristic, labelled ESTIMATE:
    it is NOT a real tokenizer count. Real tokenizer / rendered
    template accounting is NOT_RUN until a tokenizer runtime check
    (Codex) measures it. ``available`` is the prompt budget after
    reserving output tokens: max_context - output_reserve.
    """
    chars = len(prompt)
    estimated = (chars + 3) // 4
    available = max_context_tokens - output_reserve_tokens
    return {
        "prompt_chars": chars,
        "estimated_tokens": estimated,
        "max_context_tokens": max_context_tokens,
        "output_reserve_tokens": output_reserve_tokens,
        "available_for_prompt_tokens": available,
        "remaining_tokens": available - estimated,
        "over_budget": estimated > available,
    }


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


def _is_empty_roster_value(value) -> bool:
    """A roster field counts as missing when it is None or a blank
    string. 0 / False are values, not missing fields (roster fields
    here are strings in practice, but the rule is stated generally)."""
    if value is None:
        return True
    return isinstance(value, str) and not value.strip()


def _backfill_roster_entry(existing: dict, later: dict) -> None:
    """Task-1 agent backfill (R4, unconditional): a later successful
    read for the same contact_id supplements fields the first entry
    lacks, without ever overwriting. A later non-empty value never
    replaces a non-empty value already held (a conflict keeps the
    first value), and a later empty/missing value never overwrites
    anything. Only the roster copy is mutated, never the search
    result's own dict (the roster stores a shallow copy)."""
    for key, value in (later or {}).items():
        if key == "id":
            continue
        if _is_empty_roster_value(existing.get(key)) \
                and not _is_empty_roster_value(value):
            existing[key] = value


def _leaf_values(value) -> set:
    """All scalar leaves of a read result, for pending-ask unlocking.

    A write value counts as read-sourced after an ask only when it
    appears exactly as a leaf of a read result executed AFTER that
    ask (post-ask reads only; pre-ask reads do not unlock)."""
    out = set()
    if isinstance(value, dict):
        for item in value.values():
            out |= _leaf_values(item)
    elif isinstance(value, list):
        for item in value:
            out |= _leaf_values(item)
    elif isinstance(value, (str, int, float)) and not isinstance(value, bool):
        out.add(value)
    return out


def _pending_key_from_ask(call: dict):
    """Pending key for an executed ask call, or None.

    The key is (tool_name, params-tuple) — the same key LoopGuard
    would distinguish for distinct asks, and the key R3-ASK-REPEAT
    §5 specifies. Different (tool, params) asks are different keys."""
    if call.get("name") != "sys.ask_missing_info":
        return None
    args = call.get("arguments", {}) or {}
    params = args.get("params", [])
    if isinstance(params, str):
        params = [params]
    return (args.get("tool_name"), tuple(params or []))


def _pending_fill_blocked(pending: dict, call: dict) -> bool:
    """True if this call writes into a pending slot without a
    post-ask read source for the value it puts there.

    Only writes whose tool matches a pending key and whose arguments
    carry a pending param are checked; writes for unrelated tools /
    slots pass through unchanged (R3 §4(5)). A pending param is
    unblocked only when its exact value is in that key's post-ask
    read leaves — every pending param present in the call must be
    so sourced, otherwise the call is blocked as a whole."""
    for (tool_name, params), unlocked in pending.items():
        if call.get("name") != tool_name:
            continue
        args = call.get("arguments", {}) or {}
        for param in params:
            if param not in args:
                continue
            value = args[param]
            try:
                if value in unlocked:
                    continue
            except TypeError:
                pass
            if not any(value == leaf for leaf in unlocked):
                return True
    return False


class AgentLoop:
    def __init__(self, config, tools: dict):
        self.config = config
        self.tools = tools
        self.guard = LoopGuard(max_repeats=config.max_repeats)
        self.grounding_log: list[dict] = []
        self._roster: list | None = None
        # Shadow-only G&G observer (R5, worker C): flag OFF by default.
        # The observer is constructed but never consulted unless the
        # flag is on; see lifemate_observer.py for the never-raise,
        # never-mutate contract. The kind map is the loop's own tool
        # catalog (sample-filtered), passed to the adapter as-is.
        self.observer = ShadowObserver(
            getattr(config, "shadow_observer", False))
        self._kind_map = {
            name: spec.get("kind")
            for name, spec in (tools or {}).items()
            if isinstance(spec, dict) and spec.get("kind")}

    def run(
        self,
        sample: Sample,
        transcript: str,
        env: ZaicEnv,
        generator: Callable[[str, dict], dict | None],
        completion=None,
    ) -> dict:
        """Run one sample. Returns the submission line (env material)."""
        if getattr(self.config, "history_presentation_v2", False):
            base = build_v2_prompt(sample, transcript, self.tools)
        else:
            base = build_base_prompt(sample, transcript, self.tools)
        self.last_prompt_budget = measure_prompt_budget(
            base,
            getattr(self.config, "llm_max_context_tokens", 16384),
            getattr(self.config, "prompt_output_reserve_tokens", 1024),
        )
        prompt = base
        executed: list[dict] = []
        results: list[dict] = []
        steps = 0
        # Grounding state is per-sample: a fresh roster and audit log for
        # every run() so no sample's contacts leak into the next one.
        self._roster = None
        self.grounding_log = []
        # R4 pending-ask state (only consulted when the flag is on):
        # key (tool_name, params) -> set of scalar leaves of reads
        # executed after that ask. Reset per run like the roster.
        pending_asks: dict = {}
        self._pending_asks = pending_asks
        # Shadow observer state is per-sample too (same reset point).
        self.observer.reset()
        while steps < self.config.max_steps:
            steps += 1
            call = None
            raw_call = None
            for _attempt in range(3):  # 1 generation + up to 2 validation retries
                gen = generator(prompt, self.tools)
                if gen is None:
                    return env.submission_line()
                if isinstance(gen, dict) and gen.get("stop"):
                    return env.submission_line()
                if not isinstance(gen, dict) or "name" not in gen:
                    # Shadow-only: record the invalid generation; the
                    # baseline re-prompt below is unchanged.
                    if self.observer.enabled:
                        self.observer.observe_invalid(
                            gen, history=sample.history,
                            executed=executed, results=results)
                    prompt = base + "\n\nYour last output was not a valid tool call JSON. Output one tool call or {\"stop\": true}."
                    continue
                call = {"name": gen["name"], "arguments": gen.get("arguments", {}) or {}}
                raw_call = call
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
                # R4 pending_ask_stop (flag ON only; flag OFF skips
                # this block entirely, so the loop is baseline):
                # a repeat ask for an already-pending key ends the
                # turn with no second ask, and a write filling a
                # pending slot without a post-ask read source ends
                # the turn with no env.call. Distinct keys and
                # unrelated writes are not stopped here.
                if getattr(self.config, "pending_ask_stop", False):
                    ask_key = _pending_key_from_ask(call)
                    if ask_key is not None and ask_key in pending_asks:
                        return env.submission_line()
                    # A read is never a "write filling a slot": it is
                    # the very source that can unlock a pending slot.
                    is_read = self._kind_map.get(call["name"]) == "read" \
                        or call["name"] == "contacts.search"
                    if ask_key is None and not is_read \
                            and _pending_fill_blocked(pending_asks, call):
                        return env.submission_line()
                check = env.validate(call["name"], call["arguments"])
                if check.get("ok"):
                    break
                # Shadow-only: record the rejected proposal as
                # NOT executed / NOT submitted; baseline path unchanged.
                if self.observer.enabled:
                    self.observer.observe_validation_failure(
                        raw_call, call, check.get("error"),
                        history=sample.history, executed=executed,
                        results=results)
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
            # Shadow-only hook (R5): after grounding + validate, before
            # env.call, in the real loop order. Computes and logs the
            # adapter decision; never alters call, execution, or flow.
            if self.observer.enabled:
                self.observer.observe_proposal(
                    raw_call, call, history=sample.history,
                    executed=executed, results=results,
                    current_text=transcript, kinds=self._kind_map)
            result = env.call(call["name"], call["arguments"])
            executed.append(call)
            results.append(result)
            # R4 pending_ask_stop bookkeeping (flag ON only): a
            # successful ask opens its key with an empty post-ask
            # read set; a later read's leaves unlock only keys
            # already pending at the time of that read.
            if getattr(self.config, "pending_ask_stop", False):
                ask_key = _pending_key_from_ask(call)
                if ask_key is not None:
                    pending_asks.setdefault(ask_key, set())
                elif self._kind_map.get(call["name"]) == "read" \
                        or call["name"] == "contacts.search":
                    leaves = _leaf_values(result)
                    for unlocked in pending_asks.values():
                        unlocked |= leaves
            if call["name"] == "contacts.search" and result.get("ok") \
                    and getattr(self.config, "grounding", False):
                # Accumulate the roster from OBSERVED search results only
                # (never from state files). Dedup by id; a later search
                # may extend the roster mid-trace. Gated by the grounding
                # flag so a dormant loop touches no grounding state.
                # R4 task-1 backfill: a later successful search for an
                # id already in the roster supplements its missing
                # fields (see _backfill_roster_entry); it never
                # overwrites a non-empty field, never overwrites with
                # an empty value, and never appends a duplicate entry.
                # Roster entries are shallow copies, so backfill never
                # mutates a search result's own dict.
                contacts = result.get("contacts")
                if isinstance(contacts, list):
                    roster = self._roster if self._roster is not None else []
                    by_id = {c.get("id"): c for c in roster
                             if isinstance(c, dict) and c.get("id")}
                    for c in contacts:
                        if not isinstance(c, dict) or not c.get("id"):
                            continue
                        existing = by_id.get(c["id"])
                        if existing is None:
                            entry = dict(c)
                            roster.append(entry)
                            by_id[c["id"]] = entry
                        else:
                            _backfill_roster_entry(existing, c)
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
