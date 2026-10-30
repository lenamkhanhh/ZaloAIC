# G&G selection round — chat2 gaps closed on the passed path (shadow-only)

Branch: `gg-r5-number-lifecycle-shadow`, on top of commit 1
(`4fcb0bc4`, the observer import fix). No merge to main, no GPU,
no simulator/scorer/model-config change, no chat2 expected-value
change, no MEMORY edit. State: **CPU-verified only, shadow-only,
not hard-enforce-ready** (same standing as R5).

## 1. What was broken

Chat2's independent evaluation of `d1090d1d` left 3 contract bugs
and 5 scope gaps open. The scope gaps shared one root cause:
`decide()` ran its selection check (adjustment 1) **only on the
fired path**. A proposal the baseline gate PASSED received no
selection check at all — a confirmed number / ID was waved
through before anyone checked the right person, the right action,
or the right role for that number. Repro on the commit-1 tree
(`zaic-selcheck-probes/sel_repro.py`, local only, 38 cases):
**28 OK / 10 MISMATCH**, and the 10 mismatches were exactly the
target cases (5 fired-path veto failures with `mechs=[]` on the
passed path proving no check ran there).

## 2. Fixes

### 2.1 Thread-B fixes (fired path, `lifemate_callback_negation.py`)

- **SEAL-003** (emphatic negation): `_PARTICLES` gains `"mà"`.
  "Đừng có mà gọi" and "Đừng mà gọi" now negate; "Nhưng mà gọi"
  and "mà nhớ gọi" stay positive (the bridge only extends a
  real "đừng" backward search, consecutive tokens only).
- **SEAL-004 / WH-USER** (echo-questions): `_clause_is_question`
  gains the "nhỉ" rules — toned "nhỉ" always a question particle;
  toneless "nhi" only with a digit run in the clause and the
  previous token not "cho" (so "Gọi cho Nhi" stays a request).
  Plus question-clause verb blocking inside
  `analyze_action_selection` (main verb loop AND fallback
  polarity computation), so a questioned verb reads "blocked",
  never positive.
- **ATK-019** (bare "chuyển"): `["chuyen"]` joins
  `_FORWARD_PATTERNS` and `_OTHER_VERB_PATTERNS` (longest match
  keeps "chuyển tiếp / tiền / khoản" winning). The existing
  forward guards supply the phone-shaped + cho/tới/đến + person
  restriction, so money transfers and "chuyển sang" do not
  suppress anything.
- **Purpose-clause scope guard** (found by pinned tests, see §5):
  a bare trailing "không"/"hả"/"chứ" questions the opening verb
  ONLY when no purpose marker ("để") or second verb head
  intervenes — "gọi … để hỏi xem có rảnh không" is a request
  to call (pinned positive), not a question about calling.
  A question particle scopes to the nearest verb phrase.
- **Qualifier span fix** (red-team RT-07): `_extract_object`
  skips "mới"/"cũ" between "số" and a digit run without
  consuming span budget — "số mới X" is one phone mention, so
  X stays governed instead of falling past the 3-token cap.
  The skip applies only when a digit run follows immediately.

### 2.2 New passed-path check (adapter `decide()`)

New exported function `analyze_selection_consistency(text,
action, target_names, target_phones, roster, history_texts)`,
wired into `decide()` **after adjustment 2, before eligibility**,
gated to `not baseline.fired and not fired`, callback proposals
only, non-empty current text, non-empty selection targets.
On mismatch it appends one adjustment (`mechanism:
"selection_mismatch"`, `old: "passed"`, `new: "fired"`).

**Pin boundary (load-bearing):** when the baseline fired, an
un-fire rests on a specific A+B+layer-C binding the current text
does not cancel (pinned veto-only contract, incl. gold 1319 and
`positive_action_no_target_veto`). Re-vetoing there would break
pinned bindings, so the check never runs on that path.

Sub-checks, in order (first mismatch wins; abstention never
fires — UNKNOWN is not a contradiction):

1. delegation (`turn_fully_delegated`);
2. duplicate_name — a positively governed name maps to ≥2 roster
   phones, the proposal is one of them, no number in the text
   picks between them, and no history turn qualifies the name
   (any content token adjacent to the name in a history turn,
   e.g. "Minh khách hàng");
