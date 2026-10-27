# Phân tích trong lúc chờ Codex (2026-10-27, chỉ đọc data — không sửa code/repo)

Mục đích: kiểm chứng các claim của bộ probe ZAIC2 bằng label thật, và
chuẩn bị bảng kỳ vọng chẩn đoán cho lúc trace model về. File trace
gold chi tiết: `probe_gold_traces.json` (cùng thư mục). Lưu ý như
ZAIC2: đây là tài liệu chẩn đoán, KHÔNG phải đáp án để hard-code
vào agent.

## 1. Các claim của ZAIC2 — đều đúng khi kiểm bằng label thật

- 26/26 probe đều thuộc 1.237 mẫu dev (split file id → dev/heldout).
- `done=false` duy nhất trong dev: đúng chỉ 1 mẫu — **train_1696**,
  call `chat_ott.send_message` (xem §2).
- `sys.ask_missing_info` luôn ở cuối gold trong dev: 0 trường hợp ask
  không ở vị trí cuối (174 ask trong dev).

## 2. Hai mẫu cần đọc kỹ trước khi chấm trace — gold không phải lúc nào cũng "hành vi lý tưởng"

### train_1696 — gold chứa luôn cả call thất bại
Transcript: tiền Northwind chuyển sáng nay → gửi tiết kiệm 6 tháng
nguyên số đó → nhắn Zalo bà Hồng báo đã gửi. Gold:
`banking.open_savings(acc_878, 18.000.000, 6 tháng)` →
`chat_ott.list_chats` → `chat_ott.send_message(chat_6142, "Tui gửi
tiết kiệm rồi nha bà")` → kết quả `{ok: true, done: false,
message: "không tìm thấy chat_id"}`. `final_state` chỉ có banking.
- Hệ quả chẩn đoán: về mặt cơ học điểm số, model tái tạo đúng
  `chat_6142` sẽ được F1 dù call đó không đổi state; model "sửa"
  thành chat đúng (hoặc bỏ qua send) sẽ MẤT F1 so với gold. Nhưng
  **chính sách xử lý mẫu này: giữ train_1696 là gold anomaly, KHÔNG
  hardcode `chat_6142` vào agent, prompt hay bất kỳ danh sách nào,
  và không dạy model phát ra id không tồn tại.** Gold chứa call lỗi
  là đặc tính của dữ liệu, không phải hành vi cần bắt chước. Khi đo,
  báo cáo mẫu này riêng (ghi chú anomaly, hoặc loại khỏi aggregate
  chính và nêu rõ), thay vì để nó làm lệch kết luận về chất lượng
  model. History dài 22 turn — cũng là mẫu nặng context nhất
  trong nhóm probe.

### train_0082 — gold rỗng mà KHÔNG được gọi lại forecast
Transcript: mai mưa thì đẩy lịch chạy bộ muộn 2 tiếng + SMS cho bố,
không mưa thì thôi. Gold: **0 call**, final_state rỗng.
Lý do nằm trong history (10 turn): turn trước đó đã hỏi "Mai ở đây
trời thế nào?" và assistant đã trả forecast ngày mai TP.HCM "có mây,
rain: False". Điều kiện đã được trả lời từ history.
- Hệ quả chẩn đoán: model gọi lại `weather.get_forecast` ở đây là
  thừa call → trừ F1, dù trông có vẻ "thận trọng". Đối chiếu trực
  tiếp với smoke train_0025/train_0016 (không có forecast trong
  history nên BẮT BUỘC phải gọi forecast trước khi quyết định).

## 3. Thống kê dev (1.237 mẫu, 2.843 gold call) — bối cảnh cho việc đọc trace

- Số call/mẫu: 0: 89, 1: 299, 2: 332, 3: 293, 4: 127, 5: 89, 6: 8.
- Tool gold nhiều nhất: `contacts.search` 183, `sys.ask_missing_info`
  174, `smart_home.light_set` 105, `bill_payment.list_bills` 93,
  `bill_payment.pay` 91, `smart_home.get_status` 88,
  `reminders.create` 86, `calendar.list_events` 80.
