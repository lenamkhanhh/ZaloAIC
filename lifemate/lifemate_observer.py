"""Shadow-only G&G observer for the LifeMate agent loop (R5, worker C).

The observer computes the coordinator-owned adapter decision
(``lifemate_gates_adapter.decide``) for proposals that reach the
agent loop, and LOGS it. It NEVER changes agent behaviour:

- Flag OFF (default): the loop checks ``observer.enabled`` first and
  skips every observer call, so no observer code runs at all.
- Flag ON: the observer records one JSON-serialisable record per
  observed generation. It never mutates the proposal, the grounded
  call, validation, submitted calls, state, retry count, termination,
  or prompt ordering. It never inserts an ask, never rewrites
  arguments, never calls extra tools.
- The observer NEVER raises: every public method catches all
  exceptions internally and records them in the record's ``error``
  field (or drops the record only if even recording fails, which
  cannot happen for a plain list append). An observer exception must
  never become an agent error.

Allowed inputs ONLY: the current transcript, permitted context
(the loop's tools/kind map), history, and prior observations
(executed calls + their results). FORBIDDEN: gold labels, future
results, environment internals/state. The observer never calls
``env`` methods; it rebuilds its prefix from what the loop already
observed (history + executed/results), mirroring the paired audit's
prefix construction (see ``build_prefix``). Roster evidence is built
from observed contacts.search results in that same prefix, NOT from
the loop's grounding roster, so the observer is independent of the
grounding flag.

Record schema (exactly these keys, all JSON-serialisable):

- ``proposal_raw``: the generator's proposal before grounding
  (or the raw generator output for invalid generations).
- ``proposal_grounded``: the call that went to validation (after
  grounding / ask conversion), or None when there is none.
- ``validation_outcome``: "ok" | "failed" | "invalid".
  "failed" means validation rejected the call: it was NOT executed
  and NOT submitted. "invalid" means the generator output was not a
  usable tool call (non-dict or missing "name").
- ``baseline_decision``: {"fired", "applicable", "reason"} from the
  adapter's baseline gate, or None when no decision was computed
  (ask proposals, validation failures, invalid generations, or an
  observer error).
- ``candidate_decision``: {"fired", "applicable"} from the adapter,
  or None as above.
- ``adjustments``: the adapter's adjustment trail (list of dicts),
  or [] when no decision was computed.
- ``eligibility``: the adapter's R5 object-state eligibility report
  ({consumer, entity_id, status, reason}) when a decision was
  computed with eligibility enabled, else None. Report-only: it
  never changes fired/applicable. Unknown means unsupported
  consumer, missing entity, or missing context — never a guess.
- ``error``: None on success, else ``repr`` of the exception that
  prevented a decision (import failure, unparseable history, adapter
  exception, ...). An error record still proves the agent ran
  unchanged: the proposal flowed through the baseline path.
- ``position``: the evidence position of the proposal
  (``proposal_position`` passed to the adapter: max prefix position
  + 1). This is NOT a unique sequence number: two failed attempts at
  the same evidence position share it, because neither entered the
  prefix. Record order (list order) is the observation order.
- ``selection_decision``: PRESENT ONLY on a decided record
  whose adapter notes carry a ``selection_decision`` dict, and
  then it is a whole copy of that dict (``decision``,
  ``unknown_kind`` when present, ``active_status``,
  ``blocked_subtype``, ``mismatch`` when present,
  ``last_event`` when present -- whatever fields the adapter
  set, copied verbatim, never normalised or synthesised).
  Records without a selection_decision in the adapter notes
  carry NO such key, so their shape is exactly the old 9-key
  shape: this is the compatible form of the additive copy.
  Adding the key unconditionally would change every record's
  schema and break the strict 9-key validator in
  ``lifemate/shadow_export.py`` (a file owned elsewhere, not
  edited here); a consumer that wants to accept the new field
  must update that validator. The field is report-only, like
  ``eligibility``: it never changes fired/applicable, and the
  observer stays shadow-only.

Import safety: this module imports ONLY the standard library at
module level. The coordinator-owned adapter is imported LAZILY
inside ``_get_decide`` and only when flag ON and a decision is
actually needed. The adapter and its dependencies use
intra-package relative imports, and every outside consumer
(scripts, tests, entrypoints) imports them as ``lifemate.*``
with the repo root on ``sys.path`` -- the same contract as the
real entrypoint (``lifemate/run.py``). Adding lifemate/ itself
to ``sys.path`` is NOT required and must not be relied on: a
record with an import error in a clean process means the
contract is broken, not that the observer is "working". If the
import fails, the record carries the error and the agent keeps
its baseline behaviour.
"""
from __future__ import annotations

