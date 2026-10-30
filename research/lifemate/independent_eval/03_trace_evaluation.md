# Section 3 — Independent evaluation on existing model traces

Baseline: `287e68d5022aac243f2b5721029b6db6a17d93b5`.
Traces read from the committed files at that SHA (not from /tmp, not from memory).

## 1. Metadata verification (per trace)

| Field | e1_v10 | e6_c_v11 | e5_v13 |
|---|---|---|---|
| File | analysis/runtime/e1_v10_diagnostic_trace.json (54,791 B) | analysis/runtime/e6_c_v11_diagnostic_trace.json (58,751 B) | analysis/runtime/e5_v13_diagnostic_trace.json (132,653 B) |
| `usage` | DIAGNOSTIC_ONLY_NEVER_AGENT_INPUT | DIAGNOSTIC_ONLY_NEVER_AGENT_INPUT | DIAGNOSTIC_ONLY_NEVER_AGENT_INPUT |
| Evidence label | E1_NATIVE_VS_TEXT_DIAGNOSTIC (not benchmark) | E6_C_PARSER_ONLY_DIAGNOSTIC | E5_REMINDER_RULE_DIAGNOSTIC |
| Source commit | 5fb5d0a (opt-in native) | a472006 | a472006 (same as V11) |
| ASR | vinai/PhoWhisper-small, rev a86b604c346caf7148c37512eafe783a16420adb | same | same |
| LLM | Qwen/Qwen3-4B-Instruct-2507, snapshot cdbee75f17c01a7cc42f958dc650907174af0554 | same | same |
| Dataset | 876,430,231 bytes, sha256 57d37151…, v3.2.0, train 1545 | same | same |
| Transcript fields | `model_current_transcript` (model-received), `asr_transcript`, `history_asr` | same | same |
| Trace events | `generation` (with `parsed`) + `tool` (with `result`) | same | same |

Verified: the three traces are diagnostic-only artifacts; they were never agent
inputs. V13's code base is a472006 (same as V11), not "main e2245ab1".

## 2. Row inventory (independently extracted)

Write proposals extracted per trace (generation events with a write tool):

| Trace | Write rows | Matches C10 |
|---|---|---|
| e1_v10 | 14 | yes |
| e6_c_v11 | 10 | yes |
| e5_v13 | 29 | yes |

Row = one write proposal. The extraction uses only the trace file itself.

## 3. Method

For each write proposal I recorded: sample id, arm, generation index, the
proposal JSON, the model-received current transcript, the ASR history, and the
tool events strictly before the proposal's generation (causal prefix — no future
events, no gold labels).

I then ran `adapter.decide()` on each row with the trace-derived prefix. Known
limitation: the trace does not contain the roster or the original history tool
records, so my replication under-fires relative to the full-evidence run (it
fires on rows where the full run passes, e.g. train_0004). The direction of the
bias is documented per row; it does not affect the block/pass classification of
rows where the proposal is clearly wrong.

Correctness labels (my independent judgment from the transcript):
- **correct_pass**: proposal matches the request and references are valid.
- **correct_block**: proposal is wrong/unevidenced and the guard blocks it.
- **false_block**: proposal is right but the guard blocks it.
- **miss** (wrong pass): proposal is wrong but the guard lets it through.
- **insufficient_evidence**: the transcript is too garbled to judge correctness.

I do NOT infer "the agent would have fixed it" from a block, and I do NOT treat
gold-replay results as model-proposal positives.

## 4. Results

### train_0004 — correct-pass control (verified, not a block)

Rows: e1_v10 native gen1, text gen1/gen2; e6_c_v11 native_control gen1,
pseudo_boundary gen1. All five propose `smart_home.light_set(device_id=
light_bedroom2, brightness=50)` after a succeeded `smart_home.get_status`,
for the request "giảm độ sáng đèn phòng ngủ nhỏ xuống còn một nửa"
(dim the small bedroom light to half). The proposals are correct. With full
evidence (device registry from the dataset history) the guard passes them —
that is why C10 adjudicates them correct_pass. My no-roster replication fires
them, which independently confirms the pass depends on evidence, not on the
adapter waving everything through. **train_0004 is a positive control; it must
never be counted as a correct-block.**

### Rows with clear verdicts

