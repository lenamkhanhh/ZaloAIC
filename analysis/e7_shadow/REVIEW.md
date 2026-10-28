# G5 independent review record

A read-only reviewer derived expectations from SPEC and synthetic/catalog semantics BEFORE reading the implementation. No edits, model/GPU jobs or independent corpus tuning. The specialized reviewer role could not start because its fixed model was unavailable on this account; one general agent then performed the bounded correctness review.

V1 findings (1018ae9):

1. Event shift containing 'nữa' incorrectly anchored to now instead of the selected observed event (false ALLOW and false BLOCK).
2. Threshold slot borrowed an hour or quantity from another slot/clause (false ALLOW).
3. Weekday expression 'tuần sau nữa' silently dropped its modifier (wrong ALLOW/BLOCK).
4. Explicit ID matching accepted a string prefix (record_1 inside record_10).

All four were reproduced with synthetic values only, added as regression tests, and fixed. The follow-up on guard SHA25602562c37bf8c98dd5dddb1b06f6706208513cdacade9bdbb2309c26072102295 independently confirmed them resolved. The reviewer additionally checked the ID matcher directly because the public assess test now abstains earlier.

This closes those four findings only. It is not proof of all provenance semantics. Reviewer explicitly agreed that428/459 gold-write UNKNOWNs and one unresolved required fill leave CPU_NOT_READY. No statement of general zero over-rejection, no model recovery claim, no approval to run GPU.
