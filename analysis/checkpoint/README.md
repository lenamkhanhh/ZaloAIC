# Phase 2 — Checkpoint interface (LifeMate only)

**Scope label, read first:** everything in this directory is
CPU / mock tested only. There is **no real checkpoint** here, **no
model score**, **no GPU run**, and **no runtime claim**. The G&G
observer stays shadow-only; nothing here changes agent behaviour,
scoring, or any file outside `analysis/checkpoint/` in this worktree.
A fine-tune friend's weights are never edited, never committed, and
never submitted from here.

## What this is for

One JSON config swaps ASR **or** LLM independently, without editing
`lifemate/agent.py` (or any file in `lifemate/`) for each new
checkpoint. The loader in this directory maps the config onto the
ASR/LLM objects `lifemate` already provides, through their real
constructors. Anything those constructors cannot express is a named
GAP (see below), never a silent drop and never a hack in `lifemate/`.

## Files

| File | What it is |
|---|---|
| `checkpoint_config_schema.json` | The single config schema: one `asr` section + one `llm` section. |
| `example_baseline.json` | Baseline instantiation, equivalent to `lifemate/configs/recommended.json` (PhoWhisper-small + Qwen3-4B-Instruct-2507 rev `cdbee75`, greedy, seed 42, context 16384). |
| `loader.py` | Config validation, constructor mapping, `build_asr` / `build_llm`, `pipeline_overlay`, and `transcribe_safe` with the error contract. Stdlib only at import; weights load only inside the real constructors, on the GPU host. |
| `manifest_schema.json` | Manifest schema for ONE checkpoint (ASR or LLM, never a pair). |
| `manifest_asr_example.json`, `manifest_llm_example.json` | Schema examples ONLY (`status: "example-only"`). Preflight refuses them. They are not checkpoints. |
| `preflight.py` | Read-only preflight: USABLE / MISSING / UNVERIFIED / OVER_BUDGET / INVALID. Never loads weights, never measures runtime. |
| `test_checkpoint_interface.py` | 32 stdlib unittest tests, CPU only, mocks in-file. Run: `python3 -m unittest discover -s analysis/checkpoint -p 'test_*.py' -v` from the repo root. |

## How to swap a checkpoint (the intended flow)

1. Write one checkpoint config (schema v1) with the new `asr`
   and/or `llm` section. Changing `asr` leaves the `llm` section
   canonically identical, and vice versa — proven by
   `loader.swap_report` and by the overlay tests.
2. Run preflight on each new checkpoint directory (see below).
   Do not proceed on a MISSING / UNVERIFIED / OVER_BUDGET verdict
   by assuming the missing value.
3. On the GPU host, build with `loader.build_asr` /
   `loader.build_llm` (strict mode refuses GAPs) and run the
   existing `AgentLoop` unchanged. The loop's prompt template,
   tool catalog, and scoring are untouched by the swap; the tests
   prove the loader-layer equivalents (config section identity,
   overlay field identity, transcript identity, sample order).

**Caller GAP (outside this directory's ownership, not fixed here):**
`lifemate/run.py::cmd_infer` currently hardcodes
`FasterWhisperASR(checkpoint, device="cuda", compute_type="float16")`
and `VLLMGenerator(checkpoint, revision, seed)` and ignores the
`PipelineConfig` backend fields (`asr_backend`, `asr_language`,
`asr_greedy`, `llm_backend`, `llm_temperature`, `llm_max_context_tokens`).
So today a checkpoint-config swap does **not** take effect through
`run.py infer` until its caller is switched to `loader.build_*` /
`pipeline_overlay`. That caller change belongs to the coordinator /
run owner, not to this directory, and is listed as BLOCKED item B-CALLER
in the report. Do not work around it by editing `run.py` from here.

## ASR contract (documentation + code, both must agree)

- **Input audio (real loader format):** WAV, 16 kHz, mono, 16-bit
  (`lifemate/loader.py` docstring, checked on real files with stdlib
  `wave`). `loader.transcribe_safe` verifies exactly this header
  with stdlib `wave` before calling the backend.
- **Other sample rates / formats:** in strict mode (the default)
  they are a **failed record** (`error: "unsupported_audio_format"`),
  not silently resampled by this layer. Rationale: the checkpoint
  contract is only guaranteed for the loader format, and a silent
  resample would hide a data-format mismatch from the benchmark.
  (The raw `FasterWhisperASR.transcribe` path in `run.py` does not
  go through this check; that path is unchanged.)
- **Output transcript:** a string, Vietnamese diacritics preserved.
  This layer never lowercases, never strips diacritics, never
  normalises digits, and never edits the backend's text (the real
  backend already strips surrounding whitespace only).
- **Sample-ID order preserved:** one record per input sample, in
  input order, always. `loader.check_order_preserved` raises on any
  reorder / drop / duplicate. A shuffling mock is caught by test
  (`test_broken_order_is_caught`).
- **Decode configuration (baseline):** backend `faster-whisper`,
  greedy (`beam_size=1`), `language="vi"`. Hotwords /
  `initial_prompt` are **not** in the baseline and cannot be
  expressed today (GAP A3 below) — contextual decoding (P1) stays a
  proposal until a constructor parameter exists.
