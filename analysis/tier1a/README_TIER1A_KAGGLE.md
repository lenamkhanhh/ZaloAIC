# Tier 1a on Kaggle — B0 vs B-gold (LifeMate only)

Packaging of the Tier 1a benchmark (design: `next-step/stream-C.md`;
execution report: `next-step/tier1a/TIER1A-EXECUTION_REPORT.md`, verdict
BLOCKED, no model run) into a reproducible Kaggle notebook. This
directory is the only new content on branch `muse/chat3/tier1a-kaggle`.
No file under `lifemate/` was touched, nothing was merged, nothing
was pushed by this packaging step, and no GPU run, training,
submission, or model result exists from this work.

## Phase 1 fix — 2026-10-31 (CPU only, no GPU run, no model result)

Owner work on branch `muse/chat3/p1-tier1a-fix` (parent `1691cf6b`,
the tier1a-kaggle tip; not pushed, not merged). Only
`analysis/tier1a/` changed; `lifemate/` is untouched. What changed:

- **faster-whisper cannot load the pinned ASR checkpoint directly.**
  `vinai/PhoWhisper-small` is transformers-format (no `model.bin`
  for CTranslate2), so `WhisperModel("vinai/PhoWhisper-small")`
  fails — the same failure recorded in `RUN_LIFEMATE.md` section 5
  with faster-whisper 1.2.1, corroborated by faster-whisper's
  CTranslate2 requirement (converted directories contain
  `model.bin` + `config.json` + tokenizer/vocabulary) and by the
  existence of third-party CTranslate2 conversions of this exact
  checkpoint. The runner now checks ASR model files **before any
  weight is loaded** (`check-asr-model`, also run by the notebook
  preflight cell) and stops with the conversion command when the
  direct load is impossible. Two supported paths: (a) convert once
  with the pinned command below and pass the converted directory
  with `--asr-model-dir`, or (b) use the transformers backend
  (`--asr-backend transformers`, same checkpoint, greedy,
  language `vi`, via `AutoModelForSpeechSeq2Seq` in the runner —
  not in `lifemate/`). The selected backend is recorded as
  `asr_backend_actual` in the config snapshot and per-mode run
  manifests; it never silently replaces the pinned config.
  Conversion command (record the actual installed versions after
  running it; only faster-whisper is version-pinned here because
  it is the version recorded in `RUN_LIFEMATE.md` section 5):

  ```bash
  pip install "faster-whisper==1.2.1" ctranslate2 "transformers[torch]"
  ct2-transformers-converter --model vinai/PhoWhisper-small \
      --output_dir /kaggle/working/PhoWhisper-small-ct2 \
      --copy_files tokenizer.json preprocessor_config.json \
      --quantization float16
  # Verify the converted directory (also what check-asr-model does):
  #   model.bin + config.json + a tokenizer/vocabulary file must exist.
  #   preprocessor_config.json presence is reported, not hard-required.
  ```

  On the first GPU run, the conversion itself is a first-run item:
  it has not been executed here (CPU-only VM, no torch), so the
  converted directory's transcription equivalence with the
  transformers backend is still unverified and must be checked on
  the pilot 20 before the full set is trusted.

- **Completeness gate (mandatory).** `score` now refuses to compute
  any total unless both arms cover exactly the manifest ids (no
  missing, no duplicate, no extra, same id set, no run error, no
  arm mismatch) and the OFF-vs-ON pilot is 20 samples and
  identical. A partial run exits 2 with status `INCOMPLETE` and
  the missing list in `completeness_gate.json`, and no
  `score_report.json` is written. Each run mode writes its own
  `run_manifest_<mode>.json` with `COMPLETE`/`INCOMPLETE` status;
  a mid-run crash leaves partial traces plus an `INCOMPLETE`
  manifest, and score refuses them.
- **Resume.** `run --resume` reuses a previous trace only when its
  stored input hash matches the input hash recomputed for this run
  (sample, mode, wav sha, current + history transcripts, config,
  checkpoint/backend, LLM checkpoint/revision). Changed inputs,
  errored traces, and a missing run-manifest sidecar are re-run.
  The notebook run cells use `--resume`; OFF-vs-ON runs are always
  fresh (never resumed).
