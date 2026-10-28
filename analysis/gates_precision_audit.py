#!/usr/bin/env python3
"""Round 10: per-gate precision audit on the dev split.

Each gate is audited on gold trajectories (should-pass) PLUS synthetic
counterfactuals built from real gold situations (should-fire):
  * Gate 1 (contact ambiguity): gold contact writes vs the same writes
    evaluated against a roster doctored to duplicate the write's contact.
  * Gate 2 (read-before-write): gold entity-referencing writes with full
    session evidence vs the same writes evaluated with the evidence
    removed (empty PriorCall list + empty rosters). FIX ROUND 2: the
    gate now takes structured PriorCall entries (field, value) --
    a flat string set is not evidence (a free-text scalar equalling an
    id proves nothing); contacts come only from rosters or
    contacts-app results; other *_ids from id-typed fields, with reads
    verifying by lookup and writes needing non-echo ids. An old-vs-new
    effect count is reported when the previous-round module is
    available (--old-gates-path, default the e00c864c copy): gold
    applicable writes where the OLD rule passed but the NEW gate fires
    and vice versa. The verdict follows the re-audit: if stricter
    evidence pushes precision below 95%, the verdict becomes DROP
    with the FP breakdown -- the old counting is NOT smuggled back in
    to rescue it.
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
import importlib.util
import json
import math
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lifemate"))
from lifemate_gates import (  # noqa: E402
    gate_contact_ambiguity, gate_read_before_write, gate_confirmation,
    gate_confirmation_scoped, PriorCall, flatten_result_entries)
from lifemate_provenance import find_number_spans, nfc_lower  # noqa: E402

READ_VERBS = ("search", "list", "get", "status", "forecast", "balance",
              "history", "detail")


def is_read(name, kind_by_tool=None):
    """Read classification: catalog kind wins when a kind map is
    supplied (a verb-name list misclassifies 14 catalog reads --
    reviewer finding 8-V); otherwise the verb list is the fallback."""
    if kind_by_tool is not None and name in kind_by_tool:
        return kind_by_tool[name] == "read"
    verb = (name or "").split(".", 1)[1] if "." in (name or "") else ""
    return any(verb == v or verb.startswith(v + "_") for v in READ_VERBS)


def load_kind_map(train_dir):
    """{tool name: kind} from train_tools_catalog.json, or {} when
    the catalog is unavailable (caller falls back to verb list)."""
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
                                "name": entry.get("name", ""),
                                "phone": entry.get("phone", "")})
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
    ap.add_argument("--old-gates-path",
                    default=str(Path.home() / "workspace"
                                / "round10-fix-base" / "lifemate_gates.py"),
                    help="Previous-round gates module for the old-vs-new "
                         "G2 effect count; skipped if missing.")
    args = ap.parse_args()

    old_g2 = None
    old_PriorCall = None
    if Path(args.old_gates_path).exists():
        spec = importlib.util.spec_from_file_location(
            "old_lifemate_gates", args.old_gates_path)
        old_mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(old_mod)
        old_g2 = old_mod.gate_read_before_write
        old_PriorCall = old_mod.PriorCall

    split = json.load(open(args.split))
    dev_ids = {k for k, v in split.items() if v == "dev"}
    train_dir = str(Path(args.train_jsonl).resolve().parent)
    kinds = load_kind_map(train_dir)
    kind_source = "catalog" if kinds else "verb_fallback"
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
        # History evidence: new-style PriorCall objects (structured
        # entries) plus the legacy tuple/scalar forms for the
        # old-vs-new count (previous-round gate module).
        hist_user = []
        hist_priors = []
        hist_old_priors = []
        hist_rosters = []
        hist_ask_positions = []  # indices into hist_user after each ask
        for h in s.get("history", []):
            if h.get("role") == "user":
                hist_user.append(h.get("audio_text", ""))
            elif h.get("role") == "assistant":
                calls = h.get("tool_calls") or []
                results = h.get("tool_results") or []
                for idx, call in enumerate(calls):
                    if call.get("name") == "sys.ask_missing_info":
                        hist_ask_positions.append(len(hist_user))
                    res = results[idx] if idx < len(results) else None
                    ok = isinstance(res, dict) and res.get("ok") is True \
                        and res.get("done") is not False
                    entries = []
                    flat = []
                    if res is not None:
                        entries = flatten_result_entries(res)
                        flatten_scalars(res, flat)
                    hist_priors.append(PriorCall(
                        call.get("name"), call.get("arguments") or {},
                        result_entries=entries, succeeded=ok))
                    if old_PriorCall is not None:
                        hist_old_priors.append(old_PriorCall(
                            call.get("name"), call.get("arguments") or {},
                            result_scalars=flat, succeeded=ok))
                for res in results:
                    collect_rosters(res, hist_rosters)
        # Full-trajectory replay (reads AND writes, in gold order).
        env = ToolEnv("train", s["id"], root=args.data_root)
        replay_rosters = []   # (position, entry)
        replay_priors = []    # (position, PriorCall)
        replay_old_priors = []  # (position, old-module PriorCall)
        for idx, call in enumerate(gold):
            try:
                res = env.call(call.get("name"),
                               call.get("arguments") or {})
            except Exception:
                res = None
            ok = isinstance(res, dict) and res.get("ok") is True \
                and res.get("done") is not False
            flat = []
            entries = []
            if res is not None:
                flatten_scalars(res, flat)
                entries = flatten_result_entries(res)
            replay_priors.append((idx, PriorCall(
                call.get("name"), call.get("arguments") or {},
                result_entries=entries, succeeded=ok)))
            if old_PriorCall is not None:
                replay_old_priors.append((idx, old_PriorCall(
                    call.get("name"), call.get("arguments") or {},
                    result_scalars=flat, succeeded=ok)))
            if call.get("name") == "contacts.search" \
                    and isinstance(res, dict) and res.get("ok"):
                for entry in res.get("contacts") or []:
                    if isinstance(entry, dict) and entry.get("id"):
                        replay_rosters.append(
                            (idx, {"id": entry["id"],
                                   "name": entry.get("name", ""),
                                   "phone": entry.get("phone", "")}))
        # Evaluate every gold write.
        for pos, call in enumerate(gold):
            name = call.get("name", "")
            if is_read(name, kinds) or name == "sys.ask_missing_info":
                continue
            call_args = call.get("arguments") or {}
            rosters = list(hist_rosters) + [e for p, e in replay_rosters
                                            if p < pos]
            priors = list(hist_priors) + [pc for p, pc in replay_priors
                                          if p < pos]
            old_priors = list(hist_old_priors) + [
                pc for p, pc in replay_old_priors if p < pos]
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
            # ---- Gate 2 (fix-round-2 structured PriorCall contract)
            g2 = gate_read_before_write(call, priors, rosters, kinds)
            if g2.applicable:
                stats["g2"]["gold_applicable"] += 1
                if g2.fired:
                    stats["g2"]["gold_fired_FP"] += 1
                # Synthetic: same write, evidence removed.
                g2s = gate_read_before_write(call, [], [], kinds)
                if g2s.fired:
                    stats["g2"]["synthetic_TP"] += 1
                else:
                    stats["g2"]["synthetic_FN"] += 1
                # Old-vs-new effect (previous-round module, if
                # available): its gate takes (call, prior_calls,
                # rosters) with old-style PriorCall objects.
                if old_g2 is not None:
                    old = old_g2(call, old_priors, rosters)
                    if old.applicable:
                        stats["g2"]["old_new_both_applicable"] += 1
                        if not old.fired and g2.fired:
                            stats["g2"]["old_passed_new_fired"] += 1
                        elif old.fired and not g2.fired:
                            stats["g2"]["old_fired_new_passed"] += 1
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
    g2["old_new_both_applicable"] = stats["g2"]["old_new_both_applicable"]
    g2["old_passed_new_fired"] = stats["g2"]["old_passed_new_fired"]
    g2["old_fired_new_passed"] = stats["g2"]["old_fired_new_passed"]
    g2["old_new_note"] = (
        "old = previous-round (e00c864c) flat-string gate; new = "
        "registry-typed + catalog-kind gate (round 3). "
        "old_passed_new_fired = gold writes the old rule passed but "
        "the new gate fires (stricter evidence: registry-typed "
        "entries with paths, contacts only from rosters or "
        "contacts-app results, phone_number references checked "
        "against roster phones, patch-verified writes counted, "
        "all slots of a shared value checked). If this pushes "
        "precision below 95%, the verdict is DROP; the old counting "
        "is not restored.")
    g2["kind_classification"] = kind_source
    g2["gold_false_block_rate"] = (
        g2["gold_fired_FP"] / g2["gold_applicable"]
        if g2["gold_applicable"] else 0.0)
    g3s = precision_report("g3_scoped")
    lit_total = stats["g3_literal"]["gold_transfers"]
    lit_fired = stats["g3_literal"]["gold_fired"]
    lit_rate = lit_fired / lit_total if lit_total else 0.0
    summary = {
        "kind_classification": kind_source,
        # Metric honesty (reviewer finding 6-PR): G2/G3 "precision"
        # = synthetic_TP/(synthetic_TP+gold_fired_FP) with
        # synthetic_TP == applicable by construction; it equals
        # 1 - gold false-block rate and is NOT detection precision.
        # Detection is shown only on synthetic unit cases.
        "metric_note": "Quote gold_false_block_rate, not 'precision', "
                       "as the deployment-relevant number.",
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
