#!/usr/bin/env python3
"""Generate the inner split for the overnight capability audit.

Protocol (Thread C): split dev once, before any tuning, seed 1337,
70/15/15 stratified by gold kind, with history-presence and
read-before-write rates within +/-2pp of population rates per part.
Amendment (main synthesis): the 4 quarantined samples from Thread A
(train_1696, train_1005, train_1033, train_1319) are removed BEFORE
splitting, so the effective population is 1233, not 1237. The
near-duplicate normalized-request group (train_0061, train_0066,
train_0168) goes whole to inner_train.

Stratification cells: gold kind (normal/empty/ask_only/ask_after)
x history-presence x read-before-write class. Allocation per cell
uses largest-remainder to the global targets, shuffled with
seed 1337. Output is a manifest JSON with sample->part mapping plus
generator command, stratum counts, and overlap-check report.

Inputs: train.jsonl + split map (dev filter first; held-out rows are
never read into the split). No model, no GPU, no network.
"""
import json
import random
import sys
from collections import Counter, defaultdict

SEED = 1337
QUARANTINE = {"train_1696", "train_1005", "train_1033", "train_1319"}
NEAR_DUP_GROUP = ["train_0061", "train_0066", "train_0168"]
DATA_ROOT = "/home/hatch/workspace/zaic-data/lifemate/extracted/train+public_test"
REPO = "/home/hatch/workspace/zalo-aic-round3"


def gold_kind(calls):
    names = [c.get("name", "") for c in calls]
    if not calls:
        return "empty"
    if names == ["sys.ask_missing_info"]:
        return "ask_only"
    if "sys.ask_missing_info" in names:
        return "ask_after"
    return "normal"


