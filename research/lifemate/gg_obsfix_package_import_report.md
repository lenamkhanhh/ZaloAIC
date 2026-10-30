# Observer package-import fix (after R5, before any selection-check work)

Base: `gg-r5-number-lifecycle-shadow` @ `d1090d1d2c78d1354c653826d8b1d96e1c107ec8`.
This commit changes **imports and import-adjacent comments only**.
No G&G decision, threshold, evidence rule, simulator, scorer, model,
seed, split, decoding, or baseline-config change. No merge to main.
No GPU / model run. CPU-verified only.

## 1. The bug (reproduced on the real snapshot before fixing)

Clean process, cwd = repo root, no `PYTHONPATH`, normal package import:

```python
from lifemate.lifemate_observer import ShadowObserver
obs = ShadowObserver(True)
obs.observe_proposal(
    {"name": "phone.call", "arguments": {"phone_number": "0902345678"}},
    {"name": "phone.call", "arguments": {"phone_number": "0902345678"}},
    history=[], executed=[], results=[],
    current_text="Gọi số0902345678",
    kinds={"phone.call": "write"})
```

Before: `baseline_decision=null`, `candidate_decision=null`,
`error=ModuleNotFoundError("No module named 'lifemate_gates'")`.
This is exactly the independent evaluator's §5 finding: in the real
entrypoint path the observer computed no decision at all (part A,
agent unchanged, held; part B, observer actually deciding, failed).

Cause (verified, not assumed): the observer imports the adapter by
relative import, but the adapter and one of its dependencies used
top-level imports (`from lifemate_gates import ...`,
`from lifemate_callback_negation import ...`, ...). Those resolve
only when `lifemate/` itself is on `sys.path` — a precondition that
existed only in the author's tests, which the observer's own
docstring had recorded as if it were the contract.

## 2. The contract after this fix

- Inside the package, sibling modules use **relative imports**
  (`from .lifemate_gates import ...`), matching `lifemate/agent.py`.
- Every outside consumer (scripts, tests, entrypoints) imports
  **`lifemate.*` with the repo root on `sys.path`** — the same
  contract as the real entrypoint (`lifemate/run.py`, which inserts
  its parent directory and imports `lifemate.*`).
- **Never** add `lifemate/` itself to `sys.path`. That path masked
  this bug; tests that did so are migrated, not kept.
- Audit scripts keep their CLI (`--lifemate-dir <dir>`), but the
  directory must be named `lifemate` and the script puts its
  **parent** on `sys.path` (with a loud error otherwise).
- Private-workspace fallbacks are removed: `gg_shadow.py` /
  `model_trace_shadow.py` no longer fall back to a home-directory
  workdir; a missing `--lifemate-dir` / `--e7-audit` now fails with
  a message telling the caller what to pass.

Files changed (17 + this report):

- `lifemate/lifemate_gates_adapter.py` — 4 imports top-level →
  relative.
- `lifemate/lifemate_phone_callback_evidence.py` — 1 import →
  relative.
- `lifemate/lifemate_observer.py` — docstring contract paragraph
  rewritten (the old paragraph stated the broken precondition).
- `analysis/gg_paired_audit.py`, `analysis/gg_shadow.py`,
  `analysis/model_trace_shadow.py`, `analysis/e7_dag_shadow_audit.py`,
  `analysis/gates_precision_audit.py`,
  `analysis/repro_codex_counterexamples.py` — repo root on path +
  `lifemate.*` imports; fallbacks removed where present.
- `tests/test_callback_negation.py`, `tests/test_gates_adapter.py`,
  `tests/test_lifemate_gates.py`, `tests/test_lifemate_provenance.py`,
  `tests/test_name_binding.py`, `tests/test_phone_callback_evidence.py`,
  `tests/test_unfire_controls.py`, `tests/test_observer.py` — repo
  root only, `lifemate.*` imports. No test expectation changed;
  one new test added (see §3) and one harness fix: the frozen-v10
  old-baseline control now **skips** (instead of failing) when the
  local frozen-v10 reference tree is absent, so the suite runs on
  any checkout without a private workspace path.

## 3. Verification

### Repro after (same clean process as §1)

```json
"baseline_decision": {"fired": true, "applicable": true,
  "reason": "unestablished reference(s): phone_number 0902345678"},
"candidate_decision": {"fired": true, "applicable": true},
"error": null
```

Module identity is single: `lifemate.lifemate_gates` is loaded, no
top-level `lifemate_gates` copy exists.

Note on the evaluator's control diagnosis (candidate `fired=False`
with `lifemate/` on path): that value corresponds to the **spaced**
text `Gọi số 0902345678`, verified here — spaced text gives
candidate `fired=False` in the new package mode too. The unspaced
`Gọi số0902345678` in the repro gives candidate `fired=True`
(insufficient evidence for the glued token → safe direction), and
the old tree in its masked mode gives the identical answer for the
identical input. Decisions are path-independent; only loading was
broken.

### New test (pins the contract, not just OFF/ON equality)

`tests/test_observer.py::TestCleanProcessPackageObserver` spawns a
fresh interpreter with cwd = repo root, no `PYTHONPATH`, no
preloaded test modules, runs the §1 repro, and asserts: exactly one
record, `error=None`, baseline and candidate decisions are real
dicts with boolean `fired`, the gate module loads only as
`lifemate.*`, and both decisions equal a direct in-process
`decide()` call on the same inputs.

### Regression (exact counts)

All `tests/test_*.py` standalone from the repo root, both
backends (system `python3` and the tokenizer venv):

- `615/615` pass, `0` fail, `0` error, `0` skip on each backend.
- R5 was `614`; the +1 is the new clean-process test
  (`test_observer.py` 17 → 18). Every other file's count is
  unchanged. The frozen-v10 old-baseline control ran (not skipped)
  on the verifying machine where that reference tree exists.

### Paired / shadow controls (must be identical — they are)

From the repo root, `--lifemate-dir lifemate`, dev only:

- Paired gold (dev 1237, scope 976): output JSON **byte-identical**
  to the R5 control — baseline fired 15/976, candidate fired 2/976,
  same 13 un-fires, same by-group table.
- Shadow controls V10 / V11 / V13: rows **identical** and summaries
  **identical** to the R5 controls (V10: 6/0/3/5; V11: 6/0/2/2;
  V13: 16/0/0/6 with 7 out-of-scope-guard; adjudication order
  correct_block / false_block / correct_pass / miss).

## 4. Observer log: how to get / export it

The observer log currently lives **in RAM only**. There is no
automatic file output, and this commit adds none. After a run, the
owning loop holds the observer; export it explicitly:

```python
log_json = loop.observer.to_json()   # JSON list of record dicts
# or: records = loop.observer.records
```

Write `log_json` to a file from the caller if a durable artifact is
needed. `ShadowObserver.reset()` clears the records (per-sample
reset in the loop). Records are JSON-serialisable (9 keys; see the
R5 report §6 for the schema).

## 5. What this commit does NOT do

- No a2e832b observer port, no model/GPU verification (still
  CPU-verified only; the R5 §7 GPU brief for Codex is unchanged).
- No selection-check, negation, or question-handling change: the
  sealed findings (SEAL-003/004), the known-open bare-"chuyển"
  case, and the selection-consistency gap are **not** addressed
  here. They are a separate follow-up commit, so the import fix can
  be evaluated on its own.
- No group-joining, no PRODUCER_REGISTRY extension, no change to
  any evaluator expectation.
