# G&G Round: Phone + Callback Evidence and Evidence Lifecycle (Shadow)

**Branch:** new branch from `round10-provenance-gates-fixes` @ `61d84390`
(see §5 for the push commit; no merge to main).
**Scope:** shadow-only. No hard-enforce, no score claim, no inference
change, no simulator/scorer/config change, no held-out, no GPU, no
training, no organiser contact, no friend-repo/Drive/Kaggle access.
**Status:** candidate gates close the evidenced phone/contact gaps on
gold (see §3) and change nothing on model traces (see §3.3). The
candidate is **not** hard-enforce-ready (see §4.5).

## 1. Root cause

The Round-3 Gate 2 (`gate_read_before_write` @ 61d84390) only
establishes a reference from **structured prior-call results and
roster search results**. Three evidenced gap classes fell through it:

1. **Direct phone numbers.** A number the user speaks or writes in
   the current request (spoken Vietnamese digit words, a hotline, a
   corrected tail) is not a "prior result", so all 11 phone-only
   gold residuals fired (57.9% false-block rate on phone refs).
2. **Callback / contact-in-history.** A contact that exists only as
   a call/message-log counterpart (missed call, incoming message)
   is not a roster entry, so the 3 message-history gold cases
   fired. The baseline gate also had two latent bugs the review
   found: roster multiplicity was checked before log grounding
   (P3c: for a phone-only dial the target is the NUMBER, so log
   grounding must pass regardless of roster multiplicity), and the
   result flattener drops fields named `phone` (P3h: nested
   `contact.phone` in log records was invisible).
3. **Stale evidence.** Nothing ever expired: a deleted entity kept
   passing through stale priors, an empty re-read was undecided,
   and cancel-vs-delete semantics were conflated. The baseline
   had no lifecycle at all (L1b/L5/L7 gaps).

A fourth, subtler root cause: the baseline gate answered ONE
question (does an established source exist?) for what are really
TWO questions: (a) is there a valid source, and (b) does the
current request select THIS number/counterpart as the action
target? Proving (a) alone was recorded as if it proved (b). The
new contract keeps them separate, always.

## 2. New contract

### 2.1 Evidence record (shared, JSON-able)

```json
{"kind": "phone|contact|entity",
 "value": "normalized (phone digits via _norm_phone; id/name via nfc_lower)",
 "source": "roster|call_log|message_log|user_text|history_text|read_result|write_result",
 "producer": "tool name or 'user'",
 "field": "field/path",
 "outcome": "succeeded|failed|schema_rejected|noop",
 "counterpart": "record-identity dict or null",
 "position": "int (prefix order)",
 "claim": "existence|field_value|eligibility|binding",
 "status": "active|invalidated|ambiguous|unknown",
 "reason": "short machine-readable string"}
```

Only `outcome == "succeeded"` (ok True AND done not False) counts
as evidence. A call's own arguments are never evidence. Write
results restating their own reference args establish nothing
(echo rule), except patch-verified writes.

### 2.2 Verdicts

```json
{"established": "bool", "basis": "source|binding|null",
 "question_a_sources": ["..."],
 "question_b_target_selected": "true|false|null",
 "question_b_reason": "string",
 "decision": "PROVEN|AMBIGUOUS|UNKNOWN"}
```

- PROVEN iff an active source exists AND question (b) is True.
- (a) only with (b) undetermined -> AMBIGUOUS, never PROVEN.
- No (a) -> UNKNOWN. UNPROVEN is not hallucination; PROVEN is not
  a correct call (existence is not correct entity choice).

### 2.3 Phone rules (module A: `lifemate_phone_callback_evidence.py`)

- Own spoken-digit parser (the old `parse_number_words` returns
  None for every digit sequence). "không" inside a digit run is 0;
  "không phải" splits the run (negation, never digits). A long
  spoken run (>= 9 digits) classifies as phone by shape; a short
  run starting with "không" and no phone cue stays ambiguous.
- Normalization is the `_norm_phone` rule only (digits, +84/84
  fold to 0). Digits are never added, dropped, or edited.
- Tail correction ("đuôi là X chứ không phải Y") replaces only
  the tail, requires the old tail to match a history number, and
  yields a BINDING claim, not existence.
