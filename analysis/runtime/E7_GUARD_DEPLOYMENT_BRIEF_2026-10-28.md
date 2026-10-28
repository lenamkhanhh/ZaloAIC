# E7 Deployment Brief: narrow time/amount provenance guard (shadow audit first)

**Chỉ brief triển khai + tài liệu. KHÔNG sửa inference, KHÔNG chạy model/GPU
trong đợt này, KHÔNG held-out, KHÔNG hardcode probe vào agent/prompt/spec,
KHÔNG liên hệ ai. Mọi ID mẫu dưới đây là tập đo cố định (dev), không phải
input của agent. Spec của guard chỉ chứa quy tắc provenance chung + ví dụ
tổng hợp (không có ID/giá trị mẫu thật).**

**Designation:** E7 (đề xuất — xác nhận tên trước khi launch; không trùng với
E6-B/E6-C, không phải E5 mở rộng).

## 1. Giả thuyết (falsifiable)

**H:** Một guard bằng code, chặn write trước khi thực thi khi argument
time/amount của nó không truy được về (a) giá trị cụ thể trong current
request, (b) suy luận hợp lệ từ tham chiếu trong request (xem §4), hoặc (c)
observation/history mà request chỉ đích danh (và chưa bị thay thế), và trả
về feedback chỉ nêu LÝ DO block (không ra lệnh hỏi), sẽ chuyển các lỗi
fill-act của V13 thành ask đúng ở first call trên TARGET, mà không chặn bất
kỳ gold write hợp lệ nào trong shadow audit.

**H0 (null):** Guard chặn nhưng TARGET ask-first net ≤ 0 (model dừng hoặc
điền lại thay vì hỏi), HOẶC guard chặn gold write hợp lệ (spec sai).

**Cơ chế H nhắm tới (đã chứng minh ở V13):** model điền time từ context
(current_time copy, current_time date + giờ tròn tiếp theo, leak history
việc khác, concretize tham chiếu mơ hồ) rồi act ngay, khiến điều kiện "hỏi
khi thiếu" không bao giờ kích hoạt. Guard tấn công đúng chặng "điền → thực
thi": write có time không nguồn bị chặn trước khi đổi state, buộc model phải
chọn lại (hỏi / dừng / điền khác) — và lựa chọn đó chính là thứ được đo.

## 2. Base commit, đối chứng, đúng một biến thay đổi

- **Base commit: a472006** (giống V13: native V10 + E6-C parser).
  Cả hai arm dùng base này, không đổi gì khác.
- **Control arm (fresh, chạy lại trong E7):** cấu hình V13 control Y HỆT —
  không rule E5, không guard, không đổi prompt, không đổi parser, ASR cache
  v12 (rev a86b604, hash verify trước run), greedy seed 42, FP16/T4x2,
  max_steps 12, max_repeats 2, context 16384/output 512, grounding BẬT,
  proxy scorer như V13. Chạy lại control thay vì reuse số V13 để loại trừ
  harness drift (guard thay đổi loop interception point, nên control phải ở
  cùng run).
- **Trial arm:** control + guard (§4). KHÔNG có gì khác.
- **Đúng một biến:** guard interception (code, pre-execution check +
  feedback lý do). Cụ thể KHÔNG đổi: không rule E5 trong cả hai arm (kết hợp
  rule+guard là thí nghiệm RIÊNG sau E7, không gộp); không đổi parser
  (key=value giữ reporting-only, xem §7); không đổi prompt (hash prompt
  phải bằng V13 control — CPU gate G4); không đổi ASR/model/seed/config;
  không đổi tập mẫu; không đổi metric/scorer.
