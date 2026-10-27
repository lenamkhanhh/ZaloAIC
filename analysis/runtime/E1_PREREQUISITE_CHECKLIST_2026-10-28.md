# E1 Prerequisite Checklist — 8 mẫu, build từ gold, FREEZE trước run

Trạng thái: FROZEN FOR E1. Codex copy file này nguyên vẹn vào hồ sơ run
trước khi chạy Arm A/Arm B; mọi sửa đổi sau khi run bắt đầu phải lưu
thành file mới có version, không sửa lặng lẽ file này (sửa lặng lẽ làm
metric mất ý nghĩa).

Mục đích: đo riêng tầng PREREQUISITE — agent có đọc đúng cái cần đọc,
trước cái write phụ thuộc vào nó, hay không. Checklist này KHÔNG đo
format, KHÔNG đo hash/F1 (hai tầng đó đo riêng theo E1 brief). Một mẫu
có thể PASS prerequisite nhưng FAIL hash (và ngược lại): ví dụ model
đoán đúng ID mà không search thì hash đúng nhưng prerequisite FAIL —
đó chính là điểm checklist này tồn tại để bắt (evidence discipline).

## Phương pháp build (đã chạy, không phải ước lượng)

- Replay đúng gold sequence của 8 mẫu qua `zaic_tools` (ToolEnv) và
  truy vết từng argument của write/ask: giá trị đó xuất hiện lần đầu ở
  đâu — transcript, context, history, hay output của read nào trước
  đó. Chỉ khi giá trị CHỈ có trong output của một read trước đó thì
  quan hệ mới được gắn STRICT.
- Các giá trị NOWHERE (không nằm trong transcript/context/history/
  read trước dưới dạng chuỗi khớp) được phân loại riêng: DERIVED
  (suy từ ngôn ngữ, ví dụ "50 nghìn" → 50000, "một nửa" → 50) hoặc
  COMPOSED (ghép từ nhiều nguồn, ví dụ nội dung SMS) — chúng KHÔNG
  tạo quan hệ prerequisite với read nào.
- Containment là bằng chứng, không phải chứng minh tuyệt đối: nếu một
  giá trị xuất hiện trong output read một cách tình cờ (ví dụ giờ
  10:00–11:00 của 0016 cũng xuất hiện trong list_events), nó được hạ
  xuống COMPUTED thay vì STRICT. Xem ghi chú từng mẫu.
- Checklist này chứa tiêu chí đo (tên tool + quan hệ), không phải
  prompt cho agent. KHÔNG đưa file này, hay bất kỳ nội dung nào của
  nó, vào input của agent dưới mọi hình thức.

## Luật chấm chung

- Mỗi quan hệ chấm PASS/FAIL độc lập. Điểm prerequisite của một mẫu =
  số quan hệ PASS / tổng số quan hệ của mẫu đó.
- "Trước" tính theo thứ tự submitted calls (thứ tự thực thi).
- Một quan hệ STRICT/BRANCH được tính PASS khi và chỉ khi prerequisite
  tool xuất hiện trong submitted calls TRƯỚC dependent call (với các
  rule đặc biệt ghi riêng cho 0008/0019/0116). Không yêu cầu argument
  của prerequisite read phải khớp gold từng chữ — tầng argument đo
  riêng; checklist chỉ đo thứ tự và sự hiện diện.
- Model đoán đúng giá trị mà không qua prerequisite read = FAIL quan
  hệ đó, dù hash cuối có đúng. Đây là hành vi có chủ đích của
  checklist, không phải bug chấm.
- Đối với mẫu có gold ask cuối (0025): ask không phải là write; rule
  cho ask nằm ở mục của mẫu đó.

## Checklist theo mẫu

### train_0019 — empty (regression guard)

- Gold: 0 calls. Yêu cầu đặt phòng khách sạn, app khách sạn không được
  cài → không làm gì.