- **Error / missing audio:** a missing file, an unreadable WAV, a
  backend exception, or an **empty transcript** all produce
  `status="failed"`, `transcript=None`, and a named `error`. An
  empty string is never fed to the prompt as if the user said
  nothing. A failed sample keeps its position in the record list;
  downstream code must decide explicitly (exclude the sample with
  a logged reason, or fail the run) — it must not silently skip it
  and shift the order.
- **What the constructor actually takes:**
  `FasterWhisperASR(checkpoint, device="cuda", compute_type="float16")`
  and `transcribe(wav_path)` hardcodes `language="vi"`,
  `beam_size=1`. That is the whole ASR surface today.

## LLM contract (documentation + code, both must agree)

- **Base model (baseline):** `Qwen/Qwen3-4B-Instruct-2507`,
  revision `cdbee75` (from `recommended.json`).
- **Adapter vs merged vs full — three different loads:**
  - `full`: weights as stored, loaded as the checkpoint.
  - `merged`: a fine-tune already merged into full weights; loads
    exactly like `full`. The merge must have happened **before**
    delivery — this loader never merges.
  - `adapter`: a PEFT/LoRA adapter directory. **Not loadable today**
    (GAP L1): neither generator takes a base model + adapter path.
    An adapter-only delivery is BLOCKED until it is merged by the
    supplier or the constructors gain those parameters.
- **Tokenizer / chat template:** always the checkpoint's own.
  Both generators call `AutoTokenizer.from_pretrained(checkpoint)`
  and `apply_chat_template(..., add_generation_prompt=True)`.
  A separate `tokenizer_source` / `chat_template_source` that
  differs from `checkpoint` is a GAP (L2), not a quiet override.
  The template version is whatever the checkpoint directory
  contains; record it in the manifest (source + revision), do not
  assume it matches the baseline template.