- **Notebook dependencies.** The notebook now has 10 cells: the new
  dependency cell (cell 2) checks package versions from metadata
  before, installs only the missing backends, and re-checks after,
  writing `dependency_report.json`. Only faster-whisper is
  version-pinned in that install (`==1.2.1`); vllm / transformers /
  accelerate / ctranslate2 have no version pin recorded in the repo,
  so they are installed unpinned and their installed versions are
  recorded — never invented. If the install still leaves a backend
  missing, the cell raises `BLOCKED` with the exact manual pip
  command instead of starting a partial run.
- **Tests.** `test_tier1a_p1.py` (stdlib unittest, CPU only, 29
  tests): completeness gate (missing / duplicate / extra / arm
  mismatch / run error / OFF-vs-ON not identical / missing /
  short pilot / pilot-vs-full), provisional and held-out manifest
  rejection, ASR file checks (mock CT2 and transformers dirs),
  pinned faster-whisper block, resume decisions, score refusal
  without any total, and run/score separation still passing.

## Purpose

On one frozen stratified dev set, run the same samples and the same
LLM twice — once with the baseline ASR transcript as the current-turn
input (B0), once with the gold transcript as the current-turn input
(B-gold, a real `AgentLoop.run()`, never replay-gold) — and measure
how much task error is ASR-propagated versus pure LLM/agent error.
History is fixed in both modes (gold transcript if present, else the
shared baseline-ASR cache); only the current turn varies. G&G is
shadow-only throughout: observer ON to log, never to block.
`pending_ask_stop` stays False, history V2 stays off.

## Source pin (checked fail-fast, before any weight loads)

| Item | Pinned value |
|---|---|
| Branch | `muse/chat3/p1-tier1a-fix` (Phase 1 work; parent `muse/chat3/tier1a-kaggle` at `1691cf6b`) |
| `lifemate/` tree | CPU pin `ddbe0a0b18a6fb9f6e7d261628a51e7a2c6c10c6`; `git diff ddbe0a0 HEAD -- lifemate/` must be empty |
| Config | `lifemate/configs/recommended.json`, sha256 `71d5f38f23d126427b08c09925cbbd9da933fc3750cbec55942809737e980076` |
| Split | `lifemate/splits/train_dev_heldout.json`, sha256 `eefd0faa163285b23d2634bc4cc04f515b58367a2344599e46e85d48818280aa`, dev 1237 / held-out 308 |
| LLM | `Qwen/Qwen3-4B-Instruct-2507`, rev `cdbee75`, temp 0.0, seed 42, context 16384, `max_steps` 12, `max_repeats` 2, grounding on |
| ASR | `vinai/PhoWhisper-small`, faster-whisper, greedy beam 1, language `vi` |
| Budget | Total 4.244B / LLM 4.0B, under the organiser limits 6B / 5B |

If any of these checks fails, the notebook and the runner stop.
Do not work around a mismatch by editing a hash in this directory.

## Files in this directory

| File | What it is |
|---|---|
| `tier1a_kaggle.ipynb` | The Kaggle notebook, 10 cells, runnable top to bottom (see below). Valid JSON, checked with `python -m json.tool` / `json.load`, and every code cell parses. |
| `tier1a_runner.py` | Packaged runner: `smoke`, `check-separation`, `validate-manifest`, `check-asr-model`, `asr-cache`, `run`, `check-off-on`, `score` (plus `analyze` as a score alias). Paths via flags, else `TIER1A_*` env, else Kaggle defaults. ASR backend via `--asr-backend` / `TIER1A_ASR_BACKEND` and `--asr-model-dir` / `TIER1A_ASR_MODEL_DIR`; `run` accepts `--resume`; `score` accepts `--pilot` and `--off-on`. |
| `test_tier1a_p1.py` | Phase 1 unit tests (stdlib unittest, CPU only, 29 tests). See the Phase 1 section above. |
| `metrics.py` | Frozen metrics, copied verbatim from the Tier 1a executor's runner: WER normalisation (lowercase, strip punctuation, collapse whitespace, **keep Vietnamese diacritics**, digit strings as single tokens), S/D/I/N, slot error for `[0-9]+`, propagation, attribution, paired bootstrap CI (10,000 resamples, seed 20261030). |
| `refreeze.py` | Stratified refreeze (stdlib only, no torch/vllm needed). See "Manifest" below. |
| `manifest_schema.json` | Schema example ONLY: empty id list, status `schema-example-only`. It is never accepted as a run manifest and contains no real sample ids. |
| `README_TIER1A_KAGGLE.md` | This file. |