- **R19.1 — PASS khi và chỉ khi submitted calls = 0.** Bất kỳ call
  nào cũng là FAIL (kể cả search/read "thử").

### train_0116 — ask_only (ask target, không write)

- Gold: duy nhất `sys.ask_missing_info{tool_name: reminders.create,
  params: ["time"]}`. Transcript: "nhắc tôi gọi điện cho mẹ".
- **R116.1 — PASS khi và chỉ khi submitted calls = đúng 1 ask với
  tool_name = reminders.create và params = ["time"].** Bất kỳ write
  nào (đặc biệt `reminders.create` với giờ tự điền, lỗi của E0) cũng
  là FAIL, dù giờ đó có "hợp lý". Đây là rule ask-vs-act, không phải
  rule format.

### train_0025 — ask_after (branch + entity ambiguity)

- Gold theo thứ tự: `weather.get_forecast{date: 2026-11-28}` →
  `calendar.list_events{}` → `calendar.cancel_event{event_id: evt_01}`
  → `contacts.search{query: "Minh"}` →
  `sys.ask_missing_info{tool_name: phone.call, params: ["contact_id"]}`.
  Transcript: "Nếu mai mưa thì huỷ lịch đá bóng sáng mai với gọi cho
  bạn Minh nhé, còn không mưa thì thôi ạ."
- **R25.1 [BRANCH] — get_forecast phải xuất hiện TRƯỚC
  cancel_event.** Cancel trước khi biết mưa hay không = FAIL (lỗi
  title-write-trước-điều-kiện của E0 thuộc cùng họ).
- **R25.2 [STRICT] — list_events phải xuất hiện TRƯỚC cancel_event.**
  Bằng chứng: `evt_01` chỉ xuất hiện trong output của list_events
  (không có trong transcript/context/history).
- **R25.3 [ORDER] — contacts.search{query "Minh"} phải xuất hiện
  TRƯỚC ask.** Gold hỏi vì search trả về nhiều ứng viên Minh mà
  không có discriminator — ask là đường đi đúng khi mơ hồ.
- **R25.4 [NO-CALL] — submitted KHÔNG được chứa phone.call.**
  Gold không gọi ai cả; E0 gọi `c_05` là chọn bừa một trong hai Minh
  = FAIL, dù call đó well-formed và ID có provenance.

### train_0003 — multi_step (hai prerequisite STRICT + một recovery)

- Gold theo thứ tự: `bill_payment.list_bills{}` →
  `contacts.search{query: "Bác Ba"}` →
  `ewallet.topup_mobile{phone: 09919377320, amount: 50000}` →
  `contacts.search{query: "Cô giáo Mai"}` →
  `ewallet.transfer{contact_id: c_06, amount: 845000}`.
  Transcript: "nạp giúp mình 50 nghìn điện thoại cho bác Ba với chuyển
  ví cho cô Mai số tiền điện tháng này nhé."
- **R03.1 [STRICT] — contacts.search phải trả về số 09919377320
  TRƯỚC topup_mobile.** Bằng chứng: số này chỉ có trong output của
  search Bác Ba. (Số 50000 là DERIVED từ "50 nghìn" trong transcript,
  không tạo quan hệ với read nào — đừng chấm amount của topup như
  prerequisite.)
- **R03.2 [STRICT] — list_bills phải xuất hiện TRƯỚC transfer.**
  Bằng chứng: 845000 chỉ có trong output của list_bills. Đây là quan
  hệ E0 vi phạm nặng nhất: model không bao giờ gọi list_bills dù
  transcript nhắc "số tiền điện tháng này".
- **R03.3 [STRICT] — một contacts.search phải trả về c_06 TRƯỚC
  transfer.** Bằng chứng: c_06 chỉ có trong output của search
  "Cô giáo Mai". Search rỗng rồi vẫn transfer = FAIL (không có
  evidence), dù transfer có đoán đúng ID.
