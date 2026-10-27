# DataMate — Ghi chú code và implementation

> Không repo nào trong file này được gọi là "chạy được" dựa trên đọc mô tả.
> Mọi mục "tái sử dụng code" trong các ghi chú gốc đều là ý tưởng pipeline, chưa
> đọc file/commit — trước khi dùng code của repo nào, ghi file/commit đã đọc.

## Các khối code phải tự viết (không phụ thuộc repo ngoài)

### 1. Profiler (không dùng LLM) — làm trước mọi thứ khác

Với mỗi business, liệt kê: sheet/bảng, cột, kiểu dữ liệu, giá trị mẫu, alias/mã,
khoảng ngày, missing/duplicate, tên cột gần giống nhau, cột tiền tệ/ngày tháng ở
định dạng nào. Yêu cầu:

- Liệt kê **mọi** sheet, không chỉ sheet đầu tiên.
- Lấy mẫu có chủ đích: không chỉ 3 dòng đầu (dòng đầu có thể là header lệch,
  merged cells, hoặc dòng trống) mà lấy mẫu phân tầng theo thời gian và theo loại
  giá trị.
- Phát hiện header lệch, merged cells, định dạng số/tiền Việt Nam (dấu chấm phân
  cách nghìn, dấu phẩy thập phân, ký hiệu "đ"/"VND"), missing values, duplicate,
  tên sản phẩm không nhất quán và mã sản phẩm.
- Liệt kê **tập giá trị phân loại (distinct values)** cho các cột trạng thái/loại,
  không chỉ lấy mẫu ngẫu nhiên — vì một mã trạng thái "đã hủy" chỉ xuất hiện 0,1%
  nhưng loại cả đơn hàng.
- Ghi lại "bằng chứng tồn tại" cho mỗi cột cần thiết: cột có tồn tại không, có giá
  trị trong cửa sổ thời gian không — đây là đầu vào cho bước Planner/unanswerable.
- **Công cụ profiling thứ cấp (chỉ tham khảo ý tưởng, chưa đọc code, không gọi là
  "đã chạy được"):** bank-eda-profiler (DuckDB + Polars), pipedog (snapshot schema
  + scan drift + báo cáo). Ý tưởng lấy được: snapshot schema và báo cáo drift — khi
  private test có business mới, profiler phải báo cáo schema khác train ở đâu, thay
  vì im lặng chạy tiếp.

### 2. Thư viện helper cố định — viết từ rulebook, unit-test, không để LLM tự suy ra

| Helper | Viết từ đâu | Unit test bắt buộc |
|---|---|---|
| `revenue(lines)` | Tổng tiền dòng sau chiết khấu cấp dòng, voucher cấp đơn không trừ, không VAT/phí ship, loại đơn hủy và đơn có mặt hàng bị trả | Đơn hủy, đơn có 1 dòng bị trả, đơn có voucher, đơn có VAT |
| `is_cancelled / is_returned` | Distinct values của cột trạng thái trong profiler | Mọi mã trạng thái xuất hiện trong train |
| `week_of(date)`, `month_to_asof(asof)` | Tuần Mon–Sun; tháng chứa as-of tới và bao gồm as-of | Biên: as-of là thứ Hai/Chủ Nhật, ngày đầu/cuối tháng |
| `tet_window(lunar_year)` | 23 Chạp – mùng 10, qua calendar.csv của split (thư viện chỉ là fallback) | Tết các năm đã biết, năm nhuận |
| `weighted_avg_cost(lots)` | Giá mua bình quân gia quyền theo lô | Lô có số lượng 0, lô trùng ngày |
| `best_seller(rows)` | Theo số lượng, không theo doanh thu | Hòa (hòa đã loại khỏi test set theo ghi nhận — vẫn test để phát hiện) |
| `format_number / format_percent / format_date / format_month` | Number 2 chữ số thập phân; percent kèm dấu; date ISO yyyy-mm-dd; tháng yyyy-mm | Làm tròn biên (0,005), percent 0% và 100%, tháng 1 chữ số |

### 3. Tầng đọc bảng thống nhất

