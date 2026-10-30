#!/usr/bin/env python3
"""Offline shadow ON/OFF evaluator (independent, synthetic fixtures).

Compares the BASELINE gate (OFF) against the CANDIDATE adapter (ON) on
the same proposal contexts, without touching the agent, the simulator,
or any implementation file.

This is the harness for Section 4 of the independent evaluation. A true
runtime shadow needs an agent hook that does not exist yet at baseline
(see 04_shadow_protocol.md); until then, this script runs the paired
comparison OFFLINE on the public challenge-suite fixtures, which is the
part that can be executed on the baseline today.

Checks per proposal context:
  1. Paired decision: baseline Gate 2 fired? vs candidate fired?
     Records agreements and decision changes (un-fires / new fires),
     with the adjustment mechanisms for each change.
  2. Applicability stability: candidate applicability must equal
     baseline applicability (the adapter must not silently change scope).
  3. Observation-only check: decide() must not mutate the proposal,
     prefix, or roster it was given (G&G must not change agent state
     while only observing). Deep-copies inputs, runs decide, diffs.

Usage:
  python3 shadow_evaluator.py --lifemate-dir <dir with lifemate_*.py> \
      --baseline-sha <sha> [--out results.json]

Snapshot discipline: record --baseline-sha for every run; a moving
branch tip is never treated as the same version.
"""

import argparse
import copy
import json
import sys
import traceback
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from challenge_suite import CASES  # noqa: E402  (public fixtures only)


def load_modules(lifemate_dir):
    sys.path.insert(0, lifemate_dir)
    import lifemate_gates_adapter as adapter  # noqa: E402
    return adapter


def run_paired(adapter, c):
    """Return row dict. Never raises."""
    call = copy.deepcopy(c["call"])
    prefix = copy.deepcopy(c["prefix"])
    roster = copy.deepcopy(c["roster"])
    kinds = c["kinds"] if c["id"] != "IND-ROB-003" else None
    before = (copy.deepcopy(call), copy.deepcopy(prefix),
              copy.deepcopy(roster))
    try:
        d = adapter.decide(call, prefix, roster, c["current_text"],
                           kinds, proposal_position=c["proposal_position"])
    except Exception as e:  # noqa: BLE001
        return {"id": c["id"], "raised": f"{type(e).__name__}: {e}",
                "trace": traceback.format_exc(limit=3)}
    after = (call, prefix, roster)
    mutated = [name for name, b, a in
               zip(("call", "prefix", "roster"), before, after) if b != a]
    row = {
        "id": c["id"],
        "category": c["category"],
        "group": c["group"],
        "baseline_fired": bool(d.baseline_fired),
        "baseline_applicable": bool(d.baseline_reason is not None),
        "candidate_fired": bool(d.fired),
        "candidate_applicable": bool(d.applicable),
        "decision_changed": bool(d.baseline_fired) != bool(d.fired),
        "change_direction": (
            "un-fire" if d.baseline_fired and not d.fired
            else ("new-fire" if d.fired and not d.baseline_fired
                  else "none")),
        "adjustments": [
            {k: a.get(k) for k in ("mechanism", "reference", "detail")
             if k in a} if isinstance(a, dict) else str(a)
            for a in (d.adjustments or [])],
        "inputs_mutated": mutated,
        "observation_only_ok": not mutated,
    }
    return row


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lifemate-dir", required=True)
    ap.add_argument("--baseline-sha", required=True)
    ap.add_argument("--out", default=None)
    args = ap.parse_args()

    adapter = load_modules(args.lifemate_dir)
    rows = [run_paired(adapter, c) for c in CASES
            if not c.get("sealed")]

    raised = [r for r in rows if "raised" in r]
    ok = [r for r in rows if "raised" not in r]
    changed = [r for r in ok if r["decision_changed"]]
    un_fires = [r for r in changed if r["change_direction"] == "un-fire"]
    new_fires = [r for r in changed if r["change_direction"] == "new-fire"]
    mutated = [r for r in ok if not r["observation_only_ok"]]

    summary = {
        "baseline_sha": args.baseline_sha,
        "mode": "offline-synthetic (no agent hook yet; see "
                "04_shadow_protocol.md)",
        "n_contexts": len(rows),
        "n_raised": len(raised),
        "n_agreements": len(ok) - len(changed),
        "n_decision_changes": len(changed),
        "n_un_fires": len(un_fires),
        "n_new_fires": len(new_fires),
        "un_fire_ids": [r["id"] for r in un_fires],
        "new_fire_ids": [r["id"] for r in new_fires],
        "observation_only_violations": [r["id"] for r in mutated],
        "raised_ids": [r["id"] for r in raised],
    }
    out = {"summary": summary, "rows": rows}
    text = json.dumps(out, ensure_ascii=False, indent=1)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
