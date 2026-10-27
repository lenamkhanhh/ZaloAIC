# Empty-vs-ask — cặp đối chiếu trên dev, không biến ID thành luật

> Chỉ dùng dev (1.237 mẫu), không chạy model. Phương pháp: đếm gold
> theo (số kết quả search, bước tiếp theo), theo (tool_name, params)
> của ask, và replay chẩn đoán (search thật, installed_apps thật)
> cho các mẫu mâu thuẫn. Quy tắc dưới đây phát biểu trên các điều
> kiện chung (app có cài không, history đã giải quyết chưa, số
> candidate, param có mặt không) — ID mẫu chỉ là trích dẫn bằng
> chứng, không phải luật.

## 1. Search trùng tên: 1 kết quả → làm luôn; nhiều kết quả → hỏi, TRỪ khi có yếu tố phân biệt

Đếm trên toàn bộ dev với `contacts.search` trong gold (replay để
lấy số kết quả thật):

- **1 kết quả → gold làm tiếp luôn: 104/104 (100%).** Không có
  ngoại lệ. Ví dụ: train_0003 search "Bác Ba" → 1 kết quả → topup
  thẳng vào số đó; search "Cô giáo Mai" → 1 kết quả → transfer
  thẳng cho c_06.
- **Nhiều kết quả + không có yếu tố phân biệt → gold hỏi id.**
  Ở n=2: hỏi 54, làm tiếp chỉ 4 (xem §2). Ví dụ hỏi: train_0025
  search "Minh" → 2 kết quả → `ask phone.call [contact_id]`;
  train_0069 search "Hương" → 2 kết quả (một "bạn", một "khách
  hàng") → `ask sms.send [contact_id]` — dù nội dung tin nhắn
  ("nhớ mang hộ cái sạc") mang tính cá nhân, gold vẫn hỏi, tức
  relation/nội dung KHÔNG được tính là yếu tố phân biệt ở đây.
- **Nhiều kết quả + transcript/history có yếu tố phân biệt → gold
  làm tiếp với candidate khớp.** Cả 4 trường hợp n=2 làm tiếp đều
  thuộc loại này:
  - train_0509: "anh Quân bên kho" → c_01 có relation
    "bộ phận kho" (đối thủ là "bạn đại học").
  - train_0751: "chị Mai bên hậu cần" → c_04 có relation
    "phụ trách hậu cần" (đối thủ là "Mai Anh", tên khác).
  - train_0776: "nhóm nhà cung cấp Minh Hà" → c_01 có relation
    "nhà cung cấp vật tư" (đối thủ là "bạn học cũ").
  - train_1015: query "Mạ" trả về "Cô giáo Mai" (fuzzy) và "Mạ"
    (relation "mẹ") → gold gọi c_363, tức **khớp tên chính xác
    thắng khớp fuzzy**.
- Các search không có query (trả về toàn bộ danh sách, ví dụ
  train_0462/0503/0534/0570) là chức năng khác (liệt kê, không
  phải phân biệt tên) nên không tính vào quy tắc này.

**Quy tắc 1 (đã tinh chỉnh):** candidate = 1 → làm luôn; candidate
> 1 → hỏi id, TRỪ khi transcript/history chứa đúng một yếu tố
phân biệt khớp với đúng một candidate (chức danh/nhóm/relation,
hoặc khớp tên chính xác). "Trùng tên → hỏi" dạng thô là SAI nếu
không có vế trừ này.

## 2. Thiếu tham số: có app + thiếu thật → hỏi đúng tham số đó; có tham số → làm luôn

Top (tool_name, params) của ask trong dev: `phone.call
[contact_id]` 34, `sms.send [contact_id]` 24, `ewallet.transfer
[amount]` 14, `reminders.create [time]` 7, rồi các cặp khác mỗi
loại ≤ 4. Ask luôn ghi đúng tên tham số thiếu, không hỏi chung
chung — và ask luôn ở cuối gold (174/174 trong dev).

- **Thiếu giờ → hỏi giờ:** train_0116 "nhắc tôi gọi điện cho mẹ"
  (không có giờ) → `ask reminders.create [time]`.
- **Đối chiếu, có giờ → làm luôn:** train_0027 "ra sân bay lúc 8
  giờ kém 15 tối mai" → `reminders.create` với time đầy đủ;
  train_0011/0046 "tám giờ tối nay" → làm luôn.
- **Thiếu số tiền → hỏi số tiền:** train_0143 "chuyển ví cho anh
  Tuấn chút tiền" (không nêu số) → `ask ewallet.transfer
  [amount]`. Đối chiếu: khi transcript nêu số hoặc số lấy được
  từ bill (train_0003: 845.000 từ bill điện) thì làm luôn, không
  hỏi.

**Quy tắc 2:** tham số bắt buộc vắng mặt khỏi transcript + history
+ kết quả read, và không có default trong schema → hỏi đúng tham
số đó, và chỉ tham số đó. Có tham số (nêu trực tiếp hoặc suy ra
hợp lệ từ read) → không hỏi.

## 3. Empty có 5 nhóm — và ask không bao giờ là đáp án cho 3 nhóm đầu

### 3a. Người dùng hủy yêu cầu duy nhất → empty, không hỏi, không gọi
train_0036 ("tắt đèn phòng làm việc đi à thôi khỏi"), train_0155,
train_0432 ("thôi, khỏi tạo ghi chú"), train_0446, train_0606,
train_0686 ("đừng thêm gì vào danh sách đi chợ nữa"), train_1280
("à thôi khỏi, sáng mai ra chợ mình tự check"). Dấu hiệu: mệnh đề
hủy ("thôi/khoan/khỏi/đừng") phủ toàn bộ yêu cầu trước đó trong
cùng turn. Chú ý phân biệt: "không mưa thì thôi" (train_0082) là
nhánh điều kiện, không phải hủy yêu cầu — xem §3d.

### 3b. App/capability cần thiết không được cài → empty, KHÔNG hỏi
- train_0019 đặt khách sạn Đà Lạt: installed chỉ có
  alarm/smart_home/weather — không có app khách sạn nào trong
  catalog.
- train_0863 bật camera nhận diện người trước cửa: installed
  không có camera/nhận diện.
- train_0530 chuyển 350.000 cho Mai: installed không có
  contacts/ewallet/banking (chỉ notes/calendar/email/tasks/
  reminders) — chẩn đoán bằng search thật trả về lỗi "tool không
  thuộc app đã cài".
- train_1242 hủy nhắc 2h + đặt nhắc 4h: installed không có
  reminders — chẩn đoán `reminders.list` trả về lỗi tương tự.
**Quy tắc 3:** hỏi chỉ có nghĩa khi người dùng CÓ THỂ cung cấp thứ
còn thiếu. App không cài thì hỏi cũng không thay đổi được kết quả
→ empty, không ask.

### 3c. Tán gẫu / báo cáo việc đã xong → empty
train_0445, train_0797 (tán gẫu); train_1351 ("sáng nay anh gọi
Harbor View Hotel rồi, bên đấy xác nhận phòng rồi") — báo cáo
việc đã xong, không yêu cầu hành động mới.

### 3d. Điều kiện đã được history giải quyết → empty, KHÔNG đọc lại, KHÔNG hỏi
Đây là nhóm dễ bị chấm sai nhất nếu chỉ nhìn transcript:

| Mẫu | Điều kiện trong transcript | Bằng chứng đã có trong history | Gold |
|---|---|---|---|
| train_0082 | "mai mưa thì đẩy lịch… không mưa thì thôi" | Forecast ngày mai "có mây, rain: False" | empty, 0 call |
| train_0378 | Như trên (chạy bộ, SMS Minh) | Forecast Đà Nẵng "có mây, rain: false" | empty |
| train_0266 | Như trên (đá bóng, SMS Tuấn) | Forecast TP.HCM "nhiều mây, rain: false" | empty |
| train_1446 | "nếu chưa đặt buổi đó thì đặt" | History: buổi Tiếng Anh giao tiếp 8h thứ Sáu đã đặt | empty |
| train_1367 | "nếu số dư ví dưới 200k thì thôi" | History: số dư ví còn 150.000 (< 200.000) | empty |
| train_1494 | "nếu chiều nay anh phải đón Bống thì…" | Hai tầng: tin nhắn vợ "mưa thì anh đón, không mưa chị tự đón" + forecast Hà Nội "nhiều mây, rain: false" | empty |

**Đối chiếu trực tiếp:** cùng mẫu câu điều kiện nhưng history
KHÔNG có forecast → gold BẮT BUỘC gọi forecast trước rồi mới
quyết định: train_0025 (forecast → hủy lịch → search → ask),
train_0016 (forecast → dời lịch +2h → SMS). Vậy quy tắc không
phải "gặp điều kiện thì đọc forecast", mà là "điều kiện đã có đáp
án trong history thì dùng đáp án đó; chưa có thì mới đọc".

### 3e. Ngoại lệ/mâu thuẫn label — ghi rõ, không làm tròn
- Sau khi tách search không query ra, quy tắc trùng tên ở §1
  không còn ngoại lệ chưa giải thích trong dev (4/4 trường hợp
  n=2 làm tiếp đều có yếu tố phân biệt). Nếu gặp mẫu mới mà
  candidate > 1, không có yếu tố phân biệt, nhưng gold làm tiếp
  thì đó là mâu thuẫn cần báo cáo, không phải cớ để bỏ quy tắc.
- train_1696 (gold anomaly, xem `analysis/README.md`): gold chứa
  call lỗi tới id không tồn tại — không thuộc quy tắc empty/ask,
  không dùng làm bằng chứng cho bất kỳ quy tắc nào.
- Ranh giới "yếu tố phân biệt" vẫn mở: gold coi relation/chức
  danh/nhóm/khớp tên chính xác là đủ, nhưng coi nội dung tin nhắn
  (train_0069) là chưa đủ. Đừng mở rộng "yếu tố phân biệt" sang
  suy đoán ý định từ nội dung nếu chưa có bằng chứng gold.

## 4. Quy tắc tổng quát đề xuất (thứ tự quyết định)

1. Có yêu cầu hành động không? Không (tán gẫu/báo cáo) → empty.
2. Người dùng hủy yêu cầu duy nhất? → empty.
3. App/tool cần thiết có được cài không? Không → empty (không ask).
4. Yêu cầu có điều kiện không? Nếu history đã trả lời điều kiện
   → đi theo nhánh đã quyết (nhánh false → empty; nhánh true →
   làm tiếp). Chưa có đáp án → đọc để trả lời điều kiện trước.
5. Lấy candidate qua read: đúng 1 → làm luôn; > 1 và không phân
   biệt được → ask đúng id; > 1 nhưng có yếu tố phân biệt khớp
   đúng một candidate → làm với candidate đó.
6. Tham số bắt buộc còn thiếu (không có trong transcript/history/
   read, không có default) → ask đúng tham số đó, và chỉ tham số
   đó, ở cuối turn.
7. Không bao giờ ask cho thứ người dùng không thể cung cấp để đổi
   kết quả (app không cài, thực thể đã chứng minh là không tồn
   tại) — đó là empty, không phải ask.