## Notebook cells (in order)

0. Purpose, source pin, provisional-set warning, run/score separation,
   private-output note, Phase 1 ASR note.
1. **Preflight (fail-fast, before weights):** clone the branch if
   needed; config/split SHAs and fields; git `lifemate/` vs ddbe0a0;
   split counts; `check-separation`; input size (wav count + bytes);
   data-root candidate hint when `train.jsonl` is missing; ASR
   model file check (`check-asr-model`) for the selected backend.
   Writes `tier1a-output/preflight_report.json`.
2. **Dependencies (check-before, install-if-missing, re-check):**
   package versions from metadata only; installs only missing
   backends (faster-whisper pinned `==1.2.1`, others unpinned and
   recorded); raises `BLOCKED` with the manual pip command if a
   backend is still missing. No weights are loaded here.
   Writes `tier1a-output/dependency_report.json`.
3. **Refreeze:** if a frozen manifest already exists in
   `/kaggle/working`, skip with a log; otherwise run `refreeze.py`,
   then validate the manifest (status, ids sha, all-dev, no
   held-out, stratum minimum 20). Writes `manifest_gate.json`.
   Still before weights.
4. **ASR cache:** transcribe each wav exactly once for the baseline
   checkpoint, with the selected backend. Gold transcripts never
   enter the cache.
5. **Run B0 (`--resume`).** Writes `traces_B0.jsonl` and
   `run_manifest_B0.json`; the cell asserts that manifest is
   `COMPLETE` before continuing.
6. **Run B-gold (`--resume`).** Writes `traces_B-gold.jsonl` and
   `run_manifest_B-gold.json`; same `COMPLETE` assertion.
7. **OFF-vs-ON check:** pilot 20, condition B0, observer OFF then ON;
   submission lines must be identical, otherwise the notebook stops
   and the main traces are invalid.
8. **Score (score phase only):** the runner's completeness gate
   runs first (both arms exactly the manifest ids, OFF-vs-ON pilot
   20 identical); on `INCOMPLETE` it writes
   `completeness_gate.json` and no total is printed. On `COMPLETE`
   it reads run traces from disk first, then gold calls; writes
   scored traces + `score_report.json` with WER, slot error,
   attribution, paired bootstrap CI, raw and dev-reweighted means,
   and the pre-registered decision.
9. **List artifacts** under `/kaggle/working` only.

## Kaggle run commands (step by step)

Prerequisites, before cell 4: a Kaggle notebook with GPU enabled,
plus permission to load the two pinned weights. The dependency cell
(cell 2) installs missing backends itself (check-before, install,
re-check); if that install fails, it raises `BLOCKED` with the exact
manual pip command instead of starting a partial run (see
`RUN_LIFEMATE.md` §3 in the repo for the install). Set `TIER1A_DATA`
to the extracted `train+public_test` root (the directory containing
`train/train.jsonl` and the wav files — not the zip, not a parent of
the extracted folder) before running cell 1. Choose the ASR path
before cell 1 as well: either set `TIER1A_ASR_MODEL_DIR` to a
converted CTranslate2 directory (see the Phase 1 section above), or
set `TIER1A_ASR_BACKEND=transformers`. With neither, the preflight
cell stops at the ASR check for the pinned faster-whisper load.

On Kaggle, run the notebook cells top to bottom. The equivalent CLI
flow on any GPU host (same commands the notebook runs) is:

