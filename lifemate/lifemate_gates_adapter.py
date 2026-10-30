"""Coordinator adapter: candidate Gate 2 decision = baseline gate
(read-before-write, round 3) + two narrow, audited adjustments.

Adjustment 1 (UN-FIRE, phone/contact only): when the baseline gate
fires on a contact reference (id, name, or phone_number) and the new
phone/callback evidence module PROVES that reference (both questions:
a valid source AND the current request selecting it as the action
target), the call passes. Entity-id fires are never un-fired by this
module: phone/callback evidence does not establish arbitrary *_ids.

Negation veto gate (R3): an Adjustment-1 un-fire additionally
requires POSITIVE action selection from the negation module
(lifemate_callback_negation). For callback proposals (phone.call
-> call, sms.send / chat_ott.send_message -> message) a decisive
veto (negated / replaced / cancelled) always vetoes, and unknown
vetoes except no_callback_verb: when the current text has no
verb head of any action, B abstains and a history-grounded
binding stands, because B judges current-text selection only.
All other unknown reasons veto for callback proposals -- a
blocked verb is not a request, and a verb of another action
never selects this action (delta-2 fix: the old
no_action_evidence conflated "no verb at all" with
"other-action verb" and "blocked verb"). For non-callback
proposals the negation module does not cover the proposal's
action, so only a decisive, target-attached veto counts;
unknown passes through, and a standalone generic veto does not
veto an unrelated action. A veto is recorded as a
callback_selection_veto adjustment, with the raw mention recorded
separately (mention_present) and never equated with selection.
The negation module is veto-only: its "positive" means "no veto
found", never proof of binding, so it runs only after module A
established.

Adjustment 2 (SUPPRESSION, id references only): when the baseline
gate passes an id reference (contact_id or other *_id) but the
evidence ledger says that entity's existence claim is INVALIDATED
at the proposal position (a succeeded delete after the establishing
evidence, with no successful re-read since), the call fires.
Suppression never applies to bare phone numbers: dialability of a
number is not entity existence (gold routinely dials numbers with
no book entry), and it never applies to bare mutate-verb passes
(no reference to attribute). Passed name references are resolved
to a roster id on a unique match and suppressed like id refs.
Suppression wins over un-fire for the same contact_id: an observed
counterpart from before a delete does not resurrect a deleted
contact.

Layer C (INSTRUCTION SELECTION, R4): an Adjustment-1 un-fire
whose selection evidence is a BOUND REFERENCE (module A
resolved an anaphoric / prior-instruction reference) additionally
requires that the current request actually CONTINUE that
reference. Reference resolution proves WHICH instruction is
meant; it never proves continuation. Layer C
(lifemate_callback_negation.analyze_instruction_selection) is
veto-only and runs only after module A established: a
cancelled / replaced / blocked result refuses the un-fire,
whether B abstained (no_callback_verb -- the R4 hole: "làm"
is not a callback verb, so B could not see the cancellation
wrapper) or B returned positive for a different target (a
replacement number reads "positive" to B because B answers
"is the action toward THIS target vetoed?", not "is the old
instruction still live?"). A "continue" result never creates
an un-fire on its own; an "unknown" result keeps the old
abstain behaviour (the honest 0764-class case: a bare
reference with no polarity signal), now recorded as unknown
in the trail instead of being mistaken for proven
continuation. Layer C never fires when the current text
directly selects the value itself (a user_requested_target /
tail-correction source): a fresh direct request stands on its
own even if it also cancels the old instruction. Two further
veto-only checks ride on the same layer: (a) HISTORY
REVOCATION -- a user turn between the bound instruction and
the proposal that cancels that instruction (a negated mention
of its number, or a decisive instruction cancellation) revokes
it, unless a later turn re-issues the same instruction; (b)
ACTION MATCH -- when the bound instruction's action class
(call vs message, from its turn text) is exactly one class
and differs from the proposal's action, the un-fire is
refused: repeating a message instruction as a call is not a
continuation of that instruction. Ambiguous cases (both
actions, or no verb, in the bound turn) never veto here.

P3g guard (session-created log laundering): a session prior READ
(phone.recent_calls / sms.read_recent) result is pre-filtered
before it reaches the phone/callback module: records attributable
to the session's own prior writes (same normalized number, or
contact_id in a session write's contact_id args) AND shaped like
a session write (direction "outgoing", or no direction key AND
status "dialing") are removed. A number the session itself dialed
must not become "log-grounded" by being re-read. History
(pre-session) records are never filtered. Residual: a dial from an
earlier session (also status dialing, no direction) re-read now is
filtered too, firing conservatively.

Applicability is unchanged from the baseline gate. The adapter
never changes a proposal, submitted calls, state, retry, or
termination: it only returns a decision + reasons (shadow-only).

Prefix format (callers: paired audit, shadow candidate):
  call entry: {"tool", "args", "result", "outcome", "position",
               "origin"} where outcome is one of "succeeded",
    "failed", "schema_rejected", "noop", "unknown"; origin is
    "history" (pre-session context) or "session" (current session
    prior calls). The CURRENT proposal must NOT be in the prefix.
  user-turn entry: {"kind": "user_turn", "text", "position"}.
Positions must increase along the prefix; history positions
precede session positions. The proposal position defaults to
(max prefix position) + 1.
"""

import copy

from .lifemate_gates import (
    CONSUMER_REGISTRY,
    PATCH_VERIFIED,
    PriorCall,
    _call_reference_values,
    _contact_references,
    _entity_ids,
    _establishes_contact_id,
    _establishes_contact_name,
    _establishes_contact_phone,
    _establishes_entity_id,
    _is_read_tool,
    flatten_result_entries,
    gate_read_before_write,
    nfc_lower,
    registry_for_entry,
)
from .lifemate_phone_callback_evidence import (
    callback_reference_for,
    fold_vietnamese,
    norm_phone,
    parse_phone_mentions,
    parse_tail_change,
    parse_tail_correction,
    phone_evidence_for,
)
from .lifemate_callback_negation import (
    analyze_action_selection,
    analyze_instruction_selection,
    analyze_selection_consistency,
    analyze_topic_selection,
    binding_action_class,
    instruction_action,
    phone_mentions_all_content,
    turn_fully_delegated,
)
from .lifemate_evidence_lifecycle import (
    CONSUMER_CONTRACTS,
    EvidenceLedger,
    check_eligibility,
    classify_tool,
    field_value_record,
    result_succeeded,
)


class CandidateDecision:
    """Adapter decision: baseline fields + adjustment trail."""

    def __init__(self, fired, applicable, baseline_fired, baseline_reason,
                 adjustments, notes):
        self.fired = fired
        self.applicable = applicable
        self.baseline_fired = baseline_fired
        self.baseline_reason = baseline_reason
        self.adjustments = adjustments  # list of dicts
        self.notes = notes  # dict: filtered_log_records, adapter_gaps, ...

    def to_dict(self):
        return {
            "fired": self.fired,
            "applicable": self.applicable,
            "baseline_fired": self.baseline_fired,
            "baseline_reason": self.baseline_reason,
            "adjustments": self.adjustments,
            "notes": self.notes,
        }


def _outcome(entry):
    outcome = entry.get("outcome")
    if outcome in ("succeeded", "failed", "schema_rejected", "noop"):
        return outcome
    if entry.get("succeeded") is True:
        return "succeeded"
    if entry.get("succeeded") is False:
        return "failed"
    return "unknown"


def _is_session_write(entry):
    return entry.get("origin") == "session" \
        and entry.get("tool") in ("phone.call", "sms.send")


def filtered_prefix_for_phone(prefix):
    """Clone the prefix with session-created log records removed
    (P3g guard). Returns (filtered_prefix, n_filtered_records).

    Only session-origin READ results are filtered. A record is
    session-created iff it looks like a record the session's own
    dial/send created AND it matches a session write:
      - number match: normalized record number (nested contact
        phone, else top-level phone_number -- the real
        phone.recent_calls shape carries NO nested contact) in
        the session-written numbers, OR contact_id match: the
        record's contact_id (nested or top-level) in the session
        writes' contact_id args (a dial by contact_id resolves
        to a number the args never show);
      - shape: direction "outgoing", OR no direction key AND
        status "dialing" -- exactly the shape phone.call creates
        (zaic_tools phone.call records carry no direction key;
        sms.send records carry direction "outgoing").
    History records, incoming records, and direction-missing
    records with status received/missed/completed are kept:
    those are pre-session evidence, not laundering.
    Residual (documented, conservative): a dial from an EARLIER
    session (also status dialing, no direction) re-read now is
    filtered too, so the gate fires rather than trusting it.
    """
    written_numbers = set()
    written_ids = set()
    for entry in prefix or []:
        if not isinstance(entry, dict) or entry.get("kind") == "user_turn":
            continue
        if _is_session_write(entry):
            phone = norm_phone((entry.get("args") or {}).get("phone_number"))
            if phone:
                written_numbers.add(phone)
            cid = (entry.get("args") or {}).get("contact_id")
            if cid:
                written_ids.add(nfc_lower(cid))
    if not written_numbers and not written_ids:
        return list(prefix or []), 0

    def _session_created(rec):
        if not isinstance(rec, dict):
            return False
        direction = rec.get("direction")
        if not (direction == "outgoing"
                or (direction is None and rec.get("status") == "dialing")):
            return False
        contact = rec.get("contact")
        num = None
        cid = rec.get("contact_id")
        if isinstance(contact, dict):
            num = contact.get("phone")
            cid = cid or contact.get("id")
        num = norm_phone(num or rec.get("phone_number"))
        if num and num in written_numbers:
            return True
        if cid and nfc_lower(cid) in written_ids:
            return True
        return False

    filtered = []
    n_filtered = 0
    for entry in prefix or []:
        if not isinstance(entry, dict) or entry.get("kind") == "user_turn":
            filtered.append(entry)
            continue
        if entry.get("origin") != "session":
            filtered.append(entry)
            continue
        result = entry.get("result")
        if not isinstance(result, dict):
            filtered.append(entry)
            continue
        tool = entry.get("tool")
        new_result = None
        if tool == "phone.recent_calls" and isinstance(
                result.get("calls"), list):
            kept = [rec for rec in result["calls"]
                    if not _session_created(rec)]
            n_filtered += len(result["calls"]) - len(kept)
            new_result = dict(result, calls=kept)
        elif tool == "sms.read_recent" and isinstance(
                result.get("messages"), list):
            kept = [rec for rec in result["messages"]
                    if not _session_created(rec)]
            n_filtered += len(result["messages"]) - len(kept)
            new_result = dict(result, messages=kept)
        if new_result is not None:
            clone = dict(entry, result=new_result)
            filtered.append(clone)
        else:
            filtered.append(entry)
    return filtered, n_filtered


def _priors_for_gate(prefix):
    """PriorCall list for the baseline gate, from raw prefix."""
    priors = []
    for entry in prefix or []:
        if not isinstance(entry, dict) or entry.get("kind") == "user_turn":
            continue
        result = entry.get("result")
        entries = []
        if isinstance(result, dict):
            try:
                entries = flatten_result_entries(result)
            except Exception:
                entries = []
        priors.append(PriorCall(
            entry.get("tool"), entry.get("args") or {},
            result_entries=entries,
            succeeded=_outcome(entry) == "succeeded"))
    return priors


def _entry_is_read(entry, kinds):
    return _is_read_tool(entry.get("tool"), kinds)


def _resolve_roster_name(roster, name):
    """Roster id for a contact name, or None unless unique.

    Name suppression (C2 latent hole) resolves a passed name
    ref through the roster: exactly one roster entry with this
    name (nfc_lower) -> its id; zero or several -> None (no
    suppression, recorded as a gap by the caller).
    """
    matches = [e.get("id") for e in (roster or [])
               if isinstance(e, dict) and e.get("id")
               and nfc_lower(e.get("name")) == nfc_lower(name)]
    return matches[0] if len(matches) == 1 else None


