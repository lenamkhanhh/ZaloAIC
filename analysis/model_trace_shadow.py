#!/usr/bin/env python3
"""Shadow-run the prover + Gate 2 over saved E5 V13 model proposals.

Reads analysis/runtime/e5_v13_diagnostic_trace.json (40 trajectories:
20 dev samples x control/rule arms) plus the original train samples,
and evaluates every parsed write proposal WITHOUT executing anything
or modifying the trajectory.

KEY FACT ABOUT THIS TRACE (verified, not assumed): every one of the
20 samples has gold = a single sys.ask_missing_info call. These are
E5 ask-first diagnostic samples: the correct action is to ASK, so
every write proposal in the trace is gold-divergent IN ACTION, by
construction. There is therefore NO gold write value to compare a
proposed argument against -- prover "precision vs gold values" is
undefined here, and any script claiming it on this trace would be
wrong. What the shadow CAN judge, honestly:
  * guard decision per write proposal: BLOCKED (the guard would force
    ASK, matching gold) vs PASSED (the guard lets a should-ask write
    through -- a miss) vs OUT-OF-SCOPE (no monitored arg and Gate 2
    not applicable -- the flaw is a missing slot, which belongs to a
    grammar, not to this guard);
  * per monitored arg: PROVEN (each such arg is listed for individual
    judgment -- a PROVEN verdict on a should-ask sample is either a
    genuine derivation gold missed, or a false proof, and only the
    cited evidence decides which) vs UNPROVEN/AMBIGUOUS (the guard
    correctly refuses, consistent with gold's ask);
  * Gate 2 fired vs passed on the same blocked/passed split.
TARGET vs CONTROL in this trace is the E5 experiment grouping, NOT a
different gold standard (gold asks in both groups); the split is
reported descriptively only.

CAUSAL PREFIX (the evidence a guard would actually have at the
proposal's turn -- nothing else):
  * current text: the trace's model_current_transcript (what the model
    received, NOT the gold audio_text);
  * history user texts: the trace's history_asr values, in u-number
    order (what the model received, NOT gold history transcripts);
  * history tool records: the sample's ORIGINAL history assistant
    tool_calls/tool_results (the input the trajectory started from);
  * turn observations / turn priors / rosters: trace tool events
    strictly BEFORE the proposal's generation event in the same trace
    (reads become turn observations; every event becomes a PriorCall
    with its recorded result and succeeded flag);
  * NEVER: the current proposal, rejected proposals, future tool
    results, or gold/label values (gold is used ONLY to establish
    that the correct action is ASK, never fed into evidence).

DEFINITIONS (counted, not assumed -- Codex's 45-proposal figure is
NOT reused; the old "45 V13 proposals" was a different cut):
  * generation: a generation event (78);
  * no-call generation: parsed is null -- model stopped or answered
    in text (33);
  * parsed-call generation: parsed name present (45) = 29 write +
    7 read + 5 ask + 4 invalid (pseudo-call __invalid__);
  * write proposal: a parsed generation whose catalog kind is write
    (29); sys.ask_missing_info is ask, not write;
  * monitored call: a write proposal carrying >= 1 monitored arg
    (time/date/start/end/amount/contact_id) (16);
  * monitored argument: one monitored slot on one write proposal (19);
  * tool event: an executed call recorded in the trace (38).

ASR divergence is a contributing flag, compared NORMALIZED
(NFC-lowercase, punctuation/whitespace stripped): a comma or case
difference is not an ASR error.

Usage:
  python3 analysis/model_trace_shadow.py \
    --trace analysis/runtime/e5_v13_diagnostic_trace.json \
    --train-jsonl <train/train.jsonl> \
    --split lifemate/splits/train_dev_heldout.json \
    --out-json /tmp/model_trace_shadow.json
The trace file must already exist in the repo (it is part of branch
history); this script never writes trajectories.
"""

import argparse
import collections
import importlib.util
import json
import re
import sys
import unicodedata
from pathlib import Path

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parent.parent / "lifemate"))
from lifemate_provenance import Evidence, prove_argument  # noqa: E402
from lifemate_gates import gate_read_before_write, PriorCall  # noqa: E402

MONITORED = ("time", "date", "start", "end", "amount", "contact_id")


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def succeeded(result):
    return isinstance(result, dict) and result.get("ok") is True \
        and result.get("done") is not False


def flatten_entries(obj, out):
    """(field, value) pairs for scalar leaves of a result, phones
    dropped; field None for a bare scalar."""
    if isinstance(obj, dict):
        for key, value in obj.items():
            if key == "phone":
                continue
            if isinstance(value, (dict, list)):
                flatten_entries(value, out)
            elif isinstance(value, (str, int, float)) \
                    and not isinstance(value, bool):
                out.append((key, value))
    elif isinstance(obj, list):
        for value in obj:
            flatten_entries(value, out)
    elif isinstance(obj, (str, int, float)) and not isinstance(obj, bool):
        out.append((None, obj))


