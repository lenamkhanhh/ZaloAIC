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


def _norm_phone_digits(value):
    """Digits-only phone, mirroring lifemate_phone_callback_evidence
    .norm_phone for string input: an 11-digit "84..." form folds
    to a 10-digit 0-number. Non-string input yields "" (no
    coercion)."""
    if not isinstance(value, str):
        return ""
    digits = "".join(ch for ch in value if ch.isdigit())
    if digits.startswith("84") and len(digits) == 11:
        return "0" + digits[2:]
    return digits


def _valid_phone(value):
    """Roster-phone contract (R3-P0-PHONE, field "phone"): after
    norm, 0-led and 10 or 11 digits. Anything else is ignored,
    never coerced."""
    digits = _norm_phone_digits(value)
    return digits.startswith("0") and len(digits) in (10, 11)


def _valid_text(value):
    """A name/relation value carries information only when it is
    a string with a non-blank stripped form. Non-strings are
    never coerced; blank strings carry no information."""
    return isinstance(value, str) and bool(value.strip())


def _is_empty_roster_value(value) -> bool:
    """A roster field counts as missing when it is None or
    the empty string "" (unified rule, same as the observer
    and the harness). A blank string " " is not "" -- it is
    never a valid replacement value (see _valid_text), so
    it can neither fill nor overwrite a field, but an
    existing blank value is not rewritten by this helper
    alone; collectors normalise blank values away before
    any merge (see _agent_roster_entry). 0 / False are
    values, not missing fields (roster fields here are
    strings in practice, but the rule is stated generally)."""
    if value is None:
        return True
    return isinstance(value, str) and value == ""


def _agent_roster_entry(entry):
    """One roster entry, on the whitelist only, or None.
    Exactly id/name/phone/relation: ``name`` is the raw
    string when valid, else "" (missing); ``phone`` is the
    raw string when it passes the phone contract, else ""
    (missing); ``relation`` is present only when valid.
    Every other field is dropped -- the old code copied
    the whole search-result dict, so a stray ``note``
    survived in the agent roster; it no longer does. An
    entry with no id is not roster evidence."""
    if not isinstance(entry, dict) or not entry.get("id"):
        return None
    contact = {"id": entry["id"],
               "name": entry["name"] if _valid_text(
                   entry.get("name")) else "",
               "phone": entry["phone"] if _valid_phone(
                   entry.get("phone")) else ""}
    if _valid_text(entry.get("relation")):
        contact["relation"] = entry["relation"]
    return contact