import json

ASK_TOOL = "sys.ask_missing_info"

_decide_cache = {"fn": None}


def _get_decide():
    """Return the coordinator-owned adapter decide(), importing it
    lazily and caching success. Raises on import failure; the caller
    (observe_proposal) converts that into an error record."""
    fn = _decide_cache.get("fn")
    if fn is not None:
        return fn
    from .lifemate_gates_adapter import decide

    _decide_cache["fn"] = decide
    return decide


def _safe(value):
    """Deep-copy via a JSON round-trip so records never alias live
    objects and are always JSON-serialisable. Falls back to a repr
    wrapper for values that cannot round-trip."""
    try:
        return json.loads(json.dumps(value, ensure_ascii=False, default=str))
    except Exception:
        return {"__unserializable__": repr(value)}


def _outcome_of(result):
    """Outcome vocabulary, mirroring the paired audit's outcome_of:
    ok True + done not False -> "succeeded"; ok False ->
    "schema_rejected"; ok True + done False -> "noop"; anything else
    (including non-dict results) -> "unknown"."""
    if not isinstance(result, dict):
        return "unknown"
    if result.get("ok") is True and result.get("done") is not False:
        return "succeeded"
    if result.get("ok") is False:
        return "schema_rejected"
    return "noop"


def _norm_phone_digits(value):
    """Digits-only phone, mirroring lifemate_phone_callback_evidence
    .norm_phone for string input: an 11-digit "84..." form folds
    to a 10-digit 0-number. Non-string input yields "" (no
    coercion: a non-string phone is not a phone value here)."""
    if not isinstance(value, str):
        return ""
    digits = "".join(ch for ch in value if ch.isdigit())
    if digits.startswith("84") and len(digits) == 11:
        return "0" + digits[2:]
    return digits


def _valid_phone(value):
    """Roster-phone contract (R3-P0-PHONE, field "phone"): after
    norm, 0-led and 10 or 11 digits. Anything else -- a tail,
    a short number, a missing-zero number, a 9-digit or
    12-digit form, a hotline -- is not a roster phone value
    and is ignored, never coerced into one."""
    digits = _norm_phone_digits(value)
    return digits.startswith("0") and len(digits) in (10, 11)


def _valid_text(value):
    """A name/relation value carries information only when it is
    a string with a non-blank stripped form. Non-strings are
    never coerced; blank strings carry no information."""
    return isinstance(value, str) and bool(value.strip())


def _roster_entry(entry):
    """One roster entry, on the whitelist only, or None.

    Fields, exactly: id, name, phone, relation. ``id`` is the
    key only and is kept as-is when truthy (an entry with no
    id is not roster evidence). ``name`` is the raw string
    when valid, else "" (missing). ``phone`` is the raw
    string when it passes the phone contract, else ""
    (missing). ``relation`` is present only when valid;
    otherwise the key is absent (missing). Every other
    field -- even a string -- is dropped: an arbitrary
    string in a contact dictionary is not structured
    evidence, and copying it would let an unrelated string
    (a note, a label, a free-text comment) qualify a
    duplicate. Missing, in this module, is absent, None,
    or "" for name/phone, and absent for relation."""
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