- Tự phát hiện header thật (bỏ dòng tiêu đề/logo), chuẩn hóa tên cột (NFC,
  lowercase, bỏ ký tự đặc biệt — đúng cách evaluator chuẩn hóa string/table), xử
  lý merged cell, ngày tháng Excel (serial), số dạng text, đơn vị (nghìn/triệu, %,
  tiền tệ).
- Viết bằng code xác định (deterministic), không để LLM đoán — vì lỗi ở đây làm
  sai cả những câu tính toán đúng.
- Engine tính toán: DuckDB (query trực tiếp CSV/Parquet/JSON, glob file, DataFrame
  là bảng, attach SQLite) — LLM sinh SQL, DuckDB chạy, kết quả là đáp án. DuckDB
  không tính tham số model, offline được.

### 4. Lịch âm–dương Việt Nam

- **Nguyên tắc:** lịch Việt Nam là âm lịch (lunisolar), tháng theo chu kỳ mặt trăng
  ~29,5 ngày, có tháng nhuận ~2–3 năm một lần; tính theo múi giờ UTC+7. New moon có
  thể rơi gần nửa đêm nên ngày bắt đầu tháng âm có thể lệch 1 ngày so với lịch
  Trung Quốc (UTC+8). **Cấm dùng lịch Trung Quốc thay cho lịch Việt Nam.**
- **Quy tắc ưu tiên khi mâu thuẫn:** `calendar.csv` của split > rulebook của split
  > thư viện lịch. Thư viện chỉ dùng khi split không cung cấp calendar cho khoảng
  thời gian cần thiết, và khi đó phải ghi log "đã dùng thư viện thay vì
  calendar.csv".
- **Thư viện Python (trang PyPI, chưa đọc code, chưa chạy kiểm tra):**
  - `lunar-vn` (MIT theo trang PyPI): https://pypi.org/project/lunar-vn/1.3.0/ —
    chuyển solar ↔ lunar, hỗ trợ tháng nhuận, timezone mặc định UTC+7, ~1900–2100,
    thuật toán Hồ Ngọc Đức.
  - `vi-lunaire` (MIT theo trang PyPI): https://pypi.org/project/vi-lunaire/ —
    solar ↔ lunar, Can Chi, ngày lễ, ~1900–2100, thuật toán Hồ Ngọc Đức + công thức
    new moon của Jean Meeus, timezone UTC+7.
- **Unit test bắt buộc:** Tết các năm đã biết (2023: 22/01; 2024: 10/02; 2025: 29/01;
  2026: 17/02 — theo nguồn thứ cấp, đối chiếu với calendar.csv của split), cửa sổ
  23 Chạp–mùng 10, roundtrip solar→lunar→solar cho mọi ngày trong khoảng dữ liệu
  của train; nếu bất kỳ test nào lệch 1 ngày, dừng và đối chiếu calendar.csv.

### 5. Pipeline 7 bước (làm theo thứ tự, không nhảy bước)

```
Câu hỏi + business data + README + rulebook(split) + as-of + calendar.csv
  → 1. PROFILER (không LLM)
  → 2. PLANNER (LLM, prompt riêng): liệt kê cột/bảng/cửa sổ/quy tắc cần thiết;
     kết luận ĐỦ hay THIẾU dữ liệu; THIẾU → unanswerable (dừng)
  → 3. CODER (LLM): viết code SQL (DuckDB/SQLite) và/hoặc Python/pandas từ plan +
     schema đã lọc + rulebook; LLM KHÔNG tự tính nhẩm
  → 4. EXECUTOR: chạy code trong sandbox; ghi log code + kết quả + lỗi
  → 5. CHECKER: đối chiếu kết quả với plan + rulebook + as-of + đơn vị;
     lỗi thực thi hoặc kết quả rỗng/không hợp lý → sửa tối đa 1–2 vòng, kèm lỗi
     thực thi (không sửa mù)
  → 6. CROSS-CHECK: tính lại bằng đường thứ hai (SQL vs pandas); khác nhau →
     không chốt đáp án, chuyển sang abstain hoặc vòng sửa có mục tiêu
  → 7. FORMATTER (tách riêng, có test): chuyển kết quả thành type đúng
  → Quyết định cuối: trả lời / unanswerable / abstain theo ngưỡng đã calibration
     trên train_cal tách theo business và khóa trước khi đo holdout (không theo
     confidence miệng của LLM, không học ngưỡng trên public test)
```

