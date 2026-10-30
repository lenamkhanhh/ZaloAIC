# Four-arm harness — Phase 3 (LifeMate only)

**Status: harness + mock smoke only. No real arm has been measured.
No model score exists from this work. Anything labelled MOCK ONLY
below is plumbing, not a result.**

## What this is

On ONE frozen dev set, measure four combinations of two ASR
components and two LLM components, with everything else identical:

| Arm | ASR | LLM |
|-----|-----|-----|
| A | own | own |
| B | partner | own |
| C | own | partner |
| D | partner | partner |

Each arm changes only the component in its name. Sample IDs, run
order, runtime, prompt policy, tool catalog, seed, decoding, step
limit and scoring are identical across arms (see `arm_config.py`,
enforced by `validate_arms`).

Own pins (from `lifemate/configs/recommended.json`):
ASR `vinai/PhoWhisper-small`, faster-whisper, greedy beam 1, lang
`vi`, revision "" (the checkpoint string is the pin). LLM
`Qwen/Qwen3-4B-Instruct-2507`, revision `cdbee75`, vLLM
(transformers fallback), model's own chat template, temperature 0,
seed 42, context 16384, max_tokens 512.

Partner pins are UNPINNED (null in `arm_config.py`). Phase 2 must
supply them as merged LLM checkpoints with revisions, and an ASR
checkpoint with backend/revision/decode. Until then every real
command fails fast with BLOCKED -- no guessed partner checkpoint is
ever substituted.

## Files

| File | Role |
|------|------|
| `arm_config.py` | Arm contract + validation (shared identical, B/C/D differ only as named). |
| `manifest.py` | Frozen-manifest gate: real runs accept only `stratified-frozen`, dev-only, ids_sha recomputed, no held-out. Mock manifests are a separate status and are refused by the real gate. |
| `metrics.py` | Frozen WER / slot / paired-bootstrap definitions (Tier 1a definitions, restated; this worktree cannot import the tier1a worktree). |
| `tracing.py` | Real-run trace wrapper around a lifemate generator + real AgentLoop. No loop reimplementation. Raw output null-with-reason when the backend does not expose it. |
| `mock_backends.py` | MOCK ASR/LLM + mock loop simulator for smoke ONLY. Not AgentLoop, not zaic_tools. |
| `fourarm_runner.py` | `preflight`, `check-separation`, `mock-smoke`, `run` (real), `check-off-on`. |
| `score_fourarm.py` | SCORE phase only: reads traces from disk, then gold, writes `score_report.json`. Never runs the agent. |
| `tests/test_fourarm.py` | CPU unit + end-to-end mock tests (stdlib unittest). |

## Compatibility with Phase 2 (checkpoint interface)

The four-arm contract shape in `arm_config.py` is the shape this
task specified (`asr{backend, checkpoint, revision, decode}`,
`llm{base, adapter, merged, tokenizer, template, stop, context,
decoding, backend}`). Phase 2's schema v1 (branch
`muse/chat3/p2-checkpoint`, commit `30555b1`, read from its report
-- not edited, not merged here) uses different field names, so
`arm_config.to_p2_config(arm)` maps one arm onto it and returns
every GAP instead of silently dropping a field. Baseline arm A
maps gap-free. The gaps that would block a real partner arm are
Phase 2's named gaps, restated here so the coordinator merge has a
checklist:

- **A1:** transformers ASR has no class in `lifemate/asr.py`.
- **A2:** `FasterWhisperASR` takes no revision; pin by local
  directory. The four-arm ASR `revision` field is therefore
  recorded, never passed to the constructor.
- **A3:** only ASR beam 1 / language `vi` / greedy True are
  expressible (`transcribe()` hardcodes them). A real arm claiming
  another decode is refused in `validate_arms(real_mode=True)`.
