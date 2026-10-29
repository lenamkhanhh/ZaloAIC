# SFT prototype fix report — Codex audit: 3 bugs reproduced on branch originals, fixed at root, regression-tested

**Verdict up front: CPU prototype VERIFIED for the three audited bugs
and their regressions. This is NOT a ready-to-train verdict.**
Training stays unauthorized: derived-checkpoint eligibility (Q-L2)
and the zero-shot benchmark base selection are still open (see §6).
Base: branch `sft-prototype-v2` @ `7c88d415`. This round changes
only prototype builder/validator/tests/notes (CPU); no inference,
simulator, scorer, guard, config, seed, split membership, targets,
fuzzy threshold, or baseline changed. No held-out read. No training,
no GPU, no BTC contact, no Kaggle.

## 1. Root cause and before/after per repro (coordinator reruns)

All "before" rows below were reproduced by the coordinator on the
BRANCH ORIGINALS (fetched `sft-prototype-v2` @ `7c88d415` into
`/tmp/orig_validator.py` / `/tmp/orig_builder.py`; buggy patterns
confirmed in the original files: validator line 251
`base_prompt = steps[0]["prompt"]`; builder line 444
`tok.encode(text, add_special_tokens=False)`). "After" rows are the
coordinator's reruns on the fixed code. Threads A/B recorded the
same before-behavior independently before fixing; the numbers below
are the coordinator's, not copied from thread reports.

### Bug 1 — Tokenization did not match runtime
- **Root cause:** the old builder helper encoded the RAW prompt text
  with `add_special_tokens=False`, skipping the chat template,
  while runtime `llm.py::_render` (worktree a2e832b, lines 33–44)
  builds `messages=[{"role":"user","content":prompt}]` and applies
  `apply_chat_template(..., add_generation_prompt=True)` before
  either backend tokenizes. The old validator reused the builder's
  helper (`check_token_spans` imports `batch_tokenize` from the
  builder), so both sides agreed while both were wrong. The missing
  tokens sit exactly where they condition the first target token.
- **Before (coordinator, frozen v2 artifact, train_0003 step 0,
  real tokenizer):** stored `prompt_token_ids == raw encode: True`,
  `== rendered: False`. Raw 7282 tokens vs rendered 7290 (**+8**).
  Missing head `[151644 <|im_start|>, 872 'user', 198 '\n']` and
  tail `[151645 <|im_end|>, 198 '\n', 151644 <|im_start|>, 77091
  'assistant', 198 '\n']`. Rendered text:
  `<|im_start|>user\n{base_prompt}<|im_end|>\n<|im_start|>assistant\n`.
  Old budget numbers were computed on raw lengths, so they were
  wrong by the same 8 tokens per step.
- **After (coordinator, regenerated artifact):** every step's
  `prompt_token_ids == rendered_prompt_token_ids`, and
  `input_ids == rendered + target + [151645]`,
  `labels == [-100]*len(rendered) + target + [151645]` on all 38
  steps (checked programmatically, zero violations). Prompt text
  and target text are byte-identical to the old artifact on all 38
  steps — only token ids/labels changed, so no target, seed, split,
  or fuzzy-threshold change is involved.
- **Concat vs full-text (the subtle point, resolved with evidence,
  not by preference):** full-conversation tokenization equals the
  concat construction plus exactly one trailing token `[198 '\n']`
  after EOS — a token generation never emits (it stops at EOS).
  Concat (`rendered_prompt_ids + target_ids + [eos]`) is therefore
  the correct teacher-forcing construction: at inference the model
  is fed the rendered prompt ids and then generates target ids, so
  generation-time ids are ground truth and full-text tokenization
  is the approximation. The builder records
  `full_conversation_match`/`full_conversation_extra` per step as a
  diagnostic. Transformers 5.21.0 note: `apply_chat_template(
  tokenize=True)` returns a BatchEncoding, not a list — the helper
  handles both shapes.