- **Feedback của guard:** CHỈ nêu fact ("blocked: time argument has no source
  in the current request and is not derivable from it"), KHÔNG ra lệnh "hãy
  hỏi". Lý do: nếu feedback ra lệnh hỏi, không phân biệt được ask đến từ
  guard hay từ lệnh. Model tự chọn bước tiếp theo sau block — và ask/stop/
  refill chính là hành vi cần đo. Guard không bao giờ tự sinh call, không
  bao giờ convert prose thành call. Mỗi block tốn 1 attempt (giống
  validation rejection), loop tiếp tục bình thường.

## 3. Tập dev cố định

- **20 mẫu E5 y hệt V13:** 7 TARGET + 13 CONTROL, cùng ASR cache v12.
  Không thêm 28 mẫu (đó là extension hoãn lại, đăng ký riêng sau E7).
  Không held-out, không training, không đổi mẫu giữa chừng.
- **Lý do giữ nguyên 20:** giả thuyết guard nhắm vào 5 fill-act đã biết
  trong 20 này; đo trên cùng tập cho so sánh trực tiếp với V13 (control 0/7
  target, 0/13 control; rule 1/7, 0/13). Tập 28 là câu hỏi khác (generalize),
  không phải câu hỏi của E7 (mechanism).

## 4. Spec của guard (generic — không chứa giá trị mẫu thật)

Guard chạy trên MỌI proposed write (state-changing call) trong loop, trước
validator/simulator. Guard kiểm tra từng argument thuộc loại thời gian
(datetime/time/date) và số tiền/số lượng (amount/quantity/threshold) theo
catalog tool (không liệt kê theo mẫu). Một write bị block khi BẤT KỲ argument
time/amount nào của nó không đạt một trong các allow rule dưới đây.
Partial provenance = block (write là atomic: date suy ra được nhưng giờ
không suy ra được thì vẫn block, vì write mang cả datetime).

**Allow rules (guard CHO QUA):**

- **A1 — Giá trị cụ thể trong current request:** time/amount xuất hiện tường
  minh trong current request (dạng ASR mà model nhìn thấy, xem lưu ý ASR ở
  §6). Ví dụ tổng hợp: request "lúc 9 giờ tối" → write với 21:00 được qua;
  request "50 nghìn" → amount 50000 được qua.
- **A2 — Suy luận hợp lệ từ tham chiếu trong request:** date arithmetic từ
  tham chiếu thời gian trong request ("ngày mai" → date của ngày mai;
  "thứ Hai tới" → date đó; "tuần sau" → khoảng date đó). LƯU Ý: tham chiếu
  mơ hồ chỉ cho DATE, không cho GIỜ — "sáng mai" cho date ngày mai nhưng
  không cho giờ nào; write kèm giờ default vẫn block. Chuyển đổi đơn vị/
  diễn đạt số trong request ("một nửa" → 50; "50 nghìn" → 50000) được qua
  nếu mapping là xác định.
- **A3 — Observation có chủ đích (pointed observation):** giá trị do tool
  trả về cho đúng entity mà request nhắc tới (amount của đúng hóa đơn user
  hỏi, lấy từ list_bills; time của đúng event user muốn đổi, lấy từ
  list_events; ID của đúng người user nêu, lấy từ contacts.search).
  "Có chủ đích" = entity khớp với request, không phải bất kỳ observation nào
  chứa giá trị đó.
- **A4 — Refer-back tường minh + chưa bị thay thế:** giá trị trong history
  mà current request nhắc lại tường minh ("như hôm qua", "lúc giờ họp hôm
  qua", "giờ như lần trước") VÀ không bị supersession. Nếu request nói
  "mới nhất" / "lời dặn mới nhất" / "đã đổi", mọi giá trị history trước thời
  điểm cập nhật đó đều bị loại (quy tắc supersession — trường hợp khó nhất,
  xem §8).

**Block rules (guard CHẶN):**

- **B1 — Clock-derived:** time lấy từ current_time (copy nguyên giờ hiện tại,
  hoặc date hôm nay + giờ tròn tiếp theo, hoặc date ngày mai + giờ default)
  khi request không cho time. Current_time là context, không phải request.
- **B2 — History không refer-back:** time/amount trong history mà current
  request không nhắc lại (kể cả time của event khác trong lịch history).
- **B3 — Superseded history value:** giá trị history đã bị request hiện tại
  thay thế ("mới nhất", "đã đổi", "không theo cái cũ nữa").
- **B4 — Concretize tham chiếu mơ hồ:** giờ cụ thể gán cho tham chiếu mơ hồ
  ("sáng mai" → 08:00; "chiều" → 15:00; "tối" → 20:00) khi request không cho
  giờ. Phần date có thể suy ra, phần giờ thì không — và write mang cả hai
  nên block.
- **B5 — Pure invention:** giá trị không có nguồn nào trong request/history/
  observation (kể cả số tròn "đẹp" không truy được).

**Phạm vi tool/arg (theo catalog, không theo mẫu):** mọi write có argument
datetime/time/date/start/end (reminders.create time, calendar.* start/end,
alarm.* time, video_meeting.create start, …) và amount/quantity/threshold
(ewallet.transfer amount, bill_payment.* amount, home_energy.set_alert
threshold_kwh, …). **Reads KHÔNG thuộc phạm vi guard** (read không đổi state;
filled read param như flights.search date là lỗi nhẹ hơn, ghi nhận làm
limitation/future work, không chặn trong E7 — chặn read sẽ là overreach và
là biến thứ hai). **Asks (sys.ask_missing_info) KHÔNG bị guard** (meta call,
không phải write).

**Ví dụ tổng hợp (không phải dữ liệu mẫu thật):** request "nhắc tôi chúc
mừng sinh nhật Lan" (không giờ) → write reminders.create với time bất kỳ =
block (B1/B5). Request "nhắc tôi gọi cho Lan lúc 9 giờ tối" → write với
21:00 = allow (A1). Request "nhắc tôi uống thuốc sáng mai" → write với
ngày mai + 08:00 = block (B4, giờ không nguồn). Request "trả hóa đơn nước
tháng này" sau list_bills trả về hóa đơn nước 212000 → write amount 212000
cho đúng hóa đơn đó = allow (A3); amount khác = block.

## 5. CPU gates — bắt buộc trước GPU (fail gate nào thì dừng, không chạy GPU)

- **G1 — Spec hygiene:** spec + code guard không chứa sample ID, sample
  value, transcript fragment, tên entity mẫu, hay enumeration gold asks.
  Chỉ chứa quy tắc chung + ví dụ tổng hợp (§4). Check bằng grep + review tay.
- **G2 — Shadow audit (xem §6):** đạt đủ 3 ngưỡng: (i) chặn đủ 6 fill đã biết
  trong V13 (5 target fill + 1 control leak); (ii) gold false-block = 0 trên
  tập gold writes quét được (xem §6); (iii) synthetic tests 100% pass.
  Thiếu ngưỡng nào → sửa spec → audit lại. Không chạy GPU trên spec hỏng.
- **G3 — Unit tests (tổng hợp, không dữ liệu mẫu):** mỗi allow/block rule có
  ít nhất 1 test pass; prose stop không bị guard chạm (guard chỉ chạy trên
  proposed write, không bao giờ chạy trên generation text); guard không sinh
  call; block tốn đúng 1 attempt; feedback không chứa lệnh "hãy hỏi".
- **G4 — Prompt/config freeze:** hash prompt của cả hai arm E7 bằng hash
  prompt V13 control (guard là code, không thêm token prompt); parser freeze
  ở scope E6-C (key=value chỉ reporting, §7); ASR cache v12 hash verify;
  seed/config giống V13. Sai hash nào → dừng, không chạy.
- **G5 — Independent spec re-derivation:** một reviewer độc lập suy lại
  spec từ catalog + gold asks (không nhìn code guard) và đối chiếu: mọi
  allow/block rule phải khớp. Lệch → sửa spec hoặc code rồi audit lại.

## 6. Shadow audit (Phase 0, CPU-only) — cửa bắt buộc, cũng là deliverable

Shadow audit chạy guard logic OFFLINE (không thực thi, không đổi state) trên
ba tập, và phải công bố cả ba trước khi xin chạy GPU:

1. **40 traces V13 (20 mẫu × 2 arm):** phân loại MỌI proposed write
   (submitted + validator-rejected) theo provenance (§4), và ghi quyết định
   would-block/would-allow của guard cho từng argument time/amount. Yêu cầu:
   would-block đủ 6 fill đã biết (5 target fill-act + leak control) — thiếu
   cái nào là spec bug.
2. **Gold writes (false-block check):** gold first call của 20 mẫu đều là
   ask nên không đo được false-block ở đó — vì vậy quét CPU-only gold writes
   trên phần còn lại của dev (không phải 20, không phải held-out) để thu thập
   các pattern suy luận hợp lệ (request-specific time, date derivation,
   pointed-observation amount, refer-back). Yêu cầu: guard allow 100% gold
   writes hợp lệ trong tập quét; mỗi block là một spec bug phải sửa hoặc một
   limitation phải ghi rõ. Nếu có pattern hợp lệ không thể allow nếu không
   cho qua cả fill đã biết → STOP, không chạy GPU, báo cáo xung đột spec
   (đây là kết quả có giá trị, không phải thất bại im lặng).
3. **ASR-vs-gold gap:** guard live nhìn ASR, không nhìn gold. Với mỗi
   argument, báo cáo cả hai verdict: provenance theo GOLD và provenance theo
   ASR mà model nhìn thấy. Chênh lệch (gold-allow nhưng ASR-block, ví dụ giờ
   trong gold request bị ASR làm mất) là limitation của ASR, không phải spec
   bug — nhưng phải đếm riêng, vì nó giới hạn hiệu năng live của guard.
   Ngược lại, ASR-allow nhưng gold-block (ASR bịa thêm giờ khớp pattern?)
   cũng phải đếm — đó là lỗ hổng guard qua ASR.

**Ngoài ra, shadow audit phải truy nguồn cho mọi write trong 20 mẫu, kể cả
control** (đặc biệt WATCH 0823: start 10:00 của event calendar — báo cáo V13
chưa truy nguồn này). Bảng provenance đầy đủ của 20 mẫu là một phần của
deliverable shadow audit, không phải phụ lục tùy chọn.

## 7. Key=value reporting (song song, CPU-only, KHÔNG đổi parser)

- Preregister hạng mục BÁO CÁO mới: `PSEUDO_KEYVALUE_AFTER_CALL` cho
  generation có dạng `sys.ask_missing_info tool_name=<name> params=[...]`
  (khớp hẹp: đúng prefix + key=value, không parenthesis). Hạng mục này chỉ
  xuất hiện trong báo cáo/manual review, KHÔNG thay đổi parser, KHÔNG thay
  đổi scoring, KHÔNG đổi verdict. Parser E7 freeze ở scope E6-C.
- Test an toàn prose: 19 plain-text stops của V13 (prose xác nhận "Đã tạo…",
  tóm tắt hóa đơn, v.v.) phải KHÔNG bị flag bởi pattern — pattern quá rộng
  mà flag prose là fail gate, phải thu hẹp trước khi dùng cho bất kỳ run nào.
- Việc đổi parser thật (biến key=value thành caught) là thí nghiệm RIÊNG
  sau E7, với CPU gate + preregistration riêng, vì nó thay đổi channel
  metrics và sẽ làm nhiễu phép đo guard nếu gộp vào.

## 8. Metric, tiêu chí bác bỏ, nguy cơ chặn nhầm

**Metric chính:** TARGET ask-first (định nghĩa y hệt E5: first submitted
call bằng đúng gold ask theo tool_name + params set; 0 call = FAIL; write
trước ask = FAIL; sai target = FAIL), so với fresh control trong cùng run E7.

**Metric phụ (bắt buộc báo cáo, không chỉ net):**

- CONTROL ask-first + bảng thay đổi hành vi control→trial (cùng format §1.5
  của báo cáo V13: đổi first call nào, thêm/bớt stop nào) — net 0 không được
  dùng làm bằng chứng không có tác dụng phụ.
- Fill-act rate: số first write có time/amount không nguồn / tổng first
  write ở TARGET (guard phải làm số này giảm).
- Guard block rate + breakdown sau block: block→ask (đúng gold ask),
  block→ask sai params, block→stop, block→refill (điền giá trị khác rồi
  write lại — ghi rõ giá trị mới và nguồn của nó; refill qua một read trung
  gian để "lau" provenance là cơ chế lách cần báo cáo riêng, không tính là
  pass).
- Channel metrics theo counting rules của handoff c8a7d46 (theo generation,
  không cộng dồn event validator; outcome theo trace; silent theo định nghĩa
  ĐÃ ĐĂNG KÝ + hạng mục key=value reporting riêng ở §7).
- False-block live: số lần guard chặn một call khớp gold (trên các step sau
  first call + tập quét §6) — phải là 0; nếu > 0 thì đó là spec bug, báo cáo
  như một kết quả, không giấu.

**Tiêu chí bác bỏ (preregistered, đọc trước khi chạy):**

- **CONFIRMED:** TARGET net ≥ +2 vs fresh control, VÀ gold false-block
  (shadow + live) = 0, VÀ block→stop conversions = 0.
- **PARTIAL:** TARGET net = +1, HOẶC net ≥ +2 nhưng block→stop ≥ 1, HOẶC ask
  tăng nhưng exact ask-first phẳng (hỏi nhiều hơn nhưng sai params — như
  0353). PARTIAL thì phân tích nhánh nào còn lại, không adopt.
- **REFUTED:** TARGET net ≤ 0 với false-block = 0 (guard chặn nhưng model
  dừng/điền lại thay vì hỏi — ép ở tầng thực thi không sinh ra ask).
  REFUTED thì ứng viên tiếp theo là guard + ask-routing (block xong tự route
  sang ask cho param thiếu) — là thí nghiệm RIÊNG, không phải patch cho E7.
- **INVALID (không có verdict GPU):** shadow gold false-block > 0 không sửa
  được, HOẶC known fills không bị chặn đủ trong shadow, HOẶC prompt/parser/
  ASR hash lệch (G4 fail) → dừng trước GPU, sửa spec/harness, audit lại.

**Nguy cơ chặn nhầm (false-block) — liệt kê trước, đo trong shadow audit:**

1. **Refer-back bị chặn nhầm:** request nhắc lại giờ cũ ("như hôm qua") mà
   guard xếp là history không refer-back → block write hợp lệ. Mitigation:
   rule A4 + quét gold để thu thập pattern refer-back thật trước GPU.
2. **Supersession hai chiều:** chặn nhầm giá trị history vẫn còn hiệu lực,
   hoặc cho qua giá trị đã bị thay thế (pattern 0780). Đây là risk cao nhất
   vì nó đòi hiểu "mới nhất" — guard dùng marker từ vựng ("mới nhất", "đã
   đổi", "không theo cái cũ") làm heuristic, và mọi case marker mơ hồ đều
   phải vào báo cáo shadow audit dưới dạng limitation, không được silent
   allow/block.
3. **Date-vs-hour boundary:** write mang cả date (suy ra được) + giờ (không
   suy ra được) — guard block cả write (đúng theo atomic rule §4), nhưng
   điều này có thể chặn một write mà phần lớn thông tin là đúng. Đây là
   thiết kế có chủ ý (không cho qua write nửa-đúng), và phải báo cáo số lần
   nó xảy ra trong shadow audit.
4. **ASR gap (§6.3):** giờ hợp lệ trong gold nhưng mất trong ASR → guard
   live block nhầm. Đếm riêng, không đổ cho spec.
5. **Amount derivations:** "50 nghìn" → 50000, "một nửa" → 50%, chuyển đổi
   đơn vị — rule A2 phải bao phủ các mapping số học xác định trong request,
   nếu không guard sẽ block amount hợp lệ. Shadow audit phải có test amount
   riêng, không chỉ time.

## 9. Chi phí dự kiến và thứ tự thực hiện

1. **Phase 0 — Shadow audit + CPU gates (0 GPU):** viết spec + code guard
   (offline logic, không gắn vào loop chạy thật cho tới khi gates pass),
   chạy shadow audit trên 40 traces V13 + quét gold writes dev + synthetic
   tests + prompt/parser/ASR hash checks. Công việc phân tích tính bằng giờ,
   không tốn GPU. **Chỉ khi G1–G5 pass mới xin chạy GPU.**
2. **Phase 1 — GPU run (40 trials):** control fresh + trial guard trên 20
   mẫu, cùng cấu hình V13. Ước tính ~643s gồm setup theo tốc độ V13 (T4x2
   FP16, comparative — KHÔNG phải bằng chứng A30). Không training, không
   đổi model, không held-out.
3. **Phase 2 — Phân tích:** per-sample theo counting rules handoff, bảng
   provenance, breakdown sau block, bảng control behavior-change, verdict
   theo §8. Không adopt, không mở rộng, không đổi spec sau khi thấy kết quả
   — mọi phát hiện sau run đều vào báo cáo, không sửa ngược metric.

**Không làm trong E7:** không rule E5, không đổi parser, không đổi prompt,
không đổi ASR, không tập 28, không held-out, không training, không liên hệ
organizers (các câu hỏi XGrammar/param-count vẫn mở, không liên quan E7),
không hardcode bất kỳ ID/giá trị mẫu nào vào spec/code guard.

---
*Base: a472006. Tham chiếu: E5 V13 audit (8846ab1), báo cáo phân tích sâu
E5 V13 cùng đợt, handoff c8a7d46 (counting rules), brief E5 ab780806 (tập 20
mẫu, định nghĩa ask-first). Proxy là ENGINEERING_PROXY_NOT_OFFICIAL.*
