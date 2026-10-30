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
merged by id with backfill for missing fields only (see
_backfill_roster_entry -- the same rule as the runtime
observer): a later successful read fills a field the first
successful read lacked, never overwrites a non-empty value,
never overwrites with an empty value, and a failed read
neither creates nor backfills an entry.
Roster entries carry only id/name/phone plus a non-empty
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


def _harness_roster_entry(entry):
    """One roster entry, on the harness whitelist only.

    D1 (lifemate_callback_negation.py) matches a descriptor
    against every roster field other than id/name/phone, so
    forwarding every string field would let an arbitrary
    string (a note, a company, a free-text field) qualify a
    duplicate as if it were structured evidence. The harness
    therefore forwards exactly one structured attribute
    beyond id/name/phone: ``relation``, and only when it is
    a non-empty string. Any other field is dropped, and a
    non-string ``relation`` (a number, a list, ...) is
    dropped rather than coerced. Returns None when the
    entry has no id.
    """
    if not isinstance(entry, dict) or not entry.get("id"):
        return None
    roster_entry = {"id": entry["id"],
                    "name": entry.get("name", ""),
                    "phone": entry.get("phone", "")}
    relation = entry.get("relation")
    if isinstance(relation, str) and relation.strip():
        roster_entry["relation"] = relation
    return roster_entry


def _backfill_roster_entry(existing, new):
    """Fill ONLY fields that are missing in ``existing`` from ``new``.

    This is the SAME rule as the runtime observer's
    ``lifemate_observer._backfill_roster_entry`` (the two
    modules cannot import each other, so the rule is stated
    in full in both places and must stay identical):

    - Keyed by contact id only; ``id`` itself is never changed.
    - A field is "missing" when it is absent, None, or "".
    - A missing field is filled ONLY from a non-empty string
      value in the later entry. A later empty/missing value
      never overwrites anything (converse case: a later
      incomplete read cannot erase a relation the first read
      supplied).
    - A field that already holds a non-empty value is NEVER
      overwritten, even by a different non-empty value: on a
      non-empty conflict the FIRST successful value is kept,
      not silently replaced. This follows the lifecycle
      patch/state rule that a state which does not match is
      not attached to a different entity: a later read that
      disagrees with the first successful read does not get
      to rewrite the first read's evidence.
    - Only whitelisted fields ever reach this function
      (``_harness_roster_entry`` drops every other field
      first), so backfill can never promote a stray string
      into structured evidence.
    - Order is preserved: backfilling an existing entry does
      not move it.
    """
    for key, value in new.items():
        if key == "id":
            continue
        old = existing.get(key)
        if old is None or old == "":
            if isinstance(value, str) and value.strip():
                existing[key] = value
        # else: old is non-empty -- keep first, whatever the
        # later value is (equal, empty, or conflicting).


def _merge_roster_entry(out, roster_entry):
    """Append ``roster_entry`` to ``out`` or backfill its
    existing entry for the same id, per _backfill_roster_entry."""
    for existing in out:
        if existing["id"] == roster_entry["id"]:
            _backfill_roster_entry(existing, roster_entry)
            return
    out.append(roster_entry)


def collect_rosters(results, out):
    """Collect roster entries from ``results`` into ``out``,
    merging by id with backfill for missing fields only
    (see _backfill_roster_entry). A failed read (explicit
    ok=False) contributes nothing: it neither creates nor
    backfills an entry."""
    if isinstance(results, dict):
        # A failed read is not roster evidence: an explicit
        # ok=False result contributes nothing, even if its
        # payload still carries a contacts list. (A result
        # with no ok field at all keeps the old behaviour;
        # only an explicit failure is excluded, so result
        # shapes without an ok field do not lose rosters.)
        if results.get("ok") is False:
            return
        contacts = results.get("contacts")
        if isinstance(contacts, list):
            for entry in contacts:
                roster_entry = _harness_roster_entry(entry)
                if roster_entry is not None:
                    _merge_roster_entry(out, roster_entry)
        for key, value in results.items():
            if key != "phone":
                collect_rosters(value, out)
    elif isinstance(results, list):
        for value in results:
            collect_rosters(value, out)


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
        hist_rosters = []
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
                for res in results:
                    collect_rosters(res, hist_rosters)
        # ---- full-trajectory replay ----
        env = ToolEnv("train", sid, root=args.data_root)
        replay_events = []   # (idx, raw event)
        replay_priors = []   # (idx, PriorCall)
        replay_rosters = []  # (idx, roster entry)
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
                for entry in res.get("contacts") or []:
                    roster_entry = _harness_roster_entry(entry)
                    if roster_entry is not None:
                        replay_rosters.append((idx, roster_entry))
        # ---- evaluate every gold write ----
        for pos, call in enumerate(gold):
            name = call.get("name", "")
            if is_read(name, kinds) or name == "sys.ask_missing_info":
                continue
            # Merged roster for this position: history rosters
            # (already merged by collect_rosters) plus replay
            # rosters before pos, merged by id with backfill
            # for missing fields only -- the same rule as the
            # observer, applied to the replay path too, so a
            # session search that supplies a relation the
            # history search lacked backfills it here as well.
            # Fresh dict copies per position: merging must not
            # mutate hist_rosters / replay_rosters across pos.
            rosters = [dict(e) for e in hist_rosters]
            for p, e in replay_rosters:
                if p < pos:
                    _merge_roster_entry(rosters, dict(e))
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
           "fired_rows": fired_rows}
    json.dump(out, open(args.out_json, "w"), ensure_ascii=False, indent=1)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print("decision changes: %d (see %s)" % (summary["n_decision_changes"],
                                             args.out_json))


if __name__ == "__main__":
    main()