### Bug 2 — Validator trusted the artifact's base prompt
- **Root cause:** old `validate_example` took
  `base_prompt = steps[0]["prompt"]` and rebuilt later steps from
  that same base, so a forged base is self-consistent and passes.
  No independent source (sample, catalog, contract, manifest) was
  consulted.
- **Before (coordinator, branch originals):** genuine train_0019 →
  `pass, replay_ok=True, hash_match=True, failures=[]`; forged
  step0 (`"FORGED CONTEXT: user requested a different task."`) →
  `pass, replay_ok=True, hash_match=True, failures=[]`. (train_0019
  is in v2 inner_test; the repro uses its manifest part, not an
  assumed part.)
- **After (coordinator, fixed validator CLI, training mode,
  manifest v2, part inner_test):** forged 0019 → **exit 1, passed 0,
  failed 1**, failures
  `['prompt_rebuild_mismatch_runtime:step 0',
  'prompt_rebuild_mismatch:step 0']` — two independent rebuilds
  (runtime function and the older replica) agree on the tamper.
- **Fix:** the validator rebuilds the expected base prompt from the
  original sample row + catalog + pinned contract, importing
  `build_base_prompt` / `render_observation_prompt` / `Sample` /
  `Turn` / `catalog_tools_for_sample` from the pinned runtime
  worktree (read-only; it fail-closes with `runtime_rebuild_failed`
  if the imported module is not under the runtime dir). Every step
  prompt is compared exactly against its rebuilt prefix (base +
  prior observations only). An artifact-declared contract other
  than `a2e832b-text` fails `contract_mismatch`; an undeclared
  contract is an explicit SKIP (legacy tolerance), never a silent
  pass. Manifest/part/sample_id are checked against the
  independently provided manifest (see §2).

### Bug 3 — Validator ignored unsuccessful calls
- **Root cause:** the old replay loop only tracked `env.validate`
  failures; `env.call` results were recorded but their `ok`/`done`
  fields were never checked, so a call returning ok True + done
  False still passed with `replay_ok=True`, and `hash_match` (from
  the same replay) also matched because a failed call changes no
  state. The artifact's `not_done_steps` was never compared to the
  replay either.
- **Before (coordinator, branch originals):** direct ToolEnv replay
  of all gold train_1696 calls gives outcomes
  `[(True, None), (True, None), (True, False)]`; a directly built
  example has `not_done_steps=[2]`, `dropped=False`; old validator
  → `pass, replay_ok=True, hash_match=True, failures=[]`. (Note:
  the branch builder's `replay_gold` already refused 1696 via its
  all-succeed filter — Codex's repro correctly bypassed the CLI
  and built the example directly, which is what was tested.)
- **After (coordinator, fixed validator CLI):** 1696 training mode
  → **exit 1, passed 0, failed 1**, failures
  `['not_train_eligible:sample train_eligible is False',
  'not_done:step 2']` — two generic, independent reasons (no
  sample-ID rule anywhere). 1696 evaluation mode → **exit 0,
  passed 1, failed 0**, with anomaly
  `{'sample_id': 'train_1696', 'anomaly': {'not_done_steps': [2]}}`
  — eligibility is ignored in evaluation mode and the failing call
  is reported as an anomaly, exactly as the spec requires:
  train_1696 stays in the manifest/evaluation with its anomaly
  flag; training rejects it on mechanical grounds.
- **Fix:** outcome classifier `classify_outcome`: non-dict →
  `result_not_dict`; `ok` not exactly True (missing/False/other)
  → `ok_false`; ok True + done False → `not_done`; otherwise
  success (absent `done` = success, the read case).
  `schema_rejected`/`ok_false`/`result_not_dict` fail in BOTH modes
  (the replay itself is broken); `not_done` fails in training and
  is an anomaly in evaluation. Metadata is cross-checked in both
  modes (absent fields → explicit SKIP, never silent): artifact
  `not_done_steps` vs replay-derived list, `state_hash` vs replay
  hash, `executed_calls` vs gold calls — any mismatch fails.
  `replay_ok`/`hash_match` keep their narrow meanings (replay ran;
  hash matched) and can never rescue a failed verdict. An explicit
  future-observation check (canonical result JSON of a later step
  in an earlier prompt → `future_observation`) sits alongside the
  rebuilt-prompt equality check. Training-mode CLI without
  `--manifest` now exits 2 with a clear error instead of silently
  skipping membership checks.

