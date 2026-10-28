# Phân tích sâu E5 V13 + sửa bản SOTA + chọn đúng một thí nghiệm tiếp theo

**Chỉ phân tích + viết tài liệu. KHÔNG sửa inference, KHÔNG chạy model/GPU,
KHÔNG held-out, KHÔNG hardcode probe vào agent/prompt, KHÔNG liên hệ ai.
Mọi số liệu mẫu dưới đây chỉ dùng để chẩn đoán SAU khi chạy, không bao giờ
là input của agent.**

## 0. Kết luận trước: làm E7 guard nguồn time/amount, bắt đầu bằng shadow audit

**Thí nghiệm tiếp theo duy nhất: E7 — guard hẹp kiểm tra nguồn gốc (provenance)
của argument time/amount trước khi write thực thi, bắt đầu bằng shadow audit
CPU-only, chỉ chạy GPU khi shadow audit đạt ngưỡng. Brief đầy đủ ở
`E7_GUARD_DEPLOYMENT_BRIEF_2026-10-28.md` cùng đợt push này.**

Vì sao chọn guard, bằng một câu: 5/6 target không sửa được đều fail bằng cùng
một cơ chế — model tự điền time từ context rồi act ngay, khiến điều kiện
"hỏi khi thiếu" của rule không bao giờ kích hoạt — và guard là can thiệp duy
nhất trong các lựa chọn nhắm thẳng vào cơ chế điền đó ở tầng thực thi, thay vì
nhờ model tự nhận ra mình đang thiếu.

Vì sao KHÔNG chọn hai hướng còn lại (chi tiết ở §3):

- **Mở rộng E5 thêm 28 mẫu — HOÃN, không phải hủy.** Cơ chế đã biết, fill-act
  xuất hiện ở cả 3 subgroup (call/meeting/medication), không phải nhiễu mẫu.
  Rule có trần cấu trúc: bất kỳ target nào model điền time đều không sửa được
  bằng rule, nên mở rộng chỉ đo lại một hiệu ứng đã biết là bị chặn trần, tốn
  ~56 trial GPU mà không đổi được quyết định nào. Nhánh INCONCLUSIVE "mở rộng"
  được đăng ký TRƯỚC khi biết cơ chế; hoãn có lý do rõ ràng tôn trọng
  preregistration hơn là chạy mù theo chữ. Sau E7, mở rộng được đăng ký lại
  cho rule+guard hoặc guard-alone, với parser/rule/denominator đóng băng riêng
  (đúng ràng buộc của audit V13: không viết lại kết quả V13).
- **Sửa ranh giới pseudo-call (key=value) — KHÔNG phải thí nghiệm tiếp theo.**
  Gap là thật (0653 cả hai arm), nhưng nó là gap đo lường hậu-read, đổi 0/20
  kết quả ask-first của V13. Nó được làm song song ở dạng CPU-only:
  preregister một hạng mục BÁO CÁO key=value, pattern hẹp, KHÔNG đổi parser,
  để không làm nhiễu phép đo của E7. Đổi parser là ứng viên SAU E7, với gate
  CPU và preregistration riêng.
- **Hướng dự bị (không nằm trong 3 lựa chọn gốc): prompt loại trừ nguồntường minh**
  ("current_time và giờ trong history KHÔNG phải giờ user yêu cầu") — chưa test,
  rẻ, nhưng xác suất thấp hơn guard vì nó vẫn nhờ model áp dụng loại trừ lúc
  sinh (V13 đã cho thấy ruletường minh vẫn bị vi phạm), và nếu nó fail thì không biết
  là do wording hay do cơ chế miễn nhiễm. Nó thành ứng viên tiếp theo NẾU E7
  bị bác bỏ qua nhánh block→stop (lúc đó vấn đề nằm ở phản ứng sau block,
  không phải ở block).

Lựa chọn này dựa trên bằng chứng 5/7 fill-act đã truy nguồn xong (§1.3),
không phải vì Codex gợi ý guard. Nếu bằng chứng chỉ ra cue loss hay ASR mới là
cơ chế chủ đạo, lựa chọn đã khác — nhưng cue giữ 7/7 và fill-act xảy ra cả
khi ASR sạch (§1.3), nên không phải vậy.

## 1. Phân tích sâu E5 V13 (main 8846ab1, base a472006)

### 1.1 Số liệu đã kiểm chứng (40/40 trial, không lỗi runtime)

- TARGET ask-first: control 0/7 → rule 1/7 (net +1). CONTROL ask-first:
  0/13 → 0/13 (net 0). **Verdict đăng ký trước: INCONCLUSIVE, giữ nguyên.**
  Không adopt rule, không mở rộng tự động, cả 7 target ở lại mẫu số (đề xuất
  báo cáo hai cột "channel-recovered-only" KHÔNG được áp dụng, đúng audit).
- Channel: caught 4 → 0 generations; explicit format-failure traces 2 → 0;
  registered silent 0 → 0; zero-submission traces 3 → 3; clean zero-call stops
  1 → 3; first submitted tool là write 11/20 → 12/20; generations 42 → 36;
  submitted calls 20 → 18; key=value pseudo-stop sau call 1 → 1.