- Callback binding prefers incoming/missed records; distractors
  (outgoing) are excluded by name/topic/amount. Recency alone
  never binds (two unnamed missed calls -> ambiguous); only
  "số mới nhất" + a message `time` field binds by recency.
- Name matching is diacritic-sensitive on original tokens
  ("An" != "ăn"); multi-token names may match folded. An explicit
  non-generic, non-family addressee after a callback verb vetoes
  binding to anyone else (`callback_name_mismatch`); family
  references (mẹ/ma/bo/...) and generic references (người đó, tin
  nhắn) never veto.
- Roster multiplicity: number existence is separate from contact
  identity. >= 1 roster entry carrying the number proves the
  NUMBER for number-target consumers; identity stays ambiguous.
- Consumer table (`CONSUMER_REQUIRES_MEMBERSHIP`): contacts.update
  requires membership (patch find-or-noop); contacts.get/search,
  phone.call, sms.send, ewallet.transfer do not validate (an
  observed counterpart suffices for execution, never for
  membership). Unknown consumers cap at AMBIGUOUS. There is NO
  contacts.delete tool in the catalog (a previous notes claim
  said otherwise; corrected).
- History-result parsing: `json.loads` then `ast.literal_eval`,
  never `eval`; malformed input yields an explicit reason, never
  a crash. Nested `contact.phone` is extracted explicitly (the
  gates flattener drops fields named `phone`).

### 2.4 Lifecycle rules (module B: `lifemate_evidence_lifecycle.py`)

A LEDGER + rule engine (explicitly NOT a DAG; derived claims
resolve by recursive link-following with a cycle guard).

- Three independent claims: existence / field_value / eligibility.
- Only mutations with ok True + done not False AND effective=True
  have effect. Schema rejects, noops, ineffective and non-dict
  results kill nothing. Non-succeeded evidence is never active.
- Delete kills all three claims. Cancel kills eligibility +
  field_value(status) only; existence and other fields survive
  (verified: NO cancel tool truly deletes -- all 5 are patch
  status=cancelled). Update kills the field_value of touched
  fields (explicit `fields` win; fixed-field updates carry table
  `fields`: complete->done, check->checked, check_in->checked_in,
  join->status, archive-update->folder, add_to_playlist->track_ids,
  pay->paid+paid_with, subscribe->subscriptions); update with
  unknown touched fields kills ALL field claims (fail-closed).
- Re-read re-establishes: a new succeeded record at a later
  position revives the claim; the old record stays dead. An empty
  re-read after delete does NOT resurrect (delete is positive
  evidence of absence; L7 decision, grounded).
- Id reuse: `App.create.new_id = len+1` can re-mint a deleted id;
  the ledger handles it by journal position (old record stays
  dead; only the create-result record re-establishes). Residual,
  recorded, not claimed solved.
- `query(position=P)` sees the journal only up to P (future
  mutations invisible). `apply_prefix` sorts by position.
- Derived records carry `derived_from`; a dead source makes the
  derived claim `unknown` (derived_source_invalidated), an unknown
  source makes it `unknown`, a cycle makes it `unknown`.
- Registry isolation: keys are (registry, value, claim[, field]).
- email.archive is delete iff `action == "delete"`, else a folder
  update: the TABLE alone cannot decide (kind_arg); the adapter
  reclassifies (both branches tested). scene_run emits one event
  per enumerated device (accepts `id` and `device_id`); a
  non-enumerating result is skipped with a note, never guessed.
  Upserts and kind_arg tools other than email.archive are skipped
  with a note, never guessed.

### 2.5 Adapter rules (`lifemate_gates_adapter.py`)

`decide(call, prefix, roster, current_text, kinds,
proposal_position)` returns baseline fields + an adjustment trail.

- P3g filtering runs FIRST, on the baseline gate's priors AND the
  ledger AND module A's prefix (filtering only A's prefix is not
  enough: the baseline gate itself would pass via the laundered
  log entry). Filter rule: a session-origin READ record
  (phone.recent_calls / sms.read_recent) is dropped iff it looks
  session-created -- number in session-written numbers, or
  contact_id in session writes' contact_id args -- AND its shape
  is session-created: direction "outgoing", or no direction key
  AND status "dialing" (exactly what phone.call creates; sms.send
  records carry direction "outgoing"). History records, incoming
  records, and direction-missing records with status
  received/missed/completed are kept. Residual: a dial from an
  EARLIER session (also status dialing, no direction) re-read now
  is filtered too -- conservative firing, documented.