- **L1:** adapter without a merged checkpoint is unbuildable.
- **L2:** tokenizer / chat template must be the checkpoint's own.
- **L3:** only temperature 0.0 is expressible.
- **L4:** custom stop tokens are not a parameter; stopping is the
  template stop token plus the `{"stop": true}` rule. The four-arm
  `stop` list is descriptive of that rule and maps to P2 `stop:
  null`.
- **L5/L6:** context is validated by `PipelineConfig`/loader only,
  not by generators; `TransformersGenerator` ignores seed/max_tokens
  (hardcoded greedy/512).

On merge, the real path should switch to Phase 2's
`loader.build_asr` / `loader.build_llm` (the B-CALLER change in the
Phase 2 report); until then the four-arm real path uses the same
real constructors those builders use, with the same kwargs, and
refuses the same gaps. It does NOT go through `run.py infer`,
which hardcodes faster-whisper + vLLM and ignores backend fields.

Failed-record rule (Phase 2 ASR contract, applied here): a missing
wav, a backend error, or an empty transcript produces a trace with
`run_error` set and no guessed transcript, and the score phase
excludes that sample explicitly (reported in
`excluded_failed_traces`), never scoring it as 0 and never shifting
order.

## Call paths (no reimplementation)

- Agent: `lifemate.agent.AgentLoop` (real run, imported from the source tree).
- Env: `lifemate.adapter.ZaicEnv`.
- Config: `lifemate.config.PipelineConfig.from_json(recommended.json)` + per-arm ASR/LLM pin overrides only.
- ASR: `lifemate.asr.FasterWhisperASR`. LLM: `lifemate.llm.VLLMGenerator` / `TransformersGenerator`.
- Scorer: `lifemate.scoring.score_sample` -- SCORE PHASE ONLY. It is official-style, NOT the organiser evaluator (see `lifemate/scoring.py`: ask scoring and read-in-F1 are UNVERIFIED).
- ASR cache: one cache per checkpoint, key = checkpoint + revision + wav sha + backend + beam + language; never reused across checkpoints. Gold transcripts never enter a cache.
- ASR scope: EVERY user audio turn (history + current) is transcribed by the arm's ASR. A gold transcript is NEVER agent input in this harness. This differs deliberately from Tier 1a's history-fixed design: four-arm measures the full ASR arm, and public_test has no transcript to fall back to. Implementation: each sample-run gets a deep copy whose history user-turn transcripts are OVERWRITTEN with arm ASR before AgentLoop runs (the original sample is never mutated, so arm B cannot inherit arm A's history, and the gold history value is never read -- it is set, not read; see the separation check's Store-only exception for that field).

## Trace schema (run phase, one JSON line per sample-run)

`sample_id, split ("dev"), arm, mode, asr, llm, shared,
transcript_current, transcript_source, wav_path, wav_sha256,
prompt_sha256, generations[] (prompt_sha256, raw_output,
raw_output_reason, raw_output_token_count, prompt_token_count,
token_count_reason, parsed_call, error, seconds,
observation_following, observation_kind), grounding_log,
observer_log, tool_calls (executed = submission), state_hash,
termination {kind, n_generations}, seconds, run_error`.

Run traces contain NO score, NO gold call, NO gold transcript.
Score phase reads traces first, then gold. No scored trace is ever
fed back into an agent prompt.

Real-run termination honesty: AgentLoop returns only a submission
line, so the real termination is `stop` (last generation was a
stop), `max_steps`, or `returned_before_max_steps` -- never an
invented guard reason. The mock path has exact termination because
it is a simulator.

## Report (score phase)

Per arm: total mean_score, hash_rate, mean_f1, n, mean/p95 seconds,
mean WER, mean slot error rate; the same means by label group
(empty / ask_only / ask_after / normal); per-flag counts/rates for
slot_heard_wrong, wrong_tool, wrong_param, fabricated_id_time_money
(heuristic, needs human review when it fires), skipped_read,
extra_call, early_stop, late_time (> 30 s, the A30 limit); paired
differences for ALL SIX pairs (A-B, A-C, A-D, B-C, B-D, C-D) on the
same samples with bootstrap CI (10,000 resamples, seed 20261030);
and a dev-reweighted mean (label-group shares of the full dev
split, computed in the score phase -- never from held-out ids).
A report covers all 4 arms and all groups; no cherry-picked subset
is a report.