def _valid_field_value(field, value):
    """Well-formedness gate for a field value before it may become
    an active field_value record (R2-P0, validity layer).

    This is a SHAPE gate, never a completion: it never guesses a
    value, never fills one in from the roster, context, or system
    clock, and never normalizes the stored value. A value that
    fails is simply not established (the query then reads
    invalidated if a mutation killed an older value, unknown if
    there was none) -- the caller must ask, exactly as grounding
    NEEDS_ASK does upstream. Only the field families grounding can
    NEEDS_ASK on are gated; every other field passes through
    unchanged, so title/status/content/done behaviour is untouched:
      - phone / phone_number: R3-P0-PHONE contract (see
        tests/test_lifecycle_adapter_r2p0.py for the evidence
        table). This gate is NOT a telecom-validity check and
        NOT "every valid number is a 10-digit mobile": no
        prefix whitelist is applied, and uniqueness /
        membership is decided by the source (a succeeded
        read/patch result) and by the gates, never here.
        After norm_phone (digits only, an 11-digit "84..."
        form folded to a 10-digit 0-number):
          * phone (a contact record's field, e.g. a
            contacts.search/get/update result): norm digits
            must start with 0 and be 10 or 11 digits long.
            10-digit mobiles are the majority in-tree, and
            11-digit 0-led forms are attested roster phones
            (e.g. 09883322117, 09125430868) and the
            train_0063-like contacts.search value
            09631116692; the R2-P0 10-only rule discarded
            those real records as unknown/no_evidence.
          * phone_number (a dial/log field, e.g. a
            phone.recent_calls / sms.read_recent result):
            the same 0-led 10/11-digit rule, PLUS the
            hotline form 1900 + 4 digits (8 digits total,
            e.g. 19001234, attested as a phone.call target).
            A hotline is dialable, not a contact record, so
            it is accepted here and not under "phone".
        Both reject a raw tail ("duoi 222" -> "222"), a
        short string ("0903"), a missing-zero number
        ("903111222"), a 9-digit 0-led string (no field
        example attests it; indistinguishable from a
        truncated 10/11-digit number, so fail-closed), a
        12-digit string, and a spoken form with no digits.
        A 12-digit "84..." form is also rejected: the
        shared norm_phone folds only 11-digit "84..."
        forms, and no in-tree example attests the 12-digit
        form -- recorded as a residual, not invented here.
      - date: an ISO date (YYYY-MM-DD, calendar-valid) or
        YYYY-MM, the values grounding passes through unchanged.
      - time / start / end: an ISO datetime (calendar-valid),
        an ISO date, or HH:MM(:SS) with hour <= 23, minute/second
        <= 59 -- the values grounding passes through unchanged.
        A relative expression with no hour ("ngay mai luc tam
        gio") fails here, as it does in grounding (NEEDS_ASK).
    """
    import re as _re
    if field in ("phone", "phone_number"):
        digits = norm_phone(value)
        if digits.startswith("0") and len(digits) in (10, 11):
            return True
        # Hotline: dial/log field only, never a contact record.
        if field == "phone_number" and len(digits) == 8 \
                and digits.startswith("1900"):
            return True
        return False
    if field == "date":
        if not isinstance(value, str):
            return False
        if _re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            try:
                from datetime import date as _date
                _date.fromisoformat(value)
                return True
            except ValueError:
                return False
        m = _re.fullmatch(r"(\d{4})-(\d{2})", value)
        return m is not None and 1 <= int(m.group(2)) <= 12
    if field in ("time", "start", "end"):
        if not isinstance(value, str):
            return False
        if _re.fullmatch(
                r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2})?"
                r"([+-]\d{2}:?\d{2}|Z)?", value):
            try:
                from datetime import datetime as _dt
                _dt.fromisoformat(value.replace("Z", "+00:00"))
                return True
            except ValueError:
                return False
        if _re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            try:
                from datetime import date as _date
                _date.fromisoformat(value)
                return True
            except ValueError:
                return False
        m = _re.fullmatch(r"(\d{1,2}):(\d{2})(?::(\d{2}))?", value)
        if m is not None:
            return int(m.group(1)) <= 23 and int(m.group(2)) <= 59 \
                and (m.group(3) is None or int(m.group(3)) <= 59)
        return False
    return True


def _field_value_events(obj, path, tool, is_read, ref_values, pos,
                        events, call_args=None):
    """Append counterpart field_value records for item dicts in a
    succeeded result (R5 coordinator wiring for B's eligibility and
    prover-validity APIs).

    An item dict is any dict with a string "id"; its registry comes
    from registry_for_entry(tool, "id", path) with path = the key the
    item sits under (None for a top-level item). For patch-verified
    tools, a primary record (path None/"" / "item") whose tool has
    no PRODUCER_REGISTRY "id" mapping falls back to the
    PATCH_VERIFIED registry: a succeeded patch whose returned
    record id equals its patch id-arg provably looked the entity
    up, so its returned fields are post-mutation state, not an
    echo. Items whose tool has neither mapping emit nothing
    (e.g. notes.append, which is neither PRODUCER_REGISTRY-listed
    nor patch-verified -- its field values stay unknown until a
    simulator-verified mapping exists; never guessed).
    Scalar fields only (str/int/float/bool, not None, not
    nested); the "id" field itself is existence, not field_value.
    Same echo rule as the existence loop: a non-read string value
    restating the call's own reference args establishes nothing.
    These records are a NEW claim type: existing adapter consumption
    queries claim == "existence" only, so emitting them cannot change
    fired by itself.

    R2-P0, two guards on this path (both fail-closed, neither
    guesses a value):
    1. Patch-id equality (L-N3): for a patch-verified tool, a
       primary record is the patched entity's post-mutation state
       ONLY when its id equals the call's patch id-arg -- the
       same equality the existence branch already enforced, now
       threaded through via call_args. On mismatch, no field of
       that record is emitted at all (not even via a
       PRODUCER_REGISTRY mapping: contacts.update returning a
       different contact's record is the same over-establishment
       as the calendar fallback case). A missing id-arg is a
       mismatch, not a pass.
    2. Value validity (NEEDS_ASK bypass): every emitted field
       value must pass _valid_field_value. A raw tail, an
       incomplete phone, or an hour-less relative time fed past
       a NEEDS_ASK gate is not established as an active field;
       it is dropped here, never completed from roster/context/
       clock and never stored as the field's value.
    """
    if isinstance(obj, dict):
        ent = obj.get("id")
        if isinstance(ent, str):
            reg = registry_for_entry(tool, "id", path)
            patch = PATCH_VERIFIED.get(tool)
            if patch is not None and path in (None, "", "item"):
                patch_id = (call_args or {}).get(patch[1])
                if patch_id != ent:
                    reg = None
                elif reg is None:
                    reg = patch[0]
            if reg is not None:
                for fk, fv in obj.items():
                    if fk == "id":
                        continue
                    if not isinstance(fv, (str, int, float, bool)):
                        continue
                    if not is_read and isinstance(fv, str) \
                            and nfc_lower(fv) in ref_values:
                        continue
                    if not _valid_field_value(fk, fv):
                        continue
                    events.append(field_value_record(
                        reg, ent, fk, fv, pos, tool,
                        source="read_result" if is_read
                        else "write_result"))
        for k, v in obj.items():
            _field_value_events(v, k, tool, is_read, ref_values, pos,
                                 events, call_args)
    elif isinstance(obj, list):
        for v in obj:
            _field_value_events(v, path, tool, is_read, ref_values,
                                 pos, events, call_args)


def build_ledger(prefix, roster, kinds):
    """EvidenceLedger fed from the prefix (evidence + mutations).

    Returns (ledger, notes). Evidence: flattened result entries
    with a registry, patch-verified write records, and roster
    entries (position -1 = session-start knowledge). Mutations:
    classified prefix writes via the lifecycle MUTATION_TABLE,
    with email.archive reclassified by action arg and email.reply
    side effects emitted. Unknown/unclassifiable writes emit no
    mutation event (they neither invalidate nor establish).
    """
    ledger = EvidenceLedger()
    notes = {"mutation_events": 0, "mutation_skipped": [],
             "evidence_records": 0}
    events = []
    for entry in prefix or []:
        if not isinstance(entry, dict) or entry.get("kind") == "user_turn":
            continue
        tool = entry.get("tool")
        pos = entry.get("position", 0)
        outcome = _outcome(entry)
        result = entry.get("result")
        # --- evidence from succeeded results (gate echo rule
        # applied: a WRITE result restating its own reference args
        # establishes nothing -- otherwise a send to a deleted
        # contact would resurrect it in the ledger. Reads verify
        # by lookup. Patch-verified writes are added explicitly
        # below, so their echo is not double-counted here.) ---
        if outcome == "succeeded" and isinstance(result, dict):
            try:
                flat = flatten_result_entries(result)
            except Exception:
                flat = []
            is_read = _entry_is_read(entry, kinds)
            ref_values = set() if is_read else _call_reference_values(
                entry.get("args") or {})
            for raw in flat:
                if len(raw) == 3:
                    field, value, path = raw
                elif len(raw) == 2:
                    field, value, path = raw[0], raw[1], None
                else:
                    continue
                if not isinstance(value, str):
                    continue
                if not is_read and nfc_lower(value) in ref_values:
                    continue
                registry = registry_for_entry(tool, field, path)
                if registry is None:
                    continue
                events.append({
                    "kind": "entity", "value": value,
                    "registry": registry, "claim": "existence",
                    "field": field, "outcome": "succeeded",
                    "position": pos, "producer": tool,
                    "source": "read_result" if is_read else "write_result",
                    "status": "active",
                    "counterpart": None, "reason": "result_entry"})
            patch = PATCH_VERIFIED.get(tool)
            if patch is not None:
                item = result.get("item")
                if isinstance(item, dict) and item.get("id") is not None \
                        and (entry.get("args") or {}).get(patch[1]) \
                        == item.get("id"):
                    events.append({
                        "kind": "entity", "value": item["id"],
                        "registry": patch[0], "claim": "existence",
                        "field": "id", "outcome": "succeeded",
                        "position": pos, "producer": tool,
                        "source": "write_result", "status": "active",
                        "counterpart": None,
                        "reason": "patch_verified"})
            # R5: counterpart field_value records for entity-linked
            # field checks and observation expiry (see helper).
            _field_value_events(result, None, tool, is_read,
                                 ref_values, pos, events,
                                 entry.get("args") or {})
        # --- mutation events from writes (any outcome; the ledger
        # ignores non-succeeded ones itself) ---
        if _entry_is_read(entry, kinds):
            continue
        table = classify_tool(tool)
        if table is None:
            # Never silent: an unclassifiable write (e.g. a future
            # contacts.delete) emits no mutation event, and the
            # skip is logged so a later catalog addition is
            # noticed instead of silently unguarded.
            notes["mutation_skipped"].append(
                (tool, pos, "tool not in MUTATION_TABLE"))
            continue
        args = entry.get("args") or {}
        # email.archive: reclassify by action arg (B's table flag).
        if tool == "email.archive":
            action = args.get("action")
            if action == "delete":
                events.append({
                    "tool": tool, "args": args, "result": result,
                    "position": pos, "registry": "email.emails",
                    "entity_value": args.get("email_id"),
                    "mutation_kind": "delete", "effective": True})
                notes["mutation_events"] += 1
            elif args.get("email_id"):
                events.append({
                    "tool": tool, "args": args, "result": result,
                    "position": pos, "registry": "email.emails",
                    "entity_value": args.get("email_id"),
                    "mutation_kind": "update", "fields": ["folder"],
                    "effective": True})
                notes["mutation_events"] += 1
            else:
                notes["mutation_skipped"].append(
                    (tool, pos, "no email_id"))
            continue
        # scene_run: multi-entity; emit per-device events only when
        # the result enumerates affected devices, else skip.
        if tool == "smart_home.scene_run":
            devices = []
            if isinstance(result, dict):
                for key in ("devices", "affected_devices"):
                    if isinstance(result.get(key), list):
                        devices = result[key]
                        break
            emitted = 0
            for dev in devices:
                # Real scene_run results key devices by "id"
                # (gate PRODUCER_REGISTRY agrees); accept
                # "device_id" too (reviewer fix FAIL-3).
                did = None
                if isinstance(dev, dict):
                    did = dev.get("device_id") or dev.get("id")
                if did:
                    events.append({
                        "tool": tool, "args": args, "result": result,
                        "position": pos,
                        "registry": "smart_home.devices",
                        "entity_value": did, "mutation_kind": "update",
                        "effective": True})
                    emitted += 1
            if emitted:
                notes["mutation_events"] += emitted
            else:
                notes["mutation_skipped"].append(
                    (tool, pos, "scene devices not enumerated"))
            continue
        # Upserts / kind_arg tools other than email.archive: the
        # table entry alone cannot decide create-vs-update, so no
        # event (documented; never guessed).
        if table.get("kind_arg"):
            notes["mutation_skipped"].append(
                (tool, pos, "kind_arg needs adapter classification"))
            continue
        id_arg = table.get("id_arg")
        if id_arg is None:
            # Create: kills nothing; entity from result when known.
            entity = None
            if isinstance(result, dict):
                entity = result.get("id")
                if entity is None and isinstance(
                        result.get("item"), dict):
                    entity = result["item"].get("id")
            events.append({
                "tool": tool, "args": args, "result": result,
                "position": pos, "registry": table["registry"],
                "entity_value": entity,
                "mutation_kind": table["mutation_kind"],
                "effective": True})
            notes["mutation_events"] += 1
        else:
            entity = args.get(id_arg)
            if entity is None:
                notes["mutation_skipped"].append(
                    (tool, pos, "no id_arg value"))
                continue
            event = {
                "tool": tool, "args": args, "result": result,
                "position": pos, "registry": table["registry"],
                "entity_value": entity,
                "mutation_kind": table["mutation_kind"],
                "effective": True}
            # Fixed-field updates (reviewer fix R2-B1): the table's
            # explicit fields win over args-derived touching, so a
            # patch like tasks.complete (args carry only the id)
            # still kills the done field claim.
            if table.get("fields") is not None:
                event["fields"] = table["fields"]
            events.append(event)
            notes["mutation_events"] += 1
        # Side effects (e.g. email.reply updates the original).
        for side in table.get("side_effects") or []:
            side_entity = None
            if tool == "email.reply":
                side_entity = args.get("email_id")
            if side_entity is None:
                notes["mutation_skipped"].append(
                    (tool, pos, "side effect entity unknown"))
                continue
            events.append({
                "tool": tool, "args": args, "result": result,
                "position": pos, "registry": side["registry"],
                "entity_value": side_entity,
                "mutation_kind": side["mutation_kind"],
                "fields": side.get("fields"),
                "effective": True})
            notes["mutation_events"] += 1
    for contact in roster or []:
        if isinstance(contact, dict) and contact.get("id"):
            events.append({
                "kind": "entity", "value": contact["id"],
                "registry": "contacts.contacts", "claim": "existence",
                "field": "id", "outcome": "succeeded", "position": -1,
                "producer": "contacts.search", "source": "read_result",
                "status": "active", "counterpart": None,
                "reason": "roster"})
    notes["evidence_records"] = sum(
        1 for e in events if "mutation_kind" not in e)
    # Test/observability hook (logging only): which mutation
    # events carried explicit fields, so fixed-field forwarding
    # (R2-B1) is checkable without exposing the event list.
    notes["mutation_fields"] = [
        (e["tool"], list(e["fields"]))
        for e in events
        if "mutation_kind" in e and e.get("fields") is not None]
    # R2-G3: a write's own result is post-mutation state, so at a
    # shared position its mutation must precede its evidence in
    # journal order. Without this, apply_prefix (stable by
    # position) keeps evidence-before-mutation and the ledger
    # self-kills the new field_value the write just returned
    # (e.g. contacts.update phone, calendar.update_event title
    # both read back as invalidated instead of the new value).
    # Older records at strictly earlier positions are unaffected:
    # they are still killed by the mutation, as before.
    events = sorted(
        events,
        key=lambda e: (e.get("position", 0),
                       0 if "mutation_kind" in e else 1))
    ledger.apply_prefix(events)
    return ledger, notes


