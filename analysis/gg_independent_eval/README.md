# Independent G&G Challenge Suite

Independent verification of `lifemate_gates_adapter.decide()` (candidate Gate 2)
at baseline `287e68d5022aac243f2b5721029b6db6a17d93b5`. All cases are synthetic
and authored independently — no fixtures copied from the author's tests.

## Files

- `challenge_suite.py` — case definitions + runner. Pure CPU, no dataset/GPU/model.
- `manifest.json` — public case manifest: inputs, expected, rationale, what each
  case proves / does not prove, error group, fixture source.
- `sealed_manifest.json` — commitment hashes for 15 sealed cases (content withheld
  until the candidate freezes; repro published after evaluation).
- `README.md` — this file.

## Running

```bash
python3 challenge_suite.py \
  --lifemate-dir <dir containing lifemate_*.py at the pinned SHA> \
  --baseline-sha 287e68d5022aac243f2b5721029b6db6a17d93b5 \
  [--sealed /path/to/sealed_cases.py] \
  [--out results.json]
```

Exit 0 = all graded in-contract expectations hold. The JSON output records every
decision (fired/applicable/baseline/adjustments) for audit.

## Reading the results

- `fired=True` = gate blocks (safe direction); `fired=False` = lets through.
- `PASS` — decision matches the independently constructed expectation.
- `FAIL (finding_class=contract)` — the adapter violates its own pinned contract.
  These are bugs.
- `FAIL (finding_class=scope)` — the adapter has no fire path for this case by
  design (it can only un-fire a baseline fire, or suppress via the ledger).
  These are **coverage gaps**, not code bugs: they show what the current
  evaluation (paired/shadow) does not measure.
- `KNOWN-OPEN-FAIL` — pinned regression for a known open bug (batch-11 S1,
  bare-"chuyển"). Must flip to PASS after the fix.
- `RECORDED` — robustness/adjudication cases; decision recorded, not graded.

## What the suite proves / does not prove

Proves: whether the adapter blocks wrong commands and passes right ones **within
its contract**, on synthetic minimal inputs, deterministically.

Does not prove: end-to-end score impact (the adapter is audit-only at baseline —
no agent calls it); behavior on real model proposals (see the trace evaluation in
`research/lifemate/independent_eval/`); anything about the prover's verdicts
(separate surface).

## Baseline results (2026-10-30, SHA 287e68d5)

Public: 41 cases — 24 PASS, 5 scope FAILs, 2 known-open FAILs, 10 recorded.
Sealed: 15 cases — 10 PASS, 2 contract FAILs (new findings, undisclosed), 3 scope FAILs.
Sequence-independence check (IND-ROB-006): PASS — no cross-sample state leak.
