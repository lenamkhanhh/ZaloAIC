#!/usr/bin/env python3
"""G&G paired gold audit: baseline Gate 2 (61d84390) vs candidate
(adapter: phone/callback evidence + lifecycle suppression) on the
SAME inputs, SAME scope, SAME dev split.

Scope discipline (user rule): dev1237 only, every gold write
(non-read, non-ask), no gold call excluded because a gate lacks
support. The only separation is the train_1696 anomaly, reported
separately AND in a with/without sensitivity line. A scope change,
if ever needed, must be reported on a common scope with each change
listed separately -- this script makes no scope change.

Inputs mirror analysis/gates_precision_audit.py exactly: history
priors from assistant turns, history rosters from history results,
full-trajectory ToolEnv replay (reads AND writes, gold order),
rosters/priors restricted to position < pos, current_text = the
sample's dataset audio_text (dataset-provided transcript, same as
the baseline audit's G3 input; the SHADOW audit uses ASR model
transcripts instead -- the two audits differ deliberately).

Candidate prefix (raw events, proposal excluded):
  history events (origin "history", positions 0..H-1 in turn order)
  + replay events before pos (origin "session", positions H+idx)
  + history user-turn texts as {"kind": "user_turn"} entries.
Roster = hist_rosters + replay rosters with position < pos,
merged by id per the unified R4-CONFLICT rule (see
_backfill_roster_entry / the state API): a later successful
read fills a missing field and replaces a differing valid
field (last-wins, in event order); a missing or invalid
value never overwrites; a failed read neither creates nor
backfills; a lifecycle-confirmed contacts.update is a
per-field barrier, and a post-barrier read contradicting
it (or a single read contradicting itself) makes that
field UNKNOWN, not a choice.
Roster entries carry only id/name/phone plus a valid
string ``relation`` (the one structured attribute D1 needs
for train_0063/0225), taken only from successful reads;
an explicit ok=False result contributes no roster entry,
and no other string field is forwarded as evidence.

Per gold write the script records: baseline fired/applicable,
candidate fired/applicable, the reference group (phone / contact /
other-ids), every adjustment, and the candidate-with-empty-evidence
decision (synthetic control: must fire when applicable, else the
candidate passes vacuously). Decision changes are listed in full
for adjudication (the script does NOT adjudicate: agreement with
gold alone does not prove the new evidence was valid -- the
coordinator adjudicates each change from its adjustment trail).

SANCTIONED ACCESS ONLY: observations come from ToolEnv.call
replay; this script NEVER opens train_environment/ or state.json.

Usage:
  python3 analysis/gg_paired_audit.py \
      --train-jsonl <train.jsonl> --data-root <dir containing train/> \
      --split lifemate/splits/train_dev_heldout.json \
      --lifemate-dir <dir containing lifemate/*.py> \
      [--out-json /tmp/gg_paired.json]
"""

import argparse
import collections
import json
import sys
from pathlib import Path


def is_read(name, kinds):
    if kinds is not None and name in kinds:
        return kinds[name] == "read"
    verb = (name or "").split(".", 1)[1] if "." in (name or "") else ""
    return any(verb == v or verb.startswith(v + "_") for v in
               ("search", "list", "get", "status", "forecast", "balance",
                "history", "detail"))


def load_kind_map(train_dir):
    try:
        cat = json.load(open(str(Path(train_dir)
                               / "train_tools_catalog.json")))
        kinds = {}
        for app in cat.get("apps", []):
            for tool in app.get("tools", []):
                if isinstance(tool.get("name"), str):
                    kinds[tool["name"]] = tool.get("kind", "")
        return kinds
    except Exception:
        return {}


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


def _harness_roster_entry(entry):
    """One roster entry, on the harness whitelist only.

    D1 (lifemate_callback_negation.py) matches a descriptor
    against every roster field other than id/name/phone, so
    forwarding every string field would let an arbitrary
    string (a note, a company, a free-text field) qualify a
    duplicate as if it were structured evidence. The harness
    therefore forwards exactly id/name/phone/relation:
    ``name`` is the raw string when valid, else ""
    (missing); ``phone`` is the raw string when it passes
    the phone contract, else "" (missing); ``relation`` is
    present only when it is a valid string. Any other field
    is dropped, and a non-string ``name`` / ``relation``
    or a phone failing the contract is dropped rather than
    coerced. Returns None when the entry has no id.
    Missing is absent, None, or "" (name/phone), and
    absent (relation)."""
    if not isinstance(entry, dict) or not entry.get("id"):
        return None
    roster_entry = {"id": entry["id"],
                    "name": entry["name"] if _valid_text(
                        entry.get("name")) else "",
                    "phone": entry["phone"] if _valid_phone(
                        entry.get("phone")) else ""}
    if _valid_text(entry.get("relation")):
        roster_entry["relation"] = entry["relation"]
    return roster_entry