def _collect_rosters(value, out):
    """Recursively collect NORMALISED roster entries from a
    result value, mirroring the paired audit's collect_rosters:
    any "contacts" list with id-bearing entries counts;
    recursion does not descend into "phone" values. Entries
    are normalised by _roster_entry, so no stray field and
    no invalid value ever reaches a merge."""
    if isinstance(value, dict):
        contacts = value.get("contacts")
        if isinstance(contacts, list):
            for entry in contacts:
                contact = _roster_entry(entry)
                if contact is not None:
                    out.append(contact)
        for key, item in value.items():
            if key != "phone":
                _collect_rosters(item, out)
    elif isinstance(value, list):
        for item in value:
            _collect_rosters(item, out)


# ---------------------------------------------------------------------------
# Unified roster conflict rule (R4-CONFLICT, same rule in all three
# roster paths: this observer, analysis/gg_paired_audit.py, and
# lifemate/agent.py -- the modules cannot import each other, so the
# rule is stated in full in each place and must stay identical):
#
# 1. LAST-WINS, IN PREFIX ORDER. For the same registry
#    ("contacts.contacts") and contact_id, a valid field from
#    a NEWER successful read replaces the older value.
#    Order is the order of events in the prefix (list order,
#    which build_prefix guarantees is position order), never
#    the system clock. A merged roster is a current-state
#    view at proposal time, not a freeze at first sight.
# 2. A field the newer read does not carry does NOT delete
#    the older value: absence in a read is not a deletion
#    signal (a later search may be a different query
#    returning a subset). The older value is kept.
# 3. A failed / noop read creates, updates, or deletes
#    nothing (see collect_rosters_from_prefix for this
#    path's success definition).
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
#    via that field: the adapter blocks on a missing /
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
# attribute, so a conflict/reason field inside an entry
# could itself become qualifying evidence). They are
# returned by collect_rosters_from_prefix_with_conflicts
# and, per observed proposal, on ShadowObserver
# .last_roster_conflicts. They are deliberately NOT added
# to observer records: the export validator (another
# owner's file, not edited here) accepts only the 9-key
# record or the 9 keys plus selection_decision, and this
# change must not break that schema.
# ---------------------------------------------------------------------------

_ROSTER_FIELDS = ("name", "phone", "relation")


def _new_roster_state():
    """Fresh merge state: entries (the roster list, in
    first-seen order), barriers {id: {field: confirmed}},
    unknown {id: set(fields)}, conflicts [records]."""
    return {"entries": [], "barriers": {}, "unknown": {},
            "conflicts": []}


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


def _merge_group_into_state(state, grouped, unknown_map, seq):
    """Merge one read event's grouped entries into state,
    in event order (rule 1). ``seq`` is the event's order
    index in the prefix (enumeration order, not a clock).
    A field in unknown_map for an id becomes UNKNOWN in
    state (rule 6a), regardless of any older value."""
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


