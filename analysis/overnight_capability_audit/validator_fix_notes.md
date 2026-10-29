# Validator fix notes — Thread B (sft-prototype-v2 follow-up)

Scope: fix validator only (Bugs 2 and 3 from the independent Codex
audit). No builder changes, no inference/simulator/scorer/guard/
config changes, no training, no GPU, no held-out reads, no git.
Contract stays pinned: a2e832b-text, PROVISIONAL (unchanged).
This thread does NOT claim "ready to train" (Q-L2 + zero-shot
benchmark base selection are still open, owned by the coordinator).

## 1. Repro BEFORE (original code, before any fix)

Repro script: /tmp/repro_bugs.py (ephemeral; the durable repros are
the tests in test_validator_regressions.py listed in §5).
Run from ~/workspace/zalo-aic-round3, original validator:

```
BUG2 CONTROL (genuine train_0019): verdict=pass replay_ok=True hash_match=True failures=[]
BUG2 FORGED step0 train_0019: verdict=pass replay_ok=True hash_match=True failures=[]
BUG3 raw replay outcomes: [(True, None), (True, None), (True, False)]
BUG3 example not_done_steps: [2]
BUG3 train_1696 direct: verdict=pass replay_ok=True hash_match=True failures=[]
```

Both bugs reproduced exactly as Codex reported. The control (genuine
0019) passing is expected and is what makes the forged case a bug:
genuine and forged were indistinguishable to the old validator.

## 2. Root causes

**Bug 2 — artifact-trusted base prompt.** Old `validate_example`
did `base_prompt = steps[0]["prompt"]` and rebuilt later prompts from
that base. Any forged base is self-consistent by construction, so
forgery passed. There was also no independent source for the sample,
catalog, contract, or manifest: the artifact was the only source of
truth for its own prompts, and nothing checked that the sample even
belonged to the requested split part.

**Bug 3 — replay without outcome classification.** Old replay loop
set `replay_ok=False` only on `env.validate` failure; `env.call`
results were recorded but their `ok`/`done` fields were never
checked. A gold call returning ok True + done False therefore passed
with replay_ok=true, and `hash_match` (computed from the same replay)
also matched, because the failed call changes no state. The artifact's
own `not_done_steps` field was never compared against replay either,
so lying about it (`[]`) would also have passed.

**Self-found during testing (fixed in the same pass): legacy token
detection counted `target_token_ids` as a rendered field.** Legacy
v2 steps carry `target_token_ids` (raw target encoding) but no
rendered fields, so the first version of the new code classified
every legacy artifact as "mixed" and failed it instead of SKIPPING
token checks. Fixed by detecting rendered artifacts only on
rendered-only fields (`rendered_prompt`, `rendered_prompt_token_ids`,
`input_ids`, `labels`); see §4.

## 3. Before / after (same repro inputs, fixed code)

After-fix repro: /tmp/repro_after.py (same inputs, proper args:
manifest + catalog + runtime dir + part + mode):

```
BUG2 AFTER forged train_0019: verdict=fail replay_ok=True hash_match=True
  failures=['prompt_rebuild_mismatch_runtime:step 0', 'prompt_rebuild_mismatch:step 0']
BUG3 AFTER train_1696 training: verdict=fail replay_ok=True hash_match=True
  failures=['not_train_eligible:sample train_eligible is False', 'not_done:step 2']
  anomaly={'not_done_steps': [2]}
BUG3 AFTER train_1696 evaluation: verdict=pass failures=[] anomaly={'not_done_steps': [2]}
```

Notes on the after state:
- Bug 2 forged now fails on the authoritative runtime rebuild
  (`prompt_rebuild_mismatch_runtime:step 0`); the second
  `prompt_rebuild_mismatch:step 0` is the pre-existing
  builder-replica rebuild inside `validate_steps` (unchanged
  function) firing on the same tamper — two independent rebuilds
  agreeing, not a duplicate bug.
- Bug 3 training fails on TWO independent generic reasons
  (eligibility + not_done). `replay_ok` and `hash_match` stay True
  by design: they report that replay ran and the hash matches, and
  neither rescues a failing verdict. That is the point of the fix.
- Bug 3 evaluation passes with the anomaly surfaced, exactly the
  specified mode distinction (§4).

CLI end-to-end on the frozen v2 artifact (training, manifest v2,
part inner_train, no tokenizer):
`n_examples 16, passed 16, failed 0, hash_match 16, anomalies [],
token SKIPPED 16/16 (legacy)` — exit 0.
CLI on a directly built 1696 artifact: training exit 1 with
`FAIL train_1696: ['not_train_eligible...', 'not_done:step 2']`;
evaluation exit 0 with
`anomalies: [{'sample_id': 'train_1696', 'anomaly': {'not_done_steps': [2]}}]`.