# ---------------------------------------------------------------------------
# Unified roster conflict rule (R4-CONFLICT, same rule in all three
# roster paths: this agent roster, lifemate/lifemate_observer.py,
# and analysis/gg_paired_audit.py -- the modules cannot import
# each other, so the rule is stated in full in each place and
# must stay identical):
#
# 1. LAST-WINS, IN ORDER. For the same registry
#    ("contacts.contacts") and contact_id, a valid field from
#    a NEWER successful read replaces the older value.
#    Order is the order of observed searches in the run
#    (execution order), never the system clock. A merged
#    roster is a current-state view at proposal time, not
#    a freeze at first sight.
# 2. A field the newer read does not carry does NOT delete
#    the older value: absence in a read is not a deletion
#    signal (a later search may be a different query
#    returning a subset). The older value is kept.
# 3. A failed / noop read creates, updates, or deletes
#    nothing. In this path, a search contributes only
#    when its result is ok-truthy and grounding is on
#    (the loop's existing gate, unchanged).
# 4. Empty / null is missing, never a deletion: a missing
#    or invalid newer value never overwrites and never
#    deletes an older value.
# 5. LIFECYCLE BARRIER, PER FIELD. A succeeded
#    contacts.update whose returned item id equals its
#    contact_id argument is lifecycle-confirmed
#    post-mutation state (the adapter's PATCH_VERIFIED rule:
#    a succeeded patch provably looked the entity up, so its
#    returned fields are not an echo). Such an event is a
#    barrier for the whitelisted valid fields it returns:
#    pre-barrier values for those fields are discarded and
#    are never re-applied after the barrier. A later read
#    that AGREES with the confirmed value keeps it (and
#    re-establishes it if it was UNKNOWN); a later read
#    that CONTRADICTS the confirmed value does NOT
#    overwrite it and does NOT revert it -- that field
#    becomes UNKNOWN (dropped from the roster entry, with
#    a conflict record carrying the reason), so it cannot
#    be used to choose a person until a later barrier or
#    an agreeing read re-establishes it. A barrier for one
#    field touches no other field: contacts.update patches
#    phone/email only, so a phone barrier never wipes a
#    relation the update never touched.
#    "Lifecycle-confirmed" here means ONLY that
#    patch-verified shape above. It does NOT mean: a
#    failed update, an update whose item id differs from
#    its contact_id argument, an update result with no
#    item, a user turn mentioning a change, a cancelled /
#    replaced instruction (which governs instructions, not
#    roster attributes), or absence from a later search.
#    There is no contacts.delete in the tool catalog today,
#    so no delete event can be a barrier in this code;
#    absence is never treated as a deletion.
# 6. UNKNOWN WHEN ORDER / SOURCE CANNOT BE ESTABLISHED.
#    Two cases, both fail-closed: (a) a single successful
#    read contains the same id twice with different valid
#    values for one field -- the two values share one
#    position and one event, so no order between them can
#    be established, and last-wins cannot pick; that field
#    becomes UNKNOWN (dropped, conflict recorded), even if
#    an older value existed. (b) a post-barrier read
#    contradicts a barrier value (rule 5). In both cases
#    the roster entry must NOT be used to choose a person
#    via that field: grounding falls back to asking rather
#    than guessing, and the adapter blocks on a missing /
#    unqualified descriptor or phone, it does not pass on
#    the stale or ambiguous value. A later unambiguous
#    read (different event, single value) or a later
#    barrier re-establishes an UNKNOWN field; a missing
#    value in a later read does not.
# 7. Only id/name/phone/relation ever reach a merge, and
#    only valid values (rule 8) are ever applied.
# 8. Missing = absent, None, or "" (name/phone); relation
#    missing = absent. A wrong-type value (non-string
#    name/relation, phone failing the contract) is ignored:
#    no coercion, no overwrite, no deletion. A stray field
#    is dropped at collection, before any merge.
#
# Conflict records live OUTSIDE the roster list (a roster
# entry must stay whitelist-only: the D1 qualifier reads
# every field other than id/name/phone as a structured
# attribute, and grounding reads id/name from it, so a
# conflict/reason field inside an entry could itself
# become evidence). They are on AgentLoop.roster_conflicts
# (per run, reset with the roster) and are never part of
# the submission.
# ---------------------------------------------------------------------------

_ROSTER_FIELDS = ("name", "phone", "relation")


def _new_roster_state():
    """Fresh merge state: entries (the roster list, in
    first-seen order), barriers {id: {field: confirmed}},
    unknown {id: set(fields)}, conflicts [records]."""
    return {"entries": [], "barriers": {}, "unknown": {},
            "conflicts": [], "seq": 0}


def _entry_by_id(state, contact_id):
    for entry in state["entries"]:
        if entry["id"] == contact_id:
            return entry
    return None


def _drop_field(entry, field):
    """Drop a field from a roster entry, in the entry's own
    missing form: name/phone become "", relation is removed."""
    if field == "relation":
        entry.pop("relation", None)
    else:
        entry[field] = ""


def _group_read_entries(entries):
    """Group one read event's entries by id, in first-seen
    order. Returns (grouped, unknown_map): grouped is one
    entry per id with the event's valid values; unknown_map
    is {id: set(fields)} for fields that conflict WITHIN
    this single read (rule 6a) -- those fields are dropped
    from the grouped entry. Repeated identical values are
    not a conflict; a field carried by only one duplicate
    is not a conflict (absence in a duplicate is not a
    value)."""
    grouped = []
    by_id = {}
    unknown_map = {}
    for entry in entries:
        if entry is None:
            continue
        existing = by_id.get(entry["id"])
        if existing is None:
            existing = dict(entry)
            by_id[entry["id"]] = existing
            grouped.append(existing)
            continue
        for field in _ROSTER_FIELDS:
            if field not in entry:
                continue
            new = entry[field]
            if new is None or new == "":
                continue
            if field not in existing:
                existing[field] = new
            elif existing[field] is None or existing[field] == "":
                # A normalised "" is missing, not a value:
                # filling it is not a conflict.
                existing[field] = new
            elif existing[field] != new:
                unknown_map.setdefault(entry["id"], set()).add(field)
                _drop_field(existing, field)
    return grouped, unknown_map


