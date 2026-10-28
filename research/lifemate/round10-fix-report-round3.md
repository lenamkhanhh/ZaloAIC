# Round 10 fix — Round 3: registry-typed G2 evidence, kind classification, reviewer-fix integration

Tiếp nối báo cáo Round 2 (`round10-fix-report-round2.md`). Cùng nhánh
`round10-provenance-gates-fixes`, KHÔNG merge main. Base Round 3 là
commit Round 2 `3838d99f`; commit cuối Round 3 ghi trong thông điệp
bàn giao + MEMORY.md (báo cáo không thể chứa SHA của chính commit
chứa nó).

Phạm vi vẫn chỉ modules/tests/audit/report/shadow/repro. Không sửa
inference, simulator, scorer, benchmark config; không GPU, training,
held-out, không tự merge main. Không đưa gold/sample-specific rules
vào runtime.

**Qualifier áp dụng cho mọi bảng trong báo cáo này (reviewer 6-EX):
prover + G2 chứng minh existence/derivation CONDITIONAL trên các id
mà chính call đó mang — không chứng minh model đã chọn đúng entity.
PROVEN ≠ call đúng; UNPROVEN ≠ hallucination.**

## 0. Kết quả tóm tắt (đọc trước)

- Registry thay thế hoàn toàn giả định "generic id từ app nào cũng
  hợp lệ". G2 nay yêu cầu registry của evidence khớp registry của
  slot tiêu thụ.
- Scope e7 được sửa từ verb list sang catalog kind: 556 → 533 args;
  DAG 284 → 276, baseline 93 → 92, conversion 191 → 184. Mọi delta
  đều được phân rã tới từng dòng (mục 4).
- G2 gold: applicable 976, fired 15, **gold false-block rate 1.54%**,
  verdict KEEP (ngưỡng 95%). 15 = 4 cũ + 11 phone-number tồn dư
  (mục 5). Theo 6-PR, con số cần trích là false-block rate, không
  phải "precision" (precision 0.9849, Wilson [0.9752, 0.9908], là
  1 − false-block rate theo cấu trúc, không phải detection
  precision).
- Shadow đối chứng V10/V11/V13 với code mới: **row-identical 100%**
  so với baseline Round 2 (14/14, 10/10, 29/29). Không một quyết
  định nào trên model proposal thật thay đổi.
- Tests 146/146 cả hai backend. Repro 38/38.
- Sẵn sàng: prover + G2 **shadow-ready, KHÔNG hard-enforce** (mục 7).
  G1/G3 vẫn DROP.

## 1. Ba luồng song song và bàn giao

| Luồng | Việc | Kết quả bàn giao |
|---|---|---|
| Thread 1 — registry/G2 | Map registry, sửa G2 | Chỉ sửa `lifemate_gates.py` + tests của nó. Interface change: path triples (mục 2). Tests 133/133. Repro 22/23 — 1 lệch là F8 (hợp đồng cũ, mục 6). |
| Thread 2 — mixed-trace shadow | Tổng quát hóa shadow script cho V10/V11 | Chỉ sửa `model_trace_shadow.py` + output /tmp. Shadow-only tests 29/29 (ở /tmp, không push). Baseline đông lạnh 3838d99f. |
| Thread 3 — independent reviewer | Đọc lại toàn bộ, chạy lại read-only | Round-2 numbers reproduce (repro 23/23, tests 117/117, G2 99.6%, e7 284/93/191, V13 shadow 16/6/7). 17 findings có severity (mục 3). |

Sự cố phối hợp duy nhất: giữa chừng, checkout chung thay đổi dưới
chân Thread 2 (edit đang làm dở của Thread 1) và làm lệch các dòng
light_set; Thread 2 đã hủy các run đó và chạy lại trên bản sao
đông lạnh cô lập (`/tmp/t2_frozen/` = gates blob fde4ea7f…,
provenance blob 3ca05032…). Bài học cho vòng sau: **paired re-run
không bao giờ chạy trên checkout bẩn** — main đã tuân thủ khi chạy
lại mục 5.

## 2. Interface change: result entries 3-tuple (Thread 1, bắt buộc đọc)

`PriorCall.result_entries` nay có thể là `(field, value, path)`,
trong đó `path` là dotted key path từ result root tới dict chứa
leaf (bỏ qua list indices, `""` ở root). Ví dụ:
`smart_home.get_status` → `("id", v, "devices")` vs
`("id", v, "scenes")`; `loyalty.get_points` → `("id", v, "programs")`
vs `("id", v, "programs.rewards")`.