def _selection_targets(kind, value, phone_prefix, roster):
    """Target descriptors for the negation veto gate.

    Returns (names, phones) describing the bound counterpart, so
    the negation module can judge whether the current request
    positively selects it. Names include each full name plus its
    last token (the short form A resolves: "gọi An" must veto a
    bound "Nguyễn An"; a bare surname never vetoes, so only the
    last token is added). Phones come from roster entries and
    log records carrying the counterpart, so a number-based veto
    ("đừng gọi số X") also blocks an id proposal for X's owner.
    For phone-valued proposals, roster entries carrying the
    number also contribute their names (round-5 fix F-B4-8):
    the owner of a number is a target name even when the
    proposal itself carries no contact id or name.
    """
    names = set()
    phones = set()

    def _add_name(name):
        if not name:
            return
        names.add(name)
        parts = str(name).split()
        if len(parts) > 1:
            names.add(parts[-1])

    def _add_phone(phone):
        norm = norm_phone(phone) if phone else ""
        if norm:
            phones.add(norm)

    roster = roster or []
    if kind == "id":
        for entry in roster:
            if isinstance(entry, dict) and entry.get("id") == value:
                _add_name(entry.get("name"))
                _add_phone(entry.get("phone"))
    elif kind == "name":
        for entry in roster:
            if isinstance(entry, dict) \
                    and nfc_lower(entry.get("name")) == nfc_lower(value):
                _add_name(entry.get("name"))
                _add_phone(entry.get("phone"))
    elif kind == "phone":
        _add_phone(value)
        # Round-5 fix F-B4-8: a roster entry carrying this
        # number names its owner even when the proposal is
        # phone-valued (the old code only took names from log
        # records, so "nhan cho Vy so X" with a no-id roster
        # entry for Vy misread Vy as another recipient and
        # fired the content rule). Both no-id and with-id
        # entries count here; the with-id arm passes the
        # baseline gate, so only the no-id arm is observable
        # at the decide layer -- but the rule itself is uniform.
        for entry in roster:
            if isinstance(entry, dict) \
                    and norm_phone(entry.get("phone")) \
                    == norm_phone(value):
                _add_name(entry.get("name"))
    # Log records: nested contact {id, name, phone} or flat
    # {contact_id, phone_number} shapes.
    for entry in phone_prefix or []:
        if not isinstance(entry, dict):
            continue
        result = entry.get("result")
        if not isinstance(result, dict):
            continue
        records = []
        for key in ("calls", "messages"):
            items = result.get(key)
            if isinstance(items, list):
                records.extend(items)
        for rec in records:
            if not isinstance(rec, dict):
                continue
            contact = rec.get("contact")
            if isinstance(contact, dict):
                cid = contact.get("id")
                if kind == "id" and cid == value:
                    _add_name(contact.get("name"))
                    _add_phone(contact.get("phone"))
                elif kind == "name" and nfc_lower(
                        contact.get("name")) == nfc_lower(value):
                    _add_phone(contact.get("phone"))
                elif kind == "phone" and norm_phone(
                        contact.get("phone")) == norm_phone(value):
                    _add_name(contact.get("name"))
            if kind == "id" and rec.get("contact_id") == value:
                _add_phone(rec.get("phone_number"))
            elif kind == "phone" and norm_phone(
                    rec.get("phone_number")) == norm_phone(value):
                if isinstance(contact, dict):
                    _add_name(contact.get("name"))
    if kind == "name":
        _add_name(value)
    return sorted(names), sorted(phones)


# Proposal tools whose action IS a callback: only these go through
# the negation veto gate. For other tools (e.g. ewallet.transfer)
# the binding evidence stands as module A judged it; the user's
# callback-selection analysis does not cover those actions.
_CALLBACK_ACTIONS = {
    "phone.call": "call",
    "sms.send": "message",
    "chat_ott.send_message": "message",
}


def _bound_reference_sources(verdict):
    """Sources whose reason says module A bound a reference.

    Only these selections go through layer C: a direct source
    (roster, log field, read result) proves existence, but the
    SELECTION half still came from the bound reference whenever
    question_b rests on it -- and a bound reference never proves
    continuation on its own (R4).
    """
    return [s for s in verdict.get("question_a_sources") or []
            if str(s.get("reason") or "").startswith("bound_reference:")]


def _has_direct_selection_source(verdict):
    """True iff the current text itself directly selects the value.

    A user_requested_target / tail-correction source is a fresh
    direct request: it stands on its own, so layer C must not
    veto it even when the same text also cancels the old
    instruction ("đừng làm như lúc nãy nữa, gọi số X đi" with
    X == the proposal value is a new request for X, not a
    cancelled one).
    """
    return any(s.get("reason") in (
        "user_requested_target",
        "tail_correction_of_history_number")
        for s in verdict.get("question_a_sources") or [])


def _bound_turn_text(prefix, bound_position):
    """Text of the user turn at bound_position, or None."""
    if bound_position is None:
        return None
    for entry in prefix or []:
        if isinstance(entry, dict) \
                and entry.get("kind") == "user_turn" \
                and entry.get("position") == bound_position:
            text = entry.get("text")
            return text if isinstance(text, str) else None
    return None


def _extract_addressee(text):
    """Explicit addressee of a turn, or None.

    The token(s) after the first "cho" / "tới" / "đến"
    preposition (raw, diacritic-preserving: "cho" the
    preposition vs "chớ" the negation stay distinct). Family
    words count as explicit addressees; speaker-generic words
    ("em", "anh", "chị", "mình", ...) do not -- they name no
    specific person. A candidate that is itself a verb /
    discourse word ("cho xong", "cho biết") is not an
    addressee. Comparison is raw-string equality (folded
    equality would conflate "An" with "ăn", and dialect
    equivalence such as "mẹ" = "mạ" is not claimed).
    A name without a preposition ("gọi An như lúc nãy") is
    NOT extracted: out of scope, documented.
    """
    if not isinstance(text, str) or not text.strip():
        return None
    import unicodedata
    import re as _re
    toks = [t.casefold() for t in _re.findall(r"[^\W_]+", text,
                                              flags=_re.UNICODE)]
    toks = [unicodedata.normalize("NFC", t) for t in toks]
    _family = {"mẹ", "mạ", "bố", "ba", "vợ", "chồng", "con"}
    _generic = {"em", "anh", "chị", "mình", "bạn", "tôi", "nó",
                "người", "ai", "cô", "chú", "bác", "dì"}
    _not_name = {"xong", "biết", "rõ", "xem", "coi", "hết", "đủ",
                 "tiện", "nhanh", "chậm", "kỹ", "ổn", "định",
                 "giúp", "dùm", "với", "để", "là", "thì", "mà",
                 "nữa", "đi", "nhé", "nha", "à", "ơi"}
    for k, tok in enumerate(toks):
        if tok not in ("cho", "tới", "đến"):
            continue
        parts = []
        for cand in toks[k + 1:k + 3]:
            if cand in _not_name or cand.isdigit():
                break
            # Second token only: stop at words that cannot
            # continue a name ("số", reference words, verbs).
            # Without this, "cho Vy số ..." reads as "vy so"
            # and "cho Vy như lúc nãy" as "vy nhu" -- a false
            # mismatch between the same addressee.
            if parts and cand in ("số", "như", "lúc", "nãy",
                                  "làm", "gọi", "nhắn", "điện",
                                  "gửi", "trả", "dặn", "nói",
                                  "bảo", "đã"):
                break
            parts.append(cand)
            if len(parts) == 1 and cand in _family:
                break
        if not parts:
            continue
        if parts[0] in _generic:
            return None
        return " ".join(parts)
    return None


def _addressee_matches(bound_addr, curr_addr):
    """Same-person addressee comparison (round-3 fix F2): raw
    equality, or one side a single token equal to the other's
    LAST token -- the system's last-token convention, applied
    here in the single-counterpart context (one bound
    addressee, one current addressee). Diacritic-sensitive
    (raw strings): "An" never equals "ăn". "mẹ" vs "mạ" stay
    different (S10f): neither is the other's last token."""
    if bound_addr == curr_addr:
        return True
    b = bound_addr.split()
    c = curr_addr.split()
    if len(b) == 1 and b[0] == c[-1]:
        return True
    if len(c) == 1 and c[0] == b[-1]:
        return True
    return False


