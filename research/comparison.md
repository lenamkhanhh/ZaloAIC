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
   (LifeMate: log call; DataMate: log từng câu hỏi + code + kết quả thực thi).
4. Mọi model đưa vào Docker phải qua checklist: ngày phát hành ≤ mốc (LifeMate
   26/10/2026; DataMate 01/10/2026), tổng tham số ≤ trần (6B / 15B, tính cả
   ASR/embedding/reranker), license cho phép, chạy offline, vừa thời gian
   (30 s/mẫu / 6 giờ toàn bộ private test).

## LifeMate — shortlist theo mức độ ưu tiên

| Ưu tiên | Ứng viên | Vì sao | Mức bằng chứng | Rủi ro chính |
|---|---|---|---|---|
| 1 — baseline ngay | PhoWhisper-small/medium + LLM ≤ 4B instruct + validator schema | Chạy được sớm, trong trần 6B/5B/16K/30s; validator chặn lỗi tham số rẻ nhất | Code-read (PhoWhisper repo, BSD-3-Clause) cho kích thước/WER; checkpoint HF chưa xác minh | ASR lỗi thực thể; LLM chưa fine-tune gọi sai tool |
| 2 — nâng cấp đầu tiên | Irrelevance augmentation + hỏi lại/ngoài phạm vi riêng biệt (Hammer) | Sửa trực tiếp nhóm mẫu gold rỗng/thiếu — nhóm dễ mất điểm oan | Secondary (Hammer, ICLR 2025); checkpoint/license chưa xác minh | Sinh dữ liệu irrelevance không sát catalog thật |
| 3 — nâng cấp thứ hai | Fine-tune trên trajectory train đã verify bằng state_hash + function masking | Học đúng phân bố tool ZAIC, chống overfit tên tool | Hypothesis (từ APIGen/ToolACE, secondary) | Overfit train, kém generalization sang private (app mới) |
| 4 — đáng thử, ít người làm | Validator ràng buộc kiểu SCA (schema/`x-ref`/`x-one-of`/`installed_apps`) | Chặn lỗi trước khi gọi, không tốn thêm LLM call | Secondary (SCA paper) | Hiểu sai luật log call nếu lọc sau thực thi — đối chiếu thể lệ |
| 5 — harness, không phải model | Milestone/minefield + taxonomy lỗi τ-bench | Phát hiện "đúng hash nhưng đi đường nguy hiểm" | Code-read (τ-bench, MIT) | Tốn công xây, chỉ có giá trị nếu dùng để sửa model |
| Để sau | xLAM-2-3B | Chưa đủ bằng chứng | Secondary yếu (blog, không phải nguồn Salesforce chính thức) | Checkpoint/license/ngày chưa xác minh |
| Để sau | ASR large làm mặc định, agent đa LLM | Vượt trần/latency hoặc sát trần | Tính toán từ luật (Official) | Gần 6B, tốn thời gian trên A30 |
| Loại | xLAM-7B, model > 5B, API ngoài, checkpoint sau 26/10/2026, đọc `state.json` | Vi phạm luật | Official | Bị loại |

## DataMate — shortlist theo mức độ ưu tiên

| Ưu tiên | Ứng viên | Vì sao | Mức bằng chứng | Rủi ro chính |
|---|---|---|---|---|
| 1 — baseline ngay | LLM ≤ 14B + tầng đọc bảng thống nhất + trích rulebook + 1 chương trình thực thi + chuẩn hóa output + ngưỡng abstain 0,5 | Chạy được sớm; chuẩn hóa output và abstain là 2 lever rẻ nhất dưới PA | Hypothesis (tổng hợp BIRD/DABstep/SpreadsheetBench); luật PA Official | Rulebook trích sai; ngưỡng chưa hiệu chuẩn |
| 2 — nâng cấp đầu tiên | Hiệu chuẩn abstain theo loại câu + kiểm tra chéo 2 cách tính (SQL vs pandas) | Trực tiếp tối đa hóa PA, không cần model mới | Hypothesis; BAS/RAS secondary cho hướng | Ngưỡng overfit public test |
| 3 — nâng cấp thứ hai | 3 candidate + selector bằng thực thi (CHESS/BASE-SQL gọn) | Sửa lỗi tính toán — nhóm lỗi lớn nhất sau rulebook | Author (BASE-SQL, MCS-SQL); CHESS secondary | Vượt 6 giờ nếu không giới hạn candidate/lượt |
| 4 — đáng thử, ít người làm | Exploration/profiling tự động khi README nghèo (ReFoRCE/ProSPy) + retrieval ví dụ kiểu ViR² | Tấn công đúng điểm yếu "README không đều" và "doanh nghiệp mới" | Secondary (ReFoRCE/ProSPy); Author (ViR²) | Exploration tốn thời gian; ví dụ retrieval nhiễu |
| 5 — khi có thời gian/GPU | Fine-tune nhỏ trên train ZAIC (schema linking + sinh code); penalty-based abstention | Học phân bố câu hỏi/doanh nghiệp Việt | Author (SPFT/DB-Explore) cho phương pháp; hiệu quả trên ZAIC là Hypothesis | Overfit loại hình train; private có loại hình mới; checkpoint phái sinh chưa rõ cách tính cutoff |
| Để sau | MCTS 24 rollout nguyên bản (Alpha-SQL); pipeline 4 agent ~20 call/câu | Đắt, rủi ro thời gian | Author/Secondary | Vỡ ngân sách 6 giờ |
| Loại | Model API thương mại; model > 15B; MoE tính tổng > 15B; checkpoint sau 01/10/2026; chuẩn hóa bỏ dấu; lịch Trung Quốc thay lịch Việt Nam; dùng public/private test để train | Vi phạm luật hoặc làm sai khớp evaluator | Official | Bị loại hoặc mất điểm hệ thống |

## So sánh hai track — điểm khác biệt quyết định thiết kế

| Khía cạnh | LifeMate | DataMate |
|---|---|---|
| Điểm chết | Một write thừa phá `state_hash` → 0 | Một câu sai −1 xóa một câu đúng +1 |
| Lỗi đắt nhất | Side-effect không mong muốn | Trả lời bừa thay vì abstain |
| Nâng cấp rẻ nhất | Validator + read-before-write (code, 0 tham số LLM) | Formatter tách riêng + hiệu chuẩn abstain (code + calibration) |
| Nâng cấp đắt nhất | Fine-tune trên trajectory đã verify | Multi-candidate + fine-tune synthetic có kiểm chứng |
| Generalization | App/tool mới trong private (chưa xác minh mức độ) | Loại hình doanh nghiệp mới — đã xác nhận trên portal |
| Đo ổn định | Chạy lại 2 lần, đếm mẫu đổi kết quả (deterministic decoding) | Leave-one-business-type-out + đo thời gian toàn bộ public test, ngoại suy ra 6 giờ |