- Tương thích ngược: legacy 2-tuple chỉ resolve khi `(tool, field)`
  map tới đúng một registry; entry mơ hồ legacy không chứng minh
  gì.
- Mở rộng là bắt buộc, không phải tùy chọn: 4 producer tools trả
  id từ nhiều registry dưới cùng field `"id"` (get_status
  devices/scenes, music.list_tracks tracks/playlists,
  podcast_radio.search shows/episodes/stations, loyalty.get_points
  programs/programs.rewards). Map chỉ bằng `(tool, field)` sẽ hoặc
  pass sai cross-registry, hoặc block sai tất cả.
- Flattener tham chiếu `flatten_result_entries` nằm trong gate
  module (cùng quy tắc drop phone/bool như flattener cũ + path
  tracking). **Trong Round 3 này, cả ba flattener (e7 audit, gates
  audit, shadow script) đã được chuyển sang triples** — con số
  legacy-flattener 224 fired của Thread 1 chỉ là artifact chuyển
  tiếp (thiếu path), không bao giờ được trích làm chất lượng gate.
- Chữ ký hàm không đổi: `gate_read_before_write(call, prior_calls,
  rosters, kind_by_tool=None)`, `PriorCall(...)` giữ nguyên thứ tự
  field.

### 2.1 Quy tắc G2 mới

Một `*_id` được establish **iff** một prior call SUCCEEDED có entry
mà registry bằng registry của slot tiêu thụ (`PRODUCER_REGISTRY`
111 entries vs `CONSUMER_REGISTRY` 42 entries — mọi catalog `*_id`
slot 41/41 đều có mặt, cộng merchant). Reads vẫn verify bằng
lookup (succeeded read khớp registry thì establish ngay cả khi id
bằng input của read — `ride_hailing.get_ride` find-or-noop). Writes
chỉ establish id mới không-echo. Tất cả references vẫn được check,
không early return. Bare-mutate verbs vẫn cần prior succeeded read
cùng app family (không có registry cho mutate không id). Slot không
có registry → UNKNOWN, không bao giờ establish.

**Không còn tính làm evidence (cố ý):** free-text fields; và
**foreign-key fields trong record trả về** (booking's `flight_id`,
message's `contact_id`, transaction's `account_id`/`beneficiary_id`,
reservation's `book_id`, recording's `program_id`, order's
`restaurant_id`, lesson's `course_id`, call's `chat_id`, rule's
`device_id`, voucher's `reward_id`/`program_id`, saved place's
`place_id`, guest code's `lock_id`, playlist track ids, meeting
attendees) — tool sản xuất không hề lookup registry đó, nó chỉ trả
record tham chiếu tới đó. Shortcut cũ "slot's own field" đã bỏ.

### 2.2 Căn cứ mapping (theo thứ tự)

1. Catalog `x-ref` của slot tiêu thụ (`train_tools_catalog.json`,
   147 specs); 2. implementation phía tiêu thụ (collection đưa vào
   find/patch/delete/create, hoặc cross-app state check explicit);
   3. implementation phía sản xuất (collection đưa vào read(),
   record trả bởi find(), collection đưa vào create()).
   **Không bao giờ dùng:** id-string prefixes, gold pass rates,
   "chưa thấy collision".

**Shared-registry relation có evidence implementation: đúng MỘT:**
`home_automation.create_rule.device_id` → `smart_home.devices`
(catalog x-ref VÀ `home_automation.py` create_rule đọc
`session.states["smart_home"]["devices"]`, noop khi id vắng; docstring:
device_id "must exist in smart_home.devices"). Mọi cross-app state
access khác tìm được bằng grep đều KHÔNG phải id registry
(`bill_payment.pay`→ewallet balance là tiền, không phải id;
`base.contact_ref`→contacts book chỉ hoàn thiện phone, trả
`contact_id` unknown nguyên vẹn — tức non-validating, đó là lý do
sms/phone không bao giờ establish contacts; `video_meeting.create`
attendees→contacts là list validation không gated — xem residuals).

