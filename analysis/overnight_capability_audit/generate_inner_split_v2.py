#!/usr/bin/env python3
"""Generate inner split v2 for the overnight capability audit (Thread A).

Changes vs v1 (inner_split_seed1337.json, FROZEN - never overwritten):
- Population is the FULL dev set (1237), not dev-minus-quarantine.
  v1 removed train_1696/1005/1033/1319 before splitting; v2 returns
  all four to the evaluation pool. Membership (split assignment) is
  therefore SEPARATED from training eligibility (see below).
- Same seed (1337), same 70/15/15 proportions, same cell-stratified
  method (kind x history-presence x read-before-write class, per-cell
  largest remainder + within-cell rebalance, near-duplicate group
  whole to train). Targets for 1237: train 866 / val 185 / test 186
  (Thread C's original 1237 sizes); after forcing the 3-sample
  near-duplicate group to train, remaining targets are
  train 863 / val 185 / test 186.
- Per-sample flags: kind, history, rbw class, near-duplicate group,
  anomaly (train_1696 only), contact_source (first-source class of
  the sample's gold contact_id calls: roster / message_history /
  other / mixed / none).
- Training eligibility is a SEPARATE per-sample flag. Only
  train_1696 is train_eligible=False, for a mechanical, logged
  reason: its gold trajectory contains a call that fails replay
  (chat_ott.send_message chat_6142 -> ok True, done False), so it
  cannot pass a D1 all-succeed construction filter. train_1005 /
  train_1033 / train_1319 are train_eligible=True: their contact_ids
  are traceable to structured history results that ARE rendered into
  the training prompt (history results repr), and the runtime prompt
  itself permits ids "from previous tool results in this
  conversation". The residual tension (current G2 counts only
  roster/contacts-app evidence, so a hard-enforced G2 would veto
  these trajectories) is flagged for the coordinator, not hidden,
  and does not change eligibility while G2 is shadow-only.

Inputs: train.jsonl + split map (dev filter first; held-out rows are
never read into the split). No model, no GPU, no network. No git.
Output: inner_split_seed1337_v2.json (this file's sibling). Content
checks (audio content hash, tool-sequence overlap, template groups)
and the v1->v2 diff are computed by a_v2_checks.py, not here, so
that the manifest and its verification are independent.
"""
import ast
import json
import random
import sys
from collections import Counter, defaultdict

SEED = 1337
NEAR_DUP_GROUP = ["train_0061", "train_0066", "train_0168"]
ANOMALY_ID = "train_1696"
DATA_ROOT = "/home/hatch/workspace/zaic-data/lifemate/extracted/train+public_test"
REPO = "/home/hatch/workspace/zalo-aic-round3"
MSG_TOOLS = ("sms.read_recent", "phone.recent_calls")


def gold_kind(calls):
    names = [c.get("name", "") for c in calls]
    if not calls:
        return "empty"
    if names == ["sys.ask_missing_info"]:
        return "ask_only"
    if "sys.ask_missing_info" in names:
        return "ask_after"
    return "normal"


def parse_results(r):
    if isinstance(r, list):
        return r
    if isinstance(r, str):
        try:
            v = ast.literal_eval(r)
            return v if isinstance(v, list) else [v]
        except Exception:
            return []
    if isinstance(r, dict):
        return [r]
    return []


def strings_in(obj, acc):
    if isinstance(obj, str):
        acc.add(obj)
    elif isinstance(obj, dict):
        for v in obj.values():
            strings_in(v, acc)
    elif isinstance(obj, list):
        for v in obj:
            strings_in(v, acc)


def search_ids(tool, res):
    ids = set()
    if tool == "contacts.search" and isinstance(res, dict):
        for e in res.get("contacts") or []:
            if isinstance(e, dict) and e.get("id"):
                ids.add(e["id"])
    return ids


