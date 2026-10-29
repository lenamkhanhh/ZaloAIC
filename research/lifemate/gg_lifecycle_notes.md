# G&G lifecycle notes — evidence invalidation (Thread B)

**Scope:** module mới `lifemate/lifemate_evidence_lifecycle.py`
(rule engine + ledger, KHÔNG phải DAG) + tests synthetic
`tests/test_evidence_lifecycle.py`. Không sửa gates, provenance,
simulator, scorer, config hay nhánh SFT. Không đọc held-out.
Mọi khẳng định dưới đây đều có căn cứ implementation trong
`train/zaic_tools/` (data dir, chỉ đọc); dòng nào không đọc được
thì ghi BLOCKED, không đoán.

## 0. Nền tảng outcome (executor.py, base.py)

- Schema reject → `{"ok": False, "error": ...}` (executor
  `Simulator.call` → `_fail`), state không đổi, vẫn ghi log.
- App noop → `{"ok": True, "done": False, "message": ...}`
  (`base.App.noop`: unknown id, không đủ balance, đã cancelled,
  empty search...). State không đổi.
- Success → `{"ok": True}` và `done` không phải False. Chú ý:
  đa số write success KHÔNG có key `done` (App.create/patch/
  delete trả `{"ok": True, ...}`) — đó vẫn là success, KHÔNG
  phải noop. Chỉ `done is False` mới là noop.
- Tool raise exception → executor bắt và trả `{"ok": True,
  "done": False}` — cũng là noop, không invalidate gì.
- Result được deep-copy (`Simulator.call`), nên read result là
  snapshot tại thời điểm đọc — field evidence từ read có thể
  stale ngay sau đó. Đây chính là lý do cần lifecycle.
- `Session.call` ghi arguments vào calls list KỂ CẢ call bị
  reject — proposal/argument không bao giờ là evidence (gates đã
  nói, ledger nhắc lại: mutation event không tạo evidence).

## 1. Ba loại mutation theo implementation

### 1a. Delete — entity biến mất khỏi collection

Cơ chế duy nhất: `base.App.delete` (find → remove khỏi list →
`{"ok": True}` KHÔNG item, KHÔNG done). Delete trên id không tồn
tại → noop, không đổi gì.

| Tool | Registry | Ghi chú |
|---|---|---|
| reminders.delete | reminders.reminders | App.delete trực tiếp |
| alarm.delete | alarm.alarms | App.delete trực tiếp |
| shopping_list.remove | shopping_list.items | App.delete (tên remove, bản chất delete) |
| home_automation.delete_rule | home_automation.rules | App.delete |
| medication.remove | medication.schedules | App.delete |
| email.archive với action="delete" | email.emails | App.delete qua nhánh đặc biệt (xem §3) |

Hệ quả ledger: delete giết cả 3 claim (existence, field_value,
eligibility) của entity đó trong registry đó.

### 1b. Cancel — KHÔNG có cancel nào thực sự xóa

**Kết quả kiểm chứng quan trọng nhất:** quét toàn bộ apps, cả 5
cancel tool đều là `App.patch(..., set={"status": "cancelled"})`
— entity còn nguyên trong collection, chỉ mất eligibility (và
field_value của field `status`). Không tồn tại "cancel xóa thật"
để test theo nghĩa đen; test `test_no_cancel_tool_in_table_deletes`
khẳng định tính chất này từ bảng, và nếu implementation sau này
thêm một cancel-delete thì bảng + test sẽ bắt phải khai báo rõ.

| Tool | Registry | Guard/noop đặc biệt |
|---|---|---|
| calendar.cancel_event | calendar.events | patch, không guard |
| flights.cancel | flights.bookings | patch, không guard |
| food_delivery.cancel_order | food_delivery.orders | patch, không guard |
| ride_hailing.cancel | ride_hailing.rides | patch, không guard |
| subscriptions.cancel | subscriptions.subscriptions | đã cancelled → noop (lần cancel thứ 2 không đổi gì thêm) |

Hệ quả ledger: cancel giết eligibility + field_value `status`,
GIỮ existence và các field_value khác. Hệ quả phụ cần nhớ cho
adapter: `ride_hailing.get_ride` không arg trả về "latest ride
not cancelled" — một ride đã cancel vẫn tồn tại nhưng không còn
là "current ride"; đó là eligibility/read-semantics, không phải
existence.

### 1c. Update/patch — đổi field, entity còn