**Ngoại lệ field-scoped — merchants (registry yếu nhất, nói thẳng):**
merchants không có collection hay validating lookup ở đâu cả
(`ewallet.pay_qr` chỉ check balance). Merchant identity CHÍNH LÀ
giá trị field `merchant_id`, và field này đi kèm restaurant/place/
course/program records (đã verify trong gold history results cả 4
loại, không chỉ catalog text của `pay_qr`). Nên
`registry_for_entry` resolve **bất kỳ** field `merchant_id` nào về
`food_delivery.merchants`. Vẫn chặt hơn generic-id: restaurant/
place/course/program *id* không thể giả làm merchant, free text
cũng không — chỉ field `merchant_id` mới tính.

**Bug Thread 1 tự tìm và sửa trong bản nháp đầu (không giấu):**
ban đầu map `program_id`→`loyalty.programs`; catalog chỉ có một slot
`program_id` là `tv.record` (x-ref `tv.programs`), còn loyalty redeem
lấy `program` (name-or-id, không phải `*_id` slot). Đã sửa thành
`tv.programs`. Bug này gây 4 fires thừa trong lần chạy path-aware
đầu tiên.

**Tracking dual key:** `package_tracking._shipment()` match bằng
state `id` HOẶC `tracking_id`, nên cả hai producer fields đều
establish shipments.

### 2.3 8 mandatory checks (nay là regression tests, đều pass)

1. Calendar event id → ride_id: FIRES. 2. Message id / message
   `contact_id` → contact: FIRES cả hai biến thể. 3. Free-text field
   chứa id → entity: FIRES. 4. smart_home device → home_automation
   rule: pass CHỈ qua path `"devices"`; legacy 2-tuple fires; scene
   path không establish device. 5. get_ride lookup success → cancel:
   passes (path `"ride"`). 6. Failed/noop/empty reads → nothing
   (thêm biến thể wrong-registry read). 7. Create new id → CHỈ đúng
   registry của nó (calendar evt→update passes, ride cancel fires;
   booking id passes, `flight_id` foreign key của nó fires).
   8. Write echo không bao giờ tự establish (sms/phone echoes,
   transfer beneficiary echo, patch echo).

## 3. Reviewer findings: xử lý từng cái

| ID | Sev | Nội dung | Xử lý Round 3 |
|---|---|---|---|
| 1-B | BLOCKER | Generic `id` từ succeeded read bất kỳ establish mọi `*_id` | FIXED bằng registry (mục 2). Repro R3-1B. |
| 1-S | MAJOR | get_status trộn devices + scenes dưới field `"id"` | FIXED bằng path triples. Repro R3-1S (scene fires, device passes). |
| 2-P | MAJOR | Số điện thoại cách khoảng leak thành amount spans | FIXED: `_PHONE_SEQ_RE` pre-claim phone ranges vào `covered` trước mọi loop. Repro R3-2P. |
| 2-O | MAJOR | Offset direction words match anywhere (`or word in s`) | FIXED: proximity binding — tiếng/phút chỉ window 20 ký tự trước duration; "nửa tiếng" search ±20 ký tự quanh occurrence. Repro R3-2O (09:00 PROVEN, 11:00 UNPROVEN). |
| 2-N | MAJOR | Observation entity None chứng minh write gắn id | FIXED: khi call_ids non-empty, yêu cầu entity ∈ call_ids (None chỉ còn cho creates qua nhánh turn). Repro R3-2N. Gold không bị ảnh hưởng (chỉ 9 exchange_rate bare amounts, vốn đã bị cross-app block). |
| 3-PH | MAJOR | phone_number-only refs bypass G2 hoàn toàn | FIXED + MỞ RỘNG (mục 5): roster-phone unique match HOẶC số từ succeeded read của call log. Tồn dư 11 số nói/văn bản (mục 5) — phone branch chưa hard-enforce-ready. |
| 3-SL | MINOR | Cùng id value dưới 2 arg names chỉ check slot đầu | **LỆCH KHỎI ĐỀ XUẤT, CÓ LÝ DO (xem dưới):** implement ALL() thay vì any() mà reviewer gợi ý. |
| 4-PV | MAJOR | Patch-verified writes bị loại như echo → chained writes false-block | FIXED: bảng `PATCH_VERIFIED` 18 tools (base.App.patch find-or-noop, trả `{"ok","item"}`). Deletes cố ý LOẠI (entity đã xóa không được establish refs sau đó; delete trả `{"ok"}` không item nên vốn đã không có entry — yêu cầu path=="item" làm việc phân biệt branch tự động, kể cả email.archive delete branch). |
| 4-EO | MINOR | Echo set quá rộng (title/content/note) | FIXED: `_call_reference_values` thay `_call_string_values` (đã XÓA) — echo set = `*_id` args + contact_name + to values. Repro R3-4EO passes (title trùng id không suppress new-id thật). |
| 5-M | BLOCKER (scope R3) | Shadow script V13 không chạy được V10/V11 (assert gold toàn ASK) | FIXED bởi Thread 2: gold classes, error kinds, history parse guard, narrow no-op equivalence, gold-prerequisite check (mục 5). |
| 5-RS | MINOR | Repr-string/list tool-result forms bị demote thành untyped (field None) | KHÔNG SỬA trong Round 3 (residual): hướng false-block only; zero impact trên gold (không có repr-string case nào trong dữ liệu). |
| 6-PR | MAJOR (framing) | "Precision" G2/G3 không phải precision | FIXED: audit nay ghi `gold_false_block_rate` + `metric_note`; báo cáo trích false-block rate. Ngoại lệ duy nhất: G1 90.5% là trigger thật (duplicate-roster), không phải relabel. |
| 6-EX | MAJOR (scope) | Prover + G2 chỉ chứng minh existence CONDITIONAL trên call ids | ÁP DỤNG: qualifier ở đầu báo cáo này và mọi bảng adjudication. |
| 6-HR | MINOR | history_reference trả AMBIGUOUS khi ≥2 candidates dù không cái nào match value | FIXED đúng prescription reviewer: PROVEN chỉ khi đúng 1 candidate và match; AMBIGUOUS chỉ khi ≥2 supporters; còn lại fall through. Test cũ đã cập nhật hợp đồng mới kèm comment. Guard action không đổi (cả hai verdict đều block). Gold: 4 relabels (mục 4). |
| 7-SA | MAJOR | Test `test_shared_registry_read_passes…` mã hóa bug 1-B | ADDRESSED khi registry land: test đã thu hẹp — pass CHỈ qua path `"devices"` (Thread 1 cập nhật 2 tests sang hợp đồng mới). |
| 8-V | MAJOR | Phân loại read/write bằng VERB LIST, không phải catalog kind | FIXED: `kind_by_tool` param (catalog kind thắng khi có map, verb list là fallback; module vẫn standalone). e7/gates/shadow đều dùng catalog kind. Scope sửa 556→533 (mục 4). |
| 8-AR | MINOR | Headline V13 đếm theo proposal, không phải sample | FIXED: báo cáo kèm per-sample bên cạnh per-proposal (shadow summary mang samples + rows mang sample id); không bao giờ pool V13 với V10/V11. |

