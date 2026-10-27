# Khoảng trống — những gì chưa xác minh hoặc chưa truy cập được

> Đọc file này trước khi chốt bất kỳ quyết định nộp bài nào. Không lấp các mục
> dưới đây bằng suy đoán.

## 1. File HTML đính kèm của người dùng — không tìm thấy trong phiên này

- Người dùng nói đã gửi kèm file "Zalo AI Challenge 2026.html" làm context ban đầu.
  Trong workspace của phiên làm việc này, file đó **không xuất hiện** (đã tìm trong
  `~/workspace`, kể cả thư mục media và các artifact trước đó).
- Tài liệu này vì vậy dùng **bản artifact Zalo AI Challenge 2026 đã làm trước đó,
  toàn bộ chi tiết người dùng ghi trong yêu cầu, và portal chính thức kiểm tra
  2026-10-26** làm context thay thế.
- **Hành động:** nếu file thật sự chưa đính kèm, người dùng gửi lại file để đối
  chiếu; nếu file đã đính kèm ở một kênh khác, cần chuyển file vào `~/workspace/`
  rồi đối chiếu và cập nhật các điểm khác với nguồn chính thức (ưu tiên nguồn
  chính thức mới nhất khi có mâu thuẫn).

## 2. Portal và dữ liệu sau đăng nhập — chưa tải/giải nén trong phiên nghiên cứu

- Các gói zip DataMate (train, public_test) và LifeMate (train+public_test) chỉ
  được ghi nhận từ mục Data sau đăng nhập ngày 2026-10-26; **kích thước zip, số
  doanh nghiệp/câu hỏi chính xác, nội dung đầy đủ của README/rulebook/calendar.csv
  chưa được xác minh** bằng cách tải và giải nén trong phiên này.
- Catalog tool LifeMate chính xác (tên, tham số, enum, format tiền/ngày/ID),
  Docker base image, inference script chính thức — chưa xác minh.
- Một subagent DataMate trong phiên này đã thử tải lại text portal và thất bại;
  theo chỉ đạo runtime, yêu cầu đó không được lặp lại trong phiên đó — vì vậy các
  luật DataMate trong tài liệu này được ghi theo đề bài được giao và bối cảnh
  portal 2026-10-26, không phải "đã tự xác minh lại portal" trong phiên đó.

## 3. Evaluator — cách xử lý từng trường hợp chưa xác minh

### LifeMate
- Cách chấm chính xác của `sys.ask_missing_info` (đúng/sai/thừa/thiếu tính thế nào).
- Failed call có được giữ trong trace nộp hay phải loại bỏ.
- Mọi ToolEnv call có bắt buộc xuất hiện trong submission không.
- Validator lọc sau thực thi có vi phạm luật log call không.
- Cách tính tham số: total hay active (với MoE, giả định an toàn là total cho tới
  khi xác minh được).

### DataMate
- Missing answer (câu hỏi thiếu trong submission): ghi nhận từ portal sau đăng
  nhập 2026-10-26 là tính như abstain — **chưa tự xác minh evaluator**.
- Agent trả `unanswerable` khi reference là giá trị, và ngược lại.
- Sai type (ví dụ trả number thay vì percent, table sai cột).
- Hòa ranking tại biên k hoặc tại hạng 1: ghi nhận các trường hợp hòa được loại
  khỏi test set — chưa xác minh chi tiết trong evaluator/rulebook của split.
- Sai thứ tự list, sai làm tròn số, sai format date.
- Định dạng percent (0–100 hay 0–1).
- "Rows as set" cho table: thứ tự hàng có quan trọng không.
- **Hành động:** đọc evaluator (nếu có trong gói dữ liệu), README và rulebook của
  từng split; nếu evaluator không có trong gói, hỏi aichallenge@zalo.me và ghi lại
  câu trả lời. Không chốt pipeline dựa trên suy đoán ở các điểm này.

## 4. Fine-tune checkpoint và mốc thời gian — chưa rõ cách ban tổ chức hiểu

- Checkpoint phái sinh từ fine-tune (trên train ZAIC hoặc trên dữ liệu tổng hợp)
  có được tính là "model công bố trước 01/10/2026" (DataMate) / "trước 26/10/2026"
  (LifeMate) hay không — **chưa xác minh**.
- **Hành động:** hỏi ban tổ chức trước khi đầu tư nhiều vào fine-tune, hoặc chuẩn
  bị phương án dự phòng bằng model gốc chưa fine-tune.
- Teacher dùng để sinh dữ liệu tổng hợp phải ghi rõ (tên, ngày phát hành) để tránh
  tranh cãi về nguồn gốc dữ liệu, kể cả khi teacher chỉ dùng lúc tạo dữ liệu
  offline, không phải lúc inference.

## 5. Checkpoint, licence và ngày phát hành — chưa xác minh trên Hugging Face

