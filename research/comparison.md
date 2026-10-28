# So sánh và shortlist — cả hai track

> Mức bằng chứng: **Official** = portal ZAIC 2026-10-26; **Code-read** = đã mở repo;
> **Author** = tác giả tự báo cáo; **Secondary** = nguồn thứ cấp; **Hypothesis** =
> giả thuyết chuyển giao, chưa đo trên ZAIC. Số benchmark chỉ dùng để chọn cơ chế.
>
> **Ánh xạ nhãn đợt 4 (2026-10-28):** nội dung cũ giữ nguyên nhãn cũ ở trên. Mọi
> kết luận MỚI từ đợt 4 dùng hệ nhãn mới theo yêu cầu nhiệm vụ: **[OFFICIAL]** =
> đối soát trực tiếp từ BTC/README/zaic_tools; **[CODE_INSPECTED]** = đã đọc
> file/commit/class/function cụ thể; **[LOCALLY_VERIFIED]** = đã chạy thử và kiểm
> chứng log; **[INFERENCE]** = suy luận kỹ thuật. Fact về cuộc thi lấy từ
> `competition/datamate.md` (tóm tắt portal sau đăng nhập 2026-10-26, không phải văn
> bản gốc BTC) được gắn **[CODE_INSPECTED]**, không gắn [OFFICIAL].

## Nguyên tắc chung

1. Metric thật là metric của ZAIC (state_hash+F1; PA), không phải metric của
   benchmark gốc (BFCL/BIRD/DABstep).
2. Đo theo nhóm lỗi trước khi thêm model. Một nâng cấp không sửa được nhóm lỗi nào
   cụ thể thì không thêm.
3. Tính tái lập là một phần của điểm: seed cố định, greedy decoding, log đầy đủ
   (LifeMate: log call — không tự ý lọc failed call/read call khỏi submission;
   DataMate: log từng câu hỏi + code + kết quả thực thi).
4. Mọi model đưa vào Docker phải qua checklist: ngày phát hành ≤ mốc (LifeMate
   26/10/2026; DataMate 01/10/2026), tổng tham số ≤ trần (6B / 15B, tính cả
   ASR/embedding/reranker), license cho phép, chạy offline, vừa thời gian
   (30 s/mẫu / 6 giờ toàn bộ private test).

## LifeMate — shortlist theo mức độ ưu tiên

