# Hồ sơ track — DataMate

*Mức bằng chứng: official portal https://challenge.zalo.ai/portal/datamate, kiểm tra
2026-10-26 (sau đăng nhập). Các điểm ghi "cần đối chiếu" là chưa xác minh trong
phiên nghiên cứu này — xem [../gaps.md](../gaps.md).*

## Đề bài

Agent trả lời câu hỏi **tiếng Việt đời thường** trực tiếp trên dữ liệu có cấu trúc
của doanh nghiệp nhỏ Việt Nam: CSV, Excel, SQLite + README + rulebook + ngày as-of
+ lịch âm–dương theo split.

## Đầu vào / đầu ra

- **Đầu vào:** gói dữ liệu 1 doanh nghiệp, 1 câu hỏi tiếng Việt, ngày as-of,
  rulebook và `calendar.csv` của đúng split.
- **Đầu ra:** 1 đáp án có type rõ ràng — `number`, `percent`, `string`, `date`,
  `boolean`, `list`, `table` — hoặc `unanswerable` (dữ liệu không chứa thứ cần
  thiết), hoặc `abstain` (agent chủ động không trả lời).
- Đáp án chỉ đúng khi **type bằng type tham chiếu VÀ giá trị khớp**:
  number khớp chính xác sau làm tròn 2 chữ số thập phân; percent khớp sau làm tròn
  2 chữ số và đúng dấu; string chuẩn hóa NFC + lowercase + ký tự không phải
  chữ/số/khoảng trắng thành khoảng trắng + gộp khoảng trắng, **giữ dấu thanh**;
  date ISO `yyyy-mm-dd` hoặc `yyyy-mm`; boolean khớp chính xác; list có thứ tự;
  table khớp cột theo tên đã chuẩn hóa, nếu không khớp thì theo vị trí, hàng khớp
  dạng tập hợp.
- Unanswerable chỉ đúng khi tham chiếu cũng là unanswerable.

## Cách chấm — Penalized Accuracy (PA)

Đúng +1, abstain 0, sai −1, trên N câu, mọi câu trọng số bằng nhau, không điểm
từng phần. Sai type hoặc sai giá trị đều tính là sai.

**Hệ quả (suy luận từ công thức, không phải tuyên bố của evaluator):** với xác suất
đúng p đã calibration, kỳ vọng trả lời = 2p − 1, nên ngưỡng hòa vốn lý thuyết là
p > 0,5. Ngưỡng thật phải hiệu chuẩn trên held-out vì model thường overconfident.
Xem phân tích đầy đủ ở [../plans/datamate.md](../plans/datamate.md).

## Giới hạn

- Tổng tham số mọi model dùng lúc inference **≤ 15B**, tính cả embedding, reranker,
  classifier và toàn bộ tham số của MoE (không tính theo active).
- Mọi model phải có trọng số công bố công khai **trước 01/10/2026**, khai báo trong
  solution README. Quantization được phép; quantization giảm bộ nhớ, không giảm
  số tham số.
- Chạy offline trong Docker; được sinh và thực thi code.
- Máy chấm tham chiếu: 2× RTX 5090 (32GB mỗi card), 512GB RAM; toàn bộ private test
  trong **6 giờ wall-clock** kể cả thời gian nạp model; GPU Blackwell yêu cầu
  CUDA ≥ 12,8 và build PyTorch/vLLM tương thích.
- Tính tái lập: |PA(uploaded) − PA(rerun)| ≤ 0,03; nếu vượt, ban tổ chức xem log,
  có thể chạy lại thêm 1 lần và yêu cầu thêm thông tin; nếu không giải thích được
  thì bị loại.
- **Private test có cả loại hình doanh nghiệp chưa xuất hiện ở train/public test.**

## Dữ liệu (mục Data sau đăng nhập, 2026-10-26)

- Train: https://dl-challenge.zalo.ai/2026/datamate_dkewxftdzo/train.zip
- Public test: https://dl-challenge.zalo.ai/2026/datamate_dkewxftdzo/public_test.zip
- Mỗi split: `data/<business_id>/` (file `.csv`/`.xlsx`/`.sqlite` + `README.md`),
  `rulebook.md` riêng từng split, `calendar.csv` lịch âm–dương, `questions.jsonl`,
  `answers.jsonl` chỉ có ở train (có thêm trường `alias`; câu unanswerable có
  answer null — theo ghi nhận 2026-10-26).
- **Bước xác minh đầu tiên khi có dữ liệu (bắt buộc, trước mọi code đo):**
  giải nén zip thật và liệt kê file thực tế của từng split. Ghi nhận 2026-10-26
  nói public test không có `answers.jsonl`; nếu zip thật có đáp án thì toàn bộ
  giao thức đo trong repo này (học ngưỡng trên train_cal, public test chỉ đo
  format/latency) phải viết lại theo thực tế đó — không được giả định nhãn
  public tồn tại, cũng không được giả định là 'chắc chắn không có'.
- Loại hình: tạp hóa, cà phê/trà sữa, nhà hàng, nhà thuốc, vật liệu xây dựng, tiệm
  sửa xe máy, cửa hàng mẹ và bé, và nhiều loại khác. Mỗi doanh nghiệp bao phủ
  12–30 tháng, vài trăm đến ~300.000 dòng, có tính mùa vụ (Tết, Trung Thu, lễ, ngày
  trả lương, cuối tuần).
- Chất lượng README không đều: có nơi có từ điển dữ liệu đầy đủ, có nơi chỉ vài
  ghi chú, có nơi gần như không có gì — vì vậy profiler tự động là bắt buộc.
- **Chưa tải/giải nén để xác minh trong phiên này:** kích thước zip, số doanh nghiệp
  và số câu hỏi chính xác, nội dung đầy đủ của README/rulebook/calendar.csv.

## Rulebook mặc định tiêu biểu (phải dùng đúng rulebook của split đang trả lời)

- Doanh thu = tổng tiền theo dòng sau chiết khấu cấp dòng (voucher cấp đơn không
  trừ), không tính VAT và phí giao hàng, loại đơn đã hủy và đơn có bất kỳ mặt hàng
  nào bị trả lại.
- "Bán chạy" tính theo số lượng.
- Tuần từ thứ Hai đến Chủ Nhật; "tháng này" là tháng chứa ngày as-of, tính đến và
  bao gồm ngày đó.
- Chi phí mặc định là chi phí mua bình quân gia quyền theo lô.
- Cửa sổ Tết từ 23 tháng Chạp đến mùng 10 âm lịch.

## Cần đối chiếu trước khi chốt submission

- Cách evaluator xử lý: missing answer, agent trả `unanswerable` khi reference là
  giá trị (và ngược lại), sai type, hòa ranking, sai thứ tự list, sai làm tròn,
  định dạng percent (0–100 hay 0–1), "rows as set" cho table.
- Checkpoint phái sinh từ fine-tune có được tính là "model công bố trước
  01/10/2026" hay không — nếu chưa rõ, giữ phương án dự phòng bằng model gốc
  chưa fine-tune.