Cơ chế: `base.App.patch` (find-or-noop; chỉ apply field non-None;
trả `{"ok": True, "item": record}` khi tìm thấy). Patch trên id
không tồn tại → noop. Patch có `require` (smart_home *_set yêu
cầu đúng type) sai type → noop. Patch có `nested="state"`
(smart_home *_set, appliances) thì field path là `state.<field>`.

Các update đáng chú ý (không liệt kê hết — xem MUTATION_TABLE
đầy đủ 85 tool trong module):

| Tool | Registry | Field đổi | Guard |
|---|---|---|---|
| contacts.update | contacts.contacts | phone, email (chỉ non-None) | find-or-noop |
| tasks.complete / reminders.complete | tasks.tasks / reminders.reminders | done=True | idempotent, không guard (complete lại vẫn success) |
| shopping_list.check | shopping_list.items | checked=True | find-or-noop |
| home_security.acknowledge_alert | home_security.alerts | acknowledged=True | find-or-noop |
| door_lock.set_lock | door_lock.locks | locked | find-or-noop (tự check trước patch) |
| alarm.update | alarm.alarms | time/label/enabled | find-or-noop; enabled=False = disable (ledger coi là terminal cho eligibility) |
| household_chores.assign | household_chores.chores | assignee | chore phải tồn tại VÀ assignee phải là member, else noop |
| flights.check_in | flights.bookings | checked_in=True | noop nếu cancelled hoặc đã checked_in |
| video_meeting.join | video_meeting.meetings | status=joined | noop nếu missing hoặc cancelled |
| learning.enroll | learning.courses | enrolled=True | noop nếu missing hoặc đã enrolled |
| subscriptions: xem cancel | — | — | — |
| smart_home.scene_run | smart_home.devices (NHIỀU entity) + active_scene | state.* của mọi action device | ATOMIC: validate hết device trước, thiếu 1 → noop toàn bộ, không apply gì |
| notes.append | notes.notes | content APPEND (không replace) | find-or-noop; claim `content == old` chết, vì content mới là old + "\n" + new |
| email.reply | email.sent (create) + email.emails (update) | original: unread=False, replied=True | original missing → noop |
| email.archive (không action) | email.emails | folder=archive | find-or-noop; existence còn |
| bill_payment.pay | bill_payment.bills (+ ewallet nếu source=ewallet) | paid=True, paid_with | noop nếu missing/đã paid; ewallet: wallet missing/thiếu balance → noop toàn bộ |
| music.add_to_playlist | music.playlists | track_ids append | noop nếu track/playlist missing hoặc đã có |
| tv.record | tv.recordings (create) | — | noop nếu program missing hoặc đã scheduled |
| library.reserve | library.reservations (create) + library.books (update) | book available=False | noop nếu book missing hoặc đã có reservation ready/waiting |
| bike_rental.reserve | bike_rental.reservations (create) + bike_rental.bikes (update) | bike available=False | noop nếu bike missing/không available |
| loyalty.redeem | loyalty.vouchers (create) + loyalty.programs (update) | points giảm | noop nếu program/reward missing hoặc thiếu điểm |
| banking.transfer / open_savings | banking.transactions|savings (create) + banking.accounts (update) | balance giảm | noop nếu account/beneficiary missing hoặc thiếu balance |
| ewallet.* | ewallet.transactions (create) + ewallet balance (update) | balance giảm | noop nếu thiếu balance |
| learning.log_progress | learning.progress (create) + learning.courses (update) | progress_minutes tăng | course missing → noop |

Hệ quả ledger: update giết field_value của field bị chạm
(touched set suy từ args non-None, trừ id-args; adapter có thể
cấp `fields` chính xác, vd `["state.power"]`). Update KHÔNG
giết existence (trừ existence record được ground bởi chính
field bị đổi — vd số phone được ground từ field phone của
contact thì chết khi phone đổi; xem module
`_record_killed_by`). Update giết eligibility CHỈ khi set
status → "cancelled" hoặc enabled → False. Các guard đặc thù
theo action (check_in sau check_in, join sau join, reserve sau
reserve, pay sau paid) KHÔNG được mô hình hóa bởi eligibility
chung — adapter phải check từ field_value (checked_in,
status, paid...) hoặc re-read; ledger chỉ cung cấp field
evidence, không giả vờ generic eligibility bao hết mọi guard.
Lý do: ví dụ flights.cancel (patch không guard) vẫn success
trên booking đã checked_in, nên giết eligibility chung khi
check_in sẽ sai cho cancel.

### 1d. Create — sinh entity mới, không giết gì

