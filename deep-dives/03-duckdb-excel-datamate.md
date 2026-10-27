# Chuyên đề 3 — DuckDB làm Execution Engine & xử lý "Excel bẩn" cho DataMate

> Code đi kèm: [03-duckdb-excel-datamate.py](03-duckdb-excel-datamate.py)
> (665 dòng, type hints, docstring, chạy offline; đã chạy thử trên dữ
> liệu tổng hợp tự tạo, **không phải dữ liệu ZAIC**).
>
> **CẢNH BÁO QUAN TRỌNG VỀ TIỀN TỆ — đọc trước khi dùng code:**
> code demo dùng `float` cho tiền chỉ để gọn. **Ở pipeline thật, tiền
> phải dùng `DECIMAL` (DuckDB) hoặc số nguyên đơn vị nhỏ nhất (đồng),
> không bao giờ dùng float cho đáp án cuối**, vì làm tròn nhị phân của
> float có thể đẩy một đáp án đúng sang sai ở chữ số thập phân cuối —
> và DataMate không có điểm từng phần.
>
> Nhãn bằng chứng dùng trong tài liệu này:
> - `TRANSFER-HYPOTHESIS` = suy luận chuyển giao, chưa có thực nghiệm
>   trên dữ liệu ZAIC. Không được đọc thành "hiệu quả trên ZAIC".
> - `CODE-TESTED-SYNTHETIC` = đã chạy trong phiên này trên dữ liệu tổng
>   hợp tự tạo, không phải dữ liệu ZAIC.
> - `SECONDARY` = nguồn thứ cấp, chưa đối chiếu trực tiếp với trang gốc.
> - `UNVERIFIED` = chưa xác minh, phải kiểm tra trước khi đóng
>   Docker/nộp bài.

## 0. Kết luận trước — kiến trúc đề xuất

```
Excel bẩn (.xlsx) ──► tiền xử lý Python (openpyxl, chỉ đọc + làm sạch)
CSV (.csv) ────────► kiểm soát kiểu ở tầng load
SQLite (.sqlite) ──► đọc bằng sqlite3 stdlib (KHÔNG dùng DuckDB sqlite extension)
                        │
                        ▼
              DuckDB in-memory: MỌI bảng đăng ký thành view thống nhất
              + view "calendar" từ calendar.csv của đúng split
                        │
                        ▼
LLM (Qwen2.5-Coder-7B) chỉ sinh: 1 câu SQL SELECT/WITH + tham số
                        │  (không sinh code Python thay đổi dữ liệu ở luồng chính)
                        ▼
              DuckDB thực thi → kiểm chứng (lỗi / rỗng / rule assertion)
              → formatter theo type → quyết định trả lời / unanswerable / abstain
```

Lý do chọn kiến trúc này, gói trong một câu: **đưa mọi quy tắc nghiệp
vụ vào một nơi duy nhất có thể đọc, kiểm tra và tái sử dụng được (SQL +
view thống nhất), và đẩy mọi thứ "bẩn, mơ hồ, cần đoán" ra khỏi SQL, vào
tầng tiền xử lý Python nơi mỗi quyết định mơ hồ đều để lại một issue
trong audit thay vì lặng lẽ biến thành một con số sai.** Phần còn lại
của tài liệu chứng minh từng nửa của câu đó, và chỉ rõ khi nào nó
không đúng.

LLM code generator trong chuyên đề này là Qwen2.5-Coder-7B-Instruct
(7,61B tổng, Apache 2.0 — theo ghi chú round trước; ngày commit đầu tiên
trên Hugging Face vẫn `UNVERIFIED`, kiểm tra lại trước khi nộp). Đây là
model DataMate (trần 15B); nó **không** phải LLM LifeMate (xem chuyên
đề 1). Xem shortlist đầy đủ trong
[../research/comparison.md](../research/comparison.md).

## 1. SQL qua DuckDB so với code Python (pandas/polars)

### 1.1. Bảng so sánh trung thực