```bash
# 0. Clone this branch (or use the repo root you already have)
git clone -b muse/chat3/tier1a-kaggle https://github.com/lenamkhanhh/ZaloAIC.git
cd ZaloAIC
export TIER1A_SOURCE_TREE="$PWD"
export TIER1A_DATA="/path/to/extracted/train+public_test"
export TIER1A_WORKING="/kaggle/working"   # or any working dir
R=analysis/tier1a/tier1a_runner.py
OUT="$TIER1A_WORKING/tier1a-output"

# 1. CPU-only checks (no weights, no data needed except the repo tree)
python3 $R check-separation
python3 $R smoke --source-tree "$TIER1A_SOURCE_TREE" \
  --benchmark analysis/tier1a/manifest_schema.json --out /tmp/tier1a-smoke
# ASR file check (stdlib, no weights; add --asr-model-dir for a
# converted directory, or --asr-backend transformers for the fallback)
python3 $R check-asr-model --asr-backend "${TIER1A_ASR_BACKEND:-faster-whisper}" \
  ${TIER1A_ASR_MODEL_DIR:+--asr-model-dir "$TIER1A_ASR_MODEL_DIR"}

# 2. Refreeze from real data (stdlib only), then gate it
python3 analysis/tier1a/refreeze.py --data "$TIER1A_DATA" \
  --source-tree "$TIER1A_SOURCE_TREE" \
  --out "$TIER1A_WORKING/benchmark-stratified-frozen.json"
python3 $R validate-manifest --source-tree "$TIER1A_SOURCE_TREE" \
  --benchmark "$TIER1A_WORKING/benchmark-stratified-frozen.json"

# 3. ASR cache (first weight load: ASR only)
python3 $R asr-cache --source-tree "$TIER1A_SOURCE_TREE" --data "$TIER1A_DATA" \
  --benchmark "$TIER1A_WORKING/benchmark-stratified-frozen.json" --out "$OUT"

# 4-5. Runs (no score is computed here; --resume reuses only
# input-hash-identical traces)
python3 $R run --source-tree "$TIER1A_SOURCE_TREE" --data "$TIER1A_DATA" \
  --benchmark "$TIER1A_WORKING/benchmark-stratified-frozen.json" --mode B0 --out "$OUT" --resume
python3 $R run --source-tree "$TIER1A_SOURCE_TREE" --data "$TIER1A_DATA" \
  --benchmark "$TIER1A_WORKING/benchmark-stratified-frozen.json" --mode B-gold --out "$OUT" --resume

# 6. OFF-vs-ON (must be identical, or do not score)
python3 $R check-off-on --source-tree "$TIER1A_SOURCE_TREE" --data "$TIER1A_DATA" \
  --benchmark "$TIER1A_WORKING/benchmark-stratified-frozen.json" --out "$OUT/off_on"

# 7. Score (first and only place gold calls are read; the
# completeness gate runs first and refuses partial runs)
python3 $R score --traces "$OUT" --source-tree "$TIER1A_SOURCE_TREE" \
  --data "$TIER1A_DATA" \
  --benchmark "$TIER1A_WORKING/benchmark-stratified-frozen.json" --out "$OUT"
```

Environment variables (all optional; flags override them):
`TIER1A_SOURCE_TREE` (default `/kaggle/working/ZaloAIC`),
`TIER1A_DATA` (default `/kaggle/input`),
`TIER1A_WORKING` (default `/kaggle/working`),
`TIER1A_BENCHMARK` (default `$TIER1A_WORKING/benchmark-stratified-frozen.json`),
`TIER1A_REPO_URL`, `TIER1A_BRANCH`,
`TIER1A_ASR_BACKEND` (default `faster-whisper`; `transformers` is
the Phase 1 fallback for the pinned checkpoint),
`TIER1A_ASR_MODEL_DIR` (local converted CT2 directory for
faster-whisper, or transformers directory for transformers).

## Manifest (stratified freeze, no held-out, no provisional ids)