- Adjustment 1 (UN-FIRE, contact refs only): baseline fires on a
  contact reference AND module A PROVES it (both questions) ->
  pass. Entity-id fires are NEVER un-fired by A evidence.
  Un-fire requires EVERY missing contact reference covered AND no
  entity-id fire standing AND not a bare-mutate-verb fire.
- Adjustment 2 (SUPPRESSION, id refs only): baseline passes an id
  reference but the ledger says existence INVALIDATED at the
  proposal position -> fire. Never applies to bare phone numbers
  (dialability is not entity existence), name refs (see below),
  or bare mutate-verb passes. Suppression WINS over un-fire for
  the same contact_id. Ledger "unknown" after a gate pass is
  recorded as an adapter gap, never invented into a block.
- Name suppression (C2 latent hole, future-proofing): a name ref
  that passed via the roster is resolved to a roster id ONLY on a
  unique match, then existence-checked like an id ref. With the
  current catalog (no contacts.delete) this branch cannot fire
  end-to-end; the resolution helper is unit-tested and the alive
  control passes.
- Suppression scope this round: existence only. The ledger tracks
  eligibility claims, but Gate 2 checks existence only, so
  eligibility-based suppression is a documented future hook, not
  implemented.
- Boundary semantics: a mutation AT proposal_position counts as
  "before" (ledger query is inclusive). Callers MUST use the
  default proposal_position (max prefix position + 1); the shadow
  script does.
- Unknown tools (not in MUTATION_TABLE) emit no mutation event
  and are logged in `mutation_skipped` (previously silent).
- Notes semantics: `mutation_events` counts events EMITTED into
  the ledger input, not mutations that prove effective (the
  ledger itself ignores non-succeeded ones). The count can read
  higher than the effective mutation count; decisions are
  unaffected.

### 2.6 Synthetic example (evidence interface)

```python
# Prefix: history missed call from Vy (c_217) + current text
# "gọi lại cho Vy giúp tôi" + proposal phone.call c_217.
# Module A verdict: PROVEN, basis binding,
#   question_b = bound_reference_selects_counterpart,
#   consumer_no_membership_validation.
# Adapter: baseline fired (c_217 not in roster) -> adjustment
#   {reference: "id c_217", old: fired, new: passed,
#    mechanism: phone_callback_evidence}.
# Contrast: same prefix, current text "gọi lại cho An" ->
#   bind returns (None, callback_name_mismatch) -> gate stays
#   fired. A name in the text vetoes binding to anyone else.
```

## 3. Before / after metrics

All runs on FROZEN snapshots (baseline @ 61d84390 vs candidate),
identical inputs, dev only (1237), no held-out, no scope change.

### 3.1 Paired gold audit (`analysis/gg_paired_audit.py`)

| | Baseline | Candidate |
|---|---|---|
| Applicable | 976 | 976 |
| Fired (false blocks on gold) | 15 (1.54%) | 1 (0.10%) |
| Excluding the train_1696 anomaly | 14 | 0 |
| Phone group (19 applicable) | 11 fired (57.9%) | 0 |
| Contact group (107) | 3 fired (2.8%) | 0 |
| Other-ids group (850) | 1 fired (0.12%) | 1 (unchanged) |
| Synthetic control (empty prefix must fire) | 976 TP / 0 FN | 976 TP / 0 FN |
| Decision changes | -- | 14 (all un-fires, 0 new fires) |
| Errors | 0 | 0 |

The single remaining candidate fire is train_1696 pos2 (the gold
replay anomaly itself, chat_6142) -- unchanged on both sides, kept
separate, never hardcoded. Lifecycle suppression fired ZERO new
times on gold: no gold write passed baseline with invalidated
existence. That is a nil gold effect, reported plainly, not a
win; the ledger's value this round is correctness on model
traces (stale-reference blocking) and the adapter's suppression
machinery, proven by synthetic tests.

