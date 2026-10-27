# analysis/ — Tài liệu chẩn đoán LifeMate (chỉ đọc, không phải code)

Mục riêng cho việc đối chiếu giữa bên phân tích và bên code (Codex).
Không chứa raw dataset, audio hay weights.

## Nội dung

- `dev_probe_ids.json` — Danh sách 26 probe, tất cả thuộc 1.237 mẫu
  dev (split `lifemate/splits/train_dev_heldout.json`), kèm lý do
  chọn, kỹ năng cần kiểm tra và lỗi cần phân biệt. Nhóm smoke 5:
  train_0025, train_0016, train_0049, train_0004, train_0019.
  Chạy đúng nhóm này bằng `lifemate/run.py` với `--ids` hoặc
  `--ids-file analysis/dev_probe_ids.json` (xem `RUN_LIFEMATE.md`).
- `WAIT_ANALYSIS_2026-10-27.md` — Kiểm chứng probe bằng label thật,
  gold trace smoke-5, và 2 mẫu cần đọc kỹ (train_1696, train_0082).
- `OPTIMAL_PIPELINE_2026-10-27.md` — Tổng hợp pipeline tối ưu từ
  đề xuất ZAIC2 + số liệu đo trên data (ngân sách, latency,
  context, thí nghiệm phân biệt theo thứ tự rẻ → đắt).

## Quy ước bắt buộc khi dùng các file này

- **Định nghĩa read:** tool có `kind: "read"` trong catalog
  (read = không đổi state; write = đổi state/tạo hành động;
  meta = `sys.ask_missing_info`). Trên gold dev: read 1.280 /
  2.843 (45,0%), write 1.389, meta 174. Không dùng heuristic đoán
  theo tên tool (con số 1.138 cũ theo tên là sai, đã sửa).
- **train_1696 là gold anomaly:** gold chứa luôn call
  `chat_ott.send_message` tới `chat_6142` không tồn tại
  (`ok: true, done: false`). KHÔNG hardcode id sai này vào agent
  hay prompt, không dạy model phát ra id không tồn tại. Khi đo,
  báo cáo mẫu này riêng (ghi chú anomaly).
- **Không hard-code đáp án probe:** file probe cố tình KHÔNG chứa
  gold tool calls. Chấm điểm từ label train bằng
  `lifemate/run.py score`. File trace gold chi tiết KHÔNG nằm
  trong repo (giữ ở máy phân tích) đúng theo thiết kế này.
- **Hỏi chưa có đáp án (Q-L1/Q-L3/Q-L5):** cách chấm ask, read có
  tính F1 không, và hết vòng lặp nộp gì — vẫn mở, xem `gaps.md`.