### 3.1 Lệch khỏi đề xuất 3-SL — rebuttal có bằng chứng

Reviewer gợi ý: value dưới 2 slots, check slot nào cũng được
(any()) để tránh false-block. Main implement **ALL()**: một value
mang dưới 2 slots là HAI references; chỉ established khi MỌI slot
đều established (`if not all(...)` → missing).

Lý do: any() sẽ để một slot đã established che cho một slot chưa
established cùng value — đúng class lỗi masking mà Round 1 đã sửa
cho contacts. Nhãn "false-block" của reviewer không đứng vững sau
khi có registry typing: call 2-slot khác-registry (ví dụ transfer
với `from_account_id` = `beneficiary_id` = cùng value nhưng hai
registry khác nhau) **đáng** fire, vì beneficiary chưa được chứng
minh. Test `test_all_slots_checked_for_shared_value` + repro
R3-3SL khóa semantics này. Đây là quyết định có chủ ý của main,
không phải bỏ sót.

## 4. Gold audits (dev 1237, KHÔNG held-out)

### 4.1 e7 prover audit — catalog-kind scope

Scope mới: dev gold calls có catalog kind = write, ≥1 monitored
arg, trừ `sys.ask_missing_info`: **456 writes / 533 args**
(value 426, contact 107). Kind classification: `catalog`.

| | Round 2 (verb scope) | Round 3 (kind scope) |
|---|---|---|
| Args | 556 | 533 |
| DAG PROVEN | 284 (51.1%) | **276 (51.8%)** |
| Baseline PROVEN | 93 | 92 |
| Conversion | 191 | **184** |
| Value args DAG / baseline | 195 / 4 | 188 / 4 |
| Contact args DAG / baseline | 89 / 89 | 88 / 88 |
| UNPROVEN / AMBIGUOUS | 262 / 10 | 251 / 6 |