def u_number(key):
    m = re.search(r"_u(\d+)\.wav$", key or "")
    return int(m.group(1)) if m else 10 ** 9


def norm_text(text):
    nfkd = unicodedata.normalize("NFC", text or "").lower()
    kept = "".join(ch for ch in nfkd if ch.isalnum() or ch.isspace())
    return " ".join(kept.split())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--trace", required=True)
    ap.add_argument("--train-jsonl", required=True)
    ap.add_argument("--split", required=True)
    ap.add_argument("--out-json", default="/tmp/model_trace_shadow.json")
    args = ap.parse_args()

    e7 = load_module("e7_audit",
                     str(HERE.parent / "e7_dag_shadow_audit.py"))
    flatten_obs = e7.flatten_observations_with_field
    collect_events = e7.collect_events
    collect_rosters = e7.collect_rosters_from_results

    cat = json.load(open(str(Path(args.train_jsonl).resolve().parent
                           / "train_tools_catalog.json")))
    kinds = {}

    def walk(o):
        if isinstance(o, dict):
            if isinstance(o.get("name"), str) and "kind" in o:
                kinds[o["name"]] = o.get("kind")
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    walk(cat)

    def kind_of(name):
        if name == "sys.ask_missing_info":
            return "ask"
        if name == "__invalid__":
            return "invalid"
        return kinds.get(name, "unknown")

    split = json.load(open(args.split))
    dev_ids = {k for k, v in split.items() if v == "dev"}
    samples = {}
    for line in open(args.train_jsonl):
        s = json.loads(line)
        samples[s["id"]] = s

    trace = json.load(open(args.trace))
    traces = trace["traces"]
    # The mandate requires verifying every trace id is a dev sample.
    non_dev = sorted({t["id"] for t in traces} - dev_ids)
    assert not non_dev, "trace ids outside dev: %s" % non_dev
    # And that gold really is ask-only on this trace; otherwise the
    # blocked/passed framing below would be invalid.
    for t in traces:
        gold = samples[t["id"]]["label"]["tool_calls"]
        assert len(gold) == 1 and gold[0].get("name") == \
            "sys.ask_missing_info", (t["id"], gold)

    gen_counts = collections.Counter()
    rows = []
    for t in traces:
        sid, arm, group = t["id"], t["arm"], t["group"]
        s = samples[sid]
        gold_ask = s["label"]["tool_calls"][0]
        anchor = (s.get("context") or {}).get("current_time")
        hist_user_gold = [h.get("audio_text", "")
                          for h in s.get("history", [])
                          if h.get("role") == "user"]
        hist_asr = [v for _, v in sorted(
            (t.get("history_asr") or {}).items(),
            key=lambda kv: u_number(kv[0]))]
        asr_divergent = (
            norm_text(t.get("model_current_transcript")) !=
            norm_text(s.get("audio_text"))) or (
            [norm_text(x) for x in hist_asr] !=
            [norm_text(x) for x in hist_user_gold])
        hist_obs, hist_events, hist_rosters = [], [], []
        hist_call_args, hist_priors = [], []
        for h in s.get("history", []):
            if h.get("role") != "assistant":
                continue
            calls = h.get("tool_calls") or []
            results = h.get("tool_results") or []
            for idx, call in enumerate(calls):
                res = results[idx] if idx < len(results) else None
                hist_call_args.append((call.get("name"),
                                       call.get("arguments") or {},
                                       succeeded(res)))
                entries = []
                if res is not None:
                    flatten_entries(res, entries)
                hist_priors.append(PriorCall(
                    call.get("name"), call.get("arguments") or {},
                    result_entries=entries, succeeded=succeeded(res)))
            for call, res in zip(calls, results):
                flatten_obs(res, call.get("name"), hist_obs)
                collect_events(res, call.get("name"), hist_events)
                collect_rosters(res, hist_rosters)
        prefix_tool_events = []
        for ev_idx, ev in enumerate(t["trace"]):
            if ev.get("event") == "tool":
                prefix_tool_events.append(ev)
                continue
            if ev.get("event") != "generation":
                continue
            parsed = ev.get("parsed")
            if not parsed or not parsed.get("name"):
                gen_counts["no_call"] += 1
                continue
            name = parsed["name"]
            k = kind_of(name)
            gen_counts[k] += 1
            if k != "write":
                continue
            pargs = parsed.get("arguments") or {}
            executed = any(
                e.get("event") == "tool" and e.get("name") == name
                and (e.get("arguments") or {}) == pargs
                for e in t["trace"][ev_idx + 1:])
            turn_obs, turn_events, turn_priors = [], [], []
            turn_rosters = []
            for pev in prefix_tool_events:
                pname = pev.get("name")
                pres = pev.get("result")
                entries = []
                if pres is not None:
                    flatten_entries(pres, entries)
                turn_priors.append(PriorCall(
                    pname, pev.get("arguments") or {},
                    result_entries=entries, succeeded=succeeded(pres)))
                if kind_of(pname) == "read":
                    flatten_obs(pres, pname, turn_obs)
                    collect_events(pres, pname, turn_events)
                    if pname == "contacts.search" \
                            and isinstance(pres, dict) and pres.get("ok"):
                        for entry in pres.get("contacts") or []:
                            if isinstance(entry, dict) and entry.get("id"):
                                turn_rosters.append(
                                    {"id": entry["id"],
                                     "name": entry.get("name", "")})
            rosters = list(hist_rosters) + turn_rosters
            evidence = Evidence(
                current_text=t.get("model_current_transcript") or "",
                history_user_texts=hist_asr,
                turn_observations=turn_obs,
                history_observations=hist_obs,
                history_call_args=hist_call_args,
                rosters=rosters,
                observation_events=list(hist_events) + turn_events,
                prior_call_args=[(pc.tool, pc.args, pc.succeeded)
                                 for pc in turn_priors],
                anchor=anchor,
                defaults={})
            arg_rows = []
            for slot in MONITORED:
                if slot not in pargs:
                    continue
                value = pargs[slot]
                v = prove_argument(slot, value, name, evidence,
                                   call_args=pargs)
                # Gold has no write value: PROVEN args are listed for
                # individual judgment (genuine derivation vs false
                # proof); UNPROVEN/AMBIGUOUS is consistent with ask.
                arg_rows.append({
                    "slot": slot, "value": value,
                    "verdict": v.status, "rule": v.rule,
                    "detail": v.detail,
                    "judgment": "needs-judgment" if v.status == "PROVEN"
                    else "consistent-with-ask"})
            call = {"name": name, "arguments": pargs}
            g2 = gate_read_before_write(
                call, list(hist_priors) + turn_priors, rosters)
            blocked_by = []
            if g2.fired:
                blocked_by.append("g2")
            if any(a["verdict"] in ("UNPROVEN", "AMBIGUOUS")
                   for a in arg_rows):
                blocked_by.append("prover")
            if blocked_by:
                decision = "blocked"
            elif arg_rows or g2.applicable:
                decision = "passed"
            else:
                decision = "out-of-scope-guard"
            rows.append({
                "sample": sid, "arm": arm, "group": group,
                "generation_index": ev_idx,
                "call": call, "executed": executed,
                "gold_ask": gold_ask.get("arguments") or {},
                "monitored_args": arg_rows,
                "g2": {"fired": g2.fired, "applicable": g2.applicable,
                       "reason": g2.reason},
                "decision": decision, "blocked_by": blocked_by,
                "asr_divergent": asr_divergent})

    write_rows = rows
    monitored_args = [a for r in write_rows for a in r["monitored_args"]]
    proven_args = [a for a in monitored_args if a["verdict"] == "PROVEN"]
    decisions = collections.Counter(r["decision"] for r in write_rows)
    by_arm = {}
    for arm in ("control", "rule"):
        sub = [r for r in write_rows if r["arm"] == arm]
        by_arm[arm] = dict(collections.Counter(
            r["decision"] for r in sub))
    by_group = {}
    for group in ("TARGET", "CONTROL"):
        sub = [r for r in write_rows if r["group"] == group]
        by_group[group] = dict(collections.Counter(
            r["decision"] for r in sub))
    summary = {
        "trace_file": args.trace,
        "trajectories": len(traces),
        "samples": sorted({t["id"] for t in traces}),
        "all_sample_ids_in_dev": True,
        "gold_action_on_all_samples": "ask (single sys.ask_missing_info)",
        "generation_counts": dict(gen_counts),
        "generation_total": sum(gen_counts.values()),
        "write_proposals": len(write_rows),
        "monitored_calls": sum(1 for r in write_rows
                               if r["monitored_args"]),
        "monitored_args": len(monitored_args),
        "monitored_args_proven": len(proven_args),
        "monitored_args_unproven_or_ambiguous":
            len(monitored_args) - len(proven_args),
        "guard_decisions": dict(decisions),
        "guard_decisions_by_arm": by_arm,
        "guard_decisions_by_group": by_group,
        "g2_fired": sum(1 for r in write_rows if r["g2"]["fired"]),
        "g2_applicable": sum(1 for r in write_rows
                             if r["g2"]["applicable"]),
        "asr_divergent_proposals": sum(
            1 for r in write_rows if r["asr_divergent"]),
        "executed_proposals": sum(
            1 for r in write_rows if r["executed"]),
        "proven_args_need_individual_judgment": [
            {"sample": r["sample"], "arm": r["arm"], "tool": r["call"]["name"],
             "slot": a["slot"], "value": a["value"], "rule": a["rule"],
             "detail": a["detail"]}
            for r in write_rows for a in r["monitored_args"]
            if a["verdict"] == "PROVEN"],
    }
    out = {"summary": summary, "rows": rows}
    json.dump(out, open(args.out_json, "w"), ensure_ascii=False, indent=1)
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