| Tiêu chí | SQL qua DuckDB (luồng chính đề xuất) | Code Python pandas (luồng chính thay thế) | Code Python polars |
|---|---|---|---|
| Bản chất tính toán | Khai báo (declarative): nói *lấy gì*, engine quyết định *lấy như thế nào* | Mệnh lệnh (imperative): từng bước merge/filter/groupby do code chỉ định | Khai báo/lazy như SQL, API expression; tối ưu bởi engine Rust |
| Quy tắc nghiệp vụ (loại đơn hủy/trả, trừ chiết khấu dòng, loại VAT/phí ship, cửa sổ tới as-of) | Nằm trong `WHERE`/`CTE` của câu SQL, đọc được trong một chỗ, tái sử dụng nguyên văn cho câu hỏi khác cùng split | Nằm rải trong các nhánh `if`, mask boolean, hàm helper — dễ phân kỳ giữa các câu hỏi nếu mỗi câu sinh code riêng | Như pandas, nhưng expression rõ ràng hơn |
| Fan trap / double counting (xem §1.2) | Vẫn mắc được, nhưng lỗi nằm ở một chỗ duy nhất (thứ tự JOIN–GROUP BY) và có thể bắt bằng unit test trên bảng nhỏ + rule assertion | Vẫn mắc được, và lỗi còn khó thấy hơn vì merge rồi sum là hai bước tách rời, trung gian không có tên | Như pandas |
| Kiểu dữ liệu | Kiểu chặt: `DATE`, `DECIMAL`, `INTEGER`; sai kiểu thường lỗi ngay lúc chạy | Kiểu lỏng: `object`/`float64`/`NaN` lan truyền lặng lẽ; `pd.to_numeric(errors="coerce")` biến lỗi thành NaN rồi thành 0 nếu cộng dồn không cẩn thận | Kiểu chặt hơn pandas, lỗi rõ hơn |
| Lỗi thực thi | Một lỗi SQL kèm câu SQL đầy đủ — log được nguyên văn để đối chiếu Docker rerun | Lỗi Python kèm traceback, nhưng lỗi *logic* (không phải lỗi chạy) thường không có tín hiệu gì | Như pandas, lỗi rõ hơn ở expression |
| Tính xác định (determinism) | Xác định nếu có `ORDER BY` tường minh cho mọi truy vấn cần thứ tự (bảng, list, top-k); không có `ORDER BY` thì thứ tự hàng là không đảm bảo | Xác định nếu sort tường minh; `groupby`/`merge` không sort có thể cho thứ tự khác nhau giữa các lần chạy/phiên bản | Lazy + song song: vẫn xác định về giá trị nếu sort tường minh, nhưng thứ tự mặc định cũng không đảm bảo |
| Hiệu năng ở ~300.000 dòng | `TRANSFER-HYPOTHESIS`: cột dọc (columnar) + vectorized + pushdown filter/projection là kiến trúc phù hợp với lọc + groupby; 300k dòng là nhỏ so với RAM 512GB, nên nút thắt khả dĩ nằm ở LLM sinh code, không phải ở engine — **phải đo trên train held-out, không trích số benchmark blog làm bằng chứng** | Đủ nhanh ở 300k dòng cho đa số câu hỏi, nhưng merge nhiều bảng rộng + groupby trên cột `object` tốn RAM hơn và dễ phình trung gian | Nhanh hơn pandas ở cùng workload theo kiến trúc (lazy, song song, Arrow); là ứng viên thay pandas ở tầng Python nếu đo thấy pandas chậm |
| Đọc Excel bẩn | Không làm được trực tiếp: DuckDB không phải trình đọc Excel bẩn (merged cells, header nhiều cấp, format số VN) | Làm được: openpyxl/pandas là tầng duy nhất đọc được cấu trúc file gốc | Đọc Excel qua engine tương tự pandas; vẫn cần openpyxl cho merged/header |
| Logic theo từng dòng, phụ thuộc trạng thái | Yếu: SQL giỏi tập hợp, kém logic dòng phức tạp (ví dụ: parse chuỗi tự do, luật "nếu A thì tra B rồi mới quyết định C" viết bằng SQL rất dài) | Mạnh: vòng lặp/điều kiện tự nhiên | Mạnh vừa phải qua expression; logic dòng phức tạp vẫn nên viết Python |
| Chi phí bảo trì trong Docker | Một engine (DuckDB) + một bộ view thống nhất; LLM chỉ cần học một "ngôn ngữ đích" | Mỗi câu hỏi là một chương trình mới — khó kiểm chứng exhaustively | Thêm một engine thứ hai vào Docker nếu dùng song song với DuckDB: tăng diện tích lỗi, chỉ làm khi đo thấy cần |

**Không có chuyện "Text-to-SQL qua DuckDB luôn ít bug logic nghiệp vụ
hơn".** Điều đúng, và là điều duy nhất nên khẳng định, là: **SQL làm
cho bug nghiệp vụ dễ nhìn thấy, dễ test và dễ sửa hơn, vì quy tắc nằm
ở một chỗ và có tên.** Còn bản thân bug thì cả hai phía đều mắc, theo
những cách khác nhau (xem §1.2). Mọi con số "nhanh hơn X lần" trên blog
đều là `SECONDARY`, khác máy, khác dữ liệu, khác phiên bản — tài liệu
này không dùng bất kỳ con số nào trong số đó làm căn cứ chọn kiến trúc.

### 1.2. Fan trap — lỗi "chạy được nhưng sai" nguy hiểm nhất

Ví dụ tối thiểu (bảng nhỏ tự tạo, không phải dữ liệu ZAIC):

- `orders`: 1 đơn `DH001`, `order_total = 1.000.000` (tổng đã tính sẵn ở
  bảng đơn).
- `order_lines`: đơn `DH001` có 3 dòng.

Câu SQL sai nhưng chạy được:

```sql
SELECT SUM(o.order_total) AS revenue
FROM orders o JOIN order_lines l ON l.order_id = o.order_id;
-- Kết quả: 3.000.000 — sai gấp 3 lần, vì mỗi dòng nhân bản tổng của đơn.
```

Câu SQL đúng có hai dạng, và chỉ một trong hai nên dùng tùy câu hỏi:

```sql
-- Dạng A: cần tổng theo đơn -> aggregate TRƯỚC khi join, hoặc đừng join.
SELECT SUM(order_total) AS revenue FROM orders WHERE ...;

-- Dạng B: cần tổng theo dòng -> aggregate ở grain của dòng, không đụng tới
-- tổng đã tính sẵn ở bảng đơn.
SELECT SUM(l.line_amount_after_discount) AS revenue
FROM order_lines l JOIN orders o ON o.order_id = o.order_id
WHERE o.status <> 'cancelled' AND l.status NOT IN ('cancelled', 'returned');
```

Pandas mắc đúng lỗi này theo cách khó thấy hơn: `orders.merge(lines)`
rồi `.sum()` trên cột tổng của đơn — trung gian là một DataFrame phình
ra mà không ai đặt tên, không ai test riêng. Vì vậy quy tắc bắt buộc
trong pipeline (không phụ thuộc engine):

1. **Khai báo grain trước khi tính:** đáp án này là tổng ở grain đơn,
   grain dòng, hay grain ngày? Viết grain đó thành comment/CTE đầu tiên.
2. **Không bao giờ SUM một cột tổng đã tính sẵn sau khi join 1–N.**
   Hoặc aggregate trước, hoặc tính lại từ dòng.
3. **Unit test bằng bảng tay 3–5 dòng có đáp án tính tay** cho mỗi pattern
   join thường gặp (1–N, N–N qua bảng trung gian, join với bảng calendar
   1–1 theo ngày). Test này chạy trước mọi đo PA, vì PA không phân biệt
   được "sai do fan trap" với "sai do hiểu câu hỏi".
4. **Rule assertion sau thực thi:** ví dụ tổng doanh thu theo dòng không
   được vượt tổng doanh thu theo đơn quá một ngưỡng do rulebook cho phép
   (nếu rulebook không cho ngưỡng thì assertion này là `UNVERIFIED`,
   không tự đặt ngưỡng); tổng theo ngày không được vượt tổng toàn kỳ.

### 1.3. Khi nào Python thắng SQL (và phải giữ Python ở đó)

