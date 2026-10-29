#!/usr/bin/env python3
"""Independent verification of inner_split_seed1337_v2.json + v1->v2 diff.

This script does NOT generate the split; it re-verifies it from data
and writes split_v2_diff.md. It reads ONLY dev rows (split-map filter
first; held-out content is never opened). Audio files hashed here are
exactly the paths referenced by dev samples (current + history user
turns); no held-out audio path is ever opened.

Checks:
1. v2 structural: counts, partition disjointness, 0 held-out ids,
   near-duplicate group whole to train, train_eligible consistency,
   independent recomputation of kind/history/rbw rates vs manifest.
2. v1 -> v2 diff: moved ids (common 1233), added ids (4), per-part
   and per-kind count deltas.
3. Audio: path inventory, file existence, sha256 content hashes,
   content collisions (same hash, different paths) and whether any
   collision crosses v2 parts. Path-disjoint is structural; only a
   hash check can support content-disjoint, and only if it passes.
4. Tool-sequence overlap: fraction of val/test samples whose exact
   gold tool-call-name sequence also occurs in train.
5. Template groups: normalized current-request text (NFD diacritic
   fold + lowercase + digit-run masking) and an entity-masked
   secondary variant (contacts.search query substrings -> #NAME);
   group sizes and cross-part straddles. A shared normalized text
   is reported as a shared TEXT TEMPLATE, never as proof of
   template-disjointness or behaviour-disjointness.
"""
import hashlib
import json
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path("/home/hatch/workspace/zalo-aic-round3")
DATA_ROOT = Path("/home/hatch/workspace/zaic-data/lifemate/extracted/train+public_test")
AUDIT = REPO / "analysis/overnight_capability_audit"


