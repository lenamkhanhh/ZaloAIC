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

from lifemate_gates import (
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
from lifemate_phone_callback_evidence import (
    callback_reference_for,
    norm_phone,
    phone_evidence_for,
)
from lifemate_callback_negation import analyze_action_selection
from lifemate_evidence_lifecycle import (
    EvidenceLedger,
    classify_tool,
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
    quoted_mention_only, no_current_text, invalid_action)
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
           proposal_position=None):
    """Candidate Gate 2 decision for one proposal call.

    prefix: raw prefix entries (history + session, proposal
    excluded). roster: [{id, name, phone}]. current_text: the
    current request text (dataset text in gold audit, ASR model
    transcript in shadow). kinds: catalog kind map or None.
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
    if baseline.fired and missing_contact:
        covered_all = True
        for kind, value in missing_contact:
            if kind == "phone":
                verdict = phone_evidence_for(
                    value, phone_prefix, roster, current_text)
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
                if vetoed:
                    covered_all = False
                    adjustments.append({
                        "reference": "%s %s" % (kind, value),
                        "old": "fired", "new": "fired",
                        "mechanism": "callback_selection_veto",
                        "basis": verdict["basis"],
                        "question_b": False
                        if selection in ("negated", "replaced",
                                         "cancelled") else None,
                        "question_b_a":
                            verdict["question_b_target_selected"],
                        "question_b_reason":
                            verdict["question_b_reason"],
                        "selection": selection,
                        "selection_reason": selection_reason,
                        "mention_present": mention_present,
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
    return CandidateDecision(
        fired, True, baseline.fired, baseline.reason, adjustments, notes)
