# E7 Phase 0 — shadow-only provenance prototype

**Result: CPU_NOT_READY. No inference integration or GPU run.**

- 40 V13 traces audited;29 proposed writes (including rejected proposals),17 with monitored arguments.
- 1,237 dev samples screened;1,389 gold writes,459 within this guard's partial scope (511 arguments).
- Final gold decisions:31 ALLOW,428 UNKNOWN,0 BLOCK. UNKNOWNs are not successful allows and not evidence of zero over-rejection.
- Six fixed known-fill cases:5 BLOCK,1 UNKNOWN (0780 field-level supersession/refer-back).
- 33 synthetic tests pass;guard coverage87%. Independent review findings and fixes are recorded in REVIEW.md.
- Initial v1/v2/v3 audit outputs are preserved separately;corpus-motivated fixes are development, not independent validation.

No held-out assessed,no model calls. ASR-vs-gold comparisons are available for19 scoped argument occurrences on V13's observed prefixes. The remaining dev gold writes have no ASR cache;they are explicitly marked UNAVAILABLE and use gold text only as an oracle-input diagnostic.

Run from repository root:

```powershell
python -m unittest analysis.e7_shadow.test_guard -q
python analysis/e7_shadow/run_shadow.py --out ../artifacts/lifemate-e7-shadow/reproduced
```

Defaults use the existing extracted train release,the verified V13 ZIP,and the E5 CPU-validated ASR cache. `--data`, `--traces`, `--cache`, `--out` override those paths explicitly. The runner never imports the simulator adapter or executes proposals. Labels are used only by the runner to construct past-only gold observation prefixes and evaluate positive cases;`guard.assess` receives neither labels nor sample IDs.

Files:guard.py (pure three-valued decision),test_guard.py (synthetic regressions),run_shadow.py (diagnostic corpus runner),reporting.py (key=value reporting only),SPEC.md (scope and revisions),REVIEW.md (bounded independent correctness review). Runtime lifemate modules/config/seed/split/scorer/parser remain unchanged.

Published report and summaries live in analysis/runtime/E7_PHASE0_SHADOW_AUDIT_2026-10-28.md and e7_phase0_* JSON artifacts on main. Raw local outputs and gold-call details remain under ../artifacts/lifemate-e7-shadow/.