## 2. Files changed and interface changes

Ownership held: Thread A touched only builder tokenization +
tokenization tests/notes; Thread B touched only validator +
validator tests/notes. Verified: `test_sft_prototype.py` local hash
`c47b22c9…` equals its branch SHA — UNCHANGED, excluded from the
push.

- `analysis/overnight_capability_audit/sft_prototype_builder.py`
  (A): tokenization path replaced — `batch_tokenize` /
  `attach_token_data` now render via the real chat template
  (single user message, `add_generation_prompt=True`,
  `tokenize=True`); per-step artifact fields added/changed (below);
  budget uses rendered lengths + 512 reserve; EOS inside a target
  is a token error (caller drops the example, never builds a
  duplicated EOS); raw-encode helper deleted (no fallback).
- `analysis/overnight_capability_audit/sft_prototype_validator.py`
  (B): rebuilt-prompt verification from runtime functions;
  manifest/part/mode checks; outcome classifier + metadata
  cross-checks; future-observation check; independent token
  verification (validator's own `apply_chat_template` code — it
  does NOT import any builder token helper); CLI gains `--manifest`
  (required in training mode), `--part`, `--mode
  training|evaluation` (default training), `--runtime-dir`;
  summary gains `anomalies`. `validate_steps`,
  `parse_model_output`, `token_f1`, `compact` behavior unchanged
  (old tests import them and still pass untouched).
- `analysis/overnight_capability_audit/test_tokenization_regressions.py`
  (A, new, 10 tests), `tokenization_fix_notes.md` (A, new).
- `analysis/overnight_capability_audit/test_validator_regressions.py`
  (B, new, 27 tests), `validator_fix_notes.md` (B, new).
- `research/lifemate/sft_prototype_fix_report.md` (coordinator, this
  report).

**Artifact interface (binding, both sides agree):** each step now
carries `rendered_prompt` (str), `rendered_prompt_token_ids`,
`target_token_ids`, `input_ids` (= rendered + target + [eos]),
`labels` ([-100]*len(rendered) + target + [eos]), `eos_token_id`
(151645), `sequence_tokens` (= len(input_ids)),
`full_conversation_match`/`full_conversation_extra` (diagnostic).
**Breaking change: `prompt_token_ids` now MEANS rendered prompt
ids** (the old raw meaning is deleted). Token fields absent
(legacy artifact) → validator token checks report SKIPPED with a
reason and other checks decide the verdict; token fields present
but inconsistent (including mixed rendered/raw steps) → fail
`token_fields_inconsistent`. Validator function
`validate_example` gains `manifest`, `part`, `mode`,
`runtime_dir`, `catalog`, `contract_name`, `tokenizer_python`,
`token_batch` parameters (exact names in `validator_fix_notes.md`).

## 3. Test results, revisions, repro commands

Counts are reported per suite and per backend with pass/fail/error/
skip kept separate. "Skipped" is never counted as passed.

| Suite | System python3 | Venv python |
|---|---|---|
| `test_sft_prototype.py` (old, untouched) | 20 pass / 0 fail / 0 error / 0 skip | 20 pass / 0 fail / 0 error / 0 skip |
| `test_tokenization_regressions.py` (A, new) | 6 pass / 0 fail / 0 error / 2 skipped (class-level skips covering the 4 tokenizer-dependent tests; no transformers under system python) | 10 pass / 0 fail / 0 error / 0 skip |
| `test_validator_regressions.py` (B, new) | 27 pass / 0 fail / 0 error / 0 skip | 27 pass / 0 fail / 0 error / 0 skip |