| Tình huống | Thắng | Lý do |
|---|---|---|
| Đọc Excel bẩn: merged cells, header nhiều cấp, format số/ngày VN | Python (openpyxl) | DuckDB không hiểu cấu trúc trình bày của file gốc; đây là việc của tầng đọc, không phải tầng tính |
| Parse số/ngày mơ hồ, gắn cờ ambiguity | Python | Cần logic từng ô + audit issue; SQL ép kiểu sẽ hoặc lỗi cả câu, hoặc coerce lặng lẽ |
| Logic dòng phức tạp, phụ thuộc trạng thái, chuỗi tự do | Python | SQL viết ra dài, khó đọc, khó test từng nhánh |
| Tính toán thứ hai độc lập để cross-check | Python (pandas/polars) — nhưng chỉ khi logic thật sự khác | Nếu "đường thứ hai" chỉ là dịch cùng một logic sang pandas thì nó chia sẻ cùng hiểu sai với SQL và không bắt được gì; cross-check chỉ có giá trị khi hai đường suy luận khác nhau (ví dụ: SQL aggregate từ dòng vs Python tính từ bảng tổng hợp đã kiểm chứng) |
| Mọi câu hỏi lọc/nhóm/tổng/xếp hạng trên dữ liệu đã sạch | SQL/DuckDB | Một ngôn ngữ đích, một nơi chứa rule, log được nguyên văn |

**Kết luận kiến trúc:** DuckDB là engine duy nhất ở luồng chính; Python
giữ hai vai trò và chỉ hai vai trò: (a) tiền xử lý Excel bẩn thành view
sạch, (b) kiểm chứng độc lập (assertion, cross-check khi logic thật sự
khác). Không đưa polars vào làm engine thứ hai ngay từ đầu: nó là
phương án dự phòng nếu đo trên train held-out thấy pandas ở tầng kiểm
chứng chậm một cách có ý nghĩa — và "có ý nghĩa" phải đo bằng giây/câu
hỏi, không phải bằng cảm giác.

### 1.4. Tiền tệ và kiểu số — chi tiết dễ mất điểm nhưng ít người nói

- Trong code demo, tiền dùng `float` cho gọn. **Ở pipeline thật, tiền
  phải dùng `DECIMAL` (DuckDB) hoặc số nguyên đơn vị nhỏ nhất (đồng),
  không dùng float cho đáp án cuối**, vì float làm tròn nhị phân có thể
  đẩy một đáp án đúng sang sai ở chữ số thập phân cuối — và DataMate
  không có điểm từng phần.
- Quy tắc làm tròn cuối cùng (bao nhiêu chữ số, làm tròn lên hay ngân
  hàng) là `UNVERIFIED` cho tới khi đọc evaluator/rulebook của split:
  đừng tự đặt `ROUND(x, 2)` rồi coi đó là chuẩn. Formatter phải nhận quy
  tắc làm tròn làm tham số cấu hình, không hard-code trong prompt của
  LLM.
- Ngày phải là `DATE`, không phải chuỗi `dd/mm/yyyy`, trước khi join với
  calendar (xem §3). So sánh chuỗi ngày kiểu VN sẽ sai thứ tự từ điển
  (`"31/01"` > `"01/02"` theo chuỗi nhưng nhỏ hơn theo thời gian).

## 2. Xử lý "Excel bẩn" thực tế tại Việt Nam

Tiền xử lý trong code đi kèm (`read_excel_sheet`, `parse_vn_number`,
`parse_vn_date`, `flatten_headers`) tuân thủ một nguyên tắc duy nhất:
**mọi thứ mơ hồ đều thành issue trong audit, không thành số lặng lẽ.**
Bảng dưới map từng hiện tượng bẩn sang cách xử lý và hàm tương ứng.

### 2.1. Merged cells (gộp ô)

- Cơ chế openpyxl: chỉ ô góc trên-trái của vùng merge giữ giá trị; các
  ô còn lại trong vùng đọc ra `None`. Vì vậy "điền" ở đây không phải
  đoán — nó là khôi phục lại giá trị mà file gốc đã gán cho cả vùng.
- **Giới hạn bắt buộc:** chỉ điền TRONG vùng merge, không bao giờ tràn
  sang dòng/cột ngoài vùng. Code thực hiện đúng điều này bằng cách xây
  map `(dòng body, cột) -> giá trị` cho từng ô trong vùng, không dùng
  forward-fill mù trên toàn cột (forward-fill mù sẽ kéo giá trị của một
  nhóm hàng sang nhóm hàng khác khi giữa chúng có dòng trống hoặc khi
  vùng merge đã kết thúc — đó là lỗi "đoán qua dòng không liên quan").
- **Guard cho cột mã/ID:** nếu cột đích trông như mã/ID (`id`, `mã`,
  `code`, `số_...`) và vùng merge trải trên nhiều dòng thì KHÔNG điền,
  ghi issue `merged_id_not_filled`. Lý do: một mã gộp trên nhiều dòng có
  thể là một đơn duy nhất có nhiều dòng hàng (điền là đúng) hoặc là
  nhiều mã khác nhau bị gộp nhầm khi xuất file (điền là sai) — không
  phân biệt được từ file, nên phải để rule nghiệp vụ của split quyết
  định, không tự điền.
  `CODE-TESTED-SYNTHETIC`: test với cột "Mã đơn" gộp 2 dòng cho ra đúng
  1 issue và dòng thứ hai giữ `NaN` (không bị điền `DH001`).
- Merge nằm trong vùng header: không điền vào body; header nhiều cấp đã
  xử lý riêng ở §2.3.

### 2.2. Dòng trống

- Dòng trống hoàn toàn (mọi ô `None`/chuỗi rỗng) bị bỏ và đếm vào
  `dropped_blank_rows`. Dòng trống ở CUỐI file thường không xuất hiện
  trong `ws.iter_rows()` của openpyxl nên không được đếm — đó là hành vi
  của thư viện, không phải lỗi logic; dòng trống Ở GIỮA dữ liệu thì được
  bỏ và đếm.
- Dòng trống một phần (vài ô có giá trị) được GIỮ: nó có thể là dòng
  dữ liệu thiếu cột, và việc bỏ nó sẽ làm mất bằng chứng cho quyết định
  `unanswerable` (thiếu dữ liệu). Cột trống hoàn toàn cũng được giữ với
  issue `empty_column_kept`, vì schema linking cần thấy cột đó tồn tại
  nhưng rỗng — khác với cột không tồn tại.

