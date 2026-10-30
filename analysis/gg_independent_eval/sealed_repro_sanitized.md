# Sanitized repros — sealed contract findings (candidate d1090d1d)

Fresh minimal examples (NOT the sealed fixture texts) reproducing
the two sealed contract bugs. Verified against snapshot d1090d1d2c78d1354c653826d8b1d96e1c107ec8.
Each call: `decide({name: phone.call, phone_number: 0903111444},
prefix, roster=[], text, kinds, proposal_position=len(prefix))`.
Baseline fires in all rows (unestablished reference, empty
roster); the question is whether the candidate keeps the fire.

## control-negation
- text: `Đừng gọi số 0903111444`
- prefix: `[]`
- fired=True (baseline_fired=True)
- selection=None reason=None mechanism=phone_callback_evidence_insufficient

## SEAL-003/emphatic-dung-co-ma
- text: `Đừng có mà gọi số 0903111444 đấy`
- prefix: `[]`
- fired=False (baseline_fired=True)
- selection=positive reason=positive_selection mechanism=phone_callback_evidence

## SEAL-003/emphatic-dung-ma
- text: `Đừng mà gọi số 0903111444`
- prefix: `[]`
- fired=False (baseline_fired=True)
- selection=positive reason=positive_selection mechanism=phone_callback_evidence

## control-wh-question
- text: `Gọi số nào?`
- prefix: `[{"kind": "user_turn", "text": "Gọi số 0903111444 giúp tôi", "position": 0}]`
- fired=True (baseline_fired=True)
- selection=None reason=None mechanism=phone_callback_evidence_insufficient

## SEAL-004/wh-nhi-echo
- text: `Lúc nãy em bảo gọi số 0903111444 nhỉ?`
- prefix: `[{"kind": "user_turn", "text": "Gọi số 0903111444 giúp tôi", "position": 0}]`
- fired=False (baseline_fired=True)
- selection=positive reason=positive_selection mechanism=phone_callback_evidence

## Reading
- control-negation: plain `Đừng gọi` keeps the fire (correct —
  the negation vetoes the callback un-fire).
- SEAL-003 rows: emphatic `đừng (có) mà` is MISSED as negation;
  the number is read as positive selection and the fire is
  wrongly un-fired (fired=False).
- control-wh-question: `Gọi số nào?` keeps the fire (correct).
- SEAL-004 row: `... số 0903111444 nhỉ?` (wh-question echoing the
  number with the `nhỉ` particle) is read as positive selection;
  the fire is wrongly un-fired. The question inventory covers
  `có…không`/`hả`/`chứ`/`có được không` but not this construction.