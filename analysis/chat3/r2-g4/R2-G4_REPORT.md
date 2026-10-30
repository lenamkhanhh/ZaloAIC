# RUN2 — R2-G4, Group 4 Observer / log storage — REPORT (not ACCEPT)

Parent: L6 d7aecb41-b508-4570-99dd-0228ea89f166. Coordinator: main chat
e5b6f7e4-06d9-40b8-b9a3-37e913aaf595. Freeze: 13:41 Asia/Saigon 2026-10-30.
LifeMate only. Base pin: ff7a288e668f37e96c03bf9318d974e3a8e6d2a4.
Worktree: ~/workspace/chat3/r2-g4-ff7a, detached at ff7a288e (separate
from the shared checkout, which is on muse/chat3/gg-h1h2-fix).
Branch for this work (local, see Push section): muse/chat3/r2-g4-shadow-export.

## Before / after
Before (ff7a, verified in C3-E3-01 and re-verified here):
- ShadowObserver kept records only in RAM (records / to_json()).
- lifemate/run.py: 0 hits for observer/to_json, 6 subcommands, none
  wrote observer logs; cmd_infer wrote only submission lines.
- Config JSONs shipped had no shadow_observer key (default False).
- fake-run did not run AgentLoop, so it could never prove observer export.
- No export CLI, no schema file, no fresh-process export test.

After (this branch, new files only):
- lifemate/shadow_export.py — new CLI, `python -m lifemate.shadow_export`.
- tests/test_shadow_export.py — fresh-process + OFF/ON + error-gate tests.
- analysis/chat3/r2-g4/SHADOW_EXPORT_SCHEMA.md, fixture.jsonl,
  config_on.json, config_off.json, and this report.
- NO edits to lifemate/agent.py, lifemate/config.py, config JSON
  originals, lifemate/run.py, simulator, scorer, or any split.
  File-lock coordination: L4 (Group 5, chat fa70fda2-0ba8-4c1b-9064-284faf773c6d)
  was notified/requested for a future run.py subcommand lock; the
  first version deliberately needs no lock because AgentLoop already
  exposes loop.observer and the CLI reads records immediately after
  loop.run(), before the next sample's reset(). L4 reply, if any,
  does not change the files in this commit.

## What the CLI actually does
- Modes: --mode scripted-test (CPU, synthetic env/sample/generator,
  labelled synthetic, real AgentLoop + real observer/adapter) and
  --mode data (real ZaicEnv + real samples, scripted generator;
  fails fast with exit 2 if --data is absent or the split dir is missing).
- One JSONL envelope per sample/attempt, schema chat3-e3-1 (L6-accepted,
  additive derived fields only): schema_version, run_id,
  source_commit (base pin), code_commit (git HEAD at run time),
  sample_id, attempt, split, observer_enabled, records (exact,
  unmutated, in order), record_count, observer_error_count,
  observer_errors [{record_index, error}], steps_executed, positions,
  submission_tool_calls, state_hash. Record identity is
  (sample_id, attempt, record_index); position is not a unique id.
- Manifest per run: schema_version, run_id, source_commit,
  code_commit, mode, split, config/fixture/out paths, envelope
  count, total records, total observer errors, integration_success,
  failures list.
- Integration gate (strict, exit 3 on failure, export still written
  for diagnosis): OFF must have records=[]; ON records must have
  exactly the 9 observer keys, error=null, and every validated
  non-ask proposal must have non-null baseline/candidate decision
  dicts; export records must equal observer.to_json() records.
  "Observer errored but the agent still ran" is NOT success.

## Commands actually run and results (CPU_RUN, synthetic unless noted)
1. Fresh-process OFF:
   env -u PYTHONPATH python3 -m lifemate.shadow_export --mode scripted-test \
     --fixture analysis/chat3/r2-g4/fixture.jsonl \
     --config analysis/chat3/r2-g4/config_off.json \
     --out /tmp/r2g4_off.jsonl --manifest /tmp/r2g4_off.manifest.json --run-id r2-g4
   -> exit 0, 3 envelopes, records=0, observer_errors=0, integration_success=true.
2. Fresh-process ON (same, config_on.json):
   -> exit 0, 3 envelopes, records=4 (test-1: 2, test-2 ask: 1, test-3 invalid: 1),
      observer_errors=0, integration_success=true.
   -> Per sample: submission_tool_calls and state_hash OFF/ON identical
      (test-1 positions [0,1], test-2 [0], test-3 [0]).
3. python3 tests/test_shadow_export.py
   -> Ran 4 tests, OK (package import fresh-process, OFF/ON match,
      observer-error unit gate, CLI exit-3 on forced decide failure).
4. python3 tests/test_observer.py (existing suite, unchanged code)
   -> Ran 18 tests, OK (skipped=1, frozen-v10 reference absent — not a PASS).
5. Data mode, no data (expected failure, not a run):
   --mode data without --data -> exit 2, "requires --data".
   --mode data --data /tmp/nope-data -> exit 2, "data split directory not found".
   Real-data export is therefore NOT_RUN here, not claimed as run.
6. Push check (see below): local branch only.

## Open errors / residuals
- O1. Export CLI exists only as a new module, not as a lifemate/run.py
  subcommand. That integration needs an L4 file lock for run.py and
  L6 review on the final commit; it is NOT in this commit.
- O2. Frozen-v10 control still missing (same as C3-E3-01): skipped,
  not a PASS, recorded as missing artifact, not reconstructed.
- O3. Real-data export (public_test, train) NOT_RUN: no extracted
  dataset on this VM, and data is not in the repo. Model/GPU infer
  NOT_RUN for Codex.
- O4. Push: see Push section. Branch is local only at report time.
- O5. L4 lock reply for run.py was requested, not yet received at
  commit time; no run.py/agent/config edit was made, so no lock was
  needed for this commit, but the future subcommand is blocked on it.

## Push (do not substitute)
Per the known VM push block for Chat 3 (HTTPS git push has no
credential helper, gh not logged in, SSH egress blocked, and an MCP
snapshot push would create a different SHA/history), this branch was
NOT pushed via a snapshot substitute. If a git push attempt is made
from this VM and fails with the same credential error, the branch
remains local only and the coordinator push route is still required.
Do not present the local commit SHA as a remote commit, and do not
claim remote availability until a push is verified on the remote.

## Next step proposed (for L6 / coordinator, not self-granted)
1. L6 reviews this commit (files above, no existing-file edits).
2. L4 answers the run.py lock request; only then add the run.py
   subcommand reusing lifemate/shadow_export.py, re-run OFF/ON
   scripted fixture, and re-submit for L6 review on the final commit.
3. Codex GPU package: data-mode shadow-export + infer, same
   envelope, still NOT_RUN until Codex runs it.
Status: REPORTED, not ACCEPTED. No score-improvement claim, no
runtime/hard-enforce claim, no merge to main.