`base.App.create` (id mới qua `new_id`, prefix + số thứ tự).
Create không invalidate claim nào. Create chỉ thành evidence khi
adapter ghi result của nó thành evidence record.

**Edge đã xác minh — id reuse:** `new_id` tính `n = len(existing)
+ 1` và bỏ qua id đã có, nên sau một delete làm collection co
lại, id vừa xóa CÓ THỂ được cấp lại cho entity mới. Ledger xử
lý đúng nhờ thứ tự position: record cũ bị giết vẫn chết, chỉ
record create-result mới (position sau) mới re-establish. Adapter
bắt buộc phải ghi create-result thành evidence record, không
được suy "id từng tồn tại nên vẫn tồn tại".

### 1e. Read-only / meta (không mutation)

weather, exchange_rate, gold_price, fuel_price, calculator
(pure compute), maps search/route, package track, lottery
results/check, news headlines/search, podcast search, library
search, fitness get_activity, home_energy get_usage, tv guide,
music list_tracks, chat list/read, sms read_recent, phone
recent_calls, email list/read, contacts search/get, cùng mọi
list/get/search còn lại. `sys.ask_missing_info` là meta: chỉ ghi
call list, không chạm state.

## 2. Schema và semantics truy vấn (interface cho điều phối viên)

Evidence record và mutation event đúng schema đã chốt (xem
docstring module). Ba điểm adapter PHẢI tuân thủ, vì module
không tự suy ra được:

1. **Registry phải được cấp rõ.** Thứ tự resolve: key
   `registry` tường minh > `counterpart["registry"]` > registry của
   producer tool trong MUTATION_TABLE > `"unknown"` (chỉ query
   được dưới `"unknown"`, không bao giờ match nhầm registry
   thật). Với cross-app FK (home_automation rule → smart_home
   device; booking → flight; message → contact), registry là
   registry CHỨA record, không phải registry được FK trỏ tới.
2. **Phân loại mutation cần argument, không chỉ tên tool.**
   `email.archive`: action == "delete" → delete, còn lại →
   update folder. `bill_payment.pay`: source == "ewallet" →
   thêm event debit wallet + create ewallet transaction.
   Multi-effect tools cần MỘT event cho MỖI cặp (registry,
   entity) bị ảnh hưởng (danh sách `side_effects` trong
   MUTATION_TABLE; scene_run cần một event mỗi device).
3. **Field_value query là entity + field query.** Truyền entity
   id làm `value` và field path làm `field`. Query field_value
   không field sẽ fail-closed (`field_value_query_requires_field`)
   trừ khi đúng một field được ghi cho entity đó. Phone
   normalization thuộc Thread A — ledger so sánh value đúng như
   được cấp, không tự fold.

Semantics query: một key là `active` nếu CÒN ÍT NHẤT MỘT record
độc lập sống sót (mutation chỉ giết record nó link tới, theo
registry + entity: `record.value == entity` hoặc
`counterpart["id"] == entity`); `invalidated` nếu đã từng có
record nhưng tất cả đều bị giết; `unknown` nếu không có record,
record ambiguous/outcome không succeeded, hoặc derived source
chết. `query(position=P)` chỉ thấy journal tới P — mutation
tương lai không ảnh hưởng prefix hiện tại (đã test).

Derived claims: record mang `derived_from` (list
{registry, value, claim[, field]}) hoặc
`counterpart == {"derived_from": [...]}`. Source invalidated →
derived `unknown` (lý do `derived_source_invalidated`); source
unknown → `unknown` (`derived_source_unknown`); cycle →
`unknown` (`derived_cycle`). Đây là link-following đệ quy có
guard, KHÔNG phải DAG (không dựng graph, không topological
sort, không proof search) — báo cáo và brief tích hợp phải gọi
đúng tên "ledger/rule engine", không gọi "DAG hoàn chỉnh".

Ví dụ derived thật trong simulator (để adapter tham chiếu):
- video_meeting link = hàm (meeting id mới, start) — link chết
  theo nghĩa unknown nếu start đổi (hiện không có tool update
  meeting, nên case này chủ yếu là phòng thủ).
- door_lock guest code = hàm (lock_id, valid_until) — code
  unknown nếu lock field liên quan đổi (locks không có tool
  delete/update ngoài set_lock locked — locked không ảnh hưởng
  code; valid_until không update được; vẫn là derived đúng
  nghĩa, test bằng synthetic update trường valid_until).
- Giá trị thực tế hay gặp nhất: phone/contact suy từ contact
  record (contact_ref completion) — contacts.update đổi phone
  thì derived phone → contact mapping cũ unknown (đã test dạng
  grounding-field existence).
