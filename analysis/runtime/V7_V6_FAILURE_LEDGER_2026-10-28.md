# V6/V7 failure ledger — phân loại lỗi theo bằng chứng đầu vào

Ngày: 2026-10-28. Phân tích artifact, không sửa code, không chạy model,
không dùng held-out, không hard-code đáp án probe. Đây là tài liệu chẩn
đoán (DIAGNOSTIC_ONLY), không phải input cho agent hay ví dụ huấn luyện.

## 0. Nguồn và phương pháp — đọc trước khi tin bất kỳ con số nào

- Hướng dẫn phân tích: `analysis/runtime/README.md` tại main `800c34f`
  ("Analysis: publish audited V6/V7 model failure traces for research").
  Đọc theo thứ tự README chỉ định: V7 audit → trace v7 → V6 audit.
- Trace: `analysis/runtime/v7_diagnostic_trace.json` (8 trial, live ASR)
  và `v6_diagnostic_trace.json` (10 trial = 5 mẫu × 2 arm). Trace chỉ chứa
  ASR của model, raw output, call đã chạy và tool feedback; KHÔNG chứa
  full prompt, gold call, context/state dump, audio hay weights. Mọi đối
  chiếu gold trong tài liệu này lấy từ bản train release đã kiểm chứng
  (SHA256) tại máy phân tích, tra theo sample ID — không lấy từ trace.
- Code giải thích trace: **V7 = nhánh `codex/lifemate-baseline-integration`
  commit `a2e832b`; V6 = core `a9d48d2` (cùng nhánh, commit cũ hơn).**
  Code inference trên main KHÁC code đã chạy và KHÔNG được dùng để giải
  thích trace (đúng cảnh báo trong runtime README).
- Scorer trong trace là ENGINEERING_PROXY_NOT_OFFICIAL, công thức đã đọc
  từ code nhánh (`lifemate/scoring.py`): `score = f1 nếu hash đúng, else 0`;
  một call khớp chỉ khi cùng tên tool, cùng tập key đối số, và giá trị
  không-fuzzy bằng nhau tuyệt đối (param fuzzy: token-F1 > 0,6); khớp
  một-một, không kể thứ tự. Hệ quả: hash đúng vẫn score 0 nếu F1 = 0
  (gặp ở 0116-v7 và 0004-v7); đọc §5 trước khi kết luận "model kém".
- **Cảnh báo về trường `asr_current` trong trace v6:** kiểm chứng trực
  tiếp cho thấy field này GIỐNG HỆT nhau giữa hai arm cached_asr và
  gold_current ở cả 5 mẫu. Nó không ghi lại transcript vàng đã đưa vào
  arm gold-current; khác biệt input giữa hai arm chỉ được audit xác minh
  qua so sánh initial prompt, không nhìn thấy từ field này. Khi tài liệu
  này nói "arm gold-current có transcript chuẩn", căn cứ là audit đó,
  không phải field `asr_current`.
- Kiểm chứng chéo đã làm: V7 live ASR (current + history) trùng khớp
  tuyệt đối với V6 cached ASR ở cả 5 mẫu chung — so sánh v6↔v7 trên 5
  mẫu chung là so sánh cùng input. V6: 37 generation, 27 tool execution,
  1 validation_rejected. V7: 20 generation, 11 tool execution, 3
  validation_rejected (cả 3 đều của 0003).

## 1. Bảng tổng quan 18 trial (proxy = engineering proxy, không phải điểm chính thức)

| Trial | Proxy | Hash | F1 | Nộp/gold | Kết cục một dòng |
|---|---|---|---|---|---|
| v6 0019 cached / gold | 1 / 1 | đúng | 1 | 0/0 | Dừng đúng (app không cài) |
| v6 0116 cached / gold | 0 / 0 | sai | 0 | 3/1, 4/1 | Bịa giờ 11:00, tạo→xong→tạo lại |
| v6 0025 cached | 0 | sai | 0 | 0/5 | ASR nát → dừng ngay |
| v6 0025 gold-current | 0 | sai | 0,154 | 8/5 | Khởi động đúng (forecast) rồi trật: event bịa, reminder lạ, stop-as-tool, huỷ trùng |
| v6 0003 cached / gold | 0 / 0 | sai | 0 | 2/5 | Bịa contact/phone/amount, không đọc bill/contact |
| v6 0008 cached / gold | 0 / 0 | sai | 0 | 4/1 | Sửa alarm TRƯỚC khi xem forecast (gold-current còn ghi label "nếu mưa" lên alarm) |
| v7 0019 | 1 | đúng | 1 | 0/0 | Dừng đúng |
| v7 0116 | 0 | đúng | 0 | 1/1 | Hỏi sai câu: phone.call/contact_id thay vì reminders.create/time |
| v7 0025 | 0 | sai | 0 | 0/5 | ASR nát → dừng ngay (giống v6 cached) |
| v7 0003 | 0 | sai | 0 | 0/5 | Ask sai format ×3 trong 1 step, 0 call được chạy |
| v7 0008 | 0 | sai | 0 | 2/1 | Sửa alarm 2 lần, KHÔNG BAO GIỜ xem forecast |
| v7 0016 | 0 | sai | 0 | 0/5 | ASR nát phần hành động → dừng ngay |
| v7 0049 | 0 | sai | 0 | 5/4 | Trả nhầm bill điện thoại, mở tiết kiệm sai hướng, lặp call done:false |
| v7 0004 | 0 | đúng | 0 | 3/2 | Trạng thái cuối ĐÚNG (đèn 50) nhưng proxy 0: read có filter, thừa arg power, ghi trùng |