def _cancel_marker_positions(text):
    """Char positions of cancellation markers in a turn.

    Folded search (folding is 1:1 per character, so positions
    align with the raw text). "chớ" is matched on raw tokens:
    folded it collides with the preposition "cho". Used only to
    ORDER a turn's events, never to decide cancellation by
    itself.
    """
    import re as _re
    folded = fold_vietnamese(text or "")
    positions = []
    for m in _re.finditer(r"\b(dung|khoi|huy|bo|ngung)\b", folded):
        positions.append(m.start())
    for m in _re.finditer(r"chớ", (text or "").casefold()):
        positions.append(m.start())
    for m in _re.finditer(
            r"\bkhong\s+(?:can\s+|phai\s+|lai\s+|la\s+)*lam\b",
            folded):
        positions.append(m.start())
    return sorted(set(positions))


def _reference_positions(text):
    """Char positions of prior-instruction reference patterns
    (folded). Used only to order a turn's continuation event
    against its other events."""
    folded = fold_vietnamese(text or "")
    positions = []
    for pat in ("luc nay", "lam nhu", "theo nhu", "nhu em dan",
                "nhu anh dan", "nhu chi dan", "nhu da",
                "so do", "so nay", "so moi nhat",
                "nguoi vua goi", "nguoi vua nhan"):
        start = 0
        while True:
            k = folded.find(pat, start)
            if k < 0:
                break
            positions.append(k)
            start = k + 1
    return sorted(positions)


def _known_names_for_number(target_phone, bound_text, roster,
                            phone_prefix):
    """Names known to denote the bound number: the bound
    instruction's addressee, roster names for the number, and
    log-record names for the number -- each with its last-token
    short form (B matches single tokens diacritic-sensitively).
    Used only for the named-cancel check (S1)."""
    names = set()
    bound_addr = _extract_addressee(bound_text) \
        if bound_text else None
    if bound_addr:
        names.add(bound_addr)
    sel_names, _sel_phones = _selection_targets(
        "phone", target_phone, phone_prefix, roster)
    names.update(sel_names)
    for entry in roster or []:
        if isinstance(entry, dict) \
                and norm_phone(entry.get("phone")) \
                == norm_phone(target_phone):
            if entry.get("name"):
                names.add(entry.get("name"))
    expanded = set(names)
    for n in list(names):
        parts = str(n).split()
        if len(parts) > 1:
            expanded.add(parts[-1])
    return sorted(expanded)


def _generic_cancel_for_action(text, proposal_action):
    """Generic cancellation of a turn for an action (module
    level so both the between-turns scan and the bound-turn
    self-check share it)."""
    def _word_tokens(t):
        import unicodedata
        import re as _re
        return [unicodedata.normalize("NFC", x.casefold())
                for x in _re.findall(r"[^\W_]+", t or "",
                                     flags=_re.UNICODE)]
    toks = _word_tokens(text)
    if toks and all(t in ("hủy", "đi", "nữa") for t in toks) \
            and "hủy" in toks:
        return True
    if proposal_action in ("call", "message"):
        sel = analyze_action_selection(
            text, target_names=(), target_phones=(),
            action=proposal_action)
        if sel["selection"] == "negated" \
                and sel["reason"] == "generic_callback_negated":
            return True
    if any(m in toks for m in ("đừng", "khỏi", "dừng",
                               "ngừng", "hủy", "bỏ")) \
            and "làm" in toks \
            and not any(t.isdigit() for t in toks) \
            and "cho" not in toks:
        return True
    return False


def _owner_new_number_positions(text, target, known_names):
    """Char positions of owner-new-number statements that
    revoke the bound number (round-6 fix N6).

    "so moi cua <Name> la Y" (the F-B4-9 background shape) is
    evidence AGAINST the bound old number of that same person
    -- like corrected_away -- but NOT evidence to call Y
    without a request verb, so it yields a "specific" fold
    event for the old number and never binds Y. Person-scoped
    only: the statement's name must be one of known_names
    (the bound instruction's persons, via addressee / roster /
    log); a bound instruction naming nobody never revokes on
    such a statement, and a statement about someone else
    never revokes this number. The M2 shape ("ma so Y la so
    moi") does not match: its mention reason differs, so it
    keeps binding Y.
    """
    if not known_names:
        return []
    folded = fold_vietnamese(text or "")
    positions = []
    for m in parse_phone_mentions(text):
        if m.get("reason") != "owner_new_number_statement":
            continue
        if m.get("normalized") == target:
            continue
        if len(m.get("normalized") or "") < 9:
            continue
        before_words = folded[:m["span"][0]].split()
        if not before_words or before_words[-1] != "la":
            continue
        for k in range(0, len(before_words) - 4):
            if before_words[k:k + 3] != ["so", "moi", "cua"]:
                continue
            middle = before_words[k + 3:-1]
            if not (1 <= len(middle) <= 3):
                continue
            name_folded = " ".join(middle)
            if any(fold_vietnamese(nm) == name_folded
                   for nm in known_names):
                positions.append(m["span"][0])
                break
    return positions


def _turn_revocation_events(text, target, known_names,
                            proposal_action, last_full):
    """One turn's revocation events in text-position order.

    Returns (events, new_last_full): events is a sorted list of
    (char_pos, transition) with transition in specific /
    specific_tail:<len> / revive / revive_tail:<len> / generic;
    new_last_full is the most recent full number
    mentioned in this turn (requested_target / background), or
    the incoming last_full when this turn mentions none. The
    tail-change event is attributed to the bound number only
    when no different full number was mentioned in this turn
    or more recently before it (S2 guard). A restore
    tail-change / correction (new tail == the bound tail
    again) is a revive_tail event, never a silent no-op: the
    fold decides by length coverage whether it revives a
    tail-changed state (round-5 fix F-B4-2). Name-only
    revival is NOT produced here -- it needs cross-turn
    cancellation memory, so the fold loop adds it via
    _turn_name_revive_events (round-5 fix F-B4-1).
    Delegation (round-7 fix S3): a turn whose queried-action
    verbs are ALL delegation-governed is another actor's
    instruction, so its explicit re-issue must not revive a
    cancelled instruction and its continuation reference must
    not revive one either -- both would let a delegatee's
    action stand in for the user's own. Its specific /
    generic events are KEPT: withdrawing language errs toward
    fire (the safe direction) even when delegated, and the
    proven hole is only the revive side. Name-only revival is
    already delegation-safe: _turn_name_revive_events judges
    via analyze_action_selection, which blocks delegated
    verbs, so a delegated name-only turn never revives.
    """
    events = []
    fully_delegated = proposal_action in ("call", "message") \
        and turn_fully_delegated(text, proposal_action)
    mentions = parse_phone_mentions(text)
    for m in mentions:
        if m.get("normalized") == target:
            if m.get("role") in ("negated", "corrected_away"):
                events.append((m["span"][0], "specific"))
            elif m.get("role") == "requested_target" \
                    and not fully_delegated:
                events.append((m["span"][0], "revive"))
    # Owner-new-number statement (round-6 fix N6): stating
    # that the bound person's number changed revokes the old
    # number for that person, without binding the new one.
    for pos in _owner_new_number_positions(
            text, target, known_names):
        events.append((pos, "specific"))
    corr = parse_tail_correction(text)
    change = parse_tail_change(text) if corr is None else None
    tail_event = None
    if corr is not None \
            and target.endswith(corr["old_tail"]) \
            and corr["new_tail"] != corr["old_tail"]:
        tail_event = (corr["span"][0],
                      "specific_tail:%d" % len(corr["old_tail"]))
    elif corr is not None \
            and target.endswith(corr["new_tail"]) \
            and corr["new_tail"] != corr["old_tail"] \
            and not target.endswith(corr["old_tail"]):
        # Restore correction (round-5 fix F-B4-2): the new tail
        # is the bound tail again ("duoi la 5678 chu khong
        # phai 1234" after a change to 1234). The old tail is
        # not the bound tail, so this is not a correction of
        # the bound number itself.
        tail_event = (corr["span"][0],
                      "revive_tail:%d" % len(corr["new_tail"]))
    elif change is not None \
            and not target.endswith(change["new_tail"]):
        tail_event = (change["span"][0],
                      "specific_tail:%d" % len(change["new_tail"]))
    elif change is not None \
            and target.endswith(change["new_tail"]):
        # Restore tail-change (round-5 fix F-B4-2): the new
        # tail is the bound tail again ("duoi doi thanh 5678"
        # after a change to 1234). Whether it revives is
        # decided at fold time by length coverage, not here.
        tail_event = (change["span"][0],
                      "revive_tail:%d" % len(change["new_tail"]))
    if tail_event is not None:
        same_turn_others = [
            m for m in mentions
            if m.get("normalized") != target
            and len(m.get("normalized") or "") >= 9
            and m.get("role") in ("requested_target", "background")]
        same_turn_target = any(
            m.get("normalized") == target
            and m.get("role") in ("requested_target",
                                  "background")
            for m in mentions)
        if not same_turn_others \
                and (last_full is None or last_full == target
                     or same_turn_target):
            events.append(tail_event)
    sel = analyze_instruction_selection(text)
    ref = sel["reference_present"]
    verdict = sel["instruction_selection"]
    if ref and verdict in ("cancelled", "replaced"):
        markers = _cancel_marker_positions(text)
        events.append((markers[-1] if markers else 0, "specific"))
    elif ref and verdict == "continue" and not fully_delegated:
        refs = _reference_positions(text)
        events.append((refs[-1] if refs else 0, "revive"))
    if known_names and proposal_action in ("call", "message"):
        nsel = analyze_action_selection(
            text, target_names=known_names, target_phones=(),
            action=proposal_action)
        if nsel["selection"] == "negated":
            folded = fold_vietnamese(text)
            name_pos = None
            for nm in known_names:
                k = folded.find(fold_vietnamese(nm))
                if k >= 0 and (name_pos is None or k < name_pos):
                    name_pos = k
            events.append((name_pos if name_pos is not None
                           else 0, "specific"))
    if _generic_cancel_for_action(text, proposal_action):
        markers = _cancel_marker_positions(text)
        events.append((markers[-1] if markers else 0, "generic"))
    order = _event_order
    events.sort(key=lambda e: (e[0], order(e[1])))
    new_last_full = last_full
    for m in mentions:
        if len(m.get("normalized") or "") >= 9 \
                and m.get("role") in ("requested_target",
                                      "background"):
            new_last_full = m["normalized"]
    return events, new_last_full


def _event_order(transition):
    """Sort rank for revocation events at one position.

    specific (and specific_tail) first, generic next, revive
    (and revive_tail, and revive_cancel) last: at the same
    position, a cancel beats a continuation and a re-issue
    beats both."""
    if transition.startswith("specific"):
        return 0
    if transition == "generic":
        return 1
    return 2


def _folded_name_positions(text, names):
    """Char positions (folded coordinates) of name mentions.

    Positions only ORDER events within a turn; selection itself
    is judged by the negation module's diacritic-sensitive
    matching, never by this scan. Single-token names match on
    the folded token (a same-fold different-diacritic word can
    contribute a spurious ordering position, never a verdict).
    Multi-token names match folded tokens in order, consecutive.
    Returns {name: [char_pos, ...]}.
    """
    import re as _re
    folded = fold_vietnamese(text or "")
    words = [(m.group(0), m.start())
             for m in _re.finditer(r"[^\W_]+", folded)]
    out = {}
    for name in names or []:
        parts = fold_vietnamese(name or "").split()
        if not parts:
            continue
        hits = []
        if len(parts) == 1:
            hits = [s for (w, s) in words if w == parts[0]]
        else:
            width = len(parts)
            for i in range(0, len(words) - width + 1):
                if [w for (w, _s) in words[i:i + width]] \
                        == parts:
                    hits.append(words[i][1])
        if hits:
            out[name] = hits
    return out


