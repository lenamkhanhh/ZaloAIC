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