## 4. What changed in the validator

File: `analysis/overnight_capability_audit/sft_prototype_validator.py`
(only file with validator logic changes).

**a) Runtime prompt rebuild (Bug 2).** New `rebuild_expected_prompts`
imports `build_base_prompt` / `render_observation_prompt` /
`Sample` / `Turn` / `catalog_tools_for_sample` from the pinned
runtime worktree (read-only import; the imported module's `__file__`
must sit under the given runtime dir, else fail-closed). It builds
the Sample from the ORIGINAL train.jsonl row, filters tools from the
supplied catalog, renders the base with the runtime function, and
appends baseline.json config suffix lines in AgentLoop.run order
(selective_reads line, then verification-read line). Expected step
prompts are base + runtime observation rendering over earlier
observations. `validate_example` compares every artifact step prompt
exactly against the rebuilt prefix; `validate_steps` (unchanged) is
still run with the REBUILT base, never with an artifact base.
Contract: `contract_name` (CLI takes it from the artifact file's
`contract.name`) must equal `a2e832b-text` or the example fails
`contract_mismatch`. If the artifact declares no contract, the check
is SKIPPED with a reason (legacy tolerance), never a silent pass.

**b) Manifest + mode.** `validate_example` takes `manifest`
(`{"assignment", "train_eligible"}`), `part`, `mode`
(`training`|`evaluation`, default `training`), `runtime_dir`,
`catalog`. Checks: sample in assignment, else
`manifest_membership`; assignment part != requested part, else
`manifest_part_mismatch`; artifact `manifest_part` field (if
present) != requested part, else `manifest_part_mismatch`;
example `sample_id` != sample id, else `sample_id_mismatch`.
Training mode: `train_eligible` False -> `not_train_eligible`.
Evaluation mode: eligibility SKIPPED with an explicit reason.
Function-level `manifest=None`: membership/eligibility SKIPPED
with reasons (never silent). CLI training mode without `--manifest`
exits 2 with a clear error; `--manifest` without `--part` also
exits 2; evaluation mode without `--manifest` proceeds with checks
SKIPPED (warned). No sample-ID blacklist anywhere: every failure
comes from generic logic (mismatch, replay outcome, metadata).

**c) Replay outcome contract (Bug 3).** New pure classifier
`classify_outcome(result)`: non-dict -> `result_not_dict`; ok not
exactly True -> `ok_false` (missing/False/non-True all fail, never
a silent pass); ok True + done False -> `not_done`; otherwise
`success` (done absent is success — the read case). `validate_example`
classifies EVERY replayed call in order: `schema_rejected` (validate
ok False) truncates replay and fails in both modes; `ok_false` /
`result_not_dict` fail in both modes (replay itself broke);
`not_done` fails in training mode and is an anomaly in evaluation
mode. `replay_ok` means "replay produced one result per gold call"
(it stays True for 1696); `hash_match` is reported but NEVER
overrides a failure. Metadata consistency (both modes): artifact
`not_done_steps` (if present) vs replay-derived indices, else
SKIPPED; artifact `state_hash` (if present) vs replay hash, else
SKIPPED; artifact `executed_calls` (if present) vs gold calls, else
SKIPPED. A mismatch in any present field fails.

**d) Future-observation check.** Beyond the generic leakage check
in `validate_steps`, `validate_example` explicitly checks that no
FULL canonical result JSON of a LATER step appears in an earlier
step's prompt -> `future_observation:result[j] in prompt[i]`.
Checks use full JSON strings, never individual values.

**e) Training vs evaluation (summary).** Training: eligibility
fail + not_done fail. Evaluation: eligibility skipped; not_done
reported as `anomaly: {not_done_steps: [...]}` in the per-example
report and in the CLI summary `anomalies` list; verdict decided by
fidelity checks only (prompt rebuild, membership, sequence, args,
parser, leakage, future observation, metadata consistency). An
evaluation artifact that truthfully records a failing trajectory can
pass with the anomaly flag. `schema_rejected` / `ok_false` /
`result_not_dict` still fail in evaluation mode: they mean replay
itself broke, not that a call merely failed to complete.