- PhoWhisper từng size (tiny/base/small/medium/large).
- Qwen3-4B-Instruct-2507 (nguồn thứ cấp: 06/08/2025, Apache 2.0 — chưa xác minh).
- Qwen3-8B, Qwen2.5-Coder-7B/14B (nguồn thứ cấp về cỡ/license/ngày — chưa xác minh
  config của checkpoint cụ thể; đặc biệt Qwen2.5-Coder-14B được bảng thứ cấp ghi
  14,7B, cộng PhoBERT-base 0,135B là 14,835B — sát trần 15B).
- xLAM-2-3b-fc-r (chỉ có blog thứ cấp, chưa xác minh HF repo/license/ngày).
- Hammer checkpoints `MadeAgents/Hammer-*` (license chưa xác minh).
- RSL-SQL repo (chưa mở/xác minh license).
- ToolSandbox (license hiển thị NOASSERTION — đọc file LICENSE thực tế trước khi
  copy code).
- **Hành động:** đọc model card + `config.json` của checkpoint sẽ dùng, cộng tổng
  tham số thực (bao gồm embedding nếu không tie, cộng mọi model phụ), ghi lại
  commit/ngày/license trước khi đưa vào Docker.

## 6. Giải thưởng theo từng track — suy luận, chưa xác nhận

- Việc nhất 3.500 USD / nhì 2.500 USD là **theo từng track** chỉ là suy luận từ
  (3.500 + 2.500) × 2 = 12.000 USD tổng giải — chưa xác nhận trực tiếp trong thể lệ.
- **Hành động:** đối chiếu PDF thể lệ EN/VI trước khi dùng con số này làm căn cứ.

## 7. ZAIC 2025 — không tìm thấy repo/write-up chiến thắng

- Đội thắng CtelAI (RoadBuddy) và AIO_C3A (AeroEyes) năm 2025: không tìm thấy
  repo/write-up chính thức trong các tìm kiếm đã làm. Bài toán 2025 cũng không
  liên quan trực tiếp đến LifeMate/DataMate 2026 — chỉ ghi nhận để tránh tìm lại.

## 8. ZAIC 2025 và các vấn đề riêng không ảnh hưởng kỹ thuật thi đấu

- Định nghĩa và nơi hiển thị ZAIC_ID sau đăng nhập: chưa xác minh công khai (vấn
  đề của form đăng ký đội, không ảnh hưởng đến kỹ thuật thi đấu).

## 9. Số liệu benchmark — mâu thuẫn giữa các nguồn thứ cấp

- BFCL: các nguồn thứ cấp nói về phiên bản/tập model khác nhau — không chọn một
  con làm "đầu bảng BFCL".
- BIRD/Spider 2.0: số EX theo bản tổng hợp khác nhau, khác thời điểm/backbone/tập
  đánh giá — không so sánh trực tiếp.
- Spider 2.0: o1-preview 17,1% vs 21,3% giữa các nguồn; cần ghi nguồn và điều kiện
  khi trích.
- DABstep: Cascade là tự báo cáo của vendor (92,22% tổng thể, 91,01% hard) — không
  phải leaderboard chính thức.
- PExA (Spider 2.0): tin chưa xác minh từ arXiv/ACL — không dùng làm kết luận.
- ReAct: ALFWorld 71% vs 79% (khi kết hợp CoT-SC) giữa các tóm tắt — đối chiếu bảng
  gốc trước khi trích.
- **Quy tắc chung:** mọi số benchmark trong tài liệu này chỉ dùng để chọn cơ chế,
  không dùng làm mục tiêu số học cho ZAIC.

## 10. Thực nghiệm trên ZAIC — chưa có

- **Chưa có thực nghiệm nào chạy trên dữ liệu ZAIC 2026** trong bộ tài liệu này:
  chưa đo WER thực thể trên audio ZAIC, chưa đo ngưỡng abstain tối ưu, chưa đo
  latency trên A30 / thời gian trên 2× RTX 5090, chưa đo PA/state đúng của bất kỳ
  baseline nào.
- Mọi phương pháp trong tài liệu này là giả thuyết chuyển giao cho tới khi có kết
  quả trên held-out của train, trên public test, và (với DataMate) trên business
  mới (leave-one-business-out).
- Các ngưỡng đề xuất (abstain khởi đầu 0,5; WER thực thể tốt hơn ≥ 2 điểm để đổi
  bản ASR; false-positive call giảm ≥ 20%; PA tăng ≥ 0,03 để giữ hiệu chuẩn; PA
  giảm > 0,15 khi giấu loại hình để ưu tiên exploration) đều là **tiêu chí đề xuất
  trong kế hoạch thử nghiệm**, không phải con số của ban tổ chức.

## 11. Phạm vi tìm kiếm — không tuyên bố đã tìm hết

- Nghiên cứu đã tìm rộng nhưng không tuyên bố đã tìm hết Internet. Các hướng chưa
  đào sâu đủ: winning solutions thực sự cho tabular QA trên Kaggle/AIcrowd/Codabench
  kèm code và license; chuẩn hóa Excel bẩn ở mức file/commit (merged cells, header
  lệch) ngoài mô tả; các benchmark data-analysis agent mới nhất sau 2026-10-27.
- Các nguồn trong [sources.md](sources.md) có URL thiếu được liệt kê riêng ở cuối
  file đó — không bịa URL cho chúng.