DAG theo rule (Round 3): roster 88, datetime_assembly 53,
relative_date 36, offset 34, duration 24, number_words 18,
number_digits 17, observation 4, supersede 2. Residual UNPROVEN:
cross-app 57 (by design), no source 184, roster-no-intent 10.
**history_reference nay = 0 PROVEN trên gold** — cả 4 proofs cũ
đều là single-match-among-many bị gắn nhãn AMBIGUOUS sai (xem
dưới).

**Phân rã từng dòng old→new (diff row-level R2 JSON vs R3 JSON,
key = sample/tool/slot/value):**
- Scope loại 23 rows: tools lottery.check_ticket (9),
  exchange_rate.convert (8), sms.read_recent (1), tv.guide (1)
  theo unique-key đếm (19 keys; 4 rows trùng key). Trong 23 rows
  này: 8 PROVEN + 15 UNPROVEN (khớp tổng: 284−8=276,
  262−15+4 relabels=251, 10−4=6).
- Common rows: **baseline diffs = 0**. DAG diffs = đúng 4, tất cả
  là history_reference AMBIGUOUS → UNPROVEN (6-HR): train_1378
  learning.schedule_lesson time, train_1423 reminders.create time,
  train_1641 calendar.create_event start, train_1696
  banking.open_savings amount.
- **Kết luận mạnh: các fix prover 2-P/2-O/2-N + boundary fix
  (mục 6) thay đổi ZERO gold proof.** Mọi delta e7 đều là scope
  removal hoặc 6-HR relabel — không có proof thật nào bị mất hay
  thêm do fix.

### 4.2 Gates audit — path-aware + kind classification

| Gate | Applicable | Fired | Verdict |
|---|---|---|---|
| G1 contact ambiguity | 104 (kind scope; Round 2 verb scope: 105) | 10 | DROP (90.4% theo cách đếm cũ; G1 là trigger thật nên con số này có ý nghĩa detection) |
| **G2 read-before-write** | **976** | **15** | **KEEP — gold false-block rate 1.54%** |
| G3 literal | 91 transfers | 77 fired (84.6%) | DROP |
| G3 scoped | 87 | 87 (50% theo cách đếm cũ) | DROP |

Old-vs-new (module cũ e00c864c vs gate mới, cùng kind scope):
both_applicable 957, old_passed_new_fired 3,
old_fired_new_passed 0. 3 fires mới trên tập chung chính là 3
message-history contacts mà Round 2 đã sửa (nay bị block đúng) —
không phải regression. 976 − 957 = 19 calls mới applicable là
phone-only calls mà gate cũ không check (3-PH).

**Composition của 15 fires (xem mục 5 cho phone):** 4 cũ từ Round 2
(train_1005 sms.send c_778, train_1033 phone.call c_217, train_1319
ewallet.transfer c_9526 — principled message-history blocks, vì
sms/phone không validate contacts; train_1696 chat_ott.send_message
chat_6142 — gold anomaly, write tự nó fail replay) + 11 phone-number
tồn dư.

## 5. Nhánh phone_number: đo đạc thay đổi thiết kế (phát hiện mới)

Roster-only rule (bản đầu của 3-PH) cho kết quả bất ngờ: trên 19
phone-only gold calls applicable, **17 fires (89%)**. Điều tra từng
case cho thấy framing "phone = contact reference" là SAI với pattern
dominant của gold:

- Gold thường xuyên dial/SMS số **không có trong address book**
  (5/17 samples có book rỗng; có hotline 19001234, số nhà cung
  cấp, số gọi nhỡ) — và simulator KHÔNG BAO GIỜ validate
  phone_number (`phone.call`/`sms.send` tạo record vô điều kiện;
  `contact_ref` chỉ hoàn thiện counterpart khi unique match, không
  reject). Số điện thoại là literal value do user/history đưa, không
  phải entity reference cần book membership.
- 6/17 số có trong prior phone/sms records (callback pattern:
  train_0969, train_1131, train_1283, train_1314, train_1442,
  train_1662) → **thêm nguồn evidence (b)**: số xuất hiện trong
  field `phone_number` của SUCCEEDED prior READ
  (`phone.recent_calls` / `sms.read_recent`) thì established.
  Cố ý LOẠI phone.call/sms.send result phone_numbers — đó là echo
  của chính argument (write không validate), tính vào sẽ launder
  số hallucinated qua lần dùng đầu tiên của nó.
- Sau nguồn (b): fires 21 → 15, false-block rate 2.15% → 1.54%.
  Tests mới: call-log passes + write-echo không pass.