3. B decisive vetoes (negated / replaced / cancelled);
4. early matched-pass — the positive selection set (including
   correction re-scoping) contains the proposal; an exact
   same-action match passes (multi-person calls), and an
   ambiguous-name-only set passes when no explicit entry/phone
   selection contradicts it (the explicit number wins over an
   ambiguous name);
5. B unknown-mismatch mapping (`other_action_verb_only` →
   action_mismatch, `blocked_verb_only` → blocked_request,
   `negated_other_object` → negated,
   `number_as_content_for_other_recipient` →
   money_or_content_role). Two deliberate non-mappings:
   `positive_verb_not_governing_target` is subsumed by check 6
   when a verb governs an explicit non-target, and abstains on
   bare/pronoun verbs (an anaphoric or bare verb is not a wrong
   selection); `blocked_verb_only` defers to history — a prior
   turn that positively selected this proposal stands, because
   a blocked verb is "no current signal", not a cancellation;
6. positive-selection-set mismatch (wrong_person /
   action_mismatch / selection_mismatch). The action_mismatch
   branch abstains when a verb of the proposal action exists
   AND the proposal person is mentioned (a bare verb with a
   discourse recipient is an implicit selection);
7. money_or_content_role — every proposal-phone run is a money
   role ("tiền X" / "X đồng/nghìn/triệu/tỷ/vnd") or an
   old-number role ("số cũ/trước X" / "X là số cũ");
   "số mới" is a correction/selection, never old-role;
8. bare_or_question_mention — the target is mentioned but only
   in question clauses, or the text has no verb of any action.

Correction re-scoping: a bare recipient clause ("cho Tuấn")
immediately after a correction clause ("à không",
comma-separated) rebinds the nearest preceding positive
callback verb's recipient.

Person identity is a roster-entry index when a name/phone
resolves to exactly one entry, else the raw folded name /
normalized digits — so a name and a phone of the same entry
(with or without an id) resolve to the same key.

## 3. Results

- Repro: **38/38** (was 28/38). All 5 fired-path cases now fire
  via `callback_selection_veto`; all 5 scope gaps now fire via
  `selection_mismatch`; all 28 controls still pass.
- Full regression: **669/669 BOTH backends** (0 fail/error/skip;
  +54 vs the obsfix 615: 17 from `lifemate/tests/test_lifemate.py`
  (counted here, not in the obsfix tally) + 9 B-level + 28
  adapter-level incl. the 10 target cases, positive controls,
  history, correction, pronoun, callback-back, and
  qualifier-span cases).
- Paired gold audit: **byte-identical to the commit-1 control**
  — baseline 15/976, candidate 2/976 (train_1005, train_1696),
  same 13 un-fires, 0 errors. The check adds **zero** net fires
  on gold (see §4 for why that is the honest outcome, not a
  loosened one).
- Shadow control: **identical to the commit-1 control** — V10 14
  rows (passed 8 / blocked 6; correct_block 6 / false_block 0 /
  correct_pass 3 / miss 5), V11 10 rows (passed 4 / blocked 6;
  6 / 0 / 2 / 2 in the same order), V13 29 rows (blocked 16 /
  passed 6 / out-of-scope 7; correct_block 16 / false_block 0 /
  miss 6 / out_of_scope 7, adjudicated n=22). No decision
  changed.
- Shadow validity ON: reproduces R5 exactly — only V10 changes
  (2 rows, both train_0008 TEXT arm; correct_block 6→8, miss
  5→3, false_block still 0). V11/V13 unchanged.
- Shadow eligibility ON: adjudications identical to control on
  all three versions (row diffs are report fields only).
- Red-team batch (local probe, 22 NEW counterexamples:
  multi-action, vocative fronting, toneless forms, corrections,
  forward variants, positive controls): **22/22** after
  adjudication (see §5).

## 4. Paired deltas: all 8 initial fires were gold-correct

The first paired run showed 8 new candidate fires. Every one
was adjudicated against the sample's current text AND history,
and every one was a gold-correct call the check over-fired on —
each fixed by a general mechanism, never by loosening:

| Sample | Shape | Fix (general mechanism) |
|---|---|---|
| train_0063, train_0225 | duplicate name, history qualified it ("Minh/Hương khách hàng") | history-qualification abstention (§2.2 check 2) + ambiguous-name compatibility (§2.2 check 4) |
| train_0509, train_0947 | pronoun object ("cho anh ấy", "nhắn hắn") | `positive_verb_not_governing_target` dropped from the mapping (§2.2 check 5) |
| train_1662 | bare "gọi lại" to a log-grounded missed number | same drop (bare verbs are not contradictions) |
| train_0672 | past-tense current verb, history explicitly requested the call | blocked defers to history-positive (§2.2 check 5) |
| train_1162 | recipient correction ("cho ông Ba, à không, cho Tuấn") | correction re-scoping + early matched-pass (§2.2 check 4) |
| train_1481 | bare message verb, discourse recipient, call cancelled ("à thôi") | action_mismatch abstention (§2.2 check 6) |

No delta was hidden and none was preserved by loosening: after
the fixes the paired output is byte-identical to control.

## 5. Pinned-test incidents (design corrected, not loosened)

Three pinned tests broke during this round; all three were
investigated before any test was touched:

- `test_purpose_clause_trailing_khong_positive` and
  `test_r3_question_khong_positive_still_unfires` ("gọi lại cho
  Vy để hỏi xem có rảnh không"): the question-verb blocking was
  too broad — the trailing "không" belongs to the purpose
  clause, not the call verb. Fixed in code with the purpose
  scope guard (§2.1). Both tests pass unchanged.
- `test_unknown_actions` ("Chuyển số X cho Vy giúp tôi"):
  bare "chuyển" is now a recognised forward/transfer verb, so
  `instruction_action` correctly returns "other", not "unknown"
  — the same contract-change pattern the test file itself
  documents for "gửi tiền" (round-4 S3), where both labels veto
  in layer C. Only that line's expectation changed, with a
  contract-change comment; the "Báo số …" line still returns
  "unknown".

Red-team adjudication: 19/22 passed immediately; RT-14 was a
probe bug (passed a contact id as a phone number); RT-17's
expectation was wrong (forwarded content for Lan IS a
content-role fire, same family as the money role); RT-07 was a
genuine bug fixed by the qualifier span skip (§2.1).

## 6. Known limitation (carried open, not fixed)

**RT-16:** a và-chain of 3+ people ("Gọi cho Bình và Lan và Mẹ")
exceeds the 3-token object span, so the third person is not
governed and a call to them fires wrong_person. Fix direction:
extend the object span across và-chains. Out of this round
because `_extract_object` is shared with the fired path — the
change needs its own design and regression, not a drive-by
widening.

## 7. Observer log (unchanged)

RAM-only, as in commit 1: `loop.observer.records` /
`loop.observer.to_json()`; no automatic file output exists.
Export = the caller writes `to_json()` output to a file.

## 8. Commands (workspace-independent)

```
python3 tests/test_callback_negation.py
python3 tests/test_gates_adapter.py
python3 analysis/gg_paired_audit.py --train-jsonl <data>/train/train.jsonl \
  --data-root <data> --split lifemate/splits/train_dev_heldout.json \
  --lifemate-dir lifemate --out-json <out>
python3 analysis/gg_shadow.py --trace analysis/runtime/<e1_v10|e6_c_v11|e5_v13>_diagnostic_trace.json \
  --version v10|v11|v13 --train-jsonl <data>/train/train.jsonl \
  --split lifemate/splits/train_dev_heldout.json --lifemate-dir lifemate \
  [--validity] [--eligibility] --out-json <out>
```

where `<data>` is the extracted `train+public_test` directory.
Local probes (`sel_repro.py`, `sel_redteam.py`) are NOT pushed;
they live in the operator's probes directory.

## 9. Handover note for chat2 (independent re-evaluation)

- New tip: this commit (see push verification below).
- Their `_load_adapter` still needs the 2-line loader patch
  from the commit-1 handover (repo root on sys.path +
  `import lifemate.lifemate_gates_adapter`) — the package-mode
  adapter cannot load via the old top-level import.
- No expected values changed. The 10 target cases (SEAL-003a/b,
  SEAL-004, WH-USER, ATK-019, ATK-001/007/009/014/015) are covered
  by new tests in `tests/test_gates_adapter.py`
  (`TestSelectionRoundAdapter`) and B-level tests in
  `tests/test_callback_negation.py` (`TestSelectionRoundB`).
- Shadow-only: nothing here blocks a real call. The guard
  remains a shadow candidate; hard-enforce still needs the
  model-scale port + OFF-vs-ON proof from the R5 §7 brief.