| Ưu tiên | Ứng viên | Vì sao | Mức bằng chứng | Rủi ro chính |
|---|---|---|---|---|
| 1 — baseline ngay | PhoWhisper-small (244M) + Qwen3-4B-Instruct-2507 (4,0B, HF commit `cdbee75`, Apache 2.0) = 4,244B + validator schema + selective reads + loop guard | Chạy được sớm, trong trần 6B/5B/16K/30s; validator chặn lỗi tham số rẻ nhất | PhoWhisper repo BSD-3-Clause (kích thước/WER VIVOS); Qwen3 card chính thức (xem deep-profiles) | ASR lỗi thực thể; LLM chưa fine-tune gọi sai tool |
| 2 — nâng cấp đầu tiên | Entity correction RECOVER-style (N-best 5 + closed candidate + verify-and-apply; money/date/ID không fuzzy) | Sửa đúng nhóm lỗi đắt nhất (argument value ~47,7% lỗi cuối trong task-role paper, miền tiếng Anh — chỉ dùng làm tín hiệu đo lại) | PAPER (RECOVER, arXiv 2603.16411) + HYPOTHESIS chuyển giao | N-best từ beam có thể thiếu đa dạng — đo trước |
| 3 — nâng cấp thứ hai | Hammer transplant: function masking (bắt đầu thấp) + irrelevance 7,5k trộn theo tỉ lệ đo được | Sửa ask/refuse và chống overfit tên tool; paper cảnh báo trade-off execute vs irrelevance | PAPER (Hammer v1, ICLR 2025) + repo README_READ (Apache-2.0, commit `ff415d`) | Sinh dữ liệu không sát catalog thật; tỉ lệ trộn sai phá điểm execute |
| 4 — đáng thử, ít người làm | Forge-style guardrails: rescue parsing, StepEnforcer (prerequisites), TieredCompact, retry chỉ cho lỗi parse | Chặn lỗi trước khi gọi, không tốn thêm LLM call | README_READ (Forge, MIT, commit `3e5a38`) — KHÔNG phải CODE_INSPECTED | Chưa đọc thân file — mở bằng git clone trước khi copy pattern |
| 5 — harness, không phải model | Milestone/minefield + taxonomy lỗi τ-bench + đo recovery rate | Phát hiện "đúng hash nhưng đi đường nguy hiểm"; τ-bench số phải ghi pass¹ + policy + domain + backbone | τ-bench repo MIT; file agent cụ thể chỉ DEEPWIKI_SUMMARY trong round 2 | Tốn công xây, chỉ có giá trị nếu dùng để sửa model |
| Để sau (A/B, không vào shortlist chính) | **A/B #1: xLAM-2-3b-fc-r vs baseline**; **A/B #2 (sau khi đọc licence): Hammer2.1-3b vs baseline**; Hammer-4B (chỉ tham chiếu) | xLAM: specialist FC, số paper BFCL v3 65.11 (APIGen-MT, không phải leaderboard) + τ-bench multi-turn; Hammer2.1: specialist FC, cùng parser `hermes` với baseline nên port rẻ nhất | [CODE_INSPECTED] card xLAM/Hammer (phiên trước); [INFERENCE] cho mọi suy ra từ số paper | xLAM: licence UNVERIFIED trên card gốc + dòng "research purposes only" + tín hiệu thứ cấp CC BY-NC 4.0 = **blocker trước khi nộp, cần BTC xác nhận có tính là open-source không**; bảng BFCL-v3 trên card chỉ là ảnh, không có số text. Hammer2.1: licence metadata không render trên card = UNVERIFIED; NO BFCL đọc được; số BFCL v2 76.05 của Hammer-4B là của model khác, **không được chuyển sang 3B**. |
| Loại (đợt 4, FAIL cứng — không phải vi phạm luật mà là không đạt mốc kỹ thuật) | Gemma-2-2b-it; PhoGPT-4B-Chat; Vistral-7B-Chat | Gemma/PhoGPT: context 8.192 < 9.874 (mốc prompt thực đo train_1636, agent a2e832b) + không có native tool calling; Vistral: 7B vượt cap LLM <5B | [CODE_INSPECTED] card phiên trước (Gemma, Hammer, xLAM); [SECONDARY] cho PhoGPT/Vistral/Sailor2 | **Không có model tiếng Việt nào <5B có native tool calling** trong tập đã kiểm tra — lợi thế tiếng Việt phải lấy từ model đa ngữ (họ Qwen có tiếng Việt trong 29 ngôn ngữ), không đánh đổi tool format lấy tiếng Việt. Sailor2-1B chỉ làm control ngôn ngữ (không có bằng chứng tool calling). |
| Để sau | ASR large làm mặc định, agent đa LLM | Vượt trần/latency hoặc sát trần | Tính toán từ luật (Official) | Gần 6B, tốn thời gian trên A30 |
| Loại | xLAM-7B, model > 5B, API ngoài, checkpoint sau 26/10/2026, đọc `state.json` | Vi phạm luật | Official | Bị loại |

## DataMate — shortlist theo mức độ ưu tiên