`refreeze.py` selects from dev only, stratifies by label class
(empty / ask_only / ask_after / normal, exactly as
`lifemate/loader.py` computes it), orders within each stratum by
`sha256("20261030:<id>")`, allocates proportionally with a minimum
of 20 per stratum (remainder by largest remainder, top-up from the
largest stratum only through that allocation rule), excludes
outcome-blind cases before any model output (missing wav, missing
current-turn gold transcript, missing history wav — replaced by the
next sample in the same stratum, logged), and tops up coverage by
swap (preserving n and stratum counts) to at least 30 samples with a
digit string in the gold transcript and at least 30 with a gold
`contacts.search` call. If dev cannot supply a coverage threshold,
the shortfall is recorded in `coverage_shortfall`, never hidden by
lowering the threshold. Run order is the global hash order of the
selected ids; pilot 20 is the first 20 ids of the manifest.

The manifest stores ids + counts only — no transcript, no gold call,
no wav. Its `ids_sha256` is recomputed by the runner and the notebook
on every use. The provisional hash-only 200-id set is NOT in this
branch, is not quoted here, and is refused by the manifest gate
(wrong status) even if someone points the runner at it.

Refreeze is the only pre-run script that reads gold tool calls, and
only to stratify and check coverage. It never builds agent input.

## Run / score separation (enforced, not just documented)

- Run phase (`run`, `asr-cache`, `check-off-on`, the tracing
  wrapper, the ASR cache) never reads a sample's gold calls, never
  computes a score, never writes a score. `check-separation` proves
  this by parsing `tier1a_runner.py`'s AST and failing if any
  gold-access pattern appears in a run-path function. The notebook
  runs it in preflight, before weights.
- Score phase (`score`) reads run traces from disk first, then gold
  calls, and writes scored copies (`scored_traces_*.jsonl`) plus
  `score_report.json`. It never runs the agent.
- B-gold's only gold input is the gold transcript (`audio_text`) as
  the current-turn input to a real `AgentLoop.run()`. Gold calls are
  never input, never history, and never replayed into a submission.

## Trace contents (per sample-run, run phase)

One JSON line per sample-run in `traces_<mode>.jsonl`, with:
`sample_id`, `split` ("dev"), `arm`, `input_mode`,
`transcript_current`, `transcript_gold_current`,
`transcript_source_history` (per history turn: gold / baseline_asr /
missing), `wav_path`, `wav_sha256`, `prompt_sha256`, `prompt_full`
(pilot runs only; the full prompt sequence is in `generations`),
`generations`, `tool_calls`, `state_hash`, `observer_log`
(shadow-only, from `loop.observer.records`), `seconds`,
`n_generations`, `run_error`.

Each generation records: `prompt`, `raw_output`,
`raw_output_reason`, `raw_output_token_count`,
`prompt_token_count`, `token_count_reason`, `parsed_call`, `error`,
`seconds`, `observation_following`, `observation_kind`.

**Raw output, honestly.** The original runner could not capture raw
model text because `VLLMGenerator` parses internally and returns only
a dict. This packaged wrapper fixes that at the wrapper layer,
without editing `lifemate/`: for the vLLM backend it shims the inner
LLM's `generate()` and records the raw text (and token ids) before
parsing; for the transformers backend it captures generated token ids
and decodes the suffix after the templated prompt. If neither path is
available, `raw_output` is `null` with an explicit reason — raw text
is never reconstructed from the parsed call and never invented.
Token counts come from the generator's tokenizer when available
(prompt tokens = templated prompt tokens, the form the backend
generates from); otherwise they are `null` with a reason.
Observations are derived from the prompt sequence: the loop renders
each observation into the next prompt, so the suffix of the next
prompt after the base prompt is the observation (or validation /
replan message) fed back. The loop does not expose its results list,
and this runner does not reimplement the loop to pretend otherwise.
`error` marks invalid JSON outputs (`__invalid__`) and validation
failures that were not executed.

**One correction vs the original runner:** the observer log is read
from `loop.observer.records`, the real `ShadowObserver` attribute.
The original runner read `.log`, which does not exist on that object
and always yielded `[]`. This changes no library behaviour — it only
records the log that was already being computed.

## Decision rules (pre-registered, stream-C §8)

For the B-gold vs B0 pair, on paired samples with a bootstrap CI
(10,000 resamples, seed 20261030, 2.5–97.5 percentiles):

