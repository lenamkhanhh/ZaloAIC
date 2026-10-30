# Supplementary Report: Callback False-Binding Fixes (R1/R2/R3)

**Branch:** `gg-phone-callback-lifecycle` (same branch, new commit on
top of `9e3d827c`; no merge to main).
**Base verified:** workdir frozen from `9e3d827c`, all 11 pushed
file hashes re-checked equal before any edit.
**Scope:** shadow-only, no hard-enforce. No change to inference,
simulator, scorer, config, or split. No GPU, no model inference,
no training, no held-out, no SFT-branch change, no sample-specific
rule. Two threads (A: name + family, B: negation) owned separate
files; the coordinator integrated, ran paired/shadow, and owns Git.

## 0. Correction of the 9e3d827c "GO" claim

The previous round's GO applied ONLY to the scope of the checks
that were actually run (214 tests, paired gold, shadow
row-identity, two review rounds). It did not prove the absence
of false bindings, and Codex's three counterexamples prove it
did not hold outside that scope: all three are false bindings
the old adapter produced with `question_b=True`. This round
fixes those three classes. The verdict below is again scoped:
it covers the checks listed in §7, not a general proof of no
false binding.

## 1. Root causes

All three repros share one fixture (one history missed call with
a nested contact record, empty roster, `phone.call` proposal for
the logged id) and one verdict shape: `baseline_fired=True`,
candidate un-fired with `question_b=True`,
`bound_reference_selects_counterpart`. The existence half (a)
was true in all three; the selection half (b) was false. The
gate answered (b) with evidence that never established it:

- **R1 (name matching):** `_name_matches` matched on ANY token
  intersection (raw or folded). "Nguyễn An" matched the text
  "gọi lại cho Nguyễn Bình" on the shared token "nguyễn", so
  `name_filter` returned a unique match and the R2-A3 addressee
  veto never ran (it only runs when `named` is empty). A shared
  surname was treated as proof of the person.
- **R2 (family fallback):** "mẹ" sat in the addressee stoplist,
  so `_explicit_addressee` returned None (no veto) and the
  callback path fell through to `callback_single_incoming`,
  binding the sole caller. A family word was treated as "no
  constraint" instead of as a constraint needing its own
  evidence. One log record proves a caller exists; it says
  nothing about that caller being anyone's mother.
- **R3 (negation):** nothing in the pipeline examined whether
  the callback action itself was negated, corrected, or
  cancelled. `callback_reference_for` bound on name + callback
  phrase alone, so "đừng gọi lại cho Vy" bound exactly like
  "gọi lại cho Vy". Mention was equated with selection.

## 2. New question_b contract (three layers, kept separate)

An un-fire now requires ALL three, and each is recorded
separately in the adjustment trail:

1. **Existence / source (a):** a valid, active source for the
   reference (roster, log counterpart, user text, history text,
   read result) — unchanged from the previous round.
2. **Reference resolution (b1):** the current request's
   addressee resolves to THIS counterpart under the new name
   rules (§3) or the relation rules (§4). A mention in quoted
   content, in another clause, or in message content is not a
   resolution; it is recorded as mention info only.
3. **Positive action selection (b2):** the request positively
   selects this target FOR THE ACTION, judged by the negation
   module (§5). A negated, replaced, or cancelled selection
   never un-fires, even when (a) and (b1) hold. `mention_present`
   is carried alongside, never in place of, selection.

Final `question_b` in an adjustment = (a) AND (b1) AND (b2).
The raw A verdict is preserved as `question_b_a` when a veto
refuses an otherwise-established binding, so the layer that
refused is always visible.

## 3. R1 fix — name matching (thread A)

- Single-token names: exact token match, diacritic-sensitive,
  case-insensitive, never folded ("An" != "ăn").
- Multi-token names: FULL PHRASE only — all tokens in order,
  contiguous, raw or folded. A partial overlap (surname only,
  one shared token) never matches.