### 2.3. Header nhiều cấp (multi-level headers)

- Cách phát hiện: tham số `header_rows` do người gọi chỉ định, hoặc tự
  đoán (dòng đầu có ≥ 50% ô trống và dòng thứ hai có giá trị → 2 cấp,
  ngược lại 1 cấp). Tự đoán chỉ là heuristic khởi đầu: **trên dữ liệu
  thật, số cấp header phải được xác nhận từ profiler** (đếm dòng đầu
  toàn là nhãn, dòng nào là dòng dữ liệu đầu tiên có mã/ngày/số) rồi
  khóa lại theo từng sheet, không để LLM đoán lại mỗi câu hỏi.
- Cách gộp: mỗi cột lấy tất cả phần header khác rỗng từ trên xuống
  dưới, nối bằng `" | "` làm tên gốc, rồi chuyển thành tên SQL-safe
  bằng cách bỏ dấu tiếng Việt một cách xác định (`đ→d`, NFKD tách dấu
  tổ hợp) và thay ký tự không phải `[A-Za-z0-9_]` bằng `_`. Tên gốc đầy
  đủ dấu giữ trong `header_mapping` để audit và để LLM nhìn thấy ngữ
  nghĩa thật.
- Trùng tên sau khi gộp: hậu tố `_2`, `_3` theo thứ tự cột, không bao
  giờ ghi đè lặng lẽ một cột lên cột khác.
- `CODE-TESTED-SYNTHETIC`: header `[["Doanh thu", "", "Số lượng"],
  ["", "Đã trừ CK", ""]]` cho ra `Doanh_thu_Da_tru_CK` với mapping
  `"Doanh thu | Đã trừ CK"`.

Lưu ý về tên cột: việc bỏ dấu ở đây chỉ áp dụng cho **tên cột SQL
nội bộ** (định danh kỹ thuật), và tên gốc đầy đủ dấu luôn được giữ
trong `header_mapping`. Đây không phải là strip dấu để matching giá
trị — giá trị dữ liệu và đáp án không bao giờ được strip dấu (xem
chuyên đề 2, §2.4).

### 2.4. Format tiền tệ, số thập phân kiểu Việt Nam

Bảng quy tắc trong `parse_vn_number` (chế độ `auto`, không chỉ định
locale):

| Dạng chuỗi | Kết quả | Lý do |
|---|---|---|
| `1.000.000,50` | 1000000.5 | Cả hai dấu đều có: dấu cuối cùng là thập phân (`,`), dấu còn lại là hàng nghìn (`.`) |
| `1,000,000.50` | 1000000.5 | Ngược lại: dấu cuối là thập phân (`.`) |
| `1.000.000` / `1,000,000` | 1000000.0 | Nhóm hàng nghìn lặp ≥ 2 lần, mỗi nhóm đúng 3 chữ số — xác định duy nhất |
| `1,5` | 1.5 | Một dấu `,` với 1 chữ số sau: chỉ có thể là thập phân kiểu VN |
| `1.5` | 1.5 | Một dấu `.` với 1 chữ số sau: chỉ có thể là thập phân |
| `1.500` / `1,500` | `None` + issue `ambiguous_number` | **Mơ hồ thật:** 1500 (hàng nghìn) hay 1.5 (thập phân) đều hợp lệ. Ở `auto` không đoán. Muốn ép, truyền `locale="vn"` (→ 1500) hoặc `locale="en"` (→ 1.5) theo từng cột, có ghi audit |
| `(1.000.000,50)` | −1000000.5 | Ngoặc đơn kiểu kế toán = số âm |
| `50%` | `None` + issue `percent_not_converted_here` | Phần trăm là type đáp án riêng, xử lý ở formatter, không chuyển ở tầng số |
| `31/02/2025` (ở tầng ngày) | `None` + issue `invalid_calendar_date` | Xem §2.5 |

**Vì sao "1.500" phải bị gắn cờ thay vì đoán theo đa số?** Vì trong dữ
liệu doanh nghiệp Việt Nam, cả hai cách đọc đều xuất hiện thật: `1.500`
có thể là 1.500 đồng (giá lẻ, hàng nghìn) hoặc 1,5 kg (thập phân viết
bằng dấu chấm do xuất từ hệ thống khác). Đoán theo đa số sẽ đúng ở cột
này và sai ở cột khác, và sai ở đây là sai đáp án (−1 điểm), không phải
sai làm tròn. Cách đúng là xác định locale **theo cột** từ profiler:
lấy mẫu giá trị của cột, nếu đa số giá trị có cả hai dấu hoặc nhóm hàng
nghìn lặp thì locale của cột là xác định; nếu cột toàn dạng mơ hồ thì
locale của cột là `UNVERIFIED` và mọi ô mơ hồ trong cột đó phải đi vào
quyết định abstain, không được "giải quyết" bằng một luật chung cho cả
file.

### 2.5. Ngày tháng `dd/mm/yyyy` → ISO `yyyy-mm-dd`

- Quy ước duy nhất: ngày trước, tháng sau (chuẩn Việt Nam). Chuỗi ISO
  `yyyy-mm-dd` được giữ nguyên sau khi kiểm tra hợp lệ.
- Ngày không hợp lệ theo lịch (31/02, tháng 13, ngày 32) → `None` +
  issue `invalid_calendar_date`, không ép sang ngày gần nhất, không đổi
  ngày/tháng cho nhau lặng lẽ.
- Năm 2 chữ số bị từ chối (mơ hồ thế kỷ). Số serial ngày của Excel (số
  ngày từ 1899-12-30) không được parse ở đây: openpyxl với
  `data_only=True` đã trả về đối tượng `datetime`/`date` cho ô định dạng
  ngày, nên tầng này chỉ xử lý chuỗi và đối tượng ngày; nếu gặp số serial
  thô (do file xuất không kèm định dạng ngày) thì phải xử lý riêng theo
  từng sheet và ghi audit — không tự coi số đó là ngày.
- `CODE-TESTED-SYNTHETIC`: `31/12/2025` → `2025-12-31`,
  `31/02/2025` → issue, `2025-12-31` → giữ nguyên.

### 2.6. Những gì tiền xử lý KHÔNG làm (và vì sao)