- Snapshot nhúng: flights.my_bookings nhúng flight fields vào
  booking view — flights record không có tool update/delete nên
  snapshot không stale trong thực tế; KHÔNG lấy đó làm ví dụ
  derived-invalidation (ghi rõ để tránh claim sai).

## 3. Trường hợp đặc biệt (đã xác minh, dễ sai)

- **email.archive delete branch:** trả `{"ok": True}` KHÔNG item,
  KHÔNG done. Đây là success (delete thật), không phải noop.
  Phân biệt bằng action arg, không bằng "có item hay không"
  một cách mù — vì App.delete nói chung cũng không trả item
  (gates PATCH_VERIFIED đã dùng path == "item" để phân biệt
  đúng: nhánh delete không có entry id nào để (mis)use).
- **App.patch echo:** patch success trả lại record chứa id bằng
  đúng id-arg — đó là patch-verified (gates PATCH_VERIFIED),
  không phải blind echo. Ledger không xử lý establishment (việc
  của gates); ledger chỉ xử lý invalidation, và patch success
  KHÔNG giết existence (nó vừa chứng minh entity còn đó).
- **contact_ref completion (sms/phone/ewallet):** result
  contact_id/phone_number là echo của argument hoặc completion
  từ roster — không phải evidence độc lập. Adapter KHÔNG được
  feed proposal args hay write echo thành evidence record.
- **scene_run atomicity:** validate tất cả action devices trước
  rồi mới apply; thiếu 1 device → toàn bộ noop. Một scene_run
  noop không giết field claim của bất kỳ device nào.
- **Upserts (không phải create thuần, không phải update thuần):**
  bill_payment.schedule_autopay (theo type), maps.save_place
  (theo place_id, save lại chỉ relabel), news.save (theo
  article_id, save lại giữ single entry). Adapter phân loại
  theo trạng thái trước (có entry → update, chưa có → create);
  ledger ghi kind do adapter cấp.
- **Global state (không phải entity):** home_security.arm
  (mode), music/tv/podcast now_playing, robot_vacuum status,
  home_energy alert_threshold, fitness goal_steps, ewallet
  balance. Ledger biểu diễn bằng registry `<app>.global` và
  entity_value là tên field (vd "mode", "balance") — xem bảng.
  (Adapter có thể chọn key khác, nhưng phải nhất quán giữa
  evidence và mutation event cho cùng một global field.)
- **package_tracking:** reschedule key theo tracking_id (không
  phải id riêng) — registry `package_tracking.shipments`,
  entity_value = tracking_id.
- **Catalog vs implementation naming:** tên tool trong bảng lấy
  từ method implementation và khớp với tên trong PATCH_VERIFIED
  của gates (cùng một bộ tên). Adapter nên assert khớp catalog
  khi tích hợp; nếu catalog có tool implementation không hỗ trợ
  (executor trả schema fail "chưa được simulator hỗ trợ") thì đó
  là schema_rejected, không phải mutation.

## 4. Kết quả tests

`tests/test_evidence_lifecycle.py` — 34 tests, synthetic only
(không fixture gold, không sample id, không đọc data dir):

| Backend | Kết quả |
|---|---|
| system python3 (3.12.3) | 34 pass / 0 fail / 0 error / 0 skip |
| venv python (zaic-test-venv) | 34 pass / 0 fail / 0 error / 0 skip |

Bao phủ 10 nhóm bắt buộc: (1) delete → existence/field/
eligibility chết; (2) cancel status-only (calendar) → existence
còn, eligibility + status chết; (3) update → chỉ field bị chạm
chết (+ grounding-field existence, + nested state.*, +
unknown-fields conservative, + disable → eligibility chết);
(4) schema_reject/noop/ineffective/non-dict → không giết gì,
failed/ambiguous evidence không bao giờ active; (5) re-read
success tái lập (+ new value supersede, + noop read sau delete
không revive); (6) derived → UNKNOWN khi source chết (+
survive khi update không liên quan, + cycle → unknown);
(7) hai registry cùng chuỗi id không lẫn; (8) future mutation
vô hình với prefix query (+ apply_prefix tự sort theo
position); (9) không có cancel nào xóa thật (assert từ bảng) +
email.archive hai nhánh; (10) multi-effect (balance chỉ giết
balance, scene_run per-device, check_in noop trên booking đã
cancel không revive, create không giết gì, id reuse cần fresh
evidence). Thêm: outcome classification units, table sanity
(85 tool: 41 update, 33 create, 5 cancel, 5 delete, 1 none),
field_value query fail-closed khi ambiguous.