- Addressee extraction (`_extract_addressee`): quoted spans are
  stripped first; the addressee is the span right after a
  callback verb + "cho/tới/đến" in the FIRST callback clause
  (max 3 tokens, cut at clause/punctuation boundaries, titles
  like "anh Bình" trimmed). Names in other clauses, quotes, or
  message content are not addressees.
- Addressee-to-pool matching: exact full name, or a 1-token
  phrase equal to the candidate's LAST token and unique in the
  pool. A surname-only phrase never matches. An addressee that
  matches nobody yields `callback_name_mismatch` (veto); one
  matching several yields `callback_name_ambiguous`. Both block
  the topic/roster fallback — a contradicted addressee is not
  rescued by another path.
- Proper names are checked before the generic stoplist, so
  "Minh" (bare) stays a name while "mình" (diacritic) stays a
  pronoun. No name list, no gold label is used anywhere.

## 4. R2 fix — family / relation binding (thread A)

- A family/relation addressee ("mẹ/mạ/bố/ba/vợ/chồng/con")
  that does not match any candidate NAME under §3 goes down
  the relation path, never the sole-caller fallback.
- Relation binding requires STRUCTURED evidence attaching the
  relation to the counterpart: a `relation` field on a roster
  entry or on a log record (the log extractor now preserves
  this field), folded-equal to the requested relation. Reasons:
  `callback_relation_match / _ambiguous / _selects_other /
  _conflict / _unproven`.
- Without evidence: `question_b=None`, verdict AMBIGUOUS,
  reason `callback_relation_unproven`. The adapter returns a
  shadow verdict only — it never inserts an ask and never
  invents an action.
- Generic callbacks ("gọi lại người vừa gọi", "gọi lại số đó")
  carry no name/family constraint and keep the previous
  single-pool behavior unchanged.
- Name-first: a contact literally named "Mẹ" binds by NAME
  rules (single-token exact); a contact named "Mẹ Lan" does
  NOT bind on "mẹ" alone (partial overlap) and needs relation
  evidence like anyone else.

## 5. R3 fix — negation / correction (thread B + adapter gate)

New module `lifemate_callback_negation.py` (stdlib only, no
gates/provenance/phone-module imports), fixed interface:

```python
analyze_action_selection(text, target_names=(), target_phones=(),
                         action="call")
# -> {"selection": "positive"|"negated"|"replaced"|"cancelled"
#     |"unknown", "reason": str, "mention_present": bool}
```

Rules (clause-scoped, span-attached, never whole-sentence):

- Quoted spans are stripped before selection scanning; a
  mention only inside quotes yields `mention_present=True`
  but `selection=unknown`.
- Negation markers governing the action verb: đừng, chớ, khỏi,
  không cần, không + verb, không phải + verb. A bare "không"
  elsewhere is NOT action negation: question tails
  ("có ... không"), "không biết", words inside message content.
