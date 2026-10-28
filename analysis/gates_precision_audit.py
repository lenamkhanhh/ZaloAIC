#!/usr/bin/env python3
"""Round 10: per-gate precision audit on the dev split.

Each gate is audited on gold trajectories (should-pass) PLUS synthetic
counterfactuals built from real gold situations (should-fire):
  * Gate 1 (contact ambiguity): gold contact writes vs the same writes
    evaluated against a roster doctored to duplicate the write's contact.
  * Gate 2 (read-before-write): gold entity-referencing writes with full
    session evidence vs the same writes evaluated with the evidence
    removed (empty prior calls/observations/rosters).
  * Gate 3 literal (transfer confirmation): gold transfers checked for
    confirmation markers. Because gold transfers ARE correct executions,
    a fire here is a gold contradiction, not a false positive in the
    usual sense: the literal form is dropped if it fires on > 5% of gold
    transfers (the analogue of the 95% precision rule, stated openly).
  * Gate 3 scoped (confirmation only when owed): gold applicable
    transfers (prior ask in history, or details not instructed in the
    current request) vs the same transfers evaluated with post-ask
    confirmation removed.

Precision = TP / (TP + FP) with a Wilson 95% interval. Verdict: KEEP iff
precision >= 95% (user rule), else DROP. Counts are reported per gate so
a small-n gate cannot hide behind a percentage.

SANCTIONED ACCESS ONLY: every environment observation comes from
``zaic_tools.ToolEnv(...).call(...)`` -- the official runtime path, here
replaying the FULL gold trajectory (reads AND writes, in order) so read
results reflect the agent's actual session state for this turn. This
script NEVER opens train_environment/ or state.json directly. Phones are
dropped (only id/name are kept from rosters).

Usage:
  python3 analysis/gates_precision_audit.py \
      --train-jsonl <train.jsonl> --data-root <dir containing train/> \
      --split lifemate/splits/train_dev_heldout.json \
      [--out-json /tmp/gates_audit.json]
"""

import argparse
import collections
import json
import math
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lifemate"))
from lifemate_gates import (  # noqa: E402
    gate_contact_ambiguity, gate_read_before_write, gate_confirmation,
    gate_confirmation_scoped)
from lifemate_provenance import find_number_spans, nfc_lower  # noqa: E402

READ_VERBS = ("search", "list", "get", "status", "forecast", "balance",
              "history", "detail")


def is_read(name):
    verb = (name or "").split(".", 1)[1] if "." in (name or "") else ""
    return any(verb == v or verb.startswith(v + "_") for v in READ_VERBS)


def flatten_scalars(obj, out):
    if isinstance(obj, dict):
        for key, value in obj.items():
            if key == "phone":
                continue
            flatten_scalars(value, out)
    elif isinstance(obj, list):
        for value in obj:
            flatten_scalars(value, out)
    elif isinstance(obj, (str, int, float)) and not isinstance(obj, bool):
        out.append(obj)


def collect_rosters(results, out):
    if isinstance(results, dict):
        contacts = results.get("contacts")
        if isinstance(contacts, list):
            for entry in contacts:
                if isinstance(entry, dict) and entry.get("id"):
                    out.append({"id": entry["id"],
                                "name": entry.get("name", "")})
        for key, value in results.items():
            if key != "phone":
                collect_rosters(value, out)
    elif isinstance(results, list):
        for value in results:
            collect_rosters(value, out)