- Không xóa cột trống, không xóa dòng trống một phần, không điền giá trị
  thiếu bằng trung bình/mode, không sửa chính tả tên sản phẩm, không
  chuẩn hóa tên doanh nghiệp: mọi thao tác đó đều là "đoán" và đều có
  thể biến một câu `unanswerable` (thiếu dữ liệu thật) thành một đáp án
  sai (−1).
- Không đọc công thức: openpyxl `data_only=True` đọc giá trị đã tính;
  file nào chỉ chứa công thức mà chưa từng được Excel tính sẽ đọc ra
  `None` và phải được gắn cờ ở tầng profiler, không tự tính lại công
  thức bằng Python (rủi ro sai khác với cách Excel tính).
- Không hỗ trợ `.xls` cũ: openpyxl chỉ đọc `.xlsx`/`.xlsm`. File `.xls`
  (nếu split nào có) cần chuyển đổi riêng trước khi vào pipeline, và
  việc chuyển đổi đó phải được ghi lại (ngày/giờ, công cụ, số dòng
  trước/sau).

## 3. Tích hợp lịch âm–dương: nạp `calendar.csv` vào DuckDB

### 3.1. `calendar.csv` là chuẩn, không phải thư viện âm lịch

Hàm `DuckDBStore.load_calendar()` yêu cầu file có đúng các cột
`solar_date`, `lunar_year`, `lunar_month`, `lunar_day` (có thể map tên
cột khác qua tham số `columns`, nhưng tên chuẩn sau map là cố định).
Thiếu cột → raise `ValueError`, không tự sinh lịch. Lý do:

- Lịch âm Việt Nam có quy tắc riêng (tháng nhuận, giờ/múi giờ lấy ngày
  sóc) và **không đồng nhất với lịch âm Trung Quốc** trong mọi năm. Dùng
  thư viện âm lịch Trung Quốc thay thế là sai nguồn gốc, có thể lệch
  ngày ở những năm có tháng nhuận khác nhau. Thư viện âm lịch chỉ được
  dùng làm fallback khi `calendar.csv` thiếu một khoảng ngày, và mọi
  ngày lấy từ fallback phải được gắn cờ trong audit (cột nguồn:
  `calendar.csv` hay `fallback_library`), không trộn lẫn lặng lẽ.
- `UNVERIFIED` quan trọng nhất ở đây: **ngữ nghĩa của cột `lunar_year`
  trong file của split**. Với ngày 23 tháng Chạp, `lunar_year` có thể là
  (a) năm âm lịch đang kết thúc (năm của tháng Chạp đó), hoặc (b) năm âm
  lịch của cái Tết sắp tới. Code mẫu chọn quy ước (a): Tết của năm Chạp
  Y là cửa sổ từ (Y, 12, 23) đến (Y+1, 1, 10). **Trước khi dùng cho câu
  hỏi thật, phải mở `calendar.csv` và đối chiếu 2–3 mốc Tết đã biết**
  (ví dụ Tết 2025 rơi vào 29/01/2025 dương): nếu dòng 29/01/2025 có
  `(lunar_year=2025, lunar_month=1, lunar_day=1)` thì quy ước (a) đúng
  cho nửa tháng Giêng, và dòng 23 Chạp trước đó phải có
  `lunar_year=2024` thì hàm `tet_window_sql(2024)` mới đúng. Nếu file
  dùng quy ước khác, tham số truyền vào hàm phải đổi theo — hàm không
  tự đoán quy ước.
- Tương tự, câu hỏi "doanh thu dịp Tết 2025" là mơ hồ theo hai nghĩa:
  Tết diễn ra trong năm dương 2025, hay Tết của năm âm lịch 2025. Tầng
  planner phải giải quyết mơ hồ này từ rulebook/README của split trước
  khi sinh SQL, không để LLM tự chọn một nghĩa rồi tính.

### 3.2. SQL cho cửa sổ Tết — vì sao phải là OR của hai nửa

```sql
WITH tet_dates AS (
    SELECT solar_date
    FROM calendar
    WHERE (lunar_year = ? AND lunar_month = 12 AND lunar_day >= 23)
       OR (lunar_year = ? AND lunar_month = 1 AND lunar_day <= 10)
)
SELECT SUM(l.line_amount_after_discount) AS tet_revenue
FROM orders o
JOIN tet_dates c ON o.order_date = c.solar_date
JOIN order_lines l ON l.order_id = o.order_id
WHERE l.line_status NOT IN ('cancelled', 'returned');
-- Tham số: [Y, Y+1] với Y là năm của tháng Chạp (theo quy ước §3.1).
```

Lỗi thường gặp nhất ở dạng câu hỏi này là chỉ lọc `lunar_year = Y` rồi
thêm `lunar_month IN (12, 1)`: điều kiện đó **mất toàn bộ nửa tháng
Giêng** (vì tháng Giêng đã sang năm âm lịch Y+1) hoặc, nếu viết
`(lunar_month = 12 AND lunar_day >= 23) OR (lunar_month = 1 AND
lunar_day <= 10)` mà không ràng buộc năm, sẽ lấy cả tháng Giêng của MỌI
năm trong dữ liệu. Cả hai đều là lỗi "chạy được nhưng sai" mà chỉ unit
test với calendar mẫu có đủ hai năm mới bắt được.

Hàm `tet_window_sql()` trong code đi kèm sinh đúng mẫu OR hai nửa này,
và tên bảng/cột đều là tham số (mặc định `orders`/`order_lines`/
`line_amount_after_discount`/`line_status`) — **phải khớp lại với
schema thật và quy tắc doanh thu của split** (tổng tiền dòng sau chiết
khấu dòng, loại dòng hủy/trả là quy tắc minh họa theo ghi nhận round
trước, không phải luật tự suy ra nếu rulebook của split khác).

### 3.3. Các câu hỏi âm lịch khác, cùng một mẫu join