- Proxy mean: control 0.0 → rule 0.05, toàn bộ đến từ đúng một mẫu 0116
  (proxy 1.0); mọi control đều proxy 0.0 ở cả hai arm. Proxy không phải metric
  chính ở đây; ask-first mới là metric chính.
- Partition generations: control 22 tagged + 4 caught + 11 plain-text + 5
  legacy = 42; rule 19 tagged + 0 caught + 8 plain-text + 9 legacy = 36.
  Rule arm dừng bằng legacy stop nhiều hơn (9 vs 5) — rule không làm giảm
  dừng, nó đổi dạng dừng.
- Chẩn đoán chính theo handoff: control CHANNEL_CAUGHT_FAILED 2,
  WRONG_INTENT_OR_ASK_VS_ACT 16, WRONG_ASK_PARAMS 1, PREMATURE_STOP 1;
  rule PASS 1, WRONG_INTENT_OR_ASK_VS_ACT 14, WRONG_ASK_PARAMS 2,
  PREMATURE_STOP 3. Hạng mục gộp WRONG_INTENT_OR_ASK_VS_ACT che ba cơ chế
  khác nhau — tách ra ở §1.4, đừng đọc gộp thành "capability failure".

### 1.2 Vì sao rule sửa được 0116 nhưng không sửa sáu target còn lại

**0116 (PASS duy nhất) — cơ chế ba chặng, không phải rule tự sinh ra ask:**

1. Rule (có thể) đổi intent: control đi phone.call{cont_01} (sai task family,
   bị grounding chặn) → rule đi reminders.create (đúng family).
2. Model BỎ TRỐNG time thay vì điền: generation 1 là reminders.create
   {content, repeat} không có time.