V7 mean proxy 0,125 trên 8 mẫu KHÔNG so được với v6 mean 0,2 trên 5 mẫu
(khác mẫu số). Trên cùng 5 mẫu chung, proxy mean v6 cached = v7 = 0,2:
**không có cải thiện điểm nào được chứng minh**, và cũng không có bằng
chứng regression từ hai mean này.

## 2. Ledger xếp hạng (một trial có thể mang nhiều nhãn; nhãn chính in đậm)

### Hạng 1 — Chọn sai intent / entity / nhánh (xuất hiện ở 10/18 trial)

Đây là họ lỗi lớn nhất, và nó tồn tại độc lập với ASR.

- **0116-v7 (bằng chứng sạch nhất):** ASR gần như trùng transcript vàng
  ("ờ nhắc tôi gọi điện cho mẹ với nha"). Model hỏi `phone.call/
  contact_id` thay vì `reminders.create/time`. "Nhắc + gọi điện" bị đọc
  thành gọi ngay thay vì tạo reminder. Không liên quan ASR, không cần
  observation nào thêm — phân loại intent thuần túy. Tiến bộ so với v6
  (không còn bịa giờ/tạo/xoá) nhưng vẫn sai câu hỏi, nên hash đúng mà
  score vẫn 0.
- **0116-v6 (cả hai arm):** bịa giờ 11:00 (user không cho giờ nào), tạo →
  complete → tạo lại. Lỗi intent (không hỏi) + termination (xong rồi
  còn tạo lại).
- **0008-v6 và v7:** gold chỉ có 1 call là xem forecast ngày 2026-11-14
  (rain:false → không làm gì). Model cả hai bản đều sửa alarm sang
  07:30 trước khi xem forecast. Phép tính 07:00 + 30 phút là đúng, nhưng
  nhánh mưa được thực thi vô điều kiện. History cho thấy alarm còn lại
  sau khi xoá alm_01 là 07:00 (alm_02) nên ID suy ra đúng — lỗi không nằm
  ở ID mà ở thứ tự điều kiện. Policy điểm 2 của a2e832b
  ("condition-before-write") không cứu được mẫu này.
- **0049-v7:** gold là trả tiền mạng cho chủ nhà Phạm Hùng, lấy từ tiết
  kiệm (acc_02) nếu tài khoản thanh toán không đủ: list_bills{} →
  get_balance{} → list_beneficiaries{} → transfer acc_02→ben_03 221000.
  Model lọc `list_bills(type=phone)` lấy bill_01 điện thoại 200000 (sai
  bill), trả bill đó, rồi mở tiết kiệm TỪ acc_01 (sai hướng: gold dùng
  tiết kiệm làm NGUỒN, model dùng tiết kiệm làm ĐÍCH), và không bao giờ
  liệt kê beneficiaries nên ben_03 không bao giờ được giải quyết.
- **0003-v6 (cả hai arm):** không đọc bill/contact mà bịa
  contact_001/002, phone 0901234567, amount 500000 (gold: topup phone
  09919377320 50000 sau khi search "Bác Ba", transfer c_06 845000 sau khi
  search "Cô giáo Mai" và đọc bill). Arm gold-current đổi được action đầu
  sang topup nhưng vẫn bịa số — ASR sửa được chọn tool, không sửa được
  provenance của đối số.
- **0025-gold-v6:** có transcript chuẩn vẫn huỷ event_12345 bịa (2 lần,
  done:false cả hai), tạo reminder không ai yêu cầu rồi complete nó, và
  bỏ qua bước search/ask của gold.

### Hạng 2 — ASR làm hỏng input (chặn đứng 0025/0016; góp phần ở 0049/0003/0008)