- **11 tồn dư (không roster, không call-log):** số user nói bằng
  chữ số tiếng Việt trong request (0502 hotline, 0579, 0657, 0746,
  0872 — transcript đánh vần "không chín tám bảy…", không phải
  digits nên check text thô không bắt được); số user sửa lại
  (1677: prior call 09832415086 vs gold 09832415068 — near-miss có
  chủ ý, request nói "đuôi là sáu tám chứ không phải tám sáu");
  số trong history user text (0764); số từ nội dung message/nhóm
  chat (0776); không nguồn nào trong text/log/book (0451, 0664,
  0676).
- Hệ quả: **phone_number branch chưa hard-enforce-ready.** Muốn
  harden cần text evidence (spoken digit-words parsing + history
  text) — đó là interface change của gate (hiện gate không nhận
  text), để dành vòng sau, không nhồi vào Round 3. KEEP tổng thể
  vẫn đứng vì phone fires chỉ chiếm 11/976 = 1.13%.

## 6. Các sửa khác + F8 + shadow script

- **F8 contract correction (Thread 1, main xác nhận):** form Round 2
  dùng `banking.open_savings` + `account_id` làm ví dụ "create trả
  new id" là SAI — đó là foreign key trong savings record (và trong
  call thật còn là echo của `from_account_id`). Repro đã sửa:
  F8 nay là calendar.create_event → update_event (passes); thêm
  F8b savings-foreign-key (fires). **Không nới gate để cứu F8.**
