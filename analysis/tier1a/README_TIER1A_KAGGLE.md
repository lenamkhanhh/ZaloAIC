# Tier 1a on Kaggle — B0 vs B-gold (LifeMate only)

Packaging of the Tier 1a benchmark (design: `next-step/stream-C.md`;
execution report: `next-step/tier1a/TIER1A-EXECUTION_REPORT.md`, verdict
BLOCKED, no model run) into a reproducible Kaggle notebook. This
directory is the only new content on branch `muse/chat3/tier1a-kaggle`.
No file under `lifemate/` was touched, nothing was merged, nothing
was pushed by this packaging step, and no GPU run, training,
submission, or model result exists from this work.

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
| Branch | `muse/chat3/tier1a-kaggle` (this branch) |
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
| `tier1a_kaggle.ipynb` | The Kaggle notebook, 9 cells, runnable top to bottom (see below). Valid JSON, checked with `python -m json.tool` / `json.load`. |
| `tier1a_runner.py` | Packaged runner: `smoke`, `check-separation`, `validate-manifest`, `asr-cache`, `run`, `check-off-on`, `score` (plus `analyze` as a score alias). Paths via flags, else `TIER1A_*` env, else Kaggle defaults. |
| `metrics.py` | Frozen metrics, copied verbatim from the Tier 1a executor's runner: WER normalisation (lowercase, strip punctuation, collapse whitespace, **keep Vietnamese diacritics**, digit strings as single tokens), S/D/I/N, slot error for `[0-9]+`, propagation, attribution, paired bootstrap CI (10,000 resamples, seed 20261030). |
| `refreeze.py` | Stratified refreeze (stdlib only, no torch/vllm needed). See "Manifest" below. |
| `manifest_schema.json` | Schema example ONLY: empty id list, status `schema-example-only`. It is never accepted as a run manifest and contains no real sample ids. |
| `README_TIER1A_KAGGLE.md` | This file. |

## Notebook cells (in order)

0. Purpose, source pin, provisional-set warning, run/score separation,
   private-output note.
1. **Preflight (fail-fast, before weights):** clone the branch if
   needed; config/split SHAs and fields; git `lifemate/` vs ddbe0a0;
   split counts; `check-separation`; input size (wav count + bytes).
   Writes `tier1a-output/preflight_report.json`.
2. **Refreeze:** if a frozen manifest already exists in
   `/kaggle/working`, skip with a log; otherwise run `refreeze.py`,
   then validate the manifest (status, ids sha, all-dev, no
   held-out, stratum minimum 20). Writes `manifest_gate.json`.
   Still before weights.
3. **ASR cache:** transcribe each wav exactly once for the baseline
   checkpoint. Gold transcripts never enter the cache.
4. **Run B0.** Writes `traces_B0.jsonl`.
5. **Run B-gold.** Writes `traces_B-gold.jsonl`.
6. **OFF-vs-ON check:** pilot 20, condition B0, observer OFF then ON;
   submission lines must be identical, otherwise the notebook stops
   and the main traces are invalid.
7. **Score (score phase only):** reads run traces from disk first,
   then gold calls; writes scored traces + `score_report.json` with
   WER, slot error, attribution, paired bootstrap CI, raw and
   dev-reweighted means, and the pre-registered decision.
8. **List artifacts** under `/kaggle/working` only.

## Kaggle run commands (step by step)

Prerequisites, before cell 3: a Kaggle notebook with GPU enabled and
with torch + vllm + faster-whisper + transformers installed (see
`RUN_LIFEMATE.md` §3 in the repo for the install), plus permission to
load the two pinned weights. The notebook itself does not install
packages, so that a missing backend fails fast with a BLOCKED message
instead of a partial run. Set `TIER1A_DATA` to the extracted
`train+public_test` root (the directory containing `train/train.jsonl`
and the wav files) before running cell 1.

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

# 2. Refreeze from real data (stdlib only), then gate it
python3 analysis/tier1a/refreeze.py --data "$TIER1A_DATA" \
  --source-tree "$TIER1A_SOURCE_TREE" \
  --out "$TIER1A_WORKING/benchmark-stratified-frozen.json"
python3 $R validate-manifest --source-tree "$TIER1A_SOURCE_TREE" \
  --benchmark "$TIER1A_WORKING/benchmark-stratified-frozen.json"

# 3. ASR cache (first weight load: ASR only)
python3 $R asr-cache --source-tree "$TIER1A_SOURCE_TREE" --data "$TIER1A_DATA" \
  --benchmark "$TIER1A_WORKING/benchmark-stratified-frozen.json" --out "$OUT"

# 4-5. Runs (no score is computed here)
python3 $R run --source-tree "$TIER1A_SOURCE_TREE" --data "$TIER1A_DATA" \
  --benchmark "$TIER1A_WORKING/benchmark-stratified-frozen.json" --mode B0 --out "$OUT"
python3 $R run --source-tree "$TIER1A_SOURCE_TREE" --data "$TIER1A_DATA" \
  --benchmark "$TIER1A_WORKING/benchmark-stratified-frozen.json" --mode B-gold --out "$OUT"

# 6. OFF-vs-ON (must be identical, or do not score)
python3 $R check-off-on --source-tree "$TIER1A_SOURCE_TREE" --data "$TIER1A_DATA" \
  --benchmark "$TIER1A_WORKING/benchmark-stratified-frozen.json" --out "$OUT/off_on"

# 7. Score (first and only place gold calls are read)
python3 $R score --traces "$OUT" --source-tree "$TIER1A_SOURCE_TREE" \
  --data "$TIER1A_DATA" \
  --benchmark "$TIER1A_WORKING/benchmark-stratified-frozen.json" --out "$OUT"
```

Environment variables (all optional; flags override them):
`TIER1A_SOURCE_TREE` (default `/kaggle/working/ZaloAIC`),
`TIER1A_DATA` (default `/kaggle/input`),
`TIER1A_WORKING` (default `/kaggle/working`),
`TIER1A_BENCHMARK` (default `$TIER1A_WORKING/benchmark-stratified-frozen.json`),
`TIER1A_REPO_URL`, `TIER1A_BRANCH`.

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
- `tier1a-output/scored_traces_B0.jsonl`, `scored_traces_B-gold.jsonl`
- `tier1a-output/score_report.json`

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
  with a BLOCKED message and produce no number.
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
