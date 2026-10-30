# R5 — Number government + lifecycle expiry + runtime shadow (short handover)

Branch: `gg-r5-number-lifecycle-shadow` (from `gg-phone-callback-lifecycle`
@ 4bd95a51; code tree = 287e68d5, the R4 checkpoint — the 3 handoff
commits were doc-only). No merge to main. No GPU, no model, no training,
no held-out, no scorer/simulator change, no MEMORY.md change, no raw
dataset/environment pushed.

Commit hash: see the chat handover (this report is itself one of the
pushed files, so it cannot contain its own commit hash). File list +
blob SHAs are in §8; verify them against the branch tip after push.

Scope reminder (R5 task): close the batch-11 S1 wrong-number error, wire
evidence expiry into the prover, wire object-state checks into consumers
with clear contracts, integrate a G&G observer into the agent default
OFF with zero behavior impact, and hand over a candidate Codex can verify
with a real model. Hard-enforce stays FORBIDDEN. This report is NOT an
adopt/hard-enforce decision — it is the data for a later decision.

## 1. A/B/C table: done / not done, wired / not wired

| Part | Done | Wired into the decision path? |
|---|---|---|
| A. Batch-11 S1 (verb with a digit-run object misclassified as bare) | YES, closed at layer C + decide() level | YES — `_classify_object` now treats any object span containing ANY digit run as `specific`; only verbs with NO digit-run object are general/bare. Object still comes from existing government machinery (never a whole-sentence digit scan, never fragment completion). |
| A. Fallback-0676 path proof | YES — direct `_has_other_number` unit tests + an end-to-end decide() case whose trail carries the marker `generic_callback_positive_substring_excluded`, produced ONLY by the fallback path. A general-rule-preempted case (F4a) is never cited as fallback evidence. | Marker only; no decision change beyond the S1 fix. |
| A. Group joining (batch-11 M1) | NOT done — stays a backlog MINOR | NO. Fragments/groups (`0902 418 0240`, slash/comma/hyphen splits) still do not bind, by design (safe fire). Needs a parser contract before any implementation. |
| B. Prover expiry (observation / assembly / offset / duration) | YES — via optional `validity` callable (`prove_argument(..., validity=None)` default = exact old behavior) | WIRED in shadow only, behind `--validity` (default OFF). NOT wired into the agent runtime (the runtime observer logs adapter decisions; prover verdicts are a shadow-audit input, not a runtime input). |
| B. Eligibility API (42 supported / 42 explicitly unsupported consumers) | YES — `check_eligibility` returns (status, reason), status in {eligible, ineligible, unknown}; unknown always names the reason, never guesses | WIRED in shadow only: `decide(..., eligibility=True)` reports in `notes["eligibility"]`, and the runtime observer records it. REPORT-ONLY: it NEVER changes fired/applicable. |
| B. Adapter field_value emission (the wiring gap worker B flagged) | YES, coordinator-built | YES — `build_ledger` now also emits counterpart `field_value` records from item dicts in succeeded results (same echo rule as the existence loop). Existing adapter consumption queries claim == "existence" only, so these records cannot change fired by themselves. |
| C. Runtime shadow observer + agent hook + flag | YES — `lifemate_observer.py` (new) + hook-only `agent.py` + flag-only `config.py` (`shadow_observer: bool = False`) | Hook placed at the REAL loop point (frozen-v10 lineage: after grounding + validate + guard pre-block, immediately before `env.call`). Flag OFF = zero behavior change (proven vs the unmodified frozen agent, §3). Flag ON = log-only. |
| C. Port to the a2e832b benchmark loop | NOT done — report only (§6 of worker C's handover: gap list + 5 port steps) | NO. The observer was verified on the frozen-v10 lineage loop only. |

## 2. Errors closed (minimal repros)

- **S1 closed.** Before: `"Gọi số 2345 đi, số 0911111111"` + `phone.call(0911111111)`
  → un-fire (generic_callback_positive). After: fires (`unknown`,
  `positive_verb_not_governing_target`). Controls preserved: truly-bare
  `"Số Y, số 2345, gọi đi"` still un-fires (plain reason, marker does not
  leak); cross-action (message verb + call proposal) still fires;
  `và`-chains still govern both; `rồi` never chains.
- **Prover expiry works, position-sensitive.** Shadow V10: the offset base
  `alarm.list` alm_02 time 2026-11-14T07:00 is `active` at early positions
  and `invalidated field_updated@pos4` after the alarm's time was updated
  at position 4 — the 2 later text-arm proposals depending on it went
  from PROVEN/offset to UNPROVEN and from miss to correct_block (§3).
- **Eligibility reports without changing decisions.** `decide(...,
  eligibility=True)` vs `False`: fired/applicable/adjustments identical
  on every tested proposal; eligibility only adds `notes["eligibility"]`.

## 3. Errors open + boundaries (do NOT claim solved)

- Group joining (above). Single spoken digit words (`"số ba"`) are not
  digit runs (spoken runs need ≥2 words) — pinned current behavior, not
  a regression, but an open boundary in the same class.
- Registry coverage gap (measured): tasks/calendar/notes search results
  have NO `PRODUCER_REGISTRY` entries, so their items emit no existence
  or field_value records; eligibility for their consumers is `unknown`
  and their observations stay `unknown` under `--validity`. Extending the
  registry would change baseline-gate behavior — a future round, not R5.
- `history_reference` is deliberately NOT validity-gated (bare values,
  no entity link) — a history-referenced value from a deleted/updated
  entity can still prove. Needs entity-linked history evidence (future).
- Snapshot-vs-record precedence, PINNED (not a bug): staleness is defined
  ONLY by mutations touching the field, not by newer evidence records.
  A snapshot@1 beats a field record@4 when no mutation intervened.
  Flagged to Codex as a deliberate judgment call, not an error.
- Numeric balance guards, global-state consumers, multi-entity/roster
  guards: explicitly unsupported (42 consumers → `unknown`, never a
  guess). `door_lock.grant_guest_code` "eligible" covers the
  lock-existence leg only; `valid_until` is always named unchecked.
- `home_automation.create_rule` is installation-conditional; the API
  checks unconditionally — the caller must confirm installation.
- Pre-existing R4 boundaries carry over unchanged: bare-"chuyển"
  forward-inventory gap (MINOR), channel + cross-clause possessive
  un-fire, dirty-sticky across episodes (safe direction), ellipsis cost,
  quoted-name binding relying on B's veto, ASR digit loss / "tư" /
  spaced digits / compound amounts BLOCKED, prover observation expiry
  for history_reference (above), P3g residual.

## 4. Tests, paired gold, shadow (all CPU, dev only)

**Suites: 614/614 on BOTH backends** (system python3 and
`~/workspace/zaic-test-venv/bin/python`), 0 fail/error/skip. 11 files:
4 + 138 + 64 + 128 + 48 + 48 + 61 + 29 + 17 + 75 + 2 = 614
(baseline 528 + A 23 + B 43 + C 16 + coordinator 4).
New coordinator tests: decide-eligibility report-only + field_value
emission + eligible/ineligible/unknown (test_gates_adapter.py),
observer eligibility record shape (test_observer.py).

**Paired gold (dev 1237, scope 976): ZERO decision delta.**
Baseline 15/976, candidate 2/976 (train_1005 pos 1 contact + anomaly
train_1696 pos 2 other_ids), same 13 un-fires (0451, 0502, 0579, 0657,
0664, 0676, 0746, 0764, 0776, 0872, 1033, 1319, 1677), synthetic 976/0,
0 errors, by-group identical (phone 11→0, contact 3→1, other_ids 1→1).
Full-row diff vs the v10 paired output: only (a) `ledger_notes`
evidence_records counts inflated by field_value emission (notes-only),
and (b) train_1677's reason label refined to
`generic_callback_positive_substring_excluded` (A's disclosed marker;
outcome unchanged). The S1 fix changes NO gold outcome — no gold write
in scope hits the S1 mechanism.

**Shadow control (both new flags OFF): EXACT reproduction of the v10
shadow on all 3 versions** (summary-identical; rows identical except
evidence_records counts + the new row-level `eligibility: None` key).
V10: 14 rows, passed 8 / blocked 6. V11: 10 rows, passed 4 / blocked 6.
V13: 29 rows, blocked 16 / passed 6 / out-of-scope-guard 7.

**Shadow validity ON (`--validity`): V10 only changes.**
Proven args 4→2, blocked 6→8, passed 8→6, correct_block 6→8, miss 5→3,
correct_pass 3 unchanged, false_block still 0. The 2 changed rows are
both train_0008 text-arm (1 independent situation): a genuinely
incorrect proposal (gold read-only) whose offset base expired. V11 and
V13 unchanged (V13 proven was already 0).

**Shadow eligibility ON (`--eligibility`): decisions unchanged on all
3 versions** (report-only, as designed). Status histograms (rows where
the gate was applicable): V10 eligible 8 / unknown 5; V11 eligible 4 /
unknown 4; V13 eligible 2 / unknown 6. **Ineligible: 0 anywhere** — on
these traces no model proposal targets a deleted/cancelled entity.

**Counting table (new format; no arm/version double-counting).**
Control adjudications: V10 correct_pass 3 / false_block 0 / correct_block
6 / miss 5; V11 2 / 0 / 6 / 2; V13 0 / 0 / 16 / miss 6 / out_of_scope 7.
Distinct samples with ≥1 correct_block (any blocker): **11**
(0016, 0049, 0116, 0219, 0220, 0287, 0353, 0360, 0683, 0780, 0823).
Adapter-contributed (candidate fired + correct_block): **2 samples**
(0116, 0287). Adapter-only (candidate fired, baseline NOT fired): **0**.
Row-level blocked_by across versions: prover 28, g2 5, both 5
(every g2-blocked row was also prover-blocked). Validity adds 1
independent correct-block situation (train_0008) with 0 false blocks.
train_0004 remains a correct-PASS control, NOT a correct block — never
cite it as a block count. Adoption-bar leg 2 stays UNRESOLVED pending
the pinned definition (any-block reading passes with 11; adapter-
contributed reading gives 2 < 3; adapter-only gives 0). This round does
not declare adopt/hard-enforce.

**Red-team (coordinator-written, frozen candidate, synthetic only):
TWO consecutive clean batches — stop condition MET.**
Batch 1: 47 cases (A digit-run variants + fallback marker + group
boundary; B validity/eligibility/derived/future/re-read/ID-reuse/
history-ref/unknown-registry; C OFF-vs-old-baseline, grounding-ask,
flaky-decide, no-leak, max-steps, invalid, ask-only) → 44 PASS, 0 FAIL,
3 OBSERVE (all consistent with contract readings). Batch 2: 38 fresh
cases (M2-frame value-matching, owner/digit-run, question form,
roster-name vs digit-run, delegation, fragment proposals; snapshot
precedence incl. the mutation-only staleness rule, context-gated
library, FK flights.book, duration split, assembly (b) veto, offset
no-link; reject-once, noop, repeats-3, agent-level eligible record,
repr-string history, empty transcript) → 34 PASS, 0 FAIL, 4 OBSERVE
(all adjudicated consistent). Every first-run batch-2 FAIL was a probe
bug (missing existence records, a misdesigned M2 fixture, a wrong
submitted-count expectation, a misread staleness rule) — each was
corrected in the probe and re-run green on the UNCHANGED frozen
candidate, so no candidate fix was needed and no clean-batch count
was reset by a code change.

## 5. CPU run commands + flag

```bash
# Full suite (from the candidate root, both backends):
for f in tests/test_*.py; do python3 $f; done
for f in tests/test_*.py; do ~/workspace/zaic-test-venv/bin/python $f; done

# Paired gold (scope 976; lifemate-dir = candidate lifemate/):
python3 analysis/gg_paired_audit.py \
  --train-jsonl <train.jsonl> \
  --data-root <dir containing train/> \
  --split lifemate/splits/train_dev_heldout.json \
  --lifemate-dir lifemate --out-json <out.json>

# Shadow (control reproduces v10 exactly; add --validity and/or
# --eligibility for the new tables, never mixed into the control):
python3 analysis/gg_shadow.py --trace analysis/runtime/<trace>.json \
  --version <v10|v11|v13> --train-jsonl <train.jsonl> \
  --split lifemate/splits/train_dev_heldout.json \
  --lifemate-dir lifemate [--validity] [--eligibility] \
  --out-json <out.json>
```

Runtime flag: `PipelineConfig(shadow_observer=True)` (JSON key
`"shadow_observer"`, absent = False). OFF: the loop checks
`observer.enabled` first and skips every observer call (construction +
`reset()` only). ON: computes `adapter.decide(..., eligibility=True)`
and logs only — never mutates the proposal, grounded call, validation,
submitted calls, state, retries, termination, or ordering; never calls
extra tools; never reads labels, future results, or environment
internals; per-sample reset of ALL observer state; any observer failure
becomes an `error` record and baseline flow continues. The observer
depends only on the adapter interface + history/executed shapes, so it
ports to another loop by re-locating its three observe calls
(invalid-generation, validation-failure, post-validate/pre-call).

## 6. Log schema + artifact identity

Observer record (9 keys, JSON-serialisable): `proposal_raw`,
`proposal_grounded`, `validation_outcome` (ok | failed | invalid),
`baseline_decision` ({fired, applicable, reason} | None),
`candidate_decision` ({fired, applicable} | None), `adjustments`
(adapter trail or []), `eligibility` ({consumer, entity_id, status,
reason} | None — None when no decision was computed or the gate was
not applicable), `error` (None | repr), `position` (evidence position,
NOT a unique sequence number: two failed attempts at the same position
share it). Shadow row additions: row-level `eligibility` (None unless
`--eligibility`) and summary `validity_enabled` / `eligibility_enabled`
/ `eligibility_status_counts`. Local probe artifacts (NOT pushed):
`~/workspace/zaic-gg-r5-probes/` (paired JSON, 9 shadow JSONs,
r5b1/r5b2 probe scripts + results). Pushed artifacts: the 14 files in
§8 only.

## 7. Minimal GPU brief for Codex (NOT launched — Codex's job)

1. Port the observer to the a2e832b benchmark loop per worker C §7
   (copy `lifemate_observer.py` unchanged; add the flag the same way;
   re-locate the three observe calls by reading that loop — do NOT copy
   line numbers; re-run the fixture matrix with a fake generator first).
2. Run the a2e832b agent on dev (NOT held-out) with the flag ON and OFF
   on identical inputs; diff submitted calls + final state + termination
   (any difference is a blocker for the hook, per lifecycle report §6.6).
3. Adjudicate the real-model eligibility + validity deltas the same way
   as §4 (new-format counts; never force 0 diff; never loosen a rule to
   preserve 2/976).
4. Still open elsewhere (not R5): who runs the zero-shot benchmark and
   where results land (D6); organizer questions Q-L/Q-D (unsent, need
   user approval); adoption-bar leg-2 definition pin (user/Codex).
5. Do NOT hard-enforce on the basis of this report: the guard stays a
   shadow candidate (adapter-only correct blocks = 0; independent
   adapter-contributed situations = 2 < 3 on the adapter reading).

## 8. File list + blob SHAs (verify against the branch tip)

Base: `gg-phone-callback-lifecycle` @ 4bd95a51 (code = 287e68d5).
Changed files (14):

- lifemate/lifemate_callback_negation.py cf341ef4a55426c855b81a2e4d3a7a1b9f186dd5
- lifemate/lifemate_evidence_lifecycle.py 18597bdb75da5dd173284f5852416bad786adcaa
- lifemate/lifemate_provenance.py 093bc010e85d7cd141dd9d10439bfb447ceec3b5
- lifemate/lifemate_observer.py (NEW) d4a596ac8c8e1887805cf67bcd5f407c48e36a07
- lifemate/agent.py cdefcb3a18e83a3f23d03f816010396cda4675c0
- lifemate/config.py 80f3b019deb440276b842700960e7632ad66a014
- lifemate/lifemate_gates_adapter.py 1f942093200da2b55a0896e6dc98a70af5569b79
- analysis/gg_shadow.py e5634076f85bdcc69b3e550b3389781106980680
- tests/test_callback_negation.py 4e9b8c3f7d1ceb84b3d265a16dc1b6418be2c08c
- tests/test_evidence_lifecycle.py 5d15d46591fb411fd498c52ae171bca5c243dde5
- tests/test_lifemate_provenance.py ad66a4869ee56ed3ae0b6e9ff5a7be8ec6843602
- tests/test_gates_adapter.py 610c89a51375fcc2bbc402e815ac8bb475adab53
- tests/test_observer.py (NEW) eacd9aa7b7b236291a4449c93d07fea39315361f
- research/lifemate/gg_r5_number_lifecycle_shadow_report.md (this file)

## Summary

- S1 digit-run government error closed; fallback-0676 path proven by marker; group joining stays backlog MINOR.
- Prover expiry wired in shadow (`--validity`): V10 gains 1 independent correct-block situation (train_0008, true mutation expiry), 0 false blocks; V11/V13 unchanged.
- Eligibility wired report-only (`decide` + observer): 0 decision changes anywhere; 0 ineligible on model traces; 42/42 supported/unsupported split pinned.
- Runtime shadow observer integrated, flag OFF by default, non-interference proven vs the unmodified frozen agent on CPU fixtures.
- Suites 614/614 both backends; paired gold 0 decision delta (2/976 preserved); shadow control exactly reproduces v10.
- Two consecutive clean red-team batches (batch 1: 44/0/3; batch 2: 34/0/4); stop condition met with no candidate fix needed.
- Counting, honestly separated: 11 any-blocker situations, 2 adapter-contributed, 0 adapter-only; train_0004 is a correct-pass control.
- Still shadow-only, NOT hard-enforce-ready: adoption-bar leg 2 unresolved, a2e832b port unproven, registry gap for tasks/calendar/notes open.
- Next step for Codex: port the observer (§7), run OFF-vs-ON on dev with a real model, adjudicate the deltas — do not enforce yet.