# ---------------------------------------------------------------------------
# Unified roster conflict rule (R4-CONFLICT, same rule in all three
# roster paths: this harness, lifemate/lifemate_observer.py, and
# lifemate/agent.py -- the modules cannot import each other, so the
# rule is stated in full in each place and must stay identical):
#
# 1. LAST-WINS, IN ORDER. For the same registry
#    ("contacts.contacts") and contact_id, a valid field from
#    a NEWER successful read replaces the older value.
#    Order is the order of events in the prefix / history /
#    replay (list order, which is position order), never
#    the system clock. A merged roster is a current-state
#    view at proposal time, not a freeze at first sight.
# 2. A field the newer read does not carry does NOT delete
#    the older value: absence in a read is not a deletion
#    signal (a later search may be a different query
#    returning a subset). The older value is kept.
# 3. A failed / noop read creates, updates, or deletes
#    nothing. In the harness history path, only an explicit
#    ok=False result is excluded (a result with no ok field
#    keeps the old behaviour and still contributes -- that
#    pre-existing success definition is NOT redefined by
#    this change; see the report). In the replay path, a
#    read contributes only when its result is ok-truthy.
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
# could itself become qualifying evidence). In main(),
# conflicts for each evaluated gold write are collected
# into the output JSON's top-level "roster_conflicts"
# list (sample, pos, conflicts) so the coordinator can
# adjudicate them; they never change a decision by
# themselves, and they never enter the roster passed to
# decide(). The list-based collect_rosters API (results
# only, no event info) cannot see barriers, so it applies
# rules 1-4 and 6a only; the state API below applies the
# full rule, including barriers, and is what main() uses.
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
    index (enumeration order, not a clock). A field in
    unknown_map for an id becomes UNKNOWN in state
    (rule 6a), regardless of any older value."""
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
    event, or None. Confirmed means: its contact_id argument
    is truthy, and its returned item is a dict whose id
    equals that argument (the PATCH_VERIFIED shape). The
    barrier fields are the item's whitelisted valid fields,
    normalised by _harness_roster_entry. Anything else --
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
    return _harness_roster_entry(item)


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


def _merge_roster_entry(out, roster_entry):
    """Append ``roster_entry`` to ``out`` or merge it into
    its existing entry for the same id, per the unified
    rule (last-wins for a differing valid value, fill for
    a missing field, never overwrite with a missing
    value). This list wrapper carries no barrier / UNKNOWN
    state; the state API is what main() uses."""
    for existing in out:
        if existing["id"] == roster_entry["id"]:
            _backfill_roster_entry(existing, roster_entry)
            return
    out.append(roster_entry)


def _entries_from_result(results):
    """Normalised roster entries from a result value,
    recursively, mirroring collect_rosters: any "contacts"
    list with id-bearing entries counts; recursion does not
    descend into "phone" values. A branch whose dict has
    explicit ok=False contributes nothing (a failed read
    is not roster evidence). Returns a list (not merged)."""
    out = []
    if isinstance(results, dict):
        if results.get("ok") is False:
            return out
        contacts = results.get("contacts")
        if isinstance(contacts, list):
            for entry in contacts:
                roster_entry = _harness_roster_entry(entry)
                if roster_entry is not None:
                    out.append(roster_entry)
        for key, value in results.items():
            if key != "phone":
                out.extend(_entries_from_result(value))
    elif isinstance(results, list):
        for value in results:
            out.extend(_entries_from_result(value))
    return out


def collect_rosters(results, out):
    """Collect roster entries from ``results`` into ``out``,
    merging by id per the unified rule (last-wins for a
    differing valid value, fill for a missing field, never
    overwrite with a missing value, intra-read conflicts
    become UNKNOWN and drop the field). A failed read
    (explicit ok=False) contributes nothing: it neither
    creates nor backfills an entry. This list API sees
    results only, not events, so it cannot apply lifecycle
    barriers (rule 5) and records no conflicts; main()
    uses the state API for the full rule."""
    entries = _entries_from_result(results)
    if not entries:
        return
    grouped, unknown_map = _group_read_entries(entries)
    # Merge the grouped entries into the plain list, with
    # intra-read UNKNOWN fields dropping the old value.
    for entry in grouped:
        contact_id = entry["id"]
        existing = None
        for cand in out:
            if cand["id"] == contact_id:
                existing = cand
                break
        if existing is None:
            existing = {"id": contact_id, "name": "",
                        "phone": ""}
            out.append(existing)
        for field in _ROSTER_FIELDS:
            if field in unknown_map.get(contact_id, set()):
                _drop_field(existing, field)
                continue
            if field not in entry:
                continue
            new = entry[field]
            if new is None or new == "":
                continue
            existing[field] = new


def outcome_of(res):
    if not isinstance(res, dict):
        return "unknown"
    if res.get("ok") is True and res.get("done") is not False:
        return "succeeded"
    if res.get("ok") is False:
        return "schema_rejected"
    return "noop"


def group_of(call):
    args = call.get("arguments") or {}
    if args.get("phone_number"):
        return "phone"
    if args.get("contact_id") or args.get("contact_name") \
            or (isinstance(args.get("to"), str) and args.get("to")
                and "@" not in args["to"]):
        return "contact"
    if any(k.endswith("_id") for k in args):
        return "other_ids"
    return "other"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--train-jsonl", required=True)
    ap.add_argument("--data-root", required=True)
    ap.add_argument("--split", required=True)
    ap.add_argument("--lifemate-dir", required=True)
    ap.add_argument("--out-json", default="/tmp/gg_paired.json")
    args = ap.parse_args()

    # Package-mode import contract: --lifemate-dir names the package
    # directory itself; its PARENT (the repo root) goes on sys.path
    # and modules are imported as lifemate.* -- the same contract as
    # the real entrypoint (lifemate/run.py). Never add lifemate/
    # itself: that path masked the observer import failure at d1090d1d.
    _lm_dir = Path(args.lifemate_dir)
    if _lm_dir.name != "lifemate":
        raise SystemExit(
            "--lifemate-dir must name the package directory "
            "(a directory called 'lifemate'); got: %s" % args.lifemate_dir)
    sys.path.insert(0, str(_lm_dir.parent))
    from lifemate.lifemate_gates import (  # noqa: E402
        PriorCall, flatten_result_entries, gate_read_before_write)
    from lifemate.lifemate_gates_adapter import decide  # noqa: E402
    train_dir = str(Path(args.train_jsonl).resolve().parent)
    sys.path.insert(0, train_dir)
    from zaic_tools import ToolEnv  # noqa: E402

    split = json.load(open(args.split))
    dev_ids = {k for k, v in split.items() if v == "dev"}
    kinds = load_kind_map(train_dir)

    stats = collections.Counter()
    by_group = collections.defaultdict(collections.Counter)
    changes = []   # candidate decision != baseline decision
    fired_rows = []  # rows where baseline or candidate fired
    anomaly_rows = []
    errors = []
    roster_conflict_rows = []  # R4-CONFLICT: per evaluated write,
    # the roster conflict records (last_wins / UNKNOWN) for
    # its merged roster; decision logic never reads them.
    for line in open(args.train_jsonl):
        s = json.loads(line)
        if s["id"] not in dev_ids:
            continue
        sid = s["id"]
        gold = s["label"]["tool_calls"]
        current_text = s.get("audio_text", "")
        # ---- history prefix (raw events + user texts) ----
        hist_events = []
        hist_user = []
        hist_roster_ops = []  # R4-CONFLICT: ordered roster ops,
        # ("read", grouped, unknown_map) or ("barrier",
        # barrier_entry), in history order, for the state API.
        hist_priors = []
        pos_counter = [0]

        def next_pos():
            p = pos_counter[0]
            pos_counter[0] += 1
            return p

        for h in s.get("history", []):
            if h.get("role") == "user":
                text = h.get("audio_text", "")
                hist_user.append(text)
                hist_events.append({"kind": "user_turn", "text": text,
                                    "position": next_pos()})
            elif h.get("role") == "assistant":
                calls = h.get("tool_calls") or []
                results = h.get("tool_results") or []
                for idx, call in enumerate(calls):
                    res = results[idx] if idx < len(results) else None
                    hist_events.append({
                        "tool": call.get("name"),
                        "args": call.get("arguments") or {},
                        "result": res, "outcome": outcome_of(res),
                        "position": next_pos(), "origin": "history"})
                    entries = []
                    if isinstance(res, dict):
                        try:
                            entries = flatten_result_entries(res)
                        except Exception:
                            entries = []
                    hist_priors.append(PriorCall(
                        call.get("name"), call.get("arguments") or {},
                        result_entries=entries,
                        succeeded=outcome_of(res) == "succeeded"))
                # Roster ops, in result order, with event info
                # so barriers can be detected (the old code
                # collected rosters from every result here,
                # regardless of tool; this keeps that coverage
                # and adds barrier detection for updates).
                for idx, res in enumerate(results):
                    call_name = None
                    call_args = {}
                    if idx < len(calls):
                        call_name = calls[idx].get("name")
                        call_args = calls[idx].get("arguments") or {}
                    if call_name == "contacts.update" \
                            and outcome_of(res) == "succeeded":
                        barrier = _barrier_entry_from_update(
                            call_args, res)
                        if barrier is not None:
                            hist_roster_ops.append(
                                ("barrier", barrier))
                        continue
                    entries = _entries_from_result(res)
                    if entries:
                        grouped, unknown_map = \
                            _group_read_entries(entries)
                        hist_roster_ops.append(
                            ("read", grouped, unknown_map))
        # ---- full-trajectory replay ----
        env = ToolEnv("train", sid, root=args.data_root)
        replay_events = []   # (idx, raw event)
        replay_priors = []   # (idx, PriorCall)
        replay_roster_ops = []  # (idx, roster op) -- read or barrier
        for idx, call in enumerate(gold):
            try:
                res = env.call(call.get("name"),
                               call.get("arguments") or {})
            except Exception:
                res = None
            replay_events.append((idx, {
                "tool": call.get("name"),
                "args": call.get("arguments") or {},
                "result": res, "outcome": outcome_of(res),
                "position": -1, "origin": "session"}))
            entries = []
            if isinstance(res, dict):
                try:
                    entries = flatten_result_entries(res)
                except Exception:
                    entries = []
            replay_priors.append((idx, PriorCall(
                call.get("name"), call.get("arguments") or {},
                result_entries=entries,
                succeeded=outcome_of(res) == "succeeded")))
            if call.get("name") == "contacts.search" \
                    and isinstance(res, dict) and res.get("ok"):
                # Same whitelist as collect_rosters (history
                # path): id/name/phone + string relation
                # only. Without relation here, a session
                # contacts.search would still starve D1
                # exactly like the history path did. The
                # res.get("ok") guard above already keeps
                # failed reads out of this path.
                entries = []
                for entry in res.get("contacts") or []:
                    roster_entry = _harness_roster_entry(entry)
                    if roster_entry is not None:
                        entries.append(roster_entry)
                if entries:
                    grouped, unknown_map = \
                        _group_read_entries(entries)
                    replay_roster_ops.append(
                        (idx, ("read", grouped, unknown_map)))
            elif call.get("name") == "contacts.update" \
                    and outcome_of(res) == "succeeded":
                barrier = _barrier_entry_from_update(
                    call.get("arguments") or {}, res)
                if barrier is not None:
                    replay_roster_ops.append(
                        (idx, ("barrier", barrier)))
        # ---- evaluate every gold write ----
        for pos, call in enumerate(gold):
            name = call.get("name", "")
            if is_read(name, kinds) or name == "sys.ask_missing_info":
                continue
            # Merged roster for this position: history roster
            # ops in order, then replay roster ops before
            # pos in order, merged by the unified state
            # rule (last-wins, barriers, UNKNOWN) -- so a
            # session search that supplies a relation the
            # history search lacked fills it here as well,
            # and a session update that confirms a field
            # bars stale history values for that field.
            # A fresh state per position: merging must not
            # mutate history / replay ops across pos.
            roster_state = _new_roster_state()
            seq = 0
            for op in hist_roster_ops:
                if op[0] == "barrier":
                    _apply_barrier_to_state(
                        roster_state, op[1], seq)
                else:
                    _merge_group_into_state(
                        roster_state, op[1], op[2], seq)
                seq += 1
            for p, op in replay_roster_ops:
                if p < pos:
                    if op[0] == "barrier":
                        _apply_barrier_to_state(
                            roster_state, op[1], seq)
                    else:
                        _merge_group_into_state(
                            roster_state, op[1], op[2], seq)
                    seq += 1
            rosters = roster_state["entries"]
            if roster_state["conflicts"]:
                roster_conflict_rows.append(
                    {"sample": sid, "pos": pos,
                     "conflicts": roster_state["conflicts"]})
            priors = list(hist_priors) + [pc for p, pc in replay_priors
                                          if p < pos]
            # Raw prefix: history events (positions as assigned)
            # + replay events before pos (positions continue after
            # history so ledger order == prefix order).
            session_prefix = []
            next_session_pos = pos_counter[0]
            for p, ev in replay_events:
                if p < pos:
                    clone = dict(ev, position=next_session_pos)
                    next_session_pos += 1
                    session_prefix.append(clone)
            prefix = list(hist_events) + session_prefix
            proposal_position = next_session_pos
            try:
                base = gate_read_before_write(call, priors, rosters, kinds)
            except Exception as exc:  # never silently skip a write
                errors.append({"sample": sid, "pos": pos, "call": call,
                               "stage": "baseline", "error": repr(exc)})
                continue
            try:
                cand = decide(call, prefix, rosters, current_text, kinds,
                              proposal_position=proposal_position)
            except Exception as exc:
                errors.append({"sample": sid, "pos": pos, "call": call,
                               "stage": "candidate", "error": repr(exc)})
                continue
            grp = group_of(call)
            row = {"sample": sid, "pos": pos, "call": call,
                   "group": grp, "baseline_fired": base.fired,
                   "baseline_applicable": base.applicable,
                   "baseline_reason": base.reason,
                   "candidate_fired": cand.fired,
                   "candidate_applicable": cand.applicable,
                   "adjustments": cand.adjustments,
                   "notes": cand.notes}
            if sid == "train_1696":
                anomaly_rows.append(row)
            if base.fired or cand.fired:
                fired_rows.append(row)
            if base.applicable:
                stats["baseline_applicable"] += 1
                by_group[grp]["baseline_applicable"] += 1
                if base.fired:
                    stats["baseline_fired"] += 1
                    by_group[grp]["baseline_fired"] += 1
            if cand.applicable:
                stats["candidate_applicable"] += 1
                by_group[grp]["candidate_applicable"] += 1
                if cand.fired:
                    stats["candidate_fired"] += 1
                    by_group[grp]["candidate_fired"] += 1
            # Synthetic control: same write, no evidence at all.
            try:
                synth = decide(call, [], [], "", kinds,
                               proposal_position=0)
                if base.applicable:
                    if synth.fired:
                        stats["synthetic_TP"] += 1
                    else:
                        stats["synthetic_FN"] += 1
                        changes.append({**row, "synthetic_vacuous_pass": True})
            except Exception as exc:
                errors.append({"sample": sid, "pos": pos, "call": call,
                               "stage": "synthetic", "error": repr(exc)})
            if base.applicable and cand.applicable \
                    and base.fired != cand.fired:
                changes.append(row)
            elif base.applicable != cand.applicable:
                changes.append({**row, "applicability_changed": True})

    def rate(fired, applicable):
        return fired / applicable if applicable else 0.0

    summary = {
        "baseline": {
            "applicable": stats["baseline_applicable"],
            "fired": stats["baseline_fired"],
            "false_block_rate": rate(stats["baseline_fired"],
                                     stats["baseline_applicable"])},
        "candidate": {
            "applicable": stats["candidate_applicable"],
            "fired": stats["candidate_fired"],
            "false_block_rate": rate(stats["candidate_fired"],
                                     stats["candidate_applicable"])},
        "by_group": {g: {
            "baseline_applicable": c["baseline_applicable"],
            "baseline_fired": c["baseline_fired"],
            "candidate_applicable": c["candidate_applicable"],
            "candidate_fired": c["candidate_fired"],
            "baseline_rate": rate(c["baseline_fired"],
                                  c["baseline_applicable"]),
            "candidate_rate": rate(c["candidate_fired"],
                                   c["candidate_applicable"])}
            for g, c in sorted(by_group.items())},
        "synthetic": {"TP": stats["synthetic_TP"],
                      "FN": stats["synthetic_FN"]},
        "n_decision_changes": len(
            [r for r in changes if "synthetic_vacuous_pass" not in r
             and "applicability_changed" not in r]),
        "n_errors": len(errors),
        "anomaly_1696_rows": len(anomaly_rows),
    }
    out = {"summary": summary, "changes": changes,
           "anomaly_1696": anomaly_rows, "errors": errors,
           "fired_rows": fired_rows,
           "roster_conflicts": roster_conflict_rows}
    json.dump(out, open(args.out_json, "w"), ensure_ascii=False, indent=1)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print("decision changes: %d (see %s)" % (summary["n_decision_changes"],
                                             args.out_json))


if __name__ == "__main__":
    main()
