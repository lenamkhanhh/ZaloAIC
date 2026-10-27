# So sánh và shortlist — cả hai track

> Mức bằng chứng: **Official** = portal ZAIC 2026-10-26; **Code-read** = đã mở repo;
> **Author** = tác giả tự báo cáo; **Secondary** = nguồn thứ cấp; **Hypothesis** =
> giả thuyết chuyển giao, chưa đo trên ZAIC. Số benchmark chỉ dùng để chọn cơ chế.

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
| Để sau (A/B, không vào shortlist chính) | xLAM-2-3b-fc-r; Hammer-4B; Hammer2.1-3b | Dưới trần tham số, chuyên function calling | Series Salesforce + APIGen-MT (xLAM); Hammer v1 PAPER + README_READ | xLAM: licence chưa đọc trên card gốc, ngày checkpoint 3B chưa xác minh, rủi ro CC BY-NC. Hammer2.1: licence/ngày/base chưa xác minh trên card gốc, mirror báo CC-BY-NC-4.0 cho bản 0.5b. |
| Để sau | ASR large làm mặc định, agent đa LLM | Vượt trần/latency hoặc sát trần | Tính toán từ luật (Official) | Gần 6B, tốn thời gian trên A30 |
| Loại | xLAM-7B, model > 5B, API ngoài, checkpoint sau 26/10/2026, đọc `state.json` | Vi phạm luật | Official | Bị loại |

## DataMate — shortlist theo mức độ ưu tiên

| Ưu tiên | Ứng viên | Vì sao | Mức bằng chứng | Rủi ro chính |
|---|---|---|---|---|
| 1 — baseline ngay | Qwen2.5-Coder-7B-Instruct (7,61B) + PhoBERT-base (0,135B, MIT) = 7,745B + tầng đọc bảng thống nhất + trích rulebook + 1 chương trình thực thi + chuẩn hóa output + ngưỡng abstain 0,5 (lý thuyết) | Chạy được sớm; chuẩn hóa output và abstain là 2 lever rẻ nhất dưới PA | Qwen2.5-Coder blog/bảng chính thức; PhoBERT README chính thức; luật PA Official | Rulebook trích sai; ngưỡng chưa hiệu chuẩn; PhoBERT bắt buộc input đã tách từ |
| 2 — nâng cấp đầu tiên | Hiệu chuẩn abstain theo loại câu trên train_cal tách theo business + kiểm tra chéo 2 cách tính độc lập thật sự (SQL vs pandas, logic khác nhau) | Trực tiếp tối đa hóa PA, không cần model mới | Hypothesis; BAS/RAS secondary cho hướng | Ngưỡng overfit nếu học trên public test — cấm; chỉ học trên train_cal |
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
