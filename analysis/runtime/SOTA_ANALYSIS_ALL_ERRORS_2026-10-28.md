# Phân tích SOTA cho toàn bộ lỗi LifeMate + đánh giá trần + hướng khác

Tổng hợp từ 3 luồng research song song (format/training, clarification/
grounding/conditional, ASR/termination/đánh giá) đối chiếu với dữ liệu
thực nghiệm của chính mình: v7, E0, E1 V10, E6-C V11. Chỉ phân tích +
đề xuất — KHÔNG sửa inference, KHÔNG chạy model, KHÔNG đổi thiết kế
E5/E2/E3/E4 đang chờ. Mọi hướng mới dưới đây đều là đề xuất sau E5,
cần user duyệt riêng trước khi làm.

Nhãn trung thực: **[ĐO]** = số liệu từ audit của mình (đã verify trên
main). **[PAPER]** = claim đã đọc abstract/toàn văn trong research.
**[SNIP]** = số lấy từ snippet/search result, chưa đọc full paper —
dùng để định hướng, không dùng để quyết định cuối. **[SUY]** = suy
luận của bản này từ các mảnh trên, không phải claim của paper nào.

Ràng buộc lọc mọi giải pháp: inference offline hoàn toàn, LLM < 5B,
hệ thống < 6B, context ≤ 16K, ≤ 30s/mẫu trên A30, deterministic
decoding, model phát hành trước 2026-10-26. Teacher lớn (nếu có) chỉ
được dùng offline để sinh training data, không bao giờ ở inference.

## 0. Kết luận trước: hướng prompt/format-only ĐÃ chạm trần

Không phải cảm nhận — là chuỗi 3 tầng bằng chứng, mỗi tầng sửa xong
một lớp thì lỗi vẫn nằm nguyên ở tầng dưới:

1. **Trần thông tin (E0) [ĐO]:** cho gold current transcript (thông
   tin hoàn hảo) mà proxy 8 mẫu vẫn 0.125 → 0.125, 0003 vẫn fail dù
   history = 0. Bottleneck không phải thiếu thông tin.
2. **Trần format (E1 V10) [ĐO]:** native contract sửa xong parsing
   (11 tagged calls đều parse được, validation rejections 3 → 0)
   nhưng proxy chỉ tăng nhờ 0004 cleanup (0.125 → 0.1875, không task
   mới nào được giải), còn prerequisite GIẢM 5/21 → 4/21 (native làm
   0016 tệ hơn). Bottleneck không phải format.
3. **Trần channel (E6-C V11) [ĐO]:** parser bắt được pseudo-call
   (caught 0 → 2, silent 1 → 0) nhưng model không khôi phục nổi
   (recovery 0/1 quan sát được) → hết retry thành format failure,
   proxy/prerequisite/hash đều không đổi. Retry cùng một generator
   không phải là recovery.
4. **Trần rule (E1 V10) [ĐO]:** policy rules 2 (evaluate conditions
   BEFORE writes), 4 (read before write), 5 (label ≠ conditional)
   đã nằm trong prompt mà model vẫn vi phạm ở native arm (0008,
   0016, 0049). Bottleneck không phải thiếu rule, mà là model không
   tuân rule — đó là capability, không phải diễn đạt.

**Verdict:** prompt + format + retry đã hết dư địa. Phần lỗi còn lại
thuộc về capability của model 4B ở 3 việc: (a) kỷ luật evidence,
(b) phân biệt intent, (c) suy luận có điều kiện. Ba việc này không
cài được bằng thêm chữ vào prompt. Hướng đi tiếp theo chỉ còn 3
loại: **đổi SYSTEM** (guard/decoding/graph bằng code),
**đổi MODEL** (training), hoặc **thu nhỏ TASK** (thu hẹp không gian
quyết định mỗi step). Phần 3 xếp hạng 3 loại này.

**Ngoại lệ trung thực:** trần này chỉ áp cho họ prompt/format/retry.
E5 (rule nhắc–gọi), E2 (conditional), E3 (ASR medium), E4 (guard)
đều chưa chạy — chúng là những can thiệp khác họ, không bị verdict
này phủ định. Đừng đọc "chạm trần" thành "dừng mọi thí nghiệm".