- **Định nghĩa read (đã sửa sai 2026-10-27, theo Codex): read = tool
  có `kind: "read"` trong catalog** (catalog ghi rõ: read = không đổi
  state; write = đổi state/tạo hành động; meta = tool hệ thống
  `sys.ask_missing_info`). Đếm theo định nghĩa này trên gold dev:
  **read 1.280 / 2.843 (45,0%)**, write 1.389, meta 174. Con số 1.138
  trước đây là heuristic đoán theo tên tool (chứa search/get_/list_/
  check/…) nên SAI: bỏ sót 155 call read (chủ yếu các tool dạng
  `*.list` — `appliances.list` 17, `medication.list` 13,
  `subscriptions.list` 13, `reminders.list` 10, `tasks.list` 10,
  `notes.list` 9, `email.list` 8, `alarm.list` 7 — cùng
  `order_history`, `track`, `convert`, `calculate`, `guide`,
  `headlines`, `my_bookings`, `recent_calls`) và tính thừa 13 call
  write (`shopping_list.check` 7, `flights.check_in` 6, đều chứa
  "check" nhưng kind là write). 1.138 + 155 − 13 = 1.280, khớp số
  của Codex. Từ đây chỉ dùng định nghĩa theo catalog kind, không
  dùng heuristic tên nữa. Vì read chiếm tới 45% gold call nên câu
  hỏi "read có tính F1 không" (Q-L3, vẫn mở) ảnh hưởng lớn tới điểm,
  không phải chi tiết nhỏ.
- Ask tập trung vào call phụ thuộc contact: `phone.call` 34,
  `sms.send` 24, `ewallet.transfer` 15, rồi mới tới các tool khác
  (tổng 55 tool_name khác nhau). Nghĩa là độ chính xác của ask gắn
  chặt với grounding contact, không phải với "thiếu thông tin" chung
  chung.

## 4. Gold trace của nhóm smoke-5 (để đối chiếu trace model, không phải để chép)

- **train_0025** (mưa → hủy → trùng Minh → hỏi): forecast
  2026-11-28 → `calendar.list_events {}` → `cancel_event evt_01` →
  `contacts.search "Minh"` → `ask phone.call [contact_id]`.
  Final: calendar.
- **train_0016** (mưa → dời +2h → SMS): forecast 2026-11-25 →
  `list_events {}` → `update_event evt_01 10:00–11:00+07:00` →
  `search "Mẹ"` → `sms.send c_01 "mai đá bóng dời sang 10:00 nhé"`.
  Final: calendar, sms. Lưu ý: `content` là free-text (fuzzy) nhưng
  `start`/`end` là hash-relevant — sai giờ thì mất cả hash lẫn F1,
  sai wording SMS thì chỉ mất F1.
- **train_0049** (tiền mạng, fallback tiết kiệm): `list_bills` →
  `banking.get_balance` → `list_beneficiaries` →
  `transfer acc_02 → ben_03, 221.000`. Final: banking. Điểm cần xem
  trong trace: model có kiểm tra số dư trước khi chọn tài khoản
  nguồn không, và amount có khớp bill không.
- **train_0004** (đèn phòng ngủ nhỏ): `get_status {}` →
  `light_set light_bedroom2, brightness 50`. Bẫy: `light_bedroom`
  (phòng ngủ chung) vs `light_bedroom2`; brightness phải là số
  nguyên, không phải chuỗi "50%".
- **train_0019** (đặt khách sạn Đà Lạt): gold rỗng — ngoài phạm vi
  app, không call nào. Model gọi bất kỳ tool nào cũng là thừa.

## 5. Canon hash — đọc từ `zaic_tools/utils.py` thật (không suy từ tên)

- `LIVE_APPS` (loại khỏi state so sánh): exchange_rate, fuel_price,
  gold_price, lottery, weather. Vì vậy forecast trong 0025/0016
  không bao giờ ảnh hưởng hash — quyết định hủy/dời mới ảnh hưởng.
- `FREE_TEXT_KEYS` (loại khỏi state, chấm bằng fuzzy trên arguments):
  address, body, content, dropoff, expression, label, location, name,
  note, pickup, subject, title. Chuỗi được lowercase + collapse
  whitespace, và "700 cm" == "700cm"; list scalar so sánh dạng set.
- Hệ quả: "đúng hash nhưng sai F1" xảy ra đúng ở các field này
  (nội dung SMS, địa điểm xe) — khi đọc trace, hash đúng KHÔNG đủ
  để kết luận mẫu đó đạt.