def _turn_name_revive_events(text, target, known_names,
                             proposal_action, cancelled_names,
                             ambiguous_names):
    """Name-only revival events for one turn + updated cancels.

    Round-5 fix F-B4-1: a re-request that names ONLY the
    cancelled person revives the instruction -- but only when
    (a) the name was cancelled in an earlier turn (tracked by
    the caller in cancelled_names; a turn's own last-wins
    probe already orders an in-turn cancel before/after a
    re-request, so no same-turn tracking is needed here),
    (b) the name resolves uniquely to the target (not in
    ambiguous_names: tied to another number in the prefix),
    and (c) the turn mentions no different full number (a
    re-request for another number is a new instruction, not a
    revival). Selection is judged per name by the negation
    module: only a target-attached positive (positive_selection)
    counts -- a bare continuation or a positive verb for
    someone else never revives. The emitted transition is
    "revive_cancel" (round-6 fix S1/S2), NOT "revive": the fold
    applies it only when the name still maps to the bound
    number (no tail change in effect, and no tail change while
    cancelled). Returns (revive_events,
    new_cancelled_names): names negated in this turn are added,
    names revived here are removed.
    """
    new_cancelled = set(cancelled_names or ())
    if not known_names or proposal_action not in ("call", "message"):
        return [], new_cancelled
    mentions = parse_phone_mentions(text)
    other_number = any(
        m.get("normalized") != target
        and len(m.get("normalized") or "") >= 9
        and m.get("role") in ("requested_target", "background")
        for m in mentions)
    name_pos = _folded_name_positions(text, known_names)
    revive_events = []
    if not other_number:
        for nm in known_names:
            if nm in (ambiguous_names or ()):
                continue
            sel_nm = analyze_action_selection(
                text, target_names=[nm], target_phones=(),
                action=proposal_action)
            if sel_nm["selection"] == "negated" \
                    and sel_nm["reason"] == "negated_selection":
                if name_pos.get(nm):
                    new_cancelled.add(nm)
            elif sel_nm["selection"] == "positive" \
                    and sel_nm["reason"] == "positive_selection":
                hits = name_pos.get(nm)
                if hits and nm in new_cancelled:
                    revive_events.append((hits[-1],
                                          "revive_cancel"))
                    new_cancelled.discard(nm)
    return revive_events, new_cancelled


def _ambiguous_names_for_prefix(prefix, target, known_names):
    """Known names tied to a full number other than target.

    A name is ambiguous when some user turn in the prefix
    mentions both the name and a different full number as a
    requested target or background (the M3 uniqueness guard,
    prefix-wide: a name claimed by two numbers never revives
    either). The bound turn's own tie to the target does not
    count.
    """
    ambiguous = set()
    for entry in prefix or []:
        if not isinstance(entry, dict) \
                or entry.get("kind") != "user_turn":
            continue
        text = entry.get("text")
        if not isinstance(text, str):
            continue
        others = [m.get("normalized")
                  for m in parse_phone_mentions(text)
                  if m.get("normalized") != target
                  and len(m.get("normalized") or "") >= 9
                  and m.get("role") in ("requested_target",
                                        "background")]
        if not others:
            continue
        present = _folded_name_positions(text, known_names)
        ambiguous.update(n for n in present)
    return ambiguous


def _apply_revocation_events(events, state):
    """Fold one turn's ordered events into the running state.

    State is (cancel, tail_len, dirty), or None for the live
    state (None, None, False):
      cancel: None | "generic" | "specific" -- whether the
        bound instruction is cancelled (specific = named /
        value / tail-based; generic = bare stop);
      tail_len: None | int -- a tail change currently in
        effect for the bound number (the changed tail's
        length, so a later restore can be checked for
        coverage, round-5 fix F-B4-2);
      dirty: bool -- a tail change happened while the
        instruction was cancelled (round-6 fix S1/S2). The
        name's mapping went through a competing number state,
        so a later name-only re-issue can no longer cleanly
        revive the frozen instruction -- even after a restore
        (10a2). Only a full "revive" (explicit re-issue of
        the number) clears it.
    Slot discipline (round-6 fix S2): cancel and tail are
    INDEPENDENT. A tail event only replaces the tail slot --
    it never overwrites or clears the cancel slot -- and a
    tail restore only clears the tail slot, never the cancel
    slot. The old single-value fold let a tail change
    overwrite a named cancel and a later restore erase it
    entirely, although the user never lifted the cancel.
    A "revive" clears all three slots; a "revive_tail:<m>"
    clears only a tail_len <= m; a "revive_cancel"
    (name-only revival) clears the cancel slot only when the
    name still maps to the bound number -- tail_len is None
    AND not dirty. A "generic" never downgrades a specific
    cancel.
    """
    if state is None:
        cancel, tail_len, dirty = None, None, False
    else:
        cancel, tail_len, dirty = state
    for _p, trans in events:
        if trans == "specific":
            cancel = "specific"
        elif trans.startswith("specific_tail"):
            try:
                tail_len = int(trans.split(":", 1)[1])
            except (ValueError, IndexError):
                tail_len = 0
            if cancel is not None:
                dirty = True
        elif trans == "revive":
            cancel, tail_len, dirty = None, None, False
        elif trans.startswith("revive_tail"):
            if tail_len is not None:
                try:
                    m_len = int(trans.split(":", 1)[1])
                except (ValueError, IndexError):
                    m_len = 0
                if m_len >= tail_len:
                    tail_len = None
        elif trans == "revive_cancel":
            if tail_len is None and not dirty:
                cancel = None
        elif trans == "generic":
            if cancel is None or cancel == "generic":
                cancel = "generic"
    return (cancel, tail_len, dirty)


def _most_recent_full_number(prefix, before_pos):
    """Most recent full number mentioned (requested_target /
    background) in user turns before before_pos, or None."""
    last = None
    for entry in prefix or []:
        if not isinstance(entry, dict) \
                or entry.get("kind") != "user_turn":
            continue
        pos = entry.get("position")
        text = entry.get("text")
        if not isinstance(pos, int) or not isinstance(text, str):
            continue
        if pos >= before_pos:
            continue
        for m in parse_phone_mentions(text):
            if len(m.get("normalized") or "") >= 9 \
                    and m.get("role") in ("requested_target",
                                          "background"):
                last = m["normalized"]
    return last


def _bound_turn_final_state(prefix, bound_pos, target_phone,
                            proposal_action, roster, phone_prefix):
    """Last-decisive state of the bound turn itself, or None.

    The bound turn is the last phone turn by construction, so
    a cancellation INSIDE it ("Gọi số X đi, đừng gọi nữa")
    never appears in the between-turns scan -- but it still
    cancels the instruction it states (round-4 fix S5). The
    turn's own events, folded from None, decide: a final
    specific / generic state revokes; a final revive (or no
    event) leaves the binding live.
    """
    bound_text = _bound_turn_text(prefix, bound_pos)
    if bound_text is None:
        return None
    known_names = _known_names_for_number(
        target_phone, bound_text, roster, phone_prefix) \
        if proposal_action in ("call", "message") else []
    last_full = _most_recent_full_number(prefix, bound_pos)
    events, _new = _turn_revocation_events(
        bound_text, norm_phone(target_phone), known_names,
        proposal_action, last_full)
    cancel, tail_len, _dirty = _apply_revocation_events(
        events, None)
    # External contract keeps specific / generic / None: a
    # tail-changed state reports as specific.
    if cancel == "specific" or tail_len is not None:
        return "specific"
    return cancel


def _instruction_revoked(prefix, bound_position, target_phone,
                         proposal_position, proposal_action=None,
                         roster=None, phone_prefix=None):
    """History revocation for a prior-instruction binding.

    A user turn strictly between the bound instruction and the
    proposal contributes events, applied in TEXT-POSITION order
    across the whole turn (round-4 fix S5 -- the old code
    applied one event per turn in a fixed precedence, so a
    re-issue clause before a cancel clause in the SAME turn
    swallowed the cancel; now last-decisive-in-turn wins in
    both directions, like the instruction signals' own
    clause-scan last-wins):
      - value-specific: the bound number negated / corrected
        away, a layer-C cancelled / replaced verdict with a
        reference present, a NAMED cancellation of the bound
        person with a matching action (round-4 fix S1), or a
        tail-change / explicit tail correction superseding the
        bound number (round-4 fix S2) -> state = "specific"
        (never downgraded by a later generic cancellation:
        C2g specific-then-generic stays specific);
      - explicit re-issue of the same number as a requested
        target, or an anaphoric positive continuation as a
        SETTLED history turn -> state = None (revives both
        kinds);
      - a name-only re-request of a previously named-cancelled
        person (round-5 fix F-B4-1, narrowed round-6 S1) ->
        clears the cancel slot, but ONLY when the name was
        cancelled in an earlier turn, the name resolves
        uniquely to the target (M3: a name tied to another
        number in the prefix never revives), the turn mentions
        no different full number, no tail change is currently
        in effect, and no tail change happened while
        cancelled (dirty): a bare name cannot revive across a
        number change, even a restored one (round-6 S2/10a2)
        -- only an explicit full-number re-issue revives then;
      - a tail restore (round-5 fix F-B4-2, slot discipline
        round-6 S2): a tail-change / correction back to the
        bound tail clears ONLY the tail slot, and only when
        the restore covers the changed tail's length (a
        shorter suffix does not restore the number); it never
        touches a named or generic cancellation, and a tail
        change never overwrites one either.
      - generic cancellation -> state = "generic", unless the
        state is already "specific".
    The "continuation revives generic only" rule lives in the
    CURRENT-text override in _layer_c_veto, not here: a history
    ending in a specific cancel + a current bare continuation
    still fires (v1 contract, C2d, and the round-2 author test).
    A named cancel revokes ONLY when (a) the instruction named
    that person, or the number is tied to that person via
    roster / log, AND (b) the cancel's action matches the
    proposal's action -- a cancel for someone else, for a
    number-only instruction naming nobody, or for another
    action never revokes. A tail change revokes ONLY when it
    is about the bound number: same-turn or more-recent full
    numbers defeat attribution. Returns (revoked, reason, kind).
    Only phone values are checked: prior-instruction bindings
    are phone-valued (their synthetic record carries contact_id
    None), so a contact_id proposal can never be bound this way.
    """
    if bound_position is None or not target_phone:
        return False, "", ""
    turns = []
    for entry in prefix or []:
        if not isinstance(entry, dict) \
                or entry.get("kind") != "user_turn":
            continue
        pos = entry.get("position")
        text = entry.get("text")
        if not isinstance(pos, int) or not isinstance(text, str):
            continue
        if bound_position < pos < proposal_position:
            turns.append((pos, text))
    if not turns:
        return False, "", ""
    target = norm_phone(target_phone)
    bound_text = _bound_turn_text(prefix, bound_position)
    known_names = _known_names_for_number(
        target_phone, bound_text, roster, phone_prefix) \
        if proposal_action in ("call", "message") else []
    # Between-turns scan: the bound turn itself establishes the
    # target as current, so last_full starts empty (not from
    # pre-bound turns) and threads forward turn by turn.
    # Name-cancellation memory (round-5 fix F-B4-1): names
    # cancelled in earlier turns, so a later name-only
    # re-request can revive; ambiguous names (tied to another
    # number in the prefix) never revive.
    last_full = None
    state = (None, None, False)
    cancelled = set()
    ambiguous = _ambiguous_names_for_prefix(
        prefix, target, known_names)
    for _pos, text in turns:
        events, last_full = _turn_revocation_events(
            text, target, known_names, proposal_action, last_full)
        rev_evs, cancelled = _turn_name_revive_events(
            text, target, known_names, proposal_action,
            cancelled, ambiguous)
        merged = sorted(events + rev_evs,
                        key=lambda e: (e[0], _event_order(e[1])))
        state = _apply_revocation_events(merged, state)
    cancel, tail_len, _dirty = state
    if cancel is not None or tail_len is not None:
        kind = "specific" \
            if (cancel == "specific" or tail_len is not None) \
            else "generic"
        return True, "instruction_revoked_by_later_turn", kind
    return False, "", ""


def _is_number_fragment(text):
    """True iff a turn's content is essentially just a number.

    After removing digit runs (typed or spoken), the discourse
    markers "mà" / "số" / "mới" / "khác" / "là" / "cũng", and
    politeness / possessive particles, nothing substantive
    remains. Such a fragment corrects the previous
    instruction's number; it carries no action of its own, so
    the action-match check must inherit from the immediately
    preceding instruction (round-4 fix M1). A role statement
    ("Số X là số tổng đài") keeps substantive words ("tổng
    đài") and is NOT a fragment.
    """
    if not isinstance(text, str) or not text.strip():
        return False
    import re as _re
    _spoken = {"khong", "mot", "hai", "ba", "bon", "nam", "sau",
               "bay", "tam", "chin"}
    _markers = {"ma", "so", "moi", "khac", "la", "cung", "di",
                "nhe", "nha", "a", "oi", "ne", "day", "nay",
                "cua", "em", "anh", "chi"}
    toks = _re.findall(r"[^\W_]+", fold_vietnamese(text),
                       flags=_re.UNICODE)
    rest = [t for t in toks
            if not t.isdigit() and t not in _spoken
            and t not in _markers]
    return not rest