- **0025 (v6 cached, v7):** gold "Nếu mai mưa thì huỷ lịch đá bóng sáng
  mai với gọi cho bạn Minh nhé, còn không mưa thì thôi ạ" → ASR "nếu
  may vừa thì nghĩ dịch đá bóng sáy may phơi lợi cho đảng minh nhé còn
  không vui vì thôi hàng". Động từ huỷ, đối tượng gọi, và nhánh điều kiện
  đều nát → model dừng ngay với 0 call ở cả hai bản.
- **0016-v7 (mới, chỉ có ở v7):** gold "nếu mai mưa thì dời lịch đá bóng
  sáng mai muộn hai tiếng với nhắn SMS cho Mẹ báo giờ mới, còn không mưa
  thì thôi" → ASR "nếu mưa thì dò lệch đau bóng song hãy mệt nãy tiếng
  với nhẫn ét mét cho mẹ lập báo giờ mới hoặc không mưa thì thôi".
  Điều kiện ("nếu mưa… hoặc không mưa thì thôi") còn, nhưng toàn bộ
  hành động (dời lịch, nhắn SMS, giờ mới) nát → dừng ngay 0 call.
  Đây là trường hợp ASR "nửa vời" nguy hiểm: điều kiện còn khiến người
  đọc tưởng input đủ dùng, nhưng entity/hành động đã mất.
