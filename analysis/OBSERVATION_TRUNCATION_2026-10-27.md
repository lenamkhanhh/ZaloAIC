# Mất thông tin trong observation — replay gold 26 probe với repr[:300]

> Chỉ dùng dev, không chạy model, không sửa code inference. Phương
> pháp: replay gold của 26 probe qua `ZaicEnv` (diagnostic, như
> `replay-gold`), lấy `repr(tool_result)` của mỗi read và kiểm tra
> vị trí xuất hiện đầu tiên của từng giá trị mà call sau dùng tới.
> Giả định: prompt giữ lại observation của MỌI call trước, mỗi cái
> cắt ở 300 ký tự (đúng mô tả code Codex). Biến thể prompt chỉ giữ
> observation mới nhất được tính riêng ở §4.

## 1. Tổng quan: cắt thì nhiều, mất thật thì ít — nhưng mất ở chỗ hiểm

- 26 probe có 29 read trong gold; **14/29 read có `repr` dài hơn
  300 ký tự** (48%), dài nhất là `smart_home.get_status` không lọc:
  1.304 ký tự (train_0004) và 1.305 (train_0069).
- Nhưng chỉ **3 giá trị** cần cho bước sau vừa (a) không xuất hiện
  trong 300 ký tự đầu của BẤT KỲ observation nào trước đó, vừa (b)
  không có fallback trong transcript hay history. Ba giá trị này là
  mất thông tin thật, không phải "chưa thấy ở observation này".

## 2. Bảng: mẫu → read liên quan → thông tin bị cắt → history có cứu không

| Mẫu | Read liên quan (độ dài repr) | Giá trị cần cho bước sau (vị trí) | Bước sau dùng nó | Transcript/history có lại không? |
|---|---|---|---|---|
| train_0003 | `bill_payment.list_bills` (505) | amount **845.000** (ký tự 455) | `ewallet.transfer` amount | **KHÔNG.** Transcript chỉ nói "số tiền điện tháng này", không nêu số; history không có. |
| train_0004 | `smart_home.get_status` không lọc (1.304) | device_id **light_bedroom2** (ký tự 1.158) | `light_set` device_id | **KHÔNG.** Transcript có tên "đèn phòng ngủ nhỏ", không có id; history không có. |
| train_0069 | `smart_home.get_status` không lọc (1.305) | device_id **light_bedroom2** (ký tự 1.160) | `light_set` device_id | **KHÔNG.** Như trên; history không có. |

### Agent thấy gì thay vì giá trị thật (300 ký tự đầu)
- train_0003: thấy bill phone 194.000, internet 221.000 và đầu bill
  nước — nhưng KHÔNG thấy bill điện 845.000 (bill thứ 4). Lỗi dễ
  gặp: chuyển nhầm 221.000 (số tiền mạng, cũng xuất hiện trong mẫu
  khác) hoặc đoán amount → mất hash.
- train_0004 / train_0069: thấy đèn phòng khách (`light_living`),
  điều hoà phòng khách… nhưng KHÔNG thấy đèn phòng ngủ nhỏ. Lỗi dễ
  gặp: chọn `light_bedroom` (phòng ngủ chung) thay vì
  `light_bedroom2`, hoặc đoán id → mất hash.
- Cả 3 đều là list-type read mà item cần nằm cuối danh sách. Đây
  là dạng mất thông tin có hệ thống, không phải ngẫu nhiên: thứ tự
  danh sách của môi trường quyết định item nào sống sót sau [:300].

## 3. Phân biệt "không thấy trong observation này" với "không có bằng chứng ở đâu"

- **Không thấy trong observation này, nhưng có bằng chứng ở nơi
  khác:** 11/14 read dài vẫn không gây mất mát, vì giá trị cần hoặc
  nằm trong 300 ký tự đầu của một observation khác, hoặc đã có
  trong transcript/history. Ví dụ: train_0049 có 2 read dài
  (385 ký tự) nhưng `acc_02` và 221.000 vẫn nằm trong 300 ký tự đầu
  của observation tương ứng — cắt không chạm tới chúng.
