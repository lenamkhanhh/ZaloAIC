"""SCORE phase for four-arm (reads traces from disk first, then gold).

This module NEVER runs the agent and NEVER feeds a trace back into
an agent. It is the only place gold is read: gold tool calls (via
lifemate/loader + lifemate/scoring, the library scorer -- not a
reimplementation), gold current transcript (for WER/slot only), and
label class (for grouping). Scores here are official-style via
lifemate/scoring.py, NOT the organiser evaluator (see scoring.py
docstring for the UNVERIFIED points: ask scoring, read-in-F1).

Error taxonomy (per sample, computed from scored trace + gold;
flags are heuristics for triage, not proof -- fabricated_* in
particular needs human review when it fires):
  slot_heard_wrong: a digit slot in the gold current transcript is
    not intact in the arm transcript.
  wrong_tool: submitted tool-name multiset differs from gold, or a
    submitted name is absent from gold.
  wrong_param: a submitted call shares a gold call's name but its
    arguments differ (supplementary; scorer's calls_match is the
    authoritative match).
  fabricated_id_time_money: a submitted string argument value that
    (a) matches an id/time/money-like pattern or is a contact_id,
    (b) is not exactly in any gold call, (c) is not in the arm
    transcript, and (d) is not in any observation text in the trace.
    Values that came from a read observation are therefore NOT
    flagged; values invented with no observation source are.
  skipped_read: gold has a contacts.search before a non-search,
    non-ask call, and the submitted sequence has that later call
    with no preceding contacts.search.
  extra_call: submitted multiset count exceeds gold for some name,
    or len(submitted) > len(gold) with no gold counterpart.
  early_stop: termination kind == "stop" AND score < 1.0 AND
    len(submitted) < len(gold).
  late_time: trace seconds > 30.0 (the A30 per-sample limit in
    RUN_LIFEMATE.md §3; in a mock report this flag is plumbing only
    because mock seconds are synthetic).

Report: per arm -- total mean_score, hash_rate, mean_f1, n, mean /
p95 seconds, WER (mean, only where a gold transcript exists),
slot_error_rate -- plus the same means broken down by label group
(empty / ask_only / ask_after / normal), plus per-flag counts and
rates, plus paired differences for ALL SIX arm pairs on the SAME
samples (bootstrap CI, 10,000 resamples, seed 20261030), plus a
dev-reweighted mean (by label-group proportions in the full dev
split, computed in the score phase from the split file + label
classes -- never from held-out ids).

Gating: if --off-on-report is supplied and its "identical" field is
not true, scoring REFUSES (exit 3) and writes no report. A mock
report is labelled "MOCK ONLY" in its top-level "result_kind" and
must never be quoted as a model score.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from metrics import bootstrap_paired_ci, slot_error, wer  # noqa: E402

ARMS = ("A", "B", "C", "D")
PAIRS = [("A", "B"), ("A", "C"), ("A", "D"),
         ("B", "C"), ("B", "D"), ("C", "D")]
_DIGIT_RE = re.compile(r"[0-9]+")
_TIME_RE = re.compile(r"^\d{1,2}:\d{2}(:\d{2})?$")
_MONEY_KEYS = ("amount", "money", "price", "total")


def _multiset(calls):
    return Counter(c["name"] for c in calls)


def _arg_values(call):
    args = call.get("arguments") or {}
    return [(k, v) for k, v in args.items() if isinstance(v, str)]


def _looks_id_time_money(key, value):
    if key == "contact_id":
        return True
    if key in _MONEY_KEYS and _DIGIT_RE.search(value):
        return True
    if _TIME_RE.match(value.strip()):
        return True
    return False


def error_flags(trace, gold_calls, gold_transcript):
    submitted = trace.get("tool_calls") or []
    flags = {}
    # slot_heard_wrong (score phase only: needs gold transcript)
    slot = slot_error(gold_transcript, trace.get("transcript_current"))
    flags["slot_heard_wrong"] = bool(
        slot["n_slots"] and slot["n_correct"] < slot["n_slots"])
    gold_names = _multiset(gold_calls)
    sub_names = _multiset(submitted)
    flags["wrong_tool"] = (sub_names != gold_names or
                           any(n not in gold_names for n in sub_names))
    # wrong_param: same name present, args differ from every gold
    # call with that name.
    wrong_param = False
    for s in submitted:
        same = [g for g in gold_calls if g["name"] == s["name"]]
        if same and all((s.get("arguments") or {}) != (g.get("arguments") or {})
                        for g in same):
            wrong_param = True
    flags["wrong_param"] = wrong_param
    # fabricated candidate: value with no source in gold, transcript,
    # or any observation text.
    gold_values = set()
    for g in gold_calls:
        for _, v in _arg_values(g):
            gold_values.add(v)
    obs_text = " ".join(
        (gen.get("observation_following") or "")
        for gen in trace.get("generations") or [])
    transcript = trace.get("transcript_current") or ""
    fabricated = False
    for s in submitted:
        for key, value in _arg_values(s):
            if not _looks_id_time_money(key, value):
                continue
            if value in gold_values or value in transcript or value in obs_text:
                continue
            fabricated = True
    flags["fabricated_id_time_money"] = fabricated
    # skipped_read: gold read-before-write, submitted write w/o read.
    gold_read_idx = next(
        (i for i, g in enumerate(gold_calls) if g["name"] == "contacts.search"),
        None)
    skipped = False
    if gold_read_idx is not None:
        gold_later = [g["name"] for g in gold_calls[gold_read_idx + 1:]
                      if g["name"] not in ("contacts.search", "sys.ask_missing_info")]
        sub_read_idx = next(
            (i for i, s in enumerate(submitted) if s["name"] == "contacts.search"),
            None)
        for name in gold_later:
            if sub_read_idx is None:
                if any(s["name"] == name for s in submitted):
                    skipped = True
            else:
                if any(s["name"] == name
                       for s in submitted[sub_read_idx + 1:]) is False \
                        and any(s["name"] == name for s in submitted):
                    # The write exists but only before the read.
                    skipped = True
    flags["skipped_read"] = skipped
    flags["extra_call"] = any(sub_names[n] > gold_names.get(n, 0)
                              for n in sub_names)
    term = (trace.get("termination") or {}).get("kind")
    flags["early_stop"] = bool(
        term == "stop" and len(submitted) < len(gold_calls))
    flags["late_time"] = bool(
        trace.get("seconds") is not None and trace["seconds"] > 30.0)
    return flags


def _mean(xs):
    return sum(xs) / len(xs) if xs else 0.0


def _p95(xs):
    if not xs:
        return None
    s = sorted(xs)
    return s[min(len(s) - 1, int(0.95 * len(s)))]


def score_traces(traces_by_arm, gold_by_id, result_kind):
    """traces_by_arm: {arm: [trace]}; gold_by_id: {id: {gold_calls,
    label_class, gold_transcript, score, hash_correct, f1}}.
    Scores must already be computed by the caller with the library
    scorer (score_sample) or, for mock, from the mock fixture. This
    function only aggregates, groups, and pairs -- it does not invent
    scores."""
    paired_ids = sorted(set.intersection(
        *(set(t["sample_id"] for t in traces) for traces in traces_by_arm.values()))
    ) if traces_by_arm else []
    if not paired_ids:
        raise SystemExit("no sample ids present in every arm; cannot pair")
    per_arm = {}
    scored = {}  # (arm, id) -> scored record
    for arm in ARMS:
        if arm not in traces_by_arm:
            raise SystemExit(f"arm {arm} traces missing; report needs all 4 arms")
        recs = []
        for trace in traces_by_arm[arm]:
            sid = trace["sample_id"]
            if sid not in paired_ids:
                continue
            g = gold_by_id[sid]
            flags = error_flags(trace, g["gold_calls"], g.get("gold_transcript"))
            # early_stop needs the score; score<1 is checked by caller
            # via g["score"] per arm, so refine here:
            flags["early_stop"] = bool(
                (trace.get("termination") or {}).get("kind") == "stop"
                and g["score_by_arm"][arm] < 1.0
                and len(trace.get("tool_calls") or []) < len(g["gold_calls"]))
            w = wer(g.get("gold_transcript"), trace.get("transcript_current")) \
                if g.get("gold_transcript") else None
            slot = slot_error(g.get("gold_transcript"),
                              trace.get("transcript_current"))
            rec = {"sample_id": sid, "label_class": g["label_class"],
                   "score": g["score_by_arm"][arm],
                   "hash_correct": g["hash_by_arm"][arm],
                   "f1": g["f1_by_arm"][arm],
                   "seconds": trace.get("seconds"),
                   "wer": w["wer"] if w else None,
                   "slot_error_rate": slot["slot_error_rate"],
                   "flags": flags,
                   "termination": (trace.get("termination") or {}).get("kind")}
            recs.append(rec)
            scored[(arm, sid)] = rec
        by_group = {}
        for grp in sorted(set(r["label_class"] for r in recs)):
            rs = [r for r in recs if r["label_class"] == grp]
            by_group[grp] = {"n": len(rs),
                             "mean_score": _mean([r["score"] for r in rs])}
        flag_names = list(recs[0]["flags"]) if recs else []
        flag_summary = {
            name: {"n": sum(1 for r in recs if r["flags"][name]),
                   "rate": _mean([1.0 if r["flags"][name] else 0.0 for r in recs])}
            for name in flag_names}
        wers = [r["wer"] for r in recs if r["wer"] is not None]
        slots = [r["slot_error_rate"] for r in recs
                 if r["slot_error_rate"] is not None]
        per_arm[arm] = {
            "n": len(recs),
            "mean_score": _mean([r["score"] for r in recs]),
            "hash_rate": _mean([1.0 if r["hash_correct"] else 0.0 for r in recs]),
            "mean_f1": _mean([r["f1"] for r in recs]),
            "mean_seconds": _mean([r["seconds"] for r in recs
                                   if r["seconds"] is not None]),
            "p95_seconds": _p95([r["seconds"] for r in recs
                                 if r["seconds"] is not None]),
            "mean_wer": _mean(wers) if wers else None,
            "mean_slot_error_rate": _mean(slots) if slots else None,
            "by_label_group": by_group,
            "error_flags": flag_summary,
        }
    paired = {}
    for a, b in PAIRS:
        sa = [scored[(a, sid)]["score"] for sid in paired_ids]
        sb = [scored[(b, sid)]["score"] for sid in paired_ids]
        paired[f"{a}_minus_{b}"] = bootstrap_paired_ci(sa, sb)
    return {"result_kind": result_kind, "n_paired": len(paired_ids),
            "paired_ids": paired_ids, "per_arm": per_arm,
            "paired_differences": paired}


def cmd_score(args):
    traces_dir = Path(args.traces)
    if args.off_on_report:
        rep = json.loads(Path(args.off_on_report).read_text(encoding="utf-8"))
        if not rep.get("identical"):
            print("BLOCKED: G&G OFF/ON report is not identical; "
                  "refusing to score. Differences: "
                  f"{rep.get('differences')}", file=sys.stderr)
            return 3
    traces_by_arm = {}
    for arm in ARMS:
        path = traces_dir / f"traces_{arm}.jsonl"
        if not path.exists():
            print(f"missing traces for arm {arm}: {path}", file=sys.stderr)
            return 2
        traces_by_arm[arm] = [json.loads(l) for l in path.read_text(
            encoding="utf-8").splitlines() if l.strip()]
    result_kind = "mock_only" if args.mock else "official_style_dev"
    # Failed-record exclusion (P2 rule, explicit not silent):
    # traces with run_error set keep their position in the trace
    # file but are excluded from paired scoring, with the count
    # reported. They are never scored as 0 and never shift order.
    failed = {}
    for arm in ARMS:
        bad = [t["sample_id"] for t in traces_by_arm[arm]
               if t.get("run_error")]
        failed[arm] = bad
        traces_by_arm[arm] = [t for t in traces_by_arm[arm]
                              if not t.get("run_error")]
    gold_by_id = {}
    if args.mock:
        fixture = json.loads(Path(args.mock_fixture).read_text(encoding="utf-8"))
        # Mock fixture scores are plumbing, not library scores: the
        # mock gold calls are synthetic, so score with the same
        # rule as lifemate/scoring (hash gate + tool F1) implemented
        # in-line here ONLY because mock traces carry no real
        # state_hash semantics -- the real path below uses the
        # library scorer and never this branch.
        for sid, g in fixture.items():
            score_by_arm, hash_by_arm, f1_by_arm = {}, {}, {}
            for arm in ARMS:
                sub = next(t for t in traces_by_arm[arm]
                           if t["sample_id"] == sid)
                # Mock hash gate = executed calls exactly equal gold
                # calls (mock traces hash str(executed), not a real
                # env state hash); stated here so it is never mistaken
                # for a real state_hash comparison.
                h = (sub["tool_calls"] == g["gold_calls"])
                f1 = _mock_f1(sub["tool_calls"], g["gold_calls"])
                score_by_arm[arm] = f1 if h else 0.0
                hash_by_arm[arm] = h
                f1_by_arm[arm] = f1
            gold_by_id[sid] = {"gold_calls": g["gold_calls"],
                               "label_class": g["label_class"],
                               "gold_transcript": g["gold_transcript"],
                               "score_by_arm": score_by_arm,
                               "hash_by_arm": hash_by_arm,
                               "f1_by_arm": f1_by_arm}
    else:
        # Real path: library scorer, gold read only now.
        source_tree = Path(args.source_tree)
        sys.path.insert(0, str(source_tree))
        from lifemate.loader import (catalog_tools_for_sample,  # noqa: E402
                                     fuzzy_params, load_catalog, load_split)
        from lifemate.scoring import score_sample  # noqa: E402
        from lifemate.adapter import ZaicEnv  # noqa: E402
        root = Path(args.data)
        catalog = load_catalog(root, "train")
        fuzzy = fuzzy_params(catalog)
        samples = {s.id: s for s in load_split(root, "train")}

        def gold_hash(sample):
            env = ZaicEnv(root, "train", sample.id)
            for call in sample.label["tool_calls"]:
                env.call(call["name"], call["arguments"])
            return env.state_hash()

        for sid, sample in samples.items():
            if not any(t["sample_id"] == sid
                       for t in traces_by_arm["A"]):
                continue
            gh = gold_hash(sample)
            score_by_arm, hash_by_arm, f1_by_arm = {}, {}, {}
            for arm in ARMS:
                sub = next(t for t in traces_by_arm[arm]
                           if t["sample_id"] == sid)
                line = {"id": sid, "tool_calls": sub["tool_calls"],
                        "state_hash": sub["state_hash"]}
                r = score_sample(line, sample, gh, fuzzy)
                score_by_arm[arm] = r["score"]
                hash_by_arm[arm] = r["hash_correct"]
                f1_by_arm[arm] = r["f1"]
            gold_by_id[sid] = {
                "gold_calls": sample.label["tool_calls"],
                "label_class": sample.label_class(),
                "gold_transcript": sample.audio_text,
                "score_by_arm": score_by_arm,
                "hash_by_arm": hash_by_arm,
                "f1_by_arm": f1_by_arm}
    report = score_traces(traces_by_arm, gold_by_id, result_kind)
    report["excluded_failed_traces"] = failed
    # Dev-reweighted mean: weight each label group by its share of
    # the full dev split -- only meaningful for the real path; for
    # mock it is reported as null with a reason.
    if args.mock:
        report["dev_reweighted_mean_by_arm"] = None
        report["dev_reweighted_note"] = (
            "mock only: no dev reweighting; mock ids are synthetic")
    else:
        split = json.loads((Path(args.source_tree) /
                            "lifemate/splits/train_dev_heldout.json")
                           .read_text(encoding="utf-8"))
        # Label-group dev shares need label classes for all dev ids;
        # they are computed here, in the score phase, from train data.
        from lifemate.loader import load_split as _ls
        dev_samples = [s for s in _ls(Path(args.data), "train")
                       if split.get(s.id) == "dev"]
        dev_counts = Counter(s.label_class() for s in dev_samples)
        dev_total = sum(dev_counts.values())
        reweighted = {}
        for arm in ARMS:
            total = 0.0
            for grp, cnt in dev_counts.items():
                grp_mean = report["per_arm"][arm]["by_label_group"].get(
                    grp, {}).get("mean_score")
                if grp_mean is not None:
                    total += grp_mean * cnt / dev_total
            reweighted[arm] = total
        report["dev_reweighted_mean_by_arm"] = reweighted
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "score_report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


def _mock_f1(submitted, gold):
    if not gold and not submitted:
        return 1.0
    if not gold or not submitted:
        return 0.0
    used = set()
    matched = 0
    for s in submitted:
        for i, g in enumerate(gold):
            if i in used:
                continue
            if s == g:
                used.add(i)
                matched += 1
                break
    p = matched / len(submitted)
    r = matched / len(gold)
    return 2 * p * r / (p + r) if p + r else 0.0


def main(argv=None):
    parser = argparse.ArgumentParser(prog="score_fourarm")
    parser.add_argument("--traces", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--off-on-report", default=None)
    parser.add_argument("--mock", action="store_true")
    parser.add_argument("--mock-fixture", default=None)
    parser.add_argument("--source-tree", default=None)
    parser.add_argument("--data", default=None)
    args = parser.parse_args(argv)
    if args.mock and not args.mock_fixture:
        parser.error("--mock requires --mock-fixture")
    if not args.mock and (not args.source_tree or not args.data):
        parser.error("real score requires --source-tree and --data")
    return cmd_score(args)


if __name__ == "__main__":
    raise SystemExit(main())