- **Adjacent bug tìm được khi làm 2-P (không phải reviewer-flagged):
  boundary amounts.** Điều kiện adjacency `before in "-:" or
  after in "-:"` — `"" in "-:"` là True trong Python, nên code
  3838d99f đông lạnh trả [] cho amount ở đầu/cuối text (verified:
  'chuyển 500000' → [], '500000 là số tiền' → [], chỉ 'chuyển
  500000 đồng' mới work). Fix: `(before and before in "-:") or
  (after and after in "-:")`. Đã có test + repro R3-2P-boundary.
  Row diff mục 4 chứng minh fix này không đổi gold proof nào.
- **Shadow script label fix:** field `code_base` trước đây hardcode
  "3838d99f (frozen…)" — nay ghi đúng lifemate_dir thực tế được
  load, để paired re-run không mang nhãn sai.
- **Thread 2 generalizations (đã vào shadow script):** gold classes
  empty/ask_only/read_only/write/mixed_no_write (bỏ assert ask-only);
  proposal error kinds wrong_action/wrong_reference/wrong_argument/
  missing_slot/prerequisite_skipped; history parse guard (list
  passthrough → JSON-parse → ast.literal_eval → insufficient_evidence,
  không bao giờ zip char-wise lặng lẽ); malformed ask-shape
  normalization (V10 text arm {name, tool_name, params}); narrow
  no-op equivalence (extra arg equivalent chỉ khi bằng observed
  current value của field đó cho entity đó tại prefix);
  gold-prerequisite check (gold match không phải positive hợp lệ
  nếu gold reads/searches trước đó chưa thỏa tại model prefix).
  Guard-decision logic KHÔNG ĐỔI so với Round 2 → paired diff có
  ý nghĩa. Row keys: version / sample / arm / generation_index /
  call name+args.

### 6.1 Paired shadow re-run với code mới (inputs giống hệt Thread 2)

Traces ở /tmp (không push): V10 blob 6765b6a3…, V11 blob b8f91bd2…,
V13 blob 94a2a6ec…. Chạy shadow script mới với repo lifemate/ +
repo e7 audit (defaults), KHÔNG dùng frozen copy.

| Version | Rows | Quyết định | Adjudication |
|---|---|---|---|
| V10 (16 traj, 38 gen: no_call 11, read 8, ask 5, write 14, invalid 0; 14 write proposals, monitored 10 calls/10 args, 4 PROVEN) | 14 | blocked 6 / passed 8 | correct_block 6, **false_block 0**, correct_pass 3, miss 5 |
| V11 (16 traj, 37 gen: no_call 13, read 10, ask 2, write 10, invalid 2; 10 write proposals, monitored 8/8, 2 PROVEN) | 10 | blocked 6 / passed 4 | correct_block 6, **false_block 0**, correct_pass 2, miss 2 |
| V13 (40 traj, 78 gen: 33 no-call + 29 write + 7 read + 5 ask + 4 invalid; 29 write proposals, 16 monitored calls/19 args, 0 PROVEN) | 29 | blocked 16 / passed 6 / oos 7 | correct_block 16, **false_block 0**, correct_pass 0, miss 6, oos 7 |

**Row-identical: V10 14/14, V11 10/10, V13 29/29.** Không một quyết
định nào trên model proposal thật thay đổi dù registry typing,
kind classification, prover fixes và phone-log source đều đã land.
Các dòng nhạy cảm giữ nguyên: 5 light_set generations vẫn passing
(train_0004 — xem dưới), các dòng 0116 phone.call vẫn blocked.
Subset metrics (adjudicated): V10 block precision 6/6 = 1.0, recall
6/11 = 0.545, G2 fired 1/13 applicable; V11 precision 6/6 = 1.0,
recall 6/8 = 0.75, G2 fired 2/8; V13 precision 16/16 = 1.0, recall
16/22 = 0.727. **Independent positive samples vẫn = 1 trên cả ba
traces (chỉ train_0004)** — V10 đúng 1 exact gold match (native
arm, gen 2); V11 cả hai arms (native_control + pseudo_boundary, đều
exact); V10 text arm thêm 2 lần với extra power:"on" (equivalent,
không exact). MỘT tình huống lặp lại, KHÔNG phải ba positives độc
lập. Đây là giới hạn bằng chứng cho mọi claim hard-enforce.

Các case đáng nhớ (không đổi): train_0004 light_set pass hoàn toàn
dựa vào G2 (device_id không phải monitored slot; same-app evidence
smart_home.get_status → light_set — registry tightening đã giữ nó
passing đúng như yêu cầu); train_0008 alarm.update miss: time
PROVEN/offset (derivation hợp lệ) nhưng call sai (gold là một
weather.get_forecast read duy nhất; conditional request, forecast
không bao giờ được check) — **PROVEN ≠ correct call; UNPROVEN ≠
hallucination**, và đây là miss class lớn nhất (6/7 misses V10+V11);
train_0049 text open_savings amount 200000 → UNPROVEN/
observation_cross_app ×3 (cross-app refusal đúng trên proposal
thật); train_0116 phone.call cont_01 blocked bởi G2 + prover ở MỌI
arm/version.

## 7. Readiness và residuals

**Prover + G2: shadow-ready, KHÔNG hard-enforce.** 4 lý do:
1. Registry mapping đã land (lý do 1 của Thread 3 đã đóng).
2. False-block rate trên CORRECT model calls vẫn chưa đo được đầy
   đủ: chỉ 1 independent positive sample (train_0004) trên mọi
   trace — không đủ evidence cho safety claim.
3. Phone_number branch: 11/19 gold phone-only calls vẫn fire dưới
   rule hiện tại (số nói/văn bản) — hard-enforce sẽ veto pattern
   direct-dial hợp lệ.
4. Prover false-proofs 2-P/2-O/2-N đã fix + regression-tested, nhưng
   entity-choice gap vẫn còn (existence ≠ disambiguation — G2 không
   check model chọn đúng entity trong nhiều candidates; V13 6 passed
   đều là existence-valid nhưng intent-wrong).

**G1/G3: DROP không đổi.** G1 relation-aware v2 (nếu muốn) cần fresh
audit như một gate mới — 7/10 FPs cũ là relation-disambiguated
requests mà gate name-only bỏ qua.

**Residuals chưa xử lý (ghi rõ, không giấu):**
- Patch-verified writes: nay đã lift cho 18 tools (4-PV); deletes
  vẫn excluded có chủ ý.
- No invalidation tracking: evidence không bao giờ bị retract sau
  delete/cancel (pre-existing, out of scope).
- Merchant registry field-scoped — yếu nhất trong bảng; merchant
  collection/lookup tương lai sẽ củng cố nó.
- Email `to` lists và video_meeting attendees không phải `*_id`
  string args nên G2 không check (attendees ĐƯỢC simulator validate,
  nhưng không modelled trong G2). Loyalty `program` (name-or-id)
  không check; G2 không check `reward_id` thuộc named program
  (program-membership residual).
- Tools không trả id registry (weather, exchange_rate, fuel_price,
  gold_price, lottery, calculator, ewallet.get_balance scalar,
  home_energy.get_usage, robot_vacuum rooms là names,
  chat_ott.read_chat/send_message messages không id,
  household_chores members là name strings, tv.guide channels là
  name strings) — establish nothing by design.
- Repr-string/list tool-result forms demote thành untyped
  (5-RS); fuzzy 88/8 vẫn chưa validate trên noisy ASR; grounding
  adapter validate-vs-ground ordering vẫn là follow-up cho
  Codex/integration (adapter không thuộc modules vòng này);
  monitored-slot boundary (threshold_kwh, channel, free text) khiến
  guard im lặng by design ngoài scope.
- E7 scope gốc 459/511 vẫn irreproducible (guard code của Codex
  không có trong repo); scope Round 3 là reproducible scope riêng.

## 8. Files thay đổi trong push này (chỉ những file này)

- `lifemate/lifemate_gates.py` — registry tables, `_establishes_*`
  viết lại, `flatten_result_entries`, `registry_for_entry`,
  `kind_by_tool`, phone refs + call-log source, all-slots,
  reference-only echo set, `PATCH_VERIFIED`.
- `lifemate/lifemate_provenance.py` — phone-seq pre-claim,
  boundary adjacency fix, offset proximity, entity requirement,
  6-HR strict AMBIGUOUS.
- `tests/test_lifemate_gates.py` — Thread 1: 2 tests cập nhật hợp
  đồng mới + 16 registry tests; main: +7 TestRound3MainFixes +
  2 phone-log tests.
- `tests/test_lifemate_provenance.py` — +4 TestRound3ProverFixes,
  1 history-reference test cập nhật hợp đồng 6-HR.
- `analysis/e7_dag_shadow_audit.py` — `is_read` + `load_kind_map`,
  roster phones, scope_note + `kind_classification`.
- `analysis/gates_precision_audit.py` — triples flattener, kind map,
  roster phones, `gold_false_block_rate`, `kind_classification`,
  `metric_note` (6-PR).
- `analysis/model_trace_shadow.py` — Thread 2 generalization +
  triples flattener, roster phones, kind param, code_base label
  thật.
- `analysis/repro_codex_counterexamples.py` — F8 sửa hợp đồng +
  F8b + 14 cases R3 (tổng 38).
- `research/lifemate/round10-fix-report-round3.md` — báo cáo này.
- `research/lifemate/round10-fix-report-round2.md` — chỉ thêm
  correction note trỏ sang Round 3 (mục 9).

## 9. Correction note cho báo cáo Round 2 (đọc cùng Round 2)

Các con số Round 2 vẫn đúng DƯỚI verb-list scope của nó, nhưng đã
được SUPERSEDE bởi catalog-kind scope của Round 3 — trích Round 3
khi nói về hiện trạng:
- e7 scope: 556 args → 533 args; DAG 284 → 276; baseline 93 → 92;
  conversion 191 → 184.
- Gates denominator: 971 (verb scope, không phone refs) → 957
  (kind scope, old gate, tập chung) / 976 (kind scope, new gate có
  phone refs).
- G2 "precision 99.6%" (Round 2) → trích dưới dạng gold false-block
  rate: 0.41% (Round-2 scope) / 1.54% (Round-3 scope + rules). Verdict
  KEEP không đổi.
- Round-1 report stale "17/17" đã được sửa trong Round 2; Round-2
  report không còn stale claim nào khác được phát hiện trong
  Round 3 ngoài scope numbers trên.

## 10. Lệnh tái lập (từ repo root, dev 1237, không held-out)

```
python3 -m unittest discover -s tests
/tmp/rfvenv/bin/python -m unittest discover -s tests
python3 analysis/repro_codex_counterexamples.py
python3 analysis/e7_dag_shadow_audit.py --train-jsonl ~/workspace/zaic-data/lifemate/extracted/train+public_test/train/train.jsonl --data-root ~/workspace/zaic-data/lifemate/extracted/train+public_test --split lifemate/splits/train_dev_heldout.json --out-json /tmp/t3_e7_audit.json
python3 analysis/gates_precision_audit.py --train-jsonl ~/workspace/zaic-data/lifemate/extracted/train+public_test/train/train.jsonl --data-root ~/workspace/zaic-data/lifemate/extracted/train+public_test --split lifemate/splits/train_dev_heldout.json --out-json /tmp/t3_gates_audit.json
python3 analysis/model_trace_shadow.py --trace /tmp/t2_v10_trace.json --version v10 --train-jsonl ~/workspace/zaic-data/lifemate/extracted/train+public_test/train/train.jsonl --split lifemate/splits/train_dev_heldout.json --out-json /tmp/t3_v10_shadow.json
# (tương tự v11, v13; traces ở /tmp, không push)
```
