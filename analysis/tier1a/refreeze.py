"""Refreeze the Tier 1a benchmark set with stratification (LifeMate only).

This is the ONLY script in this package that reads gold tool calls
before any model run, and it does so only to stratify and to check
coverage — never to build agent input, history, or prompts. Its
output is an id list plus counts; no transcript, no gold call, and
no wav is written into the manifest. The manifest is then the only
thing the run phase sees (ids + order), and the score phase reads
gold only after run traces are on disk.

Algorithm (stream-C section 4.2, implemented exactly):
  1. Dev ids only, from lifemate/splits/train_dev_heldout.json.
     Held-out ids are never candidates; an id outside the split
     is never selected.
  2. Stratify by label class (empty / ask_only / ask_after / normal),
     computed from the label's tool-call names exactly as
     lifemate/loader.py Sample.label_class() does. Samples with no
     label are excluded as unlabelled (they cannot be stratified).
  3. Within each stratum, order by sha256(f"{benchmark_seed}:{id}")
     ascending, with benchmark_seed = 20261030 (different from the
     split seed 42, so selection order does not repeat split order).
  4. Allocate proportionally to dev stratum sizes, with a minimum
     of 20 per stratum (largest-remainder distribution of the
     remainder; a stratum smaller than the minimum takes all its
     dev samples and the shortfall is recorded, not hidden).
  5. Outcome-blind exclusion BEFORE any model output is seen:
     missing wav, missing current-turn gold transcript, or a
     history user wav that does not exist. Each excluded sample
     is replaced by the next sample in the same stratum's hash
     order, and every exclusion/replacement is logged in the manifest.
  6. Coverage top-up by swap (preserving n and stratum counts):
     at least 30 samples whose gold transcript contains a digit
     string, and at least 30 whose gold tool calls include
     contacts.search. If a feature is short, a selected sample
     without that feature is swapped for the next unselected
     sample in the same stratum that has it. If dev cannot supply
     the threshold, the shortfall is recorded in
     coverage_shortfall — the threshold is never lowered silently.
  7. Run order: the selected ids sorted by the global hash
     sha256(f"{benchmark_seed}:{id}") ascending. Pilot 20 = the
     first 20 ids of the manifest, in that order.
  8. Freeze: write the manifest JSON plus a sidecar .sha256 file
     (sha256 of the manifest file). The manifest's ids_sha256 is
     the sha256 of the JSON encoding of the id list, so the
     runner and the notebook can recompute it without the sidecar.

Stdlib only: this script parses train.jsonl directly and does not
import lifemate, so it runs on a CPU host without torch/vllm.

Usage:
  python3 refreeze.py --data <train+public_test root>
      --source-tree <repo root> --out <manifest path>
      [--n 200] [--min-per-stratum 20] [--benchmark-seed 20261030]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

EXPECTED_SPLIT_SHA = "eefd0faa163285b23d2634bc4cc04f515b58367a2344599e46e85d48818280aa"
DIGIT_RE = re.compile(r"[0-9]+")


def sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def label_class(label) -> str:
    if label is None:
        return "unlabelled"
    calls = label.get("tool_calls") or []
    if not calls:
        return "empty"
    names = [c.get("name") for c in calls]
    if names == ["sys.ask_missing_info"]:
        return "ask_only"
    if "sys.ask_missing_info" in names:
        return "ask_after"
    return "normal"


def hash_key(seed: int, sample_id: str) -> str:
    return hashlib.sha256(f"{seed}:{sample_id}".encode("utf-8")).hexdigest()


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="refreeze")
    p.add_argument("--data", required=True)
    p.add_argument("--source-tree", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--n", type=int, default=200)
    p.add_argument("--min-per-stratum", type=int, default=20)
    p.add_argument("--min-digit", type=int, default=30)
    p.add_argument("--min-contacts-search", type=int, default=30)
    p.add_argument("--benchmark-seed", type=int, default=20261030)
    args = p.parse_args(argv)

    source = Path(args.source_tree)
    data_root = Path(args.data)
    split_path = source / "lifemate/splits/train_dev_heldout.json"
    split_sha = sha256_file(split_path)
    if split_sha != EXPECTED_SPLIT_SHA:
        print(f"split SHA mismatch: {split_sha} != {EXPECTED_SPLIT_SHA}", file=sys.stderr)
        return 2
    split = json.loads(split_path.read_text(encoding="utf-8"))
    dev_ids = {k for k, v in split.items() if v == "dev"}
    held_ids = {k for k, v in split.items() if v == "heldout"}
    train_path = data_root / "train" / "train.jsonl"
    if not train_path.exists():
        print(f"BLOCKED: no train.jsonl under {data_root}", file=sys.stderr)
        return 2

    # Load dev samples only. Held-out ids are never loaded as candidates.
    by_id: dict[str, dict] = {}
    for line in train_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        raw = json.loads(line)
        if raw["id"] in dev_ids:
            by_id[raw["id"]] = raw
    missing_from_data = sorted(dev_ids - set(by_id))
    # Stratify.
    strata: dict[str, list[str]] = {}
    for sid, raw in by_id.items():
        cls = label_class(raw.get("label"))
        if cls == "unlabelled":
            continue
        strata.setdefault(cls, []).append(sid)
    for cls in strata:
        strata[cls].sort(key=lambda sid: hash_key(args.benchmark_seed, sid))
    dev_counts = {cls: len(v) for cls, v in strata.items()}
    # The split file's dev count includes unlabelled samples, if any;
    # report both so the difference is visible, not hidden.
    stratum_shortfall = []
    if sum(dev_counts.values()) != len(dev_ids):
        stratum_shortfall.append(
            f"dev ids in split: {len(dev_ids)}; stratified (labelled) dev "
            f"samples in data: {sum(dev_counts.values())}; "
            f"unlabelled or absent from data: {len(dev_ids) - sum(dev_counts.values())}")

    # Allocate: minimum per stratum, remainder by largest remainder.
    alloc: dict[str, int] = {}
    for cls, cnt in dev_counts.items():
        alloc[cls] = min(args.min_per_stratum, cnt)
    remaining = args.n - sum(alloc.values())
    if remaining < 0:
        print("n is smaller than the sum of minimum-per-stratum allocations",
              file=sys.stderr)
        return 2
    total_dev = sum(dev_counts.values())
    raw_share = {cls: remaining * cnt / total_dev for cls, cnt in dev_counts.items()}
    base_extra = {cls: int(raw_share[cls]) for cls in dev_counts}
    for cls in dev_counts:
        alloc[cls] += base_extra[cls]
    leftover = remaining - sum(base_extra.values())
    order = sorted(dev_counts, key=lambda c: (raw_share[c] - base_extra[c]), reverse=True)
    i = 0
    while leftover > 0 and order:
        cls = order[i % len(order)]
        if alloc[cls] < dev_counts[cls]:
            alloc[cls] += 1
            leftover -= 1
        i += 1
        if i > 10000:
            break
    if leftover > 0:
        print(f"cannot allocate {leftover} samples: dev strata exhausted", file=sys.stderr)
        return 2

    def wav_exists(raw: dict, rel: str | None) -> bool:
        return bool(rel) and (data_root / "train" / rel).exists()

    def excludable(raw: dict) -> str | None:
        if not raw.get("audio_text"):
            return "missing audio_text"
        if not wav_exists(raw, raw.get("audio")):
            return "missing current wav"
        for turn in raw.get("history", []):
            if turn.get("role") == "user" and turn.get("audio_text") is None \
                    and turn.get("audio") and not wav_exists(raw, turn["audio"]):
                return "missing history wav"
        return None

    selected: dict[str, str] = {}  # id -> stratum
    excluded: list[dict] = []
    for cls, count in alloc.items():
        taken = 0
        for sid in strata[cls]:
            if taken >= count:
                break
            raw = by_id[sid]
            reason = excludable(raw)
            if reason:
                excluded.append({"id": sid, "stratum": cls, "reason": reason})
                continue
            selected[sid] = cls
            taken += 1
        if taken < count:
            stratum_shortfall.append(
                f"stratum {cls}: allocated {count}, selected {taken} "
                "(stratum exhausted after outcome-blind exclusions)")

    def has_digit(sid: str) -> bool:
        return bool(DIGIT_RE.search(by_id[sid].get("audio_text") or ""))

    def has_search(sid: str) -> bool:
        label = by_id[sid].get("label") or {}
        return any(c.get("name") == "contacts.search"
                   for c in label.get("tool_calls") or [])

    def coverage_counts(ids) -> dict:
        return {"digit_string_n": sum(1 for s in ids if has_digit(s)),
                "contacts_search_n": sum(1 for s in ids if has_search(s))}

    # Coverage by swap, preserving n and stratum counts.
    selected_set = set(selected)
    for feature, check, minimum in (
            ("digit_string", has_digit, args.min_digit),
            ("contacts_search", has_search, args.min_contacts_search)):
        while coverage_counts(selected_set)[("digit_string_n" if feature == "digit_string"
                                             else "contacts_search_n")] < minimum:
            swapped = False
            for cls in strata:
                pool = [s for s in strata[cls]
                        if s not in selected_set and check(s)
                        and excludable(by_id[s]) is None]
                lacking = [s for s in selected_set if selected[s] == cls and not check(s)]
                if pool and lacking:
                    # Swap out the last-selected lacking sample in hash order.
                    out_sid = sorted(lacking, key=lambda s: hash_key(args.benchmark_seed, s))[-1]
                    in_sid = pool[0]
                    selected_set.remove(out_sid)
                    selected_set.add(in_sid)
                    selected[in_sid] = cls
                    del selected[out_sid]
                    excluded.append({"id": out_sid, "stratum": cls,
                                     "reason": f"coverage swap-out for {feature}",
                                     "replaced_by": in_sid})
                    swapped = True
                    break
            if not swapped:
                break
    cov = coverage_counts(selected_set)
    shortfall = []
    if cov["digit_string_n"] < args.min_digit:
        shortfall.append(f"digit_string coverage {cov['digit_string_n']} < {args.min_digit}: SHORTFALL")
    if cov["contacts_search_n"] < args.min_contacts_search:
        shortfall.append(f"contacts_search coverage {cov['contacts_search_n']} < {args.min_contacts_search}: SHORTFALL")

    ids = sorted(selected_set, key=lambda sid: hash_key(args.benchmark_seed, sid))
    selected_counts = {}
    for sid in ids:
        selected_counts[selected[sid]] = selected_counts.get(selected[sid], 0) + 1
    manifest = {
        "status": "stratified-frozen",
        "benchmark_seed": args.benchmark_seed,
        "n": len(ids),
        "ids": ids,
        "ids_sha256": sha256_text(json.dumps(ids, ensure_ascii=False)),
        "split_sha256": split_sha,
        "split_dev_n": len(dev_ids),
        "split_heldout_n": len(held_ids),
        "dev_ids_absent_from_data_n": len(missing_from_data),
        "stratum_dev_counts": dev_counts,
        "stratum_selected_counts": selected_counts,
        "coverage": cov,
        "coverage_thresholds": {"digit_string": args.min_digit,
                                "contacts_search": args.min_contacts_search},
        "coverage_shortfall": shortfall,
        "selection_notes": stratum_shortfall,
        "excluded": excluded,
        "note": "Stratified frozen set only. Held-out ids were never candidates. "
                "No transcript, gold call, or wav is stored in this manifest.",
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    (out.with_suffix(out.suffix + ".sha256")).write_text(sha256_file(out) + "\n", encoding="utf-8")
    print(json.dumps({k: manifest[k] for k in (
        "status", "n", "ids_sha256", "stratum_dev_counts",
        "stratum_selected_counts", "coverage", "coverage_shortfall")},
        indent=2, ensure_ascii=False))
    print(f"manifest -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