Coverage of the mandatory regressions: tokenization (a) raw≠runtime
with exactly the 8 missing tokens, (b) role-marker/generation-prefix
tamper fails even when the step is internally self-consistent, (c)
EOS missing/extra and off-by-one mask in both directions fail, (d)
budget boundary with template overhead (raw-fits-but-rendered-
exceeds fails, exact boundary passes), (e) builder ids match runtime
via TWO independent paths (direct worktree `llm._render` import and
direct `apply_chat_template` in the test, neither via the builder
helper); validator Bug 2 (a)–(e) including forged empty-stop 0019,
transcript/history/catalog/suffix tampers, sample_id/part swaps,
future-observation insertion, and valid-artifact pass; validator
Bug 3 (a) done:false fails, (b) ok:false via classifier units,
(c) forged `not_done_steps=[]` still fails (replay + metadata
mismatch), (d) hash-match-but-failed fails, (e) successful
read/write/ask/empty pass (0003/0116/0036).

Revisions: runtime worktree a2e832b (agent commit a2e832b,
contract `a2e832b-text` provisional, unchanged); tokenizer
Qwen/Qwen3-4B-Instruct-2507 rev cdbee75, transformers 5.21.0, via
`~/workspace/zaic-test-venv/bin/python` only (`local_files_only=
True`, HF cache local; system python3 has no transformers, so token
correctness is established under venv python only).

Repro commands (from `~/workspace/zalo-aic-round3/`, CPU only):
```
# suites
python3 analysis/overnight_capability_audit/test_sft_prototype.py
python3 analysis/overnight_capability_audit/test_tokenization_regressions.py
python3 analysis/overnight_capability_audit/test_validator_regressions.py
~/workspace/zaic-test-venv/bin/python analysis/overnight_capability_audit/test_tokenization_regressions.py
~/workspace/zaic-test-venv/bin/python analysis/overnight_capability_audit/test_validator_regressions.py
# regenerate (official artifact; LOCAL ONLY, never pushed)
python3 analysis/overnight_capability_audit/sft_prototype_builder.py \
  --train-jsonl ~/workspace/zaic-data/lifemate/extracted/train+public_test/train/train.jsonl \
  --data-root ~/workspace/zaic-data/lifemate/extracted/train+public_test \
  --manifest analysis/overnight_capability_audit/inner_split_seed1337_v2.json \
  --part inner_train --manifest-version v2 --select-coverage --per-class 2 \
  --tokenizer-python ~/workspace/zaic-test-venv/bin/python \
  --out analysis/overnight_capability_audit/sft_prototype_local.json
# independent validate (training mode, manifest enforced)
python3 analysis/overnight_capability_audit/sft_prototype_validator.py \
  --output analysis/overnight_capability_audit/sft_prototype_local.json \
  --train-jsonl ~/workspace/zaic-data/lifemate/extracted/train+public_test/train/train.jsonl \
  --data-root ~/workspace/zaic-data/lifemate/extracted/train+public_test \
  --catalog ~/workspace/zaic-data/lifemate/extracted/train+public_test/train/train_tools_catalog.json \
  --manifest analysis/overnight_capability_audit/inner_split_seed1337_v2.json \
  --part inner_train --tokenizer-python ~/workspace/zaic-test-venv/bin/python
```

## 4. Prototype regenerate + independent validator run (new artifact)

Regenerate (fixed builder, manifest v2, coverage, per-class 2):
selected 16, built 16, dropped 0, steps 38, scanned eligible 865,
excluded ineligible `[train_1696]` — same 16 ids as before (targets
and prompt texts byte-identical to the old artifact on all 38
steps; only token ids/labels changed).
Independent validator run on the new artifact (training mode,
manifest v2, part inner_train, tokenizer via venv):
**n_examples 16, passed 16, failed 0, hash_match 16, anomalies [],
token status enforced 16/16 (not skipped), token verdicts 16/16
pass, total trained tokens 636.** The old validator CLI invocation
without `--manifest`/`--part` no longer validates in training mode
(exit 2) — rerun commands must include them (see §3).
Migration check: the OLD raw-token artifact under the NEW validator
(training mode, manifest v2) still passes 16/16 with token status
SKIPPED 16/16 (legacy tolerance working as designed) — it is NOT a
token-correctness pass for that artifact.