| Ưu tiên | Ứng viên | Vì sao | Mức bằng chứng | Rủi ro chính |
|---|---|---|---|---|
| 1 — baseline ngay | Qwen2.5-Coder-7B-Instruct (7,61B) + PhoBERT-base (0,135B, MIT) = 7,745B + tầng đọc bảng thống nhất + trích rulebook + 1 chương trình thực thi + chuẩn hóa output + ngưỡng abstain 0,5 (lý thuyết) | Chạy được sớm; chuẩn hóa output và abstain là 2 lever rẻ nhất dưới PA | Qwen2.5-Coder blog/bảng chính thức; PhoBERT README chính thức; luật PA Official | Rulebook trích sai; ngưỡng chưa hiệu chuẩn; PhoBERT bắt buộc input đã tách từ |
| 2 — nâng cấp đầu tiên | Hiệu chuẩn abstain theo loại câu trên train_cal tách theo business + kiểm tra chéo 2 cách tính độc lập thật sự (SQL vs pandas, logic khác nhau) | Trực tiếp tối đa hóa PA, không cần model mới | Hypothesis; BAS/RAS secondary cho hướng; đợt 4: [CODE_INSPECTED] code 5 solution, [INFERENCE] cho gate/calibrator | Ngưỡng overfit nếu học trên public test — cấm; chỉ học trên train_cal. **Đợt 4 thay score trọng số cố định bằng calibrator học trên train_cal** (features: consensus fraction + execution rate + cross-path agreement + evidence coverage + fluency tuỳ chọn); **gate abstain 5 điều kiện gắn tại submission writer** (sau vote/gom cụm, trước khi ghi): không candidate nào chạy được; top share < τ; hoà top; cluster thắng là rỗng/0/NULL không có bằng chứng độc lập; output là sentinel/lỗi/placeholder. Xem `research/datamate/abstain-calibration-protocol.md`. |
| 3 — nâng cấp thứ hai | 3 candidate + selector bằng thực thi + revision an toàn tối đa 2 vòng, đóng băng kết quả đúng đầu tiên (BASE-SQL gọn, ReFoRCE guard) | Sửa lỗi tính toán — nhóm lỗi lớn nhất sau rulebook | PAPER_READ (BASE-SQL ablation); CODE_INSPECTED mức file (ReFoRCE) | Vượt 6 giờ nếu không giới hạn candidate/lượt; revision làm hỏng câu đúng nếu không có điều kiện chạy |
| 4 — đáng thử, ít người làm | Exploration xác định + schema shortlist có fallback (ReFoRCE/ProSPy + schemagate) + retrieval ví dụ kiểu ViR² | Tấn công đúng điểm yếu "README không đều" và "doanh nghiệp mới" | CODE_INSPECTED mức file (ReFoRCE); README_READ (schemagate); Author (ViR²) | Exploration tốn thời gian; shortlist quá chặt loại mất bảng cần thiết nếu không có fallback |
| 5 — khi có thời gian/GPU | Fine-tune nhỏ trên train ZAIC (schema linking + sinh code); penalty-based abstention | Học phân bố câu hỏi/doanh nghiệp Việt | Author (SPFT/DB-Explore, record ACL chính thức cho DB-Explore) cho phương pháp; hiệu quả trên ZAIC là Hypothesis | Overfit loại hình train; private có loại hình mới; checkpoint phái sinh chưa rõ cách tính cutoff (UNVERIFIED, Q-D5) |
| Để sau | MCTS 24 rollout nguyên bản (Alpha-SQL); pipeline 4 agent ~20 call/câu | Đắt, rủi ro thời gian | Author/Secondary | Vỡ ngân sách 6 giờ |
| Loại | Model API thương mại; model > 15B; MoE tính tổng > 15B; checkpoint sau 01/10/2026; chuẩn hóa bỏ dấu; lịch Trung Quốc thay lịch Việt Nam; dùng public/private test để train | Vi phạm luật hoặc làm sai khớp evaluator | Official | Bị loại hoặc mất điểm hệ thống |

## So sánh hai track — điểm khác biệt quyết định thiết kế

| Khía cạnh | LifeMate | DataMate |
|---|---|---|
| Điểm chết | Một write thừa phá `state_hash` → 0 | Một câu sai −1 xóa một câu đúng +1 |
| Lỗi đắt nhất | Side-effect không mong muốn | Trả lời bừa thay vì abstain |
| Nâng cấp rẻ nhất | Validator + selective reads (code, 0 tham số LLM) | Formatter tách riêng + hiệu chuẩn abstain (code + calibration) |
| Nâng cấp đắt nhất | Fine-tune trên trajectory đã verify | Multi-candidate + fine-tune synthetic có kiểm chứng |
| Generalization | App/tool mới trong private (chưa xác minh mức độ) | Loại hình doanh nghiệp mới — đã xác nhận trên portal |
| Đo ổn định | Chạy lại 2 lần, đếm mẫu đổi kết quả (deterministic decoding) | Leave-one-business-type-out + đo thời gian trên public test (không đo PA tại chỗ), ngoại suy ra 6 giờ |

## Shortlist model có bằng chứng (tóm tắt — chi tiết trong deep-profiles và plans)

**LifeMate (trần hệ thống < 6B, LLM < 5B, context ≤ 16K, model trước 26/10/2026):**
main = Qwen3-4B-Instruct-2507 (4,0B) + PhoWhisper-small 0,244B = **4,244B**;
+ medium 0,769B = **4,769B**; + large 1,55B = **5,55B** (sát trần). Đối chứng:
Qwen3-4B thinking (family 28/04/2025) — chỉ khi lỗi planning chiếm đa số.
Ngoài shortlist chính: xLAM-2-3b-fc-r, Hammer-4B, Hammer2.1-3b (licence/ngày
chưa xác minh trên card gốc); Llama-3.2-3B (25/09/2024, Community licence,
3,21B, tiếng Việt không nằm trong 8 ngôn ngữ hỗ trợ chính thức — đối chứng
format, không phải vì '3B nhẹ'). Quantization không làm giảm tổng tham số.

