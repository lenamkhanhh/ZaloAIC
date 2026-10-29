# Thread A — Tokenization fix notes (sft-prototype-v2 follow-up)

Scope: builder tokenization ONLY. No change to replay, classification,
prompt-text rendering, targets, seed, split membership, fuzzy
threshold, baseline config, inference, simulator, scorer, guard.
Contract kept: provisional `a2e832b-text` (no contract re-selection
in this round). No training, no GPU, no held-out, no git.

## 1. Repro BEFORE the fix (real output, venv python)

Source prompts: `sft_prototype_local.json` (v2 artifact, read-only
reference) step 0 of train_0003 (normal, 6 steps) and train_0036
(empty-stop). Tokenizer: Qwen/Qwen3-4B-Instruct-2507 rev cdbee75,
transformers 5.21.0, `local_files_only=True`.

```
train_0003 step 0 | target='{"name":"bill_payment.list_bills","arguments":{}}'
  old prompt_tokens=7282 target_tokens=13 sequence=7296
  raw len=7282 | rendered(tokenize=True) len=7290
  runtime _render+encode(no-sp) len=7290 | encode(sp) len=7290
  delta rendered-raw = 8
  rendered==runtime(no-sp): True | _render text==template text: True
  old artifact prompt_token_ids == raw encode: True
  old artifact prompt_token_ids == rendered: False
train_0036 step 0 | target='{"stop":true}'
  old prompt_tokens=6232 target_tokens=5 sequence=6238
  raw len=6232 | rendered len=6240 | delta = 8
  old artifact prompt_token_ids == raw encode: True (== rendered: False)
```

Missing tokens (identical on both steps): head
`[151644 <|im_start|>, 872 'user', 198 '\n']` and tail
`[151645 <|im_end|>, 198 '\n', 151644 <|im_start|>, 77091 'assistant',
198 '\n']` — 3 + 5 = 8 tokens. The rendered text is
`<|im_start|>user\n{base_prompt}<|im_end|>\n<|im_start|>assistant\n`.
Old training input was `raw_prompt_ids + target_ids + [EOS]`: the
model never saw the role markers or the assistant generation prefix
during training, yet sees all 8 at inference — a train/serve
mismatch concentrated exactly on the tokens that condition the first
target token.

## 2. Runtime behavior actually read (no guessing)

- `~/workspace/zaic-branch-a2e832b/lifemate/llm.py`, `_render`
  (lines 33–44): `messages = [{"role": "user", "content": prompt}]`;
  `text = tokenizer.apply_chat_template(messages, tokenize=False,
  add_generation_prompt=True)`; `size =
  len(tokenizer.encode(text, add_special_tokens=False))`; if
  `size + max_tokens > max_context_tokens` raise
  `ContextBudgetExceeded` (no silent truncation); returns `text`.
- `TransformersGenerator.__call__` (lines 143–147): `ids =
  tokenizer(text, return_tensors="pt", add_special_tokens=False)` on
  the `_render` text; generation is greedy, `max_new_tokens=512`.
  `VLLMGenerator.__call__` (lines 98–100) generates from the same
  `_render` text. Both backends therefore consume the RENDERED text.
- `llm.py` module docstring: stop = the chat template's stop token
  or a `{"stop": true}` JSON object. EOS `<|im_end|>` = 151645,
  pad `<|endoftext|>` = 151643 (measured from the tokenizer).
- `config.py` (lines 37, 40, 61–62): `llm_max_context_tokens =
  16384`, `llm_max_new_tokens = 512`, context must be ≤ 16384.
- `agent.py`: `build_base_prompt` (line 92),
  `render_observation_prompt` (line 73), `AgentLoop` (line 128).
  Base prompt TEXT is unchanged by this fix; only text→ids changed.
- Measured equivalence (this tokenizer, this template):
  `apply_chat_template(tokenize=True)` ids ==
  `encode(rendered_text, add_special_tokens=False)` ==
  `encode(rendered_text, add_special_tokens=True)` (Qwen adds no BOS).
  There is no conflict between the task's `tokenize=True`
  prescription and the runtime path: they coincide exactly.
  transformers 5.21.0 note: `apply_chat_template(tokenize=True)`
  returns a BatchEncoding, not a list — the helper extracts
  `["input_ids"]` and accepts both shapes.

## 3. Root cause

The old `TOKENIZER_HELPER` encoded each text independently with
`tok.encode(text, add_special_tokens=False)`. Applied to the raw
base prompt, that skips the chat template entirely. The validator
reused the builder's helper, so builder and validator agreed with
each other while both disagreed with runtime by exactly the 8
template-wrapper tokens on every step. The old `prompt_tokens`,
`sequence_tokens`, and budget verdicts were all computed on raw
lengths and are superseded (§6).