- Correction: "à không" / "ý là" after a positive selection +
  a different target with a verb → `replaced`; no new target →
  `cancelled`. The LAST decisive mention wins ("đừng gọi An,
  gọi lại cho Vy" → Vy positive; "gọi lại cho Vy, à không, gọi
  cho An" → Vy replaced). "không phải X mà (là) Y" → replaced;
  "không phải X" with no "mà" and no later verb → negated.
- Action scoping: "không cần nhắn, chỉ gọi lại cho Vy" →
  negated for message, positive for call. A negated message
  never vetoes a call, and vice versa.
- Value correction is NOT target replacement: "đuôi là sáu tám
  chứ không phải tám sáu" stays positive for the corrected
  number (the old tail is the replaced value, not the target).
- Past markers ("vừa/đã/mới" + verb) block the verb from
  counting as a request; correlative "vừa ... vừa ..." is
  exempt. Uncertain inputs → `unknown`, never a guess.
- The module is VETO-ONLY: "positive" means "no veto found",
  never proof of binding. It must never be used alone to
  un-fire; the adapter runs it only after module A established.

Adapter veto rule (`_vetoed_by_selection`, unit-tested):

- Callback proposals (phone.call → call; sms.send /
  chat_ott.send_message → message): a decisive veto (negated /
  replaced / cancelled) always vetoes; unknown vetoes EXCEPT
  `no_callback_verb` — when the current text contains no verb
  head of any action, B has no textual evidence to judge, so
  it abstains and a history-grounded binding (prior
  instruction, anaphoric chat reference) stands. B judges
  current-text selection only; it must not veto what it
  cannot see.
- Non-callback proposals: B does not cover the proposal's
  action, so only a decisive, TARGET-ATTACHED veto counts;
  unknown passes through, and a standalone generic veto
  ("đừng gọi nữa" with no target selection) does not veto an
  unrelated action. This closes a hole the coordinator's probe
  found mid-round: a negated callback sentence ("đừng gọi lại
  cho Vy") used to un-fire an ewallet.transfer proposal via
  callback binding. Topic/amount bindings with no callback verb
  (gold 1319) pass through untouched.

Delta-2 (coordinator fix for the final reviewer's hole, see
§8): the first version of the abstention rule let B's
fallback reason `no_action_evidence` abstain for callback
proposals, but that reason conflated three situations: (a)
truly no callback verb of any action, (b) a verb of ANOTHER
action ("nhắn lại cho Vy" + phone.call proposal), (c) a verb
that is BLOCKED (question mood "có nên gọi lại cho Vy
không", past "đã gọi lại cho Vy rồi", "chưa gọi lại cho
Vy"). Cases (b) and (c) un-fired falsely through the
abstention. The fallback now splits into `no_callback_verb`
(abstain), `other_action_verb_only`, `blocked_verb_only`, and
`negated_other_object` (all veto for callback proposals),
plus `quoted_mention_only` (veto). "trả lời" (reply) was also
added to B's message verb patterns, so it selects for
sms.send and vetoes (other-action) for phone.call. The old
`no_action_evidence` reason survives only for the empty-text
early return, where the adapter vetoes it like any other
unknown reason. One residual of the same shape remains: an
action verb OUTSIDE B's inventory ({gọi, điện, nhắn, gửi,
sms, trả lời}) is invisible to B and abstains like a
verb-less text — see §9.

Target descriptors for the veto (`_selection_targets`): the
bound counterpart's full name(s) + last token(s) (so "đừng gọi
An" vetoes a bound "Nguyễn An"; a bare surname never vetoes)
and its known phone numbers from roster/log records (so a
number-based veto blocks an id proposal for that number's
owner).

## 6. Before / after (user fixture, run on 9e3d827c then fixed)

| Case | Before (9e3d827c) | After |
|---|---|---|
| R1: log "Nguyễn An", "gọi lại cho Nguyễn Bình giúp tôi" | un-fire, question_b=True, bound_reference_selects_counterpart | fires, `callback_name_mismatch` |
| R2: log "Vy", "gọi lại cho mẹ giúp tôi" | un-fire, question_b=True, bound_reference_selects_counterpart | fires, `callback_relation_unproven` |
| R3: log "Vy", "đừng gọi lại cho Vy" | un-fire, question_b=True, bound_reference_selects_counterpart | fires, `callback_selection_veto`, selection negated, mention_present=True recorded separately |
| Control: log "Nguyễn An", "gọi lại cho Nguyễn An giúp tôi" | un-fire | un-fire (unchanged) |
| Control: log "Vy" + relation "mẹ", "gọi lại cho mẹ giúp tôi" | (would have un-fired via fallback) | un-fire via `callback_relation_match` |
| Control: log "Vy", "gọi lại người vừa gọi" | un-fire | un-fire (generic path untouched) |

## 7. Verification

### 7.1 Tests (frozen candidate, both backends, 0 fail/error/skip)

| Suite | System python3 | Venv python |
|---|---|---|
| test_lifemate_gates (old) | 48 OK | 48 OK |
| test_lifemate_provenance (old) | 46 OK | 46 OK |
| test_phone_callback_evidence (old + 1 updated) | 60 OK | 60 OK |
| test_evidence_lifecycle (old) | 36 OK | 36 OK |
| test_gates_adapter (24 old + 22 new) | 46 OK | 46 OK |
| test_name_binding (new, thread A) | 29 OK | 29 OK |
| test_callback_negation (new, thread B) | 39 OK | 39 OK |
| test_unfire_controls (new, coordinator) | 2 OK | 2 OK |
| **Total** | **306** | **306** |

Updated old test (1, with citation): `test_callback_family_reference_no_veto` — its old expectation (family binds via single-pool fallback) directly contradicts the new R2 contract; it now expects `None + callback_relation_unproven`. Two coordinator tests written on wrong premises were REPLACED, not patched to green, after probes showed the premises false: (a) a direct-negation phone case is already refused by module A (`value_negated_in_current_text`), so the B-veto phone test now uses the correction case where A establishes and B vetoes (`replaced`); (b) a contacts.update proposal never un-fired via callback binding (membership required, C8), so the non-callback boundary test now uses the real ewallet P4b case plus a unit test of the veto rule itself.

### 7.2 Un-fire quality controls (synthetic, NOT merged with gold)

`tests/test_unfire_controls.py` measures five categories
separately over one fixture family (single missed call, empty
roster, phone.call proposal), plus structural pins:

| Category | Cases | Result |
|---|---|---|
| correct_unfire | 8 (full name, generic, relation evidence, short unique, question-"không", other-clause positive, action-scoped positive, distractor) | all pass |
| false_unfire | 13 (name conflict, surname-only, family w/o evidence, family conflict, negated, "khỏi", corrected, quoted-only, addressee-switch, cross-action verb, question mood, past action, "chưa" status) | 0 (all still fire) |
| refusal | 5 (mismatch, relation-unproven, veto, replaced, generic veto) | all refused with mechanism recorded |
| false_block | 4 (exact full name, relation evidence, contact named "Mẹ", generic) | 0 (all still un-fire) |
| unknown_ambiguous | 2 (short ambiguous name, family unproven) | all fire, never guessed |
| empty-prefix control | 1 | fires (no vacuous pass) |

Synthetic variants of one fixture are NOT counted as
independent model positives and are never merged with gold.

### 7.3 Paired gold audit (dev 1237, frozen snapshots, identical inputs)

| | 9e3d827c candidate | Fixed candidate |
|---|---|---|
| Applicable | 976 | 976 (scope unchanged) |
| Fired (false blocks on gold) | 1 (0.10%) | 2 (0.20%) |
| Decision changes vs baseline | 14 un-fires | 13 un-fires |
| New un-fires | — | 0 |
| Errors | 0 | 0 |

Exactly ONE decision changed vs 9e3d827c: **train_1005 pos1**
(sms.send c_778) now fires. Analysis, not a regression to
patch around: its current text "nhắn lại mạ" is a family
addressee, the roster is empty (no contacts.search in
history), and the message record carries no `relation` field,
so under the new contract there is no structured relation
evidence. Gold knows c_778 is the mother; the runtime cannot
observe that from any allowed source, and the assistant's prose
("Mạ nhắn…") is deliberately NOT counted as relation evidence
(it is not a structured field). The count was NOT forced back
to 1/976: the rule stands as specified, and 1005 is the honest
cost of closing the R2 fallback.

The second candidate from the first post-fix run, train_0764
(phone 09020000652, prior-instruction binding), was initially
lost to a B unknown-veto and then RESTORED by the
`no_action_evidence` abstention (§5): its current text has no
callback verb at all, so B abstains and the history-grounded
binding stands. The abstention is scoped to that exact reason,
not a general loosening: quoted-only mentions, missing text,
and invalid actions still veto for callback proposals.

All other 12 gold un-fires are unchanged (11 phone incl. tail
correction 1677, which B now confirms positive via the value-
correction rule; 1033 name binding, B positive; 1319
topic/amount, B unknown → non-callback pass-through, as
designed). The remaining candidate fire besides 1005 is the
train_1696 anomaly itself, unchanged and kept separate.

### 7.4 Model-trace shadow (V10/V11/V13)

Zero diffs vs the 9e3d827c candidate on all three versions:
decisions, adjudications, AND `g2_candidate` fields identical
(0/0/0). Expected: model-trace blocks are prover-driven, and
Gate 2's few fires there are hallucinated ids with no
phone/callback evidence to un-fire or veto. The fix changes no
model-trace outcome; it changes gold-audit outcomes only where
the new contract says the old binding was false (1005).

## 8. Independent verification

Final reviewer (read-only, own counterexamples beyond author
fixtures, 38 cases + follow-ups): **CONDITIONAL GO** for push +
shadow brief — not unconditional, not NO-GO. It confirmed: the
three original repros fixed with the right mechanisms; R1
probes all pass (diacritics, Minh/mình, titles, token order,
short-name ambiguity, quote, multi-clause, surname-only,
vocative); R2 probes pass (relation via roster/log, conflict,
"Mẹ Lan", "bố" vs "ba" correctly NOT matching, two claimants,
generic + family token in another clause); decisive R3 vetoes
pass (correction across actions, general veto, other-clause
negation, action scoping, purpose tail, past + new request,
conditional per P4b scope); paired re-run matches §7.3
(976/2, dropped only 1005); shadow V10 0-diff; suite 302 at
that time; both updated old tests judged legitimate.

It also found ONE systematic hole the author fixtures missed
(X1/X2/G9/G10/G11, same root cause): B's fallback reason
`no_action_evidence` conflated "no callback verb of any
action" (legitimate abstention, gold 0764) with "verb of
another action" ("nhắn lại cho Vy" + phone.call, and reverse)
and "blocked verb" (question mood, past, "chưa"). All three
un-fired falsely through the abstention. The reviewer also
noted, honestly, that its own first 3 family probes were
fixture errors (relation placed at record top level instead
of inside the nested contact dict), corrected on re-run; and
that one quoted-name outcome is correct via B's veto even
though A still binds from the quote (defense in depth, but
fragile layering — recorded, not fixed, in this round).

Coordinator response (within scope, no planning engine): the
delta-2 fix in §5 (reason split + "trả lời" as a message verb)
closes the hole, with regression tests for X1, X2, G9, G10,
G11 and the reply verb, plus 4 new controls cases. After the
fix: repros R1/R2/R3 still refuse; suite 306/306 both
backends; paired still 976/2 with dropped-only-1005; shadow
still 0-diff on all versions. HONEST LIMIT: the delta-2 fix
itself was verified by the coordinator (tests + paired +
shadow + repros), NOT re-reviewed by an independent agent.
The brief must carry the reviewer's conditions as history:
the pre-delta-2 abstention was a known false-un-fire class,
now fixed and regression-tested, but not independently
re-reviewed; and shadow un-fire counts must not be cited as
hard-enforce evidence.

## 9. Still unsupported / known boundaries (not solved, not hidden)

- Relation matching is folded string equality on the `relation`
  field only: synonyms ("bố" vs "ba") do NOT match, and prose
  ("Mạ nhắn…") is never relation evidence. A relation stated
  only in message content cannot bind.
- B does not model question frames beyond `có ... không`,
  vocative/imperative address ("Vy ơi, gọi lại đi"), reported
  speech ("Vy bảo mai gọi"), past-negated statements
  ("không có gọi cho Vy" reads positive for the verb), or
  action verbs outside its inventory ({gọi, điện, nhắn, gửi,
  sms, trả lời}): such a verb is invisible to B and abstains
  like a verb-less text. Binding in those cases rests on
  module A alone, as before.
- B's short-name handling depends on the adapter passing the
  resolved short form (full name + last token); a short form A
  did not resolve is invisible to B.
- Double negation reads as negated (safe-direction false
  block, not a false un-fire).
- Quoted names: A may still bind from quoted content in some
  paths; the correct outcome currently relies on B's
  `quoted_mention_only` veto (defense in depth, fragile
  layering — a future round should make A quote-proof).
- Non-callback proposals: a standalone generic veto does not
  veto them (by design); only target-attached decisive vetoes
  do. Whether a cancelled callback should block an unrelated
  action to the same person is undecided and out of scope.
- "tư" for digit 4, spaced digit strings, compound spoken
  amounts, ASR digit loss, and semantic coreference beyond
  name/topic/amount/time remain BLOCKED, as in the previous
  round.
- Prover observation expiry is still NOT wired (only Gate 2
  has the ledger), eligibility suppression is still NOT wired,
  and independent model positives are still 1 (train_0004).
  None of these is addressed by this round, and none may be
  cited as resolved by it.
- Final verdict: SHADOW CANDIDATE ONLY, not hard-enforce-ready.

## 10. Reproducibility

- Base: branch `gg-phone-callback-lifecycle` @ `9e3d827c`
  (frozen snapshot `~/workspace/zaic-gg-candidate-frozen/`,
  hashes re-verified before editing).
- Candidate workdir: `~/workspace/zaic-gg-fix-candidate`;
  frozen runs: `~/workspace/zaic-gg-fix-frozen/`.
- Repro (before fix, from the base frozen dir; after fix, from
  the candidate frozen dir):
  `PYTHONDONTWRITEBYTECODE=1 python3 /tmp/repro_r123.py`
  (fixture verbatim from the task; adapter `decide` with the
  given prefix/proposal/kinds).
- Paired gold (frozen candidate dir):
  `python3 analysis/gg_paired_audit.py --train-jsonl
  ~/workspace/zaic-data/lifemate/extracted/train+public_test/train/train.jsonl
  --data-root ~/workspace/zaic-data/lifemate/extracted/train+public_test
  --split lifemate/splits/train_dev_heldout.json --lifemate-dir
  ~/workspace/zaic-gg-fix-frozen/lifemate --out-json /tmp/gg_paired_fix3.json`
- Shadow (same flags, `--trace analysis/runtime/<version>.json
  --version <v10|v11|v13>`).
- Regression: `python3 tests/test_<suite>.py` and
  `~/workspace/zaic-test-venv/bin/python tests/test_<suite>.py`
  for the 8 suites in §7.1.
- Dependencies: stdlib only for all new/changed modules.
  Data: dev 1237 only; held-out never opened. No sample id or
  gold value appears in runtime logic (1005/0764/1319/1696
  appear only in audit/reporting contexts, never in gate,
  evidence, adapter, or negation logic).

## 11. Files pushed (same branch, no merge)

- `lifemate/lifemate_phone_callback_evidence.py` (thread A)
- `lifemate/lifemate_callback_negation.py` (thread B, new)
- `lifemate/lifemate_gates_adapter.py` (coordinator wiring)
- `tests/test_phone_callback_evidence.py` (thread A, 1 update)
- `tests/test_name_binding.py` (thread A, new)
- `tests/test_callback_negation.py` (thread B, new)
- `tests/test_gates_adapter.py` (coordinator, R1/R2/R3 + veto)
- `tests/test_unfire_controls.py` (coordinator, new)
- `research/lifemate/gg_phone_callback_notes.md` (thread A append)
- `research/lifemate/gg_callback_fix_r1r2r3_report.md` (this report)
- NOT pushed: lifecycle/prover files (untouched), sft files,
  data, traces, weights, raw environments, held-out content.