- **Không có bằng chứng ở bất kỳ đâu trong prompt:** đúng 3 giá trị
  ở §2. Với 3 giá trị này, model KHÔNG THỂ suy ra đáp án đúng từ
  prompt — mọi output đều là đoán. Đây là lỗi của observation
  builder, không phải lỗi suy luận của model, và không được chấm
  như "model kém".
- **Giá trị không nằm trong bất kỳ read nào:** trường hợp riêng
  train_1696 (gold anomaly): `chat_6142` không có trong kết quả
  `list_chats` — không phải do cắt, mà do gold chứa id không tồn
  tại. Xem quy ước anomaly trong `analysis/README.md`; không
  hardcode id này.

## 4. Biến thể: nếu prompt chỉ giữ observation MỚI NHẤT thì mất nhiều hơn

Nếu Codex không tích lũy observation mà chỉ giữ cái mới nhất, thì
trong 22 giá trị phụ thuộc observation (không có fallback transcript
/ history), **6 giá trị bị mất** vì read nguồn không phải là call
ngay trước đó:

| Mẫu | Giá trị | Read nguồn (cách bước sau bao nhiêu call) |
|---|---|---|
| train_0003 | 845.000 | `list_bills` (cách 3 call: search, search rồi mới transfer) |
| train_0011 | bill_03 | `list_bills` (không phải call kề trước) |
| train_0049 | acc_02 | `get_balance` (cách 2 call) |
| train_0049 | 221.000 | `list_bills` (cách 3 call) |
| train_0079 | bill_03 | `list_bills` (không phải call kề trước) |
| train_0092 | rest_01 | `list_restaurants` (không phải call kề trước) |

Codex cần xác nhận chính sách giữ observation thực tế của mình:
tích lũy tất cả (→ mất 3 giá trị) hay chỉ mới nhất (→ mất 6 giá
trị). Dù trường hợp nào, §5 cũng sửa được cả hai.

## 5. Đề xuất giữ thông tin theo schema (không chọn dữ liệu theo đáp án gold)

Nguyên tắc: mọi quyết định giữ/cắt đều dựa trên **schema của kết
quả** (loại field, loại tool), không dựa trên việc giá trị đó có
phải đáp án gold hay không.

1. **Không cắt giữa giá trị.** Render observation theo schema thay
   vì `repr(...)[:300]`: giữ nguyên mọi field id và scalar quan
   trọng (id, amount, balance, time, enum); với list thì liệt kê
   cặp (id, tên hiển thị) của từng item + tổng số; chỉ cắt các
   field free-text (content/body/subject — đúng nhóm FREE_TEXT_KEYS
   của canon hash) và cắt ở cuối, kèm dấu "…đã cắt".
2. **Đọc lại có lọc, với filter lấy từ lời người dùng.** Khi list
   bị cắt, agent đọc lại hẹp hơn bằng filter mà transcript đã cho:
   `get_status` lọc theo phòng ("phòng ngủ nhỏ"),
   `list_bills` lọc theo loại ("điện"). Filter lấy từ transcript,
   không lấy từ gold — đây là cách dùng đúng theo thiết kế catalog
   (catalog ghi rõ get_status không lọc sẽ trả cả danh sách).
3. **Sổ đăng ký id (id registry) xuyên suốt các bước.** Mọi id từng
   xuất hiện trong observation đều giữ lại được tra cứu (id →
   tool, tên hiển thị) cho tới hết turn; observation mới không được
   xóa id của observation cũ. Sổ này sửa cả biến thể latest-only
   ở §4.
4. **Đánh dấu cắt rõ ràng trong prompt.** Nếu observation vẫn bị
   cắt, ghi rõ "observation đã cắt ở 300 ký tự, còn N ký tự chưa
   hiện" để model phân biệt "không thấy" với "không tồn tại" — và
   khi đó hành vi đúng là đọc lại có lọc (mục 2), không phải đoán.
5. **Không làm:** không tăng cap mù lên 2.000 (chỉ dời ngưỡng vỡ,
   prompt phình theo số bước); không chọn item theo đáp án gold;
   không hardcode id (train_1696).
