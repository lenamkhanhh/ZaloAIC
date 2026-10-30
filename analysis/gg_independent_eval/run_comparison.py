#!/usr/bin/env python3
"""Baseline-vs-candidate comparison driver (independent evaluation).

Runs the frozen challenge suite (public + sealed) against two FIXED
snapshots in two SEPARATE processes (no shared module cache), then
diffs per-case verdicts.

Usage:
  python3 run_comparison.py \
    --baseline-dir <dir with lifemate_*.py at baseline SHA> \
    --candidate-dir <dir with lifemate_*.py at candidate SHA> \
    --baseline-sha <full sha> --candidate-sha <full sha> \
    --sealed /path/to/sealed_cases.py \
    --out-dir <dir for results>

Outputs in --out-dir:
  - baseline_results.json / candidate_results.json (raw suite outputs)
  - RUN_LOG.md (full SHAs, sha256 of every lifemate_*.py used,
    python version, exact commands, timestamps)
  - diff.json (per-case baseline->candidate verdict transitions)

Exit 0 always (a verdict FAIL is data, not a runner error); the
comparison report interprets the diff. Never modifies either
snapshot. Sealed cases are read from the given path and never
written into --out-dir.
"""

import argparse
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
NEEDED = ["lifemate_gates.py", "lifemate_gates_adapter.py",
          "lifemate_provenance.py", "lifemate_phone_callback_evidence.py",
          "lifemate_callback_negation.py", "lifemate_evidence_lifecycle.py"]


def sha256_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def snapshot_hashes(d):
    out = {}
    for name in NEEDED:
        p = Path(d) / name
        if not p.exists():
            out[name] = "MISSING"
        else:
            out[name] = sha256_file(p)
    return out


def run_suite(python, lifemate_dir, sha, sealed, out_path):
    cmd = [python, str(HERE / "challenge_suite.py"),
           "--lifemate-dir", str(lifemate_dir),
           "--baseline-sha", sha,
           "--sealed", str(sealed),
           "--out", str(out_path)]
    t0 = time.time()
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    dt = time.time() - t0
    return {"cmd": cmd, "seconds": round(dt, 1),
            "returncode": proc.returncode,
            "stdout_tail": proc.stdout[-2000:],
            "stderr_tail": proc.stderr[-2000:]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--baseline-dir", required=True)
    ap.add_argument("--candidate-dir", required=True)
    ap.add_argument("--baseline-sha", required=True)
    ap.add_argument("--candidate-sha", required=True)
    ap.add_argument("--sealed", required=True)
    ap.add_argument("--out-dir", required=True)
    args = ap.parse_args()

    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    started = time.strftime("%Y-%m-%dT%H:%M:%S%z")

    base_hashes = snapshot_hashes(args.baseline_dir)
    cand_hashes = snapshot_hashes(args.candidate_dir)

    base_out = out / "baseline_results.json"
    cand_out = out / "candidate_results.json"
    base_run = run_suite(sys.executable, args.baseline_dir,
                         args.baseline_sha, args.sealed, base_out)
    cand_run = run_suite(sys.executable, args.candidate_dir,
                         args.candidate_sha, args.sealed, cand_out)

    base_res = json.loads(base_out.read_text(encoding="utf-8"))
    cand_res = json.loads(cand_out.read_text(encoding="utf-8"))
    b_by_id = {r["id"]: r for r in base_res["results"]}
    c_by_id = {r["id"]: r for r in cand_res["results"]}
    assert set(b_by_id) == set(c_by_id), "case id sets differ!"

    transitions = []
    for cid in sorted(b_by_id):
        b, c = b_by_id[cid], c_by_id[cid]
        transitions.append({
            "id": cid,
            "sealed": b["sealed"],
            "category": b["category"],
            "finding_class": b.get("finding_class"),
            "baseline_verdict": b["verdict"],
            "candidate_verdict": c["verdict"],
            "baseline_fired": b["actual_fired"],
            "candidate_fired": c["actual_fired"],
            "changed": b["verdict"] != c["verdict"],
        })
    (out / "diff.json").write_text(
        json.dumps(transitions, ensure_ascii=False, indent=1),
        encoding="utf-8")

    log = [
        "# Comparison run log",
        "",
        f"started: {started}",
        f"python: {sys.version.split()[0]} ({sys.executable})",
        "",
        "## Snapshots",
        f"baseline:  {args.baseline_sha}  (dir {args.baseline_dir})",
        f"candidate: {args.candidate_sha} (dir {args.candidate_dir})",
        "",
        "## lifemate_*.py sha256 (files actually imported)",
        "baseline:",
    ]
    log += [f"  {k}: {v}" for k, v in sorted(base_hashes.items())]
    log.append("candidate:")
    log += [f"  {k}: {v}" for k, v in sorted(cand_hashes.items())]
    log += [
        "",
        "## Commands (separate processes, no shared module cache)",
        "baseline:  " + " ".join(base_run["cmd"]),
        f"  -> returncode {base_run['returncode']}, "
        f"{base_run['seconds']}s",
        "candidate: " + " ".join(cand_run["cmd"]),
        f"  -> returncode {cand_run['returncode']}, "
        f"{cand_run['seconds']}s",
        "",
        "## Case counts",
        f"baseline:  {base_res['summary']['verdict_counts']}",
        f"candidate: {cand_res['summary']['verdict_counts']}",
        f"changed verdicts: "
        f"{sum(1 for t in transitions if t['changed'])}",
    ]
    (out / "RUN_LOG.md").write_text("\n".join(log) + "\n",
                                    encoding="utf-8")
    print("\n".join(log))


if __name__ == "__main__":
    main()