**DataMate (trần tổng inference ≤ 15B, model trước 01/10/2026):** main =
Qwen2.5-Coder-7B-Instruct 7,61B + PhoBERT-base 0,135B = **7,745B**; đối chứng
Qwen3-8B 8,19B (secondary) + 0,135 = **8,325B**. 14B chỉ với lệnh cấm model
phụ: Qwen2.5-Coder-14B 14,7B + 0,135 = **14,835B** (dư 0,165B); Qwen3-14B
~14,8B (secondary) + 0,135 = **14,935B** (dư 0,065B — thực tế không dùng được
kèm model phụ). Một checkpoint dùng nhiều vai trò tính tham số một lần,
nhưng checker cùng checkpoint chia sẻ blind spot với coder — thí nghiệm phân
biệt trong plans/datamate.md. Cách tính total vs non-embedding và ngày của
checkpoint phái sinh là **UNVERIFIED** (Q-D5/Q-L6) — giả định an toàn là
total, bao gồm embedding và mọi model phụ.

## Cập nhật đợt 4 (2026-10-28)

- **LifeMate — E7 guard vẫn CPU_NOT_READY, không vào GPU.** Phase 0 shadow audit:
  chỉ 31/459 gold write được giám sát được ALLOW chắc chắn (6,75%), 428 UNKNOWN,
  0 BLOCK; một known fill (0780) chưa phân giải được (supersession ở cấp field).
  Kết luận: không tích hợp guard này, không chạy E7 GPU; đây KHÔNG phải verdict
  E7 REFUTED (giả thuyết block→ask chưa từng được chạy). Hai hướng thiết kế tiếp
  theo: (1) thu hẹp can thiệp thành một họ source/slot nhỏ, nhận diện được rõ ràng,
  có chính sách abstention tường minh; (2) nếu cần phủ rộng thì phải xây representation
  task/slot/reference có cấu trúc (kèm supersession + arithmetic hợp lệ) trước —
  một component ngữ nghĩa có đánh giá lỗi/chi phí riêng, không phải hệ quả miễn phí
  của JSON schema validation. [CODE_INSPECTED: `analysis/runtime/E7_PHASE0_SHADOW_AUDIT_2026-10-28.md`]
- **LifeMate — grounding đợt 4 (thay cho guard phổ quát):** TOP 1 = tầng grounding
  đa tín hiệu xác định, 0 param mới (text + segmental FED epitran/Panphon + tone-digit
  riêng + acoustic rescore tie-breaker + chuẩn hoá typed); TOP 2 = contextual 2-pass
  faster-whisper `initial_prompt`/`hotwords` có điều kiện (chỉ mẫu nghi ngờ, phải đo
  overcorrection). Không chọn: mã Soundex/Metaphone tiếng Anh (va chạm Hương/Hang);
  viphoneme mặc định (license non-commercial + import lỗi thiếu vinorm); stack
  pyctcdecode + wav2vec2-vi làm chính (CTC-only, 2× ASR); embedding làm kênh chính
  (kém đúng ở lỗi thanh điệu); TCPGen (cần retrain); speech-to-intent drop-in
  (không tồn tại cho ZAIC; "VSLUE" không có thật). Xem
  `research/lifemate/asr-repair-decision-framework.md`. Nền tảng số: validate() miễn
  phí, mọi call() đều tốn trace; write chuẩn F1 = 1.0, +1 read thừa = 0.6667,
  +2 read thừa = 0.5, ask thay write = 0.0 (đo bằng đúng hàm `tool_f1` của nhánh
  experiment) — pipeline tinh gọn là weakly dominant ở cả hai nhánh của Q-L3.
- **LifeMate — serving mặc định (chưa có số A30 thật):** vLLM BF16, không quant,
  không guided decoding ở vòng đầu (`--max-model-len 16384`,
  `--gpu-memory-utilization 0.90`, `--max-num-seqs 1`, `--enable-prefix-caching`,
  `--tool-call-parser hermes`, greedy temperature=0, seed 42). Số học bộ nhớ: weights
  8GB + KV ~144KB/token → 16K tokens ≈ 2,36GB — bộ nhớ không phải nút thắt, latency
  mới là thứ phải đo. llama.cpp Q8_0 là dự phòng (cần port parser `<tool_call>` thủ
  công; dưới Q4_K_M cấm dùng cho agent tool). XGrammar chỉ là thí nghiệm vòng sau,
  sau khi BTC xác nhận và sau khi dev chứng minh lỗi format (không phải lỗi giá trị)
  mới là lỗi chủ đạo. Baseline giữ nguyên Qwen3-4B-Instruct-2507 (rev `cdbee75`,
  Apache 2.0, 4,244B tổng, context native 262K, non-thinking, BFCL-v3 61.9
  card-claimed — bảng leaderboard BFCL chính thức là trang JS-render, không đọc được
  bảng số trực tiếp trong phiên này nên mọi số BFCL đều là card/paper hoặc NO BFCL).