def _bound_instruction_action(prefix, bound_pos, bound_text,
                              target_names=(), target_phones=()):
    """Action class of a bound instruction turn, with fragment
    inheritance (round-4 fix M1): a number-fragment correction
    ("Mà số Y") inherits the action of the immediately
    preceding user turn when that action is classified
    (call / message / other / contact). Anything else keeps
    the turn's own classification -- an unclassified
    instruction stays unknown (never guessed), and a fragment
    with no classified predecessor stays unknown too.

    Round-8 fix S1+M1: when target names/phones are given,
    the classification is the BINDING action class
    (binding_action_class): suppressed bare verbs and
    delegation-governed verbs do not count, so a
    forward+bare turn is "other" (not "call") and a mixed
    turn keeps only its own (non-delegated) actions. Without
    targets the old instruction_action reading stands, for
    callers that cannot judge suppression (a suppression is
    always relative to a target).
    """
    if bound_text is None:
        return "unknown"
    if target_names or target_phones:
        own = binding_action_class(bound_text, target_names,
                                   target_phones)
    else:
        own = instruction_action(bound_text)
    if own != "unknown" or not _is_number_fragment(bound_text):
        return own
    prev_text = None
    for entry in prefix or []:
        if not isinstance(entry, dict) \
                or entry.get("kind") != "user_turn":
            continue
        pos = entry.get("position")
        text = entry.get("text")
        if isinstance(pos, int) and isinstance(text, str) \
                and pos < bound_pos:
            prev_text = text
    if prev_text is None:
        return "unknown"
    if target_names or target_phones:
        prev = binding_action_class(prev_text, target_names,
                                    target_phones)
    else:
        prev = instruction_action(prev_text)
    return prev if prev != "unknown" else "unknown"


def _layer_c_veto(verdict, kind, value, prefix, roster,
                  current_text, kinds, proposal_position,
                  proposal_action):
    """Layer C verdict for one established un-fire candidate.

    Returns (vetoed, mechanism_or_None, instruction_selection,
    instruction_reason). (False, None, selection, reason) when
    layer C does not apply or allows. Veto-only: it never
    creates an un-fire, only refuses one. Two branches:

    (1) Bound-reference branch (a bound_reference source):
    checks, in order: bound-instruction addressee match (a
    current addressee explicit on BOTH sides and different
    from the bound turn's addressee refuses -- one side
    missing means unknown, never a veto; a single token equal
    to the other's last token counts as the same person, F2);
    bound-instruction action match (call / message / other /
    unknown / contact vs the proposal's action -- continuing
    a save instruction is still not a call, and an
    unclassified instruction is still not a call either, F5); history revocation, then a current-text positive
    continuation supersedes a GENERIC revocation only
    (last-decisive-wins across history + current text: a
    re-invocation after a generic stop is a new decision, but
    a bare continuation never resurrects a specifically
    -cancelled number); current-text instruction selection
    (cancelled / replaced / blocked veto).

    (2) Topic branch (S14, non-callback proposals only): when
    the verdict is topic/amount-bound (question_b_reason
    topic_amount_selects_counterpart) but carries no
    bound_reference source, a current-text topic cancellation
    / question / condition / recount / deferral vetoes. A
    positive topic continuation never vetoes (gold 1319
    keeps un-firing). If this branch ever regresses gold it
    must be reverted, not patched with a fallback.
    """
    bound_sources = _bound_reference_sources(verdict)
    if bound_sources and _has_direct_selection_source(verdict):
        return False, None, None, "layer_c_not_applicable"
    names, phones = _selection_targets(kind, value, prefix, roster)
    if isinstance(current_text, str) and current_text.strip():
        sel = analyze_instruction_selection(
            current_text, target_names=names, target_phones=phones)
    else:
        sel = {"instruction_selection": "unknown",
               "reason": "no_current_text",
               "reference_present": False}
    selection = sel["instruction_selection"]
    reason = sel["reason"]
    if bound_sources:
        prior = [s for s in bound_sources
                 if str(s.get("reason") or "").startswith(
                     "bound_reference:prior_instruction")]
        if prior:
            counterpart = prior[0].get("counterpart") or {}
            bound_pos = counterpart.get("position")
            bound_text = _bound_turn_text(prefix, bound_pos)
            # Addressee match (S10): both sides explicit and
            # different -> the current request is for someone
            # else, not a continuation of this instruction.
            # The bound addressee also joins the known names
            # for layer-C target comparisons -- but NOT for
            # the binding action class below: the forward
            # recipient must not be mistaken for the number's
            # owner, or a forward to that recipient would
            # wrongly escape suppression (round-8 fix S1).
            # base_names is captured before augmentation.
            base_names = list(names)
            bound_addr = _extract_addressee(bound_text) \
                if bound_text is not None else None
            if bound_addr is not None:
                names = list(names) + [bound_addr]
                curr_addr = _extract_addressee(current_text)
                if curr_addr is not None \
                        and not _addressee_matches(bound_addr,
                                                   curr_addr):
                    return True, \
                        "prior_instruction_addressee_mismatch", \
                        "replaced", \
                        "addressee_mismatch_%s_vs_%s" % (
                            bound_addr, curr_addr)
            # Number-as-content (round-4 fix S4, layer-C
            # defense): the current text mentions the proposal
            # number only as message content for another
            # recipient ("nhắn cho Vy số X"). The B gate
            # already refuses these for callback proposals;
            # layer C refuses them too so the content rule
            # holds on both paths, with the refusal visible
            # in the trail (question_b stays None: the
            # selection is undetermined for this action,
            # not disproven).
            if kind == "phone" \
                    and proposal_action in ("call", "message") \
                    and isinstance(current_text, str) \
                    and phone_mentions_all_content(
                        current_text, names, [value]):
                return True, \
                    "prior_instruction_recipient_mismatch", \
                    "unknown", \
                    "number_as_content_for_other_recipient"
            # Action match: the bound instruction's own action
            # must match the proposal's action when it is
            # positively classified. "other" (save / look up /
            # delete / ...) matches neither call nor message.
            # "unknown" (round-3 fix F5) also vetoes for call /
            # message proposals: an unclassified instruction
            # ("chuyển số cho Vy", bare "gửi", "báo số cho Vy")
            # must never pass through the mismatch check as if
            # it were a call -- UNKNOWN is not PROVEN. "both"
            # (includes the proposal action) and "contact"
            # (generic "liên hệ": compatible with, but not
            # proof of, a call/message) pass this check. This
            # check precedes the continuation override:
            # continuing a save instruction is still not a call.
            # A number-fragment correction inherits the action
            # of the immediately preceding instruction (M1).
            instr_action = _bound_instruction_action(
                prefix, bound_pos, bound_text, base_names,
                [value])
            if proposal_action is not None:
                if instr_action in ("call", "message") \
                        and instr_action != proposal_action:
                    return True, \
                        "prior_instruction_action_mismatch", \
                        "action_mismatch", \
                        "instruction_action_%s_vs_proposal_%s" % (
                            instr_action, proposal_action)
                if instr_action == "other" \
                        and proposal_action in ("call", "message"):
                    return True, \
                        "prior_instruction_action_mismatch", \
                        "action_mismatch", \
                        "instruction_action_other_vs_proposal_%s" \
                        % proposal_action
                if instr_action == "unknown" \
                        and proposal_action in ("call", "message"):
                    return True, \
                        "prior_instruction_action_mismatch", \
                        "action_mismatch", \
                        "instruction_action_unknown_vs_proposal_%s" \
                        % proposal_action
            # History revocation (prior-instruction only),
            # computed before the continuation override so the
            # override can be restricted by revocation kind.
            revoked, revoke_reason, revoke_kind = \
                _instruction_revoked(
                    prefix, bound_pos, value, proposal_position,
                    proposal_action, roster, prefix)
            # Bound-turn self-revocation (round-4 fix S5): the
            # bound turn is the last phone turn, so a
            # cancellation INSIDE it never appears in the scan
            # above -- but it still cancels the instruction it
            # states. Folded into (revoked, revoke_kind) so
            # the continuation override below treats it exactly
            # like a between-turns revocation of the same kind.
            if not revoked:
                self_state = _bound_turn_final_state(
                    prefix, bound_pos, value, proposal_action,
                    roster, prefix)
                if self_state is not None:
                    revoked, revoke_reason, revoke_kind = (
                        True, "instruction_revoked_by_bound_turn",
                        self_state)
            # Current positive continuation supersedes a
            # GENERIC history revocation only
            # (last-decisive-wins across history + current
            # text): a re-invocation after a generic stop is a
            # new decision, but a bare continuation must not
            # silently resurrect a specifically-cancelled
            # number -- that needs an explicit re-issue (the
            # revival check inside _instruction_revoked).
            # Recomputed with the augmented names so a
            # known-different cancel target is skipped.
            if isinstance(current_text, str) \
                    and current_text.strip():
                sel2 = analyze_instruction_selection(
                    current_text, target_names=names,
                    target_phones=phones)
                if sel2["instruction_selection"] == "continue" \
                        and (not revoked
                             or revoke_kind == "generic"):
                    return False, None, "continue", \
                        sel2["reason"]
                # Use the augmented-names judgement below, so
                # a known-different cancel target (visible only
                # via the bound addressee) is skipped there too.
                selection = sel2["instruction_selection"]
                reason = sel2["reason"]
            if revoked:
                return True, "prior_instruction_revoked", \
                    "revoked", revoke_reason
        if selection in ("cancelled", "replaced", "blocked"):
            return True, "prior_instruction_selection_veto", \
                selection, reason
        return False, None, selection, reason
    # Name-resolution branch (round-4 fix M3): the verdict rests
    # on a name uniquely resolved to this number via an
    # instruction turn. The binding itself was established in
    # module A with strict guards; layer C only adds the
    # revocation check the bound branch has: a later turn
    # revoking that instruction refuses the un-fire.
    name_sources = [s for s in verdict.get("question_a_sources")
                    or []
                    if s.get("reason")
                    == "instruction_name_resolution"]
    if name_sources:
        counterpart = name_sources[0].get("counterpart") or {}
        map_pos = counterpart.get("position")
        revoked, revoke_reason, _revoke_kind = \
            _instruction_revoked(
                prefix, map_pos, value, proposal_position,
                proposal_action, roster, prefix)
        if revoked:
            return True, "prior_instruction_revoked", \
                "revoked", revoke_reason
        return False, None, "name_resolved", \
            "instruction_name_resolution"
    # Topic branch (S14): non-callback proposals only, and
    # only when the verdict actually is topic-bound.
    if proposal_action is None and isinstance(current_text, str) \
            and current_text.strip() \
            and "topic_amount_selects_counterpart" in str(
                verdict.get("question_b_reason") or ""):
        tsel = analyze_topic_selection(current_text)
        if tsel["topic_selection"] in ("cancelled", "blocked"):
            return True, "topic_selection_veto", \
                tsel["topic_selection"], tsel["reason"]
        return False, None, tsel["topic_selection"], \
            tsel["reason"]
    return False, None, selection, reason