### 3.2 All 14 adjudicated decision changes

Phone (11 -- every phone residual closed):
- 0451 phone.call 09875551235: bound_reference (number in chat
  content, new number superseding the old within that text).
- 0502 phone.call 19001234: spoken hotline directly requested.
- 0579 phone.call 09870001117: spoken digits directly requested
  ("không chín tám bảy, không không không, một một một bảy").
- 0657 phone.call 09870011220: spoken digits directly requested.
- 0664 phone.call 09889990002: digits directly requested.
  CAVEAT (P4b): the request is conditional ("nếu báo là cửa đang
  mở thì khóa ngay lại, xong gọi..."). The gate answers existence
  + selection for the number; whether the condition held is a
  planning question the gate does not answer. Same caveat for
  0676 (conditional warehouse-alarm call).
- 0676 phone.call 09886655445: spoken digits directly requested
  (conditional, same caveat).
- 0746 phone.call 09024180240: spoken digits directly requested.
- 0764 phone.call 09020000652: bound_reference (history text).
- 0776 phone.call 09098877660: bound_reference (message content).
- 0872 phone.call 09012345677: spoken digits directly requested
  (the "12 phố Hoa" distractor did not break it).
- 1677 phone.call 09832415068: tail correction of history spoken
  09832415086 ("đuôi là sáu tám chứ không phải tám sáu").

Contact (3 -- all via genuine binding, verified after the
name-veto fix; none relied on the old name-filter fallback):
- 1005 sms.send c_778: bound_reference_selects_counterpart,
  consumer_no_membership_validation.
- 1033 phone.call c_217: bound_reference_selects_counterpart,
  consumer_no_membership_validation.
- 1319 ewallet.transfer c_9526: topic_amount_selects_counterpart
  (amount 200,000 + lamp mention match the message), consumer
  requires no membership validation.

No (a)-only verdict was counted as PROVEN anywhere in the 14:
every un-fire carries question_b True with a named reason above.

### 3.3 Model-trace shadow (`analysis/gg_shadow.py`)

Candidate shadow = baseline shadow ROW-IDENTICAL on all versions
(decisions and adjudications, 0 diffs on 14 + 10 + 29 rows):

| Version | Baseline | Candidate |
|---|---|---|
| V10 | blocked 6 / passed 8; correct_block 6, correct_pass 3, miss 5 | identical |
| V11 | blocked 6 / passed 4; correct_block 6, correct_pass 2, miss 2 | identical |
| V13 | blocked 16 / passed 6 / out-of-scope 7; correct_block 16, miss 6, oos 7 | identical |

Why identical: model-trace blocks are driven by the PROVER
(monitored args UNPROVEN/AMBIGUOUS), not by Gate 2 (which fired
only 1/2/2 times). The 5 candidate adjustment rows are all
correct REFUSALS to un-fire hallucinated ids (cont_01 x4,
contact_mom x1, `no_counterpart_selection_signal`), so the
correct_blocks are preserved. Zero new misses, zero lost blocks.
Independent positive samples stay 1 (train_0004, in V10/V11) --
no hard-enforce claim changes that.

### 3.4 Regression (frozen candidate, both backends)

| Suite | Tests | Result |
|---|---|---|
| test_lifemate_gates (old) | 48 | OK |
| test_lifemate_provenance (old) | 46 | OK |
| test_phone_callback_evidence (51 old + 9 reviewer) | 60 | OK |
| test_evidence_lifecycle (34 old + 2 reviewer) | 36 | OK |
| test_gates_adapter (13 + 4 R2 + 7 review-FAIL) | 24 | OK |
| Total | 214 | 0 fail / 0 error / 0 skip |

One old test was updated under the new contract, with citation:
`test_roster_unique_vs_duplicate` now asserts the R2-A2 split
(identity ambiguous + number-existence active + PROVEN on name
selection) instead of "no active roster source on duplicate".
All other old tests pass unchanged.

## 4. Remaining errors, false blocks, false passes

### 4.1 False blocks remaining on gold

- train_1696 pos2 only (the anomaly; excluded from the 0% claim).
- Conditional calls (0664/0676 pattern): the gate passes the
  number, but condition evaluation is out of scope -- a future
  planning layer, not a gate fix.

### 4.2 False passes / over-permissiveness risks

- ASR digit loss is permanent at text level: a missing, extra,
  or unclear digit yields UNKNOWN/AMBIGUOUS, never a guessed
  completion. No ASR-confidence input exists.
- "tư" for digit 4 is unsupported (10 standard digit words
  only). Space-separated digit strings ("0902 418 0240") are not
  merged (only spoken-word runs merge). Compound spoken amounts
  ("sáu trăm hai mươi nghìn") are not parsed for amount
  disambiguation (simple amounts only).
- Semantic coreference beyond name/topic/amount equality +
  recency-by-time stays AMBIGUOUS.
- Numbers in images/attachments or audio-only are out of scope.
- Single-token names with ASR-dropped diacritics ("Bình" ->
  "binh") fall back to AMBIGUOUS (safe direction, documented).
- Name veto can over-veto when a verb sits in the addressee slot
  ("nhắn lại bảo An" is handled via stoplist; rarer verbs fall
  back to firing -- baseline behavior, not a regression).

### 4.3 Lifecycle residuals

- Id reuse after delete is handled by position, recorded, not
  claimed solved for all consumers.
- Derived-from invalidation (L8) works at module level but the
  adapter never emits `derived_from` and only queries existence:
  derived claims do not reach the gate. The adapter is a
  ledger/rule engine, not a DAG; do not call it one.
- Eligibility claims are tracked but not wired to any gate check
  (Gate 2 checks existence only). Action-specific guards
  (check_in refuses cancelled/already-checked-in, join refuses
  cancelled, reserve refuses reserved) need a per-consumer claim
  map that does not exist yet.
- Global-state updates (music.play, tv.tune, robot_vacuum, ...)
  carry table notes but no entity-keyed field emission; the
  adapter's global-entity convention (`<app>.global`) is
  unvalidated for these.
- Upserts (schedule_autopay by type, save_place by place_id,
  news.save by article_id) need adapter classification by prior
  state and are skipped, never guessed.
- scene_run atomicity (any missing device -> whole noop) is the
  adapter's emission burden; the ledger does not verify it.

### 4.4 Prover lifecycle NOT wired (explicit)

Only Gate 2 got the ledger this round. The prover's
`observation_events` still never expire: a value proven from a
read that a later mutation invalidates stays PROVEN in the
prover. Wiring prover observation expiry to the ledger is the
next round's work, not this one's; do not describe the prover as
lifecycle-aware.

### 4.5 Not hard-enforce-ready

- Independent positive samples: 1 (train_0004). The adoption bar
  from the capability audit (guard false-block <= 2% Wilson upper
  <= 5% AND correct blocks on >= 3 independent situations) still
  FAILS on the second leg.
- Phone branch residual: existence is not disambiguation, and a
  benchmark trace with gold writes is still needed for blocking
  precision on correct proposals.
- Repr-string handling is defensive-only: stored `tool_results`
  contain 0 str values (dev 1237: list 2384 / MISSING 3208 /
  str 0; full 1545: list 2981 / MISSING 4001 / str 0). The old
  "repr-string 412" figure is not reproducible from stored types
  (it likely described the rendered prompt form) and must not be
  quoted as a stored-type count. No dev coverage exists for
  repr-string history turns.

## 5. Reproducibility

### 5.1 Source / data identity

- Baseline: branch `round10-provenance-gates-fixes` @
  `61d84390cf652b9490de5f5db8378d5802c11182` (frozen snapshot
  `~/workspace/zaic-gg-baseline-61d84390`).
- Candidate workdir: `~/workspace/zaic-gg-candidate`; frozen copy
  used for all runs: `~/workspace/zaic-gg-candidate-frozen/`
  (git metadata stripped; lifemate/*.py + analysis scripts copied
  verbatim).
- Data (read-only, never pushed): train.jsonl 1545 samples
  (`~/workspace/zaic-data/lifemate/extracted/train+public_test/train/`),
  split `lifemate/splits/train_dev_heldout.json` (dev 1237 /
  held-out 308, held-out never opened). zaic_tools implementation
  read from the same data root (phone.call/sms.send shapes,
  patch/delete semantics verified there).
- Dependencies: Python stdlib only for all new modules, adapter,
  audits, and shadow. Tokenizer-dependent tests use the local
  venv (`~/workspace/zaic-test-venv/bin/python`); no torch, no
  GPU, no network, no paid API.

### 5.2 Commands (from the frozen candidate dir unless noted)

```bash
# Paired gold audit (baseline reproduced first from the baseline
# snapshot with analysis/gates_precision_audit.py: 976 / 15 / 1.54%)
python3 analysis/gg_paired_audit.py \
  --train-jsonl ~/workspace/zaic-data/lifemate/extracted/train+public_test/train/train.jsonl \
  --data-root ~/workspace/zaic-data/lifemate/extracted/train+public_test \
  --split lifemate/splits/train_dev_heldout.json \
  --lifemate-dir ~/workspace/zaic-gg-candidate-frozen/lifemate \
  --out-json /tmp/gg_paired.json
# Trace shadow (V10/V11/V13; trace files under analysis/runtime/)
python3 analysis/gg_shadow.py --trace analysis/runtime/e1_v10_diagnostic_trace.json \
  --version v10 --train-jsonl <same> --split <same> \
  --lifemate-dir ~/workspace/zaic-gg-candidate-frozen/lifemate \
  --out-json /tmp/gg_shadow_cand_v10.json
# Regression (both backends; counts in §3.4)
python3 tests/test_lifemate_gates.py
python3 tests/test_lifemate_provenance.py
python3 tests/test_phone_callback_evidence.py
python3 tests/test_evidence_lifecycle.py
python3 tests/test_gates_adapter.py
~/workspace/zaic-test-venv/bin/python tests/test_*.py  # same files
```

Sanctioned data access only: ToolEnv replay for the gold audit;
history user texts as dataset text (gold audit) or ASR model
transcripts (shadow) -- that difference is deliberate and matches
each audit's existing inputs. Never open `train_environment/` or
`state.json` directly. No sample id or gold value appears in
runtime logic (verified by grep: only format examples like
hotline shapes in comments; train_1696 appears only in audit
reporting, never in gate/provenance/adapter logic).

### 5.3 Files pushed (source / tests / audit / report only)

- `lifemate/lifemate_phone_callback_evidence.py` (module A)
- `lifemate/lifemate_evidence_lifecycle.py` (module B)
- `lifemate/lifemate_gates_adapter.py` (coordinator adapter)
- `analysis/gg_paired_audit.py`, `analysis/gg_shadow.py`
- `tests/test_phone_callback_evidence.py`,
  `tests/test_evidence_lifecycle.py`, `tests/test_gates_adapter.py`
- `research/lifemate/gg_phone_callback_notes.md`,
  `research/lifemate/gg_lifecycle_notes.md`, this report
- NOT pushed: sft files, data, traces, weights, raw environments,
  `sft_prototype_local.json`, any held-out content.

## 6. SHADOW integration brief for Codex

### 6.1 Hook location

Wrap `gate_read_before_write` at its single call site in the
agent loop with `adapter.decide(...)`. The adapter is a
read-only decision probe: it takes the proposal + prefix + roster
+ current request text and returns a `CandidateDecision`
(baseline fields + adjustment trail). It must never mutate the
proposal, submitted calls, state, retry count, or termination.

### 6.2 Allowed runtime data

- Raw prefix events in order: prior calls {tool, args, result,
  outcome, position, origin: history|session} + history user-turn
  texts {kind: user_turn, text, position}. The CURRENT proposal
  is never in the prefix; its arguments are never evidence.
- Roster: contacts search/get records [{id, name, phone}].
- Current request text (ASR transcript at runtime, as in shadow).
- Catalog kinds map (read/write per tool).
- Forbidden: gold labels, held-out content, future turns,
  `state.json` / environment internals (ToolEnv remains the only
  state access).

### 6.3 Ordering (per turn, per sample)

1. Grounding (unchanged, runs first, as configured).
2. Validate (schema check; unchanged).
3. Shadow guard: `adapter.decide(proposal, prefix, roster,
   current_text, kinds, proposal_position=max_prefix_pos+1)`.
   Log the full decision (baseline fired/applicable/reason +
   candidate fired + adjustments + notes incl. filtered_log_records,
   adapter_gaps, ledger_notes, mutation_fields).
4. Call (unchanged -- the shadow decision must not alter it).
5. Result-update: append the call + result to the prefix with
   origin "session" and its true outcome (succeeded / failed /
   schema_rejected / noop, derived from ok + done exactly as
   `result_succeeded` defines it). The ledger for the NEXT turn
   is rebuilt from this prefix; there is no cross-turn state.

### 6.4 Per-sample reset

Fresh ledger + fresh prefix per sample (the adapter builds both
from the passed prefix on every call; it holds no state between
calls). History prefix (pre-session turns) is never P3g-filtered;
only session-origin READ results are filtered, by the rule in
§2.5. Boundary: a mutation at exactly proposal_position counts
as "before"; always pass proposal_position = max prefix position
+ 1 (the default), never a stale or reused value.

### 6.5 Before / after logging (required fields per proposal)

Baseline: fired, applicable, reason. Candidate: fired,
adjustments[] (each: reference, old, new, mechanism, basis,
question_b, question_b_reason, sources), notes (filtered count,
adapter gaps, ledger notes). A shadow run is comparable iff
baseline fields are logged alongside candidate fields (as
`gg_shadow.py` does with `g2` + `g2_candidate`).

### 6.6 Non-interference: what is proven, what is NOT

- PROVEN for the offline shadow: `gg_shadow.py` only adds
  decision/candidate fields to rows; the adapter has no code path
  that mutates proposals, state, retry, or termination; paired
  and shadow runs are row-identical where the candidate makes no
  adjustment, and every adjustment is logged.
- NOT proven (BLOCKER for runtime integration): non-interference
  of the hook INSIDE the agent loop. This round changed no agent
  / inference code (brief-only, as specified). Before enabling
  the hook in the live loop, Codex must prove it by diffing
  submitted calls + final state + termination with the hook
  on vs off on identical inputs: any difference is a blocker,
  and the hook must ship behind a flag that defaults OFF until
  that diff is clean. The hook must also never be used to
  hard-enforce: enforcement needs the adoption bar in §4.5,
  which is not met.

## 7. Independent verification history

- Reviewer phase 1 (read-only): baseline gaps P2a/P2b (digit
  parser), P3c (roster-before-log), P3g (self-created log),
  P3h (nested phone dropped), C8 (binding must not mint roster),
  C9/C10/C11, L-series lifecycle gaps -- all incorporated.
- Reviewer phase 2 part 1 (modules): 7 FAILs found (R2-A1/A2/A3/
  A4/A5, R2-B1/B2) -- all fixed in-module with regression tests
  (§3.4 counts include them); paired + shadow verified unchanged
  after the fixes.
- Reviewer phase 2 part 2 (integration, pre-fix): CONDITIONAL GO
  for shadow-as-measurement, with FAIL-1 (P3g real-shape filter
  bug), FAIL-2 (direction-missing dialing records), FAIL-3
  (scene_run field name), plus C2 latent (name suppression) --
  all fixed and tested (see §2.5, adapter tests
  TestIntegrationReviewFails); paired + shadow verified unchanged
  after those fixes.
- Final delta verification: **GO for push + shadow brief.**
  Independent re-verification (41 assertions, 0 fail, plus 7 new
  self-set counterexamples all holding) confirmed all 12 delta
  items: R2-A1/A2/A3/A4/A5, R2-B1/B2, FAIL-1/2/3, C2 name
  resolution, paired + shadow unchanged (paired identical to
  /tmp/gg_paired3.json; shadow V10 row-identical), and the
  R2-A2 test update judged legitimate (it asserts MORE than the
  old test, with a clear contract citation; the no-selection
  AMBIGUOUS guard and the identity-consumer non-PROVEN guard are
  intact). Regression cross-check on frozen: 48/46/60/36/24, all
  OK. The 5 brief points it requires (P3g earlier-session
  residual, L8 unwired, no consumer->claim map, E1b boundary
  semantics, name suppression not end-to-end provable) are all
  already stated in §2.5/§4.3 above.