- **Prompt / tool format (agent's format, unchanged):** exactly one
  JSON object per turn, `{"name": "<tool>", "arguments": {...}}`
  or `{"stop": true}` (see `lifemate/agent.py::build_base_prompt`
  and `lifemate/llm.py::parse_model_output`). Fenced JSON is
  accepted by the parser; non-object / unparseable output becomes
  `{"name": "__invalid__", "arguments": {}}` for the loop's
  validation path — never silently repaired into a guessed call.
  Stop is the chat template's stop token **or** `{"stop": true}`.
- **Stop tokens:** no custom stop list exists (GAP L4). If a
  fine-tune needs a custom stop string, that is a constructor GAP
  to report, not a config value to invent.
- **Context:** at most **16384** tokens
  (`llm_max_context_tokens`, `recommended.json`). The loader
  validates `<= 16384` and rejects more. But neither generator
  takes a context parameter or truncates: an over-long prompt
  fails inside the backend, not here (warning, GAP L5 note).
- **Decoding (baseline, from `recommended.json`):** greedy,
  temperature `0.0`, seed `42`. vLLM hardcodes
  `SamplingParams(temperature=0.0, seed, max_tokens)`; transformers
  hardcodes `do_sample=False`, `max_new_tokens=512`. Any other
  temperature is a GAP (L3); any other `max_tokens` for the
  transformers kind is a GAP (L6).
- **Load paths:** vLLM primary
  (`VLLMGenerator(checkpoint, revision, seed, max_tokens)`),
  transformers fallback
  (`TransformersGenerator(checkpoint, revision, device)`).
  The fallback has no seed and no `max_tokens` parameter — a
  config that needs those on the fallback path is a GAP, and the
  two backends are therefore **not** interchangeable for every
  config. Record which backend a run used; do not report a
  transformers run as a vLLM run.
- **What the constructors actually take** is exactly the signatures
  above. There is no dtype / quantisation / device parameter on
  the vLLM generator and no context / stop / adapter parameter on
  either.

## Manifest (one per checkpoint)

Schema: `manifest_schema.json`. A manifest states: kind, load_kind
(LLM), source label, revision, `files_required` (literal relative
paths), `file_sha256` (sha256 **of each named file as stored** —
never of a folder), training data, licence, release date, declared
parameters, max context (LLM), status.

**Hard rule:** training lineage is never inferred from a folder
name, a model id, or a config value. If the supplier did not state
it, `training_data` is exactly `"UNKNOWN"`. The same applies to
licence and release date when not stated for that exact revision.
Both examples therefore say `training_data: "UNKNOWN"` even though
their shapes resemble known baseline models — resemblance is not
lineage, and the examples are `example-only` anyway.

A pair (ASR + LLM) is two manifests plus one checkpoint config.
Preflight is run per checkpoint; the pair budget is checked by
passing each checkpoint's verified parameter count as the other's
companion (see preflight usage).

## Preflight (read-only)

```bash
python3 analysis/checkpoint/preflight.py \
  --manifest /path/to/manifest.json \
  --checkpoint-dir /path/to/checkpoint \
  [--companion-params-b 0.244] [--out /path/to/report.json]
```

- Exit `0` only for `USABLE`; `2` otherwise.
- `USABLE` means: all `files_required` present and non-empty,
  tokenizer present, `config.json` parses with a model identity,
  all declared hashes match, this checkpoint's own budget lines
  verified and within limits (LLM < 5B; context ≤ 16384), and
  parameters verified from the artifact.
- `MISSING` lists the exact relative paths absent/empty.
- `UNVERIFIED` means files are complete but a needed value cannot
  be verified from the artifact (no computable parameter count,
  no context value, adapter without its base). It is not a pass.
- `OVER_BUDGET` means a verified value breaks a limit.
- `INVALID` means manifest / config / hash problems (including
  `example-only` manifests and hash mismatches).
- **Runtime is always `unverified`** in preflight. No
  seconds/sample is ever inferred from a CPU run, a mock, or a
  different GPU. A 30 s/sample claim needs a real GPU run.
- **A single-checkpoint USABLE is not a system-budget pass.**
  The report's `budget.pair_total_verified` is false until a
  companion value is supplied; run preflight on both checkpoints
  and cross-pass the verified counts before declaring the pair
  under 6B total.

## GAP table (constructor / parameter that is missing)

| ID | Gap | Where it bites |
|---|---|---|
| A1 | No transformers ASR class in `lifemate/asr.py` | A fine-tune delivered in transformers format cannot be loaded by `FasterWhisperASR` (RUN_LIFEMATE §5 already records this failure mode for the baseline weights: no CTranslate2 `model.bin`). Supplier must deliver a CTranslate2-converted directory, or an ASR class must be added by the lifemate owner. |
| A2 | `FasterWhisperASR` has no `revision` parameter | An HF-id ASR pin cannot be enforced; use a local directory as the pin. |
| A3 | No `language` / `beam_size` / `hotwords` / `initial_prompt` parameters (`transcribe()` hardcodes `vi` / beam 1 / neither) | Non-`vi`, non-greedy, or contextual decoding cannot be expressed. |
| L1 | No LLM constructor takes `base_model` + `adapter_path` | Adapter-only LLM delivery is unbuildable; supplier must merge, or constructors must gain those parameters. |
| L2 | No separate tokenizer / chat-template source parameter | Both generators use the checkpoint's own tokenizer/template only. |
| L3 | No `temperature` parameter (vLLM hardcodes 0.0; transformers hardcodes greedy) | Any non-greedy decoding cannot be expressed. |
| L4 | No custom stop-token parameter | Custom stop strings cannot be expressed. |
| L5 | No `max_context_tokens` parameter on either generator | The 16384 cap is validated by the loader / `PipelineConfig`, but no generator truncates or rejects over-long prompts itself. |
| L6 | `TransformersGenerator` has no `max_tokens` / `seed` parameter (hardcodes 512 / greedy) | Fallback backend cannot express a different output budget. |
| C1 | Caller: `lifemate/run.py::cmd_infer` hardcodes faster-whisper + vLLM and ignores backend fields | A checkpoint-config swap has no effect through `run.py infer` until the caller uses `loader.build_*` / `pipeline_overlay` (coordinator / run owner). |

## What is BLOCKED, and exactly what unlocks it

- **B-REAL-CHECKPOINT:** no real fine-tuned checkpoint has been
  delivered to this worktree. Unlock: for each checkpoint, a local
  directory + a `candidate` manifest (see manifest schema) stating
  source, revision/hash, `files_required`, per-file sha256,
  `training_data` (or `"UNKNOWN"`), licence/release date (or
  `"UNKNOWN"`), and `load_kind`. For an adapter LLM: the merged
  directory instead, or the base model identity + adapter files
  with an explicit statement of how they are to be loaded.
- **B-ASR-FORMAT:** if the ASR fine-tune is transformers-format,
  it is unusable through the current ASR constructor (GAP A1).
  Unlock: a CTranslate2-converted directory (with `model.bin`,
  config, and tokenizer files) from the supplier, or a new ASR
  class from the lifemate owner.
- **B-CALLER:** `run.py infer` does not use this loader yet (GAP
  C1). Unlock: a caller change by the run owner to build through
  `loader.build_*`; this directory must not make that edit itself
  under its file ownership.
- **B-GPU:** no GPU run, no seconds/sample, no WER, no task score
  exists for any new checkpoint. Unlock: a GPU host with the
  backends installed (RUN_LIFEMATE §3) plus data (the Tier 1a
  blockers B1/B2 still apply to any real run). Held-out data is
  never used for any checkpoint choice.
- **B-PARAMS:** a checkpoint whose `config.json` carries no
  explicit `num_parameters` and is not a complete Qwen2/Qwen3
  config with explicit `tie_word_embeddings` will preflight as
  UNVERIFIED on parameters. Unlock: the supplier states the
  parameter count with its derivation, or ships a config from
  which it is computable — not a folder-name inference.

## What was NOT done here

No training, no weight editing, no submission, no contact with the
organisers, no held-out use, no merge, no push, no edit to
`lifemate/` or `analysis/tier1a/`, no real checkpoint, no model
result, no claim of any score, WER, or timing. The 32 tests are
mock / CPU tests of this interface only.