## G&G OFF/ON gate

G&G is shadow-only. Before scoring, `check-off-on` runs the pilot
set with the observer OFF and then ON and compares calls, final
state (`state_hash`), submission lines and termination. They must
be identical. Any difference exits 3, and `score_fourarm.py
--off-on-report` refuses to score against a non-identical report.
The mock OFF/ON result in this branch proves the comparison code,
not G&G behaviour on real runs -- a real OFF/ON check must be run
on the GPU host before real scoring.

## Commands (CPU, work now)

```bash
cd <repo-root>   # this worktree, branch muse/chat3/p3-fourarm
R=analysis/fourarm/fourarm_runner.py
python3 $R preflight --source-tree . --out /tmp/fourarm-preflight
python3 $R check-separation
python3 $R mock-smoke --source-tree . --out /tmp/fourarm-smoke
python3 $R check-off-on --source-tree . --out /tmp/fourarm-offon --mock
python3 analysis/fourarm/score_fourarm.py --traces /tmp/fourarm-smoke \
  --out /tmp/fourarm-score --mock \
  --mock-fixture /tmp/fourarm-smoke/mock_gold_fixture.json \
  --off-on-report /tmp/fourarm-offon/off_on_report.json
python3 -m unittest discover -s analysis/fourarm/tests -v
```

## Real run (BLOCKED here, exact unlock list)

```bash
python3 $R run --source-tree . --data <extracted train+public_test> \
  --benchmark <stratified-frozen manifest> --arms <arms.json> \
  --out <working dir, never the repo>
python3 $R check-off-on --source-tree . --out <dir> \
  --data <data> --benchmark <manifest> --arms <arms.json>
python3 analysis/fourarm/score_fourarm.py --traces <run out> \
  --out <score dir> --source-tree . --data <data> \
  --off-on-report <off_on_report.json>
```

BLOCKED on this host, with the exact artifact each blocker needs:

- **B1 data:** extracted `train+public_test/` root with
  `train/train.jsonl` + wav files. Verify per RUN_LIFEMATE.md §0:
  zip 876430231 bytes, sha256
  `57d371518996ec70d3af86402b7eba61208093c82955b9807a7ab39604b47320`,
  `unzip -t` no errors. Currently: no data dir, `LIFEMATE_DATA`
  unset, no `train.jsonl` found.
- **B2 GPU + backends:** 1× GPU ≥ 16 GB VRAM (A30 is the reference
  for the 30 s/sample limit), torch + vllm + faster-whisper (+
  transformers) importable, `nvidia-smi` succeeding. Currently:
  none importable, no `nvidia-smi`.
- **Partner pins (Phase 2):** partner ASR checkpoint/backend/
  revision/decode, partner LLM merged checkpoint + revision +
  tokenizer/template/stop/context/decoding/backend, in an
  `arms.json` matching the `arm_config.py` contract. Currently:
  all partner fields null. An adapter without a merged checkpoint
  is refused, not silently downgraded, because `lifemate/llm.py`
  has no adapter-merge step.
- **Frozen manifest:** a `stratified-frozen` manifest from Tier 1a
  refreeze (dev only, stratum minimum 20, ids + sha only). The
  provisional hash-only 200-id set is never accepted. Currently:
  no such manifest exists in this branch (it must be produced when
  data arrives, before any model output, and must not be the
  provisional set).

## What was NOT done

No real arm run, no model score/WER/timing, no training, no weight
change, no submission, no organiser contact, no held-out use, no
edit to `lifemate/`, `analysis/tier1a/`, or any other branch, no
merge, no push. Traces, fixtures and reports from smoke live in
`/tmp` (or the `--out` dir given), never committed to the repo.
