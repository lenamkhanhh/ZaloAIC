#!/usr/bin/env python3
"""Observer entry-path verification (independent, candidate d1090d1d).

Question: when the package is used the realistic way (repo root on
sys.path, `import lifemate.lifemate_observer` — NO lifemate/ dir added
to sys.path), does ShadowObserver actually compute decisions, or does
it only ever emit error records?

The observer module docstring admits the precondition: the adapter's
absolute imports (`from lifemate_gates import ...`) require lifemate/
on sys.path, "the same precondition as the existing adapter tests".
This script checks what happens WITHOUT that test-only hack.

Setup: copies the candidate lifemate/*.py into <tmp>/root/lifemate/
(a faithful package layout), puts ONLY <tmp>/root on sys.path, and
runs everything in THIS process (fresh interpreter per run; the
driver runs it once per configuration).

Checks:
  1. `from lifemate.lifemate_observer import ShadowObserver` imports
     cleanly (stdlib-only at module level) — must not raise.
  2. ShadowObserver(True).observe_proposal(valid phone proposal)
     appends exactly one record and never raises.
  3. PRIMARY (realistic path): baseline_decision and
     candidate_decision are None and error names the missing
     module — i.e. the observer does NOT compute decisions here.
  4. DIAGNOSTIC (labelled, with lifemate/ ALSO on sys.path — the
     tests' precondition): the same call DOES compute decisions.
     This proves the root cause is purely the import precondition,
     not broken observer logic.

Usage:
  python3 verify_observer_entry.py --lifemate-dir <candidate lifemate/>
      --out <json>
Exit 0 = all checks behaved as asserted (including the expected
failure mode in check 3); the JSON records what was observed.
"""

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

PROBE = r'''
import json, sys
root = sys.argv[1]
mode = sys.argv[2]
sys.path.insert(0, root)
if mode == "with-hack":
    sys.path.insert(0, root + "/lifemate")
from lifemate.lifemate_observer import ShadowObserver

obs = ShadowObserver(True)
proposal = {"name": "phone.call",
            "arguments": {"phone_number": "0903111222"}}
kinds = {"phone.call": "write", "phone.recent_calls": "read"}
history = [{"role": "user", "audio_text": "gọi số 0903111222",
            "tool_calls": [], "tool_results": []}]
obs.observe_proposal(proposal, proposal, history=history,
                     executed=[], results=[],
                     current_text="gọi số 0903111222", kinds=kinds)
rec = obs.records[0]
out = {
    "mode": mode,
    "n_records": len(obs.records),
    "baseline_decision": rec["baseline_decision"],
    "candidate_decision": rec["candidate_decision"],
    "error": rec["error"],
    "eligibility": rec["eligibility"],
}
print(json.dumps(out, ensure_ascii=False))
'''


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lifemate-dir", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    tmp = Path(tempfile.mkdtemp(prefix="obs_entry_"))
    pkg = tmp / "lifemate"
    shutil.copytree(args.lifemate_dir, pkg,
                    ignore=shutil.ignore_patterns("__pycache__"))
    results = {}
    for mode in ("realistic", "with-hack"):
        # Fresh interpreter per mode: no shared module cache.
        cmd = [sys.executable, "-c", PROBE, str(tmp), mode]
        proc = subprocess.run(cmd, capture_output=True, text=True,
                              timeout=120)
        results[mode] = {
            "returncode": proc.returncode,
            "stdout": proc.stdout.strip(),
            "stderr": proc.stderr.strip()[-1500:],
        }

    realistic = json.loads(results["realistic"]["stdout"])
    with_hack = json.loads(results["with-hack"]["stdout"])
    checks = {
        "import_clean": results["realistic"]["returncode"] == 0,
        "one_record_no_raise": realistic["n_records"] == 1,
        "realistic_no_decisions":
            realistic["baseline_decision"] is None
            and realistic["candidate_decision"] is None,
        "realistic_error_is_import":
            realistic["error"] is not None
            and "ModuleNotFoundError" in realistic["error"]
            and "lifemate_gates" in realistic["error"],
        "with_hack_computes_decisions":
            with_hack["baseline_decision"] is not None
            and with_hack["candidate_decision"] is not None
            and with_hack["error"] is None,
    }
    out = {"checks": checks,
           "all_checks_hold": all(checks.values()),
           "realistic": realistic,
           "with_hack_summary": {
               "baseline_decision": with_hack["baseline_decision"],
               "candidate_decision": with_hack["candidate_decision"],
               "error": with_hack["error"]},
           "raw": results}
    Path(args.out).write_text(json.dumps(out, ensure_ascii=False,
                                        indent=1), encoding="utf-8")
    print(json.dumps(checks, ensure_ascii=False, indent=2))
    shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