def wilson(tp, fp):
    n = tp + fp
    if n == 0:
        return (0.0, 0.0)
    p = tp / n
    z = 1.96
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def instructed_in_current(call_args, current_text, rosters):
    """Proxy for 'the transfer was fully instructed in this request':
    the amount appears as a number span in the current text AND the
    recipient is named in the current text (via the roster name for the
    write's contact_id, or a name argument)."""
    amount = call_args.get("amount")
    if amount is None:
        return False
    amount_ok = any(float(v) == float(amount)
                    for _, v in find_number_spans(current_text or ""))
    if not amount_ok:
        return False
    cid = call_args.get("contact_id")
    name = None
    for entry in rosters or []:
        if entry.get("id") == cid:
            name = entry.get("name")
    hay = nfc_lower(current_text or "")
    if name and nfc_lower(name) in hay:
        return True
    if call_args.get("contact_name") \
            and nfc_lower(call_args["contact_name"]) in hay:
        return True
    return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--train-jsonl", required=True)
    ap.add_argument("--data-root", required=True)
    ap.add_argument("--split", required=True)
    ap.add_argument("--out-json", default="/tmp/gates_audit.json")
    args = ap.parse_args()

    split = json.load(open(args.split))
    dev_ids = {k for k, v in split.items() if v == "dev"}
    train_dir = str(Path(args.train_jsonl).resolve().parent)
    sys.path.insert(0, train_dir)
    from zaic_tools import ToolEnv  # noqa: E402

    stats = {
        "g1": collections.Counter(),
        "g2": collections.Counter(),
        "g3_literal": collections.Counter(),
        "g3_scoped": collections.Counter(),
    }
    for line in open(args.train_jsonl):
        s = json.loads(line)
        if s["id"] not in dev_ids:
            continue
        gold = s["label"]["tool_calls"]
        current_text = s.get("audio_text", "")
        # History evidence.
        hist_user = []
        hist_calls = []
        hist_obs = []
        hist_rosters = []
        hist_ask_positions = []  # indices into hist_user after each ask
        for h in s.get("history", []):
            if h.get("role") == "user":
                hist_user.append(h.get("audio_text", ""))
            elif h.get("role") == "assistant":
                calls = h.get("tool_calls") or []
                results = h.get("tool_results") or []
                for call in calls:
                    hist_calls.append((call.get("name"),
                                       call.get("arguments") or {}))
                    if call.get("name") == "sys.ask_missing_info":
                        hist_ask_positions.append(len(hist_user))
                for res in results:
                    flatten_scalars(res, hist_obs)
                    collect_rosters(res, hist_rosters)
        # Full-trajectory replay (reads AND writes, in gold order).
        env = ToolEnv("train", s["id"], root=args.data_root)
        replay_obs = []       # (position, scalars)
        replay_rosters = []   # (position, entry)
        for idx, call in enumerate(gold):
            try:
                res = env.call(call.get("name"),
                               call.get("arguments") or {})
            except Exception:
                continue
            if call.get("name") == "contacts.search" \
                    and isinstance(res, dict) and res.get("ok"):
                for entry in res.get("contacts") or []:
                    if isinstance(entry, dict) and entry.get("id"):
                        replay_rosters.append(
                            (idx, {"id": entry["id"],
                                   "name": entry.get("name", "")}))
            flat = []
            flatten_scalars(res, flat)
            replay_obs.append((idx, flat))
        # Evaluate every gold write.
        for pos, call in enumerate(gold):
            name = call.get("name", "")
            if is_read(name) or name == "sys.ask_missing_info":
                continue
            call_args = call.get("arguments") or {}
            rosters = list(hist_rosters) + [e for p, e in replay_rosters
                                            if p < pos]
            prior_calls = list(hist_calls) + [
                (c.get("name"), c.get("arguments") or {})
                for c in gold[:pos]]
            prior_obs = list(hist_obs) + [
                v for p, flat in replay_obs if p < pos for v in flat]
            # ---- Gate 1
            g1 = gate_contact_ambiguity(call, rosters)
            if g1.applicable:
                stats["g1"]["gold_applicable"] += 1
                if g1.fired:
                    stats["g1"]["gold_fired_FP"] += 1
                # Synthetic: doctor the roster to duplicate the contact.
                ref_id = call_args.get("contact_id")
                ref_name = None
                for entry in rosters:
                    if entry.get("id") == ref_id:
                        ref_name = entry.get("name")
                if ref_name and not any(
                        len({e.get("id") for e in rosters
                             if nfc_lower(e.get("name")) ==
                             nfc_lower(ref_name)}) >= 2 for _ in [0]):
                    dup = list(rosters) + [{"id": "c__synthetic_dup",
                                            "name": ref_name}]
                    g1s = gate_contact_ambiguity(call, dup)
                    if g1s.fired:
                        stats["g1"]["synthetic_TP"] += 1
                    else:
                        stats["g1"]["synthetic_FN"] += 1
            # ---- Gate 2
            g2 = gate_read_before_write(call, prior_calls, prior_obs,
                                        rosters)
            if g2.applicable:
                stats["g2"]["gold_applicable"] += 1
                if g2.fired:
                    stats["g2"]["gold_fired_FP"] += 1
                # Synthetic: same write, evidence removed.
                g2s = gate_read_before_write(call, [], [], [])
                if g2s.fired:
                    stats["g2"]["synthetic_TP"] += 1
                else:
                    stats["g2"]["synthetic_FN"] += 1
            # ---- Gate 3 (transfers only)
            if name in ("banking.transfer", "ewallet.transfer"):
                texts = hist_user + [current_text]
                g3 = gate_confirmation(call, texts)
                stats["g3_literal"]["gold_transfers"] += 1
                if g3.fired:
                    stats["g3_literal"]["gold_fired"] += 1
                else:
                    stats["g3_literal"]["gold_passed"] += 1
                # Scoped variant.
                had_prior_ask = bool(hist_ask_positions)
                if had_prior_ask:
                    post_ask = hist_user[hist_ask_positions[-1]:] \
                        + [current_text]
                else:
                    post_ask = []
                instructed = instructed_in_current(call_args, current_text,
                                                   rosters)
                g3s = gate_confirmation_scoped(call, post_ask,
                                               had_prior_ask, instructed)
                if g3s.applicable:
                    stats["g3_scoped"]["gold_applicable"] += 1
                    if g3s.fired:
                        stats["g3_scoped"]["gold_fired_FP"] += 1
                    # Synthetic: applicable transfer, confirmation removed.
                    g3syn = gate_confirmation_scoped(call, [], True, False)
                    if g3syn.fired:
                        stats["g3_scoped"]["synthetic_TP"] += 1
                    else:
                        stats["g3_scoped"]["synthetic_FN"] += 1

    def precision_report(key):
        tp = stats[key]["synthetic_TP"]
        fp = stats[key]["gold_fired_FP"]
        lo, hi = wilson(tp, fp)
        prec = tp / (tp + fp) if (tp + fp) else 0.0
        return {
            "gold_applicable": stats[key]["gold_applicable"],
            "gold_fired_FP": fp,
            "synthetic_TP": tp,
            "synthetic_FN": stats[key]["synthetic_FN"],
            "precision": prec,
            "wilson95": [lo, hi],
            "verdict": "KEEP" if prec >= 0.95 else "DROP",
        }

    g1 = precision_report("g1")
    g2 = precision_report("g2")
    g3s = precision_report("g3_scoped")
    lit_total = stats["g3_literal"]["gold_transfers"]
    lit_fired = stats["g3_literal"]["gold_fired"]
    lit_rate = lit_fired / lit_total if lit_total else 0.0
    summary = {
        "gate1_contact_ambiguity": g1,
        "gate2_read_before_write": g2,
        "gate3_literal": {
            "gold_transfers": lit_total,
            "gold_fired": lit_fired,
            "gold_passed": stats["g3_literal"]["gold_passed"],
            "gold_fire_rate": lit_rate,
            "verdict": "DROP" if lit_rate > 0.05 else "KEEP",
            "verdict_rule": "DROP iff gold fire rate > 5%: a hard gate "
                            "that vetoes gold-correct transfers contradicts "
                            "the gold behaviour it should protect.",
        },
        "gate3_scoped": g3s,
    }
    json.dump(summary, open(args.out_json, "w"), ensure_ascii=False)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
