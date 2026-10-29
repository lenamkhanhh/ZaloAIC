# G&G — Phone evidence + history/callback contract (Thread A)

Module: `lifemate/lifemate_phone_callback_evidence.py` (new, stdlib
only, no import of gates/provenance — the coordinator wires it in).
Tests: `tests/test_phone_callback_evidence.py` (new, synthetic
only). No gate, provenance, audit, simulator, scorer, config, or
SFT-branch file was touched. No git command was run. No training,
GPU, inference, held-out, or paid API. Verdicts here are about
EVIDENCE, not about score: nothing is hard-enforced and no score
increase is claimed.

## 1. Verified contract table (read from zaic_tools code, not assumed)

| Tool | Implementation fact | Consequence for evidence |
|---|---|---|
| `phone.call` | Always `ok True`; appends a call record; `contact_ref` completes contact_id/phone ONLY on a unique roster match, never rejects | Its result `phone_number`/`contact_id` is an ECHO of the argument (or of the unique roster match). Never an independent source. |
| `sms.send` | Same shape: always `ok True`; message record echoes the argument | Same echo exclusion. |
| `phone.recent_calls` | `read("calls")`: returns the whole call log | A SUCCEEDED result's `phone_number` field is observed log evidence for the NUMBER. History-shaped results additionally carry a nested `contact: {id, name, phone}` plus `direction` (`incoming`/`outgoing`) and `status` (`missed`/`completed`) — the state-shaped records do not carry direction. |
| `sms.read_recent` | `read("messages", eq={contact_id})`: returns message records with `contact_id`, `phone_number`, `direction`, `content` | A SUCCEEDED result's `phone_number`/`contact_id` fields are observed log evidence for the counterpart. `direction == "incoming"` matters for reply binding. |
| `chat_ott.read_chat` | Returns `messages` with `from`, `content`, `time` (no structured counterpart) | Content numbers are `read_result` observations (existence only), never contact records. `time` enables "newest" selection. |
| `contacts.search` / `contacts.get` | Reads over `contacts.contacts`; search matches substring (lower, no diacritics) on name/relation/phone | Returned records ARE roster-equivalent membership evidence. |
| `contacts.update` / `contacts.delete` | `patch` / `delete`: find-or-noop — a SUCCEEDED call provably looked the id up | Patch-verified: a succeeded update whose returned record id equals its `contact_id` argument proves membership. A log counterpart alone does NOT prove it. |
| `ewallet.transfer` | Records `"to": contact_id or phone`; no contact validation (phone→contact completion only on unique match) | Like phone/sms: an observed counterpart suffices for execution, but does not prove roster membership. |
| `base.contact_ref` | Phone→contact completion ONLY on exactly one roster match; two matches complete nothing | Roster phone evidence requires a UNIQUE match. A duplicate-phone roster entry is ambiguous evidence, never a source. |
| Executor | A call is REJECTED (`ok False`) ONLY on schema error; anything else returns `ok True, done False` with state unchanged | Only `ok True` AND `done is not False` counts as "succeeded" evidence. Schema-rejected / failed / noop results establish nothing. |