def _vetoed_by_selection(selection, reason, is_callback):
    """Veto rule for the R3 gate, unit-testable in isolation.

    Callback proposals: a decisive veto (negated / replaced /
    cancelled) always vetoes, and unknown vetoes EXCEPT
    no_callback_verb -- when the current text contains no verb
    head of any action, B has no textual evidence to judge, so
    it abstains and a history-grounded binding (prior
    instruction, anaphoric chat reference) stands. B judges
    current-text selection only; it must not veto what it
    cannot see. All other unknown reasons (blocked_verb_only,
    other_action_verb_only, negated_other_object,
    quoted_mention_only, no_current_text, invalid_action,
    positive_verb_not_governing_target -- round-10 fix S1:
    a positive verb governing another object is not
    selection evidence for this target)
    veto for callback proposals: a blocked verb is not a
    request, and a verb of another action never selects this
    action (coordinator delta-2 fix for the reviewer's
    abstention hole: the old no_action_evidence conflated
    "no verb at all" with "other-action verb" and "blocked
    verb").
    Non-callback proposals: only a decisive, target-attached
    veto counts; unknown passes through and a standalone
    generic veto does not veto an unrelated action.
    """
    if selection == "positive":
        return False
    if not is_callback:
        return selection in ("negated", "replaced", "cancelled") \
            and reason != "generic_callback_negated"
    if selection == "unknown":
        return reason != "no_callback_verb"
    return True