## 4. Fix (builder tokenization part only)

- New `TOKENIZER_HELPER`: per (prompt, target) pair it returns
  `rendered_prompt` (template text), `rendered_prompt_token_ids`
  (template, `tokenize=True`), `runtime_input_ids` (encode of the
  rendered text, no special tokens), `target_token_ids`, and
  `full_conversation_token_ids` (diagnostic only). `attach_token_data`
  RAISES (refuses to build) if template ids != runtime ids.
- Per-step training construction (teacher forcing, generation-time
  ids are ground truth):
  `input_ids = rendered_prompt_ids + target_ids + [EOS]`,
  `labels = [-100]*len(rendered_prompt_ids) + target_ids + [EOS]`.
  Invariants asserted per step: prompt segment fully masked, target
  segment exactly the target ids, exactly one EOS at the end,
  labels/input lengths equal. EOS inside target ids → token error →
  caller drops the example with reason `token_error` (never builds
  a duplicated-EOS example).
- Budget on RENDERED length: step passes iff
  `len(rendered_prompt_ids) + 512 ≤ 16384` AND
  `len(input_ids) ≤ 16384`; otherwise DROP + log, never truncate.
- Old raw-encode helper is DELETED. `batch_tokenize` now takes
  (prompt, target) pairs (a flat [prompt, target, ...] list is
  paired positionally, which is exactly the old unit-test call
  shape). Its flat `"ids"` output now holds
  `[rendered_prompt_ids, target_ids, ...]` with the NEW semantics,
  so the pre-existing unit test keeps unpacking correctly.
  `attach_token_data` still accepts a legacy flat-`"ids"` shape
  ONLY for the pre-existing synthetic budget unit test, which feeds
  fake ids and checks budget logic, not tokenization; `main()`
  never builds that shape, so it is not a production raw-encode
  fallback.
- CONTRACT dict gained a `"tokenization"` entry documenting the
  change inside the artifact itself.

## 5. Concat vs full-conversation tokenize (diagnostic, decided)