def _apply_barrier_to_state(state, barrier_entry, seq):
    """Apply a lifecycle-confirmed contacts.update to state
    (rule 5). ``barrier_entry`` is a normalised roster
    entry built from the update's returned item. Only its
    present valid fields become barriers, and only those
    fields are overwritten (pre-barrier values for those
    fields are discarded); other fields are untouched, and
    an UNKNOWN for a barrier field is cleared by the
    confirmed value. A barrier is not a conflict and is
    not recorded in conflicts."""
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
    event, or None. Confirmed means: the event succeeded,
    its contact_id argument is truthy, and its returned
    item is a dict whose id equals that argument (the
    PATCH_VERIFIED shape). The barrier fields are the
    item's whitelisted valid fields, normalised by
    _roster_entry. Anything else -- a failed update, an
    id mismatch, no item, an invalid field value -- yields
    no barrier at all (never a partial barrier from an
    unconfirmed value)."""
    if not isinstance(args, dict) or not args.get("contact_id"):
        return None
    if not isinstance(result, dict):
        return None
    item = result.get("item")
    if not isinstance(item, dict) or item.get("id") != args.get(
            "contact_id"):
        return None
    return _roster_entry(item)


def _backfill_roster_entry(existing, new):
    """Backward-compatible single-entry merge, now LAST-WINS
    (rule 1), not keep-first: a missing field is filled, an
    equal value is kept, and a different valid value from
    the later entry replaces the older one. Missing /
    invalid later values never overwrite. Implemented via
    the state core so the single-entry path cannot drift
    from the grouped path; barrier and UNKNOWN state are
    not carried by this wrapper (callers that need them
    use the state functions)."""
    state = _new_roster_state()
    state["entries"].append(existing)
    grouped, unknown_map = _group_read_entries([dict(new)])
    _merge_group_into_state(state, grouped, unknown_map, 0)
    # The wrapper mutates ``existing`` in place: the state
    # entry IS ``existing`` (same dict object), so no copy
    # back is needed. If ``new`` had no id match this is a
    # no-op for the caller only when ids differ -- in that
    # case the state gained a second entry, which the
    # caller ignores, exactly as the old wrapper did.


def _merge_roster_entry(out, contact):
    """Append ``contact`` to ``out`` or merge it into its
    existing entry for the same id, per the unified rule
    (last-wins for a differing valid value, fill for a
    missing field, never overwrite with a missing value).
    This list wrapper carries no barrier / UNKNOWN state;
    collect_rosters_from_prefix (which does) is the path
    the observer itself uses."""
    for existing in out:
        if existing["id"] == contact["id"]:
            _backfill_roster_entry(existing, contact)
            return
    out.append(contact)


def collect_rosters_from_prefix_with_conflicts(prefix):
    """Roster evidence from observed contacts.search results
    in the prefix (history + session), in prefix order,
    deduped by id, plus the conflict records produced by
    the unified rule. Returns (roster, conflicts).

    Success-only: a prefix entry contributes roster
    evidence ONLY when its read succeeded. Entries built
    by build_prefix carry "outcome" ("succeeded" exactly,
    per _outcome_of); entries without that field are
    judged by the same rule on their result (ok is True
    and done is not False). A failed read (ok False /
    schema_rejected), a noop, or a result with no ok True
    never becomes successful evidence, even if it carries
    a "contacts" list -- a failed result's payload is not
    a roster, and a failed read neither creates nor
    backfills an entry, so a failed first read does not
    poison a later successful one and a failed later read
    cannot erase or rewrite one.

    Lifecycle barriers (rule 5) are applied in prefix
    order as they occur: a succeeded contacts.update
    event (patch-verified, see _barrier_entry_from_update)
    sets confirmed fields before later reads are merged,
    and later reads are merged against those barriers.

    No future data: this function sees only the prefix it
    is given. A record observed at a proposal is not
    retroactively rewritten by a later search; the later
    search only affects later proposals' prefixes."""
    state = _new_roster_state()
    for seq, entry in enumerate(prefix or []):
        if not isinstance(entry, dict):
            continue
        result = entry.get("result")
        outcome = entry.get("outcome")
        if outcome is not None:
            succeeded = outcome == "succeeded"
        elif isinstance(result, dict):
            succeeded = result.get("ok") is True \
                and result.get("done") is not False
        else:
            succeeded = False
        if not succeeded:
            continue
        if entry.get("tool") == "contacts.update":
            barrier = _barrier_entry_from_update(
                entry.get("args") or {}, result)
            if barrier is not None:
                _apply_barrier_to_state(state, barrier, seq)
            continue
        found = []
        _collect_rosters(result, found)
        grouped, unknown_map = _group_read_entries(found)
        _merge_group_into_state(state, grouped, unknown_map, seq)
    return state["entries"], state["conflicts"]


def collect_rosters_from_prefix(prefix):
    """Roster list only; see
    collect_rosters_from_prefix_with_conflicts for the
    rule, the success definition, and the conflict
    records that accompany this list."""
    roster, _conflicts = collect_rosters_from_prefix_with_conflicts(
        prefix)
    return roster