- **DataMate — không solution nào có abstain thật.** DABstep: prompt-only
  "Not Applicable", không post-check, hết max-steps thì ép đoán (smolagents
  `provide_final_answer`); ReFoRCE: hoà → không copy file, nhưng `run_main.sh`
  Step 3/4 lấp đầy mọi task (copy `first_key` / file đầu tiên) và `get_metadata.py`
  tạo metadata trỏ tới file không tồn tại; CHESS: placeholder
  `"SELECT * FROM table_name"` điểm 0, điểm 1 giả tạo ở nhánh 1 candidate / 0 test,
  `ZERO_COUNT_RESULT`/`ALL_NONE_RESULT` đã bị comment out (COUNT=0 và toàn NULL
  được coi là đúng), `pick_final_sql` chết, `max_fixing` không tồn tại ở commit này
  (đừng trích); CSC-SQL: tất cả draft lỗi → nộp draft lỗi ngẫu nhiên (mặc định
  `return_random_one_when_all_errors=True`), kết quả rỗng là cluster hợp lệ
  (frozenset), vote_list được lưu nhưng không dùng để quyết định; XiYan-SQL: repo
  hub chỉ có README (không có code pipeline), paper không có nhánh unanswerable,
  refine 1 lần rồi append mù, cụm rỗng tạo "đa số giả". **Không solution nào dùng
  DuckDB, không solution nào cross-check SQL-vs-Python** — cross-check của repo là
  thiết kế gốc, phải đo tỉ lệ "đồng thuận mà vẫn sai" trên dev có nhãn trước khi
  coi nó là tín hiệu mạnh. Xem `research/datamate/abstain-calibration-protocol.md`.
- **DataMate — kiểm kê dữ liệu thật đã xong (2026-10-28, [LOCALLY_VERIFIED]):**
  train 3000 câu / 30 business, public_test 1000 câu / 14 business và **không có
  `answers.jsonl`** (giao thức "không dùng public_test để tune" đứng vững);
  định dạng file train: 99 xlsx, 20 csv, 1 sqlite (biz_123); schema `calendar.csv`:
  `date,weekday,lunar_day,lunar_month,lunar_year,lunar_leap,holiday`, phủ
  2024-01-01–2027-12-31; gold percent thang 0–100; gold number là số thuần; date
  ISO cả `yyyy-mm-dd` và `yyyy-mm`; phân bố loại đáp án: number 1884, percent 578,
  string 88, list 193, unanswerable 70, date 145, table 19, boolean 23; **không có
  field type tường minh** (LOBO chạy nhánh pseudo-type). Hệ quả ngân sách: nếu
  private cùng quy mô public_test (~1000 câu) thì trần 6 giờ cho trung bình
  **21,6 giây/câu** — thấp hơn ~40,81 giây/sample của XiYan trên BIRD dev.
  Xem `research/datamate/abstain-calibration-protocol.md` §6.11.
- **DataMate — validation:** LOBO Variant B làm chính (m < 4), Variant A làm chẩn
  đoán chuyển ngưỡng (m ≥ 4); ngưỡng vận hành = 0,5 + δ (δ = bias LOBO đo được) +
  LCB khi mẫu ít; báo per-type + PA min + độ phân tán ngưỡng, không gộp mù.
  Formatter: code xác định, tách khỏi LLM; percent không hardcode 0–100/0–1 (đo trên
  gold train); âm lịch qua lookup generic (schema calendar.csv UNVERIFIED) + abstain
  khi không có calendar; Excel: chọn sheet bằng scoring, merge fill-down chỉ cho
  cột nhãn, header detect bằng rule có fallback ladder, giữ thứ tự dòng gốc.
- **Lộ trình:** `plans/round4-test-roadmap.md` — thứ tự CPU-only trước
  (D-0 → E-asr-1 → E-asr-2 → E-asr-3 → E-lean → D-1 → D-4), rồi chạy model theo route
  Kaggle (cần phê duyệt riêng từng lần), rồi A30 + câu trả lời BTC, cuối cùng ngân
  sách 6 giờ. Không fine-tune, không E7 GPU, không mở rộng E5, không tune trên
  public_test hay held-out trong đợt 4.