## 5. Token counts / budget / mask — corrected numbers

| Quantity | Old (raw-encode, SUPERSEDED — do not quote) | New (rendered, correct) |
|---|---|---|
| Template overhead per step | 0 (missing) | +8 tokens every step |
| Max prompt tokens (prototype set) | 8594 | **8602** |
| Max sequence tokens | 8600 | **8608** |
| Trained tokens (targets + EOS, 38 steps) | 636 | **636 (unchanged — targets and EOS unchanged)** |
| Budget check | raw prompt + 512 ≤ 16384 | rendered prompt + 512 ≤ 16384 AND sequence ≤ 16384; headroom on worst step 8602 + 512 = 9114 ≤ 16384; 0 over-budget |
| Labels | [-100]*len(raw) + target + [eos] — WRONG span (missing 8 template tokens; prompt span misaligned, generation prefix untracked) | [-100]*len(rendered) + target + [eos] — prompt fully masked including generation prefix, target fully trained, exactly one EOS |

Impact note: no training ever ran on the old labels, so the old
numbers' impact is prototype-only — but any training run that had
used them would have trained on misaligned spans. Per-example
trained tokens are unchanged from the previous round (0036: 6,
0057: 6, 0116: 23, 0219: 23, 0048: 37, 0245: 37, 0003: 112, 0004: 43,
0011: 101, 0014: 63, 0690: 44, 0789: 30, 0451: 30, 0502: 27, 0063:
31, 0095: 23; sum 636).

## 6. Remaining limits and verdict

- **CPU prototype VERIFIED** for the three audited bugs and all
  listed regressions, on the regenerated artifact, with independent
  (non-shared-helper) token verification and rebuilt-prompt +
  replay-outcome verification.
- **NOT ready-to-train.** Still open, unchanged by this round:
  derived-checkpoint eligibility Q-L2 (draft questions exist,
  never sent — user approval required before sending); zero-shot
  benchmark base selection (base stays PROVISIONAL
  Qwen3-4B-Instruct-2507); official evaluator absent (all scores
  are the engineering proxy); fill-act rule manual agreement audit
  (20 cases, ≥80%) still pending before any decision verdict uses
  fill-act; guard shadow on prototype trajectories still not run
  (validator deliberately does not import the guard); guard tension
  on the 3 message-history trajectories (1005/1033/1319) still
  unresolved (guard evolution vs search-first teaching); repr-
  string history still not demonstrated by any gold prototype
  example (synthetic conformance only — the prototype set is
  unchanged, so this gap carries over); A30 latency and train
  cost/memory still NOT_MEASURED.
- **Honest limitations of this round's tests:** ok:false
  end-to-end via real replay is NOT achievable from gold calls
  (gold all validate; no ok:false gold trajectory exists in dev)
  — covered by classifier unit tests + the 1696 not_done
  end-to-end, not by an invented e2e case. Token correctness is
  established under venv python only (system python has no
  transformers; its token tests SKIP by design). The validator's
  token reference is runtime `llm._render`; proving that reference
  equals the full training serialization was Thread A's scope and
  is documented in §1 (concat = generation-time ids).
- **Push:** this report + the 6 thread files go to the SAME branch
  `sft-prototype-v2` (no merge to main). `sft_prototype_local.json`
  (regenerated, full prompt texts) stays LOCAL ONLY and is never
  pushed, nor are audio, environments, weights, or full datasets.
  Commit + remote blob-SHA verification are recorded in the
  handover reply (verified before delivery, not claimed in advance).