def main():
    split = json.load(open(f"{REPO}/lifemate/splits/train_dev_heldout.json"))
    dev_ids = {k for k, v in split.items() if v == "dev"}
    catalog = json.load(open(f"{DATA_ROOT}/train/train_tools_catalog.json"))
    kind_by_tool = {}
    for app in catalog["apps"]:
        for t in app["tools"]:
            kind_by_tool[t["name"]] = t.get("kind", "")
    rows = {}
    for line in open(f"{DATA_ROOT}/train/train.jsonl"):
        s = json.loads(line)
        if s["id"] not in dev_ids:
            continue  # held-out dropped before any analysis
        rows[s["id"]] = s
    assert len(rows) == 1237, len(rows)
    qkinds = {}
    for q in QUARANTINE:
        qkinds[q] = gold_kind(rows[q]["label"]["tool_calls"])
    eligible = {k: v for k, v in rows.items() if k not in QUARANTINE}
    assert len(eligible) == 1233, len(eligible)

    def cell_of(s):
        calls = s["label"]["tool_calls"]
        kind = gold_kind(calls)
        hist = bool(s.get("history"))
        # read-before-write class in gold order
        seen_read = False
        rbw = "no_write"
        for c in calls:
            k = kind_by_tool.get(c.get("name", ""), "")
            if k == "read":
                seen_read = True
            elif k == "write":
                rbw = "write_after_read" if seen_read else "write_without_prior_read"
                break
        return (kind, hist, rbw)

    cells = defaultdict(list)
    for sid, s in eligible.items():
        if sid in NEAR_DUP_GROUP:
            continue
        cells[cell_of(s)].append(sid)
    # Targets for the 1230 unforced samples (train target 863 total,
    # 3 forced to train -> 860 remaining; val 185; test 185).
    targets = {"inner_train": 860, "inner_val": 185, "inner_test": 185}
    assert sum(targets.values()) == 1230
    rng = random.Random(SEED)
    assign = {sid: "inner_train" for sid in NEAR_DUP_GROUP}
    # Per-cell largest-remainder allocation (exact per cell), then
    # balance global part totals to targets by moving samples
    # between parts WITHIN the same cell (stratum composition of
    # each cell is preserved; part rates shift by at most a few
    # samples and are re-verified against +/-2pp below).
    alloc = {}
    for cell, members in cells.items():
        n = len(members)
        raw = {p: n * t / 1230 for p, t in targets.items()}
        base = {p: int(raw[p]) for p in targets}
        short = n - sum(base.values())
        order = sorted(targets, key=lambda p: raw[p] - base[p], reverse=True)
        for p in order[:short]:
            base[p] += 1
        alloc[cell] = base
    totals = Counter()
    for cell, base in alloc.items():
        for p, v in base.items():
            totals[p] += v
    while any(totals[p] != targets[p] for p in targets):
        over = [p for p in targets if totals[p] > targets[p]][0]
        under = [p for p in targets if totals[p] < targets[p]][0]
        moved = False
        for cell in sorted(alloc):
            if alloc[cell][over] > 0:
                alloc[cell][over] -= 1
                alloc[cell][under] += 1
                totals[over] -= 1
                totals[under] += 1
                moved = True
                break
        assert moved, "no cell to rebalance"
    for cell, members in cells.items():
        members = sorted(members)
        rng.shuffle(members)
        idx = 0
        for part in ("inner_train", "inner_val", "inner_test"):
            take = alloc[cell][part]
            for sid in members[idx:idx + take]:
                assign[sid] = part
            idx += take
        assert idx == len(members), (cell, idx, len(members))
    assert len(assign) == 1233
    assert Counter(assign.values()) == {"inner_train": 863, "inner_val": 185, "inner_test": 185}

    def rates(part_ids):
        n = len(part_ids)
        kinds = Counter(gold_kind(rows[s]["label"]["tool_calls"]) for s in part_ids)
        hist = sum(1 for s in part_ids if rows[s].get("history")) / n
        rbw = Counter(cell_of(rows[s])[2] for s in part_ids)
        return {
            "n": n,
            "kind_rates": {k: round(v / n, 4) for k, v in sorted(kinds.items())},
            "history_rate": round(hist, 4),
            "rbw_rates": {k: round(v / n, 4) for k, v in sorted(rbw.items())},
        }

    pop_ids = sorted(eligible)
    pop = rates(pop_ids)
    parts = {p: rates(sorted(s for s, q in assign.items() if q == p))
             for p in ("inner_train", "inner_val", "inner_test")}
    # +/-2pp checks on history + rbw rates.
    checks = {}
    for p, r in parts.items():
        checks[p] = {
            "history_within_2pp": abs(r["history_rate"] - pop["history_rate"]) <= 0.02,
            "rbw_within_2pp": all(
                abs(r["rbw_rates"].get(k, 0) - pop["rbw_rates"].get(k, 0)) <= 0.02
                for k in pop["rbw_rates"]),
        }
    # Overlap checks: partition disjointness + audio-path disjointness.
    all_ids = sorted(assign)
    audio = {}
    for sid in all_ids:
        audio.setdefault(rows[sid].get("audio"), []).append(sid)
    audio_shared = {a: v for a, v in audio.items()
                    if len({assign[s] for s in v}) > 1}
    manifest = {
        "generator": "analysis/overnight_capability_audit/generate_inner_split.py",
        "seed": SEED,
        "population": "dev 1237 minus Thread A quarantine 4 = 1233",
        "quarantine_removed_before_split": {q: qkinds[q] for q in sorted(QUARANTINE)},
        "near_duplicate_group_whole_to_train": NEAR_DUP_GROUP,
        "counts": dict(Counter(assign.values())),
        "population_rates": pop,
        "part_rates": parts,
        "rate_checks_within_2pp": checks,
        "overlap_checks": {
            "partition_disjoint": len(all_ids) == len(set(all_ids)) == 1233,
            "audio_paths_shared_across_parts": audio_shared,
            "heldout_ids_present": sorted(set(assign) - dev_ids),
            "quarantine_ids_present": sorted(set(assign) & QUARANTINE),
        },
        "assignment": dict(sorted(assign.items())),
    }
    out = f"{REPO}/analysis/overnight_capability_audit/inner_split_seed1337.json"
    with open(out, "w") as f:
        json.dump(manifest, f, indent=1, sort_keys=False)
    print(json.dumps({k: manifest[k] for k in (
        "counts", "population_rates", "part_rates",
        "rate_checks_within_2pp", "overlap_checks") if k != "overlap_checks"},
        indent=1))
    print("overlap:", {k: (v if not isinstance(v, dict) or not v else v)
                       for k, v in manifest["overlap_checks"].items()})
    ok = all(all(c.values()) for c in checks.values()) \
        and manifest["overlap_checks"]["partition_disjoint"] \
        and not manifest["overlap_checks"]["audio_paths_shared_across_parts"] \
        and not manifest["overlap_checks"]["heldout_ids_present"] \
        and not manifest["overlap_checks"]["quarantine_ids_present"]
    print("ALL_CHECKS_PASS:", ok)
    if not ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