def build_prefix(history, executed, results):
    """Build the adapter prefix from history + session observations,
    mirroring the paired audit exactly:

    - History turns in order: a user turn becomes
      {"kind": "user_turn", "text": <audio_text or "">, "position": p};
      an assistant turn contributes one event per tool call, zipped
      with tool_results by index (missing result -> None):
      {"tool", "args", "result", "outcome", "position": p,
      "origin": "history"}.
    - Session events (executed/results zipped) continue positions
      after history with origin "session".
    - Positions are one contiguous counter; the next proposal's
      proposal_position is len(prefix).

    Returns (prefix, error): on success error is None. On unparseable
    history (tool_results present but not a list), returns
    (None, message): the caller must NOT compute a decision on a
    partial prefix; it records the error instead. A None tool_results
    is a no-call assistant turn and contributes no events (same as
    the audit's ``or []``).
    """
    prefix = []
    pos = 0
    for turn in history or []:
        role = getattr(turn, "role", None)
        if role == "user":
            text = getattr(turn, "audio_text", None)
            prefix.append({"kind": "user_turn",
                           "text": text if text is not None else "",
                           "position": pos})
            pos += 1
        elif role == "assistant":
            calls = getattr(turn, "tool_calls", None) or []
            res = getattr(turn, "tool_results", None)
            if res is None:
                continue
            if not isinstance(res, list):
                return None, ("history tool_results not a list "
                              "(unparseable); prefix withheld")
            for idx, call in enumerate(calls):
                if not isinstance(call, dict) or "name" not in call:
                    continue
                result = res[idx] if idx < len(res) else None
                prefix.append({"tool": call["name"],
                               "args": call.get("arguments") or {},
                               "result": result,
                               "outcome": _outcome_of(result),
                               "position": pos,
                               "origin": "history"})
                pos += 1
    for call, result in zip(executed or [], results or []):
        if not isinstance(call, dict) or "name" not in call:
            continue
        prefix.append({"tool": call["name"],
                       "args": call.get("arguments") or {},
                       "result": result,
                       "outcome": _outcome_of(result),
                       "position": pos,
                       "origin": "session"})
        pos += 1
    return prefix, None