Lưu ý về 2 failure ban đầu khi chạy (đều là test bug, đã sửa,
không phải module bug): (a) helper test tự biến result=None
thành `{"ok": True}` nên case "non-dict" sai — sửa thành chuỗi
"not-a-dict" thật; (b) update với args={} đúng ra không chạm
field nào (patch chỉ apply non-None) nên không giết gì — case
"unknown fields" phải là event KHÔNG có key args. Cả hai đều
được giữ lại thành ghi chú trong test để lần sau không tái phạm.

## 5. Những gì module KHÔNG làm (để điều phối viên/Codex khỏi tích hợp sai)

- Không phân loại tool call thành mutation event (việc của
  adapter, cần action arg + side-effect events).
- Không mô hình hóa guard theo action (check_in/join/reserve/
  pay...): eligibility chung chỉ chết bởi delete, cancel
  status-only, update status → cancelled / enabled → False.
- Không normalize phone/text, không parse history repr/list
  (việc của Thread A và adapter).
- Không tự tạo evidence từ mutation event (kể cả create).
- Không claim DAG: đây là ledger + rule engine với derived
  link-following đệ quy.
- Không hard-enforce, không đổi score, không sửa gates: tích
  hợp là shadow-only, theo brief của điều phối viên.

## 6. BLOCKED / chưa rõ (không đoán, cần adapter hoặc Codex xác nhận khi tích hợp)

- **Không có BLOCKED về implementation của app nào:** đã đọc
  hết các app có write tool (base + 40+ app). Hai chỗ đọc bằng
  grep/sed thay vì đọc full file (learning.schedule_lesson,
  podcast play/subscribe/queue) nhưng body đủ để phân loại —
  không còn nghi ngờ về kind/registry.
- **Cần adapter xác nhận (không phải blocker của module):**
  (a) tên tool catalog khớp 1-1 với method implementation
  (khớp với PATCH_VERIFIED nên khả năng cao là khớp);
  (b) cách adapter lấy `entity_value` cho create events (id mới
  nằm trong result `id`/`item.id` — ledger không tự trích);
  (c) global-state key naming (`<app>.global` + field name) có
  được adapter dùng nhất quán cho cả evidence và mutation hay
  không;
  (d) field path cho nested patch: adapter nên cấp `fields`
  dạng `["state.power"]` thay vì để ledger suy từ args (suy từ
  args cho ra `"power"`, vẫn match nhờ rule `state.` + tên, nhưng
  cấp explicit thì rõ ràng hơn).
- **Không tìm thấy (ghi rõ thay vì bịa):** không có app nào có
  cancel tool thực sự xóa entity; không có tool update cho
  flights/flight record, video_meeting meeting (ngoài join),
  guest_code, hay menu — nên các derived claim từ những record
  đó không có đường invalidation thực trong simulator hiện tại
  (chỉ có đường synthetic/phòng thủ).
- **Giới hạn thiết kế cần Codex biết:** field_value query bắt
  buộc field khi entity có nhiều field (fail-closed); derived
  source cho field_value nên ghi rõ field, nếu bỏ field thì
  match bất kỳ field nào của entity đó (leniency có ghi rõ
  trong docstring — adapter nên tránh dựa vào đó).

## Reviewer round-2 fixes (coordinator-applied, 2026-10-29)

- R2-B1: explicit `fields` added to 9 fixed-field update
  entries (implementation-verified in zaic_tools): tasks.complete
  [done], reminders.complete [done], shopping_list.check
  [checked], flights.check_in [checked_in], video_meeting.join
  [status], email.archive update branch [folder],
  music.add_to_playlist [track_ids], bill_payment.pay
  [paid, paid_with], podcast_radio.subscribe [subscriptions].
  The adapter forwards table `fields` into primary update
  events (previously only side-effect fields were forwarded);
  `build_ledger` notes now log `mutation_fields` as a test hook.
- R2-B2: email.archive delete branch is implemented ONLY in the
  adapter (reclassify by action arg, tested both branches at
  adapter level); the table entry documents kind_arg + the
  update-branch fields and warns that direct table users must
  reclassify first. The table alone still cannot decide the
  branch -- that is by design, not a bug to fix in the table.
- Consumer->claim mapping (L3) remains adapter/Codex future
  work: the ledger supplies existence/field_value/eligibility
  claims; action-specific guards (check_in/join/reserve) need a
  per-consumer claim map that does not exist yet. The gate this
  round queries existence only.