| Câu hỏi | Điều kiện trên `calendar` | Ghi chú |
|---|---|---|
| Rằm tháng 7 | `lunar_month = 7 AND lunar_day = 15` | Hàm `lunar_day_sql(7, 15)`; không cần biết năm dương tương ứng vì join tự cho ra đúng ngày của từng năm có trong dữ liệu |
| Mùng 1 Tết | `lunar_month = 1 AND lunar_day = 1` | Nếu cần một Tết cụ thể, thêm `lunar_year = ?` — và xác nhận quy ước năm ở §3.1 trước |
| "Tháng Chạp" (cả tháng) | `lunar_month = 12` (kèm `lunar_year` nếu cần một năm) | Không thêm điều kiện ngày; tháng Chạp có thể có 29 hoặc 30 ngày — đừng hard-code 30 |
| "Trong tháng Giêng" | `lunar_month = 1` | Tương tự; đừng giả định tháng Giêng trùng với tháng 1 dương |
| Ngày âm → dương ngược lại | `SELECT solar_date FROM calendar WHERE lunar_year=? AND lunar_month=? AND lunar_day=?` | Nếu tháng đó là tháng nhuận, `calendar.csv` phải có cách phân biệt tháng nhuận (cột riêng hoặc quy ước tên); nếu file không phân biệt được thì câu hỏi đó là `UNVERIFIED`, không tự chọn tháng thường/tháng nhuận |

**Kiểm chứng bắt buộc trước khi tin calendar join:** tỉ lệ ngày trong
bảng đơn hàng tìm thấy trong `calendar` (coverage). Ngày nào không có
trong calendar thì không được bỏ lặng lẽ khỏi tổng (bỏ lặng lẽ = doanh
thu thiếu = đáp án sai); nó phải thành issue: hoặc calendar thiếu khoảng
ngày đó (lỗi dữ liệu, cần fallback có gắn cờ), hoặc ngày đơn hàng sai
định dạng (lỗi tiền xử lý, quay lại §2.5).

## 4. Pipeline vận hành đề xuất (từ file thô đến đáp án)

1. **Profiler (không LLM):** liệt kê mọi sheet/bảng, số dòng/cột, kiểu
   suy ra, tỉ lệ null, min/max ngày, mẫu giá trị cho mỗi cột số/ngày,
   danh sách merged ranges, số cấp header. Snapshot profiler này là
   "schema + dữ liệu mẫu" duy nhất mà LLM được nhìn — không đưa toàn bộ
   300k dòng vào prompt (vượt context, tốn thời gian, và LLM không cần
   toàn bộ dữ liệu để viết SQL đúng).
2. **Tiền xử lý Excel bẩn (§2) → view sạch**, giữ `header_mapping` +
   danh sách issue cho audit. Locale số theo cột được khóa ở bước này.
3. **Đăng ký view thống nhất vào DuckDB** (`DuckDBStore`): mỗi bảng
   nguồn một view, tên view khớp với tên mà LLM thấy trong profiler.
   Không đổi tên bảng giữa profiler và execution — lệch tên là lỗi phổ
   biến nhất của text-to-SQL và hoàn toàn tránh được bằng một map tên
   duy nhất.
4. **LLM sinh 1 câu SQL SELECT/WITH + tham số.** Validator trước thực
   thi: câu phải bắt đầu bằng SELECT/WITH (chặn INSERT/UPDATE/DELETE/
   DROP...), mọi bảng/cột trong câu phải tồn tại trong view đã đăng ký,
   mọi hằng ngày phải ở dạng ISO. Validator này là code, không phải
   prompt — prompt có thể bị LLM bỏ qua, code thì không.
5. **Thực thi qua DuckDB, kiểm chứng:** phân biệt 3 trạng thái như
   ReFoRCE (thành công / lỗi / rỗng) — rỗng không đồng nghĩa với đáp án
   0 hay `unanswerable`; rỗng vì filter quá chặt khác với rỗng vì dữ
   liệu trống thật, và chỉ profiler + rulebook mới phân biệt được.
6. **Formatter theo type** (số, phần trăm, chuỗi, ngày, boolean, list,
   table) với quy tắc làm tròn lấy từ cấu hình split (xem §1.4), không
   hard-code trong prompt.
7. **Quyết định cuối:** đủ dữ liệu + tính toán chắc → trả lời; thiếu
   bảng/cột/rule theo schema linking → `unanswerable`; dữ liệu đủ nhưng
   tính toán không chắc (xem chuyên đề 4 về abstain) → `abstain`. Ba
   quyết định này là ba nhánh khác nhau, không gộp thành một ngưỡng duy
   nhất.

## 5. Thí nghiệm nhỏ nhất để biết kiến trúc này có đáng theo tiếp

Tất cả đo trên **train held-out tách theo business** (không đo PA trên
public test — public test không có gold local theo ghi nhận portal
2026-10-26; xác nhận lại bằng cách giải nén và liệt kê file thật trước
khi viết code đo). Mỗi thí nghiệm có bảng tay tính trước đáp án đúng:

| ID | Thí nghiệm | Đo | Tiêu chí giữ/dừng (ĐỀ XUẤT, không phải kết luận) |
|---|---|---|---|
| T1 | Fan-trap unit test: bảng orders/lines tay 3–5 dòng, đáp án tính tay | Đúng/sai từng pattern join | Phải đúng 100% trước khi đo PA; sai 1 pattern thì dừng, sửa quy tắc grain |
| T2 | Calendar join coverage + Tết 2 nửa | % ngày đơn hàng có trong calendar; doanh thu Tết mẫu so với tính tay | Coverage < 100% thì dừng, xử lý ngày thiếu trước (không bỏ lặng lẽ) |
| T3 | Ambiguity audit: tỉ lệ ô số/ngày bị gắn cờ trên train | % ô mơ hồ theo cột, và sau khi khóa locale theo cột thì còn bao nhiêu | Nếu một cột vẫn > 5% mơ hồ sau khi khóa locale thì cột đó cần quy tắc riêng từ rulebook, không đoán chung |
| T4 | SQL-only vs SQL + Python cross-check độc lập | PA, giây/câu, tỉ lệ mâu thuẫn và trong ca mâu thuẫn bên nào đúng nhiều hơn | Chỉ giữ cross-check nếu PA tăng mà thời gian vẫn trong ngân sách ngoại suy 6 giờ |
| T5 | So sánh engine ở tầng kiểm chứng (pandas vs polars) | Giây/câu ở tầng kiểm chứng (không tính LLM) | Chỉ đổi engine khi chênh lệch có ý nghĩa trên cùng held-out và cùng máy đo |