3. Simulator validator chặn create thiếu time bắt buộc ("thiếu tham số bắt
   buộc: time") → generation 2 hỏi đúng reminders.create/time → PASS.

Điểm mấu chốt: ask ở 0116 được kích hoạt bởi VALIDATOR, không phải trực tiếp
bởi chữ trong rule. Generation 1 của rule arm không phải là ask — nó là một
create thiếu time. Nếu model đã điền time (như năm target còn lại), validator
đã chấp nhận create và 0116 đã fail như các mẫu kia. **Pass của 0116 là
mong manh: nó phụ thuộc vào việc model bỏ trống thay vì điền — đúng hành vi
mà năm mẫu còn lại không thể hiện.** Rule đã chứng minh được một việc
(chọn đúng task family: cả 7 first submitted call của rule arm đều thuộc họ
reminders, so với control có 0116 đi phone.call và 0287 kẹt format sau
transfer attempt), nhưng không chứng minh được việc thứ hai (ngăn điền time).

**Năm target còn lại — cùng một cơ chế: điền rồi act (fill-act).**
0219, 0220, 0287, 0360, 0780 đều có first submitted call là reminders.create
kèm một time đầy đủ, không qua read nào trước đó (trừ 0360-control, xem
§1.4). Rule không sửa được chúng vì rule giả định model nhận ra time đang
thiếu — nhưng model không trải nghiệm thiếu: nó đã "giải quyết" thiếu bằng
cách bịa/điền một giá trị hợp lệ từ context, rồi thiếu biến mất trước khi
điều kiện của rule kịp kích hoạt. **Confabulation làm tan biến missingness
trước khi rule có cơ hội chạy.** Đây là lý do mọi can thiệp dạng "nhắc model
hỏi khi thiếu" đều bị chặn trần bởi cơ chế này, và là lý do can thiệp tiếp
theo phải nằm ở tầng thực thi (guard chặn write), không phải tầng nhắc nhở.

**0353 (rule arm) — lỗi khác hẳn: hỏi sai param, không phải fill-act.**
Model hỏi reminders.create/content thay vì time. ASR current "nhắc tôi để họ
phụ huynh vậy" đã làm hỏng chính content ("đi họp" → "để họ"), nên model
đánh giá content là thứ thiếu và hỏi content. Family đúng, có hỏi, nhưng chọn
sai slot: gold ưu tiên time, model ưu tiên content khi cả hai đều có vấn đề.
Đây là lỗi chọn slot dưới ASR nhiễu, không phải lỗi intent family, không
phải fill-act, không phải channel.

### 1.3 Truy nguồn từng time model sử dụng (gold request + gold history + context)

Quy ước: "nguồn" chỉ tính khi giá trị đó là thứ user yêu cầu CHO reminder này.
Xuất hiện trong context (current_time, history, observation) KHÔNG đồng nghĩa
được user yêu cầu. Gold request của cả 7 target đều KHÔNG có giờ cụ thể
(0780 chỉ có "sáng mai" mơ hồ); gold label của cả 7 đều là ask
reminders.create/time.

| Mẫu | Time model dùng (rule arm) | Gold request | History có giờ? | current_time | Nguồn kết luận |
|---|---|---|---|---|---|
| 0116 | (không dùng — bỏ trống → hỏi) | "nhắc tôi gọi điện cho mẹ" (không giờ) | Có giờ khác việc: họp team 15:00 ngày mai (không liên quan) | 2026-11-19T10:30 | N/A — omission, không phải fill |
| 0219 | 2026-11-06T14:00 | "nhắc em đi họp" (không giờ) | Không có history | 2026-11-06T13:30 | **current_time date + giờ tròn tiếp theo** (13:30→14:00). Không từ request/history/observation (first call chính là create) |
| 0220 | 2026-11-18T13:10 | "nhắc mình gọi cho mẹ" (không giờ) | Không có history | 2026-11-18T13:10 | **current_time copy nguyên xi** (cả date lẫn giờ). Stop text control xác nhận "13:10 hôm nay" |
| 0287 | 2026-11-13T09:00 | "nhắc mình gọi cho mẹ" (không giờ) | Không có giờ (giá vàng, số dư ngân hàng, số dư ví) | 2026-11-13T08:45 | **current_time date + giờ tròn tiếp theo** (08:45→09:00) |
| 0353 (control) | 2026-11-09T14:00 | "nhắc tôi đi họp phụ huynh" (không giờ) | CÓ: lịch ngày mai gồm họp dự án 15:30, **đi chơi công viên 14:00**, đá bóng 19:00 | 2026-11-08T11:30 | **Irrelevant-history leak — khớp chính xác**: date 11-09 + giờ 14:00 = slot đi công viên trong history, gán sang reminder họp phụ huynh. Không phải default hour (14:00 xuất hiện verbatim trong history cho việc khác) |
| 0360 | 2026-11-15T20:00 | "nhắc mình gọi cho mẹ" (không giờ) | Không có giờ (số điện thoại, thời tiết, số dư, giá xăng) | 2026-11-15T19:10 | **current_time date + giờ tròn tiếp theo** (19:10→20:00). Rule arm bỏ luôn contacts.search mà control đã làm |
| 0780 | 2026-10-18T08:00 | "đặt nhắc uống Cardiol sáng mai, theo lời dặn MỚI NHẤT của bác sĩ" (chỉ mơ hồ "sáng mai", không giờ cụ thể) | CÓ, nhưng phức tạp: giấy ra viện ghi 8 giờ sáng (ĐÃ BỊ THAY THẾ bởi "uống sau bữa sáng" + "mới nhất"); ăn sáng cuối tuần ~8 giờ | 2026-10-17T20:00 | **Không xác định được giữa 3 ứng viên, nhưng cả 3 đều không phải giờ user yêu cầu**: (a) default giờ sáng cho "sáng mai"; (b) leak từ giấy ra viện 8 giờ — giá trị ĐÃ BỊ user chỉ định thay thế ("mới nhất"); (c) leak từ giờ ăn sáng ~8 giờ. Date 10-18 thì suy ra được từ "sáng mai" + today, nhưng GIỜ 08:00 thì không suy ra được từ request |

Tổng kết truy nguồn:

- **5/5 time fill-act, 0 cái từ request, 0 cái từ observation có chủ đích.**
  Ba cơ chế điền: (1) copy current_time (0220); (2) current_time date + giờ
  tròn tiếp theo (0219, 0287, 0360 — pattern nhất quán: 13:30→14:00,
  08:45→09:00, 19:10→20:00); (3) leak history việc khác (0353-control).
  0780 là trường hợp mơ hồ giữa default và leak — nhưng với guard thì không
  cần phân biệt: giờ không nằm trong request dưới mọi giả thuyết, nên guard
  chặn cả hai.
- **ASR không phải nguyên nhân chủ đạo của fill-act.** 0219 ASR sạch
  ("nhắc em đi họp với nha"), 0220 cue giữ (chỉ "gọi cho mẹ" → "khỏi cha mẹ",
  không ảnh hưởng time vì request vốn không có time), 0360 ASR gần sạch —
  cả ba vẫn fill-act. Cue giữ 7/7 chỉ chứng minh cue "nhắc" không mất, không
  chứng minh ASR toàn vẹn (0220/0287/0353/0780 có nhiễu từ khác, đúng audit),
  nhưng nhiễu đó không giải thích fill-act ở các mẫu ASR sạch.
- **Trường hợp 0780 là bằng chứng mạnh nhất cho guard nguồn:** ngay cả khi
  model copy history 8 giờ, đó là giá trị user đã chỉ định THAY THẾ bằng lời
  dặn mới nhất (không có giờ). Một guard cho phép "giờ trong history" một
  cách mù sẽ CHO QUA leak này; guard phải có quy tắc supersession (giá trị
  trước thời điểm "mới nhất" bị loại khi request nói "mới nhất"). Xem brief E7.

### 1.4 Tách loại lỗi — đừng gọi tất cả là capability failure

Rule arm, 7 target:

- **PASS (1):** 0116 — qua omission + validator (§1.2). Không chứng minh rule
  tự sinh ask.
- **Thiếu-time nhưng vẫn act — fill-act (5):** 0219, 0220, 0287, 0360, 0780.
  Family đúng, nhưng act thay vì ask vì time đã bị điền. Đây là lỗi
  missingness-recognition (model không nhận ra thiếu vì đã tự điền), khác với
  lỗi phân loại intent.
- **Hỏi sai params (1):** 0353 — family đúng, có hỏi, chọn sai slot (content
  thay vì time) dưới ASR nhiễu content.
- **Lỗi channel (0):** rule arm không còn caught/format-failure nào ở target.

Control arm, 7 target (first-call):

- **Channel-failed (2):** 0116, 0287 — đều kết thúc FORMAT_FAILURE_RETRY_
  EXHAUSTED. Lưu ý 0287-control đã drift đúng hướng nhưng sai channel:
  generation cuối là pseudo-call reminders.create/[content, time] — model đã
  chạm tới tool và params đúng nhưng ở dạng không thực thi được, rồi hết retry.
- **Fill-act first-call (4):** 0219, 0220, 0353, 0780.
- **Read-first thay vì ask-first (1):** 0360-control — contacts.search "mẹ"
  trước, tìm được c_03, rồi mới create với time điền 20:00. Metric ask-first
  tính là fail (first call ≠ ask), nhưng đây là thu thập evidence trước khi
  act — khác với chọn sai task family, và không phải "model ngu": search này
  là hợp lý, chỉ là không khớp metric nghiêm ngặt (gold muốn ask TRƯỚC).
  Rule arm 0360 bỏ luôn bước search này (first call thành write) — rule làm
  giảm evidence gathering ở mẫu này, một tác dụng phụ cần ghi nhận.

### 1.5 Control vốn 0/13: net 0 che cả perturbation lẫn floor

- **Không có spillover họ task:** 0/13 first call của rule arm ở control là
  reminders.* — rule không kéo control sang tạo reminder. WATCH 0961 không
  bị trigger bởi "sợ quên" (không có reminders ask nào) — cue specificity giữ.
- **Nhưng net 0 KHÔNG có nghĩa là không có hiệu ứng.** 5/13 control đổi hành
  vi control→rule (8/13 giữ nguyên):
  - 0653: flights.search thêm passengers:1 (pseudo-stop sau đó giữ nguyên).
  - 0683: video_meeting.create đổi start 10:00 → 09:00, title dài thêm.
  - 0684: ask maps.search_place/query → stop 0 call (PREMATURE_STOP mới).
  - 0961: list_bills{type:water} → list_bills{} (mất filter) + hỏi bằng prose
    liệt kê 3 hóa đơn thay vì submitted ask (WATCH: behavior đổi, score không
    đổi; prose ask không phải submitted ask).
  - 1234: email.read (2 calls) → stop 0 call (PREMATURE_STOP mới).
  - Giữ nguyên: 0498 (cùng ask sai params contact_id+amount), 0823 (cùng
    event calendar với start điền 10:00), 1029, 1075, 1104, 1107, 1111, 1223
    (stop cả hai arm).
- **Rule arm làm ÍT đi, không làm tốt hơn ở control:** premature stops 1 → 3
  (thêm 0684, 1234), clean zero-call stops 1 → 3, first-write 11 → 12,
  submitted calls 20 → 18, generations 42 → 36. Hai premature stop mới là tác
  dụng phụ thật của rule trên control, vô hình với net 0. Kết luận đúng về
  control: "không spillover họ reminders, nhưng có perturbation gồm 2 stop
  mới; net 0 là floor (metric đã ở đáy, không đo được loss thêm) cộng
  perturbation, không phải bằng chứng không có tác dụng phụ."
- **WATCH 0823 cần shadow audit truy nguồn:** event calendar với start
  2026-10-10T10:00 giống hệt cả hai arm; gold hỏi start nên start này cũng là
  fill — nhưng báo cáo này chưa truy nguồn của nó (không nằm trong 7 target).
  Brief E7 giao shadow audit truy nguồn cho mọi write trong 20 mẫu, kể cả
  control, để không bỏ sót fill ngoài target.

### 1.6 Pseudo-call key=value ở 0653 cả hai arm — đọc nguyên văn, giữ verdict

Cả hai arm, sau flights.search trả về rỗng (`flights: []`), generation tiếp
theo đều là nguyên văn:

`sys.ask_missing_info tool_name=flights.search params=["date"]`

Đây là unsubmitted pseudo-call, KHÔNG phải ask thật: thiếu dấu mở ngoặc của
pattern đã đăng ký (`app.tool(` lowercase), nên parser E6-C xếp là plain-text
stop. Nội dung của nó TRÙNG gold ask (flights.search/["date"]) — model đã
"nói đúng" ask cần thiết nhưng ở sai channel, và SAU một read (nên first-call
đã fail trước đó ở cả hai arm: first call là flights.search, không phải ask).

**Giới hạn của định nghĩa silent — và vì sao verdict vẫn INCONCLUSIVE:**

- Định nghĩa đã đăng ký trong handoff c8a7d46 §1.5: SILENT_PSEUDO là trace
  zero-submission (0 submitted call) kết thúc sạch nhưng có generation dạng
  call. 0653 đã có 1 submitted read, nên theo định nghĩa đó, registered
  silent = 0. Định nghĩa này được viết cho pattern pseudo-ask LÀ first action
  (kiểu 0116-V10), không bao quát pseudo-ask hậu-read.
- Theo cách đọc RỘNG HƠN của wording "silent" trong brief (đếm mọi pseudo-call
  không được submit, không phân biệt đã có call trước đó), 0653 sẽ kích hoạt
  CONFOUNDED. Audit V13 đã công khai độ nhạy này thay vì thay thế lén sau khi
  thấy kết quả — và báo cáo này giữ nguyên cách xử lý đó: **không sửa metric
  sau khi thấy kết quả, không rescore V13, verdict giữ INCONCLUSIVE theo
  preregistration.**
- Hệ quả cho thí nghiệm tiếp theo: trước run GPU tiếp theo, phải preregister
  một hạng mục BÁO CÁO riêng cho key=value hậu-call (pattern hẹp: bắt đầu
  đúng `sys.ask_missing_info tool_name=` + `params=`), với test an toàn prose
  (19 stop đã review: prose xác nhận "Đã tạo...", tóm tắt hóa đơn, v.v. KHÔNG
  được flag). Parser KHÔNG đổi trong E7 — hạng mục này chỉ là báo cáo, để
  phép đo E7 có đúng một biến (xem brief). Sửa parser là việc sau E7.
- Giá trị thực của việc sửa boundary: 0 kết quả ask-first nào của V13 thay đổi
  (0653 first call đã là read). Giá trị của nó nằm ở (a) trung thực đo lường
  cho các run sau, và (b) các trường hợp tương lai mà pseudo-ask LÀ first
  action (lúc đó nó mới ảnh hưởng metric). Đừng bán nó như fix cho V13.

### 1.7 Verdict giữ nguyên và các ràng buộc còn hiệu lực

- INCONCLUSIVE (nhánh +1 đăng ký trước). Không adopt rule. Không mở rộng 28
  tự động. Không viết lại kết quả V13. Mọi thí nghiệm sau phải đăng ký
  parser/rule/denominator riêng, giữ nguyên evidence V13 (đúng ràng buộc audit).
- Hai câu hỏi cho bước tiếp theo mà audit nêu — (a) liệu tham chiếu time rộng
  trong history/observation có cho time không liên quan rò vào argument, và
  (b) preregister detection cho key=value mà không ép prose thành tool — câu
  (a) đã có đáp án ở §1.3: CÓ, đã chứng minh (0353 park leak; 0780 superseded
  leak khả dĩ; clock fills). Câu (b) được xử lý ở §1.6 + brief E7 (reporting,
  không đổi parser).

## 2. Sửa các kết luận quá rộng trong bản SOTA (main c962d174)

Nguyên tắc: bản SOTA giữ nguyên làm record có ngày; các sửa chữa dưới đây là
bản chính thức thay thế các câu đó. Không sửa ngược file cũ để khỏi mất audit
trail. Mọi trích dẫn paper từ đây phải kèm model/benchmark/metric/phạm vi +
link + vị trí bảng/section, và một câu về khoảng cách chuyển giao sang
LifeMate — không chuyển kết quả paper thành bảo đảm cho LifeMate.

### 2.1 Sửa 1 — E0 KHÔNG phải "thông tin hoàn hảo"

- **Câu cũ (SOTA §0):** E0 cho "gold current transcript (thông tin hoàn hảo)"
  mà proxy không đổi → "trần thông tin".
- **Sự thật:** E0 chỉ dùng gold CURRENT transcript; history vẫn ASR (audit E0:
  "gold current transcript only, ASR history kept"). History ASR nhiễu vẫn còn
  (ví dụ 0780 history ASR giữ fragment "tám giờ sáng" nhưng nhiễu nặng ở các
  chỗ khác), và intent errors vẫn còn.
- **Câu sửa:** E0 loại trừ ASR của current request khỏi vai trò nguyên nhân
  DUY NHẤT, nhưng KHÔNG test thông tin hoàn hảo. "Trần thông tin" là overstated;
  đúng hơn là "trần của việc sửa ASR current-request". History-ASR noise và
  intent errors vẫn là contributors chưa bị loại trừ bởi E0. V13 củng cố điểm
  này theo hướng khác: fill-act xảy ra cả khi ASR current sạch (§1.3), nên
  intent/fill mới là bottleneck đã chứng minh — nhưng đó là kết luận từ V13,
  không phải từ E0.

### 2.2 Sửa 2 — Chưa chứng minh "toàn bộ prompt/format/retry đã chạm trần"

- **Câu cũ (SOTA §0):** "prompt + format + retry đã hết dư địa", "không cài
  được bằng thêm chữ".
- **Phạm vi thực tế đã test:** (a) prompt rules chung (ACTION_POLICY +
  rule E5: "chỉ hỏi khi thiếu", vague ≠ cụ thể); (b) chuyển sang native
  format (E1 V10); (c) parser-retry với feedback format cụ thể (E6-C V11).
  Cả ba đều KHÔNG đụng tới cơ chế điền: không rule nào nóitường minh rằng
  current_time và giờ trong history KHÔNG phải giờ user yêu cầu, không
  feedback nào nói "time bạn điền không có trong request".
- **Chưa test, vẫn thuộc họ prompt/retry:** prompt loại trừ nguồntường minh
  (source-exclusion); feedback nhắm vào provenance ("time này lấy từ đâu?")
  thay vì feedback format; retry với yêu cầu trích dẫn nguồn của time.
- **Câu sửa:** Các biến thể prompt/format/retry ĐÃ TEST cho thấy diminishing
  returns, và cơ chế fill-act giải thích vì sao (model điền trước khi rule
  kịp chạy). Nhưng trần cho TOÀN BỘ họ này CHƯA được chứng minh — các biến
  thể chưa test vẫn có thể giảm fills ở mức xác suất. Lý do chọn guard trước
  prompt-variant không phải vì prompt đã "chết", mà vì guard là can thiệp
  duy nhất đảm bảo ở tầng thực thi + cho ra shadow audit đo được (§3). Nếu E7
  bị bác bỏ, prompt-variant là ứng viên tiếp theo, không phải đã bị loại vĩnh
  viễn.

### 2.3 Sửa 3 — Resolver ≠ ledger nguồn; validator và grounding đã có trong code

Ba tầng phải phân biệt rõ — bản SOTA đã gộp tầng 2 và 3:

| Tầng | Đã có trong code? | Chặn được gì | KHÔNG chặn được gì (bằng chứng V13) |
|---|---|---|---|
| **Simulator validator** (schema + required params) | Có (phía simulator) | Create thiếu time bắt buộc (0116-rule gen1: "thiếu tham số bắt buộc: time") | Mọi time đã điền đầy đủ và hợp schema — cả 5 fill-act đều pass validator, trả ok:true |
| **Grounding** (agent-side, chặn ID bịa/malformed trước thực thi) | Có (a2e832b) | cont_01 (0116-control, sai format ID), contact_mom (0287-control) — cả hai đều không tới TOOL event, đi qua retry path | Time/amount hợp dạng đã điền (2026-11-06T14:00, 100000, v.v.); ID thật nhưng sai người (chưa test, không được phép suy ra là chặn được) |
| **Closed-world resolver** (paper Iyer, arXiv:2609.19425) | Chưa có; là paper | H1–H3 + phần detectable của H5: tool không tồn tại, argument không khai báo, sai type/enum/range. Verified: 322 hallucinations đo được; fabricated tools tập trung ở raw-JSON (34 vs 3); "no honest over-rejection" CHỈ cho các class schema-detectable trong ablation (§VI) | **H5 residue: borrowed arguments schema-indistinguishable from a valid call** — paper tự xác định đây là phần dư không thể rút gọn (reducible to tool-selection). 5 time fill-act của V13 CHÍNH LÀ residue này: datetime hợp schema, mượn từ context |
| **Provenance ledger/guard** (đề xuất E7) | Chưa có; là brief mới | Time/amount phải truy được về request cụ thể / suy luận hợp lệ / observation có chủ đích (xem brief) — tầng DUY NHẤT trong bốn tầng chặn được fill-act | Chưa biết: false-block trên suy luận hợp lệ (refer-back, supersession) — phải đo bằng shadow audit trước GPU |

- **Câu cũ cần bỏ:** "resolver là bằng chứng mạnh nhất cho guard" và "reject
  toàn bộ hallucination". Sửa thành: resolver là tầng cần thiết cho H1–H3
  (phần lớn đã được validator + grounding bao phủ ở mức tương đương cho ID),
  nhưng PROVABLY không đủ cho vấn đề của V13 — chính paper resolver đã loại
  trừ residue này khỏi phạm vi của nó. Guard E7 không phải là "áp dụng
  resolver"; nó là một cơ chế STRICT HƠN (provenance, không chỉ schema), và
  rủi ro false-block của nó KHÔNG được thừa hưởng từ "no over-rejection"
  của resolver — phải đo riêng bằng shadow audit trên gold writes.
- **Số "13–57% raw-JSON hallucination" trong SOTA:** KHÔNG verify được từ
  abstract/intro đã đọc — bỏ khỏi mọi quyết định, thay bằng số đã verify:
  322 hallucinations (single-registry) + 154 (MCP), fabricated tools 34
  raw-JSON vs 3 schema-enforced. Tỷ lệ per-model không dùng cho quyết định
  nào trong báo cáo này.

### 2.4 Sửa 4 — Trích dẫn paper đã verify lại (model/benchmark/metric/phạm vi)

Quy tắc từ đây: số paper nào không có đủ 4 cột (model, benchmark, metric,
phạm vi) + link + vị trí thì không dùng để quyết định. Các số dưới đây đã
đọc primary (abstract và/hoặc bảng chính), không còn là snippet mù.

**When2Call — Ross et al., arXiv:2504.18851**
([paper](https://arxiv.org/html/2504.18851v1)):**

- Model: Mistral-NeMo-Minitron 4B/8B Base (MNM), baseline = SFT trên các
  dataset tool-calling open-source. KHÔNG phải Qwen.
- Benchmark: When2Call — multiple-choice đơn lượt, 4 hành vi (direct answer /
  tool call / follow-up question / unable to answer); dữ liệu tổng hợp từ
  BFCL v2 Live + APIGen qua Mixtral 8x22B; tiếng Anh; tool API.
- Metric + vị trí: Table 3 (§3.4) — MC Macro F1, length-normed Acc, Tool
  Hall% (định nghĩa: chọn tool-call khi KHÔNG có tool nào được cung cấp —
  KHÔNG phải tỷ lệ bịa parameter value); BFCL v2 Live AST Acc, BFCL
  Irrelevance Acc. Table 5 (§4.1) — so sánh MC F1 vs LLM-as-judge F1.
- Số đã verify (Table 3): MNM 4B baseline F1 29.7, Tool Hall 16%, BFCL AST
  57.9%, BFCL Irr 41.1% → When2Call-SFT F1 48.1, Tool Hall 4.3%, AST 51.7%
  (giảm 6.2pp — over-conservatism khi thêm negative examples, §3.4/§5) →
  When2Call-RPO F1 51.0, Tool Hall 1.9%, AST 54.0%, Irr 77.4%. LLM-as-judge F1
  (Table 5): 27.9 → 48.6 → 64.3. Training: 8 node NVIDIA 8xH100, ~3–4 giờ/model
  (§3.3); SFT LR 5e-6 (4B), RPO LR 9e-7, KL 0.05.
- Khoảng cách chuyển giao sang LifeMate (bắt buộc ghi): MC đơn lượt vs
  generation đa lượt; text tiếng Anh vs voice tiếng Việt qua ASR; follow-up
  TEXT question vs submitted sys.ask_missing_info call; MNM vs Qwen3-4B.
  Kết luận cho phép: SFT+RPO có mục tiêu CÓ THỂ dạy model 4B quyết định
  call/ask/unable trong setting MC. Kết luận KHÔNG cho phép: dự đoán mức tăng
  ask-first nào cho LifeMate, hay coi Tool Hall% là tỷ lệ bịa parameter.

**SAGE-Agent — Suri et al., arXiv:2511.08798
([paper](https://arxiv.org/html/2511.08798v1)):**

- Model/phương pháp: POMDP + EVPI trên structured uncertainty theo từng
  parameter; uncertainty-weighted GRPO.
- Benchmark: ClarifyBench — multi-turn disambiguation, user MÔ PHỎNG bằng
  LLM, domains document editing / vehicle control / travel booking.
- Số (ABSTRACT, bảng chưa kiểm tra): coverage +7–39%, số câu hỏi làm rõ
  giảm 1.5–2.7×; When2Call accuracy 3B 36.5% → 65.2%, 7B 36.7% → 62.9%.
  Base model family không ghi trong abstract — không trích Qwen2.5 khi chưa
  verify bảng.
- Khoảng cách: user mô phỏng (không phải user thật), không voice, không
  tiếng Việt, domains khác reminders. Dùng làm hướng thiết kế gate (step-0
  slot gate), không phải bằng chứng hiệu quả cho LifeMate.

**CAST — arXiv:2608.30147, §4.2 Table 1 + abstract
([paper](https://arxiv.org/html/2608.30147)):**

- Model: CAST-Policy-4B/8B (fine-tune từ base instruct; dữ liệu từ τ-Bench
  Retail split 500 tasks, teacher Qwen3-32B assistant + Qwen2.5-72B user sim).
- Benchmark: τ-Bench Retail (in-domain), Airline/Telecom/Telehealth
  (out-of-domain); tiếng Anh e-commerce.
- Số đã verify (§4.2): CAST-Policy-4B vs base instruct: **+18.9% pass^1,
  +10.4% pass^4** trên Retail. **Sửa số cũ "+22.6% pass^1" trong SOTA: số này
  không verify được — bỏ, dùng +18.9%/+10.4%.** Abstract: vượt GPT-OSS-120B
  hơn 10% pass^4 trên Retail; +9% Telehealth out-of-domain (abstract claim).
- Khoảng cách: retail ≠ voice reminders; fine-tuning bằng teacher
  trajectories ≠ prompt/guard; pass^k (reliability qua lặp) ≠ ask-first.
  Phần portable duy nhất sang LifeMate là nguyên tắc verify-before-write
  ("chỉ chấp nhận giá trị xuất hiện trong nguồn grounding cho phép") — và
  nguyên tắc đó, khi áp cho time, chính là guard E7 (phiên bản code, không
  phải phiên bản training).

**Closed-world resolver — Iyer, arXiv:2609.19425, abstract + §I/§III/§IV/§VI
([paper](https://arxiv.org/html/2609.19425)):**

- Xem §2.3. Nhấn mạnh lại: paper tự định vị là "measurement and benchmark
  study", resolver là "reference point", và residue H5 là ngoài phạm vi.
  Mọi câu trong SOTA dùng resolver để hứa hẹn chặn invented values đều bị
  thay thế bởi §2.3.

**Các số còn lại trong SOTA ở mức [SNIP] — hạ cấp, không dùng để quyết định:**
XGrammar-2 BFCL (Llama-3.2-3B 33.12→77.75%), ToolDec, CLAM, MAST, DeReAct,
MDPI verification, FlowMind, ECLM, ProGRes, WCN — tất cả vẫn ở mức snippet,
chưa đọc primary PDF trong đợt này. Chúng giữ vai trò định hướng, và bất kỳ
quyết định nào dùng tới chúng sau này đều phải verify primary trước.
Đặc biệt: hướng constrained decoding (rank 2 trong SOTA) vẫn mở, nhưng số
BFCL của nó hiện KHÔNG phải bằng chứng decision-grade; nó không được dùng
để biện minh cho E7 hay bất kỳ run GPU nào cho tới khi verify xong, và nó
vẫn phụ thuộc câu hỏi organizers (XGrammar trên Docker A30) chưa được gửi.

## 3. So sánh ba lựa chọn (và một dự bị)

| Tiêu chí | A. Mở rộng E5 (+28 mẫu) | B. Guard nguồn time/amount (E7) — CHỌN | C. Sửa boundary pseudo-call | D. Prompt loại trừ nguồn (dự bị) |
|---|---|---|---|---|
| Lỗi nhắm tới | Đo lại hiệu ứng rule (chưa biết mechanism khi đăng ký) | Đúng 5/7 fill-act + leak 0353 + fill control (0823 chờ trace) | Pseudo-ask hậu-read (0653) | Fill-act (gián tiếp, qua wording) |
| Bằng chứng | Cơ chế đã biết; fill-act ở cả 3 subgroup → hệ thống, không phải nhiễu | Truy nguồn xong 5 time + 1 leak; 0 từ request; pattern giờ tròn/clock/leak rõ | 1/20 mẫu, cả hai arm giống nhau, 0 first-call outcome | Chưa test; ruletường minh đã từng bị vi phạm (E1 rules 2/4/5) |
| Chi phí | ~56 trial GPU (~900s+ theo tốc độ V13) + phân tích | Shadow audit CPU-only (giờ phân tích, 0 GPU) + 40 trial GPU (~643s theo V13) | Code + CPU tests (rẻ); rerun verify sẽ làm nhiễu nếu gộp với B | 40 trial GPU + CPU prompt tests |
| Điều chưa biết lớn nhất | 28 mẫu có subgroup/fill-source mới không? (không đổi quyết định dù đáp án nào) | False-block trên suy luận hợp lệ (refer-back, supersession); phản ứng sau block (ask/stop/refill) | False-positive trên prose thật (prose có nhắc tên tool) | Model có áp dụng loại trừ lúc sinh không, và fail thì do wording hay cơ chế? |
| Kết quả quyết định được | Xác nhận rule yếu có generalize không — nhưng dù +3 cũng không adopt được khi chưa sửa fill; dù 0 cũng vẫn cần guard | Có: guard chuyển fill→ask được hay không; false-block bao nhiêu; model phản ứng sau block ra sao | Chỉ đổi phân loại channel, không đổi task success | Chỉ xác suất giảm fills, không đo được cơ chế |
| Verdict | HOÃN (đăng ký lại sau E7) | CHỌN | Song song CPU-only, reporting-only, không đổi parser | Dự bị nếu E7 bị bác qua block→stop |

Lý do A thua B dù A là nhánh preregistered của INCONCLUSIVE: preregistration
ghi "mở rộng khi +1" trước khi biết cơ chế; bây giờ cơ chế đã biết và nó đặt
trần cấu trúc cho rule (fill thì rule vô dụng). Chạy A bây giờ là đo lại trần
đã biết. Hoãn A có lý do và có điều kiện quay lại rõ ràng (sau E7, đăng ký
mới) — đó là tôn trọng preregistration đúng nghĩa, không phải phá vỡ nó.
Lý do C thua B: C sửa cách ĐO một lỗi đã xảy ra sau read; B sửa lỗi GÂY RA
fail ở first call. Thứ tự đúng là sửa lỗi trước, sửa thước đo sau (và sửa
thước đo bằng reporting trước, parser sau, để không làm nhiễu phép đo lỗi).

## 4. Quyết định và điều gì sẽ làm thay đổi nó

**Làm E7 theo brief đính kèm.** Shadow audit là cửa bắt buộc: nếu shadow
audit cho thấy (i) guard không chặn được đủ 6 fill đã biết, hoặc (ii) có
false-block trên gold writes mà spec không sửa được nếu không cho qua cả
fill, thì DỪNG trước GPU, báo cáo xung đột spec, và chuyển sang D
(prompt-variant) + C (reporting). Nếu E7 chạy và bị bác bỏ qua nhánh
block→stop (guard chặn nhưng model dừng thay vì hỏi), thì ứng viên tiếp theo
là guard + ask-routing (block xong tự route sang ask cho param thiếu) — đó
là HAI biến (block + routing), nên nó là thí nghiệm RIÊNG sau E7, không gộp
vào E7. Nếu E7 CONFIRMED, thì bước sau là rule+guard kết hợp trên tập 20 rồi
mới xét mở rộng 28 với preregistration mới.

---
*Nguồn: E5 V13 audit + verified_comparison + diagnostic_trace +
plain_text_stop_review (main 8846ab1); gold transcripts/context/history từ
train release v3.2.0 (chẩn đoán sau chạy, không phải input agent); SOTA
c962d174; papers đã verify ở §2.4. Proxy là ENGINEERING_PROXY_NOT_OFFICIAL;
official evaluator vẫn chưa có.*