Two adapter warnings for the coordinator (found while reading, not
fixed here — out of Thread A scope):
- The gates' `flatten_result_entries` DROPS every field named
  `phone`, so a history `recent_calls` record's nested
  `contact.phone` is invisible to the current audit flattener. The
  coordinator's adapter must extract `contact.phone` explicitly
  (this module's `extract_log_records` already does).
- History `recent_calls` records carry `direction`/`status` that
  state-shaped records lack; the adapter must preserve them, or
  callback binding loses the incoming/missed distinction.

## 2. Root cause of the 11 phone residuals (grouped, no values)

The old gate accepted a phone number ONLY from (a) a unique roster
match or (b) a `phone_number` field in a succeeded
`phone.recent_calls` / `sms.read_recent` result. Every residual
fails one of those two narrow rules for a different, legitimate
reason:

| Group | Count | Why the old gate fired | What this module adds |
|---|---|---|---|
| Spoken digits in the current request (hotline + mobiles, comma-grouped or space-separated) | 5 | The number exists only as Vietnamese digit words in the request text; the old gate reads no text | `parse_phone_mentions`: digit-word runs (không/một/…/chín, commas don't break runs) → `norm_phone`, role `requested_target` |
| Digits in the current request | 1 | User-stated digits were not a source at all | Same path, `kind: digits` |
| Spoken digits in the current request (second batch) | 1 | Same as above | Same path |
| Tail correction against a history number | 1 | Current text states only a corrected TAIL ("đuôi là X chứ không phải Y"); the full corrected number exists nowhere verbatim | `parse_tail_correction` + `apply_tail_correction`: old tail must match a history number's tail exactly; only the tail is replaced; the result is a BINDING claim (user-specified target), never an existence claim |
| Prior-instruction reference ("làm như em dặn lúc nãy") | 1 | The number lives in a history USER turn's conditional instruction, not in any log field | `bind_history_reference` prior-instruction branch: most recent history user turn with a `requested_target` phone mention; multiple numbers in that turn → no bind |
| Chat-content number + "số mới nhất / số đó" | 1 | The number lives in a chat message's CONTENT (three numbers across three messages: old line, accounting number, new incident line) | `read_result` observation + anaphoric binding: "mới nhất" + message `time` selects the newest; topic overlap is the fallback; anything else stays ambiguous |
| Anaphoric "số đó" to a history chat read | 1 | The number lives in a history `read_chat` result's content, restated in the assistant turn | Anaphoric binding over the latest chat read's messages (all messages of one result share a position, so all are considered together); exactly one distinct number required |

Note on method: these groups shaped the DESIGN (the brief orders
reading every case first), but no sample ID and no gold value
appears in the module logic. Generality is argued by the synthetic
tests (§5), not by the residuals; the coordinator's paired audit
on the full dev set is the independent check.

## 3. Root cause of the 3 callback cases (regression cases, not law)

The old G2 rule accepted a `contact_id` ONLY from the contacts app
(registry `contacts.contacts`). All three cases are log-only
counterparts, and the old rule fired on them:

- A reply target observed in a succeeded `sms.read_recent` result
  (incoming message; the current request replies to its topic).
- A callback target observed in a succeeded `phone.recent_calls`
  result (incoming MISSED call; an outgoing distractor record
  sits in the same result — binding must prefer incoming/missed
  and use the name when given).
- A transfer target observed in a succeeded `sms.read_recent`
  result (incoming message; the current request names the person
  and the refund amount, which the message content carries).

The contract correction: `sms`/`phone` never validate contacts, so
for `phone.call` / `sms.send` / `ewallet.transfer` an observed log
counterpart is sufficient FOR EXECUTION — but it is still NOT
roster membership, and the verdict says so explicitly. For
`contacts.update` (patch-verified) the same counterpart is
AMBIGUOUS, never PROVEN. A `contact_id` found only in free text,
or as another registry's foreign key, is never a source for any
consumer. The three cases are regression tests for the old rule,
not a new global registry relaxation: no registry mapping was
widened.

## 4. Interface (binding for the coordinator)

Evidence record (dict, JSON-able):
`{"kind": "phone"|"contact", "value": <normalized phone digits per
_norm_phone, or id / folded name>, "source": "roster"|"call_log"|
"message_log"|"user_text"|"history_text"|"read_result", "producer":
<tool name or "user">, "field": <e.g. "phone_number",
"result.phone_number", "current_text",
"current_text_tail_correction", "result.messages[].content",
"bound_history_record">, "outcome": "succeeded"|"failed"|
"schema_rejected"|"noop", "counterpart": <record identity dict
{tool, position, record_id, contact_id} or None>, "position":
<int, index in the prefix; -1 for session-level roster / current
text>, "claim": "existence"|"binding", "status": "active"|
"ambiguous"|"unknown", "reason": <short machine-readable str>}`.

Verdict (dict):
`{"established": bool, "basis": "source"|"binding"|None,
"question_a_sources": [evidence...],
"question_b_target_selected": True|False|None,
"question_b_reason": str, "decision": "PROVEN"|"AMBIGUOUS"|"UNKNOWN"}`.

Decision rule (exact): PROVEN iff valid (active) sources exist AND
question (b) is True. AMBIGUOUS iff valid sources exist but (b)
is None (selection undetermined) — including the
observed-counterpart-with-membership-required case. UNKNOWN iff
no valid source. `established` is True exactly for PROVEN.
`basis` is `"source"` when establishment does not depend on
binding (roster, log, read-result, direct user-text target) and
`"binding"` when it rests on a bound history reference or a tail
correction.

Functions (all in `lifemate_phone_callback_evidence.py`):
- `parse_phone_mentions(text)` → mentions with raw / normalized /
  span / kind (digits|spoken) / role (requested_target | negated |
  corrected_away | background | ambiguous) / reason. Non-phone
  runs (money, time, date, order codes, short tails) are NOT
  returned; see `find_digit_runs` + `classify_phone_context`.
- `classify_phone_context(text, run)` → money | time | date |
  order_code | other_number | phone | ambiguous, from ADJACENT
  cues (an adjacent unit wins over distant cues of another kind).
- `parse_tail_correction(text)` / `apply_tail_correction(number,
  correction)` — explicit "đuôi là X chứ không phải Y" only; the
  number must already end with the old tail.
- `parse_history_result(raw)` → `{status: ok|malformed, value,
  reason}`. dict/list pass through; strings via `json.loads` then
  `ast.literal_eval`. NEVER `eval`; never char-wise zip; malformed
  yields a reason, never a crash or a guess.
- `extract_log_records(result, tool, position)` → structured
  records (nested `contact` dicts unpacked; `time` preserved;
  free-text content never mined for contact_ids).
- `bind_history_reference(current_text, history_records)` →
  (record, reason) or (None, reason). Patterns: callback/reply,
  missed caller, anaphoric number ("số đó", "số mới nhất" + time
  field, topic fallback), prior instruction. Exactly one candidate
  after filtering, or no bind. "A number exists somewhere in
  history" is never enough. Recency alone does NOT bind a callback
  ("người vừa gọi" with two missed calls stays ambiguous); only
  the explicit "số mới nhất" + time field binds by recency.
- `phone_evidence_for(value, session_prefix, roster,
  current_text=None)` — sources in authority order (roster unique,
  log fields, user text, bound history, read-result content);
  write echoes and proposal arguments are excluded by
  construction (only succeeded RESULTS and turn texts are read).
- `callback_reference_for(call_args, session_prefix, roster=None,
  current_text=None, consumer_tool=None)` — reports roster
  membership, observed counterpart, and consumer acceptance
  separately. Unknown consumers are capped at AMBIGUOUS (acceptance
  cannot be claimed). `CONSUMER_REQUIRES_MEMBERSHIP` encodes the
  verified table in §1.

Session-prefix entry shapes accepted: `{"tool", "args", "result",
"outcome"|"succeeded", "position"}` for prior calls (history
turns' calls included), and `{"kind": "user_turn", "text",
"position"}` for history user turns. The CURRENT proposal must
not be in the prefix. Without `current_text`, question (b) is
None and nothing can be PROVEN.

## 5. Tests (synthetic only; invented fixtures)

`tests/test_phone_callback_evidence.py`: **51 tests, all passing**
under system python3 (stdlib only, no venv needed — the module has
no third-party dependency). Counted as 51 passed / 0 failed /
0 errors / 0 skipped. Coverage: digits, `+84` folding,
no-digit-editing (near-miss stays a near-miss), spoken digits
(comma-grouped, space-separated, leading zeros after the "số"
cue), bare "không" (no guess), "không phải" (negation, with a
loop-regression guard), negated vs affirmed numbers in one
sentence, retired old numbers vs new numbers stated in the same
message, tail-correction parse/apply/wrong-tail/multiple-matches,
background vs target, money/time/date/order-code/short-tail/bare-
digits discrimination (including money+phone in one sentence),
history parsing (dict, list, JSON, Python repr, malformed,
hostile string with no eval), nested contact unpacking, callback
binding (named missed vs outgoing distractor, unnamed single
missed, two missed with no name → ambiguous, topic
disambiguation, newest-by-time chat selection, multi-number chat
with no cue → ambiguous, prior-instruction binding, mere
co-occurrence → no bind), phone evidence (user digits/spoken,
write-echo exclusion, proposal-args exclusion, failed-log
exclusion, roster unique vs duplicate, roster-without-selection
→ AMBIGUOUS not PROVEN, different-number-requested → not
selected, tail-correction binding), callback reference (observed
counterpart + phone.call → PROVEN without claiming membership,
same + contacts.update → AMBIGUOUS, roster + contacts.update →
PROVEN, free-text id → UNKNOWN, other-registry id string →
UNKNOWN, unknown consumer → AMBIGUOUS).

Bugs found by the tests during this round and fixed in the module
(not hidden): (1) a `find_digit_runs` loop hazard on "không phải"
(run starting at a negation could not advance); (2) negation
scope too wide (an 8-token window negated the affirmed second
number in "Không phải số A, mà là số B" — now adjacency-gated);
(3) retired-number scope too wide ("số mới là X, số cũ không dùng
nữa" wrongly retired X — now requires "số cũ" to attach to the
mention); (4) anaphoric chat binding ignored all but the first
message of a result (messages of one result share a position —
now all are considered); (5) `_content_amounts` definition lost
in an edit (NameError caught by the suite, restored).

## 6. What the module does NOT do (explicit limits)

- Does not fix wrong intent, missing prerequisites, or unchecked
  conditions (round §4 holds).
- Does not prove a call correct: PROVEN means "grounded in a valid
  source AND selected by the current request", not "the call is
  the right action". Existence ≠ correct entity choice.
- Does not recover numbers lost in ASR: if the transcript drops
  digits, the text layer reports UNKNOWN/AMBIGUOUS — it never
  guesses digits. (ASR-digit-loss cases stay BLOCKED at this
  layer; recovery would need audio or a re-ask, both out of scope.)
- Does not parse compound spoken amounts ("sáu trăm hai mươi
  nghìn", "một triệu tám") for amount disambiguation — simple
  amounts only; compounds yield no match, never a guess.
- Does not merge space-grouped digit strings ("0902 418 0240")
  into one number — spoken-word runs merge, digit strings do not
  (merging digit strings would also merge separate numbers and
  date parts). Observed data uses contiguous digits or spoken
  words, so this is a documented gap, not a seen failure.
- Does not support the southern "tư" for 4 — only the ten
  canonical digit words. If the data shows "tư", add it as a
  tested extension, not silently.
- Does not resolve cross-turn narrative coreference beyond the
  implemented patterns (name/topic/amount equality + recency-by-
  time). A reference that needs semantic inference ("the person
  who complained about the bill") stays AMBIGUOUS.
- Does not handle numbers in images/attachments, or numbers
  stated only in audio without a transcript.
- Two registries sharing one id string are kept apart by
  construction (extraction is tool-typed; a chat id is never a
  contact id), but the coordinator must keep that typing when
  wiring (do not flatten records into bare strings).

## 7. Adjudication check (NOT a test, NOT a score claim)

A scratch script (`/tmp/scratch_residual_check.py`, not shipped)
queried the module with the 11 phone-residual values and the 3
callback values for adjudication only, using full prefixes
(history turns + ToolEnv-replayed prior gold calls). Result: all
11 phone cases PROVEN (5 spoken + 1 digits + 1 spoken + 1 tail
correction + 1 prior instruction + 1 chat-latest-time + 1 chat
unique + 1 digits — grouped per §2) and all 3 callbacks PROVEN.
This shows the module CAN ground these cases; it is not a
false-block-rate measurement. The coordinator's paired audit on
the full dev set, with the wired gates, is the check that decides
whether any of this changes gate decisions, and by how much. In
particular, the (a)/(b) split means some previously "fired"
decisions may become AMBIGUOUS rather than PROVEN when selection
is undetermined — the audit must report those separately, not
fold them into a single coverage number.

## 8. Handover notes for the coordinator

- Wire `phone_evidence_for` / `callback_reference_for` as
  ADDITIONAL evidence for the phone/contact branches of G2 only;
  do not replace the existing roster/log rules — the new verdicts
  should be reported alongside them in the paired audit (old
  decision vs new decision per call).
- The paired audit must keep the (a)-only and full-PROVEN counts
  separate, and must adjudicate every decision change (not just
  count coverage growth).
- Adapter requirements: extract nested `contact.phone` (the
  current flattener drops `phone` keys); preserve `direction` /
  `status` / `time` on log records; pass history user-turn texts
  as `user_turn` entries; never put the current proposal in the
  prefix; pass `current_text` (without it nothing is PROVEN).
- Suggested shadow reporting columns per phone/contact decision:
  old gate verdict, new verdict, basis (source|binding), (a)
  sources, (b) selected + reason, consumer acceptance note.
- This module is shadow-only input. It changes no proposal,
  submitted call, state, retry, or termination, and it must not be
  wired to block anything until the paired audit + reviewer
  (Thread C) sign off.

## Reviewer round-2 fixes (coordinator-applied, 2026-10-29)

Independent review found 7 module issues; all fixed in-module
before the paired audit re-run (tests added in
tests/test_phone_callback_evidence.py::TestReviewerRound2Fixes):

- R2-A5: `_is_retired_old_number` now matches "số cũ" as
  consecutive TOKENS, not substring ("số của" no longer retires).
  New rule: a speaker-owned number with an action on the speaker
  ("Số của em là X, gọi giúp em") is `requested_target`
  (`speaker_number_called`), not background.
- R2-A1: leading-"không" ambiguity only for SHORT runs (<7
  digits) without a phone cue; a long SPOKEN run (>=9 digits)
  classifies as phone by shape (`long_spoken_shape`). Bare long
  runs are returned (role ambiguous) instead of dropped.
- R2-A2: roster-multi now yields TWO evidences: identity
  ambiguous AND number-existence active
  (`roster_number_present_multiple_contacts`). For number-target
  consumers + name selection this is PROVEN; identity is never
  claimed from it (counterpart None). Callback `ref_phone`
  roster membership likewise requires a UNIQUE match.
- R2-A3: `name_filter` never falls back to the full pool; an
  explicit non-generic, non-family addressee token after a
  callback verb vetoes binding (`callback_name_mismatch`).
  Family references (mẹ/ma/bo/...) and generic references
  (người đó, tin nhắn) never veto. Topic selection now runs over
  the name-narrowed pool, or the full pool when no name matched
  (fixes a regression the no-fallback change introduced).
- R2-A4: `_name_matches` matches names on diacritic-SENSITIVE
  original tokens (Unicode word regex -- NOT the ASCII
  `_TOKEN_RE`, which shreds "Mạ" into {"m","a"}); multi-token
  names may additionally match folded. "An" no longer matches
  "ăn". Trade-off: ASR dropping diacritics on a single-token
  name falls back to AMBIGUOUS (safe direction).
- R2-A6 (P3g at module level): NOT a module fix -- origin
  filtering is the ADAPTER's job (`filtered_prefix_for_phone`,
  applied to gate priors, A prefix, and ledger). A module-level
  probe with digits restated in current text PROVEs via
  user_text legitimately; only the anaphoric form is laundering,
  and the adapter test covers it.
- Contacts.delete: does not exist in the catalog; removed from
  CONSUMER_REQUIRES_MEMBERSHIP. Succeeded contacts.update
  membership is covered by the GATE's PATCH_VERIFIED path, not
  by `callback_reference_for` (notes corrected).