- **R03.4 [RECOVERY, ghi nhận không tính điểm cứng] — sau một search
  rỗng, model có thử mở rộng query (ví dụ search không query — theo
  mô tả catalog, search không query trả cả danh bạ) hay đổi query
  không?** Ghi YES/NO vào report để phân tích, không tính vào điểm
  prerequisite (vì gold không quy định chiến lược recovery). E0 lặp
  lại cùng query rỗng = NO.

### train_0008 — history (branch thuần, không write trong gold)

- Gold: duy nhất `weather.get_forecast{date: 2026-11-14}`.
  Transcript: "Cái còn lại nếu mai mưa thì dời muộn nửa tiếng, không
  mưa giữ nguyên." History: user đã hỏi alarm ngày mai rồi xoá alarm
  sớm nhất — alarm còn lại là alm_02 (ID này lấy từ history, KHÔNG
  cần read nào).
- **R08.1 [BRANCH] — get_forecast{date: 2026-11-14} phải là call đầu
  tiên có ý nghĩa, TRƯỚC mọi alarm.update.** Update trước forecast =
  FAIL (lỗi E0 vẫn mắc).
- **R08.2 [BRANCH-OUTCOME] — PASS khi và chỉ khi submitted KHÔNG
  chứa alarm.update.** Gold environment cho forecast rain = false nên
  gold không ghi gì. (Nếu forecast thực tế trong run trả rain = true
  thì rule này phải được xem lại — Codex ghi lại forecast result vào
  report; rule này giả định rain = false như gold environment.)
- **R08.3 [WRONG-READ] — submitted KHÔNG được dùng get_current thay
  cho get_forecast.** E0 đọc thời tiết hiện tại thay vì forecast ngày
  mai = FAIL (sai tool đọc cho điều kiện ngày mai).

### train_0016 — conditional_positive (branch + strict + task-type guard)

- Gold theo thứ tự: `weather.get_forecast{date: 2026-11-25}` →
  `calendar.list_events{}` →
  `calendar.update_event{event_id: evt_01, start/end 10:00–11:00}` →
  `contacts.search{query: "Mẹ"}` → `sms.send{contact_id: c_01, …}`.
  Transcript: "nếu mai mưa thì dời lịch đá bóng sáng mai muộn hai
  tiếng với nhắn SMS cho Mẹ báo giờ mới, còn không mưa thì thôi nhé."
- **R16.1 [BRANCH] — get_forecast phải xuất hiện TRƯỚC
  update_event.**
- **R16.2 [STRICT] — list_events phải xuất hiện TRƯỚC update_event.**
  Bằng chứng: `evt_01` chỉ có trong output của list_events. Giờ
  10:00–11:00 là COMPUTED (giờ gốc từ list_events + "muộn hai tiếng"
  trong transcript), không chấm như STRICT — dù chuỗi giờ có xuất
  hiện trong output list_events, đó có thể là trùng lặp tình cờ.
- **R16.3 [STRICT] — contacts.search phải trả về c_01 TRƯỚC
  sms.send.** (Nội dung SMS là COMPOSED, không tạo quan hệ.)
- **R16.4 [TASK-TYPE] — submitted KHÔNG được chứa reminders.create
  hay reminders.complete.** E0 tạo + hoàn thành reminder thay vì đổi
  calendar event = FAIL (nhầm loại task, không phải format).

### train_0049 — balance_fallback (ba STRICT + fallback direction)

- Gold theo thứ tự: `bill_payment.list_bills{}` →
  `banking.get_balance{}` → `banking.list_beneficiaries{}` →
  `banking.transfer{from_account_id: acc_02, beneficiary_id: ben_03,
  amount: 221000}`. Transcript: "chuyển tiền mạng tháng này cho chủ
  nhà Phạm Hùng nhé, nếu tài khoản thanh toán không đủ thì lấy từ
  tiết kiệm giúp tôi."
- **R49.1 [STRICT] — list_bills phải xuất hiện TRƯỚC transfer.**
  Bằng chứng: 221000 chỉ có trong output của list_bills.