## 6. Rủi ro và những điều KHÔNG làm

- **Không dùng DuckDB sqlite extension trong Docker offline:** extension
  cần tải về lần đầu; thay bằng `sqlite3` stdlib + `register` (code đã
  làm vậy). Tương tự, không dùng `read_xlsx` qua extension chưa có sẵn
  trong image — Excel đi qua openpyxl.
- **Không để LLM sinh code Python thay đổi dữ liệu ở luồng chính:** code
  Python sinh ra khó kiểm chứng exhaustively, và một câu lệnh ghi/xóa
  vô tình trong code sinh ra là rủi ro lớn hơn mọi lợi ích linh hoạt của
  nó.
- **Không chuyển float làm tròn thành đáp án tiền tệ** (§1.4).
- **Không dùng lịch Trung Quốc, không dùng thư viện âm lịch làm chuẩn**
  (§3.1).
- **Không đoán locale số theo từng ô** (§2.4): locale khóa theo cột, ô
  mơ hồ còn lại thành issue.
- **Không tin profiler của một split cho split khác:** mỗi split có
  rulebook riêng, header riêng, và có thể có loại hình doanh nghiệp mới
  — profiler và helper phải chạy lại cho từng split, không copy kết quả
  từ split này sang split khác.

## 7. Code đi kèm và kết quả chạy thử (dữ liệu tổng hợp, KHÔNG phải ZAIC)

File [03-duckdb-excel-datamate.py](03-duckdb-excel-datamate.py) gồm:
`parse_vn_number` (+ `parse_number_column`), `parse_vn_date` (+
`parse_date_column`), `flatten_headers`, `read_excel_sheet`
(merged/header/dòng trống/guard cột ID), `DuckDBStore`
(`register_frame`, `load_sqlite` bằng stdlib, `load_calendar` có kiểm
tra cột), `tet_window_sql`, `lunar_day_sql`, và hàm `_demo()`.

Kết quả chạy thật trong phiên này (venv thử: DuckDB 2.0.0, pandas
3.1.0, openpyxl 3.1.5; dữ liệu tổng hợp tự tạo):

- Số: `1.000.000,50` → 1000000.5; `1,000,000.50` → 1000000.5;
  `1.000.000` → 1000000.0; `1,5` → 1.5; `1.500` ở chế độ auto →
  `None` + issue mơ hồ; `1.500` với `locale="vn"` → 1500.0, với
  `locale="en"` → 1.5; `(1.000.000,50)` → −1000000.5; `50%` → issue
  không chuyển đổi.
- Ngày: `31/12/2025` → `2025-12-31`; `31/02/2025` → issue ngày không
  hợp lệ; `2025-12-31` giữ nguyên.
- Excel tổng hợp (header 2 cấp + nhóm hàng gộp 2 dòng + số/ngày VN):
  đọc ra đúng 2 dòng, nhóm hàng được điền trong vùng merge, mapping
  `Doanh_thu_Da_tru_CK = "Doanh thu | Đã trừ CK"`, ép số VN và ngày đều
  không còn issue.
- Guard cột ID: cột "Mã đơn" gộp 2 dòng KHÔNG bị điền, đúng 1 issue
  `merged_id_not_filled` (đã sửa lỗi trùng issue theo từng ô trong
  vùng).
- Demo DuckDB: doanh thu cửa sổ Tết (năm Chạp 2024, dữ liệu mẫu) =
  300.0 (2 đơn trong cửa sổ, 1 đơn ngày 11 tháng Giêng bị loại đúng);
  đơn ngày rằm tháng 7 tìm được đúng 1 đơn.
- `py_compile` pass. Chưa chạy trên dữ liệu ZAIC thật; chưa đo hiệu
  năng trên 300k dòng thật; chưa đo trên máy chấm 2× RTX 5090.

## 8. Nguồn