def _merge_group_into_state(state, grouped, unknown_map):
    """Merge one read event's grouped entries into state,
    in execution order (rule 1). The event's sequence
    number is state["seq"], incremented per event."""
    seq = state["seq"]
    state["seq"] += 1
    for entry in grouped:
        contact_id = entry["id"]
        existing = _entry_by_id(state, contact_id)
        if existing is None:
            existing = {"id": contact_id, "name": "",
                        "phone": ""}
            state["entries"].append(existing)
        unknown_fields = unknown_map.get(contact_id, set())
        barriers = state["barriers"].get(contact_id, {})
        unknown = state["unknown"].setdefault(contact_id, set())
        for field in _ROSTER_FIELDS:
            if field in unknown_fields:
                old = existing.get(field)
                _drop_field(existing, field)
                unknown.add(field)
                state["conflicts"].append({
                    "contact_id": contact_id, "field": field,
                    "old": old, "new": None,
                    "reason": "intra_read_conflict_unknown",
                    "seq": seq,
                    "detail": "one read contains conflicting "
                    "values for this field; no order can be "
                    "established, so the field is UNKNOWN, "
                    "not last-wins and not keep-first"})
                continue
            if field not in entry:
                continue
            new = entry[field]
            if new is None or new == "":
                continue
            if field in barriers:
                confirmed = barriers[field]
                if new == confirmed:
                    if field in unknown:
                        existing[field] = confirmed
                        unknown.discard(field)
                    elif existing.get(field) != confirmed:
                        existing[field] = confirmed
                    continue
                old = existing.get(field)
                _drop_field(existing, field)
                unknown.add(field)
                state["conflicts"].append({
                    "contact_id": contact_id, "field": field,
                    "old": confirmed, "new": new,
                    "reason": "barrier_contradiction_unknown",
                    "seq": seq,
                    "detail": "post-barrier read contradicts "
                    "lifecycle-confirmed value from a "
                    "succeeded contacts.update; field is "
                    "UNKNOWN, neither overwritten nor "
                    "reverted"})
                continue
            if field in unknown:
                existing[field] = new
                unknown.discard(field)
                continue
            old = existing.get(field)
            if old is None or old == "":
                existing[field] = new
            elif old != new:
                existing[field] = new
                state["conflicts"].append({
                    "contact_id": contact_id, "field": field,
                    "old": old, "new": new,
                    "reason": "last_wins",
                    "seq": seq,
                    "detail": "later successful read replaces "
                    "earlier value for the same id"})
            # else: equal -- keep.


def _apply_barrier_to_state(state, barrier_entry):
    """Apply a lifecycle-confirmed contacts.update to state
    (rule 5). ``barrier_entry`` is a normalised roster
    entry built from the update's returned item. Only its
    present valid fields become barriers, and only those
    fields are overwritten (pre-barrier values for those
    fields are discarded); other fields are untouched, and
    an UNKNOWN for a barrier field is cleared by the
    confirmed value. A barrier is not a conflict and is
    not recorded in conflicts."""
    seq = state["seq"]
    state["seq"] += 1
    contact_id = barrier_entry["id"]
    existing = _entry_by_id(state, contact_id)
    if existing is None:
        existing = {"id": contact_id, "name": "", "phone": ""}
        state["entries"].append(existing)
    barriers = state["barriers"].setdefault(contact_id, {})
    unknown = state["unknown"].setdefault(contact_id, set())
    for field in _ROSTER_FIELDS:
        if field not in barrier_entry:
            continue
        # A normalised entry always carries name/phone keys,
        # with "" for missing: "" is NOT a confirmed value
        # and must never become a barrier or overwrite a
        # value the update never touched.
        if barrier_entry[field] is None or barrier_entry[field] == "":
            continue
        barriers[field] = barrier_entry[field]
        existing[field] = barrier_entry[field]
        unknown.discard(field)


def _barrier_entry_from_update(args, result):
    """Lifecycle-confirmed barrier entry for a contacts.update
    event, or None. Confirmed means: its contact_id argument
    is truthy, and its returned item is a dict whose id
    equals that argument (the PATCH_VERIFIED shape). The
    barrier fields are the item's whitelisted valid fields,
    normalised by _agent_roster_entry. Anything else --
    an id mismatch, no item, an invalid field value --
    yields no barrier at all (never a partial barrier from
    an unconfirmed value). Callers check success
    separately, per their path's success definition."""
    if not isinstance(args, dict) or not args.get("contact_id"):
        return None
    if not isinstance(result, dict):
        return None
    item = result.get("item")
    if not isinstance(item, dict) or item.get("id") != args.get(
            "contact_id"):
        return None
    return _agent_roster_entry(item)


