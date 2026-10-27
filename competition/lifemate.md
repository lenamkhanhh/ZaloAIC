# Hồ sơ track — LifeMate

*Mức bằng chứng: official portal https://challenge.zalo.ai/portal/lifemate, kiểm tra
2026-10-26 (sau đăng nhập). Các điểm ghi "cần đối chiếu" là chưa xác minh trong
phiên nghiên cứu này — xem [../gaps.md](../gaps.md).*

## Đề bài

Agent nghe yêu cầu **tiếng Việt** (audio), dùng user context, lịch sử hội thoại và
schema tool của các app mô phỏng (smart home, banking, ride-hailing, food delivery,
email) để lập kế hoạch và gọi tool đúng thứ tự, đạt trạng thái cuối mong muốn.

## Đầu vào / đầu ra

- **Đầu vào:** 1 file audio yêu cầu tiếng Việt, ngữ cảnh người dùng, các app đã cài,
  lịch sử hội thoại, tool schemas.
- **Đầu ra:** danh sách `tool_calls` có thứ tự + `state_hash` do môi trường tạo
  (`env.get_state_hash()`).
- **Thiếu thông tin:** gọi `sys.ask_missing_info`.
- **Ngoài phạm vi:** trả danh sách rỗng `[]`.
- Mẫu gold rỗng chỉ được điểm khi danh sách nộp cũng rỗng.

## Cách chấm

- `state_hash` nộp phải bằng gold `state_hash`; nếu không, mẫu đó **0 điểm** — bất
  kể tool calls trông đúng đến đâu.
- Nếu hash đúng, chấm F1 trên tool calls: khớp khi cùng tên tool, mọi tham số
  non-fuzzy giống hệt, tham số fuzzy đạt token-F1 > 0,6 sau lowercase và Unicode NFC;
  thứ tự không xét; mỗi call khớp tối đa 1 call.
- Timeout hoặc lỗi thực thi = 0 điểm cho mẫu đó.
- Seed cố định, deterministic decoding (greedy hoặc temperature = 0); nếu chạy lại
  khác kết quả nộp, ban tổ chức chạy Docker 5 lần lấy trung bình.

## Giới hạn

- Toàn hệ thống **< 6B tham số**, LLM **< 5B**, context **≤ 16.384 token**.
- Model mã nguồn mở, phát hành **trước 26/10/2026**.
- Mỗi mẫu tối đa **30 giây trên 1× NVIDIA A30** (CPU 16-core Xeon Gold 6442Y, 64GB RAM).
- Chạy fully offline. Nộp Docker + `submission.jsonl`.
- **Cấm:** đọc trực tiếp `state.json` hoặc bất kỳ file nào dưới `<split>_environment/`;
  mọi đọc/ghi phải qua `zaic_tools`, đúng 1 ToolEnv cho mỗi mẫu, và mọi call trên
  ToolEnv đó phải xuất hiện trong submission.

## Dữ liệu (mục Data sau đăng nhập, 2026-10-26)

- Tải: https://dl-challenge.zalo.ai/2026/lifemate_argfzdgert/train+public_test.zip
- Train ~1.600 mẫu có nhãn, public_test ~600 mẫu, private_test ~600 mẫu.
- Audio WAV 16 kHz mono 16-bit, ~100% giọng người thật, đủ Bắc–Trung–Nam, có từ
  tiếng Anh xen vào.
- Train có thêm `audio_text` và nhãn gold `tool_calls`, `tool_results`, `final_state`.
  **Public test chỉ có `sample_submission.jsonl` làm mẫu format theo ghi nhận
  2026-10-26 — không khẳng định public_test có gold;** mọi thí nghiệm cần điểm
  số phải chạy trên train held-out. Bước xác minh đầu tiên: mở 1–2 dòng
  public_test jsonl, kiểm tra có field gold nào không; nếu có gold thì ghi chú
  này phải viết lại theo thực tế của zip.
- Mỗi split: `audio/<id>/<id>.wav`, `<split>.jsonl`, `<split>_tools_catalog.json`,
  `<split>_environment/<id>/state.json`, `zaic_tools/` riêng từng split;
  `sample_submission.jsonl` chỉ có ở public_test.
- Tool catalog có `kind` (read/write/meta, meta = `sys.ask_missing_info`), `x-ref`
  (phải là ID hợp lệ), `x-match: fuzzy`, `x-one-of`; chỉ gọi tool của app trong
  `context.installed_apps`.
- **Chưa tải/giải nén để xác minh trong phiên này:** kích thước zip, catalog tool
  chính xác, Docker base image, inference script chính thức.

## Giả định làm việc về read/F1 — ASSUMPTION, chưa truy cập được evaluator

- F1 được tính trên toàn bộ `tool_calls` đã nộp, mẫu số gồm cả call thừa;
  `state_hash` do evaluator tự tính từ state cuối. Nếu F1 thực tế chỉ tính
  trên call thành công hoặc bỏ qua read, phân tích read trong repo này phải
  viết lại. Vì vậy: **không mặc định read trước và sau mọi write** — xem
  bảng selective reads và loop guard trong
  [../research/lifemate/deep-profiles.md](../research/lifemate/deep-profiles.md) §0.
- Validator TRƯỚC khi gọi là an toàn; **lọc call SAU khi đã thực thi là rủi
  ro** — không tự ý giấu failed call hay read call khỏi submission.

## Cần đối chiếu trước khi chốt submission (xem gaps.md Q-L1..Q-L6)

- Cách chấm chính xác của `sys.ask_missing_info` (đúng/sai/thừa/thiếu tính thế nào).
- Failed call có được giữ trong trace nộp hay phải loại bỏ.
- Cách tính tham số: total hay active (với MoE, giả định an toàn là total).
- Mọi ToolEnv call có bắt buộc xuất hiện trong submission không, và validator lọc
  sau thực thi có vi phạm luật log không.
- Read call có tính vào F1 không, và read thừa có bị trừ như write thừa không.