- **R49.2 [STRICT] — get_balance phải xuất hiện TRƯỚC transfer.**
  Bằng chứng: acc_02 (tài khoản tiết kiệm, nguồn fallback khi tài
  khoản thanh toán không đủ) chỉ xác định được từ output của
  get_balance.
- **R49.3 [STRICT] — list_beneficiaries phải xuất hiện TRƯỚC
  transfer.** Bằng chứng: ben_03 chỉ có trong output của
  list_beneficiaries.
- **R49.4 [FALLBACK-DIRECTION] — transfer (nếu có) phải có
  from_account_id là tài khoản tiết kiệm theo get_balance, KHÔNG
  phải mở savings mới.** `banking.open_savings` trong submitted =
  FAIL (E0/v7 thêm savings actions; gold fallback là chuyển TỪ tiết
  kiệm, không phải mở tiết kiệm). Nếu model transfer từ tài khoản
  thanh toán mà không qua get_balance thì R49.2 đã FAIL; R49.4 chỉ
  chấm riêng lỗi open_savings.

### train_0004 — device_grounding (strict nhẹ + scorer caveat)

- Gold theo thứ tự: `smart_home.get_status{}` →
  `smart_home.light_set{device_id: light_bedroom2, brightness: 50}`.
  Transcript: "giảm độ sáng đèn phòng ngủ nhỏ xuống còn một nửa nhé."
- **R04.1 [STRICT] — get_status phải xuất hiện TRƯỚC light_set.**
  Bằng chứng: light_bedroom2 chỉ có trong output của get_status.
  (Brightness 50 là DERIVED/COMPUTED: "một nửa" của độ sáng hiện tại
  trong get_status — không chấm như STRICT, nhưng ghi nhận nếu model
  đặt brightness không bằng một nửa giá trị get_status trả về thì
  đó là lỗi value, đo ở tầng arguments, không phải ở đây.)
- **CAVEAT — không chấm chặt args ở đây:** gold get_status không có
  room filter và gold light_set không có `power`. Một submitted read
  có filter hay write có thêm optional arg KHÔNG làm FAIL R04.1 —
  đó là phạm vi proxy-mismatch/scorer (câu hỏi organizer Q-L), không
  phải prerequisite. R04.1 chỉ chấm thứ tự và sự hiện diện.

## Tổng hợp nhanh (để Codex đối chiếu, không thay bảng trên)

| Mẫu | Số quan hệ chấm điểm | Các quan hệ |
|---|---|---|
| 0019 | 1 | R19.1 (0 calls) |
| 0116 | 1 | R116.1 (ask đúng, không write) |
| 0025 | 4 | R25.1 branch, R25.2 strict, R25.3 order, R25.4 no-call |
| 0003 | 3 (+1 ghi nhận) | R03.1, R03.2, R03.3 strict; R03.4 recovery (không tính điểm) |
| 0008 | 3 | R08.1, R08.2, R08.3 |
| 0016 | 4 | R16.1 branch, R16.2 strict, R16.3 strict, R16.4 task-type |
| 0049 | 4 | R49.1–R49.3 strict, R49.4 fallback-direction |
| 0004 | 1 | R04.1 strict |

## Freeze và sử dụng trong E1

1. Codex copy file này vào hồ sơ run E1 trước khi chạy arm đầu tiên.
2. Trong report E1, mỗi arm có một bảng PASS/FAIL cho 21 quan hệ chấm
   điểm trên (R03.4 chỉ ghi YES/NO, không tính điểm).
3. Điểm prerequisite được báo CÙNG với format metrics, hash, F1 —
   không thay thế chúng, không gộp thành một số duy nhất với chúng.
4. Nếu forecast result thực tế của 0008 trong run khác gold
   environment (rain = true), Codex ghi rõ và R08.2 được đánh dấu
   NOT-APPLICABLE thay vì FAIL, kèm bằng chứng forecast result.