def _backfill_roster_entry(existing: dict, later: dict) -> None:
    """Backward-compatible single-entry merge, now LAST-WINS
    (rule 1), not keep-first: a missing field is filled, an
    equal value is kept, and a different valid value from
    the later entry replaces the older one. Missing values
    never overwrite. Implemented via the state core so the
    single-entry path cannot drift from the grouped path;
    barrier and UNKNOWN state are not carried by this
    wrapper (callers that need them use the state
    functions). Only the roster copy is mutated, never the
    search result's own dict (the roster stores a copy)."""
    state = _new_roster_state()
    state["entries"].append(existing)
    grouped, unknown_map = _group_read_entries([dict(later)])
    _merge_group_into_state(state, grouped, unknown_map)


class AgentLoop:
    def __init__(self, config, tools: dict):
        self.config = config
        self.tools = tools
        self.guard = LoopGuard(max_repeats=config.max_repeats)
        self.grounding_log: list[dict] = []
        self._roster: list | None = None
        # R4-CONFLICT merge state for the grounding roster
        # (per run, reset with the roster): entries is the
        # roster list itself, conflicts are the unified
        # rule's conflict records (last_wins / UNKNOWN).
        # roster_conflicts is never part of a submission.
        self._roster_state = _new_roster_state()
        self.roster_conflicts = self._roster_state["conflicts"]
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
        # _roster stays None until the first successful search (or
        # barrier) in the run, exactly as before: grounding treats
        # None (no roster yet) differently from [] (a roster that
        # exists but is empty), and a dormant loop must keep
        # _roster None. The state entries list becomes the
        # roster on first use, so grounding then sees the live
        # merged list.
        self._roster_state = _new_roster_state()
        self._roster = None
        self.roster_conflicts = self._roster_state["conflicts"]
        self.grounding_log = []
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
            # R4 pending_ask_stop, REVISED contract (flag ON only;
            # flag OFF skips this block entirely):
            # a sys.ask_missing_info that env.call executes
            # SUCCESSFULLY (result ok is True, as the real adapter
            # returns for an ask: ok True + waiting_for_user) ends
            # the turn IMMEDIATELY, with the ask kept in the
            # submission. The generator is not called again, and no
            # read / write / further ask runs after that ask.
            # This is deliberately NOT a pending-key / post-ask-read
            # rule any more: there is no read-leaf unlock, no
            # distinct-key allowance after an ask, and no fill
            # blocking to evaluate, because the turn is already
            # over. An ask that validation rejects never reaches
            # env.call, so it cannot trigger this rule; an ask
            # whose env.call returns ok False is not successful,
            # so it falls through to the old flow below (guard /
            # re-prompt) instead of ending the turn by this rule.
            if getattr(self.config, "pending_ask_stop", False) \
                    and call["name"] == "sys.ask_missing_info" \
                    and result.get("ok") is True:
                return env.submission_line()
            if call["name"] == "contacts.search" and result.get("ok") \
                    and getattr(self.config, "grounding", False):
                # Accumulate the roster from OBSERVED search results only
                # (never from state files). Gated by the grounding
                # flag so a dormant loop touches no grounding state.
                # R4-CONFLICT unified rule: a later successful search
                # for an id already in the roster fills its missing
                # fields and replaces a differing valid field
                # (last-wins, in execution order); it never
                # overwrites with a missing/invalid value, never
                # appends a duplicate entry, and a single read
                # contradicting itself makes that field UNKNOWN.
                # Roster entries are normalised copies (whitelist
                # only), so merging never mutates a search
                # result's own dict, and stray fields never
                # survive into the roster.
                if self._roster is None:
                    self._roster = self._roster_state["entries"]
                contacts = result.get("contacts")
                if isinstance(contacts, list):
                    entries = []
                    for c in contacts:
                        entry = _agent_roster_entry(c)
                        if entry is not None:
                            entries.append(entry)
                    if entries:
                        grouped, unknown_map = \
                            _group_read_entries(entries)
                        _merge_group_into_state(
                            self._roster_state, grouped, unknown_map)
            if call["name"] == "contacts.update" and result.get("ok") \
                    and getattr(self.config, "grounding", False):
                # R4-CONFLICT lifecycle barrier (rule 5): a
                # succeeded contacts.update whose returned item
                # id equals its contact_id argument confirms
                # post-mutation fields for that id. Gated by
                # the grounding flag, like searches, so a
                # dormant loop touches no grounding state.
                if self._roster is None:
                    self._roster = self._roster_state["entries"]
                barrier = _barrier_entry_from_update(
                    call.get("arguments") or {}, result)
                if barrier is not None:
                    _apply_barrier_to_state(
                        self._roster_state, barrier)
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