## 1. Catalog lỗi từ dữ liệu của mình (đối tượng của mọi giải pháp)

| # | Lỗi | Bằng chứng [ĐO] | Tầng |
|---|---|---|---|
| L1 | Act/ask-before-evidence: viết/hỏi trước khi đọc dữ liệu cần thiết | 0003 hỏi thay cho list_bills+search; 0008 update trước forecast; 0016 tạo reminder không forecast/list; 0049 mở savings không list_bills/transfer. Nặng nhất, 4/8 mẫu | Capability + system |
| L2 | Bịa giá trị/ID: contact ID, amount, time không có trong observation | 0116 `cont_01` bịa (ID thật dạng `c_01`); 0049 bịa 1200000; 0116-E0 bịa giờ; 0016-native bịa time/repeat daily | Capability + system |
| L3 | Nhắc-vs-gọi: "nhắc gọi" → gọi ngay thay vì tạo reminder + hỏi time | 0116 cả hai arm E1; gold = reminders.create/time | Decision under uncertainty |
| L4 | Sai ask entity: hỏi sai tool/params | 0003 nested ask `{ewallet.transfer, [contact_id, phone, amount]}` thay vì đọc; 0116 hỏi phone.call/contact_id thay vì reminders/time | Decision + slot detection |
| L5 | Condition-into-label: viết điều kiện vào label thay vì kiểm tra rồi mới viết | 0008 `alarm.update{label: "họp sớm (nếu mưa)"}` không forecast ở arm nào | Conditional reasoning |
| L6 | Task-type confusion: nhầm loại task | 0016 reschedule calendar → tạo (+ hoàn thành ở E0) reminder | Intent classification |
| L7 | Entity-pick vs ask: chọn bừa entity thay vì hỏi | 0025-E0 chọn bừa một Minh; 0116 đi về phone.call thay vì hỏi | Decision under uncertainty |
| L8 | Format/pseudo-call: text mang hình thức call nhưng không submit được | V10 native: 4 plain-text stops, 1 là pseudo-call, diagnostics còn đánh `format_valid: true` (lỗ đo). V11: caught → exhausted → format failure | Decoding |
| L9 | Recovery thất bại: retry elaboration thay vì sửa | V11: retry thêm param `phone_number` vào pseudo-call sai, không chuyển sang tagged call | Decoding + feedback |
| L10 | ASR-blocked: transcript garbled → stop 0 calls | 0025 cả hai arm V10 stop 0 calls; E0 chứng minh gold-current mở được 6 calls (F1 0.5455) | ASR front-end |
| L11 | ASR echo: copy text garbled vào argument | 0016-native echo ASR garbled vào reminder content | ASR + grounding |
| L12 | Premature stop: dừng khi task chưa xong | 0025 stop 0 calls; pattern chung: stop là action rủi ro thấp nhất (hash giữ đúng một cách vacuous) | Termination |
| L13 | Lỗi đo (không phải lỗi model): hash đúng nhưng F1 0; ask không đổi state nên hash không phân biệt "đã ask" với "không làm gì" | 0004 hash đúng/F1 0; 0116 hash true với 0 calls | Evaluation |

## 2. SOTA cho từng nhóm lỗi (đã lọc theo ràng buộc)

### 2.1 Nhóm format/channel (L8, L9) — có giải pháp BẢO ĐẢM

- **Constrained decoding (XGrammar / ToolDec) [PAPER/SNIP]:**
  XGrammar là backend structured generation mặc định của vLLM/SGLang;
  ToolDec chuyển tool schema thành finite-state machine, chỉ sample
  token hợp lệ → syntax errors về 0, base model 0% → tới 60% trên
  ToolBench trong paper ToolDec. XGrammar-2 thêm TagDispatch cho
  xen kẽ reasoning + `<tool_call>`. Số BFCL-v3 được báo cáo (snippet,
  chưa verify full): Llama-3.2-3B 33.12% → 77.75% khi bật grammar —
  3B có grammar vượt 70B không grammar. **Giới hạn:** grammar chỉ
  bảo đảm SHAPE, không bảo đảm intent hay giá trị đúng; và grammar
  phải cho phép toàn bộ action space (call HOẶC ask HOẶC stop) —
  nếu ép một nhánh thì chỉ đổi lỗi format thành lỗi intent. **Điều
  kiện áp dụng chưa verify:** Docker A30 chính thức có cho dùng
  vLLM + XGrammar không — phải hỏi organizers trước khi thiết kế
  quanh nó (câu hỏi mở, không phải kết luận).