class ShadowObserver:
    """Per-run shadow log. One instance lives on the AgentLoop; the
    loop calls reset() at the start of every run() so no state leaks
    across samples. Every method below never raises."""

    def __init__(self, enabled=False):
        self.enabled = bool(enabled)
        self.records = []
        # Conflict records from the most recent observed
        # proposal's roster (see collect_rosters_from_prefix_
        # with_conflicts). In-memory only, never a record
        # key: the export schema is owned elsewhere.
        self.last_roster_conflicts = []

    def reset(self):
        try:
            self.records = []
            self.last_roster_conflicts = []
        except Exception:
            pass

    def _append(self, record):
        try:
            self.records.append(record)
        except Exception:
            pass

    def observe_invalid(self, raw, history=None, executed=None,
                        results=None):
        """Record a generator output that was not a usable tool call
        (non-dict or missing "name"). No decision is computed."""
        try:
            prefix, _err = build_prefix(history, executed, results)
            position = len(prefix) if prefix is not None else 0
            self._append({
                "proposal_raw": _safe(raw),
                "proposal_grounded": None,
                "validation_outcome": "invalid",
                "baseline_decision": None,
                "candidate_decision": None,
                "adjustments": [],
                "eligibility": None,
                "error": None,
                "position": position,
            })
        except Exception as exc:  # never leak into the agent
            self._append({
                "proposal_raw": _safe(raw),
                "proposal_grounded": None,
                "validation_outcome": "invalid",
                "baseline_decision": None,
                "candidate_decision": None,
                "adjustments": [],
                "eligibility": None,
                "error": repr(exc),
                "position": 0,
            })

    def observe_validation_failure(self, raw, grounded, error,
                                   history=None, executed=None,
                                   results=None):
        """Record a proposal rejected by validation: NOT executed,
        NOT submitted, no decision computed."""
        try:
            prefix, _err = build_prefix(history, executed, results)
            position = len(prefix) if prefix is not None else 0
            self._append({
                "proposal_raw": _safe(raw),
                "proposal_grounded": _safe(grounded),
                "validation_outcome": "failed",
                "baseline_decision": None,
                "candidate_decision": None,
                "adjustments": [],
                "eligibility": None,
                "error": None,
                "position": position,
            })
        except Exception as exc:  # never leak into the agent
            self._append({
                "proposal_raw": _safe(raw),
                "proposal_grounded": _safe(grounded),
                "validation_outcome": "failed",
                "baseline_decision": None,
                "candidate_decision": None,
                "adjustments": [],
                "eligibility": None,
                "error": repr(exc),
                "position": 0,
            })

    def observe_proposal(self, raw, grounded, history=None,
                         executed=None, results=None, current_text="",
                         kinds=None):
        """Record a validated proposal with its adapter decision.
        Ask proposals are recorded with no decision: the gate scope
        excludes sys.ask_missing_info (same as the paired audit).
        Any failure (prefix build, adapter import, adapter exception)
        becomes an error record; the agent flow is untouched."""
        try:
            prefix, prefix_error = build_prefix(history, executed,
                                                results)
            if prefix is None:
                self._append({
                    "proposal_raw": _safe(raw),
                    "proposal_grounded": _safe(grounded),
                    "validation_outcome": "ok",
                    "baseline_decision": None,
                    "candidate_decision": None,
                    "adjustments": [],
                    "eligibility": None,
                    "error": prefix_error,
                    "position": 0,
                })
                return
            position = len(prefix)
            grounded_name = grounded.get("name") if isinstance(
                grounded, dict) else None
            if grounded_name == ASK_TOOL:
                self._append({
                    "proposal_raw": _safe(raw),
                    "proposal_grounded": _safe(grounded),
                    "validation_outcome": "ok",
                    "baseline_decision": None,
                    "candidate_decision": None,
                    "adjustments": [],
                    "eligibility": None,
                    "error": None,
                    "position": position,
                })
                return
            roster, roster_conflicts = \
                collect_rosters_from_prefix_with_conflicts(prefix)
            self.last_roster_conflicts = roster_conflicts
            try:
                decision = _get_decide()(
                    grounded, prefix, roster, current_text, kinds,
                    proposal_position=position, eligibility=True)
            except Exception as exc:
                self._append({
                    "proposal_raw": _safe(raw),
                    "proposal_grounded": _safe(grounded),
                    "validation_outcome": "ok",
                    "baseline_decision": None,
                    "candidate_decision": None,
                    "adjustments": [],
                    "eligibility": None,
                    "error": repr(exc),
                    "position": position,
                })
                return
            record = {
                "proposal_raw": _safe(raw),
                "proposal_grounded": _safe(grounded),
                "validation_outcome": "ok",
                "baseline_decision": {
                    "fired": decision.baseline_fired,
                    "applicable": decision.applicable,
                    "reason": decision.baseline_reason,
                },
                "candidate_decision": {
                    "fired": decision.fired,
                    "applicable": decision.applicable,
                },
                "adjustments": _safe(decision.adjustments),
                "eligibility": _safe(
                    (decision.notes or {}).get("eligibility")),
                "error": None,
                "position": position,
            }
            # Additive, whole-dict copy of the structured
            # selection decision, present only when the
            # adapter actually set one. No old field is
            # changed, and fired/applicable are untouched:
            # this is a log field, not a gate input.
            selection = (decision.notes or {}).get(
                "selection_decision")
            if isinstance(selection, dict):
                record["selection_decision"] = _safe(selection)
            self._append(record)
        except Exception as exc:  # last-resort guard: never raise
            try:
                self._append({
                    "proposal_raw": _safe(raw),
                    "proposal_grounded": _safe(grounded),
                    "validation_outcome": "ok",
                    "baseline_decision": None,
                    "candidate_decision": None,
                    "adjustments": [],
                    "eligibility": None,
                    "error": repr(exc),
                    "position": 0,
                })
            except Exception:
                pass

    def to_json(self):
        """Serialise the log (for artifacts/debugging). Never raises."""
        try:
            return json.dumps(self.records, ensure_ascii=False)
        except Exception:
            return "[]"
