# CONTEXT HANDOFF — LifeMate / G&G (Grounding & Gates)

Tài liệu tự chứa cho Codex. Ngày bàn giao: 2026-10-30. Commit được audit:
`287e68d5022aac243f2b5721029b6db6a17d93b5` (nhánh `gg-phone-callback-lifecycle`).
Trạng thái: **bản final — đã đối chiếu trực tiếp code/API/test trong task bàn giao
ngày 2026-10-30; mọi điểm chưa xác minh được đều ghi rõ UNKNOWN hoặc "trích kết quả
cũ" kèm nguồn, không đoán. Bản sửa đổi 1 (2026-10-30, sau push 47424307): bổ sung
cross-check từ luồng pipeline — xem Phụ lục A.**

Quy ước đọc:
- `fired=True` = gate chặn (hướng an toàn), `fired=False` = un-fire (cho qua).
- X, Y, Z trong ví dụ là **số synthetic của probe** (fixture red-team), không phải
  số thật trong dataset. Tên người trong ví dụ (OWNER, OTHER) là vai trò; tên cụ thể
  trong probe (nếu có) cũng là fixture, không phải contact thật.
- "Trích kết quả cũ" = con số lấy từ báo cáo/audit trước, chưa chạy lại trong task
  bàn giao này. "Đã verify trong task này" = đã đối chiếu trực tiếp code/API/test
  trong task bàn giao này.
- Không có raw dataset, gold text, held-out content, voucher code, credential trong
  tài liệu này. Mọi ví dụ đều synthetic hoặc paraphrase cơ chế (không trích gold text).

## Mục lục