- **0049-v7 (một phần):** "chuyển tiền mạng tháng này cho chủ nhà Phạm
  Hùng" → "chuyện tim mạng thấy hành gia trỗi gà phản hồn nghé": từ
  "mạng" còn, tên chủ nhà và loại bill mất hẳn — trực tiếp dẫn tới chọn
  sai bill (xem hạng 1). Mệnh đề fallback ("nếu tài khoản thanh toán
  không đủ thì lấy từ tiết kiệm") còn nguyên, nhưng model vẫn đảo ngược
  hướng fallback — phần đó không đổ cho ASR được.
- **0003-v7 (nhẹ, không phải nguyên nhân chính):** "Ơi, nạp giúp mình 50
  nghìn điện thoại cho bác Ba với chuyển ví cho cô Mai số tiền điện
  tháng này nhé" → "ê nạn kíp mình năm mươi ngàn tiền điện thoại cho
  bác ba với chuyển ví cho cô mai số tiền điện thánh là nhé". 50 nghìn,
  bác Ba, cô Mai, "tiền điện tháng này" đều còn — đủ để bắt đầu bằng
  list_bills + search. Lỗi chính của 0003-v7 là format + bỏ qua bước
  đọc (hạng 3, 4), không phải ASR.
- **0008 (nhẹ):** "nếu mai mưa thì dời muộn nửa tiếng, không mưa giữ
  nguyên" → "cái còn lại nếu may mưa thì dời muộn nửa tiếng không mưa
  rửa hoen". Điều kiện và hành động còn đủ để hiểu — model vẫn viết
  trước khi đọc forecast, nên đây không phải lỗi ASR.

### Hạng 3 — Thiếu observation / bỏ qua bước đọc bắt buộc (prerequisite)

- **0008:** forecast là bước đầu tiên của gold; model viết trước, đọc
  sau (v6) hoặc không đọc (v7). Không có observation nào trong trace
  quyết định được nhánh mưa trước khi ghi.
- **0003-v7:** thay vì list_bills (lấy 845000) và contacts.search (lấy
  c_06, phone 09919377320), model nhảy thẳng sang hỏi — và hỏi cả
  những thứ lẽ ra đọc được. Ask không thay thế được read ở đây.
- **0049-v7:** không có `list_beneficiaries` nào trong trace, nên
  ben_03/chủ nhà không bao giờ xuất hiện; transfer của gold vì vậy
  không thể xảy ra dù các bước khác có đúng.
- **0025-gold-v6:** huỷ event_12345 trước khi list_events; chỉ sau 2 lần
  done:false mới list rồi huỷ evt_01 đúng. Thứ tự đọc-sau-ghi là mẫu
  lặp lại, không phải tai nạn một lần.

### Hạng 4 — Không dừng đúng lúc (termination)

Mẫu hệ thống, không phải ngẫu nhiên: **guard `max_repeats=2` cho phép
mọi call lặp chạy đúng 2 lần rồi mới chặn lần thứ 3.** Vì vậy "ghi trùng"
xuất hiện dưới dạng đúng 1 lần thừa ở khắp nơi — model không dừng sau
thành công lần đầu, guard chỉ ngăn lần thứ ba:

- 0004-v7: light_set đúng (bedroom2, 50) chạy 2 lần; lần 2 xong mới
  replan → stop.
- 0049-v7: open_savings done:false chạy 2 lần (lần 2 cũng done:false),
  lần 3 bị chặn. Model phớt lờ feedback done:false — đúng điều policy
  điểm 5 của a2e832b cấm ("done:false did NOT complete"), nhưng vẫn xảy
  ra.
- 0008-v7: alarm.update chạy 2 lần, lần 3 bị chặn, không có stop đúng
  nghĩa sau đó (trace kết thúc bằng guard, không phải stop).
- 0116-v6: create → complete → create lại (lần 3 bị chặn).
- 0025-gold-v6: cancel evt_01 chạy 2 lần; lần 2 xong thì guard trigger
  thứ hai (đã replan 1 lần ở lần huỷ event_12345 thứ hai) nên trace dừng
  — kết thúc bằng guard, không phải stop.
- Dừng sớm (đầu kia của termination): 0025/0016 dừng ngay với 0 call
  thay vì đọc để khôi phục hoặc hỏi. 0019 dừng ngay là ĐÚNG (gold rỗng)
  — cùng một hành vi, khác nhau ở chỗ input có khôi phục được không.

Ngoại lệ cần giữ: dev có request yêu cầu lặp thật (ví dụ hai phần
thưởng giống nhau — xem AGENT_FIX của nhánh). Vì vậy **không dedup mù**:
tiêu chí phân biệt đã có trong policy điểm 6 ("repeat only if the user
explicitly requested multiple instances") — vấn đề là model không tuân
thủ, không phải thiếu luật.

### Hạng 5 — Format (hẹp nhưng chặn đứng hoàn toàn khi xảy ra)

- **0003-v7:** model 3 lần liên tiếp output ask ở dạng
  `{"name": "sys.ask_missing_info", "tool_name": ..., "params": [...]}` —
  field ask nằm ở top-level thay vì trong `"arguments"`. Loop lấy
  `arguments = gen.get("arguments", {})` → `{}` → validation báo "thiếu
  tham số bắt buộc: tool_name, params" → observation lỗi → model lặp
  lại y hệt (greedy, 3 attempt trong 1 step rồi trace kết thúc, 0 call).
  Đây là lỗi hợp đồng output, không phải lỗi hiểu task: cùng một output
  đó nếu bọc trong `"arguments"` thì đã chạy được (và ask early-return
  của a2e832b sẽ kết thúc turn).
- **0025-gold-v6:** `{"name": "stop", "reason": "..."}` bị validation
  reject ("tool 'stop' không có trong catalog") vì code v6 chỉ nhận
  `{"stop": true}`. a2e832b đã sửa điểm này (`is_stop_signal` chấp nhận
  cả name=stop không arguments) — lỗi format này không còn ở v7.
- V6 tổng cộng chỉ 1 validation_rejected; v7 tổng cộng 3 (đều là 0003).
  Format không phải họ lỗi phổ biến, nhưng khi nó đánh vào ask — công
  cụ duy nhất để xin thông tin — thì toàn bộ turn sụp đổ.

### Hạng 6 — Proxy mismatch (điểm 0 không có nghĩa là làm sai)

- **0004-v7 là bằng chứng rõ nhất:** trạng thái cuối ĐÚNG (đèn
  bedroom2 brightness 50, hash đúng) nhưng F1 = 0 → score 0, vì matcher
  đòi cùng tập key đối số: read có thêm filter `room` (gold `{}`),
  write thừa `power: "on"` (gold chỉ có device_id + brightness). Cả hai
  đều là thông tin đúng/thừa vô hại với trạng thái, nhưng matcher tính
  là không khớp. Cộng thêm ghi trùng (hạng 4) thì F1 vẫn 0 dù bỏ duplicate.
  **Đừng đọc 0004-v7 như "model làm sai task"** — nó làm đúng trạng
  thái, sai ở khía cạnh trace-equivalence mà evaluator chính thức chưa
  xác nhận có chấm như vậy hay không (câu hỏi Q-L3/Q-L5 vẫn mở).
- **0116-v7:** hash đúng nhưng F1 = 0 vì ask sai tool (hạng 1). Hash đúng
  ở đây là rỗng tuếch (ask không đổi state) — minh hoạ rằng "hash
  agreement ≠ task success" theo cả hai chiều: hash đúng có thể sai
  task (0116), và task đúng có thể F1 0 (0004).
- **Nhạy cảm của mean v7:** proxy mean 0,125; nếu chỉ tính hash (bỏ F1)
  thì mean là 0,375 (3/8: 0019, 0116, 0004). Con số này KHÔNG phải đề
  xuất thay scorer — nó chỉ cho thấy mean proxy nhạy với quy tắc khớp
  đến mức nào, và vì vậy không nên dùng mean 8 mẫu để xếp hạng model.
- **0025-gold-v6 F1 = 0,154:** chỉ đúng 1/13 cặp khớp được (cancel
  evt_01); forecast thừa key `location`, list_events thừa key khoảng
  ngày nên đều trượt matcher dù nội dung gần đúng. Cùng một quy tắc
  key-set-exact gây ra cả ba hiện tượng trên.

## 3. V6 → V7 trên 5 mẫu chung (cùng input ASR, đã kiểm chứng)

| Mẫu | V6 (a9d48d2) | V7 (a2e832b) | Đọc |
|---|---|---|---|
| 0019 | Dừng đúng, 1 | Dừng đúng, 1 | Không đổi, vẫn đúng |
| 0116 | Bịa giờ, tạo→xong→tạo lại | Hỏi sai câu, không ghi bậy | Termination tốt lên (hết ghi bịa), intent vẫn sai (sai câu hỏi) |
| 0025 | ASR nát → dừng ngay | ASR nát → dừng ngay | Không đổi |
| 0003 | Bịa contact/phone/amount, 2 transfer | Ask sai format ×3, 0 call | Hành vi đổi hẳn nhưng không tốt lên: validation chặn được transfer bịa (model không thử), nhưng format ask chặn luôn turn; grounding evidence chưa được kiểm chứng vì model không thử transfer nữa |
| 0008 | Sửa→xem current→sửa→xem forecast→(chặn) | Sửa→sửa→(chặn), không xem forecast | Tệ hơn ở một khía cạnh: v7 không đọc forecast lần nào; policy condition-before-write không có tác dụng quan sát được |

Kết luận v6→v7: **không có cải thiện nào được chứng minh trên 5 mẫu
chung** (mean proxy 0,2 → 0,2). Thay đổi thực sự là đổi dạng lỗi ở 0116
(tốt lên về termination) và 0003 (đổi từ bịa ID sang lỗi format), còn
0008 vẫn sai cùng một chỗ. Các thay đổi plumbing (JSON đầy đủ, evidence
ledger, policy dài, not_done) chưa chạm được vào các lỗi intent/
prerequisite/termination này trên tập mẫu này.

## 4. Ba câu hỏi ưu tiên trong runtime README — trả lời bằng trace

### Q1. Ask format (0003) và 0116 hỏi sai: format repair hay sai intent?

Cả hai, nhưng ở hai tầng khác nhau và cần tách ra:

- **0003-v7 là lỗi format thuần túy ở tầng envelope:** output thiếu
  `"arguments"` bọc ngoài. Parser hiện tại (`parse_model_output` ở
  nhánh) chỉ json.loads rồi trả dict nguyên trạng; loop lấy
  `gen.get("arguments", {})`. Không có bước chuẩn hoá nào cho ask ở
  top-level, và validation-retry đưa cùng một observation lỗi trở lại
  nhưng model greedy vẫn lặp y hệt 3 lần. Format repair (chuẩn hoá
  top-level tool_name/params vào arguments, hoặc parser chấp nhận dạng
  này) sẽ cho turn này chạy tiếp — nhưng **không sửa được intent**:
  audit đã chỉ ra model còn hỏi `phone` cho `ewallet.transfer` (param
  không tồn tại) và hỏi những thứ lẽ ra phải đọc (bill amount, contact).
  Sau format repair, 0003 vẫn cần list_bills + search trước khi hỏi.
- **0116-v7 là sai intent thuần túy, không liên quan format:** ask được
  bọc đúng `{"name", "arguments": {tool_name, params}}`, chạy được, kết
  thúc turn đúng cơ chế — chỉ sai nội dung (phone.call thay vì
  reminders.create). Format repair không động được vào mẫu này.
- **Bằng chứng từ chính model artifact (không phải web):** chat template
  của Qwen3-4B-Instruct-2507 rev cdbee75 (đã tải, đọc trực tiếp từ
  tokenizer_config) CÓ hỗ trợ native tool-calling: nhánh `{% if tools
  %}` render system block `<tools>` + hướng dẫn trả
  `<tool_call>{"name", "arguments"}</tool_call>`, và message role `tool`
  render thành `<tool_response>`. Nhưng llm của nhánh KHÔNG truyền tools
  vào template (chỉ 1 user message, tools=None) nên template đi nhánh
  else — model bị dùng ngoài hợp đồng native của nó: tool mô tả bằng
  prose trong 1 user message khổng lồ, observation nối thêm dạng text,
  output kỳ vọng là bare JSON. Đây là giả thuyết có căn cứ mạnh nhất cho
  vì sao ask bị bẹt thành top-level: model không được đặt vào format mà
  nó được huấn luyện để gọi tool. Thí nghiệm E1 (§6) kiểm chứng trực
  tiếp giả thuyết này.

### Q2. 0008 viết trước khi xem thời tiết; 0004 ghi trùng — plan/decision representation, tool-message structure, hay execution policy?

Trace cho thấy cả ba tầng đều có dấu vết, nhưng bằng chứng mạnh nhất
hiện tại chỉ về execution policy + termination:

- **0008:** policy text đã nói rõ "evaluate conditions BEFORE dependent
  writes" nhưng model vẫn viết trước ở cả hai bản. Đây không phải thiếu
  chữ trong prompt — đây là prompt không ràng buộc được hành vi. Một
  representation dạng plan (trạng thái "điều kiện chưa quyết định" được
  theo dõi ngoài prompt, và write bị chặn cho tới khi observation quyết
  định điều kiện xuất hiện) mới là thứ có thể ép thứ tự này — nhưng đó
  là thay đổi cơ chế, cần thí nghiệm E2, không phải thêm chữ vào policy.
- **Tool-message structure** là giả thuyết phụ có căn cứ từ template
  (role `tool` + `<tool_response>` tồn tại nhưng không được dùng):
  observation hiện tại là text nối vào user message, nên model có thể
  "đọc lướt" qua feedback done:false / forecast. Đưa observation về
  đúng message role tool là một thay đổi cấu trúc đáng thử cùng E1 (vì
  cùng một lần đổi contract), nhưng trace hiện tại không đủ để tách tác
  dụng của nó khỏi tác dụng của native tool-calling — E1 phải đo riêng
  từng tầng nếu muốn kết luận (xem thiết kế E1).
- **0004 ghi trùng:** không phải lỗi plan — plan đúng, device đúng,
  brightness đúng. Lỗi là không dừng sau thành công lần đầu. Guard hiện
  tại cho phép đúng 1 lần thừa rồi mới chặn. Tiêu chí đúng đã có trong
  policy điểm 6 (chỉ lặp khi user yêu cầu nhiều instance) nhưng model
  không tuân thủ. Thí nghiệm E4 đo xem siết guard hay bổ sung
  completion-check mới là thứ sửa được lỗi này mà không phá các request
  lặp hợp lệ.

### Q3. ASR: small-vs-medium có đáng làm không? ASR upgrade alone có đủ không?

- **Đáng làm, nhưng không đủ — và v6 đã chứng minh phần "không đủ":**
  arm gold-current của v6 (transcript chuẩn cho current, history ASR giữ
  nguyên) vẫn 0 điểm ở cả 4 mẫu action (0116, 0025, 0003, 0008). Transcript
  chuẩn sửa được bước đầu ở 0025 (bắt đầu bằng forecast) và chọn tool đầu
  ở 0003 (topup), nhưng downstream vẫn trật: bịa ID/amount, reminder lạ,
  stop-as-tool, huỷ trùng, viết trước forecast. Vì vậy mọi tuyên bố
  "lên medium là xong" đều sai với bằng chứng hiện có.
- **Phần "đáng làm":** 0025 và 0016 bị chặn đứng hoàn toàn bởi ASR (0
  call), và 0049 bị ASR phá tên chủ nhà + loại bill dẫn tới sai bill.
  Một thí nghiệm ASR small-vs-medium đo đúng các slot quyết định
  (condition, negation, tên, tiền, giờ) + hiệu ứng downstream trên cùng
  8 mẫu sẽ định lượng được phần lỗi nào là ASR — xem E3. Lưu ý: v7
  không có arm gold-current, nên với agent mới, phép tách ASR/LLM vẫn
  chưa được lặp lại; E0 lấp đúng lỗ này.

### Q4. 0004 và ngữ nghĩa scoring chính thức

Đã phân tích ở hạng 6: read có filter, arg optional thừa, và ghi trùng
đều bị matcher hiện tại tính trượt dù trạng thái cuối đúng. Cho tới khi
organizer trả lời Q-L3 (read có tính F1 không) và Q-L5/Q-L1 (ask và hết
vòng lặp nộp gì), mọi kết luận "0004 là lỗi model" đều phải đi kèm chú
thích này. Trong ledger này, 0004 được tính là: **termination lỗi thật
(ghi trùng) + proxy mismatch (phần còn lại)** — không gộp thành một.

## 5. Những gì trace KHÔNG chứng minh được (đừng suy diễn quá)

- Không chứng minh model xếp hạng thế nào, baseline chất lượng đại diện
  ra sao (8 mẫu chọn tay, không phải mẫu ngẫu nhiên; mean 0,125/0,2
  không có ý nghĩa thống kê).
- Không chứng minh latency A30 hay context thực tế (runtime T4x2, FP16;
  v7 hết 258,95s cho 8 mẫu, v6 415,08s cho 10 trial — chỉ là thời gian
  chạy smoke, không phải bằng chứng 30s/sample).
- Không chứng minh observation truncation là nguyên nhân ở các mẫu này:
  v7 dùng JSON đầy đủ mà 0003/0008/0116/0049 vẫn sai — truncation đã bị
  loại khỏi danh sách nghi phạm chính cho 8 mẫu này (trừ việc v6 0003
  không có list_bills nên truncation không phải nguyên nhân trực tiếp
  ngay cả ở v6, như audit đã ghi).
- Không cho thấy full prompt: mọi kết luận về prompt đều suy từ code
  nhánh + template, không phải từ prompt đã chạy (prompt không nằm
  trong artifact).

## 6. Thí nghiệm tiếp theo — mỗi giả thuyết một thí nghiệm nhỏ

Tất cả đều dùng dev (không held-out), greedy/seed 42, cùng ASR small trừ
khi ghi rõ khác, và báo cả hash lẫn F1 lẫn score (không chỉ mean proxy).
Không thí nghiệm nào trong số này được thực hiện ở đây — đây là đề xuất
cho Codex, chưa sửa code.

### E0 (lấp lỗ phương pháp, ưu tiên cao nhất): lặp lại paired diagnostic cho agent mới

- Giả thuyết đối thủ: "a2e832b đã sửa phần LLM, chỉ còn ASR là vấn đề."
- Thiết kế: chạy lại đúng 8 mẫu v7 với agent a2e832b nhưng current
  transcript = gold (history ASR giữ nguyên như v7), giống thiết kế v6.
  So sánh từng mẫu với v7 live-ASR.
- Đo: per-sample delta (call, hash, F1) và phân loại lỗi còn lại.
- Kết luận được: nếu 0003/0008/0116/0049 vẫn sai với transcript chuẩn
  thì lỗi là LLM/policy/contract, không phải ASR; nếu sửa được thì ASR
  mới là nút thắt cho mẫu đó. Không có E0, mọi tranh luận ASR-vs-LLM
  cho agent mới đều là đoán.

### E1 (giả thuyết contract): native tool-calling vs text contract

- Giả thuyết: model sai format ask vì bị dùng ngoài hợp đồng native
  (template có `<tools>`/`<tool_call>`/`<tool_response>` nhưng llm không
  truyền tools; output kỳ vọng bare JSON).
- Thiết kế: cùng 8 mẫu, greedy, 2 arm. Arm A: contract hiện tại (giữ
  nguyên). Arm B: truyền tools vào `apply_chat_template` (system block
  `<tools>`), observation render thành message role `tool`
  (`<tool_response>`), parser chấp nhận `<tool_call>` JSON. Chỉ đổi
  contract, không đổi model/policy/grounding.
- Đo: tỉ lệ format error, ask đúng tool_name/params, và 0003 có vượt
  qua được ask để tới read không.
- Falsify: nếu arm B vẫn bẹt ask ra top-level hoặc vẫn hỏi sai tool thì
  giả thuyết contract sai — vấn đề nằm ở hiểu task, không phải format.
- Tách tầng (nếu cần kết luận sâu): arm B1 chỉ đổi parser (chấp nhận
  `<tool_call>` nhưng giữ text prompt) và arm B2 chỉ đổi template
  (truyền tools) để biết tầng nào có tác dụng. Mặc định chạy B gộp
  trước cho rẻ, tách sau chỉ khi B có hiệu ứng.

### E2 (giả thuyết prerequisite): policy + ví dụ condition-before-write vs policy hiện tại

- Giả thuyết: policy text hiện tại không đủ để ép thứ tự điều kiện →
  write; cần ví dụ minh hoạ hoặc cơ chế, không phải thêm chữ chung chung.
- Thiết kế: cùng 8 mẫu, 2 arm prompt-only (không sửa code). Arm A:
  policy hiện tại. Arm B: policy hiện tại + 1 ví dụ ngắn condition-
  before-write (dạng: request "nếu mưa thì…" → bước đầu phải là read
  quyết định điều kiện, chưa được write). Đo riêng 0008 + 0016 (hai mẫu
  conditional) và kiểm tra regression trên 6 mẫu còn lại.
- Đo: 0008 có đọc forecast trước write không; 0016 có bắt đầu bằng
  forecast/list thay vì dừng ngay không.
- Falsify: nếu arm B vẫn viết trước thì vấn đề không phải thiếu ví dụ
  — cần cơ chế chặn write ngoài prompt (đề xuất sau, không làm ngay).

### E3 (giả thuyết ASR): small-vs-medium, đo slot quyết định + downstream

- Giả thuyết: một phần lỗi là ASR small, và medium sửa được đúng các
  slot quyết định.
- Thiết kế: (1) transcribe current + history audio của 8 mẫu bằng
  PhoWhisper-small và medium (cùng greedy), chấm thủ công theo slot:
  condition, negation, tên người, tiền, giờ, địa điểm — không chấm WER
  chung chung vì WER không nói được slot nào chết. (2) Chạy agent
  a2e832b trên cùng 8 mẫu với transcript medium (arm medium) so với
  transcript small (v7 đã có).
- Đo: bảng slot còn/mất theo từng mẫu, và per-sample delta call/hash/F1
  giữa hai arm.
- Falsify: nếu medium không sửa được slot của 0025/0016 (hoặc sửa slot
  mà agent vẫn sai như v6 gold-current), thì ASR không phải nút thắt
  cho các mẫu đó — dừng đầu tư ASR và quay lại E1/E2/E4.
- Lưu ý ngân sách: medium + Qwen3-4B = 4,769B, vẫn dưới cap 6B (đã tính
  ở OPTIMAL_PIPELINE); licence/date của medium trên thẻ vinai vẫn chưa
  kiểm chứng — kiểm chứng trước khi dùng cho submission, không phải
  cho thí nghiệm chẩn đoán này.

### E4 (giả thuyết termination): siết guard vs completion-check, có đối chứng lặp hợp lệ

- Giả thuyết: model không dừng sau thành công lần đầu; guard hiện tại
  (cho lặp 2 lần) che giấu lỗi này thành "chỉ thừa 1 lần".
- Thiết kế: cùng 8 mẫu + thêm các mẫu dev có gold lặp hợp lệ (gold chứa
  cùng 1 call 2 lần do user yêu cầu nhiều instance — ví dụ nhóm
  two-rewards; tìm trong dev, không dùng held-out). 2 arm: guard
  max_repeats=2 (hiện tại) vs max_repeats=1 (chặn mọi lặp).
- Đo: số lần ghi thừa trên 8 mẫu, và tỉ lệ phá request lặp hợp lệ ở
  nhóm đối chứng.
- Falsify: nếu max_repeats=1 không giảm được ghi thừa (model đổi sang
  call khác tương đương) hoặc phá nhiều request hợp lệ thì guard không
  phải đáp án — cần completion-check theo ngữ nghĩa (đã xong tất cả
  action của nhánh → stop), không phải đếm lặp.
- Không làm: dedup mù toàn cục (phá request lặp hợp lệ — đã cảnh báo
  trong AGENT_FIX và README).

### E5 (giả thuyết intent thuần): policy disambiguation cho "nhắc + hành động"

- Giả thuyết: 0116 sai vì model không phân biệt "nhắc làm X" (reminder
  cần time) với "làm X ngay" (call cần contact).
- Thiết kế: prompt-only, 2 arm trên nhóm ask_only của dev (0116 + các
  mẫu ask_only khác, vẫn là dev; bắt đầu với ~20 mẫu cho rẻ). Arm A:
  policy hiện tại. Arm B: policy + 1 quy tắc phân biệt duy nhất
  ("nhắc + hành động = reminder, hỏi time; chỉ khi user nói gọi ngay
  mới là call, hỏi contact_id").
- Đo: tỉ lệ ask đúng tool_name/params (không cần chạy full trace nếu
  chỉ đo ask đầu tiên — rẻ hơn, nhưng phải báo rõ đó là đo ask, không
  phải đo full task).
- Falsify: nếu arm B vẫn hỏi phone.call thì vấn đề không phải thiếu quy
  tắc — model không áp dụng được quy tắc phân biệt, cần xem lại cách
  model đọc request (quay lại E1).

## 7. Thứ tự làm (đề xuất)

1. **E0 trước** — rẻ, lấp lỗ phương pháp, và quyết định E1/E3 cái nào
   đáng làm tiếp. Không có E0 thì E1 và E3 đều tranh luận trên nền
   thiếu arm đối chứng.
2. **E1 và E3 song song** (hai giả thuyết độc lập lớn nhất: contract và
   ASR). E1 trả lời 0003; E3 trả lời 0025/0016/0049-phần-ASR.
3. **E2, E5** (prompt-only, rẻ) sau khi có E0 — chúng sửa intent/
   prerequisite mà E0 sẽ xác nhận là còn tồn tại với transcript chuẩn.
4. **E4** khi cần quyết định về guard/completion — chỉ sau khi biết
   duplicate có còn là vấn đề dưới contract mới (E1) hay không, vì
   contract mới có thể tự nó sửa termination.
5. **Không làm ngay:** chạy lớn hơn 8 mẫu, training/SFT, đổi model,
   held-out, hay bất kỳ thay đổi inference nào chưa qua E0–E5. Đặc biệt
   không đề xuất model khác trước khi phân loại xong — ledger này cho
   thấy phần lớn lỗi là contract/intent/prerequisite/termination, không
   phải "model yếu" nói chung.