| # | Nguồn | Ngày truy cập | Trạng thái |
|---|---|---|---|
| S1 | DuckDB Python API docs — https://duckdb.org/docs/2.0/clients/python/reference/ (kèm trang tổng quan https://41a8e9e3.duckdb-web.pages.dev/docs/stable/clients/python/overview) | 2026-10-27 | `SECONDARY` (đọc qua kết quả tìm kiếm, chưa mở trực tiếp toàn văn): API `register`/`read_csv`/`read_parquet`, Python ≥ 3.9; snippet trang tổng quan ghi "latest stable 1.4.2" — lưu ý venv thử ngày 2026-10-27 cài được DuckDB 2.0.0, nên số phiên bản "mới nhất" phải kiểm tra lại lúc build, không tin snippet cũ |
| S2 | DuckDB vs pandas — bài blog so sánh (https://dev.to/veilanalytics/duckdb-vs-pandas-why-your-analytics-script-runs-10x-faster-after-one-switch-1hhh, https://dev.to/0012303/duckdb-just-made-sqlite-look-slow-run-analytics-on-csvs-without-a-database-5hie, https://www.thinkdifferent.blog/blog/the-successor-to-python-pandas-why-polars-duckdb-and-modern-alternatives-are-reshaping-data-analysis/) | 2026-10-27 | `SECONDARY`, chỉ dùng cho hướng kiến trúc (columnar/vectorized, Arrow zero-copy khi query DataFrame). Mọi con số "X lần" trong các bài này KHÔNG được trích làm bằng chứng trong tài liệu này vì khác máy/dữ liệu/phiên bản |
| S3 | openpyxl merged cells — https://www.silicloud.com/blog/how-can-python-read-and-merge-data-from-cells/ và https://iditect.com/program-example/read-merged-cells-in-excel-with-python.html | 2026-10-27 | `SECONDARY`: chỉ ô góc trên-trái giữ giá trị, `ws.merged_cells.ranges` cho bounds. Metadata gói trong venv thử: openpyxl 3.1.5, MIT |
| S4 | Polars/pandas/DuckDB licences — https://deepnote.com/blog/ultimate-guide-to-the-polars-library-in-python (tổng hợp: polars MIT, pandas BSD-3, DuckDB MIT) | 2026-10-27 | `SECONDARY`: chưa đối chiếu file LICENSE gốc của từng dự án trong phiên này; kiểm tra lại LICENSE khi đóng Docker. Metadata gói trong venv thử: openpyxl MIT (xác nhận), DuckDB/pandas không có trường License trong metadata (None) nên không kết luận từ đó |
| S5 | Quy tắc DataMate, rulebook, calendar.csv, giới hạn 15B/6 giờ/2× RTX 5090 | — | Theo đề bài được giao + ghi chú round trước (portal 2026-10-26); evaluator/rulebook của đúng split vẫn `UNVERIFIED` cho tới khi đọc file thật trong gói dữ liệu |

## 9. Đã xác minh / giả định / cần đo / câu hỏi evaluator còn mở

- **Đã xác minh (trong phạm vi bản nháp):** cơ chế merged cells của
  openpyxl (chỉ ô góc trên-trái giữ giá trị); quy tắc phân biệt số VN
  mơ hồ `1.500` và lý do phải gắn cờ thay vì đoán; mẫu SQL cửa sổ Tết
  OR hai nửa và lỗi mất nửa tháng Giêng nếu chỉ lọc một năm; code đã
  chạy thử trên dữ liệu tổng hợp với kết quả ở §7.
- **Giả định:** quy tắc doanh thu minh họa (tổng tiền dòng sau chiết
  khấu dòng, loại dòng hủy/trả) khớp với rulebook của split; quy ước
  `lunar_year` (a) cho cửa sổ Tết; locale số khóa theo cột là đủ; nút
  thắt nằm ở LLM sinh code chứ không phải engine ở 300k dòng.
- **Cần đo trên dữ liệu/phần cứng ZAIC thật:** hiệu năng DuckDB trên
  business lớn nhất (~300k dòng) và ngân sách 6 giờ; coverage của
  calendar join trên dữ liệu thật; tỉ lệ ô mơ hồ sau khi khóa locale
  theo cột; PA của SQL-only so với SQL + cross-check độc lập trên
  train held-out tách theo business.
- **Câu hỏi evaluator còn mở:** ngữ nghĩa `lunar_year` và cách phân
  biệt tháng nhuận trong `calendar.csv`; quy tắc làm tròn, format phần
  trăm (0–100 hay 0–1), thứ tự list, "rows as set" cho table; ngày
  commit đầu tiên của Qwen2.5-Coder-7B-Instruct và cách BTC tính tổng
  tham số; xem danh sách đầy đủ Q-D1..Q-D6 trong
  [../gaps.md](../gaps.md). Không gửi câu hỏi cho ban tổ chức trong đợt
  này.

---

## Cập nhật đợt 3 (2026-10-27) — sửa code, đã kiểm chứng bằng test

Các thay đổi trong `03-duckdb-excel-datamate.py`:

- **Dấu âm không còn mất.** Nhánh số nguyên thuần cuối hàm
  `parse_vn_number()` trước đây trả `float(text)` mà quên áp dấu âm,
  nên `-100` và `(100)` đều thành `+100.0`. Giờ trả đúng `-100.0`;
  `(1.000,50)` → `-1000.5`.
- **Số nguyên thuần ở locale vn/en.** Regex locale trước đây bắt đầu
  bằng `\d{1,3}` nên từ chối cả `1000`. Giờ `\d+` ở đầu cho phép số
  nguyên bất kỳ độ dài nào, vẫn từ chối `1.5` ở locale vn (không phải
  dạng VN hợp lệ).
- **Tiền tách khỏi float.** Thêm `parse_vn_money()` trả `Decimal` với
  cùng quy tắc dấu/phân cách; `parse_vn_number()` (float) chỉ còn cho
  số lượng thông thường. Caller nào đổi Decimal sang float trước khi
  format đáp án là phá contract, không phải lỗi parser. Demo cũ dùng
  float cho tiền chỉ để gọn — từ đợt này demo và code phân biệt rõ.
- **Query chỉ-đọc được thực thi.** `DuckDBStore.query()` giờ gọi
  `_assert_readonly_sql()`: một statement duy nhất bắt đầu SELECT/
  WITH (sau khi bỏ comment), cấm từ khóa ghi và hàm đọc file
  (`read_csv`, `read_parquet`, …). Phiên bản trước chỉ ghi "chỉ cho
  phép SELECT/WITH" trong docstring mà không chặn gì. Ghi rõ giới hạn:
  đây là guard cú pháp, KHÔNG phải sandbox OS — SQL do model sinh vẫn
  cần chạy trong process riêng với filesystem giới hạn nếu coi là
  không tin cậy.
- **SQL Tết loại ở mức đơn hàng.** `tet_window_sql()` trước đây chỉ
  lọc dòng `line_status NOT IN ('cancelled', 'returned')`. Theo diễn
  giải rulebook "đơn bị hủy / đơn có hàng trả", một đơn có bất kỳ dòng
  trả nào thì toàn bộ đơn bị loại (thêm `NOT EXISTS` cho dòng
  cancelled/returned cùng đơn). Đây là DIỄN GIẢI, chưa đối chiếu nguyên
  văn rulebook của đúng split — nếu rulebook thật chỉ loại theo dòng
  thì bỏ mệnh đề `NOT EXISTS` và ghi lại lý do. Test đã chạy: đơn có
  dòng ok 100 + dòng returned 50 và đơn ok 200 → doanh thu 200 (đơn
  thứ nhất đóng góp 0).
- **Calendar dayfirst.** `load_calendar()` giờ parse `solar_date`
  với `dayfirst=True`, để chuỗi `05/02/2025` không bị đọc lầm thành
  05 tháng 2 hay 02 tháng 5 theo mặc định mơ hồ của pandas; chuỗi ISO
  không bị ảnh hưởng.
- **Liên hệ đợt research 3:** kiến trúc chốt đầu tiên là B-trimmed
  (A đo trước → shortlist + fallback → sửa có điều kiện kiểu ReFoRCE),
  BASE-SQL bị xóa khỏi danh sách code cần đọc (repo trống), DABstep
  baseline đã đọc thật, và trigger sửa phải loại trừ đáp án rỗng đã
  kiểm chứng — xem `../research/round3-p3-datamate-complete-solutions.md`
  và `research-updates-2026-10-27.md` §3. Code hiện tại chưa triển
  khai pipeline B-trimmed đầy đủ; đó là bước tiếp theo sau khi đo A.