- **direction_concluded:** paired diff ≥ 0.05 AND CI excludes 0.
- **not_separable:** diff < 0.02 OR wrong-both share > 0.50 of all
  wrong samples in the pair.
- Otherwise **inconclusive**.

A 2-point diff is never called a win. Scores here are official-style
via `lifemate/scoring.py` on dev, never a BTC score. Both raw means
on the benchmark set and dev-reweighted means (by stratum proportions
from the frozen manifest) are reported, with breakdowns by label
class, by digit-containing samples, and by gold `contacts.search`
samples.

## Output artifacts (all under `/kaggle/working`, never in the repo)

- `tier1a-output/preflight_report.json` — preflight (before weights)
- `tier1a-output/dependency_report.json` — dependency check/install (before weights)
- `tier1a-output/manifest_gate.json` — manifest gate (before weights)
- `benchmark-stratified-frozen.json` (+ `.sha256` sidecar) — frozen
  manifest, in the working dir, not the repo
- `tier1a-output/config_snapshot.json` — config actually used
  (recommended + `shadow_observer: true` only)
- `tier1a-output/run_manifest_B0.json`, `run_manifest_B-gold.json`
- `tier1a-output/excluded.json` — outcome-blind exclusions
- `tier1a-output/asr_cache_baseline.json`, `asr_cache_log.json`
- `tier1a-output/model_load.json`
- `tier1a-output/traces_B0.jsonl`, `traces_B-gold.jsonl` — run traces
- `tier1a-output/off_on/off_on_report.json` (+ pilot traces)
- `tier1a-output/completeness_gate.json` — score gate (COMPLETE or INCOMPLETE)
- `tier1a-output/scored_traces_B0.jsonl`, `scored_traces_B-gold.jsonl`
- `tier1a-output/score_report.json` (written only when the gate is COMPLETE)

Sensitive outputs (data, transcripts, traces) live only in the
private Kaggle working output. They are not written to the repo and
must not be committed to GitHub.

## Blockers remaining (nothing in this package removes them)

- **B1 — data:** an extracted `train+public_test/` root with
  `train/train.jsonl` + wav files, pointed to by `TIER1A_DATA`.
  Without it, preflight fails fast at the input check.
- **B2 — GPU + backends:** a GPU host with torch + vllm +
  faster-whisper (+ transformers) installed and permission to load
  `Qwen/Qwen3-4B-Instruct-2507` rev `cdbee75` and
  `vinai/PhoWhisper-small`. Without it, `asr-cache`/`run` exit 2
  with a BLOCKED message and produce no number. For ASR, first
  decide the Phase 1 path: a converted CTranslate2 directory
  (conversion + verification are first-run items on the GPU host)
  or the transformers backend. The LLM backend in the runner is
  still vLLM-only (the library also has a transformers LLM backend,
  but the runner does not wire it; that is a separate, later change
  if vLLM is unavailable, not a Phase 1 silent fallback).
- **B3/B4 — NOT needed for Tier 1a:** replacement ASR/LLM pins are
  decided only after Tier 1a answers the bottleneck question. Do not
  pin them before B0 vs B-gold runs.
- **ASR revision:** `recommended.json` records no ASR revision
  field, so the cache meta uses revision `""` and the checkpoint
  string is the pin. If a revision is later pinned for a replacement
  ASR arm, it must be recorded in that arm's config snapshot.

## What was NOT done here

No GPU run, no training, no submission, no contact with the
organisers, no held-out use, no model result, no claim of any score,
WER, or timing, no edit to `lifemate/`, no merge, no push. The
packaging was smoke-tested on CPU only (config/split SHAs, manifest
gate, separation check, metric unit checks, raw-capture shim unit
test, trace schema); model loading, ASR, LLM generation, AgentLoop
execution, OFF-vs-ON comparison, and all real values are first-run
items on the GPU host, measured by the pilot 20 before the full set.
The Phase 1 fix adds CPU tests for the new gates (29 tests, see
above) and mock-directory ASR checks; the converted-CT2 transcription
path, the transformers ASR path on real audio, and every GPU value
remain first-run items, not results claimed here.