### 6. Quy tắc join và aggregate — nơi lỗi "chạy được nhưng sai" hay ẩn nhất

- **Fan trap:** join đơn hàng (1) với dòng hàng (nhiều) rồi SUM tiền sẽ nhân đôi
  nếu join thêm một bảng nhiều nữa (ví dụ thanh toán nhiều lần). Quy tắc: aggregate
  ở mức dòng trước khi join, hoặc dùng `COUNT(DISTINCT ...)`, hoặc tính bằng
  subquery đã aggregate — và cross-check bằng pandas với cùng logic.
- **Join ngầm:** khi câu hỏi nhắc một thực thể không có khóa trực tiếp (ví dụ "khách
  hàng" qua số điện thoại/email thay vì mã), liệt kê khóa join từ profiler
  (distinct values, tỷ lệ khớp) trước khi viết SQL, không để LLM đoán khóa.
- **Cửa sổ thời gian:** mọi filter ngày phải có cả hai biên và kiểm tra "có vượt
  as-of không". Câu hỏi "tháng này" mà code lấy cả tháng (bao gồm ngày sau as-of)
  là sai logic dù SQL chạy được.
- **Tiền tệ/đơn vị:** không cộng số ở đơn vị khác nhau (nghìn đồng vs đồng, kg vs
  tấn) nếu không có bước quy đổi trong helper. Profiler phải ghi đơn vị của từng
  cột tiền/số lượng.

### 7. Formatter theo type — checklist trước khi ghi submission

| Type | Kiểm tra |
|---|---|
| number | Làm tròn 2 chữ số thập phân; không thêm ký tự tiền tệ; không dùng định dạng phân cách nghìn nếu evaluator so sánh số |
| percent | Kèm dấu theo đúng định dạng đã ghi trong đề bài; kiểm tra 0–100 hay 0–1 (đừng đoán — đọc evaluator/rulebook; điểm này UNVERIFIED, Q-D4) |
| string | Chuẩn hóa NFC + lowercase + thay ký tự không phải chữ/số/khoảng trắng bằng khoảng trắng; giữ dấu thanh; dùng alias/mã trong dữ liệu |
| date | ISO yyyy-mm-dd; tháng yyyy-mm; kiểm tra không vượt as-of khi câu hỏi giới hạn tới as-of |
| boolean | Chỉ true/false theo đúng type, không trả "có/không" dạng string |
| list | Đúng thứ tự đã ghi trong đề bài (nếu đề bài không ghi thứ tự, ghi log và đối chiếu evaluator — đừng tự chọn thứ tự) |
| table | Đúng tên cột, đúng thứ tự cột, đúng hàng; rows as set theo ghi nhận (cần đối chiếu evaluator: "as set" có nghĩa thứ tự hàng không quan trọng hay không) |
| unanswerable | Chỉ trả khi Planner kết luận thiếu dữ liệu, không phải khi code lỗi |
| abstain | Khi không đủ tự tin sau calibration, hoặc hai đường tính mâu thuẫn và đã hết vòng sửa |


## Hồ sơ sâu round 2 — đọc ở đây, không lặp lại trong file này

- ReFoRCE (CODE_INSPECTED ở mức file), schemagate (README_READ), DSR-SQL
  (PAPER_READ, repo chính thức 404), BASE-SQL ablation, DABstep/I2I-STRADA:
  xem [deep-profiles.md](deep-profiles.md).
- ReFoRCE: lấy SqlEnv 3 trạng thái, vòng sửa tối đa 3 lần → simplify khi rỗng
  → dừng sau 3 thất bại liên tiếp, exploration xác định trước exploration LLM,
  `reduce_ddl()`; bỏ random vote khi hòa (hòa → abstain), bỏ GPT API và
  credential Snowflake/BigQuery, cắt kết quả thăm dò bằng aggregate có chủ đích
  thay vì cắt mù 500 ký tự.
- schemagate: shortlist bảng/cột xác định trước khi đưa cho LLM, bảng không được
  phép vắng mặt hoàn toàn khỏi prompt; guard fallback một lần sang schema đầy đủ
  trước khi kết luận unanswerable; đo recall shortlist trên train.