- **Retry với feedback CÓ ĐÍCH [PAPER]:** literature phân biệt rõ
  intrinsic self-correction (model tự phê bình, không tín hiệu ngoài
  — Huang et al. ICLR 2024: thường làm tệ đi) với external-feedback
  correction (compiler/test/simulator error — có hiệu quả). V11 của
  mình khớp đúng dự báo: retry với message chung chung chỉ khiến
  model elaboration thêm param sai. Dạng retry duy nhất có cơ sở:
  message đích danh lỗi ("bạn emit pseudo-call dạng text, nó không
  bao giờ được execute; hoặc emit tagged `<tool_call>` JSON, hoặc
  stop bằng prose") + tối đa 2–3 attempts, budget dùng chung đã
  tính cả grounding rejection.
- **Parser recovery hẹp [SUY từ bằng chứng]:** chỉ an toàn cho hư
  hỏng SYNTAX trên call vốn đã đúng (JSON bọc markdown, JSON cụt
  cân bằng ngoặc được, cách viết XML/Hermes tương đương). KHÔNG
  được convert pseudo-call thành submitted ask — vì pseudo-call
  thường mang intent SAI (phone.call thay vì reminders.create), convert
  sẽ hợp thức hoá intent sai thành submitted call, tệ hơn fail sạch
  mà còn phá chẩn đoán. Convert ≠ recover.

### 2.2 Nhóm bịa evidence / act-before-evidence (L1, L2) — guard bằng code thắng prompt

- **Closed-world resolver / provenance guard [PAPER]:** resolver
  training-free đứng trước agent, reject tool/argument bịa chỉ dựa
  trên registry + nguồn quan sát. Kết quả đọc được: trên 10 model
  hosted, raw-JSON hallucination 13–57% (mọi model đều bịa ít nhất
  một lần); gating-only stack execute 100% hallucination; resolver
  reject toàn bộ với 0 over-rejection. **Scale không sửa lỗi này:**
  Llama-3.1 8B ≈ 70B ≈ Mistral 675B về tỉ lệ bịa. Đây là bằng chứng
  mạnh nhất cho hướng E4: mọi argument của write/ask phải truy vết
  được về transcript/history/output tool trước đó, nếu không thì
  block kèm feedback đích danh ("contact_id chưa từng xuất hiện →
  search trước" / "time chưa có → ask"). Zero model call, deterministic,
  offline — khớp hoàn toàn ràng buộc.
- **Dynamic enum grammar [SUY — composition chưa có paper đánh giá]:**
  build grammar lúc chạy từ observation ledger (ID nào đã thấy mới
  được sinh). Ghép ToolDec + resolver: giá trị bịa trở thành KHÔNG
  SINH RA ĐƯỢC thay vì sinh ra rồi chặn. Chưa có paper nào đánh giá
  đúng dạng này cho tool agent — ghi rõ là đề xuất composition, không
  phải SOTA đã chứng minh. Đáng một CPU test trước khi tin.
- **Verifier/critic [PAPER]:** CAST (Saeidi et al.) — action-level
  critique supervision trên Qwen3: +22.6% pass^1 in-domain trên
  τ-bench Retail, vượt GPT-OSS-120B > 10% pass^4 về reliability.
  Prompt verification của CAST viết đúng rule mình cần: "chỉ chấp
  nhận giá trị xuất hiện verbatim trong nguồn grounding; không truy
  vết được về USER message hoặc TOOL output thì là hallucinated."
  Chi phí: critic thêm model call mỗi step — chỉ dùng cho check
  ngữ nghĩa mà rule không biểu diễn được, và chỉ nếu budget 30s
  còn đủ. Rule guard trước, critic sau (xem §3).
- **Training cho evidence discipline [PAPER]:** SFT chỉ trên trace
  đã verify bằng simulator (APIGen-style: format + execution +
  semantic check; loại mọi trace có ID/giá trị bịa). ToolACE-8B
  91.41% BFCL; xLAM-7B 88.24% BFCL. Nhưng Tool Zero cảnh báo: SFT
  cải thiện in-distribution nhưng phẳng hoặc regress trên multi-turn
  (9.6 → 7.8 một comparison) — SFT single-turn không sửa được
  planning multi-turn. Muốn sửa evidence discipline thì train trên
  multi-turn trajectory trong simulator (Sim-Tau: Qwen3-8B 49.3
  τ-bench, vượt GPT-4 45.4), không phải trên cặp API single-turn.

### 2.3 Nhóm ask-vs-act / intent (L3, L4, L6, L7) — quyết định dưới uncertainty

- **Cơ chế gốc [PAPER]:** "Learning to Ask" (EMNLP 2025): do
  next-token prediction, model có xu hướng tự điền argument thiếu
  một cách tuỳ tiện — bịa là hành vi mặc định, không phải bug suy
  luận lẻ. Hệ quả: không có prompt nào triệt được L2/L3 hoàn toàn;
  phải có cơ chế ngoài model (guard) hoặc training chuyên biệt.
- **Ask-when-Needed / CLAM [PAPER]:** CLAM (Kuhn et al.): detect
  ambiguity bằng few-shot + logprob "ambiguous" rồi mới hỏi; adjusted
  accuracy ~54% vs 34% default GPT, câu hỏi làm rõ đúng 84–99% theo
  human judge. Tín hiệu logprob rẻ, single-pass, tương thích greedy
  decoding. Giới hạn: CLAM là QA, không phải tool-calling — cần
  phiên bản slot-level (mục dưới).
- **SAGE-Agent [PAPER]:** clarification cho tool agent dưới dạng
  POMDP + EVPI chọn câu hỏi + uncertainty theo từng parameter (không
  phải một scalar chung). Uncertainty-weighted GRPO: When2Call
  accuracy 3B 36.5% → 65.2%, 7B 36.7% → 62.9%; model 3B train kiểu
  này vượt model 7B train thường (45.1%) — **chất lượng tín hiệu >
  scale**. Phần inference (structured uncertainty + EVPI ranking)
  làm được bằng code + logprobs quanh model frozen; phần training
  cần RL setup.
- **When2Call SFT+RPO [PAPER]:** đúng bài toán ask-vs-act cho model
  4B: baseline F1 29.7, hallucination 16% → SFT: F1 48.1, hallucination
  4.3% → RPO: F1 51.0, hallucination 1.9%. Đánh đổi: BFCL AST hơi giảm
  (57.9% → 54.0%) vì model dè dặt hơn. Đây là phiên bản durable của
  rule E5 (prompt rule → training) nếu E5 cho thấy rule có tác dụng
  nhưng model không tuân ổn định.
- **Timing [PAPER]:** "Ask Early, Ask Late, Ask Right": goal
  clarification mất gần hết giá trị sau 10% trajectory; input
  clarification giữ giá trị tới ~50%; hỏi muộn quá mid-trajectory
  còn tệ hơn không hỏi. Không frontier model nào hỏi đúng window
  trong 300 session tự do. Hệ quả cho E5: quyết định ask-vs-act phải
  ở step 0 / trước first write — rule chỉ trigger sau khi model đã
  act là quá muộn về mặt nguyên tắc. (E5 hiện tại đã đúng hướng này
  vì rule nằm trong system prompt từ đầu.)
- **Tín hiệu nào dùng được ở inference [PAPER/SUY]:** (1) missing-slot
  detection bằng code (slot bắt buộc không có nguồn trong transcript/
  history/output → ask) — rẻ, deterministic, gắn nhân quả đúng với
  failure mode, là tín hiệu chính nên dùng; (2) logprob ambiguity —
  tín hiệu phụ; (3) self-consistency / semantic entropy — cần
  sampling nhiều lần, XUNG ĐỘT với deterministic decoding + budget
  30s, chỉ dùng offline (phân tích, training signal). Raw confidence
  của model vốn miscalibrated (Kadavath 2022) — không dùng làm gate
  duy nhất.
- **Ask-as-action [PAPER]:** ACTIONRATING: đặt clarification vào
  action space chung thang đo với act, ask cạnh tranh trực tiếp với
  act mỗi step; Information-Seeking Effectiveness 50% → 74%. Dạng
  policy không cần training của nó: khi uncertain giữa ask và act
  thì mặc định ask (rẻ, đảo ngược được) thay vì act (đổi state, phá
  hash) — đặc biệt đúng cho task ask-only của E5.

### 2.4 Nhóm conditional (L5) — không có paper đặt tên lỗi này, nhưng có kiến trúc sửa

- Không paper nào đặt tên "condition-into-label". Analog gần nhất:
  formal tool contracts với preconditions (practitioner literature)
  và CodeAct (check precondition inline bằng code trước khi execute).
- **State graph với conditional edges [PAPER/SUY]:** LangGraph-style:
  state là object typed; node = step; conditional edge = nhánh đánh
  giá bằng code trên observation. Task có điều kiện map thành:
  node `check_condition` → edge theo predicate đã đánh giá bằng code
  → node `act` hoặc `skip/ask`. Node write không nằm trên nhánh
  false → model không thể "viết điều kiện vào label" vì đường đó
  không tồn tại. FlowMind: Qwen3-8B ReAct 5.7% → ES-ReAct 22.7% trên
  FlowBench subset; logic/branching tasks đặc biệt ưu explicit
  pre-plan hơn reactive execution. Chi phí: graph thiết kế tay theo
  họ task (hoặc học từ trace kiểu AFlow về sau); graph do chính LLM
  tự sinh sẽ tái tạo đúng failure mode ở bước sinh graph.
- **Verification module [PAPER]:** MDPI Sensors 2026: skill constraints
  + result verification module bắt latent errors (tool chạy thành công
  nhưng output lệch yêu cầu — đúng dạng condition-into-label):
  final accuracy 93.33% vs ReAct 65.83%, Plan-and-Execute 70.83%;
  verification precision 93.55%, recall 90.63%, và token ít nhất
  (55k vs 125–148k). Verification tự trả tiền bằng token — không phải
  chi phí thuần.

### 2.5 Nhóm ASR (L10, L11) — trần thông tin, phải sửa ở front-end hoặc policy

- **N-best selection [PAPER]:** ProGRes (SLT 2024): rescoring N-best
  bằng LLM log-likelihood + ASR confidence → cải thiện WER tương đối
  5–25%; LLM-only rescoring không có ASR scores thì không cải thiện
  đáng kể. Dighe et al.: đưa N-best vào LLM (thay vì 1-best) + LoRA
  fine-tune cải thiện downstream task. **Áp dụng:** nếu "nhắc" bị
  phá ở 1-best nhưng còn trong một hypothesis N-best thì agent
  N-best-aware có thể khôi phục cue. Whisper beam search cho N-best
  miễn phí về mặt nghiên cứu (việc engineering, không phải research).
  Cost: vài chục token cho câu lệnh ngắn — không đáng kể so với 16K.
- **WCN (word confusion networks) [PAPER — kết quả âm quan trọng]:**
  Everson et al. 2024 đọc full text: zero-shot KHÔNG variant WCN nào
  thắng 1-best với bất kỳ model nào (kể cả GPT-3.5); one-shot + WCN
  thì GPT-3.5 đóng 81% gap tới oracle, còn BLOOMZ-3B vẫn không thắng
  1-best. Kết luận tác giả: model size là critical. **Đừng tốn
  context vào WCN strings cho Qwen3-4B nếu không fine-tune.**
- **Specialized corrector [SNIP]:** ECLM 2025: seq2seq corrector nhỏ
  train trên mixture real + synthetic ASR errors vượt generic LLM,
  nhỏ hơn 15×, nhanh hơn 5–40×, không hallucination, cắt WER tương
  đối 13% trung bình 8 datasets, generalize qua nhiều ASR architecture.
  Công thức áp dụng được: TTS tiếng Việt → PhoWhisper-small → cặp
  noisy/clean để train corrector < 500M (vừa budget < 6B). Nhưng đây
  là pipeline training, chỉ làm khi slot-error rate sau N-best
  selection vẫn biện minh được.
- **Confidence-gated policy [PAPER/SUY]:** Naderi et al. Interspeech
  2024: chỉ correct câu/từ dưới ngưỡng confidence — correct mọi thứ
  sẽ phá cả câu vốn đúng. RLLM-CF: pre-detection gate là thành phần
  chống over-correction. Grounding theory (Clark & Brennan): chọn
  grounding action theo expected utility — P(đúng) từ ASR confidence
  × cost sai. **Policy cụ thể cho mình:** slot nào chỉ có từ ASR
  confidence thấp và không catalog read nào xác nhận → ask, không
  echo vào write; cue word confidence thấp hoặc vắng mặt khỏi mọi
  N-best → clarify, không đoán, không stop. Đây là policy bằng code
  (threshold + provenance), không phải hy vọng prompt — vì model đã
  chứng minh nó sẽ đoán (bịa time/ID) thay vì hỏi.
- **Trần thông tin [SUY — quan trọng]:** nếu cue "nhắc" bị ASR phá
  hoàn toàn thì không phương pháp LLM-side nào khôi phục được intent
  — signal đã mất. Phần lỗi này là bài toán ASR (E3: medium model,
  decoding tốt hơn) hoặc interaction design (ask-when-uncertain),
  không phải bài toán agent. Khi đo E5/E3, phải tách riêng mẫu
  cue-destroyed khỏi mẫu agent-fail (brief E5 đã làm đúng việc này
  bằng cột ASR cue) — nếu không sẽ kết tội sai agent.

### 2.6 Nhóm termination (L12) — sửa harness trước khi trách model

- **MAST (NeurIPS 2025) [SNIP]:** 1,642 traces, 7 frameworks: step
  repetition 15.7%, unaware of termination conditions 12.4%,
  incorrect/incomplete verification ~17% gộp. Can thiệp: làm rõ
  final-decision authority +9.4% task success, thêm verification step
  +15.6% — cùng model, không đổi weights. Lỗi dừng sớm/loop của mình
  là 2 mode phổ biến nhất trong taxonomy lớn nhất của field.
- **DeReAct [SNIP]:** tách policy ReAct thành Critic validate action
  trước execution + Context Manager certify completion TỪ STATE
  (không phải từ claim của model). Gains +6.5–7.0 points Pass@1 cho
  model yếu, +4.2–5.2 cho model mạnh — gains lớn nhất ở model yếu,
  đúng trường hợp mình. Áp dụng: completion gate kiểm tra bằng code
  (required reads đã xong? required ask đã submit? không ID bịa?)
  — stop chỉ được chấp nhận khi gate pass, nếu không loop tiếp với
  hint "thiếu X" trong budget retry hữu hạn. Critic có thể là chính
  model 4B với prompt hẹp, fresh context (không thừa hưởng optimism
  của actor) — hoặc pure code khi điều kiện check được.
- **Loop detection bằng fingerprint [SUY từ practice]:** hash
  (tool_name, result_preview) mỗi iteration; 3 fingerprint giống nhau
  liên tiếp = stuck. Phân biệt activity vs progress: progress = state
  thay đổi, không phải output text mới. PHẢI state-aware vì control
  legitimate-repeat (gold loyalty.redeem ×2) tồn tại — detector chỉ
  đếm repetition sẽ phá đúng case đó. Hiện đã có max_steps 12 /
  max_repeats 2; nâng cấp là progress theo state, không phải theo
  output similarity.
- **Reflexion [PAPER — với caveat]:** AlfWorld 63% → 97%, HumanEval
  80% → 91% với external feedback thật. Nhưng "Honest Lying" 2026:
  reflection với feedback binary/outcome-level bị frozen 46%,
  correct 5.9% mỗi transition; chỉ feedback step-level, cụ thể
  ("argument X không xuất hiện trong observation nào") mới sửa được.
  Thesis replication 2026: model low-capacity không dùng được nội
  dung Reflexion. Kết luận cho mình: đừng làm generic "reflect and
  retry" — nếu làm reflection thì feedback phải là grounding-specific
  message từ guard, và vẫn xếp sau critic bằng code.

### 2.7 Nhóm đo (L13) — sửa metric, không sửa model

- **τ-bench [PAPER]:** reward = state hash × output text. **Do-nothing
  loophole [PAPER]:** agent không làm gì đạt 38% (airline) / 6%
  (retail) trên task không đổi state — đúng dạng ask task của mình
  (ask không đổi state nên hash luôn đúng). Patch đã có trong brief
  E5 là đúng: ask-first (first submitted call = gold ask, 0 calls =
  FAIL) báo cáo DỌC, không bao giờ average chung vào state score.
  Best practice từ τ²-bench: báo state / trajectory / communication
  thành 3 trục riêng.
- **Prerequisite checklist là procedural axis [PAPER/SUY]:** AgentPex
  2026: trace có thể outcome 1.0 nhưng vi phạm procedure bắt buộc
  (bỏ verification sau action). "Đoán đúng mà không đọc" phải FAIL
  procedural ngay cả khi outcome đúng — checklist 21 quan hệ của
  mình nên giữ vĩnh viễn như một trục đánh giá, không phải diagnostic
  một lần.
- **Taxonomy báo cáo [SNIP]:** ToolScan 7 classes (Tool/Argument
  Hallucination, Invalid Invocation, Partial Execution, Output
  Hallucination, Invalid Intermediate Reasoning, Reentrant Failures)
  map sạch lên lỗi mình (ID bịa = Argument Hallucination, stop sớm =
  Partial Execution, pseudo-call = Invalid Invocation); cộng APB E2
  (Premature Conclusion) + MAST termination modes cho trục stop.
  Giữ cây chẩn đoán 5 nhánh hiện tại làm measurement layer, ToolScan
  làm reporting layer — tương thích, không cạnh tranh.

## 3. Xếp hạng hướng khác (sau E5, theo leverage × fit × cost)

Thứ tự này là **division of labor**, không phải một phương pháp duy
nhất: mỗi hướng sở hữu một nhóm lỗi mà các hướng khác không sở hữu.

| Rank | Hướng | Sở hữu lỗi | Bằng chứng mạnh nhất | Cost | Điều kiện |
|---|---|---|---|---|---|
| 1 | **Provenance guard + precondition gates + completion gate bằng code** (họ E4, nâng cấp theo resolver + DeReAct + state graph) | L1, L2, L5, L12 | Resolver reject toàn bộ hallucination, 0 over-rejection; verification +15.6% (MAST); condition edge loại bỏ cả class lỗi thay vì giảm tỉ lệ | Code only, 0 model call, deterministic | Không cần duyệt model; cần duyệt thiết kế guard (nằm trong E4 đã định) |
| 2 | **Constrained decoding** (XGrammar/ToolDec) | L8, L9 | Syntax errors → 0; 3B+grammar > 70B không grammar (snippet) | Library, overhead ~0 theo claim | **Phải verify Docker A30 chính thức cho phép** trước; nếu không cho thì dừng ở rank 1 + retry có đích |
| 3 | **Step-0 slot/intent gate bằng code** (missing-slot detection + ambiguity logprob; ask-as-action; ask-first policy khi uncertain) | L3, L4, L6, L7 | SAGE/CLAM mechanism; timing paper (ask ở step 0); When2Call cho thấy decision này train được | Code + logprobs, rẻ | Không đổi E5 rule; gate này là layer ngoài model, chạy trước branch |
| 4 | **N-best ASR + confidence-gated ask policy** | L10, L11 | ProGRes 5–25% relative WER; N-best selection an toàn hơn generation (không hallucination mới) | Engineering (beam N-best), vài chục token | Không dùng WCN text cho 4B nếu không fine-tune (bằng chứng âm) |
| 5 | **Dynamic enum grammar** (build từ observation ledger lúc chạy) | L2 (tầng generation) | Composition của 2 mảnh đã chứng minh; CHƯA có paper đánh giá đúng dạng | CPU test trước | Chỉ làm sau khi rank 1–2 đã đo; ghi rõ là thử nghiệm, không phải SOTA |
| 6 | **Training: When2Call-style SFT+RPO trên trace simulator-verified (tiếng Việt, cue patterns thật)** | L3, L4, L1 (durable version) | 4B F1 29.7 → 51.0, hallucination 16% → 1.9%; Sim-Tau 8B vượt GPT-4 trên τ-bench | Days, teacher offline only, GPU train | Chỉ sau khi E5 đo xong rule effect (đừng train thứ chưa đo); deadline 2026-11-16 là rủi ro timeline |
| 7 | **RL với shaped rewards (GRPO/DAPO)** trên simulator, bắt đầu từ model SFT | L1, L12, L3 (residual) | Tool-N1: RL > SFT +6.36% cùng data; small-model RLVR: sparse final-only reward là tệ nhất mọi seed → reward phải có format + step validity + outcome (prerequisite relations của mình là process reward tự nhiên) | Multi-day, 2×T4 chật cho full GRPO (cân nhắc LoRA-GRPO hoặc thuê GPU) | Chỉ nếu rank 1–6 vẫn chưa đủ; SFT warmup bắt buộc (đừng RL-from-base khi deadline gần) |
| 8 | **Thu nhỏ decision space** (tool shortlisting top-k; router 0.5B + executor 4B = 4.5B < 6B) | Residual planning failures khi mọi thứ trên đã làm | Chưa có số trực tiếp cho task này; là suy luận từ việc catalog ~75% prompt và planning là bottleneck còn lại | Retriever/classifier nhỏ | **Phải verify cách organizers đếm params hệ thống** (đọc hiện tại là assumption, chưa confirm) |

**KHÔNG làm (có bằng chứng chống):**

- Thêm prompt text nữa / rule dài hơn — trần §0.
- Intrinsic self-reflection generic — frozen 46%, không hiệu quả ở
  model nhỏ, tốn generation trong budget 30s.
- Sampling-based uncertainty ở inference (self-consistency, semantic
  entropy) — xung đột deterministic decoding, tốn 2–10× latency.
- End-to-end speech LLM thay cascade — cascade vẫn thắng ở low-resource
  (Kazakh–Russian: 21.3 vs 17.97 BLEU); không tồn tại <5B Vietnamese
  tool-use speech model trước cutoff; làm nó là research project,
  không phải fix.
- Chờ model lớn hơn — không được dùng (cap 5B), và scale không sửa
  bịa argument (8B ≈ 70B ≈ 675B).
- Convert pseudo-call thành submitted ask — hợp thức hoá intent sai
  (xem §2.1).
- ECLM corrector ngay bây giờ — chỉ khi slot-error sau N-best
  selection vẫn biện minh được pipeline training.

## 4. Trình tự đề xuất (mỗi bước đo được trên dev split hiện tại)

1. **Ngay sau E5 (không cần training):** rank 1 (guard E4 nâng cấp) +
   rank 3 (step-0 gate) + rank 4 (N-best + confidence policy) — toàn
   code, đo bằng ask-first + prerequisite axes đã có.
2. **Song song:** hỏi organizers 2 câu (XGrammar/vLLM trên Docker A30
   chính thức? cách đếm params hệ thống cho router?) — vì rank 2 và
   rank 8 phụ thuộc câu trả lời, đừng thiết kế trước khi có đáp án.
3. **Nếu rank 1–4 chưa đủ:** rank 6 (SFT simulator-verified) — dùng
   chính trace/gold của mình + teacher offline; đo trên dev, verify
   trên held-out sau freeze (held-out vẫn chỉ post-freeze).
4. **Nếu vẫn chưa đủ và còn thời gian trước 2026-11-16:** rank 7 (RL
   shaped rewards) từ model SFT; rank 8 (shortlisting/router) nếu
   bottleneck còn lại là planning/context chứ không phải intent.
5. **Không bao giờ:** đổi E5 arms/mẫu/rule giữa chừng để "thử" hướng
   mới — E5 đo xong rồi mới dùng kết quả của nó để quyết định rank 6.

## 5. Gap trung thực (không tìm thấy, không bịa)

- Không paper nào về Vietnamese voice-agent clarification hay asking
  dưới ASR noise — hướng ASR-aware asking (§2.5) là engineering
  synthesis, không phải literature finding.
- Không paper nào đặt tên "condition-into-label" — §2.4 là analog
  gần nhất, không phải match chính xác.
- Không paper nào đánh giá dynamic enum grammar cho tool agent.
- Một số số BFCL/τ-bench trích từ snippet chưa đọc full paper
  ([SNIP]) — trước khi dùng số nào để quyết định cuối, check lại
  primary PDF và phiên bản benchmark (multi-turn BFCL chưa chuẩn
  hoá: 16.2% vs 47.00% ở hai version khác nhau không so được).
- Qwen3.5-4B τ-bench 24.0 vs 27B 84.7 là họ Qwen3.5, không phải Qwen3 —
  dùng làm bằng chứng về gap theo scale, không phải số chính xác
  cho model của mình.