def fold(s):
    s = unicodedata.normalize("NFD", s or "").lower()
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = re.sub(r"\d+", "#", s)
    return " ".join(s.split())


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
    split = json.load(open(REPO / "lifemate/splits/train_dev_heldout.json"))
    dev_ids = {k for k, v in split.items() if v == "dev"}
    catalog = json.load(open(DATA_ROOT / "train/train_tools_catalog.json"))
    kind_by_tool = {}
    for app in catalog["apps"]:
        for t in app["tools"]:
            kind_by_tool[t["name"]] = t.get("kind", "")
    rows = {}
    for line in open(DATA_ROOT / "train/train.jsonl"):
        s = json.loads(line)
        if s["id"] not in dev_ids:
            continue
        rows[s["id"]] = s
    assert len(rows) == 1237
    v1 = json.load(open(AUDIT / "inner_split_seed1337.json"))
    v2 = json.load(open(AUDIT / "inner_split_seed1337_v2.json"))
    a1, a2 = v1["assignment"], v2["assignment"]
    out_lines = []
    out_lines.append("# inner_split_seed1337 v1 -> v2 diff + verification\n")
    out_lines.append("v1: population dev-minus-quarantine = 1233 (seed 1337, "
                     "863/185/185). v2: full dev = 1237 (seed 1337, "
                     "866/185/186). v1 file was only read, never "
                     "overwritten. All counts below are recomputed from "
                     "data + manifests.\n")

    # 1. Structural verification of v2 (independent recomputation).
    out_lines.append("## 1. v2 structural verification (independent)\n")
    assert len(a2) == 1237 and len(set(a2)) == 1237
    assert Counter(a2.values()) == {"inner_train": 866, "inner_val": 185, "inner_test": 186}
    assert not (set(a2) - dev_ids), "held-out ids present!"
    nd = ["train_0061", "train_0066", "train_0168"]
    assert all(a2[s] == "inner_train" for s in nd)
    te = v2["train_eligible"]
    assert sum(1 for v in te.values() if not v) == 1 and te["train_1696"] is False
    def cell_of(s):
        calls = s["label"]["tool_calls"]
        kind = gold_kind(calls)
        hist = bool(s.get("history"))
        seen = False
        rbw = "no_write"
        for c in calls:
            k = kind_by_tool.get(c.get("name", ""), "")
            if k == "read":
                seen = True
            elif k == "write":
                rbw = "write_after_read" if seen else "write_without_prior_read"
                break
        return kind, hist, rbw
    def rates(ids):
        n = len(ids)
        kinds = Counter(cell_of(rows[s])[0] for s in ids)
        hist = sum(1 for s in ids if cell_of(rows[s])[1]) / n
        rbw = Counter(cell_of(rows[s])[2] for s in ids)
        return (n, {k: round(v / n, 4) for k, v in sorted(kinds.items())},
                round(hist, 4), {k: round(v / n, 4) for k, v in sorted(rbw.items())})
    pop = rates(sorted(rows))
    out_lines.append(f"- counts: {dict(Counter(a2.values()))}; disjoint: True; "
                     f"held-out ids: 0; near-dup group in train: {nd}; "
                     f"train_eligible False: only train_1696.\n")
    for part in ("inner_train", "inner_val", "inner_test"):
        ids = sorted(s for s, p in a2.items() if p == part)
        n, kr, hr, rr = rates(ids)
        ok = all(abs(kr.get(k, 0) - pop[1].get(k, 0)) <= 0.02 for k in pop[1]) \
            and abs(hr - pop[2]) <= 0.02 \
            and all(abs(rr.get(k, 0) - pop[3].get(k, 0)) <= 0.02 for k in pop[3])
        out_lines.append(f"- {part}: n={n}, kind={kr}, history={hr}, rbw={rr} "
                         f"-> within +/-2pp of population: {ok}\n")
        assert ok

    # 2. v1 -> v2 diff.
    out_lines.append("\n## 2. v1 -> v2 diff\n")
    common = sorted(set(a1) & set(a2))
    moved = sorted(s for s in common if a1[s] != a2[s])
    added = sorted(set(a2) - set(a1))
    removed = sorted(set(a1) - set(a2))
    out_lines.append(f"- common ids: {len(common)}; moved part: {len(moved)}; "
                     f"added (quarantine returned): {added} -> "
                     f"{[(s, a2[s]) for s in added]}; removed: {removed}.\n")
    out_lines.append("- counts v1 -> v2 per part: "
                     f"{dict(Counter(a1.values()))} -> {dict(Counter(a2.values()))}.\n")
    def kind_counts(asg):
        c = Counter()
        for s, p in asg.items():
            c[(p, gold_kind(rows[s]["label"]["tool_calls"]))] += 1
        return c
    k1, k2 = kind_counts(a1), kind_counts(a2)
    for part in ("inner_train", "inner_val", "inner_test"):
        d = {k: k2[(part, k)] - k1[(part, k)] for k in ("normal", "ask_after", "empty", "ask_only")}
        out_lines.append(f"- kind delta {part}: {d}\n")
    out_lines.append(f"- moved ids ({len(moved)}): {', '.join(moved)}\n")
    out_lines.append("- Why so many moves are expected: v2 re-runs the "
                     "identical stratified procedure (seed 1337) on a "
                     "different population (1237 vs 1233); cell "
                     "membership changes shift in-cell shuffle order. "
                     "v1 was a proposal never used for training, so "
                     "re-running costs nothing; hand-placing only 4 ids "
                     "would have introduced placement bias.\n")

    # 3. Audio content-hash check (dev paths only).
    out_lines.append("\n## 3. Audio checks (dev paths only)\n")
    audio_owner = {}  # path -> sample id (first owner)
    audio_kind = {}   # path -> 'current' | 'history'
    for sid, s in rows.items():
        if s.get("audio"):
            audio_owner.setdefault(s["audio"], sid)
            audio_kind.setdefault(s["audio"], "current")
        for h in s.get("history", []):
            if h.get("role") == "user" and h.get("audio"):
                audio_owner.setdefault(h["audio"], sid)
                audio_kind.setdefault(h["audio"], "history")
    missing = [p for p in audio_owner if not (DATA_ROOT / "train" / p).is_file()]
    hashes = {}
    for p in audio_owner:
        fp = DATA_ROOT / "train" / p
        if not fp.is_file():
            continue
        h = hashlib.sha256()
        with open(fp, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        hashes[p] = h.hexdigest()
    by_hash = defaultdict(list)
    for p, h in hashes.items():
        by_hash[h].append(p)
    collisions = {h: ps for h, ps in by_hash.items() if len(ps) > 1}
    cross_part = []
    for h, ps in collisions.items():
        parts = {a2[audio_owner[p]] for p in ps}
        if len(parts) > 1:
            cross_part.append((h[:16], ps, sorted(parts)))
    out_lines.append(f"- dev audio paths inventoried: {len(audio_owner)} "
                     f"(current: {sum(1 for v in audio_kind.values() if v == 'current')}, "
                     f"history: {sum(1 for v in audio_kind.values() if v == 'history')}); "
                     f"files missing on disk: {len(missing)} {missing[:5]}.\n")
    out_lines.append(f"- sha256 computed: {len(hashes)}; distinct hashes: {len(by_hash)}; "
                     f"content collisions (same hash, different paths): {len(collisions)}.\n")
    out_lines.append(f"- collisions crossing v2 parts: {len(cross_part)} {cross_part[:5]}.\n")
    if not collisions:
        out_lines.append("- CONTENT-DISJOINT (dev audio, v2 parts): no two "
                         "different dev audio paths share content, so no "
                         "content overlap exists across parts. (This is a "
                         "statement about referenced dev audio files only; "
                         "it says nothing about held-out audio, which was "
                         "never opened.)\n")
    else:
        out_lines.append("- CONTENT-DISJOINT: NOT established (see collisions above).\n")

    # 4. Tool-sequence overlap.
    out_lines.append("\n## 4. Tool-sequence overlap (exact gold call-name sequences)\n")
    seq_of = {sid: tuple(c.get("name", "") for c in s["label"]["tool_calls"]) for sid, s in rows.items()}
    train_seqs = {seq_of[s] for s, p in a2.items() if p == "inner_train"}
    out_lines.append(f"- distinct gold tool sequences in dev: {len(set(seq_of.values()))}.\n")
    for part in ("inner_val", "inner_test"):
        ids = [s for s, p in a2.items() if p == part]
        shared = sum(1 for s in ids if seq_of[s] in train_seqs)
        out_lines.append(f"- {part}: {shared}/{len(ids)} samples "
                         f"({shared / len(ids):.1%}) have an exact gold tool "
                         f"sequence that also occurs in train. This is "
                         f"EXPECTED (582 distinct sequences over 1237 "
                         f"samples) and is reported, not hidden; it is why "
                         f"a random split measures new requests with "
                         f"familiar behaviours, not unseen behaviour.\n")

    # 5. Template groups.
    out_lines.append("\n## 5. Template groups (normalized request text)\n")
    def queries_of(s):
        qs = set()
        for calls in ([h.get("tool_calls") or [] for h in s.get("history", []) if h.get("role") == "assistant"] + [s["label"]["tool_calls"]]):
            for c in calls:
                if c.get("name") == "contacts.search" and (c.get("arguments") or {}).get("query"):
                    qs.add(fold((c.get("arguments") or {}).get("query")))
        return qs
    groups = defaultdict(list)
    egroups = defaultdict(list)
    for sid, s in rows.items():
        norm = fold(s.get("audio_text"))
        groups[norm].append(sid)
        en = norm
        for q in queries_of(s):
            if q:
                en = en.replace(q, "#NAME")
        egroups[en].append(sid)
    for label, gr in (("normalized (fold + digit-mask)", groups),
                      ("entity-masked secondary (queries -> #NAME)", egroups)):
        multi = {k: v for k, v in gr.items() if len(v) > 1}
        straddle = {k: v for k, v in multi.items() if len({a2[s] for s in v}) > 1}
        out_lines.append(f"- {label}: {len(gr)} groups; multi-member groups: {len(multi)}; "
                         f"groups straddling v2 parts: {len(straddle)}.\n")
        for k, v in sorted(straddle.items(), key=lambda kv: -len(kv[1]))[:10]:
            out_lines.append(f"  - group size {len(v)}: {[(s, a2[s]) for s in v]}\n")
    out_lines.append("- No 'template-disjoint' claim is made: shared "
                     "normalized text is a shared TEXT TEMPLATE only. "
                     "Behaviour-template (tool-sequence) overlap is "
                     "reported separately in section 4.\n")
    text = "".join(out_lines)
    with open(AUDIT / "split_v2_diff.md", "w") as f:
        f.write(text)
    print(text)
    print("WROTE split_v2_diff.md")


if __name__ == "__main__":
    main()