Measured on both repro steps: full-conversation tokenize
`[user, assistant(target)]` equals concat PLUS one trailing token
`[198 '\n']` (the template's newline after the final `<|im_end|>`).
Concat is correct and full-text is the approximation: at inference
the model generates target tokens and then EOS, and generation stops
— the trailing newline after EOS is never generated and never
appears in any model input. Training on full-text ids would teach an
extra token after EOS. The builder therefore keeps concat, and each
step records `full_conversation_match` (bool) and
`full_conversation_extra` (expected `[198]`) as diagnostics.

## 6. Interface change (binding for Thread B's validator)

Per step in builder output (in addition to unchanged `prompt`
base text and `target` JSON text):

| Field | Meaning (new) |
|---|---|
| `rendered_prompt` (str) | chat-template output text |
| `rendered_prompt_token_ids` (list[int]) | template ids (= runtime ids, asserted) |
| `prompt_token_ids` (list[int]) | **BREAKING: now rendered ids** (old raw meaning deleted) |
| `prompt_tokens` (int) | len(rendered ids) |
| `target_token_ids` (list[int]) | encode(target, no special tokens) |
| `target_tokens` (int) | len(target ids) |
| `input_ids` (list[int]) | rendered + target + [151645] |
| `labels` (list[int]) | [-100]*len(rendered) + target + [151645] |
| `eos_token_id` (int) | 151645 |
| `sequence_tokens` (int) | len(input_ids) |
| `full_conversation_match` / `full_conversation_extra` | concat-vs-full diagnostic |
| `token_budget_over_steps` / `budget_status` | unchanged shape, rendered-based values |
| `token_errors` (per example) | e.g. `eos_in_target`; caller drops the example |

Without `--tokenizer-python`, token fields are absent and
`budget_status` is `"unchecked"` as before (validator must SKIP
token checks with a stated reason, never pass them).

## 7. Corrected numbers (old numbers superseded)

Regeneration (fixed builder, same 16 samples / 38 steps / 0 dropped,
same per-class ids, scanned eligible 865, excluded `[train_1696]`;
output written to /tmp/a_prototype_regen.json — the reference
`sft_prototype_local.json` was NOT overwritten):

- Template overhead: exactly **+8 tokens on every one of the 38
  steps** (3 head + 5 tail wrapper tokens; content-independent).
- Trained tokens: **636 unchanged** (targets + EOS per step; target
  texts and target ids are unchanged — only prompt ids changed).
  Per-step prompt/target texts verified byte-identical to the old
  artifact for all 38 steps.
- **Max rendered prompt: 8602 (old raw number 8594 is superseded).**
- **Max sequence: 8608 (old raw number 8600 is superseded).**
- Budget headroom: max rendered prompt + 512 = 9114 ≤ 16384; all
  steps pass budget; 0 over-budget.
- Every regenerated step re-verified in the regen script:
  `prompt_token_ids == rendered_prompt_token_ids`,
  `labels == [-100]*len(rendered) + target + [151645]`,
  `input_ids == rendered + target + [151645]`.

## 8. Test results (separate pass/fail/error/skip, no merging)

New file: `test_tokenization_regressions.py` (10 tests).

- Venv python (`~/workspace/zaic-test-venv/bin/python`):
  **10 passed, 0 failed, 0 errors, 0 skipped.** Covers: (a) raw
  differs from runtime with exactly the 8 missing tokens named;
  (b) dropped role marker and altered generation prefix rejected
  even when the tampered step is internally consistent (template
  marker constants checked: head `[151644, 872, 198]`, tail
  `[151645, 198, 151644, 77091, 198]`); (c) EOS missing/extra and
  mask shifted by one in both directions rejected; EOS inside
  target surfaced as token error; (d) raw-fits-but-rendered-fails
  budget case fails while the exact-boundary case passes;
  (e) builder ids equal runtime ids via BOTH independent paths
  (worktree `llm._render` import + direct `apply_chat_template`
  in the test, never the builder helper); concat-vs-full diagnostic.
- System python3: **6 passed, 0 failed, 0 errors, 4 tokenizer tests
  skipped** (reported by unittest as 2 class-level skips: the
  tokenizer test classes). Skips are skips, not passes, and the
  file says so. Pure-logic tests (verification rejections, fake-id
  budget/error paths) pass on both backends.
- Pre-existing suite `test_sft_prototype.py` (NOT modified):
  **20 passed, 0 failed, 0 errors, 0 skipped on BOTH backends**
  after the fix (flat `"ids"` compat + legacy fake-id attach branch
  kept it green; its token-span test now exercises the new
  rendered semantics).

## 9. Revisions and repro commands

- Tokenizer: Qwen/Qwen3-4B-Instruct-2507, revision cdbee75,
  transformers 5.21.0, `local_files_only=True`, HF cache local.
  Runtime: worktree `~/workspace/zaic-branch-a2e832b/lifemate/`,
  agent commit a2e832b, contract `a2e832b-text` (provisional,
  unchanged by this fix). EOS 151645, max_context 16384,
  max_new_tokens (reserve) 512.
- Repro (before-fix numbers in §1):
  `~/workspace/zaic-test-venv/bin/python /tmp/repro_tokenization.py`
  (scratch script; its output is quoted in §1).
- New tests:
  `~/workspace/zaic-test-venv/bin/python analysis/overnight_capability_audit/test_tokenization_regressions.py`
  (expect 10 passed, 0 skipped);
  `python3 analysis/overnight_capability_audit/test_tokenization_regressions.py`
  (expect 6 passed, tokenizer tests skipped).
- Regeneration (coordinator to rerun on the frozen snapshot into
  the real local artifact path; Thread A wrote only /tmp):
  ```
  python3 analysis/overnight_capability_audit/sft_prototype_builder.py \
    --train-jsonl ~/workspace/zaic-data/lifemate/extracted/train+public_test/train/train.jsonl \
    --data-root ~/workspace/zaic-data/lifemate/extracted/train+public_test \
    --manifest analysis/overnight_capability_audit/inner_split_seed1337_v2.json \
    --part inner_train --manifest-version v2 --select-coverage --per-class 2 \
    --tokenizer-python ~/workspace/zaic-test-venv/bin/python \
    --out <coordinator-chosen local path, NEVER pushed>
  # expect: selected 16, built 16, dropped 0, steps 38, scanned 865
  ```

## 10. Remaining limits / BLOCKED / SKIPPED (honest list)

- System-python runs SKIP tokenizer tests by design (no
  transformers there); token correctness is established only under
  the venv python. No token check is ever reported as pass without
  the real tokenizer.
- The regenerated artifact in /tmp is Thread A's verification copy
  only; the coordinator must regenerate the canonical local
  artifact and run Thread B's independent validator on it.
- This fix covers builder tokenization only. Artifact-trust issues
  (forged base prompt, not-done calls) are Thread B's validator
  scope and are NOT fixed here; Thread A changed no validator code.
- No statement of "ready to train" is made: Q-L2 (derived
  checkpoint eligibility) and zero-shot benchmark base selection
  remain open, per the parent task.
