# Shadow export — schema chat3-e3-1 (RUN2, Group 4, R2-G4)

Base pin: ff7a288e668f37e96c03bf9318d974e3a8e6d2a4. LifeMate only.
This schema was accepted by L6 for C3-E3-01 (conditional accept);
RUN2 adds only additive derived fields, it does not change the
meaning of any L6-accepted field.

## File format
One JSON line per sample/attempt, UTF-8, `ensure_ascii=False`.
A manifest JSON file accompanies every export.

## Envelope fields
- schema_version: "chat3-e3-1"
- run_id: string, e.g. "r2-g4"
- source_commit: base pin ff7a288e... (NOT the checkout HEAD after branching)
- code_commit: git HEAD of the checkout that ran the CLI, or null
- sample_id, attempt (int, 0-based, fixture order), split
  ("synthetic" for scripted-test, otherwise the real split; never held-out)
- observer_enabled: bool, from config
- records: exact observer records, in list order, unmutated
- record_count, observer_error_count
- observer_errors: [{record_index, error}] — errors are explicit at
  envelope level, never hidden inside records alone
- steps_executed: len(submission_tool_calls)
- positions: [record.position for each record]
- submission_tool_calls, state_hash: from env.submission_line()

## L4 lock conditions — mandatory for the first version (L4, 2026-10-30)
These three conditions are part of this spec, not optional notes.
If any one is violated, the export silently loses log and must not
be reported as an observer run.

(a) In-process only. The CLI must run the loop in the same process
and export immediately after each loop.run(), before the next
sample starts. Reason: AgentLoop.run() calls observer.reset() at
the start of every sample (lifemate/agent.py; observer.reset() in
lifemate/lifemate_observer.py) and the log lives only in RAM.
A post-hoc exporter reading the RAM of a previous run is
impossible, unless there is a run.py integration or a file write
during the run itself. This CLI satisfies (a): _run_one() copies
loop.observer.records and parses loop.observer.to_json() right
after loop.run() returns, inside the same process, per sample.

(b) shadow_observer must be True at runtime. This is the config
value actually used when the CLI runs, not a file edit. Default
is False (lifemate/config.py: shadow_observer=False): then the
loop skips every observer call, records=[], to_json()="[]".
Such a run must be reported explicitly as observer OFF
(envelope observer_enabled=false, manifest observer_status="OFF"),
never as "no decision" or as a decision-less observer run.
OFF is a control run only; ON is the only observer run.

(c) Per-sample export, public API only, no filtering, no rewriting.
Export per sample with its sample id, writing exactly the records
from to_json() (already JSON-serialisable via _safe in
lifemate_observer.py). Do NOT filter out error records, do NOT
rewrite decisions, do NOT call env directly, do NOT use gold
labels, and do NOT change agent behaviour. The CLI uses only the
public API loop.observer (.records / .to_json()); it never calls
env methods for export and never mutates the proposal, call,
state, retry count, termination, or prompt ordering.

With (a)-(c), not editing lifemate/agent.py, lifemate/config.py,
config JSON originals, simulator, scorer, split, or lifemate/run.py
in the first version is correct and sufficient — as L4 confirmed.

## Record fields (exactly these 9, no more, no less)
proposal_raw, proposal_grounded, validation_outcome ("ok"|"failed"|"invalid"),
baseline_decision ({fired, applicable, reason} or null),
candidate_decision ({fired, applicable} or null),
adjustments (list or []), eligibility ({consumer, entity_id, status, reason} or null),
error (null or repr), position (int).

Identity: (sample_id, attempt, record_index). position is NOT a
unique id. Null-decision rules: ask, validation failure and
invalid generation have null decisions.

## Forbidden in export
Gold labels, label final_state, env internal state, future
results, held-out ids, credentials, raw audio, weights, full train data.

## Integration gate (strict)
OFF: records=[], submission/state_hash are the control.
ON: every record has the 9 keys, error=null, every validated
non-ask proposal has non-null baseline and candidate decision dicts,
and export records == observer.to_json() records.
Any failure: export file is still written for diagnosis, manifest
integration_success=false, CLI exit code 3. "Observer errored but
the agent still ran" is NOT integration success.

## Manifest fields (additive)
In addition to the L6-accepted manifest fields, the manifest
carries observer_status: "OFF" if every envelope has
observer_enabled=false, "ON" if every envelope has
observer_enabled=true, "MIXED" otherwise, "UNKNOWN" if there are
no envelopes. This is the explicit OFF label required by L4
condition (b); integration_success=true for an OFF run means
only "control run succeeded", never "observer produced decisions".

## Commands (first version, new files only)
  python -m lifemate.shadow_export --mode scripted-test \
    --fixture <fixture.jsonl> --config <config.json> \
    --out <out.jsonl> --manifest <manifest.json>
  python -m lifemate.shadow_export --mode data \
    --data <extracted train+public_test> --split public_test \
    --fixture <fixture.jsonl> --config <config.json> \
    --out <out.jsonl> --manifest <manifest.json>
Exit: 0 success, 2 usage/data/config error, 3 observer integration failure.
A future lifemate/run.py subcommand reusing lifemate/shadow_export.py
needs an L4 file lock for run.py; it is NOT part of this first version.
L4 lock for run.py, granted conditionally (not for immediate edit):
only an additive subcommand (e.g. shadow-export), no change to
existing subcommands, their arguments/defaults/behaviour, and no
change to agent.py/config.py/config JSON/simulator/scorer/split in
the same change; only on branch muse/chat3/r2-g4-shadow-export,
from ff7a288e, separate worktree, no push to chat1/chat2 branches,
no merge main, no force-push; subcommand must export per sample,
handle observer OFF explicitly, not filter error records, and not
change agent behaviour; before starting any run.py edit, G4 must
notify L4 in advance (not only after) so L4 can check collisions —
L4's R2-G5 branch changed agent.py/config.py locally, not pushed,
not overlapping run.py, but integration order still needs
coordinator/L6 to settle; a run.py subcommand is justified only
when it avoids duplicate infer logic (ASR/LLM/transcription) that
would drift, and that justification must be written in the run.py
edit request — otherwise prefer the new-file AgentLoop wrapper.
Final report still goes through L6 review on the final commit;
no self-ACCEPT.