**f) Token checks (independent implementation).** This file NEVER
imports builder token helpers (`batch_tokenize`,
`attach_token_data` are absent from the module; a test asserts
this). New `batch_rendered_tokens` runs ONE validator-owned
tokenizer subprocess (helper code embedded in the validator; calls
`apply_chat_template` directly with a single user message +
`add_generation_prompt=True`, then `encode(..., add_special_tokens=False)`
for rendered text and target — the runtime `llm._render` reference).
`_verify_token_fields` compares exactly: `rendered_prompt`,
`rendered_prompt_token_ids`, `target_token_ids`, `input_ids`
(rendered + target + [eos]), `labels` ([-100]*rendered + target +
[eos]), `eos_token_id` (151645), `sequence_tokens`
(= len(input_ids)); `prompt_token_ids`, when present, must equal
the rendered ids. Specific failures: `double_eos` (target already
ends in EOS), `prompt_trained_not_masked`,
`target_masked_or_eos_wrong`, `budget_prompt_plus_reserve`
(rendered + 512 > 16384), `budget_sequence`. Legacy artifacts (no
rendered-only field on any step) -> token checks SKIPPED with
reason, other checks decide the verdict. Mixed steps -> fail
`token_fields_inconsistent`. `check_token_spans` keeps its old
name/signature but is reimplemented on this path (legacy -> SKIPPED
dict, no raise). CLI batches tokens once for all rendered examples;
a batch failure warns and SKIPs token checks (never a silent pass).
Caveat (honest boundary): token tests prove ENFORCEMENT (tampered
fields fail); proving separate prompt/target encoding equals the
full training serialization is Thread A's scope, not this file's.

**CLI changes.** New flags: `--manifest`, `--part`,
`--mode training|evaluation` (default training), `--runtime-dir`
(default the pinned worktree lifemate dir). Old flags
(`--output/--train-jsonl/--data-root/--catalog/--zaic-tools-dir/
--tokenizer-python/--model/--revision`) unchanged. Exit codes:
0 all pass, 1 any fail, 2 CLI usage errors (training without
manifest, manifest without part, unreadable/malformed manifest).
Summary gains an `anomalies` list. A sample id missing from
train.jsonl now yields a fail report (`sample_not_found`) instead
of a crash (small robustness fix, same file).

**Unchanged on purpose.** `validate_steps`, `parse_model_output`,
`token_f1`, `compact` are byte-identical in behavior (old tests
import them). No changes to `sft_prototype_builder.py`,
`test_tokenization_regressions.py`, or Thread A's notes. No
seed/split/targets/fuzzy-threshold/baseline/config changes. The
validator never puts gold/future observations into model input:
rebuilt prompts contain only prior observations by construction.

## 5. Tests

New file: `analysis/overnight_capability_audit/test_validator_regressions.py`
(27 tests). No changes to `test_sft_prototype.py` were required:
the old suite passes unmodified against the new validator (its
imports — `validate_steps`, `parse_model_output`, `token_f1` — are
unchanged), verified by rerun below.

Coverage (each maps to a brief requirement):
- Bug 2: forged step0 on empty-stop train_0019 (part read from
  manifest v2, not hardcoded) fails on runtime rebuild; genuine
  0019 passes; current-transcript tamper fails; history-turn tamper
  (train_0063) fails; catalog tamper (tool description) fails;
  config-suffix tamper fails; sample_id change fails; requested
  part mismatch fails; artifact manifest_part tamper fails; future
  observation insertion fails on `future_observation`; valid frozen
  v2 artifact (train_0003) passes with token SKIPPED (legacy).
- Bug 3: 1696 direct end-to-end training fails on `not_done:step 2`
  with `hash_match=True` (hash does not rescue); classifier unit
  tests (success / done-absent success / not_done / ok_false /
  ok-missing / ok-non-True / non-dict); 1696 with forged
  `not_done_steps=[]` still fails (replay not_done + metadata
  mismatch); 1696 evaluation passes with anomaly `{not_done_steps:
  [2]}` and eligibility SKIPPED; successful read/write/ask/empty
  (train_0003 / train_0116 / train_0036) pass with empty replay
  not_done; manifest=None skips membership/eligibility at function
  level; CLI training without manifest exits 2; CLI part mismatch
  exits 1.
- Token (independent): legacy artifact token SKIPPED; rendered
  fields enforced on a valid example; label tamper, rendered-prompt
  tamper, prompt-trained, double_eos (isolated: consistent fields
  built from an EOS-terminated target, only double_eos fires),
  budget boundary (synthetic 16000-token rendered prompt ->
  `budget_prompt_plus_reserve`); validator has no builder token
  helper attributes.

