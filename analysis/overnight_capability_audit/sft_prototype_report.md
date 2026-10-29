# Thread B report — Runtime pin + SFT prototype (CPU only)

Status: DELIVERED for coordinator review. This report does NOT declare
"ready to train" — that decision is the coordinator's, after the v2
manifest rerun (see §8).

## 1. Runtime comparison (evidence table)

Sources: a2e832b worktree `~/workspace/zaic-branch-a2e832b/lifemate/`
(read-only); `analysis/runtime/E1_DEPLOYMENT_BRIEF_2026-10-28.md` §§2–3
(V10 native M1–M8); `analysis/runtime/E1_V10_INTENT_ANALYSIS_2026-10-28.md`
(V10 results); `analysis/runtime/SOTA_ANALYSIS_ALL_ERRORS_2026-10-28.md`
(V11/E6-C); `analysis/runtime/E5_V13_DEEP_ANALYSIS_AND_NEXT_STEP_2026-10-28.md`
(pseudo-call boundary). Trace files `/tmp/t2_v10_trace.json`,
`/tmp/t2_v11_trace.json` are GONE (checked 2026-10-29, /tmp cycle) — the
trace portion below is therefore UNVERIFIED and rests on reports only.
Nothing in this table comes from a trace file.

| Dimension | a2e832b text contract (reference runtime) | V10 native contract (Codex opt-in, NOT in a2e832b worktree) | V11 / E6-C (V10 + parser-side catch) |
|---|---|---|---|
| Messages | Single user message: `messages = [{"role": "user", "content": prompt}]`, rendered by `tokenizer.apply_chat_template(..., add_generation_prompt=True)` (`llm.py:_render`). No tool role. | `[system_msg, user_msg] + [assistant(tool_call), tool(result)] × calls` (E1 M1). Generator protocol changes `gen(prompt, tools)` → `gen(messages, tools)` — mandatory interface change. | Same as V10 (no message change reported). |
| Tools | Prose tool list inside the prompt: one JSON line per tool sorted by name, `{name, kind, description, parameters, returns}`, only the sample's installed tools + `sys.ask_missing_info` (`loader.catalog_tools_for_sample`). | Function definitions `{"type": "function", "function": {name, description, parameters}}`; DROP kind/returns/app; STRIP all `x-*` keys (108 params carry `x-ref`/`x-match` internal metadata) before giving them to the model (E1 M2). | Same as V10. |
| Observation | Text appended to the prompt: `render_observation_prompt` — lines `- <name>(<args-as-Python-repr>) -> <outcome>; output=<compact JSON>`, outcome `not_done` / `ok` / `error: <error>`; replan appends `\nChoose a different, evidence-backed action or stop.` | Message sequence: `assistant(tool_calls=[call])` then `tool(content=<full compact result JSON>)`; `not_done` stays inside the JSON, not an interpretive word; replan line becomes a user message (E1 M5). | Same as V10. |
| Parser | `llm.parse_model_output`: strip, optional ```json fence, `json.loads`, dict required; garbage → ValueError → wrapper converts to `{"name": "__invalid__", "arguments": {}}`, loop rejects via validation, never silently repairs. | Native parser (E1 M6): extract `<tool_call>…</tool_call>` by DOTALL regex; ≥1 block → parse FIRST block only, require name string + arguments object (string arguments tried once via `json.loads`); extra blocks counted in `multi_block_turns`, not executed. 0 blocks → three distinct cases, never merged into stop: (a) bare `{"stop": true}` / `{"name": "stop"}` w/o arguments → STOP; (b) bare JSON object naming a tool → FORMAT ERROR (validation_rejected path), NOT executed, NOT stop; (c) plain text non-JSON → STOP (text-only = completion). Broken block JSON → validation_rejected, no auto-repair. | V11 adds a parser-side pseudo-call catch with NARROW scope: only the registered lowercase `app.tool(` prefix. Caught pseudo-call generations 0 → 2, silent pseudo-call stops 1 → 0 (channel scope only, NOT ask recovery). key=value pseudo-calls are a separate REPORTING category (narrow pattern), parser UNCHANGED in E7 by preregistered rule. |
| Stop / EOS | `is_stop_signal`: `stop is True` OR (`name == "stop"` and no arguments) → generator returns None. `{"stop": true}` is the stop target. No explicit EOS token id in the text path (framework default). | Explicit stop: vLLM `stop_token_ids=[151645]`; Transformers `eos_token_id=151645` explicitly; do NOT rely on framework defaults (snapshot has no `generation_config.json`) (E1 M7). Legacy `is_stop_signal` used only in Arm A; Arm B stop = no block. | Same as V10. |
| Retry / loop guard | Up to 3 attempts per step (1 generation + up to 2 validation retries); validation failure becomes an observation for the next generation (FAILED call appended, marked "validation failed (NOT executed, NOT submitted)"), never a submitted call. `LoopGuard(max_repeats=2)`: a call executed 2× is never executed again (pre-block); first trigger replans once, second trigger stops the trace as-is. `max_steps` 12. | Unchanged guard/completion by design (E1 exclusion P4: max_repeats/guard/completion belong to E4, not E1). Validation-retry line rewritten for native ("Your last output was not a valid `<tool_call>` block…"). | Same as V10; retry elaborates instead of fixing (V11 retry adds a `phone_number` param into the wrong pseudo-call instead of switching to a tagged call — recovery failure L9). |
| Grounding | `ground_arguments` runs BEFORE `env.validate` when `config.grounding` is true (grounding errors become a validation-style failure, not an executed call). `configs/baseline.json` (grounding=false) vs `recommended.json` (grounding=true) are otherwise IDENTICAL (selective_reads=true, verification_read_after_write=false, max_steps 12, max_repeats 2, Qwen3-4B-Instruct-2507 rev cdbee75, vllm, temp 0.0, seed 42, max_context 16384, max_new_tokens 512, total 4.244B, llm 4.0B, PhoWhisper-small). Base prompt TEXT is identical under both configs — only the grounding repair step differs at inference. | Grounding stays ON in both E1 arms by design (E1 exclusion P5; E0 proved it blocks invented IDs; turning it off would confound). | Same as V10. |

### V10 results (small-sample diagnostics, NOT a benchmark)

Proxy 0.125 → 0.1875 comes entirely from sample 0004 (0 → 0.5, native
drops an optional arg); prerequisite 5/21 (text) → 4/21 (native) —
DECREASED, so native must never be described as "better at planning".
Sample 0003: ask-as-escape (nested ask, 0 reads). Sample 0016: native
WORSE than text (task-type confusion + ASR echo + invented time).
Sample 0049: better reads, task still wrong (F1 0.5 but score 0, hash
wrong). V10 does NOT separate which contract part caused any effect
(schemas vs roles vs parser move as a bundle). Follow-up arms B-roles /
B-tools were proposed to isolate roles vs schemas but were NOT run in
the first E1 round.

### Runtime benchmark status: UNVERIFIED / PROVISIONAL

No full-dev zero-shot benchmark output artifact exists in this workspace
(searched `analysis/runtime/` and the a2e832b worktree). What exists:
small-sample diagnostics (E0/V10/V11/V13) and mechanics-only
`run.py` subcommands (`replay-gold` diagnostic, `fake-run` empty policy,
never a baseline). The running zero-shot benchmark mentioned in the
follow-up task lives OUTSIDE this workspace (Codex side); its results
are future input for base selection, not present evidence.

## 2. Chosen contract (exactly one) — PROVISIONAL

- **Contract: `a2e832b-text`** — the current text runtime, because the
  SFT pilot runs on the current runtime and the native contract's
  attribution is unresolved (bundle effect, prerequisite decreased).
  Pinned in `sft_prototype_builder.py` CONTRACT: worktree
  `~/workspace/zaic-branch-a2e832b/lifemate/`, agent commit `a2e832b`,
  single user message + prose tool list + text observations,
  parser `llm.parse_model_output`, stop target `{"stop":true}`
  (canonical compact form; the parser is whitespace-insensitive, so
  compact vs spaced changes nothing — a documented choice, not a
  runtime change), EOS `<|im_end|>` id 151645, max_steps 12,
  max_repeats 2, max_context 16384, max_new_tokens 512,
  baseline config `lifemate/configs/baseline.json`,
  transcript_mode `gold`, status PROVISIONAL.
- **Grounding correction vs overnight v1 shorthand:** v1 said
  "grounding stays ON at inference". Precisely: the frozen zero-shot
  baseline cell is `baseline.json` (grounding=false) for clean
  attribution; `recommended.json` (grounding=true) is a SEPARATE
  inference variable to be evaluated separately, NOT baked into
  training targets (targets = gold calls as-is). The base prompt text
  is identical under both configs, so this choice does not change any
  training prompt — only which inference cell the pilot is compared
  against.
- **No "best base" claim:** Qwen3-4B-Instruct-2507 is used ONLY as the
  default `--model`/`--revision` (cdbee75) because it is the current
  runtime's model. It is NOT concluded to be the best base — the
  zero-shot benchmark output is absent (see §1). The builder takes
  `--model` / `--revision` / `--tokenizer-python` as parameters.
- **No inference modification:** the builder/validator only transform
  gold trajectories into training examples + checks. The a2e832b
  worktree and main `lifemate/` code were not modified. No GPU, no
  model inference, no training, no held-out reads, no simulator /
  scorer / guard / config changes.

## 3. Builder / validator design

Files (all under `analysis/overnight_capability_audit/`):
`sft_prototype_builder.py` (29,971 bytes), `sft_prototype_validator.py`
(17,548 bytes), `test_sft_prototype.py` (19,353 bytes),
`sft_prototype_local.json` (LOCAL ONLY, 3,796,252 bytes — full prompt
texts; never push; repro in §8).

### Builder

- Rendering replicates a2e832b `agent.py` exactly: instruction line +
  ACTION_POLICY (6 rules + output line, verbatim) + current-time line +
  `User: <name>, city <city>.` + full context JSON + prose tool list
  (sorted by name, sample's installed tools + ask only) +
  `Conversation history:` (user: `audio_text` or
  `[audio, no transcript available]`; assistant: `text` + `calls=` JSON
  + `results=` Python repr — history tool_results is sometimes a repr
  STRING, never json-parsed blindly) + `Current user request
  (transcript): <audio_text>` + the two baseline suffix lines.
  Observation lines use Python repr for arguments and the
  `not_done`/`ok`/`error:` outcome mapping. No replan line (gold
  trajectories never take the replan path).
- Steps: step t prompt uses ONLY observations of steps < t (step 0
  prompt = base exactly). Each call step target = canonical compact
  JSON `{"name", "arguments"}`. A trailing stop step (target
  `{"stop":true}`, call=None) is appended UNLESS the last call is
  `sys.ask_missing_info` (ask ends the turn) or there are 0 calls
  (then the single step IS the stop step).
- Gold replay: `ToolEnv("train", id, root=data_root)`; every gold call
  is validated BEFORE executing — a validation failure DROPS the
  sample with reason (never executes, never repairs, never includes
  the rejected call as an executed step). The executed list comes
  from the builder's own replay bookkeeping, NOT from
  `get_tool_calls()` (which also contains rejected calls).
- Drops (never repairs): `>12` gold calls (exceeds_max_steps),
  ask-not-last, one identical call >2 times (loop_guard_exceeded;
  exactly 2 repeats are kept), validation failure, token-budget
  exceeded. No silent truncation anywhere.
- Determinism: no randomness anywhere; sorted-id scan order, fixed
  class order, greedy first-unpicked selection. Rebuild to a second
  file is byte-identical (verified, §5).
- CLI: `--train-jsonl`, `--data-root`, `--zaic-tools-dir`,
  `--manifest`, `--part` (default inner_train), `--manifest-version`,
  `--ids-file`, `--select-coverage`, `--per-class` (default 2),
  `--model`, `--revision`, `--tokenizer-python`,
  `--max-context-tokens` (test hook only, default 16384),
  `--out`. Exactly one of `--ids-file` / `--select-coverage` is
  required, else exit 2. `--ids-file` entries outside the manifest
  part ABORT with exit 2 and build nothing.
- Tokenizer: one subprocess (`--tokenizer-python`, the venv python)
  loading `AutoTokenizer` offline (`local_files_only=True`) once for
  all texts (600 s timeout). Without `--tokenizer-python`, examples
  get `budget_status "unchecked"` and the validator MUST re-check
  with a tokenizer; nothing is silently truncated.

### Validator (assertions, not prose)

- Prompt rebuild equality: rebuild the full step list from base +
  calls + results and require prompt AND target string equality
  (not substring).
- Leakage (full JSON strings only, never individual values — a
  person's name legitimately appears in the request): at step t, the
  prompt must NOT contain (a) the compact result JSON of step t or
  any later step, (b) the compact gold final_state JSON (skipped when
  trivial `"{}"`/`"[]"`), (c) the target JSON of step t — with one
  documented exception: the STOP target is exempt, because the
  instruction text itself (instruction line + ACTION_POLICY lines 1
  and 6) contains the exact literal `{"stop":true}`; its presence is
  the format specification, not a leaked answer. This exception was
  found by the validator itself during the smoke test (12 initial
  "failures", all stop steps, all explained by the instruction) and
  is covered by a dedicated test.
- Sequence fidelity (PRIMARY): executed call sequence (excluding the
  stop step) must equal the gold sequence by name + canonical args
  JSON in order; ask, when present, must be the last call; exactly
  one stop step at the end (or absent iff ask-terminated; empty =
  single stop step).
- Argument fidelity: identical arg key sets; exact equality for
  non-fuzzy params; token-F1 > 0.6 for fuzzy params (replicating
  `scoring.py` token_f1: NFC, lowercase, strip non-word chars,
  whitespace tokens; empty/empty → 1.0; threshold source: the
  engineering proxy scorer, NOT the official evaluator).
- Parser round-trip: replicate `llm.parse_model_output` (strip,
  optional fence, JSON object, stop detection); each target must
  parse to the recorded call (call steps) or a stop signal (stop
  steps).
- state_hash is SECONDARY: replayed independently in a fresh ToolEnv
  and reported as `hash_match`, but it never determines the verdict,
  because reads/asks do not change state. The counterexample test
  proves this: a trajectory equal to gold PLUS one extra read fails
  the sequence check while its state hash is unchanged (hash half
  demonstrated on a real ToolEnv, sample train_0003, extra read
  `contacts.search {"query": "ZZZ-no-such-name"}`).
- Guard diagnostic: the validator does NOT import the guard. Guard
  flags, when supplied, are recorded verbatim and a unit test proves
  the verdict is identical with flags True / False / absent. A guard
  fire on a gold trajectory is a guard-false-block DIAGNOSTIC, never
  a data error and never a drop reason. Full guard shadow on
  prototype trajectories is a coordinator step using the Round 3
  audit scripts, not this validator.
- Token spans (only when token data is available): labels are exactly
  `[-100]*len(prompt_ids) + target_ids + [eos_id]`; decode of
  `prompt_ids + target_ids + [eos]` must round-trip to prompt text +
  target text + EOS text; `prompt_tokens + 512 ≤ 16384` and
  `sequence_tokens ≤ 16384`. If token data is unavailable, token
  checks report SKIPPED with a reason and string-boundary checks
  still run. The prefix property (prompt ids + target ids + EOS ==
  encode(prompt + target + EOS)) was verified for the stop target and
  a tool-call target; the validator still asserts it per example
  rather than assuming it.
- Scope limit (stated plainly): replay via `env.call` verifies ONLY
  simulator transitions. It does NOT verify the whole AgentLoop —
  prompt rendering inside the loop, validation retries, loop guard,
  grounding, and in-loop parser behaviour are covered by the
  conformance test + prompt-rebuild check, not by this replay.

## 4. Coverage classes and generic selection rules

Rules are generic (no sample IDs, no answer keys). A class with no
match records `NOT_FOUND` and is never force-fit.

| Class | Rule (as implemented) | Limitation |
|---|---|---|
| empty_stop | 0 gold calls → single stop step | — |
| ask_only | gold_kind == ask_only (calls == [sys.ask_missing_info]) | — |
| read_ask | ≥1 read, no write, last call is ask | — |
| read_write | a write whose `*_id` argument value appears as an `id` field value in an EARLIER READ result (fixed during this session: earlier WRITE results no longer count — a created id is not a read) | Existence only, not entity-choice correctness |
| multi_step | ≥3 gold calls | — |
| conditional_no_write | 0 writes AND ≥1 read AND a conditional marker in the CURRENT request text AND no ask anywhere in gold (markers: nếu, trừ khi, trong trường hợp, chỉ khi, nếu không, khi, if, unless, in case) | Rule CANNOT prove the read result decided the branch — matches are candidates under the rule, not branch-verified |
| direct_phone | phone.call/sms.send with a phone_number argument AND no contacts.search anywhere in gold | — |
| history_dependent | an `*_id` argument value appears in a flattened history assistant tool_result value AND does NOT appear in the current request text (substring check) | Substring check, not semantic inference |

## 5. CPU results — three buckets, never mixed

### (a) Synthetic tests

`test_sft_prototype.py`: **20/20 pass under system python3 AND
20/20 pass under the venv python** (0 skipped, 0 failed). Coverage:
rendering conformance vs real a2e832b `build_base_prompt` /
`render_observation_prompt` (ran, not skipped — worktree import
succeeded); one synthetic test per coverage class; leakage rejection
(future result, own target); prompt-rebuild mismatch rejection;
sequence counterexample (extra read, same hash); ask-not-last;
fuzzy token-F1 boundary (> 0.6 pass, ≤ 0.6 fail); guard-flag-ignored;
token spans (exact label mask, EOS position, decode round-trip,
budget boundary — via the venv-python subprocess); no-silent-
truncation (unit + CLI hook with `--max-context-tokens 100` →
built 0, dropped 1, reason `token_budget_exceeded`); parser round-trip
(plain, fenced, stop, garbage raises); determinism (byte-identical
rebuild); manifest restriction (see below). Fixtures are labelled
synthetic (`synthetic-*`); no synthetic count is mixed into gold
counts. Note: the validator's fuzzy check is scoring.py token-F1,
backend-independent — there is no difflib/RapidFuzz split for these
tests, so no backend split is reported.

### (b) v1 smoke test (FROZEN manifest v1, inner_train 863)

Command (from `~/workspace/zalo-aic-round3/`):
`python3 analysis/overnight_capability_audit/sft_prototype_builder.py
--train-jsonl ~/workspace/zaic-data/lifemate/extracted/train+public_test/train/train.jsonl
--data-root ~/workspace/zaic-data/lifemate/extracted/train+public_test
--manifest analysis/overnight_capability_audit/inner_split_seed1337.json
--part inner_train --manifest-version v1-frozen --select-coverage
--per-class 2 --tokenizer-python ~/workspace/zaic-test-venv/bin/python
--out analysis/overnight_capability_audit/sft_prototype_local.json`

Result: selected 16, built 16, dropped 0, steps 38, scanned part 863.
No class was NOT_FOUND on v1. All 16 ids verified to be in
`inner_train` of the v1 manifest.

| Class | Selected ids (v1) |
|---|---|
| empty_stop | train_0036, train_0057 |
| ask_only | train_0116, train_0219 |
| read_ask | train_0048, train_0245 |
| read_write | train_0003, train_0004 |
| multi_step | train_0011, train_0014 |
| conditional_no_write | train_0690, train_0789 |
| direct_phone | train_0451, train_0502 |
| history_dependent | train_0063, train_0095 |

Per-example token counts (prompt_tokens summed over steps — steps
share prefixes, so this is NOT a training-token total; trained tokens
= target_tokens + 1 EOS per step):

| id | kind | steps | trained tokens | max prompt tokens |
|---|---|---|---|---|
| train_0036 | empty | 1 | 6 | 6232 |
| train_0057 | empty | 1 | 6 | 3732 |
| train_0116 | ask_only | 1 | 23 | 6275 |
| train_0219 | ask_only | 1 | 23 | 5932 |
| train_0048 | ask_after | 2 | 37 | 6437 |
| train_0245 | ask_after | 2 | 37 | 7071 |
| train_0003 | normal | 6 | 112 | 7784 |
| train_0004 | normal | 3 | 43 | 5905 |
| train_0011 | normal | 5 | 101 | 8594 |
| train_0014 | normal | 4 | 63 | 5837 |
| train_0690 | normal | 2 | 44 | 4271 |
| train_0789 | normal | 2 | 30 | 5765 |
| train_0451 | normal | 2 | 30 | 4436 |
| train_0502 | normal | 2 | 27 | 3980 |
| train_0063 | normal | 2 | 31 | 7096 |
| train_0095 | normal | 2 | 23 | 6894 |

Totals: 636 trained tokens (targets + EOS), max sequence 8600 tokens,
max prompt 8594 tokens — all within budget (prompt + 512 ≤ 16384,
sequence ≤ 16384), 0 over-budget, 0 not_done steps in the selected
set (no selected gold step returned ok=True/done=False).
Validator on the smoke output (with `--tokenizer-python`):
**16/16 pass, hash_match 16/16 (secondary), token spans 16/16 pass.**
Self-found issue during this run (fixed, not hidden): the first
validator run flagged 12 "leakage:target" failures — all were stop
steps, all explained by the instruction containing the stop literal
(see §3 exception). After the fix, the validator passes 16/16 and the
unit test suite covers the exception explicitly.
Additional CLI checks: `--ids-file` with 2 valid inner_train ids →
built 2; `--ids-file` with an inner_val id (train_0007) → exit 2, no
file built; determinism re-run → byte-identical output file.

### (c) v2 results — PENDING (coordinator rerun)

The final prototype samples MUST come from Thread A's revised manifest
v2, not from v1. This bucket is empty by design. See §8 for the exact
rerun commands.

## 6. Evidence ledger (frozen snapshot actually read)

- a2e832b worktree (read-only): `lifemate/agent.py` (AgentLoop.run,
  build_base_prompt, render_observation_prompt, LoopGuard),
  `llm.py` (_render, parse_model_output, is_stop_signal),
  `loader.py` (Sample/Turn, label_class, catalog_tools_for_sample,
  history repr-string warning), `run.py` (replay-gold, fake-run,
  check-submission, score, make-split, infer), `config.py`,
  `scoring.py` (state-hash-gated tool F1, token_f1, fuzzy x-match),
  `configs/baseline.json` + `recommended.json` (identical except
  grounding), `grounding.py` header, `adapter.py` function list.
- Reports: `analysis/runtime/E1_DEPLOYMENT_BRIEF_2026-10-28.md` §§2–3,
  `E1_V10_INTENT_ANALYSIS_2026-10-28.md`,
  `E5_V13_DEEP_ANALYSIS_AND_NEXT_STEP_2026-10-28.md`,
  `SOTA_ANALYSIS_ALL_ERRORS_2026-10-28.md`,
  `research/lifemate/overnight_capability_decision.md` (v1),
  `analysis/overnight_capability_audit/inner_split_seed1337.json`
  (v1: population 1233 after quarantine of train_1696/1005/1033/1319
  before splitting, seed 1337, 863/185/185 — this file ALREADY
  embodies the main-synthesis amendment; it is NOT Thread C's
  original 866/185/186 proposal over 1237).
- Data: `train/train.jsonl` (1545 samples), `train_tools_catalog.json`
  (147 tools: write 84, read 62, meta 1), split map
  `lifemate/splits/train_dev_heldout.json` (dev 1237 / held-out 308,
  seed 42). Held-out content was NOT read; the builder only selected
  from the manifest part passed in (inner_train).
- Tokenizer: `~/workspace/zaic-test-venv/bin/python`, transformers
  5.21.0, no torch; Qwen/Qwen3-4B-Instruct-2507 rev cdbee75 from local
  HF cache, `local_files_only=True`; EOS `<|im_end|>` 151645, pad
  `<|endoftext|>` 151643. System python3 has NO transformers — the
  `--tokenizer-python` subprocess path is mandatory, not optional.
- ToolEnv: verified `validate` enforces installed-apps membership
  (train_0019 contacts.search rejected with "không thuộc app đã
  cài"), rejected calls DO appear in `get_tool_calls()` (hence the
  builder's own bookkeeping rule), `get_state_hash()` returns hex.

## 7. Unknowns / blockers (Thread B cannot resolve alone)

1. v2 manifest does not exist yet (Thread A, parallel) — final
   prototype membership is pending (§8).
2. Zero-shot benchmark output is absent from the workspace — contract
   choice is PROVISIONAL and no base ranking is claimed (§1–§2).
3. Tokenizer exists only in the venv, not system python — tests and
   validator must always pass `--tokenizer-python` explicitly.
4. Official evaluator absent — all scores are the engineering proxy;
   the fuzzy threshold 0.6, ask scoring, and read-call scoring are
   proxy conventions, unverified against the official evaluator.
5. faster-whisper `hotwords` presence unverified (carried from the
   overnight audit, not Thread B's to resolve).
6. History-as-text vs history-as-real-turns is a P2 follow-up (E1),
   not part of this contract — the prototype trains the text-history
   rendering the current runtime actually uses.
7. Guard shadow on prototype trajectories was not run by this thread
   (validator deliberately does not import the guard) — coordinator
   step using Round 3 audit scripts.
8. The conditional_no_write rule is a candidate rule, not a
   branch-verified rule (§4); the two v1 matches (train_0690,
   train_0789) are matches under that rule, not proof that the read
   result decided the branch.

## 8. Coordinator rerun (v2) — exact commands

From `~/workspace/zalo-aic-round3/`:
```
python3 analysis/overnight_capability_audit/sft_prototype_builder.py \
  --train-jsonl ~/workspace/zaic-data/lifemate/extracted/train+public_test/train/train.jsonl \
  --data-root ~/workspace/zaic-data/lifemate/extracted/train+public_test \
  --manifest <V2_MANIFEST_PATH> --part inner_train --manifest-version v2 \
  --select-coverage --per-class 2 \
  --tokenizer-python ~/workspace/zaic-test-venv/bin/python \
  --out analysis/overnight_capability_audit/sft_prototype_local.json
python3 analysis/overnight_capability_audit/sft_prototype_validator.py \
  --output analysis/overnight_capability_audit/sft_prototype_local.json \
  --train-jsonl ~/workspace/zaic-data/lifemate/extracted/train+public_test/train/train.jsonl \
  --data-root ~/workspace/zaic-data/lifemate/extracted/train+public_test \
  --catalog ~/workspace/zaic-data/lifemate/extracted/train+public_test/train/train_tools_catalog.json \
  --tokenizer-python ~/workspace/zaic-test-venv/bin/python
```
Expected: per-class ids (or NOT_FOUND per class, never force-fit),
built/dropped counts with reasons, validator pass/fail per example,
token-span verdicts. The v1 ids in §5 are a smoke test only and must
NOT be carried forward as the final prototype. `sft_prototype_local.json`
is LOCAL ONLY and must not be pushed; the builder, validator, tests,
and this report are the pushable Thread B artifacts.