def decide(call, prefix, roster, current_text, kinds,
           proposal_position=None, eligibility=False):
    """Candidate Gate 2 decision for one proposal call.

    prefix: raw prefix entries (history + session, proposal
    excluded). roster: [{id, name, phone}]. current_text: the
    current request text (dataset text in gold audit, ASR model
    transcript in shadow). kinds: catalog kind map or None.
    eligibility (R5, default False): when True, ALSO report the
    object-state eligibility of the proposal's consumer (B's
    check_eligibility over the prefix ledger) in notes["eligibility"]
    as {consumer, entity_id, status, reason}. Report-only: it NEVER
    changes fired/applicable. Unknown (unsupported consumer, missing
    entity, missing context) is reported as unknown, never guessed.
    Snapshot-based staleness is NOT used here (ledger-only query).
    Eligibility is reported only when the gate is applicable (the
    main path); early-return decisions carry no eligibility field.
    """
    roster = roster or []
    if proposal_position is None:
        positions = [e.get("position", 0) for e in (prefix or [])
                     if isinstance(e, dict)]
        proposal_position = (max(positions) + 1) if positions else 0
    # --- P3g filtering FIRST: the baseline gate's priors AND the
    # ledger must see the same filtered session log records as the
    # phone/callback module. Otherwise a session-created outgoing
    # record would pass the baseline gate directly (log-grounded),
    # and the adapter would have nothing to correct: filtering
    # only A's prefix is not enough. History records are never
    # filtered (pre-session origin). ---
    phone_prefix, n_filtered = filtered_prefix_for_phone(prefix)
    priors = _priors_for_gate(phone_prefix)
    baseline = gate_read_before_write(call, priors, roster, kinds)
    adjustments = []
    notes = {"filtered_log_records": n_filtered, "adapter_gaps": [],
             "ledger_notes": {}}
    if not baseline.applicable:
        return CandidateDecision(
            False, False, False, baseline.reason, adjustments, notes)
    # --- per-reference baseline status (mirror the gate loop) ---
    roster_ids = {nfc_lower(e.get("id")) for e in roster
                  if isinstance(e, dict) and e.get("id")}
    roster_names = {nfc_lower(e.get("name")) for e in roster
                    if isinstance(e, dict) and e.get("name")}
    roster_phones = {e.get("id"): e.get("phone") for e in roster
                     if isinstance(e, dict) and e.get("id")
                     and e.get("phone")}
    refs = _contact_references(call)
    ids = _entity_ids(call)
    missing_contact = []  # (kind, value)
    passed_contact_ids = []
    passed_contact_names = []
    passed_entity = []  # (value, [slots])
    for kind, value in refs:
        if kind == "id":
            if _establishes_contact_id(priors, roster_ids, value, kinds):
                passed_contact_ids.append(value)
            else:
                missing_contact.append((kind, value))
        elif kind == "name":
            if _establishes_contact_name(priors, roster_names,
                                         value, kinds):
                passed_contact_names.append(value)
            else:
                missing_contact.append((kind, value))
        elif kind == "phone":
            if not _establishes_contact_phone(priors, roster_phones,
                                              value):
                missing_contact.append((kind, value))
    for eid in sorted(ids):
        slots = [key for key, val in (call.get("arguments") or {}).items()
                 if val == eid and key.endswith("_id")]
        if all(_establishes_entity_id(priors, slot, eid, kinds)
               for slot in slots):
            passed_entity.append((eid, slots))
        # entity-id fires are never un-fired by phone/callback
        # evidence; they stand (recorded in baseline_reason).
    # --- adjustment 1: un-fire covered contact references ---
    fired = baseline.fired
    # Proposal action for history binding (round-7 fix S3):
    # the phone-evidence binding must know which action is
    # queried so fully-delegated turns can be excluded from
    # prior-instruction candidates. Non-callback proposals
    # get None (no exclusion, old behaviour).
    proposal_action = _CALLBACK_ACTIONS.get(call.get("name"))
    if baseline.fired and missing_contact:
        covered_all = True
        for kind, value in missing_contact:
            if kind == "phone":
                verdict = phone_evidence_for(
                    value, phone_prefix, roster, current_text,
                    action=proposal_action)
            else:
                ref_args = {"contact_id": value} if kind == "id" \
                    else {"contact_name": value}
                verdict = callback_reference_for(
                    ref_args, phone_prefix, roster, current_text,
                    consumer_tool=call.get("name"))
            if verdict["established"]:
                # --- negation veto gate (R3): A proves the binding,
                # but the un-fire also requires POSITIVE action
                # selection toward this target. B is a veto-only
                # gate: it never proves a binding on its own (its
                # "positive" means "no veto found"), so it runs
                # only after A established, and only for proposals
                # whose action IS a callback. Anything but
                # positive refuses the un-fire (safe direction);
                # the mention itself is recorded separately, never
                # equated with selection.
                selection = None
                selection_reason = None
                mention_present = None
                vetoed = False
                action = _CALLBACK_ACTIONS.get(call.get("name"))
                # Veto gate (R3), refined (delta-2): for callback
                # proposals the request IS a callback, so a
                # decisive veto (negated / replaced / cancelled)
                # always vetoes, and unknown vetoes EXCEPT
                # no_callback_verb: when the current text has no
                # verb head of any action, B has no textual
                # evidence to judge, so it abstains and a
                # history-grounded binding (prior instruction,
                # anaphoric chat reference) stands. B judges
                # current-text selection only; it must not veto
                # what it cannot see (gold 0764: prior
                # instruction binding + verb-less current text).
                # All other unknown reasons veto for callback
                # proposals (blocked verb, other-action verb).
                # For non-callback proposals B does not cover the
                # proposal's action, so only a decisive,
                # target-attached veto counts; unknown passes
                # through, and a standalone generic veto
                # ("đừng gọi nữa" with no target selection) does
                # not veto an unrelated action. This closes the
                # hole where a negated callback sentence un-fired
                # a non-callback proposal, without breaking
                # topic/amount bindings like gold 1319 (no
                # callback verb -> B unknown -> pass-through).
                names, phones = _selection_targets(
                    kind, value, phone_prefix, roster)
                if isinstance(current_text, str) \
                        and current_text.strip():
                    sel = analyze_action_selection(
                        current_text, target_names=names,
                        target_phones=phones,
                        action=action if action is not None
                        else "any")
                else:
                    sel = {"selection": "unknown",
                           "reason": "no_current_text",
                           "mention_present": False}
                selection = sel["selection"]
                selection_reason = sel["reason"]
                mention_present = sel["mention_present"]
                if action is not None:
                    vetoed = _vetoed_by_selection(
                        selection, selection_reason, True)
                else:
                    vetoed = _vetoed_by_selection(
                        selection, selection_reason, False)
                # --- layer C (R4): a bound reference proves
                # WHICH instruction is meant, never that the user
                # wants to CONTINUE it. Layer C is veto-only: it
                # can refuse an un-fire B allowed (abstain, or
                # positive for a different target), never create
                # one B refused. Its fields are recorded on both
                # branches so the trail shows the claim actually
                # proven: continue (real continuation basis),
                # unknown (honest abstain, e.g. a bare reference),
                # or a veto reason. ---
                c_vetoed, c_mechanism, c_selection, c_reason = \
                    _layer_c_veto(
                        verdict, kind, value, phone_prefix, roster,
                        current_text, kinds, proposal_position,
                        action)
                # --- round-9 fix S1: a bare mention is not
                # selection evidence. B abstains on
                # no_callback_verb so that a history-grounded
                # binding CAN stand -- but the abstention on
                # its own must not authorize an un-fire.
                # Un-fire through a B abstention additionally
                # requires layer C to affirmatively confirm a
                # continuation ("continue", e.g. gold 0764:
                # prior instruction + verb-less
                # continuation) or a name resolution
                # ("name_resolved"). Otherwise there is no
                # selection evidence from either layer: a
                # bare number mention (topic / filler /
                # question / evaluation) or a
                # transfer-to-agent mention ("chuyển số X
                # cho em": handing a number to the agent
                # is not a request to call it) must not
                # authorize a call/sms. Veto (safe
                # direction). Exception: when layer C is
                # not applicable (bound reference AND a
                # direct selection source coexist), an
                # explicit continuation phrase in the
                # current text still counts as selection
                # evidence ("làm như lúc nãy đi, số X" is
                # a genuine continuation with the number
                # restated, unlike a bare restatement).
                # This only touches callback proposals:
                # non-callback proposals keep their
                # unknown pass-through (gold 1319 topic
                # branch), because their action is not
                # covered by B. The trail keeps
                # selection_reason=no_callback_verb plus
                # the layer-C fields, so this joint veto
                # stays distinguishable from B's own
                # vetoes (whose reasons are never
                # no_callback_verb).
                #
                # Round-9 narrowing (two gates, both
                # load-bearing against old pinned tests):
                # (a) mention_present must be True: a
                # bare anaphor ("Như lúc nãy", "Như em
                # dặn lúc nãy") mentions NO number, so
                # it refers to the prior instruction
                # itself and keeps the v1 pinned
                # abstain-preserved un-fire (basis
                # binding); only a direct number
                # restatement is a bare mention that
                # must not authorize an action.
                # (b) An M2 correction frame ("Mà số Y
                # là số mới") explicitly selects the
                # new number, so mentions carrying the
                # ma_new_number_selection reason are
                # exempt: the frame is selection
                # evidence, not a bare mention.
                # (c) A roster-owner recipient ("cho
                # <owner>"): the N1 owner-tie beats
                # forward suppression, so the mention
                # is not forwarded away and the
                # abstention stands (batch-5 7b).
                if action is not None and not vetoed \
                        and not c_vetoed \
                        and selection == "unknown" \
                        and selection_reason == "no_callback_verb" \
                        and mention_present \
                        and c_selection not in (
                            "continue", "name_resolved"):
                    continued = False
                    if c_reason == "layer_c_not_applicable" \
                            and isinstance(current_text, str) \
                            and current_text.strip():
                        sel_na = analyze_instruction_selection(
                            current_text, target_names=names,
                            target_phones=phones)
                        continued = sel_na[
                            "instruction_selection"] == "continue"
                    ma_new_number = False
                    if isinstance(current_text, str) \
                            and current_text.strip():
                        ma_new_number = any(
                            m.get("normalized") == value
                            and m.get("reason")
                            == "ma_new_number_selection"
                            for m in parse_phone_mentions(
                                current_text))
                    # (c) Roster-owner recipient (N1 pin):
                    # when the current text addresses the
                    # number to its roster owner ("cho
                    # <owner>"), the owner-tie beats
                    # forward suppression -- the mention
                    # is not forwarded away -- so the
                    # abstention stands. Distinct from
                    # S1 transfer-to-agent ("cho em"): a
                    # generic addressee is not the owner.
                    owner_recipient = False
                    if isinstance(current_text, str) \
                            and current_text.strip() and roster:
                        curr_tokens = fold_vietnamese(
                            current_text).split()
                        for entry in roster:
                            if not isinstance(entry, dict):
                                continue
                            entry_phone = entry.get("phone")
                            if entry_phone is None:
                                continue
                            try:
                                entry_norm = norm_phone(
                                    str(entry_phone))
                            except Exception:
                                continue
                            if entry_norm != value:
                                continue
                            owner_name = entry.get("name")
                            if not owner_name:
                                continue
                            owner_tokens = fold_vietnamese(
                                str(owner_name)).split()
                            if not owner_tokens:
                                continue
                            needle = ["cho"] + owner_tokens
                            nlen = len(needle)
                            if any(
                                    curr_tokens[i:i + nlen]
                                    == needle
                                    for i in range(
                                        len(curr_tokens)
                                        - nlen + 1)):
                                owner_recipient = True
                                break
                    if not continued and not ma_new_number \
                            and not owner_recipient:
                        vetoed = True
                if vetoed or c_vetoed:
                    covered_all = False
                    # First-refusal-wins attribution: layer C
                    # exists to refuse what B allowed, so when B
                    # already refused, B's refusal is recorded
                    # (its selection_reason stays visible); C's
                    # fields remain in the trail below either
                    # way. This preserves v1's pinned boundary
                    # where a named other-clause cancellation is
                    # B's negated_other_object veto, not a
                    # layer-C override.
                    if c_vetoed and not vetoed:
                        mechanism = c_mechanism
                        # A decisive layer-C refusal (cancelled /
                        # replaced / revoked) disproves selection
                        # for this proposal; a blocked one
                        # (question / recount / quote) or an
                        # action mismatch leaves it undetermined
                        # for this action, never proven.
                        question_b = False if c_selection in (
                            "cancelled", "replaced", "revoked") \
                            else None
                    else:
                        mechanism = "callback_selection_veto"
                        question_b = False if selection in (
                            "negated", "replaced",
                            "cancelled") else None
                    adjustments.append({
                        "reference": "%s %s" % (kind, value),
                        "old": "fired", "new": "fired",
                        "mechanism": mechanism,
                        "basis": verdict["basis"],
                        "question_b": question_b,
                        "question_b_a":
                            verdict["question_b_target_selected"],
                        "question_b_reason":
                            verdict["question_b_reason"],
                        "selection": selection,
                        "selection_reason": selection_reason,
                        "mention_present": mention_present,
                        "instruction_selection": c_selection,
                        "instruction_reason": c_reason,
                        "sources": verdict["question_a_sources"]})
                else:
                    adjustments.append({
                        "reference": "%s %s" % (kind, value),
                        "old": "fired", "new": "passed",
                        "mechanism": "phone_callback_evidence",
                        "basis": verdict["basis"],
                        "question_b":
                            verdict["question_b_target_selected"],
                        "question_b_reason":
                            verdict["question_b_reason"],
                        "selection": selection,
                        "selection_reason": selection_reason,
                        "mention_present": mention_present,
                        "instruction_selection": c_selection,
                        "instruction_reason": c_reason,
                        "sources": verdict["question_a_sources"]})
            else:
                covered_all = False
                adjustments.append({
                    "reference": "%s %s" % (kind, value),
                    "old": "fired", "new": "fired",
                    "mechanism": "phone_callback_evidence_insufficient",
                    "basis": verdict["basis"],
                    "question_b": verdict["question_b_target_selected"],
                    "question_b_reason": verdict["question_b_reason"],
                    "sources": verdict["question_a_sources"]})
        # Un-fire only when EVERY missing contact reference is
        # covered AND no entity-id fire stands (entity fires are
        # visible in baseline_reason; recompute: gate fired with
        # no missing entity ref means contact-only fire).
        entity_fired = any(
            not all(_establishes_entity_id(priors, slot, eid, kinds)
                    for slot in [key for key, val in
                                 (call.get("arguments") or {}).items()
                                 if val == eid and key.endswith("_id")])
            for eid in sorted(ids))
        bare_mutate_fire = (not refs and not ids)
        if covered_all and not entity_fired and not bare_mutate_fire:
            fired = False
    # --- adjustment 2: lifecycle suppression of passed id refs ---
    if True:  # suppression applies whether fired or passed
        ledger, ledger_notes = build_ledger(phone_prefix, roster, kinds)
        notes["ledger_notes"] = ledger_notes
        suppressions = []
        for value in passed_contact_ids:
            status, _ev, reason = ledger.query(
                "contacts.contacts", value, "existence",
                position=proposal_position)
            if status == "invalidated":
                suppressions.append(("contact_id %s" % value, reason))
            elif status == "unknown":
                notes["adapter_gaps"].append(
                    "ledger unknown for passed contact_id %s" % value)
        for eid, slots in passed_entity:
            for slot in slots:
                registry = CONSUMER_REGISTRY.get(slot)
                if registry is None:
                    continue
                status, _ev, reason = ledger.query(
                    registry, eid, "existence",
                    position=proposal_position)
                if status == "invalidated":
                    suppressions.append(
                        ("entity id %s (slot %s)" % (eid, slot), reason))
                    break
                elif status == "unknown":
                    notes["adapter_gaps"].append(
                        "ledger unknown for passed entity id %s "
                        "slot %s" % (eid, slot))
        # Name refs that passed via the (possibly stale) roster:
        # resolve the name to a roster id ONLY on a unique match,
        # then apply the same existence check. A deleted contact
        # must not keep passing through its name (reviewer C2
        # latent hole; no contacts.delete exists today, but the
        # check is cheap and closes the name path for any future
        # delete-like invalidation).
        for name in passed_contact_names:
            resolved = _resolve_roster_name(roster, name)
            if resolved is None:
                notes["adapter_gaps"].append(
                    "name %s does not resolve uniquely in roster; "
                    "no suppression" % name)
                continue
            status, _ev, reason = ledger.query(
                "contacts.contacts", resolved, "existence",
                position=proposal_position)
            if status == "invalidated":
                suppressions.append(
                    ("contact_name %s -> %s" % (name, resolved),
                     reason))
            elif status == "unknown":
                notes["adapter_gaps"].append(
                    "ledger unknown for passed contact_name %s" % name)
        if suppressions:
            fired = True
            for ref, reason in suppressions:
                adjustments.append({
                    "reference": ref, "old": "passed", "new": "fired",
                    "mechanism": "lifecycle_suppression",
                    "basis": None, "question_b": None,
                    "question_b_reason": reason, "sources": []})
    # --- selection-consistency check (selection round) ---
    # PIN BOUNDARY: this runs ONLY when the baseline gate
    # passed AND no earlier adjustment fired (not
    # baseline.fired, not fired). When the baseline fired, an
    # un-fire rests on a specific A+B+layer-C binding the
    # current text does not cancel (the pinned veto-only
    # contract, incl. gold 1319 and the
    # positive_action_no_target_veto pin); re-vetoing there
    # would break pinned bindings. The passed path had NO
    # selection check at all -- a confirmed number / ID was
    # waved through before anyone checked the right person,
    # the right action, or the right role for that number
    # (chat2 ATK-001/007/009/014/015). This check fires ONLY
    # on an explicit contradiction reported by
    # analyze_selection_consistency; a genuine abstention
    # (consistent True, no decision) still stands -- the
    # baseline pass stands. That abstention rule does NOT
    # cover H2-S11: decision "unknown_pending" is NOT an
    # abstention, it is a structured UNKNOWN that must
    # still fire (fired True) with mechanism
    # "unknown_pending", never fired False, never
    # re-labelled as a discharged completion. The
    # adjustment trail is what carries the decision into
    # the observer/shadow logs (the observer copies
    # adjustments whole); notes["selection_decision"]
    # carries the same fields for in-process consumers.
    # It is a shadow adjustment like the lifecycle one:
    # same adjustment record shape.
    if not baseline.fired and not fired \
            and proposal_action is not None \
            and isinstance(current_text, str) \
            and current_text.strip():
        sel_names, sel_phones = set(), set()
        for kind, value in refs:
            names, phones = _selection_targets(
                kind, value, phone_prefix, roster)
            sel_names.update(names)
            sel_phones.update(phones)
        # R5 identity: the proposal's contact_id, if any,
        # is passed through to the selection check as the
        # proposal's identity, so it is resolved against
        # the observed roster there instead of collapsing
        # to a name/phone target. The check runs for an
        # id proposal even when no name/phone target was
        # derived: with an id, the check no longer needs
        # a name/phone target to have a proposal key.
        proposal_contact_id = None
        for kind, value in refs:
            if kind == "id":
                proposal_contact_id = value
                break
        if sel_names or sel_phones \
                or proposal_contact_id is not None:
            # Prior user-turn texts: the check consults
            # them ONLY for duplicate-name qualification
            # and for blocked-verb history-positive
            # abstention (see its docstring). Session tool
            # entries carry no user text and are skipped.
            history_texts = [
                e.get("text") for e in (prefix or [])
                if isinstance(e, dict)
                and e.get("kind") == "user_turn"
                and isinstance(e.get("text"), str)]
            try:
                consistency = analyze_selection_consistency(
                    current_text, proposal_action,
                    target_names=sorted(sel_names),
                    target_phones=sorted(sel_phones),
                    roster=roster, history_texts=history_texts,
                    proposal_contact_id=proposal_contact_id)
            except Exception as exc:  # never break deciding
                notes["adapter_gaps"].append(
                    "selection_consistency_error:%r" % (exc,))
                consistency = {"consistent": True}
            # H2-S11: decision is checked BEFORE the binary
            # flag, on purpose. An old caller that read
            # only consistent would still fire here
            # (consistent stays False for unknown_pending),
            # but the mechanism must be unknown_pending,
            # not selection_mismatch, or the shadow log
            # would re-label an unproven instruction as a
            # proven contradiction. .get() keeps the
            # exception fallback ({"consistent": True},
            # no decision) on the old pass path.
            if consistency.get("decision") == "unknown_pending":
                fired = True
                ref_label = ("%s %s" % refs[0]) if refs \
                    else (call.get("name") or "proposal")
                adjustments.append({
                    "reference": ref_label, "old": "passed",
                    "new": "fired", "mechanism": "unknown_pending",
                    "basis": None, "question_b": None,
                    "question_b_reason": "unknown_pending: %s "
                    "(active_status=%s, blocked_subtype=%s)"
                    % (consistency.get("detail"),
                       consistency.get("active_status"),
                       consistency.get("blocked_subtype")),
                    "sources": []})
                notes["selection_decision"] = {
                    "decision": "unknown_pending",
                    "unknown_kind": consistency.get(
                        "unknown_kind"),
                    "active_status": consistency.get(
                        "active_status"),
                    "blocked_subtype": consistency.get(
                        "blocked_subtype"),
                    "mismatch": consistency.get("mismatch"),
                    "last_event": consistency.get("last_event"),
                    }
            elif not consistency["consistent"]:
                fired = True
                ref_label = ("%s %s" % refs[0]) if refs \
                    else (call.get("name") or "proposal")
                adjustments.append({
                    "reference": ref_label, "old": "passed",
                    "new": "fired", "mechanism": "selection_mismatch",
                    "basis": None, "question_b": None,
                    "question_b_reason": "%s: %s" % (
                        consistency["mismatch"],
                        consistency["detail"]),
                    "sources": []})
                if consistency.get("decision") == "mismatch":
                    # S11 discharged / cancelled / none
                    # taxonomy (check-5 direct past govern):
                    # still a selection_mismatch fire, but
                    # the decision fields are preserved in
                    # notes so the log does not collapse
                    # discharged into unknown_pending.
                    notes["selection_decision"] = {
                        "decision": "mismatch",
                        "active_status": consistency.get(
                            "active_status"),
                        "blocked_subtype": consistency.get(
                            "blocked_subtype"),
                        "mismatch": consistency.get("mismatch"),
                        "last_event": consistency.get(
                            "last_event"),
                        }
    # --- R5 eligibility report (shadow only; NEVER changes fired) ---
    if eligibility:
        tool_name = (call or {}).get("name")
        call_args = (call or {}).get("arguments") or {}
        contract = CONSUMER_CONTRACTS.get(tool_name or "")
        entity_id = call_args.get(contract["id_arg"]) \
            if contract else None
        try:
            status, reason = check_eligibility(
                ledger, tool_name, entity_id,
                position=proposal_position, args=call_args)
        except Exception as exc:  # never let reporting break deciding
            status, reason = "unknown", "eligibility_error:%r" % (exc,)
        notes["eligibility"] = {
            "consumer": tool_name, "entity_id": entity_id,
            "status": status, "reason": reason}
    return CandidateDecision(
        fired, True, baseline.fired, baseline.reason, adjustments, notes)