Results (pass / fail / error / skip, separately):
- New suite, system python3: 27 pass / 0 fail / 0 error / 0 skip.
- New suite, venv python: 27 pass / 0 fail / 0 error / 0 skip.
- Old suite (`test_sft_prototype.py`), system python3: 20 pass /
  0 fail / 0 error / 0 skip.
- Old suite, venv python: 20 pass / 0 fail / 0 error / 0 skip.
No test run is reported as "20/20" or "27/27" with hidden skips:
skip counts are 0 in all four runs above.

Revisions used: runtime worktree agent commit a2e832b (read-only
import; baseline.json: grounding=false, selective_reads=true,
verification_read_after_write=false, max_context 16384,
max_new_tokens 512, llm_revision cdbee75); tokenizer
Qwen/Qwen3-4B-Instruct-2507 rev cdbee75, transformers 5.21.0,
via ~/workspace/zaic-test-venv/bin/python only (system python3 has
no transformers; tokenizer subprocess is the only tokenizer path).

## 6. Reproduction commands

From ~/workspace/zalo-aic-round3 (CPU only):
```
# New regression suite (both backends)
python3 analysis/overnight_capability_audit/test_validator_regressions.py
~/workspace/zaic-test-venv/bin/python analysis/overnight_capability_audit/test_validator_regressions.py
# Old suite (must stay green, unmodified)
python3 analysis/overnight_capability_audit/test_sft_prototype.py
~/workspace/zaic-test-venv/bin/python analysis/overnight_capability_audit/test_sft_prototype.py
# CLI on the frozen v2 artifact (training, manifest, no tokenizer)
python3 analysis/overnight_capability_audit/sft_prototype_validator.py \
  --output analysis/overnight_capability_audit/sft_prototype_local.json \
  --train-jsonl ~/workspace/zaic-data/lifemate/extracted/train+public_test/train/train.jsonl \
  --data-root ~/workspace/zaic-data/lifemate/extracted/train+public_test \
  --catalog ~/workspace/zaic-data/lifemate/extracted/train+public_test/train/train_tools_catalog.json \
  --manifest analysis/overnight_capability_audit/inner_split_seed1337_v2.json \
  --part inner_train
# expect: passed 16, failed 0, hash_match 16, token SKIPPED 16/16 (legacy), exit 0
```
Durable repros are the tests above; /tmp/repro_bugs.py and
/tmp/repro_after.py were the ephemeral before/after scripts (their
outputs are quoted verbatim in §1 and §3).

## 7. Interface notes for the coordinator (builder side, NOT done here)

- The validator now ENFORCES rendered token fields when present
  (see §4f). The frozen v2 artifact has none, so its token checks
  SKIP by design. The enforce path is only exercised once Thread
  A's builder emits `rendered_prompt`,
  `rendered_prompt_token_ids`, `target_token_ids`, `input_ids`,
  `labels`, `eos_token_id`, `sequence_tokens` per the agreed
  interface (prompt_token_ids = rendered ids). The coordinator
  must run the validator on the REGENERATED artifact to exercise
  enforcement; this thread's enforce tests use validator-rendered
  fields, which prove tamper detection, not builder correctness.
- CLI training mode now REQUIRES --manifest/--part. Old validator
  invocations without them will exit 2; the coordinator's rerun
  commands must add both flags (as in §6).
- The validator's token reference is runtime `llm._render`.
  Thread A owns proving that reference equals the full training
  serialization (separate prompt/target encoding vs end-to-end
  input_ids); if A changes the serialization, this validator's
  reference must be re-checked, not silently assumed.

## 8. Still BLOCKED / SKIPPED (not papered over)

- Token checks on the frozen v2 artifact: SKIPPED (legacy, no
  rendered fields) — by design, pending regenerated artifact
  (§7). This is NOT a pass of token correctness for that artifact.
- ok:false end-to-end via real replay: NOT FEASIBLE from gold
  calls (gold calls all validate; a real ok:false gold trajectory
  does not exist in dev). Covered by classifier unit tests +
  1696 not_done end-to-end; no fabricated e2e case is claimed.
- Guard shadow on prototype trajectories: NOT RUN by this thread
  (validator deliberately never imports the guard; guard fires are
  diagnostic only). Still open for the coordinator.
- Runtime import failure mode: if the pinned worktree cannot be
  imported or baseline.json is missing, `validate_example` fails
  closed (`runtime_rebuild_failed`) rather than passing on
  artifact prompts. No such failure occurred in this thread's runs.
- Training itself remains NOT AUTHORIZED (Q-L2 + benchmark base
  selection open). This thread verifies the prototype validator
  only.