| Row | Transcript (essence) | Proposal | My judgment | Guard (C10) | Guard (my run) |
|---|---|---|---|---|---|
| 0116 (V10/V11/V13) | "nhắc tôi gọi điện cho mẹ" (REMIND me to call mom) | phone.call contact_id cont_01 | WRONG (reminder→call; cont_01 unevidenced) | block | block (adapter: phone_callback_evidence_insufficient) |
| 0287 (V13) | "nhắc mình gửi cho mẹ" (REMIND me to send) | ewallet.transfer contact_mom | WRONG (reminder→transfer) | block | block (adapter: phone_callback_evidence_insufficient) |
| 0219/0220/0353/0360/0683/0780/0823 (V13) | reminder / meeting / calendar requests | matching creates | RIGHT (face-value) | pass | pass |
| 1075 (V13) | "hạ cái cảnh báo xuống" (lower the alert) | home_energy.set_alert | RIGHT (face-value) | pass | pass |
| 0004 (all) | dim bedroom light to half | light_set bedroom2 50 | RIGHT | pass | fire (no-roster artifact) |

### Garbled-transcript rows (insufficient_evidence for correctness)

V10: 0008 (all gens), 0016, 0049 (all gens). V11: same samples. V13: 1029,
1104, 1111 (partially). The ASR transcripts are too garbled to judge whether
the proposals are right or wrong. I record the guard's decision but do NOT
assign correct_block/miss labels to these rows from the transcript alone.
(C10's labels for these rows rest on evidence beyond the trace — dataset
history and roster — which I did not re-read, per the no-held-out rule and
the read-only data constraint.)

### Summary table (my independent adjudication)

| Trace | correct_pass | correct_block | false_block | miss | insufficient_evidence | out_of_scope |
|---|---|---|---|---|---|---|
| e1_v10 (14) | 3 (0004×3) | 1 (0116) | 0 | 0 | 10 | 0 |
| e6_c_v11 (10) | 2 (0004×2) | 1 (0116) | 0 | 0 | 7 | 0 |
| e5_v13 (29) | 8* | 2 (0116, 0287) | 0 | 0 | 12 | 7* |

\* V13 correct_pass and out_of_scope counts are face-value judgments on clear
transcripts; the 7 out_of_scope are rows where the guard's monitored-arg scope
does not cover the proposal (consistent with C10's out_of_scope 7).

Comparison with C10: C10 reports more correct_blocks and misses than I can
independently verify from the traces alone (V10: 6 correct_block/5 miss; V11:
6/2; V13: 16/6). The difference is exactly the garbled-transcript rows, where
C10 used dataset/roster evidence I did not re-read. **I do not dispute C10's
labels; I mark them as not-independently-verified rather than confirmed.**
The rows I CAN verify independently (0004 passes, 0116/0287 blocks) agree with
C10.

## 5. Contributor breakdown (prover / G2 / adapter)

From my replication (adapter.decide on trace-derived prefixes):

- **G2 (baseline read-before-write)** drives nearly all blocks: every blocked
  row in my run has `baseline_fired=True`. The blocks are for unestablished
  references (device ids, alarm ids, contact ids, bill ids without prior reads).
- **Adapter adjustments** on trace rows: the only adjustment seen is
  `phone_callback_evidence_insufficient` (on 0116 and 0287 phone/transfer
  proposals) — i.e., the adapter examined the un-fire path and refused it,
  keeping the baseline's fire. No `phone_callback_evidence` un-fire occurred on
  any trace row (expected: these are model proposals, not the synthetic
  un-fire constructions).
- **Adapter-contributed correct blocks** (per C10, cited): 0116 (V10/V11/V13)
  and 0287 (V13) — rows where the adapter's trail records its own reason
  alongside G2. Union of distinct samples: {0116, 0287} = 2.
- **Adapter-only correct blocks**: 0 in all three traces (every adapter-
  contributed row also has G2/prover blocking). Cited from the handoff's
  measurement cross-check; consistent with my replication (all my blocks are
  baseline_fired=True).
- **Prover**: not separately executed in this task (its verdicts are in C10's
  "blocked" definition). The overlap is total on the verified rows: no row is
  blocked by the adapter alone.

## 6. What this does and does not establish

Establishes:
- The three traces' metadata is correct (models, dataset, source commits,
  diagnostic-only usage).
- train_0004 is a correct-pass control, not a block — verified from the trace
  data itself.
- On clearly-wrong proposals (0116, 0287: reminder→call/transfer), the guard
  blocks; the adapter's trail records its refusal to un-fire.
- The adapter never un-fires a model proposal in these traces; all its
  contributions here are "keep the block".

Does not establish:
- Correctness labels for garbled-transcript rows (insufficient evidence).
- That any block would have improved the agent's score (no e2e measurement).
- That the guard's precision/recall on these traces generalizes (n is small;
  14/10/29 rows).