1. [Chốt danh tính nguồn](#1-chốt-danh-tính-nguồn)
2. [Bản đồ toàn bộ pipeline](#2-bản-đồ-toàn-bộ-pipeline)
3. [Danh mục thành phần và trạng thái](#3-danh-mục-thành-phần-và-trạng-thái)
4. [Lịch sử sửa lỗi](#4-lịch-sử-sửa-lỗi)
5. [Danh sách việc chưa hoàn thành (phân loại A–F)](#5-danh-sách-việc-chưa-hoàn-thành)
6. [Dữ liệu và phép đo](#6-dữ-liệu-và-phép-đo)
7. [Test / red-team artifact](#7-test--red-team-artifact)
8. [Hợp đồng giữa các module](#8-hợp-đồng-giữa-các-module)
9. [Kế hoạch tiếp theo](#9-kế-hoạch-tiếp-theo)
- [Checklist cho Codex](#checklist-cho-codex)
- [Thông tin chưa biết / cần Codex cung cấp](#thông-tin-chưa-biết--cần-codex-cung-cấp)
- [Tóm tắt (≤15 dòng)](#tóm-tắt)
- [Phụ lục A — Cross-check từ luồng pipeline (2026-10-30)](#phụ-lục-a--cross-check-từ-luồng-pipeline-2026-10-30)

## Bảng trạng thái tổng hợp (đọc nhanh)

| Hạng mục | Trạng thái thực tế (không nâng mức) |
|---|---|
| Agent runtime (a2e832b baseline) | Chạy được, có grounding cũ; G&G chưa nối |
| Agent runtime (main + nhánh G&G) | Chạy được, có grounding vòng 5+; G&G chưa nối |
| Grounding (lifemate_grounding) | Code + unit test + replay gold; chưa đo tăng điểm end-to-end |
| Prover (lifemate_provenance) | Code + unit test + gold audit (E7); chưa nối runtime; chưa shadow runtime |
| G1/G2/G3 | G1 DROP, G3 DROP (scoped), G2 KEEP; G2 baseline trong runtime? Xem §3 |
| Phone/callback evidence + adapter | Code + unit test + paired gold + shadow trace; chưa nối runtime |
| Negation/correction/action-selection | Code + unit test + red-team probe; chưa nối runtime |
| Prior-instruction continuation/cancellation | Code + unit test + red-team probe; chưa nối runtime |
| Evidence ledger/lifecycle | Code + unit test; chưa nối runtime; prover lifecycle CHƯA nối (ghi riêng) |
| Derived-value invalidation | Ledger rule có; prover observation expiry CHƯA nối |
| Eligibility checks | Chưa nối (BLOCKER riêng, xem §5) |
| Runtime shadow integration | CHỈ là brief (§6 lifecycle report); chưa có hook trong agent loop |
| SFT prototype | CPU prototype + validator + fix report; CHƯA train; base PROVISIONAL; chờ câu hỏi BTC |
| Tăng điểm end-to-end (proxy hay thật) | CHƯA chứng minh ở bất kỳ mức nào (xem §6.7) |
| Điều kiện dừng R4 (2 batch sạch liên tiếp) | CHƯA đạt (clean count = 0; batch 11 có 1 SERIOUS mở) |
| Hard-enforce | KHÔNG sẵn sàng (adoption bar fail chân thứ hai: independent positives = 1) |

## 1. Chốt danh tính nguồn

### 1.1 Repo, branch, commit (đã verify trong task này qua GitHub API)

- Repo: `https://github.com/lenamkhanhh/ZaloAIC` (public — lưu ý: public là workaround
  truy cập GitHub App, không phải quyết định công khai vĩnh viễn; đừng đổi visibility
  nếu không có chỉ thị riêng).
- Nhánh đang làm: `gg-phone-callback-lifecycle`.
- Commit đang kiểm chứng (checkpoint R4 v10 + báo cáo): 
  `287e68d5022aac243f2b5721029b6db6a17d93b5`
  (2026-10-29T15:31:23Z, message: "G&G R4: binding/action-selection contract v10
  checkpoint + handover report (shadow-only, no merge; batch 11 open SERIOUS recorded)").
  Parent: `6030f760a973b6d813c7f9b178d278dda4801193` ("Fix callback false bindings
  R1/R2/R3"). Không có commit nào sau `287e68d5` trên nhánh (branch tip == commit này,
  đã verify qua list_commits).
- Main: tip `1caa885ac35f2719f85ef553db457b984e6d2131` ("Test push: add TEST_PUSH.md",
  2026-10-28). **Chưa merge** bất kỳ công việc G&G R4 nào vào main. Main không chứa
  commit R4; nhánh R4 không merge vào main.
- Commit nào là bản đang kiểm chứng, bản nào chỉ là checkpoint:
  - `287e68d5` = checkpoint cuối đợt R4 (v10 + báo cáo), đã qua final reviewer đọc
    đúng commit (PASS checkpoint, KHÔNG phải phê duyệt hard-enforce).
  - `6030f760` = base của đợt R4 (đã audit: R1/R2/R3 fix, 306 tests).
  - `61d84390cf652b9490de5f5db8378d5802c11182` (viết tắt 61d84390) =
    round10-provenance-gates-fixes (fix rounds 1–3 sau Round 10; message "Round 3:
    registry-typed G2 + kind classification + reviewer fixes", 2026-10-28T17:36:03Z).
  - `219d7fec` = Round 10 trên main. `1caa885a` = main tip (test push, không phải code).
  - `a2e832b` = nhánh `codex/lifemate-baseline-integration` (Codex baseline agent;
    KHÔNG nhầm với main). `d549f583` = overnight-capability-audit.
    `26ba11df8a6abd99a13334346c145135d1838306` = sft-prototype-v2 tip.
- Link trực tiếp tới file tại commit cố định (dùng mẫu này, thay `<path>`):
  `https://github.com/lenamkhanhh/ZaloAIC/blob/287e68d5022aac243f2b5721029b6db6a17d93b5/<path>`
  Ví dụ: báo cáo R4:
  `https://github.com/lenamkhanhh/ZaloAIC/blob/287e68d5022aac243f2b5721029b6db6a17d93b5/research/lifemate/gg_r4_binding_action_selection_report.md`
  Adapter:
  `https://github.com/lenamkhanhh/ZaloAIC/blob/287e68d5022aac243f2b5721029b6db6a17d93b5/lifemate/lifemate_gates_adapter.py`

### 1.2 File trong commit 287e68d5 (đã verify: get_commit + blob SHA remote == local)

| File | Thay đổi vs parent | Blob SHA (remote == local) |
|---|---|---|
| lifemate/lifemate_callback_negation.py | +2149/−23 | 2773821cc80e919c2376bbd555cb492c17984f80 |
| lifemate/lifemate_gates_adapter.py | +1332/−8 | 107b46a8e69d7433abd4d076d9e13ec8d3dd8341 |
| lifemate/lifemate_phone_callback_evidence.py | +516/−5 | 2f1411523f3d2cd5b9919edf399f8d8fc492a452 |
| tests/test_callback_negation.py | +1227/−1 | 260fb5c230e397de65ac9db2b7b4b2979272bef4 |
| tests/test_gates_adapter.py | +1646/−0 | 84c6744d4ec630e68a242f75ead6e1f451febc30 |
| tests/test_phone_callback_evidence.py | +367/−6 | 9c5a2f42b680895bc74add25990cc126afe85edf |
| research/lifemate/gg_r4_binding_action_selection_report.md | +555 (added) | f3b10513def02a2990b091e5e11d9c315c877c96 |

Lưu ý: test_gates_adapter +1646/−0 so với parent là nhất quán — test replacement
được thêm trong đợt R4 rồi rewrite trong đợt, nên so với parent nó là pure addition;
dòng rewrite đã cite là so với v9, không phải so với parent.

### 1.3 Runtime / agent / config / model / tokenizer (đã verify trong task này)

Ba trạng thái agent — đừng nhầm lẫn:

| Trạng thái | Agent grounding import | Config grounding | G&G adapter được agent gọi? |
|---|---|---|---|
| a2e832b (Codex baseline, nhánh codex/lifemate-baseline-integration) | `from .grounding import ground_arguments` (agent.py:39), gọi khi `self.config.grounding` (agent.py:166) | baseline.json `grounding=false`; recommended.json `grounding=true` | KHÔNG (grep toàn worktree: 0 import G&G module) |
| main 1caa885a | `from .lifemate_grounding import ground_tool_call`, gọi khi `getattr(self.config, "grounding", False)` | recommended `grounding=true`; baseline `grounding=false` (khớp a2e832b) | KHÔNG |
| nhánh G&G 287e68d5 | Giống main — agent.py **byte-identical** với main (đã verify qua API + diff) | Giống main | KHÔNG |

G&G adapter chỉ được gọi bởi: `analysis/gg_paired_audit.py`, `analysis/gg_shadow.py`,
và tests (`tests/test_gates_adapter.py`, `tests/test_unfire_controls.py`) — đã verify
bằng grep toàn frozen v10 (ngoài ra chỉ còn 2 file .md nhắc tới nó, không phải code).
**Kết luận: G&G là audit-script-only + tests ở mọi trạng thái; chưa có agent nào gọi nó.**

Config chung (đọc trực tiếp baseline.json + recommended.json, 2 file chỉ khác cờ
grounding): ASR `vinai/PhoWhisper-small` (backend transformers, greedy, vi);
LLM `Qwen/Qwen3-4B-Instruct-2507` revision `cdbee75` (backend vllm, temp 0.0, seed 42,
ctx 16384, max_new_tokens 512); max_steps 12; max_repeats 2; total 4.244B
(LLM 4.0B + ASR 0.244B); heldout_frac 0.2; split_seed 42; selective_reads true;
verification_read_after_write false; constrained_decoding "validate-and-retry";
local_files_only true. ASR revision: PhoWhisper-small rev
`a86b604c346caf7148c37512eafe783a16420adb` (full SHA — XÁC NHẬN từ trace metadata
của cả 3 traces V10/V11/V13, không còn là "trích kết quả cũ"; config JSON chỉ ghi
checkpoint name, KHÔNG pin ASR revision — đừng suy ra rev từ config). LLM snapshot
đầy đủ: `cdbee75f17c01a7cc42f958dc650907174af0554` (config `llm_revision: "cdbee75"`
chỉ là prefix rút gọn).
Tokenizer: dùng qua model revision trên; không có tokenizer revision riêng được ghi.

### 1.4 Artifact chỉ ở workspace local (không push, không có trên nhánh)

| Artifact | Đường dẫn local | Tái tạo được? |
|---|---|---|
| R4 probes + followups + handovers + C reports | ~/workspace/zaic-gg-r4-probes/ (r4_r123, r4b3–r4b11 + followups, r4b*_a_handover, r4b*_report, verification drafts) | Có — chạy lại trên freeze tương ứng (xem §7); probe là synthetic, không chứa raw data |
| R4 freezes v1–v10 + candidates | ~/workspace/zaic-gg-r4-frozen-v1…v10, zaic-gg-r4-candidate*, candidate-final | Có — v10 == nội dung commit 287e68d5 (code) + báo cáo; các freeze giữa chỉ còn local |
| R4 verification drafts | ~/workspace/zaic-gg-r4-report/verification_v1…v10.md | Có — C reports; bản v10 cũng là bản nháp của C (không phải file trên nhánh) |
| SFT local-only | sft_prototype_local.json (local-only, KHÔNG push, KHÔNG đưa vào bàn giao) | Không — cố tình không push; xem §6.3 |
| Dataset LifeMate | ~/workspace/zaic-data/lifemate/ (train.jsonl, train_environment/, train_tools_catalog.json, audio/) | Không push (đúng quy tắc); Codex lấy từ nguồn dữ liệu gốc của cuộc thi |
| DataMate data | ~/workspace/zaic-data/datamate/ | Không push |
| /tmp artifacts | Đã mất do /tmp cycling (xem §7.3) | Một phần không tái tạo (T2 raw traces) |

Cảnh báo local clone: `~/workspace/zalo-aic-round3/` có git HEAD stale (8d4721e) và
working tree có sửa local stale — diff vs origin/main gây hiểu lầm. Mọi khẳng định
về commit trong tài liệu này đều đối chiếu GitHub API, không tin local HEAD.

## 2. Bản đồ toàn bộ pipeline

### 2.1 Sơ đồ thực tế (code đang chạy — đã verify trong task này ở mức wiring)

```
audio (current request)
  → ASR transcript (PhoWhisper-small)                [agent runtime]
  → prompt build (history + catalog + current text)  [agent runtime]
  → model proposal (Qwen3-4B-Instruct-2507, vLLM)     [agent runtime]
  → grounding (NẾU config.grounding)                 [agent runtime, xem §2.2]
  → env.validate (schema check only)                 [agent runtime]
  → env.call (ToolEnv; rejected calls → get_tool_calls) [agent runtime]
  → observation (text appended to prompt)            [agent runtime]
  → next step (loop guard; max_steps 12)             [agent runtime]

G&G adapter / prover / gates / negation / phone / lifecycle:
  → KHÔNG nằm trong chuỗi trên ở bất kỳ trạng thái agent nào.
  → Chỉ chạy trong: analysis/gg_paired_audit.py (gold replay),
     analysis/gg_shadow.py (model-trace shadow), và tests.
```

Thứ tự đã verify trong task này (frozen v10 agent.py): grounding chạy trước
validate (dòng ~185: `if getattr(self.config, "grounding", False)` →
`ground_tool_call(...)` → grounding_log append), sau đó validate (dòng ~206:
`env.validate(...)`), sau đó call (dòng ~222: `env.call(...)`).
Chi tiết function-level dưới đây đã verify trực tiếp trên worktree a2e832b
(`~/workspace/zaic-branch-a2e832b/lifemate/`, code tại commit a2e832b):

**Entry point — `run.py:cmd_infer` (188).**
Mỗi sample: `transcript = asr.transcribe(wav)` cho current request — LUÔN transcribe
(203); history user turns chỉ được transcribe khi `audio_text is None` và `turn.audio`
tồn tại (208–209); `tools = catalog_tools_for_sample(catalog, sample)`; `env =
ZaicEnv(root, split, sample.id)`; `loop = AgentLoop(config, tools)`; `line =
loop.run(sample, transcript, env, llm)`; ghi JSON line ra out file. Các lệnh khác
trong `run.py:main` (219–228): replay-gold, fake-run, check-submission, score,
make-split, infer. Loader (`loader.py`): `Turn.audio_text` là None trên public_test;
public_test KHÔNG có label, KHÔNG có audio_text ở đâu (loader.py:10, 44, 57);
train mới có audio_text.

**Agent loop — `agent.py:AgentLoop.run` (134).**
`base = build_base_prompt(sample, transcript, tools)` (92); nếu selective_reads thì
thêm dòng "Read only to resolve a missing entity..."; nếu không
verification_read_after_write thì thêm dòng "Do not add a verification read after a
write...". Vòng lặp `while steps < max_steps` (12 theo config). Mỗi step tối đa 3
attempts (1 generation + tối đa 2 validation retries): `gen = generator(prompt,
tools)`; gen None hoặc stop signal → submission; gen không phải dict hoặc thiếu
"name" → re-prompt "Your last output was not a valid tool call JSON...".
`call = {name, arguments}`; nếu config.grounding thì `ground_arguments(call, tools,
executed, results, history=sample.history, transcript=transcript,
context=sample.context)` (167), else errors = []; `check = {ok False, error:
join(errors)}` nếu grounding có lỗi (validate KHÔNG được gọi khi grounding lỗi —
short-circuit), else `env.validate(name, arguments)` (173); check ok → break; else
re-prompt với observation "validation failed (NOT executed, NOT submitted)" và
call = None. Hết 3 attempts mà call None → submission. LoopGuard: nếu
`repeat_count(call) >= max_repeats` thì replan một lần (replan=True prompt), đã
replan rồi thì submission. `result = env.call(name, arguments)` (189);
`executed.append(call)`, `results.append(result)`; `sys.ask_missing_info` với ok →
submission; completion callback → submission; `guard.record(call,
state_progress=bool(result.get("ok")))` → "continue" (re-render prompt),
"replan_once" (replan prompt), else submission.

**Prompt build — `agent.py:build_base_prompt` (92) và `render_observation_prompt` (73).**
Base prompt: header (Vietnamese voice assistant, exactly one JSON object per turn,
never invent ids) + ACTION_POLICY + current time + user profile + full context JSON
+ tools (sample-filtered, sorted, mỗi tool một JSON với name/kind/description/
parameters/returns) + conversation history (user turn: audio_text hoặc "[audio, no
transcript available]"; assistant turn: text + `calls=<tool_calls>` +
`results=<tool_results!r>` — lưu ý: `!r` là repr TRONG PROMPT, không phải stored
data; stored tool_results là list, xem §6.3) + "Current user request (transcript):
{transcript}". Observation render: mỗi cặp executed/result thành dòng
`- name(args) -> outcome; output=<json>`; outcome = "not_done" nếu ok và done is
False, "ok" nếu ok, else "error: ..."; replan thêm "Choose a different,
evidence-backed action or stop." Prompt được rebuild từ base mỗi step (không phải
tool message append).

**LLM backends — `llm.py`.**
`_render` (31): single user message `[{role: user, content: prompt}]`,
`tokenizer.apply_chat_template(..., add_generation_prompt=True)`; budget check:
prompt tokens + max_tokens > max_context_tokens → `ContextBudgetExceeded` (không
silent truncation). `VLLMGenerator` (primary): temp 0.0, seed 42, max_tokens 512,
max_model_len 16384. `TransformersGenerator` (fallback): greedy (`do_sample=False`),
max_new_tokens 512. `build_generator`: temp != 0 → lỗi (chỉ hỗ trợ deterministic
greedy). `PromptReadingFake` chỉ dùng cho test (không phải model, output không được
báo cáo thành model results).

**Hiệu chính quan trọng về `__invalid__` (báo cáo cũ nói chưa chính xác về vị trí).**
`parse_model_output` (llm.py:45) KHÔNG trả `{"name": "__invalid__"}` — nó RAISE
ValueError cho garbage ("Returns None for a stop signal; raises ValueError for
garbage"). Cả hai generator `__call__` (VLLM + Transformers) đều catch ValueError
và trả `{"name": "__invalid__", "arguments": {}}`. Loop sau đó validate `__invalid__`
(unknown tool → fail) với tối đa 2 retries, không bao giờ tự sửa thành call đoán.
Kết quả cuối của claim cũ là đúng (garbage → validation reject, never auto-repaired);
chỉ có attribution là sai vị trí (generator wrapper, không phải parser).

### 2.2 Hai sơ đồ grounding — đừng nhầm lẫn

Thiết kế mong muốn (theo các vòng grounding): grounding chuẩn hoá slot trước khi
validate, để model proposal sai format/sai slot được sửa về dạng hợp lệ trước khi
chạm simulator. Code đang chạy:

| Agent | Module grounding được import | Gọi khi nào |
|---|---|---|
| a2e832b (baseline) | `grounding.py` ("Typed grounding for LifeMate slots", rule-based, zero model params): `ground_arguments` | `self.config.grounding` |
| main + nhánh G&G | `lifemate_grounding.py` ("Deterministic grounding and normalization for LifeMate (round 5)"): `ground_tool_call` | `getattr(self.config, "grounding", False)` |

Khoảng thiếu giữa thiết kế và code: grounding (cả hai module) chỉ chuẩn hoá slot/
giá trị; nó KHÔNG phải là G&G (không có provenance veto, không có gate chặn, không
có ledger). Đừng đặt G&G vào sơ đồ runtime như thể đã tích hợp — G&G chưa được agent
nào gọi (bằng chứng grep §1.3).

Chi tiết module grounding A2E (đã verify trực tiếp): `grounding.py:ground_arguments`
(190) — "Normalize only supplied slots; never invent a missing argument. Ambiguity
goes back to the model as a validation error, not an auto-ask." Helpers cùng file:
`parse_money` (68), `parse_date` (109), `normalise_id` (147), `ground_name` (152);
`FUZZY_THRESHOLD = 88.0`, `FUZZY_MARGIN = 8.0` (48–49); backend RapidFuzz nếu có,
else difflib fallback (backend được report trên mỗi kết quả fuzzy). Bên trong dùng
`EvidenceLedger` từ `evidence.py:33` (thu thập ids/phones từ executed/results/history/
transcript/context). Không có module "hook" riêng trong A2E: agent import trực tiếp
(`agent.py:39`) và gọi inline trước validate.
Config default (đã verify trực tiếp): `config.py:PipelineConfig` có `grounding: bool
= True  # False in baseline.json` — tức default khi không load JSON là BẬT; chỉ
`baseline.json` tắt tường minh. Ghi đúng: baseline = TẮT, recommended = BẬT, default
dataclass = BẬT.

Cảnh báo lineage (đã verify trực tiếp — đừng dùng agent.py của V10 làm tài liệu cho
runtime A2E, và ngược lại): agent.py của V10 KHÁC A2E ở những điểm cốt lõi — V10
không có `ACTION_POLICY` (grep = 0); observation dùng `repr(result)` và truncate 300
ký tự (`output[:300] + "..."`), trong khi A2E dùng compact JSON đầy đủ và phân biệt
outcome `not_done` (ok nhưng done False) — V10 gộp thành "ok"; V10 có roster tracking
(`self._roster`, `grounding_log`) và chuyển `NEEDS_ASK` (hoặc leftover contact-name
key) thành `sys.ask_missing_info`. V10 là lineage grounding-hook round 8, không phải
A2E cộng thêm G&G. Main và V10 share cùng agent.py (byte-identical, §1.3), nhưng cả
hai đều khác A2E.

### 2.3 Sơ đồ mong muốn cho G&G (BRIEF, chưa implement — lifecycle report §6)

```
1. Grounding (không đổi, chạy đầu, theo config)
2. Validate (schema check, không đổi)
3. Shadow guard: adapter.decide(proposal, prefix, roster, current_text, kinds,
   proposal_position=max_prefix_pos+1)
   → log full decision (baseline + candidate + adjustments + notes)
4. Call (không đổi — shadow decision KHÔNG được alter call)
5. Result-update: append call + result vào prefix, origin "session",
   outcome thật (succeeded / failed / schema_rejected / noop, từ ok + done
   đúng như result_succeeded định nghĩa). Ledger cho turn SAU được rebuild
   từ prefix này; không có cross-turn state.
Per-sample reset: fresh ledger + fresh prefix mỗi sample; adapter không giữ
state giữa các call. History prefix KHÔNG bao giờ bị P3g-filter; chỉ
session-origin READ results bị filter (rule §2.5 lifecycle report).
Boundary: mutation tại đúng proposal_position tính là "before"; luôn truyền
proposal_position = max prefix position + 1 (default), không dùng giá trị
cũ/tái sử dụng.
```

Hook point tồn tại: `gate_read_before_write` tại `lifemate/lifemate_gates.py:866`
(baseline G2). Adapter gọi nó tại `lifemate_gates_adapter.py:1793`.
**Nhưng: không có hook nào wrap nó trong agent loop ở code hiện tại.**
Brief §6 là đề xuất thiết kế, không phải code đã implement. Bằng chứng: grep
agent.py (cả 3 trạng thái) không thấy import/call adapter; grep toàn frozen v10
chỉ thấy adapter được import bởi 2 audit script + 2 test file (+ 2 file .md).
Tên thư mục `analysis/runtime/` gây hiểu lầm: nó chứa audit reports + audit scripts
(E0/E1/E5/E6-C/E7 audits, diagnostic traces), KHÔNG phải runtime code.

### 2.4 Zaic_tools contract (đã verify trực tiếp trong task này từ package thật
trong data dir: `train/zaic_tools/executor.py`, `validate.py`, `apps/*.py`)

- Một call bị REJECT (ok False) CHỈ khi schema error (executor.py: Simulator.call:
  `schema_error(...)` → `_fail` nếu có lỗi; tool không có trong TOOLS cũng fail qua
  `_fail`). `schema_error` (validate.py:100–120) kiểm tra: name trong catalog, name
  trong allowed (installed apps), required params (missing), x-one-of groups, và
  type-check CHỈ các prop có trong spec (dòng 117: args không nằm trong props không
  bao giờ bị xét → extra unknown args IGNORED, đúng claim cũ).
- App exception không raise vào agent loop: Simulator.call catch Exception → trả
  `{"ok": True, "done": False, "message": ...}` ("not a schema error, so the call
  stands and changes nothing") — state không đổi nhưng outcome trông như noop.
- `Simulator.validate` = schema check only, không execute, KHÔNG append vào sim.log
  (validate.py docstring + executor.py: validate không chạm self.log).
  `Session.call` append vào self.calls TRƯỚC khi gọi super().call, nên rejected calls
  CÓ trong `get_tool_calls()` (executor.py: Session docstring: "rejected calls
  included"; get_tool_calls docstring: "the tool_calls field of the submission line").
- Evidence "success" = ok True AND done is not False. Lưu ý: `phone.call` trả
  `{"ok": True, "call": call}` KHÔNG có key "done" → done is None (không phải False)
  → tính là succeeded, đúng rule.
- `contacts.search` (contacts.py:11): @read, query optional: substring (lower, KHÔNG
  dấu) trên name/relation/phone; không query → toàn bộ address book. `contacts.get`:
  @read theo id. `contacts.update`: @write, patch phone/email only. **KHÔNG có
  contacts.delete** (def listing đầy đủ của contacts.py: search/get/update only).
- `phone.call` (phone.py:11): @write; `contact_ref` rồi tạo record {"id",
  "contact_id", "phone_number", "status": "dialing"} — KHÔNG có direction key, KHÔNG
  nested contact. `phone.recent_calls`: @read, trả self.read("calls").
  `sms.send` (sms.py:11): @write; tạo record có "direction": "outgoing".
  `contact_ref` (base.py:105): CHỈ complete counterpart còn thiếu khi unique match
  (digits so sánh, +84 = 0); cả hai đã cho hoặc không có contacts app → trả nguyên;
  KHÔNG BAO GIỜ reject — các field phone_number/contact_id trong result là argument
  echoes sau completion, không phải validation.
- `email.read` (email.py:36): trả `{"ok": True, "email": dict(e)}` (record dưới
  "email", không phải "item"). `email.archive` (72): action == "delete" →
  `App.delete(...)`; branch khác patch folder="archive".
- Chưa đối chiếu lại trong task này (giữ nhãn trích kết quả cũ): fixed-field patches
  (tasks/reminders/shopping/flights/video_meeting/music/bill_payment/podcast_radio);
  smart_home và home_automation share MỘT device registry (chưa xác minh cơ chế
  sharing từ code trong task này); catalog kind là phân loại read/write (counterexample
  email.read kind "read" — Simulator.kind default "write" khi tool không có trong
  TOOLS, executor.py: kind).

### 2.5 Scorer proxy (cảnh báo diễn giải)

Official evaluator ABSENT — mọi scoring đều là engineering proxy (trích kết quả cũ,
chưa đối chiếu lại trong task này): tool-call F1 iff submitted state_hash == gold
state_hash else 0, order ignored. F1 dilution đã đo: write only 1.0, +1 read 0.6667,
+2 reads 0.5, ask only 0.0. **Proxy ≠ official score.** Mọi con số "tăng điểm" trong
tài liệu này đều KHÔNG tồn tại (xem §6.7) — đừng trích proxy như điểm thi.

## 3. Danh mục thành phần và trạng thái

Mức chứng minh (không nâng mức này thành mức khác):
`code` < `unit-test` < `replay` (gold replay qua ToolEnv) < `shadow` (model-trace
shadow, quyết định offline) < `runtime` (được agent gọi trong loop) < `e2e`
(chạy end-to-end có đo) < `tăng điểm` (đo được cải thiện trên metric).
**Không thành phần G&G nào đạt `runtime`, `e2e`, hay `tăng điểm`.**

| Thành phần | Trách nhiệm | File / hàm | Commit / nguồn | Đã viết | Được runtime gọi? | Đã kiểm chứng bằng gì | Giới hạn | Việc còn thiếu |
|---|---|---|---|---|---|---|---|---|
| Number/money normalization (grounding) | Chuẩn hoá số/money trong slot trước validate | lifemate/lifemate_grounding.py (round 5) qua ground_tool_call | main, rounds 4–9 (xem git log của file để chốt SHA) | Có | CÓ (khi config.grounding=true) | Unit test (test_lifemate_grounding.py 48) + replay gold | Chỉ chuẩn hoá, không veto; không phân biệt money-vs-phone mọi trường hợp | Đo tác động end-to-end (chưa có) |
| Number/money normalization (prover) | Parse digit/spoken/mixed, money words, digit-form value | lifemate/lifemate_provenance.py: parse_number_words, find_number_spans, _digit_form_value | Nhánh round10-provenance-gates-fixes @ 61d84390 (theo round10-fix-report-round3) | Có | KHÔNG (prover audit-only) | Unit test (test_lifemate_provenance.py 46) + gold audit E7 | Spaced digits, "tư", compound amounts BLOCKED | Nối prover vào runtime (chưa có task) |
| Relative date/time | Parse relative date/time, daypart adjust, datetime assembly | lifemate/lifemate_provenance.py: parse_relative_datetime, find_datetime_spans, RelativeResult | Như trên | Có | KHÔNG | Unit test + gold audit E7 (datetime_assembly 53, relative_date 36, offset 34, duration 24 PROVEN) | Week/month reference không day → never a day, never PROVEN (by design) | Như trên |
| Contact grounding (runtime) | Resolve contact-name key → contact record | lifemate_grounding.py qua ground_tool_call | main, rounds 4–9 | Có | CÓ (khi flag on) | Unit test + replay gold | Roster-before-log ordering đã fix ở vòng fix; xem §4 | Đo end-to-end |
| Contact grounding (G&G) | Roster/log/name binding cho gate | lifemate_gates_adapter.py: _selection_targets, _instruction_name_map, _known_names_for_number; lifemate_phone_callback_evidence.py (roster number-vs-identity split) | Nhánh G&G @ 6030f760 → 287e68d5 | Có | KHÔNG | Unit test + paired gold + shadow | S1 roster/log arm không quan sát được ở decide() level cho phone proposal (chỉ unit-test được qua _known_names_for_number); tên không "cho" không resolve trong M3; folded "minh" excluded | Nối runtime; mở rộng roster/log arm |
| Provenance prover | DAG chứng minh argument: PROVEN iff CPU re-derivation reproduces đúng giá trị, else veto to ASK | lifemate/lifemate_provenance.py: prove_argument (1418), prove_call (1797), Verdict, Evidence | Nhánh round10-provenance-gates-fixes @ 61d84390 | Có | KHÔNG | Unit test + gold audit E7: 533 args, DAG PROVEN 276 (51.8%), baseline PROVEN 92, conversion 184 | Residual UNPROVEN: cross-app 57 (by design), no source 184, roster-no-intent 10; history_reference = 0 PROVEN trên gold (4 proofs cũ là mislabel, đã sửa); observation expiry CHƯA nối | Nối prover vào runtime; wire observation expiry; đo shadow runtime |
| G1 (contact ambiguity) | Fire khi contact reference ambiguous | lifemate/lifemate_gates.py (G1) | Round 10 fix rounds @ 61d84390 | Có | KHÔNG | Gold audit: DROP (quyết định audit: không giữ) | — | Không áp dụng (đã DROP có chủ ý) |
| G2 (read-before-write) | Fire khi write thiếu read trước đó (registry-typed) | lifemate/lifemate_gates.py: gate_read_before_write (866) | Round 10 fix rounds @ 61d84390 | Có | KHÔNG (chỉ là hook point cho brief §6) | Gold audit: KEEP 99.6% (theo fix rounds); paired: baseline fired 15/976 | P3g residual (earlier-session dial cũng status dialing/no-direction → filtered → conservative firing) | Nối runtime qua hook (brief §6) + chứng minh non-interference |
| G3 (confirmation) | Fire khi write thiếu confirmation | lifemate/lifemate_gates.py (G3) | Như trên | Có | KHÔNG | Gold audit: DROP | — | Không áp dụng (đã DROP có chủ ý) |
| Phone evidence | Spoken-digit parser, tail correction, callback binding, roster number-vs-identity split | lifemate/lifemate_phone_callback_evidence.py | Nhánh G&G @ 9e3d827c → 6030f760 → 287e68d5 | Có | KHÔNG (qua adapter, audit-only) | Unit test (75) + paired gold + shadow | Phone branch residual: existence ≠ disambiguation; fragment/group joining chưa có (batch-11 M1) | Vòng 11: digit-run classification + optional group joining |
| Callback/name/family binding | Full-phrase name match, addressee-span, relation path (structured relation field, else AMBIGUOUS) | lifemate/lifemate_callback_negation.py: analyze_action_selection, _name_matches; adapter _selection_targets | Nhánh G&G @ 6030f760 → 287e68d5 | Có | KHÔNG | Unit test (115 negation + 125 adapter) + red-team batches 1–11 | Relation synonyms ("bố"/"ba") không match; quoted-name binding dựa vào B veto (fragile layering); verbs ngoài inventory abstain như verb-less | Mở rộng relation synonyms (cần quyết policy, không phải patch keyword) |
| Negation/correction/action-selection | Layer-C veto-only: continue/cancelled/replaced/blocked/unknown; chỉ cancelled/replaced/blocked veto | lifemate/lifemate_callback_negation.py + adapter layer C | Nhánh G&G @ 6030f760 → 287e68d5 | Có | KHÔNG | Unit test + red-team batches 1–11 + paired 0 delta + shadow 0 diff | Batch-11 S1 mở (digit-run object misclassification); suppressed-verb fallback reason label approximate | Vòng 11 (xem §5.C) |
| Prior-instruction continuation/cancellation | Revocation state machine (specific/generic), settled-history continuation, bare continuation overrides generic only, bare "thôi" = withdrawal chỉ khi là final clause | Adapter: _turn_revocation_events, _apply_revocation_events, _bound_turn_final_state, _instruction_revoked, _bound_instruction_action | Nhánh G&G @ 6030f760 → 287e68d5 | Có | KHÔNG | Unit test + red-team batches 1–11 | Dirty-sticky (name revival chỉ cho undisturbed mappings; explicit number re-issue luôn revive); instruction-cancel events vẫn action-agnostic (hướng an toàn) | Nối runtime; quyết policy cho cancel action-agnostic nếu muốn chặt hơn |
| Evidence ledger/lifecycle | Ledger/rule engine (KHÔNG phải DAG): delete kills all claims, cancel status-only, fixed-field table, re-read re-establishes, derived→unknown khi source dead | lifemate/lifemate_evidence_lifecycle.py: MUTATION_KINDS, TERMINAL_STATUS_VALUES, claim existence\|field_value, derived_from | Nhánh G&G @ 9e3d827c → 6030f760 | Có | KHÔNG (qua adapter build_ledger, audit-only) | Unit test (36) + paired + shadow | Prover observation expiry CHƯA nối; eligibility suppression CHƯA nối; consumer→claim map absent | Wire expiry + eligibility (cần task mới, xem §5) |
| Derived-value invalidation | Derived claim → unknown khi source chết | Lifecycle module (rule có) | Như trên | Có (rule) | KHÔNG | Unit test | Prover-side observation expiry chưa nối nên derived invalidation chưa tới được prover verdict | Wire prover observation expiry |
| Eligibility checks | Suppress call khi eligibility chết (vd status-only cancel kills eligibility) | (rule trong ledger có; suppression trong gate CHƯA viết) | — | Một phần (rule) / chưa viết (suppression) | KHÔNG | — | Xem §5 (chia 2 mục: rule = B, suppression = A) | Thiết kế + implement suppression + test |
| Adapter | Candidate Gate 2 decision: baseline fields + adjustment trail; P3g filter trước; joint veto (v9); government rule (v10) | lifemate/lifemate_gates_adapter.py: decide (1770), CandidateDecision (155), build_ledger (327) | Nhánh G&G @ 287e68d5 | Có | KHÔNG (chỉ audit + test) | Unit test (125) + paired 0 delta + shadow 0 diff (mọi vòng C) + red-team | question_b naming dễ bị đọc nhầm thành selection proof (documentation note); F-B4-5 warning (nếu gate học đọc arg `phone` thì non-callback pass-through thành lỗ thật) | Nối runtime qua hook + chứng minh non-interference |
| Runtime shadow integration | Hook decision-only quanh gate_read_before_write, per-sample reset, before/after logging, flag default OFF | CHỈ brief tại research/lifemate/gg_phone_callback_lifecycle_report.md §6 (không có code hook) | Nhánh G&G (brief) | KHÔNG (chỉ brief) | KHÔNG | Offline shadow đã chứng minh non-mutation (chỉ thêm field); in-loop non-interference CHƯA chứng minh (BLOCKER) | Bất kỳ khác biệt on/off nào cũng là blocker | Codex: implement hook + diff on/off (xem §9) |
| SFT prototype (liên quan) | CPU data prototype cho Codex review + pilot sau; contract PROVISIONAL a2e832b-text; D1-lite falsifiable pilot, DPO conditional only | analysis/overnight_capability_audit/sft_prototype_builder.py, sft_prototype_validator.py + tests + fix notes + fix report (nhánh sft-prototype-v2 @ 26ba11df) | Nhánh sft-prototype-v2 @ 26ba11df8a6abd99a13334346c145135d1838306 | Có (prototype) | KHÔNG (không phải runtime) | CPU verified cho 3 bugs Codex-audited (chat-template tokenization, forged-step validator, replay outcome contract); manifest v2 + diff | NOT ready-to-train (Q-L2 + zero-shot benchmark base selection còn mở); sft_prototype_local.json local-only, KHÔNG push | Chờ câu hỏi BTC (Q-L1..Q-L5) + base selection; xem §5.E |

## 4. Lịch sử sửa lỗi

**Cảnh báo về commit:** các vòng R4 v1–v10 KHÔNG commit riêng — chúng chỉ là freeze
local (`~/workspace/zaic-gg-r4-frozen-vN`). Commit duy nhất chứa toàn bộ code R4 là
`287e68d5` (checkpoint cuối). Vì vậy cột "commit sửa" dưới đây ghi "vN (freeze local,
chưa push riêng) → checkpoint 287e68d5" cho các mục R4. Các mốc trước R4 có commit
riêng (61d84390, 6030f760) thì ghi rõ SHA.

### 4.1 Era grounding / Round 10 / fix rounds (trước R4)

| Cơ chế lỗi | Lỗi gốc / repro trước sửa | Root cause | Sửa | Kiểm tra sau sửa | Giới hạn còn lại |
|---|---|---|---|---|---|
| Grounding module + hook | Model proposal sai slot/format chạm simulator | Thiếu chuẩn hoá trước validate | lifemate_grounding.py + hook, wired OFF by default (recommended.json untouched); round 9 architecture = dynamic grammar (syntax only) + provenance DAG + deterministic gates; KHÔNG thêm LLM verifier dưới 6B/30s | Unit test + replay gold; "prove 100% of values" được kết luận literally unachievable | Chưa đo end-to-end; grounding ≠ G&G |
| G2 registry-typed | G2 phân loại read/write bằng verb list → sai (vd email.read) | Verb guessing thay vì catalog kind | kind_by_tool param (catalog kind thắng khi có map, verb list fallback); e7/gates/shadow đều dùng catalog kind | E7 scope 556 → 533 args; gates denominator 971 → 957 (old gate) / 976 (new gate + phone refs); G2 false-block 0.41% (R2 scope) → 1.54% (R3 scope) | P3g residual |
| Roster-intent | Roster match không có intent bị tính là proof | Roster existence ≠ intent | Roster-no-intent rule (10 residual UNPROVEN) | Gold audit R3 | — |
| History-reference mislabel | 4 proofs history_reference là single-match-among-many bị gắn PROVEN sai | Single match trong nhiều ứng viên không phải proof | Gắn lại AMBIGUOUS | history_reference = 0 PROVEN trên gold (R3) | — |
| G1/G3 adoption | G1/G3 không đủ chính xác để giữ | Audit cho thấy false-block/precision không đạt | DROP G1, DROP G3; KEEP G2 | Gates audit | G1/G3 không áp dụng |
| Duplicate → AMBIGUOUS → ask | Duplicate contact không được xử lý | Thiếu disambiguation | Duplicate → AMBIGUOUS → ask, gold-confirmed 69/73 (94.5%) | Gold audit | — |
| Money parse bug | Parse money sai | Bug parser | Fixed (round 8) | Tests | Compound amounts vẫn BLOCKED |
| FUZZY thresholds | Contact fuzzy match threshold | Tuning | FUZZY_THRESHOLD = 88.0 / FUZZY_MARGIN = 8.0 KEPT | Gold audit | — |

### 4.2 Era R4 — contract binding/action-selection (base 6030f760 → checkpoint 287e68d5)

Nhóm theo cơ chế (không kể lại từng cuộc trao đổi):

**A. Cancellation-negation contract (R4 gốc → v1).**
Lỗi: "Thôi, không cần làm như em dặn lúc nãy nữa" / "Khỏi làm như lúc nãy nữa" /
"Đừng làm như em dặn lúc nãy" → false un-fire (selection unknown/no_callback_verb,
question_b=true, basis=binding, reason=bound_reference_selects_value); control
"Làm như em dặn lúc nãy" → un-fire đúng. Root: unknown selection + bound reference
→ proven. Sửa (v1): layer-C veto-only analyze_instruction_selection (chỉ
cancelled/replaced/blocked veto; chỉ khi selection evidence là bound reference và
current text không trực tiếp select value) + history revocation + action match.
Kiểm tra: R4 repro 4/4 OK, giữ 7/7 tới v10. Giới hạn: không sửa bằng cách thêm "làm"
vào verb list (user cấm).

**B. Clause-scan + revocation machinery (batches 1–3 → v2, v3).**
Lỗi: folded/raw mismatch giết cancellation ("không phải/lại/là + làm"); dừng/ngừng
unmodeled; "không phải + reference" không "làm" vô hình; question frames hẹp; recount
qua trailing "rồi"/"xong rồi"; "chưa + làm"; replacement ở clause sau không cancel
marker; tail-change không full number vô hình; cancellation ở clause sau reference
clause bị bỏ; addressee/family change trên prior-instruction path; instruction verbs
ngoài {call,message} bị "continued" vào call/message; generic cancellation ở turn giữa
+ bare anaphor resurrect instruction; "à không" regex bug; topic-bound non-callback
bypass B và layer C; conditional không check ("nếu rảnh") execute ngay.
Root: layer C chưa phải clause-scan last-decisive-wins; revocation chưa phân
specific/generic; topic branch thiếu; conditional thiếu. Sửa (v2): rewrite layer C
thành clause-scan; folded particle set; dừng/ngừng; "không phải"+manner; wider question
detection; past-after-reference; "chưa"; replacement-with-cue mọi clause; tail-change
mọi digit run trong tail-change context; cross-clause cancellation; addressee giữ từ
turn gốc + mismatch veto; instruction_action "other" class; generic same-action
cancellation revoke; "à không" guard; topic branch; conditional markers → blocked.
Revocation: specific/generic (current continuation chỉ override generic);
first-refusal-wins khi B và C cùng veto; bare "thôi" = withdrawal CHỈ khi là final
clause. Sửa tiếp (v3): F1 state machine (specific không bị generic downgrade;
settled-history continuation revive mọi state; current bare continuation chỉ override
generic); F3 "số mới là" cue + "mà"-fragment rule; F5 unknown instruction action →
veto cho call/message, chỉ "liên hệ" compatible; F8 khoan-governs check trước
continuation; F2 addressee last-token; F4 tail window bỏ + adjacency guard; F6 wrapper
scope; F7 "hễ" conditional + wait-then blocked + "rồi mới làm" → instruction_only_then_blocked.
Kiểm tra: v2 suites 353, paired 0 delta, shadow 0 diff; v3 suites 366, 0 dòng test cũ
bỏ, paired 0 delta + 0 field diff, shadow 0 diff. Giới hạn: mô hình revival hai tầng
của F1 là model DUY NHẤT giữ mọi test cũ xanh (A công khai mời contest bằng contract
argument, không phải bằng chứng tuyệt đối).

**C. Named-cancel, tail-change, foreign verb, content role, same-turn cancel,
wrapper-blindness (batch 3 → v4).**
Lỗi: named cancellation không tạo revoke event; tail-change ở HISTORY turn bị bỏ;
verb ngoài inventory ("Chuyển tiếp/Forward/Share") → unknown rồi prior instruction
lọt; number-as-content bị tính là number-as-target; cancel trong CÙNG turn bị drop khi
turn đó cũng có re-issue; layer B mù wrapper. Sửa (v4): named-cancel branch
(negated + target_names = known names cho số đó + action khớp proposal → specific
event); parse_tail_change (typed + spoken, 6 forms) + attribution guard; tail-change
ở history = specific revoke event khi new tail ≠ bound tail; foreign inventory mở rộng
+ B trả other_action_verb_only khi foreign verb govern target mention (cả direct-request
và prior-instruction base); content rule cả hai path (owner exception; generic
recipients cố tình excluded); in-turn events xếp theo character position + bound-turn
final state fold; B áp _wrapped_verb_starts; M1 fragment correction thừa hưởng action
của turn classified ngay trước; M2 copula exemption hẹp; M3 _instruction_name_map
(strict: đúng MỘT số, current action khớp instruction action, family/generic excluded,
folded "minh" excluded). Kiểm tra: v4 suites 399, paired 0 delta, shadow 0 diff,
S5 independent review PASS. Giới hạn: S1 roster/log arm không quan sát được ở decide()
level cho phone proposal (chỉ unit-test qua _known_names_for_number); bare "Số mới là X"
vẫn background (fire đúng); instruction-cancel events vẫn action-agnostic (hướng an toàn).

**D. Fold state machine: revival, tail, dirty, lookup, forward, delegation, channel,
owner (batches 4–6 → v5, v6).**
Lỗi: name-only re-issue sau named-cancel không revive; hai tail-change restore tail
gốc không revive (fold gap); content rule misfire trên lookup-verb mention khi clause
sau nêu recipient khác; forward + bare call: bare "gọi" được tính positive bất kể
forward trước đó + named recipient (FALSE UN-FIRE); message request un-fire money
transfer (đã chứng minh KHÔNG có real path — xem §5); delegation "nhờ/bảo <người> gọi
số X" bị đọc thành positive call (FALSE UN-FIRE); channel exception chỉ "qua" (thiếu
bằng/ở/theo/vào); owner exception fail qua roster (_selection_targets chỉ lấy tên từ
log, không lấy roster); copula "số mới của <Name> là Y" bind thành direct request
(FALSE UN-FIRE); batch-5 tiếp: name-only revival xoá tail-changed state; tail-change
ghi đè named cancel rồi restore xoá cancel (single-state fold không biểu diễn được
"cancelled AND tail-restored"); lookup exception không check verb sau target ai
(message-specific hole); forward suppression mất trên comma/period; "Nhờ vả gọi số X"
(không delegatee) bị đọc thành delegation (false block).
Sửa (v5): revival ở fold level qua _turn_name_revive_events; transitions
specific_tail/revive_tail + length-cover rule; lookup verbs tim/lay/tra cứu/kiểm
tra/xem (bare "tra" excluded); _forwarded_target_to_other (bare verb bị suppress khi
cùng clause đã forward ĐÚNG target number cho named other recipient);
_delegated_verb_starts (nhờ/bảo + person + verb → blocked; generic "nhờ em" KHÔNG phải
delegation); channel prepositions {qua, bằng, ở, theo, vào} trong 3-token window;
_selection_targets kind phone lấy thêm tên roster; _is_owner_new_number_statement.
Sửa (v6): revival dùng transition riêng revive_cancel (chỉ clear cancel khi name vẫn
map tới bound number, không live tail-change, không dirty); fold viết lại thành
(cancel, tail_len, dirty) — cancel và tail độc lập, restore chỉ clear tail
(length-cover), dirty chỉ clear bởi full revive; lookup exception yêu cầu following
verb có object_kind "target" hoặc "general"; forward suppression xét thêm clause ngay
trước trong cùng text (không cross-turn); M1 skip "vả" làm filler trước khi scan person.
Pins (v6): N6 revoke-only (statement "số mới của <Name> là Y" → specific revoke event
cho bound old number, KHÔNG bind Y); N5 reading (i) + possessive carve-out ("nhắn cho
Bình bằng số X" → channel/address → un-fire đúng; mention kèm "của tôi/em/mình" trong
cùng clause → channel exception KHÔNG áp → fired; "của anh/chị" giữ channel reading);
delta fix possessive beats roster (2 chỗ); dirty-sticky ACCEPTED (name revival chỉ cho
undisturbed mappings; explicit number re-issue luôn revive); find-then-call SUPERSEDED
(xem §4.3). Kiểm tra: v5 suites 417, paired 0 delta + 0 trail diff, shadow 0 diff,
F-B4-5 độc lập xác nhận không real path; v6 suites 426, paired 0 delta + 0 trail diff,
shadow 0 diff. Giới hạn: "đổi thành" chưa phải redirect verb ở thời điểm này (đã sửa
ở v9); generic recipients không trigger S4 content rule (by design); tên không "cho"
không resolve trong M3.

**E. Binding action class, partition, demotion, fragment, possessive (batches 7–8
→ v7, v8).**
Lỗi: suppressed bare verb không survive vào history binding (forward+bare turn + CONT
→ false un-fire; binding action class recompute thành call/message); early X mention
(forward object, tagged requested_target) short-circuit explicit redirect sau đó
("Chuyển tiếp số X cho Bình. Tôi đổi sang số 12, gọi đi" + call X → false un-fire);
delegation exclusion ở TURN granularity không phải verb level (mixed turn delegated
call + own message → message proposal fired sai); bare number fragment giữa forward
và bare call phá suppression ("Số 12, gọi đi" — fragment có digit run ≥ 2 bị tính là
content clause); content-layer cross-clause possessive không phá roster-owner exception.
Sửa (v7): forward-recognition path thống nhất — backward scan skip CONTENT-LESS clause
(không verb, không digit run ≥ 2 ký tự), dừng ở content clause đầu tiên; standalone
proper name không làm clause thành content; forward verb không explicit mention resolve
object về most-recent TARGET mention trước nó trong cùng text (từ TEXT, không từ
proposal); recipient scan đổi thành "after forward verb"; suppressed bare verb bị đánh
`blocked` ngay sau khi verb_info build xong; turn fully-delegated bị exclude khỏi
prior-instruction branch (không mentions-revive, không continue-revive;
specific/generic preserved), per-action precision qua proposal_action; M1 possessive
mention của target phone ở BẤT KỲ clause nào cũng phá equivalence.
Sửa (v8): binding action class = verbs của turn TRỪ forward-suppressed bare verbs
TRỪ delegation-governed verbs (helper binding_action_class, mirror instruction_action;
adapter truyền base_names = roster/log names GỐC trước khi append bound addressee);
"both" thu hẹp (CHỈ khi cả call AND message đều có); M1 partition mentions theo
governing verb qua phone_numbers_for_action (preceding verb quyết định, không
fall-through; "và"-chain share object; "rồi" KHÔNG chain; chỉ multi-number turns);
S2 demotion trong parse_phone_mentions (mention là object của forward verb → role
"background"/"forwarded_object", governing check strict + generic-recipient exemption
+ backstop "đổi sang" + số khác → explicit_redirect_supersedes); M2 bare fragment
(digit-run / spoken digit / "số") = content-less cho backward scan; M3 possessive_phones
precompute (owner exception chỉ khi mention không khớp possessive phone nào).
A tự bắt 3 bugs trong vòng 8 (callback+other → "both" mirror bug; preceding-verb
fall-through; demotion generic exemption), đều fix + test pin. Kiểm tra: v7 suites 437,
paired 0 delta + 0 field diff, shadow 0 diff; v8 suites 453/505, paired 0 delta + 0 field
diff, shadow 0 diff. Giới hạn: suppressed-verb fallback reason label approximate;
elided resolution dùng most-recent TARGET mention (multi-number err về fire);
instruction_action vẫn đếm delegated verbs (chỉ ảnh hưởng M3 fact map).

**F. Selection-evidence: joint veto + government rule (batches 9–10 → v9, v10).**
Lỗi (batch 9): bare mention không verb tự authorize call/sms (prefix rỗng, không
history): "À, số X", "Số X phải không?", "Số X đẹp quá", "Số X, chuyển cho em đi" →
un-fire qua requested_target + selection unknown. Root: binding + selection unknown →
proven (vi phạm trực tiếp contract R4). Sửa (v9): joint veto trong decide() (callback
proposal, B không veto, layer C không veto, nhưng B selection unknown/no_callback_verb
VÀ layer-C selection không phải continue/name_resolved → FIRE) + 3 gate thu hẹp:
(a) mention_present (chỉ veto khi current text trực tiếp nhắc value; bare anaphor
exempt); (b) M2 marker ("number + là số mới/khác" frame, reason ma_new_number_selection
= selection evidence cho correction); (c) owner-recipient ("cho <owner>" exempt theo
pin N1; khác transfer-to-agent "cho em" generic). Veto thô ban đầu phá 4 test cũ;
phân tích trail cho distinction sạch. Layering: transfer-to-agent vừa KHÔNG bị demote
(giữ generic exemption) VỪA KHÔNG select action — hai tính chất cùng đúng.
Lỗi (batch 10): verb leak — callback verb ở đâu đó + number mention ở đâu đó =
positive selection (generic_callback_positive), bất kể government/thứ tự/câu/assertion:
"Gọi số X đi, số Y" + call Y → un-fire. Ba path, một mechanism: general-events path
(object span bắt đầu bằng "số" bị tính "general" dù chứa number khác); fallback path
(unconditional positive cho MỌI positive verb); event-loop path (nearest-preceding-verb
positive cho "Gọi số X số Y đi" / "…rồi số Y" / "…đi số Y" + call Y). Bypass joint veto
v9 (veto chỉ trigger khi selection unknown; leak manufacture ra selection positive).
Defense ellipsis bị bác: chỉ bao biện được 1c (Y sau verb, cùng clause), không bao biện
được F1c (Y trước verb) và F1d (Y mang assertion). Sửa (v10): government rule thống
nhất — verb select đúng number nó govern: explicit object → chỉ object đó (span chứa
BẤT KỲ number nào cũng "specific", không "general"); event loop skip event khi có
number khác xen giữa verb và mention, trừ "và"-chain ("rồi" không chain); bare verb +
1 số → select nó (S3 general rule giữ); bare verb + nhiều số → không select số nào
(fallback unknown, reason mới positive_verb_not_governing_target); cross-action bound
giữ (message verb không leak sang call). Fallback version đầu TOO BROAD (phá 11 test cũ
+ 4 probe vì lật PINNED veto-gate contract cho NAME-governing verbs: M3 name-only,
family "mẹ", log-counterpart dựa vào fallback no-veto vì B không có target-name mention)
— refined fallback khôi phục tất cả; chỉ NUMBER government và bare-target cases thành
unknown. Paired regression tự tìm của A và đã sửa trong candidate (KHÔNG nới expectation):
0676 (spoken number comma-groups — fragment của target không phải competitor; substring
test) và 1677 (correction frame — rejected run không phải competitor; rejected-exclusion
CHỈ trong has_other_number, không áp cho (F-a), hướng an toàn); cả hai về đúng reason
gốc v9; paired 0 delta. Kiểm tra: v9 suites 462/514, paired 0 delta, shadow 0 diff;
v10 suites 476/528, paired 0 delta, shadow 0 diff. Giới hạn: ellipsis thật giờ fired
(ambiguous → fire, boundary cost); gate (c) double-object không "cho" chưa cover;
batch-11 S1 mở (xem §5.C).

**G. Inventory gaps (taxonomy: mechanism chạy đúng, chỉ thiếu verb-form — MINOR).**
- Bare-"chuyển" (batch 8, MINOR, hướng không an toàn, hẹp, ĐÃ ĐO, chưa sửa): "Chuyển
  số X cho Bình, gọi đi" + call X → un-fire; sms fired đúng; explicit call un-fire đúng;
  redirect fired nhờ backstop; "chuyển tiền" không bị nhận nhầm thành forward. Hướng sửa:
  pattern "chuyển" + số phone-shaped + cho/tới/đến + người, cho cả demotion lẫn
  suppression, kèm shape guard phân biệt "chuyển tiền"/"chuyển sang". Vòng 9 drop theo
  escape hatch (opportunistic); vòng 10 không nằm trong scope (B nói rõ khác "gửi").
- "đổi thành" (batch 9 M1, ĐÃ SỬA ở v9): backstop mở rộng sang họ switch ("đổi sang",
  "đổi thành", "đổi lại", "chuyển sang").
- "gửi" (batch 10 M1, ĐÃ SỬA ở v10): thêm bare "gui" vào message inventory (dạng dài
  thắng bằng longest-match); phân biệt: "nhắn" recipient-directed (bare number =
  recipient), "gửi" thing-directed (bare number + không named recipient = ambiguous →
  fire); named target owner trong clause resolve được; money guard trong _find_verbs
  (single point): reject bare-"gửi" trước money/goods/parking/mail heads, bare amounts
  (<9 digits), number-word + amount-word. S4 content vẫn dominate cho non-owner.

### 4.3 Finding đã đóng / còn mở / bị rút lại / đổi cách hiểu (không litigate lại)

ĐÃ ĐÓNG (fix + probe pass + paired/shadow 0 delta): R4 gốc; batches 1–3 SERIOUS
(S1–S15, F1–F8, S1–S6 + M1–M3); batch 4 MINORs (8/9; F-B4-5 chứng minh không real path);
batch 5 SERIOUS (S1–S4 + M1); batch 6 SERIOUS (S1–S3 + M1); batch 7 SERIOUS (S1/S2 +
M1/M2/M3); batch 9 S1 (joint veto) + M1 (switch family); batch 10 S1 (government rule)
+ M1 ("gửi").

CÒN MỞ: batch-11 S1 (SERIOUS, digit-run misclassification); batch-11 M1 (MINOR,
fragment/group joining); bare-"chuyển" (MINOR); channel + cross-clause possessive
(boundary); dirty-sticky (accepted, safe-direction); same-verb hai số unbound (chosen
degradation); gate (c) double-object gap (narrow, safe-direction); name-bare + bare-verb
fallback preemption (v10 boundary, batch 11 adjudicate là đúng cho number-identified
proposals — xem dưới); prover lifecycle + eligibility (BLOCKER riêng, §5).

BỊ RÚT LẠI / ĐỔI CÁCH HIỂU (không tính là finding, không báo lại):
- M5b (batch 1): expectation DISPUTED, behavior đúng (default proposal_position =
  max+1 nên cancel turn tại position 5 IS trước proposal position 6 → fire đúng).
- X2 (batch 2): B tự rút (parallel requests không phải replacement → un-fire đúng).
- Batch 2: B rút 2 cases (X2 + S15d7 short pause then do, consistent với Md7).
- Batch 3: B rút 6 expectation errors + 1 void fixture (session-echo fixture 11e,
  lỗi fixture của B).
- Batch 4: G2 suffix-tail (suffix chứng minh không đổi; veto cần proof); G2
  longer-tail-345678 (lỗi fixture của B — 345678 IS last 6 digits của X; sửa thành
  345679 re-verify fired); G2 guard-same-turn-other (binding đã broken, an toàn).
- Find-then-call (batch 4 G3) SUPERSEDED bởi S3: expectation cũ encode premise
  pre-S3 ("mọi positive following verb đều làm lookup thành preparatory"); S3 chứng
  minh premise đó quá rộng; dưới "ambiguous → fire", fire là đúng; không có carve-out
  có nguyên tắc (name/verb carve-out = fake fix). Baseline batch 4 = 92/103 + 1 superseded.
- 8b-generic (batch 10): expectation error của B (un-fire là đúng theo rule S4 đã công
  bố: generic "cho em" cố tình không trigger content rule; reading benefactive).
- F4a (batch 11): expectation error của B (un-fire là đúng: 2345 không phải phone
  mention; 1 phone mention + truly bare verb → general rule select Y đúng). Hệ quả:
  cặp F4a/F4b KHÔNG test được tính target-relative của substring rule (general rule
  preempt trước khi fallback chạy) — tính này vẫn UNTESTED (không confirmed, không
  refuted); paired gold chỉ validate outcome 0676.
- 1h (batch 8): stale expectation theo pin N1 (hành vi đúng là un-fire; probe encode
  expectation cũ fired). Code KHÔNG được sửa để 1h "pass" probe.
- Dirty-sticky: ACCEPTED làm rule (không phải finding mở cần "sửa" — name revival chỉ
  cho undisturbed mappings).
- F-B4-5: KHÔNG phải finding (đã chứng minh không real path, 2 lần độc lập) + standing
  warning nếu gate học đọc arg `phone`.

## 5. Danh sách việc chưa hoàn thành

Mỗi mục ghi nhóm (A–F), bằng chứng, ảnh hưởng, sửa bằng CPU được không, cần
inference/GPU hay dữ liệu gì, ai làm tiếp, dependency, tiêu chí hoàn thành.
"Ngoài scope" KHÔNG có nghĩa "không thể sửa"; "có module" KHÔNG có nghĩa "đã giải
quyết trong runtime".

### A. Chưa được giao / bị prompt cấm làm

**A1. Bật chặn trong runtime (hard-enforce).**
Bằng chứng: R4 brief cấm ("do NOT wire prover lifecycle or enable hard-enforce");
adoption bar §4.5 chưa đạt (xem §6.7). Ảnh hưởng: gate không bảo vệ model thật.
CPU được không: hook là CPU, nhưng chứng minh non-interference cần chạy model
(GPU) on/off. Ai: user quyết định sau khi bar đạt; Codex implement hook + flag OFF
trước. Dependency: B1 + adoption bar. Hoàn thành khi: bar đạt + on/off diff sạch +
user approval riêng cho việc bật. Hiện tại: KHÔNG làm.

**A2. Gửi câu hỏi BTC (Q-L1..Q-L5, Q-D1, vLLM/XGrammar, param counting,
derived-checkpoint cutoff).**
Bằng chứng: draft tồn tại, NEVER sent (trích kết quả cũ). Ảnh hưởng: SFT chưa đủ
điều kiện train (Q-L2); LifeMate compliance questions chưa có đáp án. CPU: không
liên quan. Ai: user duyệt → người được chỉ định gửi. Dependency: user approval.
Hoàn thành khi: câu hỏi đã gửi + có trả lời (hoặc BTC xác nhận không cần).

**A3. Wire prover observation expiry + eligibility suppression.**
Bằng chứng: R4 brief cấm wire prover lifecycle; lifecycle report liệt kê expiry +
eligibility suppression là blocker riêng, chưa nối. Ảnh hưởng: derived invalidation
chưa tới được prover verdicts; eligibility chết chưa suppress được call. CPU: phần
lớn là CPU (wiring + test), nhưng cần paired/shadow re-verify (CPU). Ai: task mới —
Muse hoặc Codex (chưa giao). Dependency: không phụ thuộc BTC. Hoàn thành khi: expiry
đổi verdict đúng (test), suppression đổi decision đúng (test), paired 0 delta ngoài
ý muốn, shadow 0 diff ngoài ý muốn.

**A4. Re-audit friend repo (khoakhoahihi/ZAIC-Track-LifeMate-).**
Bằng chứng: user chỉ thị STOPPED 2026-10-28, never reopen by another route.
Ảnh hưởng: friend-harness numbers mãi mãi non-comparable. Ai: không ai (bị cấm).
Hoàn thành khi: không áp dụng (mục cấm, không phải mục làm).

### B. Đã viết nhưng chưa nối vào pipeline

**B1. Toàn bộ G&G (adapter/prover/gates/negation/phone/lifecycle) → runtime hook.**
Bằng chứng: grep §1.3 (agent không import adapter ở mọi trạng thái; adapter chỉ được
audit script + test gọi). Ảnh hưởng: mọi số paired/shadow đều offline; gate không
ảnh hưởng model thật. CPU được không: viết hook là CPU; chứng minh non-interference
cần chạy agent thật (GPU cho model runs) + diff CPU. Ai: Codex implement hook theo
brief §6 lifecycle report; Muse verify. Dependency: brief §6 (có sẵn); flag OFF
default. Hoàn thành khi: hook chạy decision-only + log đầy đủ + on/off diff sạch
(submitted calls + final state + termination giống hệt) trên dev mẫu (không held-out).

### C. Đã thử sửa nhưng vẫn có repro lỗi

**C1. Batch-11 S1: digit-run object misclassification (SERIOUS, mở).**
Bằng chứng: r4b11_probes + followup2 (F2a/S1a/S1d) trên frozen v10; xem §4.2.F.
Ảnh hưởng: verb govern fragment/short run → select nhầm phone mention duy nhất
(hướng không an toàn, nhưng trigger hẹp: cần non-phone digit-run object + đúng 1
phone mention + cùng action). CPU được không: CÓ (classification fix + unit test).
Ai: Muse (vòng 11) hoặc Codex (nếu nhận vòng). Dependency: không. Hoàn thành khi:
F2a/S1a/S1d fired; F4a/batch-10 1c/2b-noroster/S1b giữ nguyên; paired 0 delta;
shadow 0 diff; batch 12 không tìm ra SERIOUS mới cùng cơ chế.

**C2. Batch-11 M1: fragment/group joining (MINOR, mở, hướng an toàn).**
Bằng chứng: r4b11_followup F1/F2b trên v10. Ảnh hưởng: chunked dialing không bind
→ false block (an toàn nhưng bất tiện); tần suất thực tế thấp (ASR thường trả
contiguous). CPU: CÓ. Ai: Muse/Codex. Dependency: không phá fragment rule
(fragment một mình không full mention vẫn phải fired). Hoàn thành khi: chunked numbers
bind đúng mọi separator; fragment-alone vẫn fired; paired/shadow 0 delta.

**C3. Bare-"chuyển" (MINOR, mở từ batch 8, hướng không an toàn, hẹp).**
Bằng chứng: r4b8_probes 3i + re-verify batches 9–11 (không lan rộng). Ảnh hưởng:
"Chuyển số X cho Bình, gọi đi" + call X → un-fire sai. CPU: CÓ. Ai: Muse/Codex.
Dependency: shape guard phân biệt "chuyển tiền"/"chuyển sang" (đã có bằng chứng
"chuyển tiền" không bị nhận nhầm). Hoàn thành khi: case đích fired; sms fired;
explicit call un-fire; redirect fired; "chuyển tiền" vẫn fired (không forward).

**C4. Channel + cross-clause possessive (boundary, cần policy pin trước khi code).**
Bằng chứng: batch 8 N2 + M3 cross-clause (đã đo). Ảnh hưởng: input tự mâu thuẫn
(roster: X là của Vy; text: X là của tôi) + cross-clause possessive → un-fire.
CPU: CÓ sau khi có pin. Ai: user chốt pin (channel exception có mở rộng cross-clause
không?) → Muse/Codex implement. Dependency: quyết policy. Hoàn thành khi: pin được
ghi + implement theo pin + test cả hai chiều (same-clause giữ nguyên).

**C5. Relation synonyms, out-of-inventory verbs, quoted-name veto layering.**
Bằng chứng: R4 report §6 + batch findings (relation "bố"/"ba" không match; verbs
ngoài inventory abstain như verb-less; quoted-name binding dựa vào B veto).
Ảnh hưởng: một số cách nói tự nhiên bị abstain/fire (hướng an toàn) hoặc dựa vào
layering mong manh. CPU: CÓ nhưng cần quyết policy trước (R4 cấm patch keyword
riêng lẻ — synonyms phải là policy, không phải blacklist). Ai: user/Muse quyết policy
→ implement. Dependency: không. Hoàn thành khi: policy ghi rõ + implement có scope +
red-team không tìm ra leak mới.

### D. Chưa đủ dữ liệu / trace để đánh giá

**D1. E7 guard readiness (CPU_NOT_READY — KHÔNG phải E7 REFUTED).**
Bằng chứng: E7 Phase 0 shadow audit (trích kết quả cũ): dev gold 31 ALLOW, 428
UNKNOWN, 0 BLOCK → positive coverage 6.75%; parser unchanged trong E7. Ảnh hưởng:
guard như đặc tả không đủ coverage để đánh giá bằng GPU. CPU: CÓ (redesign/thu hẹp
hoặc mở rộng evidence). Ai: Muse redesign → user duyệt GPU run sau. Dependency:
không chạy GPU khi chưa CPU-ready. Hoàn thành khi: CPU audit cho coverage đủ cao +
gold false-block = 0 (gate G1–G5 trong brief E7) rồi mới chạy GPU 40-trial.

**D2. Substring rule target-relativity (0676).**
Bằng chứng: batch-11 F4a expectation error (general rule preempt trước fallback).
Ảnh hưởng: không biết substring fix có thực sự target-relative hay chỉ là
general-rule counting. CPU: CÓ (thiết kế probe tới được fallback, không dùng
bare-verb + fragment). Ai: red-team (Muse). Dependency: không. Hoàn thành khi:
probe isolate được rule (kết quả đổi chiều khi đổi target, giữ nguyên khi đổi
fragment không liên quan).

**D3. 1d-rejected path indistinguishability.**
Bằng chứng: batch-11 N4 (outcome consistent, trail label generic_callback_positive
không phân biệt live-mention counting vs fallback exclusion). Ảnh hưởng: không
chứng minh được mechanism nào đã chạy. CPU: CÓ (trail instrumentation phân biệt
hai path). Ai: Muse/Codex. Dependency: không. Hoàn thành khi: trail ghi rõ path +
probe 1d-rejected cho kết quả phân biệt được.

**D4. End-to-end score impact (proxy hay official).**
Bằng chứng: không có e2e run nào với gate on/off (xem §6.7). Ảnh hưởng: không biết
gate có cải thiện điểm thật không. CPU: KHÔNG (cần chạy agent thật = GPU cho model
runs; diff là CPU). Ai: Codex (shadow runtime) → Muse (phân tích). Dependency: B1.
Hoàn thành khi: shadow runtime chạy + on/off diff + proxy delta được đo (và ghi rõ
là proxy, không phải official).

**D5. T2 raw traces đã mất (/tmp/t2_v10_trace.json, /tmp/t2_v11_trace.json).**
Bằng chứng: /tmp cycling (trích kết quả cũ). Ảnh hưởng: trace-level native details
của E1 V10/V11 UNVERIFIED, chỉ còn report-level. CPU: KHÔNG khôi phục được (cần
chạy lại agent = GPU, hoặc chấp nhận report-level). Ai: Codex (chạy lại nếu cần)
hoặc chấp nhận. Dependency: agent run tương đương (config a2e832b). Hoàn thành khi:
trace regenerate được HOẶC ghi nhận vĩnh viễn là report-level only.

**D6. Zero-shot benchmark base selection (cho SFT).**
Bằng chứng: SFT handover (base PROVISIONAL; results pending — trích kết quả cũ).
Ảnh hưởng: SFT chưa chọn được base để pilot. CPU: KHÔNG (benchmark cần GPU).
Ai: UNKNOWN — cần user cho biết benchmark do ai chạy, kết quả ở đâu (xem §Thông tin
chưa biết). Dependency: kết quả benchmark. Hoàn thành khi: base được chọn có bằng
chứng + contract cập nhật (không còn PROVISIONAL).

### E. Chờ luật / BTC / dependency bên ngoài

**E1. Câu hỏi BTC (xem A2).** Blocks SFT train readiness (Q-L2) + LifeMate
compliance. Ai: user duyệt gửi.

**E2. SFT pilot/train.** Blocks: Q-L2 (E1) + base selection (D6). Không train trước
khi cả hai resolve. Ai: Codex pilot sau khi đủ điều kiện. Dependency: E1 + D6.
Hoàn thành khi: pilot chạy được + kết quả CPU-verified + quyết định train/no-train
có bằng chứng.

**E3. Friend-harness 4 access questions.** Không có trả lời; audit đã STOPPED (A4).
Không phải dependency của G&G (chỉ ảnh hưởng so sánh model selection, đã có hướng
riêng: re-measure trên dev + proxy của mình).

### F. Chủ động không hỗ trợ trong thiết kế hiện tại

| Mục | Lý do thiết kế (không phải lỗi chưa sửa) |
|---|---|
| LLM verifier dưới 6B/30s | Round 9 architecture: dynamic grammar + provenance DAG + deterministic gates; verifier LLM tốn budget + mất determinism |
| "Prove 100% of values" | Literally unachievable (round 9 kết luận) |
| Generic recipients trigger S4 content rule | Speaker-reference ambiguity để ngỏ có chủ ý; benefactive reading ("nhắn cho em") → un-fire là đúng |
| Bare "Số mới là X" authorize call | Bare statement không authorize call; fire là đúng/an toàn |
| G1/G3 gates | DROP có chủ ý sau audit (không thêm lại nếu không có bằng chứng mới) |
| Cross-app provenance | UNPROVEN by design (57 residual cross-app trong E7 audit) |
| Ellipsis readings | Ambiguous → fire có chủ ý (contract R4) |
| Folded "minh" trong name map; tên không "cho" trong M3 | Boundary cost đã công bố |
| Same-verb hai số unbound; shared-object multi-number degrade | Safe degradation đã chọn |
| Spaced digits / "tư" / compound amounts | BLOCKED area đã công bố (ASR loss); không phải mục sửa trong scope hiện tại |

## 6. Dữ liệu và phép đo

### 6.1 Split: train 1545 / dev 1237 / held-out 308

- train.jsonl: 1545 samples (đã verify trong task này bằng đếm: samples = 1545).
- Split file: `lifemate/splits/train_dev_heldout.json` — dict mapping sample id →
  "dev"/"heldout" (đã verify file tồn tại trong worktree a2e832b; không đọc nội dung
  held-out). Seed 42. Dev 1237 / held-out 308.
- Stratify: empty/ask_only/ask_after/normal (trích kết quả cũ). Cùng tool-sequence có
  thể ở cả hai phía — 695 sequence cho 1545 mẫu (trích kết quả cũ) — nên held-out đo
  khái quát trong họ template, không phải khái quát sang template hoàn toàn mới.
- Held-out: CHỈ dùng làm post-freeze verification, KHÔNG BAO GIỜ dùng cho
  selection/tuning; không mở nội dung held-out trong bất kỳ task nào của đợt này.
  Mọi số paired/shadow/probe trong tài liệu này đều là dev (hoặc synthetic), trừ khi
  ghi rõ khác.
- Data locations (không nội dung): `~/workspace/zaic-data/lifemate/extracted/
  train+public_test/train/` = audio/, train.jsonl, train_environment/,
  train_tools_catalog.json (147 tools: write 84, read 62, meta 1, zaic_tools/ — trích
  kết quả cũ), zaic_tools/. DataMate: `~/workspace/zaic-data/datamate/` (extracted/,
  public_test.zip, train.zip). Không push raw data lên nhánh (đúng quy tắc).

### 6.2 SFT inner split (trích kết quả cũ — manifest v2)

- Inner split v1 giữ nguyên làm control (không đụng). Manifest v2: inner_train 866 /
  val 185 / test 186; effective train 865 eligible; chỉ train_1696 ineligible
  (giữ trong evaluation với anomaly flag; anomaly: not_done_steps [2] — xác nhận qua
  SFT fix report trên nhánh sft-prototype-v2).
- Quarantine REVERSED: train_1005/1033/1319 trả lại evaluation AND training với
  contact_source=message_history flag; train_1696 chỉ loại khỏi training.
- Contract pinned PROVISIONAL `a2e832b-text`. H1 ("pure SFT only learns ask form")
  là hypothesis chưa chứng minh; D1-lite là falsifiable pilot; DPO conditional only.
- Manifest v2 (đã verify trong task này qua GitHub API directory listing + đọc đầu
  file): `analysis/overnight_capability_audit/inner_split_seed1337_v2.json` trên nhánh
  sft-prototype-v2 (280,662 bytes; generator
  `analysis/overnight_capability_audit/generate_inner_split_v2.py`; version "v2";
  seed 1337; base = v1 `inner_split_seed1337.json` FROZEN, "v1 population was
  dev-minus-quarantine = 1233"; population = "full dev 1237 (quarantine returned to
  evaluation pool)"). Counts trong file: inner_train 866 / inner_val 185 /
  inner_test 186. `train_eligible_counts`: eligible 1236 / excluded 1 (universe = toàn
  dev 1237); `train_eligible_reasons`: train_1696 (gold trajectory có not_done steps —
  xem fix report cho wording đầy đủ). Phân biệt hai con số dễ nhầm: 1236 eligible là
  trên toàn dev (1237 − 1); 865 effective train là eligible TRONG inner_train
  (866 − 1, vì train_1696 nằm trong inner_train). Cả hai đều đúng, khác universe.
  File cũng ghi `near_duplicate_group_whole_to_train` (vd train_0061/0066/0168 —
  near-duplicate groups đi nguyên nhóm vào train).
- sft_prototype_local.json: local-only, KHÔNG BAO GIỜ push, KHÔNG đưa vào bàn giao
  này (đã xác nhận sự tồn tại theo quy tắc, không đọc nội dung).

### 6.3 Các con số 976 / 533 / 276 — scope + commit (đã verify nguồn trong task này)

**Gates denominator 976 (paired audit).**
Nguồn: `research/lifemate/round10-fix-report-round3.md` (correction note) +
C10 paired output (trích kết quả cũ). Dòng denominator: 971 (verb scope) → 957
(kind scope, old gate) / **976 (kind scope, new gate có phone refs)**.
Định nghĩa: dev gold writes mà candidate gate applicable (gate scope cover call:
phone/contact/other-ids reference present). Command (từ docstring
`analysis/gg_paired_audit.py`): `python3 analysis/gg_paired_audit.py --train-jsonl
<train.jsonl> --data-root <dir containing train/> --split
lifemate/splits/train_dev_heldout.json --lifemate-dir <dir containing lifemate/*.py>`.
Kết quả (C10, trích kết quả cũ): applicable 976/976; baseline fired 15/976 (1.54%);
candidate fired 2/976 (0.20%); 13 decision changes (un-fires); synthetic control
976/0 (candidate-with-empty-evidence phải fire khi applicable, else pass vacuously);
0 errors. Backend: CPU (ToolEnv replay). Giới hạn diễn giải: gold trajectories +
dataset transcripts (KHÔNG phải model ASR transcripts — shadow mới dùng ASR);
gold-match ≠ valid positive (prerequisites phải thỏa tại model prefix, else
"gold_match_but_prerequisite_skipped"); script KHÔNG adjudicate (coordinator adjudicate
từng change từ adjustment trail). Nhóm reference: phone / contact / other-ids;
anomaly train_1696 báo cáo riêng AND trong with/without sensitivity line.
Fired rows cuối (candidate): train_1005 pos 1 (contact) + train_1696 pos 2 (other_ids
anomaly). 13 un-fires: 0451, 0502, 0579, 0657, 0664, 0676, 0746, 0764, 0776, 0872,
1033, 1319, 1677 (IDs, không kèm nội dung).

**E7 prover audit: 456 writes / 533 args / 276 PROVEN.**
Nguồn: `research/lifemate/round10-fix-report-round3.md` §4.1, commit thuộc nhánh
round10-provenance-gates-fixes @ 61d84390 (report tự ghi không thể chứa SHA của chính
commit chứa nó — cùng self-reference note như báo cáo R4).
Scope: dev gold calls có catalog kind = write, ≥1 monitored arg, trừ
`sys.ask_missing_info`: **456 writes / 533 args** (value 426, contact 107).
Kind classification: catalog. Kết quả Round 3 (kind scope) vs Round 2 (verb scope):
Args 556 → 533; DAG PROVEN 284 (51.1%) → **276 (51.8%)**; Baseline PROVEN 93 → 92;
Conversion 191 → 184; Value DAG/baseline 195/4 → 188/4; Contact DAG/baseline 89/89 →
88/88; UNPROVEN/AMBIGUOUS 262/10 → 251/6. DAG theo rule (R3): roster 88,
datetime_assembly 53, relative_date 36, offset 34, duration 24, number_words 18,
number_digits 17, observation 4, supersede 2. Residual UNPROVEN: cross-app 57
(by design), no source 184, roster-no-intent 10. history_reference = 0 PROVEN trên
gold (4 proofs cũ là single-match-among-many mislabel, đã sửa thành AMBIGUOUS).
Giới hạn: số Round 2 chỉ đúng dưới verb-list scope của nó (đã SUPERSEDE bởi Round 3);
đừng trích 556/284/93/191 làm hiện trạng.

**Repr-string reconciliation (đã verify trong task này bằng đếm lại type, không đọc
nội dung).**
Full file 1545 samples, 3491 history assistant turns: tool_results list 2981,
field ABSENT 510 (turns không có call), str 0. Docstring `gg_shadow.py` ghi "list
(2981 turns) or None (510 turns...)" — cùng số; "None" ở đây = field absent (không
phải giá trị None được lưu). Con số "MISSING 4001" trong reconciliation cũ =
3491 user turns (không có tool_results field) + 510 assistant no-call turns =
4001 (đếm MỌI history turn). Không có mâu thuẫn: list = 2981 và str = 0 khớp mọi nguồn;
chỉ khác universe đếm (assistant turns vs mọi turn). Con số "repr-string 412" cũ
KHÔNG tái lập được từ stored types — KHÔNG được trích. Repr-string handling trong
parsers chỉ là defensive-only (json.loads → ast.literal_eval → ghi missing evidence).

### 6.4 Suites 476 / 528 (đã verify trong task này: chạy lại cả 2 backend, đều OK)

Command: `python3 tests/test_<name>.py` và `~/workspace/zaic-test-venv/bin/python
tests/test_<name>.py` trên workdir code-identical với frozen v10 (candidate-final).
Kết quả: pass 528/528 cả 2 backend, 0 fail, 0 error, 0 skip (đếm "Ran N" + "OK" mỗi file).

| File | Count | Nhóm |
|---|---|---|
| tests/test_lifemate_gates.py | 48 | 8 file chuẩn |
| tests/test_lifemate_provenance.py | 46 | 8 file chuẩn |
| tests/test_phone_callback_evidence.py | 75 | 8 file chuẩn |
| tests/test_evidence_lifecycle.py | 36 | 8 file chuẩn |
| tests/test_gates_adapter.py | 125 | 8 file chuẩn |
| tests/test_name_binding.py | 29 | 8 file chuẩn |
| tests/test_callback_negation.py | 115 | 8 file chuẩn |
| tests/test_unfire_controls.py | 2 | 8 file chuẩn |
| **Tổng 8 file chuẩn** | **476** | |
| tests/test_agent_grounding_hook.py | 4 | Grounding |
| tests/test_lifemate_grounding.py | 48 | Grounding |
| **Tổng cả 10 file** | **528** | |

"476/528" là số lượng test (unittest count), không phải coverage, không phải tỉ lệ
pass của model. Tiến trình: v1 329 → v2 353 → v3 366 → v4 399 → v5 417 → v6 426 →
v7 437 → v8 453/505 → v9 462/514 → v10 476/528 (trích kết quả cũ từ C reports các vòng;
số v10 đã verify lại trong task này). Dòng test cũ bị gỡ/đổi expectation trong toàn
đợt R4: đúng 3 dòng đã cite (v4 "Gửi tiền" instruction_action unknown → other; v6 S3
lookup rewrite giữ positive assertions ở dạng tied; v10 replacement test veto
attribution, outcome không đổi). Không expectation nào khác bị nới.

### 6.5 Ba phép đo khác nhau — đừng trộn

| Phép đo | Đo cái gì | Input | Pass/fail nghĩa là gì | Con số hiện tại |
|---|---|---|---|---|
| Gold false block (paired audit) | Gate chặn một gold-correct call có đủ evidence | Gold trajectories dev, dataset transcripts, ToolEnv replay | false_block = blocked nhưng proposal IS correct call với sufficient evidence | Baseline 15/976; candidate 2/976 (C10, trích kết quả cũ) |
| False un-fire (red-team probe) | Gate cho qua một proposal synthetic sai/không được authorize | Synthetic prefix + current text + proposal (do B tự tạo, không dùng gold) | fail = un-fire khi expected fired (theo construction rõ ràng; mơ hồ thật → expected fire) | Danh sách finding theo batch (§4, §7); KHÔNG phải tỉ lệ — đừng tính "tỉ lệ pass probe" thành metric |
| Model-trace outcome (shadow) | Guard decision trên model proposal thật từ trace đã lưu | Saved model traces (V10/V11/V13), model-received transcripts (ASR), causal prefix | correct_block / false_block / correct_pass / miss / out_of_scope / insufficient_evidence (mỗi write proposal đúng 1 category) | V13 control (trích từ docstring gg_shadow.py): 29 write proposals, 16 monitored calls, 19 monitored args, blocked 16 / passed 6 / out-of-scope-guard 7 |

Quy tắc từ docstring gg_shadow.py: "NEVER merge versions/arms into one opaque metric:
one run = one trace file; summaries are per file." Paired và shadow khác input một
cách có chủ ý (paired: dataset audio_text; shadow: model ASR transcripts) — đừng so
sánh trực tiếp hai con số như cùng một phép đo.

### 6.6 V10 / V11 / V13 — input / transcript / history

- V10: trace `analysis/runtime/e1_v10_diagnostic_trace.json` (committed, tồn tại trong
  frozen v10). V11: `analysis/runtime/e6_c_v11_diagnostic_trace.json`. V13:
  `analysis/runtime/e5_v13_diagnostic_trace.json`. (Các file này KHÔNG phải T2 raw
  traces đã mất — xem D5.)
- Input theo docstring gg_shadow.py (đã verify trong task này bằng cách đọc script):
  current text = trace's model_current_transcript (model nhận được, KHÔNG phải gold
  audio_text); history user texts = trace's history_asr (theo u-number order);
  history tool records = sample's ORIGINAL history tool_calls/tool_results; turn
  observations/priors/rosters = trace tool events STRICTLY BEFORE proposal's generation
  event trong cùng trace (reads → turn observations; mọi event → PriorCall với recorded
  result + succeeded flag). NEVER: current proposal, rejected proposals, future tool
  results, gold values (gold CHỈ dùng cho adjudication bên ngoài, không feed vào evidence).
- Row = một write proposal trong trace. Counts (trích kết quả cũ từ C reports v8–v10,
  rows identical khi so paired): V10 14 rows, V11 10 rows, V13 29 rows. Breakdown
  decision từ output C v10 (trích output cũ, chưa chạy lại): V10 passed 8 / blocked 6;
  V11 passed 4 / blocked 6; V13 blocked 16 / passed 6 / out-of-scope-guard 7 (khớp
  regression control trong docstring gg_shadow.py).
- Trace metadata (chỉ đọc metadata, không đọc nội dung trace): cả 3 traces đều có
  field `usage = 'DIAGNOSTIC_ONLY_NEVER_AGENT_INPUT'` — trace là diagnostic-only,
  không bao giờ là agent input. Đừng viết "trace chạy trên agent a2e832b": trace sinh
  từ commit 5fb5d0a (V10) / a472006 (V11, V13) như đã ghi ở trên.
- Quan hệ script: `gg_shadow.py` = `model_trace_shadow.py` + phần adapter shadow
  (import `adapter_decide`, dựng `hist_prefix` bằng ASR texts, `cand_prefix/cand_pos`,
  gọi `adapter_decide`). Docstring usage của gg_shadow.py còn ghi tên cũ
  `model_trace_shadow.py` — đừng nhầm thành hai script khác nhau.
- Provenance chính xác của từng trace (đã verify trong task này từ audit .md trong
  analysis/runtime/, là primary source — ưu tiên hơn standing note):
  - V10 (E1 V10, audit E1_V10_AUDIT_2026-10-28.md): source
    `5fb5d0aa8d405cd3d9dc5f5abaa743f10df633de` (opt-in native), control gốc a2e832b;
    16/16 trials, cùng cached V7 ASR current/history, revisions, seed, data/split và
    settings; dev only; text arm reproduce V7 submissions/raw generations trên 8/8
    samples; proxy 0.125 → 0.1875; prerequisite 5/21 → 4/21; runtime 406.1s.
    Audit command: `python ../artifacts/lifemate-e1/v10-result/audit.py` (ZIP CRC,
    prompt hash reconstruction, V7 comparison, simulator replay, proxy recomputation).
    Derived traces đã publish LOẠI full prompts, gold transcripts/calls, audio, weights.
  - V11 (E6-C V11, audit E6_C_V11_AUDIT_2026-10-28.md): source
    `a472006441ec69aee1238153b0c7daf53ba41dee`; mọi thứ giống V10 (model/revisions,
    greedy seed42, context/output reserve, grounding, loop limits, data release, dev
    split, FP16/T4 placement, attention) — CHỈ opt-in reject_pseudo_calls thay đổi;
    16/16 trials; native_control arm reproduce V10 trên 8/8 samples (+ 7 samples còn
    lại của boundary arm cũng reproduce V10 chính xác, trừ timing); runtime 373.3s.
    Audit: `v11-result/audit.py` (ZIP CRC, prompt hash reconstruction, V10 exact trace
    comparison, simulator replay, proxy recomputation, parser diagnostics, frozen
    prerequisite checks). Source/parser vẫn là a472006 đã push trên experiment branch;
    main chỉ nhận analysis.
  - V13 (E5 V13, audit E5_V13_AUDIT_2026-10-28.md): **base
    `a472006441ec69aee1238153b0c7daf53ba41dee` (GIỐNG V11)**, native V10 + E6-C parser
    enabled ở cả hai arms; chỉ trial arm thêm đúng brief ab780806 reminder rule ngay
    sau ACTION_POLICY (không E6-B); greedy seed42, FP16/T4x2, maxsteps12, maxrepeats2,
    context16384/output512, grounding và scorer giống V11; 40/40 trials, proxy
    recomputation khớp; G1–G5 hoàn thành trước comparative LLM run; ASR-only v12
    transcribe độc lập 20 samples/65 audio files, revision a86b604 (khớp prefix của
    a86b604c trong standing note); control 0116 reproduce chính xác E6-C V11.
    Audit: `../artifacts/lifemate-e5/audit.py` rồi `review.py` (CRC, cached input,
    78 generation-message hashes reconstruct qua actual AgentLoop, replay, proxy
    recomputation). Runtime 643.4s (không phải bằng chứng A30).
  - **Hiệu chính:** standing note cũ ghi "E5 V13 (main e2245ab1)" là SAI nếu hiểu
    e2245ab1 là code commit của V13 — audit (primary source) ghi base a472006 và
    "source/model revisions... match V11". e2245ab1 có thể là commit của artifact
    snapshot hoặc repo state khác, nhưng KHÔNG được trích làm code commit của V13
    nếu không có bằng chứng riêng; ghi UNKNOWN cho ý nghĩa của e2245ab1.
- History parsing guard (mới trong shadow v2): tool_results kỳ vọng là list aligned
  với tool_calls. Dạng repr-string (hoặc non-list, non-None) KHÔNG được zip thầm lặng —
  parse bằng json.loads rồi ast.literal_eval; nếu không ra list thì ghi missing evidence
  cho sample đó (parse note trong output) và các call bị ảnh hưởng không đóng góp
  observation/succeeded flag. Sample nào thiếu history evidence thì MỌI proposal của
  nó bị adjudicate "insufficient_evidence" (guard decision vẫn được tính và báo cáo để
  row còn dùng được cho paired re-run). Trên data này guard không bao giờ fire
  (list 2981 / str 0 — xem §6.3).

### 6.7 Independent positives + adoption bar + tăng điểm

- Independent positive (định nghĩa từ lifecycle report §4.5 + capability audit):
  một "correct block" trên model proposal sai, mà guard chặn đúng với đủ evidence,
  trên một sample độc lập với các sample khác (variants của một fixture KHÔNG tính
  là nhiều positive độc lập). Đếm hiện tại: **1 (train_0004)** — trích kết quả cũ.
- Adoption bar (trích nguyên văn lifecycle report §4.5): "guard false-block <= 2%
  Wilson upper <= 5% AND correct blocks on >= 3 independent situations".
  Trạng thái: **FAILS on the second leg** (chỉ 1 < 3). Chân thứ nhất: candidate
  false-block 2/976 = 0.20% (point estimate); tính nhẩm Wilson 95% upper ≈ 0.7%
  (dưới 5%) — con số này là tính nhẩm của người viết bàn giao, CHƯA phải số audit;
  Codex tự tính lại nếu cần dùng làm bằng chứng. Các báo cáo ghi failure ở chân thứ
  hai, không ghi failure ở chân thứ nhất.
- **Tăng điểm end-to-end: CHƯA chứng minh ở bất kỳ mức nào.** Không có e2e run với
  gate on/off; không có proxy delta nào thuộc về gate. Các số sau KHÔNG phải gate gains
  (đừng trích sai): E1 V10 proxy 0.125 → 0.1875 là thí nghiệm prompt/format (không phải
  G&G); E5 V13 INCONCLUSIVE (target ask-first 0/7 → 1/7, control 0/13 → 0/13); E0 không
  đổi (0.125 → 0.125, gold current transcript only, history vẫn ASR — KHÔNG phải
  perfect information). SOTA corrections đứng: E0 không phải perfect information;
  prompt/format/retry ceiling toàn họ CHƯA chứng minh; resolver ≠ provenance guard.

## 7. Test / red-team artifact

### 7.1 Committed tests (trên nhánh @ 287e68d5)

10 file trong §6.4. Ba file test thay đổi trong commit 287e68d5 (SHA đã verify
remote == local, §1.2). Bảy file test còn lại không nằm trong commit này (đã có từ
parent 6030f760); nội dung của chúng trên nhánh == frozen v10 vì các vòng R4 không
chạm tới chúng (suy luận từ cumulative diff base→v10 = đúng 6 file code/test +
report — Codex có thể verify bằng cách đọc từng file tại commit 287e68d5 qua API).
Toàn bộ 10 file đã chạy lại trong task này trên code-identical workdir: 528/528 cả
2 backend (§6.4).

### 7.2 Local-only probes / batches (không có trên nhánh)

Thư mục: `~/workspace/zaic-gg-r4-probes/` — 126 files (đã liệt kê trực tiếp trong
task này). Nhóm chính:
- `r4_r123.py` — R4 repro gốc (1 control + 3 cancel).
- `r4b<N>_probes.py` (N = 4–11) + `r4b<N>_followup*.py` — probe scripts của luồng B
  (batch 4–11; batch 1–2 đã mất theo §7.3; batch 3 chỉ còn `r4b3_findings.py` +
  `r4b3_followup.py`, không có file tên `r4b3_probes.py`).
- `r4b<N>_report.md` (N = 5–11) + `r4b<N>_a_handover.md` (N = 5–10) +
  `r4b<N>_a_probes.py` (N = 5–9) + `r4b6_delta_probes.py`, `r4b7_coord_check.py`,
  `r4b8_debug.py` — handovers/reports của luồng A và B (round 10 của A chỉ còn
  `r4b10_a_handover.md`, không có `r4b10_a_probes.py` riêng).
- `r4a_paired_*.json`, `r4a_shadow_*.json` — paired/shadow outputs của luồng A
  (v3, cand4).
- `r4c_paired_*.json` (v5–v9 + fresh variants) — paired outputs của luồng C.
- `a_selfcheck_*.json` (paired v9/v10; shadow v9/v10 × v10/v11/v13) và
  `c_verify_*.json/.py` (paired v3–v10 + fresh; shadow v3–v10 × v10/v11/v13 + fresh;
  `c_verify_fb45.py`, `c_verify_s5.py`, `c_verify_test_update.py`,
  `c_verify_v5_spot.py`) — verification outputs của luồng C.
Quy tắc tái chạy: mỗi probe đánh trên đúng freeze của nó (r4b<N> đánh trên
frozen-v<N-1>); mọi probe tự viết đều truyền `proposal_position` tường minh;
không chạy paired comparison trên checkout đang bị sửa.
Probe quan trọng chưa có trên repo (Codex cần nếu muốn tái chạy mà không có
workspace local): minimal sanitized reproduction cho batch-11 S1 + M1 và R4 repro
gốc — xem §8.4 (script tối thiểu + lệnh chạy). Các probe khác có thể tái tạo từ
mô tả mechanism trong §4 (mọi case đều dùng fixture X/Y + prefix/current/proposal
rõ ràng trong B reports).

### 7.3 Batches đã mất artifact / không tái tạo được

- Batch 1–2 probe scripts: nằm trong /tmp, đã mất do /tmp cycling. Kết quả batches
  1–2 chỉ còn ở dạng B/C reports (đã ghi trong §4.2.B); không chạy lại được script gốc.
  Hệ quả: findings batches 1–2 được tin ở mức report-level (đã qua C verification
  thời đó + không bị vòng sau bác), không phải mức re-runnable.
- T2 raw traces: /tmp/t2_v10_trace.json, /tmp/t2_v11_trace.json đã mất. Trace-level
  native details của E1 V10/V11 UNVERIFIED, report-level only (xem D5). Các diagnostic
  traces committed trong analysis/runtime/ KHÔNG phải T2 traces này — đừng nhầm.
- Các freeze giữa (v1–v9) chỉ còn local (zaic-gg-r4-frozen-vN); không push. Nếu
  workspace local mất, chỉ còn v10 (commit 287e68d5) + base (6030f760) là khôi phục
  được từ remote. Các vòng giữa chỉ còn truy vết qua báo cáo R4 §2–§3.

### 7.4 Cases không chạm tới branch đang test (preemption — thiết kế probe mới phải tránh)

1. Bare-verb + fragment (F4a): general rule preempt trước khi fallback chạy →
   không test được substring rule target-relativity (D2).
2. Bare verb + ≥2 phone mentions: ambiguous veto preempt → không test được
   government rule (cần đúng 1 mention hoặc explicit object).
3. S4 content preempt: non-owner recipient trong clause → fired bởi content rule
   trước khi selection logic được quan sát (muốn test selection thì dùng owner hoặc
   generic recipient).
4. First-refusal-wins: khi B và C cùng veto, trail chỉ ghi veto của B (layer-C veto
   không quan sát được) — muốn test layer C riêng thì cần construction B không veto.
5. P3g filter preempt: session log records bị filter trước khi baseline gate thấy →
   muốn test baseline-gate behaviour trên log records thì dùng history-origin records.
6. Joint veto preempt: khi B veto, joint veto không được quan sát (veto của B đã
   đủ) — muốn test joint veto thì cần B không veto + selection unknown.

### 7.5 Final review + stop condition

- Final reviewer đã đọc ĐÚNG commit 287e68d5 qua GitHub API (get_commit +
  get_file_contents với ref = chính SHA): PASS trên 5 hạng mục (đúng 7 file, SHA khớp,
  code chứa joint veto + government rule + "gửi"/money guard như mô tả, không hardcode
  — 2 hit train_* là comment giải thích rule chung, report trung thực: batch 11 NOT
  clean, clean count 0, stop condition NOT met, chữ "GO" duy nhất trong report là
  phủ định "This report is NOT a GO"). Reviewer KHÔNG chạy lại suites (dựa vào SHA
  chain: remote SHA == local SHA của file C v10 đã chạy). PASS này là checkpoint
  verification, KHÔNG phải phê duyệt hard-enforce.
- Không có commit nào sau 287e68d5 trên nhánh (đã verify qua list_commits) → không
  có post-review change nào cần re-review. Quy tắc: bất kỳ push nào sau commit này
  cũng cần review mới trước khi được coi là checkpoint.
- **Stop condition R4: CHƯA đạt.** Cần HAI batch sạch liên tiếp trên frozen candidates.
  Lịch sử: batch 4 sạch (#1 chuỗi cũ) → batch 5 reset (4 SERIOUS) → batch 6 (3) →
  batch 7 (2) → batch 8 sạch (#1 chuỗi mới) → batch 9 reset (1) → batch 10 (1) →
  batch 11 (1). Clean count hiện tại = 0. Còn lại: vòng 11 (sửa batch-11 S1/M1) +
  batches 12–13 (hai batch sạch liên tiếp mới đủ điều kiện dừng).

## 8. Hợp đồng giữa các module

### 8.1 Schemas (synthetic examples; X/Y là fixture, không phải số thật)

**Prefix / history events (đầu vào decide).**
```python
# History user turn:
{"kind": "user_turn", "text": "<current request text>", "position": 0}
# Session event (ToolEnv replay, gold order):
{"tool": "phone.call", "args": {...}, "result": {...}, "outcome": "succeeded",
 "position": <int>, "origin": "session"}   # origin: "history" | "session"
# Roster:
[{"id": "<id>", "name": "<name>", "phone": "<phone>"}]
# kinds map (catalog kind, không phải verb guessing):
{"phone.call": "write", "contacts.search": "read", ...}
```
**decide signature (adapter:1770).**
```python
def decide(call, prefix, roster, current_text, kinds, proposal_position=None):
    # prefix: raw prefix entries (history + session, proposal EXCLUDED)
    # roster: [{id, name, phone}]
    # current_text: dataset text (gold audit) hoặc ASR transcript (shadow)
    # kinds: catalog kind map hoặc None
    # proposal_position mặc định = max(prefix positions) + 1, else 0
```
**CandidateDecision (adapter:155).**
```python
{"fired": bool, "applicable": bool,
 "baseline_fired": bool, "baseline_reason": str,
 "adjustments": [{"reference": str, "old": ..., "new": ...,
                  "mechanism": str, "basis": str,
                  "question_b": bool, "question_b_reason": str,
                  "sources": [...]}],
 "notes": {"filtered_log_records": int, "adapter_gaps": [...],
           "ledger_notes": [...], "mutation_fields": [...]}}
```
**Ledger record (lifecycle module).**
```python
{"kind": ..., "value": ..., "source": ..., "producer": ...,
 "field": ..., "outcome": "succeeded"|..., "counterpart": ...,
 "position": int, "claim": "existence"|"field_value",
 "status": ..., "reason": ...}
# derived_from: [{"registry": ..., "value": ..., "claim": ...}]
# MUTATION_KINDS = ("delete", "cancel", "update", "create", "none")
# TERMINAL_STATUS_VALUES = ("cancelled",)
```
**Prover (lifemate_provenance.py).**
```python
prove_argument(slot, value, tool, evidence, rules=None, call_args=None)  # :1418
prove_call(call, evidence, rules=None)                                   # :1797
# Verdict statuses: PROVEN, UNPROVEN, AMBIGUOUS, SUPERSEDED
# "a segment can be a proven error, not a proof — counts as would-block, never PROVEN"
# UNKNOWN source is never defaulted to same-app/PROVEN
# Offset rule: derived value PROVEN only if base value independently PROVEN
# Week/month reference with no day is never a day, never PROVEN
# Two tasks with the same value are not one → AMBIGUOUS
```
**Outcome rule (mọi module dùng chung).**
`outcome = "succeeded"` iff `ok is True AND done is not False`. Còn lại:
schema_rejected (ok False — chỉ khi schema error), failed, hoặc noop
(ok True + done False, state không đổi). Helper: `result_succeeded` định nghĩa
rule này trong `lifemate_evidence_lifecycle` (adapter import nó tại
lifemate_gates_adapter.py:151); `_outcome(entry)` tại adapter:178 là mapper local
từ recorded entry sang một trong ("succeeded", "failed", "schema_rejected",
"noop", "unknown") — ưu tiên entry["outcome"] nếu có, else entry["succeeded"] boolean.
(Đã verify trong task này bằng cách đọc trực tiếp hai hàm.)
**Phone evidence.**
```python
# Digit runs: {"kind": "digits" | "spoken" | "mixed"}
# Mentions: {"span": ..., "kind": ..., "role": ...}  # role: requested_target |
#   background | forwarded_object | ...
# Prefix user turns: {"kind": "user_turn", "text": ..., "position": ...}
```

### 8.2 Assumptions mà caller PHẢI đảm bảo

1. Proposal KHÔNG nằm trong prefix; arguments của proposal KHÔNG BAO GIỜ là evidence.
2. Positions có thứ tự nhất quán: history 0..H-1, session H+idx (replay theo gold order).
3. Roster đầy đủ cho sample (contacts search/get records); kinds map khớp catalog
   mà agent dùng.
4. current_text là CURRENT request text (dataset text trong gold audit, ASR transcript
   trong shadow — KHÔNG BAO GIỜ dùng gold audio_text trong shadow).
5. proposal_position = max(prefix positions) + 1 (default); KHÔNG dùng giá trị cũ/tái
   sử dụng. Mutation tại đúng proposal_position tính là "before".
6. Không gold label, không future turn, không state.json / environment internals
   trong prefix. ToolEnv là đường truy cập state duy nhất.
7. P3g filtering chạy TRƯỚC: baseline gate priors VÀ ledger thấy cùng filtered
   session log records; history records KHÔNG BAO GIỜ bị filter; chỉ session-origin
   READ results bị filter.
8. Per-sample reset: fresh ledger + fresh prefix mỗi sample; adapter không giữ state
   giữa các call.
9. Synthetic probes phải truyền proposal_position tường minh (không dựa vào default
   khi prefix chứa position lạ).

### 8.3 Nơi adapter cho qua trong khi module abstain (exceptions có bằng chứng)

Quy tắc chung: UNKNOWN trong action-selection KHÔNG thành PROVEN chỉ vì binding tìm
được record. Các exception sau được phép vì có bằng chứng riêng (pin/test), không
phải vì "module abstain nên adapter cho qua":

| Exception | Khi nào adapter cho qua | Bằng chứng cho phép |
|---|---|---|
| M2 correction gate (b) | B selection no_callback_verb + frame "number + là số mới/khác" (reason ma_new_number_selection) + prior-instruction context | M2 original un-fire giữ qua v9/v10; phân biệt với F1d (fresh call, verb govern số khác → fired) |
| Owner-recipient gate (c) | Current text có "cho <owner-name>" với owner = roster owner của value | Pin N1 (batch 8): forward recipient = owner → suppression không áp (recipient phải là "other"); candidate-collapse |
| Bare anaphor / prior-instruction continue gate (a) | mention_present=False + bound prior instruction + continue selection (vd CONT) | Pin v1 + 0764 (instruction continue, mention_present False) giữ qua v9/v10; S12/S5 tests |
| NAME-governing fallback no-veto | Verb govern NAME (không phải number) + B không có target-name mention → fallback không veto | PINNED veto-gate contract (M3 name-only, family "mẹ", log-counterpart); batch-11 N1 xác nhận: chỉ đúng cho NAME-identified proposals, không áp cho number-identified proposals (2a fired đúng) |
| Transfer-to-agent generic exemption | Mention "cho em/mình" không bị demote (generic exemption) VÀ không select action | V9 layering: demotion và selection là hai tính chất khác nhau; S4 rule công bố (generic cố tình không trigger content) |
| S4 owner exception | Recipient là owner của target number → mention không bị tính là content | Pin S4 + v8/v10 (roster owner-tie); đối lập: named non-owner → fired |
| 1319 topic branch (non-callback) | Topic/amount match là REFERENCE RESOLUTION, không phải action selection; un-fire vì current text TỰ NÓ chứa explicit transfer verb + recipient name + amount | Adjudication đứng (v3): current text tự select, không phải topic branch select |

Ngược lại, KHÔNG exception cho: bare mention không verb (v9 joint veto fired);
verb leak (v10 government rule fired); forward object mention (v8 demotion fired);
delegated turn binding (v7 exclusion fired); digit-run object misclassification
(batch-11 S1 — sẽ fired sau vòng 11).

### 8.4 Minimal sanitized reproduction (cho Codex chạy không cần workspace local)

```python
# Repro R4 gốc + batch-11 S1 trên bất kỳ checkout nào chứa adapter + phone module.
# Chạy từ thư mục chứa lifemate/ (vd frozen v10). Không cần dataset, không GPU.
import sys; sys.path.insert(0, "lifemate")
from lifemate_gates_adapter import decide

X, Y = "0902345678", "0911111111"   # fixture synthetic, không phải số thật
KINDS = {"phone.call": "write", "sms.send": "write"}

# R4 repro (phải 4/4: control un-fire, 3 cancel fired):
prefix = [{"kind": "user_turn", "text": "Gọi số 0902345678 giúp tôi", "position": 0}]
call = {"name": "phone.call", "arguments": {"phone_number": X}}
for text, want in [("Làm như em dặn lúc nãy", False),                       # control: un-fire
                   ("Thôi, không cần làm như em dặn lúc nãy nữa", True),    # cancel: fired
                   ("Khỏi làm như lúc nãy nữa", True),
                   ("Đừng làm như em dặn lúc nãy", True)]:
    d = decide(call, prefix, [], text, KINDS, proposal_position=1)
    print(text, "-> fired:", d.fired, "want:", want, "OK" if d.fired == want else "FAIL")

# Batch-11 S1 (v10: un-fire SAI; sau vòng 11 phải fired):
for text, prop in [("Gọi số 2345 đi, số 0911111111", "sms.send")]:
    d = decide({"name": prop, "arguments": {"phone_number": Y}},
               [], [], text, KINDS, proposal_position=0)
    print("S1:", text, "-> fired:", d.fired, "(v10: False = bug; post-v11: True)")
# Lưu ý: proposal_position truyền tường minh (quy tắc §8.2.9).
# Lệnh chạy suites: python3 tests/test_lifemate_gates.py ... (10 file, §6.4).
```

## 9. Kế hoạch tiếp theo

Thứ tự concrete, dựa trên trạng thái thật. KHÔNG thực hiện các bước này trong task
bàn giao này (user cấm) — đây chỉ là kế hoạch cho Codex / phiên sau.

1. **Vòng 11 (hẹp, CPU):** sửa batch-11 S1 — general/bare classification CHỈ cho verb
   KHÔNG có digit-run object nào; mọi verb có digit-run object (phone hay fragment/
   short) đều không phải general → không select phone mention khác. Controls giữ:
   F2a/S1a/S1d fired; F4a / batch-10 1c / 2b-noroster / S1b giữ nguyên; paired 0 delta;
   shadow 0 diff; pinning tests dùng synthetic numbers (không copy gold text).
   Sau đó freeze v11 → batch 12 red-team. (Bare-"chuyển" có thể gộp vào vòng 11 nếu
   điều phối viên thấy không xung đột — không ép; nếu gộp thì verify riêng từng fix.)
2. **Batch-11 M1 (CPU, MINOR, có thể cùng vòng 11 hoặc vòng riêng):** group-joining
   trong parse_phone_mentions với separator set tường minh; verify fragment-alone
   vẫn fired; paired/shadow 0 delta.
3. **Probe substring rule (CPU):** construction tới được fallback (không bare-verb +
   fragment) để isolate tính target-relative của 0676 fix (D2); kèm trail
   instrumentation phân biệt live-mention counting vs fallback exclusion (D3).
4. **Policy pins (cần user quyết trước khi code):** channel + cross-clause possessive
   (C4); relation synonyms + out-of-inventory verbs (C5 — policy, không patch keyword).
5. **Runtime shadow hook (Codex, cần GPU cho model runs):** implement hook quanh
   gate_read_before_write theo brief §6 lifecycle report (decision-only, per-sample
   reset, before/after logging đầy đủ, flag default OFF). Sau đó diff on/off trên
   identical inputs (submitted calls + final state + termination) — bất kỳ khác biệt
   nào cũng là blocker, hook không được ship nếu diff không sạch.
6. **Đo blocking precision trên model proposals (sau bước 5):** chạy shadow trên
   traces mới (không phải gold trajectories) để tìm independent correct-blocks thứ 2,
   thứ 3 (hiện chỉ có 1 = train_0004).
7. **Prover lifecycle + eligibility wiring (task mới, CPU + re-verify):** wire observation
   expiry vào prover verdicts; wire eligibility suppression vào gate decision; test +
   paired/shadow re-verify (A3).
8. **E7 guard (CPU trước, GPU sau):** redesign/thu hẹp evidence cho tới khi CPU audit
   cho coverage đủ + gold false-block = 0 (D1); KHÔNG chạy GPU 40-trial khi chưa
   CPU-ready.
9. **SFT (chờ E1 + D6):** không train khi chưa có trả lời Q-L2 và chưa chọn base từ
   benchmark; pilot chỉ sau khi cả hai resolve.
10. **Không cần research thêm:** government rule, joint veto, fold machine, S4 content,
    pins N1/N5/N6, bare-"chuyển" fix direction, digit-run fix direction (đã đủ bằng
    chứng trong §4). Đừng mở lại các finding đã rút/superseded (§4.3) trừ khi có
    construction mới chứng minh chúng sai.
11. **Điều kiện thử shadow runtime:** hook + flag OFF + logging đầy đủ + on/off diff
    sạch trên dev mẫu (không held-out). **Điều kiện cân nhắc bật chặn (hard-enforce):**
    adoption bar đạt (false-block Wilson upper ≤ 5% + ≥ 3 independent correct-blocks)
    + non-interference diff sạch + user approval riêng. Hiện tại: KHÔNG đạt — đừng bật.

## Checklist cho Codex

- [ ] Đọc báo cáo R4 (`research/lifemate/gg_r4_binding_action_selection_report.md`
  @ 287e68d5) trước khi chạm code; đọc lifecycle report §6 trước khi chạm hook.
- [ ] Verify branch tip vẫn là 287e68d5 (nếu có commit mới, review lại từ đầu — §7.5).
- [ ] Chạy 10 suites (§6.4) cả 2 backend: kỳ vọng 528/528, 0 fail/error/skip.
- [ ] Chạy paired audit trên dev (command §6.3): kỳ vọng applicable 976, candidate
  fired 2/976, 13 un-fires, synthetic 976/0, 0 errors.
- [ ] Chạy shadow trên V10/V11/V13 traces (§6.6): kỳ vọng rows identical với C10
  (14/10/29 rows, 0 diffs).
- [ ] Chạy minimal repro §8.4: R4 4/4 đúng; batch-11 S1 un-fire (bug mở, kỳ vọng).
- [ ] Trước khi sửa vòng 11: đọc §4.2.F + §5.C1/C2 + §7.4 (preemption) để tránh phá
  pins; pinning tests dùng synthetic numbers.
- [ ] Trước khi implement hook: đọc brief §6 lifecycle report + §8.2 (assumptions);
  hook phải decision-only, flag OFF, log đầy đủ.
- [ ] Trước khi trích số: kiểm tra scope trong §6.3 (976 ≠ 533 ≠ 528; Round 2 numbers
  đã supersede; repr-string 412 không được trích).
- [ ] Không dùng held-out cho selection/tuning; không mở held-out content; không push
  raw data/traces/prompts; không merge vào main; không sửa MEMORY.md trong task code.
- [ ] Mọi thay đổi expectation trong test phải cite như §6.4 (đúng 3 dòng đã cite
  trong R4; không nới expectation để test xanh).

## Thông tin chưa biết / cần Codex cung cấp

1. ~~Tên file manifest SFT v2 chính xác~~ — ĐÃ GIẢI QUYẾT trong task này:
   `analysis/overnight_capability_audit/inner_split_seed1337_v2.json` trên nhánh
   sft-prototype-v2 (xem §6.2; phân biệt 1236 eligible toàn dev vs 865 effective
   trong inner_train).
2. ~~Provenance chính xác của traces V10/V11/V13~~ — ĐÃ GIẢI QUYẾT trong task này từ
   audit .md trong analysis/runtime/ (xem §6.6), kèm hiệu chính: V13 base là a472006
   (giống V11), không phải "main e2245ab1" như standing note cũ.
3. ~~ASR revision PhoWhisper-small~~ — ĐÃ GIẢI QUYẾT (cross-check 2026-10-30):
   full SHA `a86b604c346caf7148c37512eafe783a16420adb` từ trace metadata cả 3
   traces; config JSON không pin ASR revision (xem §1.3).
4. **Wilson upper chính thức** cho candidate false-block 2/976 (bản bàn giao chỉ tính
   nhẩm ≈ 0.7%; cần tính lại có audit trail nếu dùng làm bằng chứng adoption bar).
5. ~~Tên helper outcome chính xác~~ — ĐÃ GIẢI QUYẾT trong task này:
   `result_succeeded` trong `lifemate_evidence_lifecycle` (adapter import tại :151);
   `_outcome(entry)` tại adapter:178 là mapper local (xem §8.1).
6. ~~Inventory đầy đủ thư mục probes local~~ — ĐÃ GIẢI QUYẾT trong task này:
   126 files, liệt kê theo nhóm tại §7.2.
7. ~~Chi tiết function-level của agent loop a2e832b~~ — ĐÃ GIẢI QUYẾT trong task này
   bằng cách đọc trực tiếp worktree a2e832b (xem §2.1: cmd_infer, AgentLoop.run,
   build_base_prompt, render_observation_prompt, _render, parse_model_output +
   hiệu chính __invalid__).
8. **Người chạy zero-shot benchmark (D6) và vị trí kết quả** — cần user cho biết
   (benchmark đang chạy ở đâu, kết quả sẽ về đâu).
9. **Quyết định policy** (cần user, không phải Codex tự quyết): channel cross-clause
   pin (C4); relation synonyms scope (C5); có gửi câu hỏi BTC không (A2/E1); vòng 11
   do Muse hay Codex làm (C1/C2).
10. **Ngân sách GPU cho các bước cần model runs** (shadow on/off diff, E7 40-trial sau
    khi CPU-ready, benchmark D6) — cần user xác nhận trước khi chạy.

## Phụ lục A — Cross-check từ luồng pipeline (2026-10-30)

Sau khi bản chính được push (commit 47424307), luồng bằng chứng pipeline đã bàn giao
và điều phối viên đã spot-verify trực tiếp từng điểm mới trước khi đưa vào đây
(grep + đọc metadata, không tin mù). Các điểm sau BỔ SUNG (không sửa kết luận chính):

1. **V10 agent.py ≠ A2E agent.py** (xem §2.2): không ACTION_POLICY, observation
   truncate 300 ký tự, outcome gộp not_done→ok, roster tracking + NEEDS_ASK →
   ask_missing_info. Main == V10 agent (byte-identical), nhưng cả hai đều khác A2E.
2. **Module grounding A2E chi tiết** (xem §2.2): helpers parse_money/parse_date/
   normalise_id/ground_name, EvidenceLedger (evidence.py:33), FUZZY 88.0/8.0,
   RapidFuzz/difflib, không có module hook riêng.
3. **Config default grounding = True** (config.py:47); chỉ baseline.json tắt tường
   minh (xem §2.2).
4. **ASR rev + LLM snapshot full SHA từ trace metadata** (xem §1.3):
   a86b604c346caf7148c37512eafe783a16420adb và
   cdbee75f17c01a7cc42f958dc650907174af0554; config JSON không pin ASR rev.
5. **Trace usage = DIAGNOSTIC_ONLY_NEVER_AGENT_INPUT** cho cả 3 traces; decision
   breakdowns V10/V11 từ output C v10 (xem §6.6); quan hệ gg_shadow =
   model_trace_shadow + phần adapter shadow.
6. **ASR backends** (bổ sung cho §2.1, chưa verify trực tiếp trong task này —
   trích từ luồng pipeline, ghi rõ nguồn): TransformersASR (WAV mono 16-bit 16 kHz,
   pipeline automatic-speech-recognition, generate_kwargs language vi / task
   transcribe / num_beams 1 / do_sample False); FasterWhisperASR là alternative
   (CT2); TranscriptOracle train-only, raise trên public_test ("Public/private
   samples must go through real ASR"). Tool list per-sample = sample.installed_tools
   + sys.ask_missing_info ("Never put the full split catalog in a prompt").

Không có điểm nào trong cross-check này làm thay đổi kết luận chính (G&G audit-only,
số paired/shadow, adoption bar, điều kiện dừng). Các điểm pipeline agent ghi
UNKNOWN (prompt template từ initial_prompt_sha256; paired 976 không chạy lại trong
luồng đó) đã được tài liệu chính xử lý: 976 ghi "trích kết quả cũ" từ C10 (§6.3),
prompt hash không được dùng làm bằng chứng nội dung.

## Tóm tắt

LifeMate baseline (Qwen3-4B-Instruct-2507 + PhoWhisper-small = 4.244B) chạy được,
nhưng G&G ở mọi trạng thái vẫn là audit-only: agent không gọi adapter, prover, gates
hay lifecycle (grep đã chứng minh). Checkpoint mới nhất là 287e68d5 trên nhánh
gg-phone-callback-lifecycle (chưa merge main), với 476 test chuẩn + 52 grounding =
528, cả hai backend đều xanh. Paired gold: candidate fired 2/976 (baseline 15/976);
E7 prover: 276/533 PROVEN; independent correct-block chỉ 1 (train_0004) nên adoption
bar chưa đạt và hard-enforce chưa sẵn sàng. R4 sửa xong contract binding/action-
selection qua 10 vòng (joint veto + government rule là hai fix lớn cuối), nhưng điều
kiện dừng chưa đạt: batch 11 còn 1 SERIOUS mở (digit-run misclassification) + 1 MINOR
(fragment joining), clean count = 0. Việc tiếp theo theo thứ tự: vòng 11 (CPU) →
batch 12–13 → hook shadow runtime (flag OFF, diff on/off sạch) → đo blocking
precision → wire lifecycle/eligibility → SFT chỉ sau khi BTC trả lời + chọn base.
Tài liệu đầy đủ là file này; mọi con số đều kèm scope + commit + giới hạn, và mọi
điểm chưa xác minh đều ghi UNKNOWN/chờ bằng chứng thay vì đoán.