def contact_source_flag(sample):
    """First-source class of the sample's gold contact_id calls."""
    roster = set()
    msg_strings = set()
    other_strings = set()
    prior_arg = set()

    def feed(tool, res, arg):
        if res is not None:
            strs = set()
            strings_in(res, strs)
            if tool in MSG_TOOLS:
                msg_strings.update(strs)
            else:
                other_strings.update(strs)
            roster.update(search_ids(tool, res))
        if arg:
            prior_arg.add(arg)

    for h in sample.get("history", []):
        if h.get("role") != "assistant":
            continue
        calls = h.get("tool_calls") or []
        results = parse_results(h.get("tool_results"))
        for i, c in enumerate(calls):
            r = results[i] if i < len(results) else None
            feed(c.get("name"), r, (c.get("arguments") or {}).get("contact_id"))
    gold_calls = sample["label"]["tool_calls"]
    gold_res = sample["label"].get("tool_results") or []
    cats = []
    for i, c in enumerate(gold_calls):
        cid = (c.get("arguments") or {}).get("contact_id")
        r = gold_res[i] if i < len(gold_res) else None
        if cid:
            if cid in roster:
                cats.append("roster")
            elif cid in msg_strings:
                cats.append("message_history")
            elif cid in other_strings:
                cats.append("other")
            elif cid in prior_arg:
                cats.append("prior_arg")
            else:
                cats.append("nowhere")
        feed(c.get("name"), r, cid)
    if not cats:
        return "none"
    if len(set(cats)) == 1:
        return cats[0]
    return "mixed"


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

    def cell_of(s):
        calls = s["label"]["tool_calls"]
        kind = gold_kind(calls)
        hist = bool(s.get("history"))
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

    flags = {}
    for sid, s in rows.items():
        calls = s["label"]["tool_calls"]
        kind, hist, rbw = cell_of(s)
        flags[sid] = {
            "kind": kind,
            "history": hist,
            "rbw": rbw,
            "near_dup_group": sid in NEAR_DUP_GROUP,
            "anomaly": sid == ANOMALY_ID,
            "contact_source": contact_source_flag(s),
        }
    train_eligible = {}
    reasons = {
        ANOMALY_ID: (
            "Gold trajectory contains a failing call: "
            "chat_ott.send_message chat_6142 -> ok True, done False "
            "('khong tim thay chat_id'); chat_6142 is not in the "
            "preceding list_chats result. The trajectory therefore "
            "cannot pass a D1 all-succeed construction filter. "
            "Kept in evaluation with anomaly flag; its metric must "
            "be reported separately (state hash cannot distinguish "
            "reproducing the failing call from skipping it)."
        ),
    }
    for sid in rows:
        train_eligible[sid] = sid not in reasons

    cells = defaultdict(list)
    for sid in rows:
        if sid in NEAR_DUP_GROUP:
            continue
        cells[cell_of(rows[sid])].append(sid)
    # Targets for the 1234 unforced samples (train target 866 total,
    # 3 forced to train -> 863 remaining; val 185; test 186).
    targets = {"inner_train": 863, "inner_val": 185, "inner_test": 186}
    assert sum(targets.values()) == 1234
    rng = random.Random(SEED)
    assign = {sid: "inner_train" for sid in NEAR_DUP_GROUP}
    alloc = {}
    for cell, members in cells.items():
        n = len(members)
        raw = {p: n * t / 1234 for p, t in targets.items()}
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
    assert len(assign) == 1237
    assert Counter(assign.values()) == {"inner_train": 866, "inner_val": 185, "inner_test": 186}

    def rates(part_ids):
        n = len(part_ids)
        kinds = Counter(flags[s]["kind"] for s in part_ids)
        hist = sum(1 for s in part_ids if flags[s]["history"]) / n
        rbw = Counter(flags[s]["rbw"] for s in part_ids)
        return {
            "n": n,
            "kind_rates": {k: round(v / n, 4) for k, v in sorted(kinds.items())},
            "history_rate": round(hist, 4),
            "rbw_rates": {k: round(v / n, 4) for k, v in sorted(rbw.items())},
        }

    pop = rates(sorted(rows))
    parts = {p: rates(sorted(s for s, q in assign.items() if q == p))
             for p in ("inner_train", "inner_val", "inner_test")}
    checks = {}
    for p, r in parts.items():
        checks[p] = {
            "kind_within_2pp": all(
                abs(r["kind_rates"].get(k, 0) - pop["kind_rates"].get(k, 0)) <= 0.02
                for k in pop["kind_rates"]),
            "history_within_2pp": abs(r["history_rate"] - pop["history_rate"]) <= 0.02,
            "rbw_within_2pp": all(
                abs(r["rbw_rates"].get(k, 0) - pop["rbw_rates"].get(k, 0)) <= 0.02
                for k in pop["rbw_rates"]),
        }
    manifest = {
        "generator": "analysis/overnight_capability_audit/generate_inner_split_v2.py",
        "version": "v2",
        "seed": SEED,
        "base": "v1 inner_split_seed1337.json (FROZEN reference; v1 population was dev-minus-quarantine = 1233)",
        "population": "full dev 1237 (quarantine returned to evaluation pool)",
        "near_duplicate_group_whole_to_train": NEAR_DUP_GROUP,
        "counts": dict(Counter(assign.values())),
        "train_eligible_counts": dict(Counter(
            "eligible" if v else "excluded" for v in train_eligible.values())),
        "train_eligible_reasons": reasons,
        "population_rates": pop,
        "part_rates": parts,
        "rate_checks_within_2pp": checks,
        "overlap_checks": {
            "partition_disjoint": len(assign) == len(set(assign)) == 1237,
            "heldout_ids_present": sorted(set(assign) - dev_ids),
            "note": "Audio content-hash, tool-sequence overlap, and template-group checks are computed independently by a_v2_checks.py (see split_v2_diff.md); this generator does not claim them.",
        },
        "assignment": dict(sorted(assign.items())),
        "flags": {sid: flags[sid] for sid in sorted(flags)},
        "train_eligible": {sid: train_eligible[sid] for sid in sorted(train_eligible)},
    }
    out = f"{REPO}/analysis/overnight_capability_audit/inner_split_seed1337_v2.json"
    with open(out, "w") as f:
        json.dump(manifest, f, indent=1, sort_keys=False)
    print(json.dumps({k: manifest[k] for k in (
        "counts", "train_eligible_counts", "part_rates",
        "rate_checks_within_2pp")}, indent=1))
    print("flags contact_source:", Counter(f["contact_source"] for f in flags.values()))
    print("flags anomaly:", [s for s, f in flags.items() if f["anomaly"]])
    ok = all(all(c.values()) for c in checks.values()) \
        and manifest["overlap_checks"]["partition_disjoint"] \
        and not manifest["overlap_checks"]["heldout_ids_present"]
    print("ALL_CHECKS_PASS:", ok)
    if not ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
