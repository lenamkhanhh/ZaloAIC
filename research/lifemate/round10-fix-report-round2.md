# Round 10 fix — Round 2: structured G2 evidence, roster-intent fix, model-trace shadow

Tiếp nối báo cáo Round 1 (`round10-fix-report.md`). Cùng nhánh
`round10-provenance-gates-fixes`, KHÔNG merge main. Base Round 2 là
commit Round 1 `e00c864c`; commit cuối Round 2 ghi trong thông điệp
bàn giao + MEMORY.md (báo cáo không thể chứa SHA của chính commit
chứa nó).

Phạm vi vẫn chỉ modules/tests/audit/report. Không sửa inference,
simulator, scorer, benchmark config; không GPU, training, held-out,
không tự merge main.

## 0. Đặt tên trung thực (kế thừa Round 1)

Module provenance vẫn là typed-evidence RULE ENGINE trả Verdict,
không phải DAG đồ thị (không có parent pointer/invalidation graph).
Gate 2 vẫn là predicate thuần CPU trên evidence đã quan sát.

## 1. Từng điểm Codex nêu: tái hiện, phân tích, sửa

### 1.1 H5: fixture sai hợp đồng, không phải runtime sai

Tái hiện: chạy lại script trên code Round 1 cho đúng 16/17, H5 FAIL
(`expected=SUPERSEDED actual=UNPROVEN/none`, exit 1). Nguyên nhân:
fixture H5 dùng `history_call_args` 2-tuple (không có outcome), nhưng
Round 1 đã siết `_call_entry_succeeded` — 2-tuple = outcome unknown
→ không phải evidence. Claim 17/17 trong báo cáo Round 1 được ghi
TRƯỚC lần siết đó nên đã stale; Codex kiểm tra độc lập đúng.

Sửa (fixture/expectation, KHÔNG nới runtime để cứu test):
- H4: chuyển sang 3-tuple `succeeded=True` — trước đó H4 pass một
  cách rỗng (không có evidence nào nên cancel logic chưa từng được
  kiểm chứng thật). Nay cancel được kiểm chứng với evidence hợp lệ
  và vẫn UNPROVEN.
- H5: chuyển sang 3-tuple `succeeded=True` — supersede qua history
  reference được kiểm chứng thật, verdict SUPERSEDED/supersede.
- H5b (mới): cùng text correction như H5 nhưng history 2-tuple
  (unknown outcome) → UNPROVEN. Đây là kiểm chứng trực tiếp nguyên
  tắc "outcome unknown không cấp bằng chứng".
- Đính chính claim 17/17 trong báo cáo Round 1 (3 chỗ) + §9 nguồn
  (xem §6).

### 1.2 G2: flat string không phải evidence (c_fake)

Tái hiện đúng như Codex: `phone.call{contact_id: c_fake}` với
`PriorCall(calendar.list_events, {}, result_scalars=["c_fake"],
succeeded=True)` cho `fired=False` ở code Round 1. Nguyên nhân:
gate cũ gom mọi scalar kết quả thành một tập string phẳng toàn cục
— một mô tả/nội dung tự do đúng bằng `c_fake` cũng "chứng minh"
contact tồn tại.

Sửa — G2 v2, evidence có cấu trúc (`PriorCall.result_entries` là
danh sách cặp `(field, value)` từ result, phones dropped):
- Contact: chỉ từ roster, hoặc field `id`/`contact_id` trong kết quả
  của contacts-app (read verify bằng lookup; write cần non-echo);
  field `name` chỉ từ contacts-app READ. Kết quả app khác KHÔNG
  bao giờ xác lập contact — kể cả khi field là `id` (một calendar
  `id` bằng `c_fake` không phải contact record).
- `*_id` khác: field phải là `id` hoặc đúng field của slot
  (ví dụ `ride_id`); free-text field (`content`, `description`,
  `title`, `note`...) và scalar trần (field None) không bao giờ
  tính. Một generic `id` từ READ được tính bất kể app family
  (xem 1.4: ids là registry-scoped state observations).
- Mọi reference vẫn được kiểm tra (không early return).

### 1.3 Echo exclusion: read lookup vs write echo

Đọc implementation `zaic_tools` (ride_hailing.py, base.py, sms.py,
phone.py, contacts.py) và phân biệt theo contract, không theo cảm
tính:
- READ verify bằng lookup: `ride_hailing.get_ride` có decorator
  `@read`, dùng `find("rides", ride_id)` — tìm thấy mới trả ride,
  không thấy trả `noop()` = `{ok: True, done: False}` → không phải
  succeeded theo hợp đồng. Vì vậy read thành công xác nhận ID đầu
  vào, kể cả khi ID kết quả bằng ID đối số. Ca Codex (get_ride
  thành công → cancel) nay PASS, đúng.
- READ rỗng/noop/thất bại: `succeeded=False` → không xác lập gì.
- CREATE thành công trả ID mới: ID mới khác đối số → non-echo →
  xác lập (ví dụ `banking.open_savings` trả `account_id` mới).
- WRITE chỉ echo đối số: không xác lập. `sms.send`/`phone.call`
  KHÔNG validate contact (`contact_ref` trả id nguyên vẹn) và kết
  quả của chúng mang `contact_id` echo — kể cả khi echo nằm trong
  message/call dict lồng nhau (phát hiện này loại bỏ phương án
  "nested dict = record thật": message dict có đủ field khác nhưng
  `contact_id` trong nó vẫn là echo, không phải identity).
- ID trong free text hoặc field không liên quan: không xác lập.

Residual có chủ ý (ghi rõ, không giấu): write dạng patch
(cancel/update) trả full record của entity mà nó đã lookup — về
mặt ngữ nghĩa nó ĐÃ xác minh entity, nhưng kết quả của nó không
phân biệt được bằng shape với echo không-validate (cùng là record
chứa ID đối số). Quy tắc hiện tại loại trừ cả hai (conservative).
Muốn nhận patch-verified cần danh sách verb lookup (update/delete/
cancel...) — đã cân nhắc và LOẠI (xem §5): danh sách verb là
heuristic dễ phân loại sai và âm thầm mở lỗ hổng echo.

### 1.4 Sửa luật rồi lại sửa luật: app-family cho generic "id"

Bản G2 v2 đầu tiên yêu cầu field `id` generic phải cùng app family
(calendar `id` ≠ alarm `id`). Re-audit gold cho thấy luật này quá
chặt: 11 gold writes `home_automation.create_rule{device_id}`
bị chặn vì device id chỉ xuất hiện trong `smart_home.get_status`
(khác app). Đọc implementation: `create_rule` ghi rõ trong
docstring "device_id must exist in smart_home.devices" — hai app
dùng CHUNG một registry devices. Evidence là thật, luật mới là sai.

Sửa: bỏ điều kiện app-family cho READ. Một `id` từ READ là state
observation; ids là registry-scoped (có prefix theo domain, trừ
device ids vốn chỉ sống trong đúng một registry). Giả định này được
ghi rõ làm residual: nếu hai registry từng collide cùng chuỗi `id`
thì sẽ false pass — trong catalog 147 tool hiện tại không có
collision như vậy (kiểm chứng bằng re-audit: sau khi bỏ app-family,
gold FP còn 4, không xuất hiện false pass mới nào ngoài 3 ca
contact message-history đã phân tích ở §4.1).

### 1.5 Roster intent: proposal tự sinh contact_name (lỗi thật)

Kiểm tra thêm theo yêu cầu: `_roster_intent` ở Round 1 coi
`call_args["contact_name"]` bằng tên roster entry là một "mention".
Đó là lỗ hổng tự sinh evidence: model bịa `contact_name="Minh"`
trong proposal sẽ tự PROVEN `contact_id` của Minh dù user không
hề nói "Minh". Đã sửa: intent CHỈ lấy từ user text hiện tại
(full-name phrase hoặc token độc quyền); `contact_name` trong
proposal không còn là nguồn mention (tham số `call_args` được gỡ
khỏi `_roster_intent`).

Phạm vi, nói rõ: lỗi này xảy ra NGAY CẢ KHI `contact_name` là
argument hợp schema (không chỉ extra-schema), vì giá trị của nó
đến từ model chứ không phải user. Vấn đề LIỀN KỀ nhưng NGOÀI
phạm vi modules Round 1–2: adapter grounding (Round 5) viết lại
`contact_name`→`contact_id` bất kể tool schema có field đó không,
trong khi `Simulator.validate` BỎ QUA unknown args, và hook Round 8
chạy ground TRƯỚC validate. Thứ tự sanitize/validate dự kiến đúng
là: validate schema trước (loại/báo unknown args), rồi mới ground
các arg đã biết — hoặc adapter phải kiểm tra schema keys trước
khi viết lại. Điểm này được ghi làm follow-up, KHÔNG sửa adapter
trong round này (adapter không thuộc hai module của mandate;
config/integration thuộc Codex).

Tác động gold: re-run e7 audit sau khi sửa cho số IDENTICAL với
Round 1 (284/93/191, cùng phân bố rule) — không một gold contact
proof nào dựa vào clause `contact_name`, nên sửa này không tốn
coverage gold nào.

## 2. Tóm tắt cơ chế G2 v2

```
reference (slot S, value V) được xác lập iff tồn tại PriorCall
succeeded với entry (F, V) sao cho:
  contact_id: V ∈ roster ids, hoặc contacts-app result với
    F ∈ {id, contact_id} (read: luôn tính; write: chỉ non-echo)
  contact name: V ∈ roster names, hoặc contacts-app READ với
    F == name
  *_id khác: F == "id" hoặc F == S, và (read: luôn tính;
    write: chỉ khi V ∉ string-values(args))
bare-mutate (không có id arg): cần một READ succeeded cùng app family
trước đó. Failed/noop/empty read: succeeded=False, không tính.
```

## 3. Lệnh tái lập

```bash
cd ~/workspace/zalo-aic-round3
# Repro 23 ca (expect: 23/23 PASS, exit 0)
python3 analysis/repro_codex_counterexamples.py
# Unit tests, cả hai backend (expect: 117 tests OK mỗi backend)
python3 -m unittest discover -s tests
/tmp/rfvenv/bin/python -m unittest discover -s tests
# Gold shadow audit (expect: DAG 284/556, baseline 93, conversion 191)
python3 analysis/e7_dag_shadow_audit.py \
  --train-jsonl ~/workspace/zaic-data/lifemate/extracted/train+public_test/train/train.jsonl \
  --data-root ~/workspace/zaic-data/lifemate/extracted/train+public_test \
  --split lifemate/splits/train_dev_heldout.json \
  --out-json /tmp/e7_dag_audit_R2.json
# Gates audit (expect: G2 KEEP 99.6%, G1/G3 DROP; old-vs-new 3/0)
python3 analysis/gates_precision_audit.py \
  --train-jsonl ~/workspace/zaic-data/lifemate/extracted/train+public_test/train/train.jsonl \
  --data-root ~/workspace/zaic-data/lifemate/extracted/train+public_test \
  --split lifemate/splits/train_dev_heldout.json \
  --out-json /tmp/gates_audit_R2.json
# Downgrade adjudication 355 -> 284 (expect: 72 invalid, 0 unclassified, exit 0)
python3 analysis/downgrade_adjudication.py \
  --old ~/workspace/round10-base/e7_dag_audit_OLD.json \
  --new /tmp/e7_dag_audit_NEW.json
# Model-trace shadow (trace đã có sẵn trên nhánh tại
# analysis/runtime/e5_v13_diagnostic_trace.json, blob SHA
# 94a2a6ec95470e0e63258d8b0592e2d627d0a64f)
python3 analysis/model_trace_shadow.py \
  --trace analysis/runtime/e5_v13_diagnostic_trace.json \
  --train-jsonl ~/workspace/zaic-data/lifemate/extracted/train+public_test/train/train.jsonl \
  --split lifemate/splits/train_dev_heldout.json \
  --out-json /tmp/model_trace_shadow.json
```

## 4. Số đo — ba tầng TÁCH RIÊNG (synthetic, gold, model-trace)

### 4.1 Gold coverage + gates (dev 1237)

- E7 shadow: KHÔNG ĐỔI so với Round 1 — DAG 284/556 (51.1%),
  baseline 93, conversion 191; scope 479 writes/556 args giữ nguyên;
  phân bố rule giống hệt (roster 89, assembly 53, relative_date 37,
  observation 4, number_words 23, number_digits 17, offset 34,
  duration 24, supersede 3). Sửa roster-intent tốn 0 coverage gold.
- Gates: G1 90.5% DROP (không đổi), G3 literal 84.6% fire DROP,
  G3 scoped 50% DROP (không đổi). **G2: applicable 971, FP 4,
  precision 99.6% Wilson [98.9, 99.8] → KEEP** (ngưỡng 95%).
  Old-vs-new (Round 1 flat-string → Round 2 structured):
  old_passed_new_fired 3, old_fired_new_passed 0.
  - 1 FP là gold anomaly train_1696 chat_6142 (write mà chính gold
    cũng fail replay — gate chặn ở đó là ĐÚNG, giữ anomaly trong
    báo cáo, không drop mẫu).
  - 3 FP còn lại là contact chỉ xuất hiện trong message/call
    history (sms.read_recent / phone.recent_calls) mà chưa từng qua
    address book: theo implementation (sms/phone không validate
    contact), message record với contact_id KHÔNG chứng minh contact
    tồn tại trong address book — đây là block conservative có
    nguyên tắc, không phải lỗ hổng luật. (11 ca device ban đầu bị
    chặn bởi luật app-family đã được sửa ở §1.4 và nay pass.)
- LƯU Ý DIỄN GIẢI (sửa cách nói Round 1): 355→284 là thay đổi
  coverage sau khi sửa semantics/evidence, KHÔNG đồng nghĩa "mọi
  gold value cũ đều sai". Xem §4.4.

### 4.2 Synthetic (không phải deployment precision)

- Repro: **23/23 PASS, exit 0** (17 cũ đã sửa fixture + H5b mới +
  F5–F9 mới: flat-string, read-lookup, noop-read, create-new-id,
  free-text-field).
- Unit tests: **117 tests PASS trên cả hai backend** (difflib và
  RapidFuzz), gồm 5 test G2 mới (flat-string, read-lookup/noop,
  write-non-echo/patch-echo, shared-registry/message-history) và
  1 test roster-intent (proposal contact_name không phải intent).
- CẢNH BÁO LẶP LẠI: TP/(TP+FP) trên synthetic tự thiết kế KHÔNG
  phải "real deployment precision" — chỉ số gold ở §4.1 và shadow
  ở §4.3 mới mang ý nghĩa đó, mỗi cái trong denominator của nó.

### 4.3 Model-trace shadow (lần đầu có số thật, không còn BLOCKED)

Nguồn: `analysis/runtime/e5_v13_diagnostic_trace.json` trên chính
nhánh (blob SHA 94a2a6ec... đã verify) — 40 trajectories (20 mẫu
dev × 2 arms control/rule), 78 generation events. Con số "45
proposals" cũ KHÔNG dùng nữa; đếm lại từ đầu bằng catalog kind:
- Generations: 78 = 33 no-call (parsed null: model stop/text) +
  45 parsed-call = **29 write** + 7 read + 5 ask + 4 invalid
  (pseudo-call `__invalid__`). Tool events (executed): 38 = 26 write
  + 7 read + 5 ask. **29 write proposals, 16 monitored calls,
  19 monitored arguments.** 3 proposals được propose nhưng không
  executed (phone.call 0116 control, ewallet.transfer 0287 control,
  reminders.create thiếu time 0116 rule — lý do không execute
  không ghi trong trace).
- Tất cả 20 sample id đều thuộc dev (assert trong script). Gold
  trên cả 20 mẫu đều là MỘT call `sys.ask_missing_info` duy nhất
  (đã assert): đây là mẫu ask-first chẩn đoán E5 — mọi write
  proposal đều sai về ACTION theo gold, nên KHÔNG có gold value
  để so sánh argument; script KHÔNG tính prover precision/recall
  theo gold value (tính như vậy trên trace này sẽ là sai phương
  pháp). TARGET/CONTROL chỉ là grouping thí nghiệm E5, không phải
  gold standard khác nhau (gold ask ở cả hai nhóm).
- Causal prefix đúng nguyên tắc: current text =
  model_current_transcript, history user text = history_asr theo
  thứ tự u-number, history tool records từ input gốc của sample,
  turn evidence chỉ từ tool events TRƯỚC proposal trong cùng trace;
  proposal hiện tại, proposal bị reject và future result không làm
  nguồn; gold chỉ để xác định "đúng ra phải ASK".
- Kết quả guard decision trên 29 write proposals (gold = ask):
  **blocked 16, passed 6, out-of-scope-guard 7.**
  - 16 monitored calls: **16/16 bị chặn** (toàn bộ qua prover;
    2 ca còn bị G2 chặn thêm: phone.call cont_01 và
    ewallet.transfer contact_mom — đúng 2 id bịa). **19/19
    monitored args UNPROVEN/AMBIGUOUS, 0 PROVEN** — prover không
    bịa ra derivation nào trên mẫu should-ask (0 false proof, 0 ca
    cần phân xử PROVEN). Đây là kết quả mạnh nhất của shadow.
  - 6 passed (3 proposal × 2 arms): email.reply mail_6244,
    library.reserve book_5170, email.archive mail_90 — references
    ĐÃ established (G2 pass đúng luật: entity tồn tại) và KHÔNG có
    monitored arg. Guard không bắt được lỗi này vì lỗi nằm ở
    ACTION/chọn entity (gold ask vì chưa xác định được email/sách
    nào), không phải ở giá trị argument hay sự tồn tại. G2 kiểm
    tra existence, không kiểm tra disambiguation — giới hạn thật,
    xem §6.
  - 7 out-of-scope: notes.create (free text), home_energy.set_alert
    threshold_kwh, tv.tune channel, reminders.create thiếu time —
    không monitored arg, G2 không áp dụng. Thiếu slot là việc của
    grammar, không phải guard này; threshold_kwh/channel cho thấy
    biên monitored slot hiện tại chưa phủ các ask-param đặc thù
    từng tool.
  - ASR divergent (so sánh đã chuẩn hoá: lowercase, bỏ dấu câu):
    27/29 proposals — ASR lệch gold transcript ở hầu hết mẫu, nhưng
    guard dùng transcript model thực nhận nên quyết định không phụ
    thuộc vào so sánh với gold.
  - Nói gọn đúng bản chất: trong phạm vi của nó (monitored args +
    references), guard chặn 100% write should-ask; ngoài phạm vi
    đó nó im lặng theo thiết kế. "16/29 blocked" KHÔNG phải điểm
    chất lượng tổng — mẫu số 29 gồm cả những lỗi guard này không
    được thiết kế để bắt.

### 4.4 Adjudication 355 → 284 (đính chính diễn giải Round 1)

Script `analysis/downgrade_adjudication.py` join OLD (Round 10) với
NEW (Round 1) theo (sample, tool, slot), phân loại từng ca PROVEN→
UNPROVEN/AMBIGUOUS theo rule diff (không suy ra từ việc "rule mới
không chấp nhận"):
- **72/72 downgrades là invalid-old-proof theo construction,
  0 unclassified, 0 window-artifact** (exit 0). Phân bố: assembly
  xuyên text/không link 28, roster không intent/trùng tên 10,
  observation scalar bỏ qua field/entity/source 14, observation
  chứng minh contact 6, observation che ambiguity của history
  reference 2, relative_date midnight 5, relative_date từ value
  xuyên app không link 1, duration từ start chưa proven 4,
  number span/substring/phone/id 2.
- 3 ca cuối được kiểm tra tay riêng (train_1236: old relative_date
  trong khi current text không có time span nào — value chỉ có
  trong ride booking khác app, không link; train_1378/1696: old
  observation che history reference có 3–4 candidates — verdict
  mới AMBIGUOUS là đúng, không phải mất coverage của proof hợp lệ).
- 18 re-attributions PROVEN→PROVEN (đổi rule nhưng giữ verdict:
  observation→offset 10, observation→duration 3,
  observation→roster 4, assembly→offset 1) — proof cũ sai nhưng
  giá trị vẫn chứng minh được bằng cơ chế đúng.
- **Diễn giải đúng**: "invalid old proof" nghĩa là DERIVATION cũ
  không thực sự xác lập giá trị (trích dẫn sai nguồn/sai field/
  sai typing/thiếu link/thiếu intent), KHÔNG có nghĩa gold value
  trong 72 ca đó sai. Gold là reference trajectory; một giá trị
  gold đúng vẫn có thể từng được "chứng minh" bằng lý do sai.
  Báo cáo Round 1 viết "71 ca false-PROVEN" — hiểu đúng là 72 ca
  downgrade (64 UNPROVEN + 8 AMBIGUOUS) có proof cũ không hợp lệ
  theo construction, không phải 72 gold value sai.

## 5. Hướng đã thử nhưng loại

- Luật app-family cho generic `id`: đã implement, re-audit cho
  thấy chặn sai 11 gold device-rule (shared registry, §1.4) →
  bỏ, thay bằng nguyên tắc registry-scoped + ghi residual.
- Test "nested dict = record thật" để phân biệt patch-verified với
  echo: bị bác bởi sms.send — message dict lồng nhau vẫn chứa echo
  `contact_id` (không phải identity của contact) → chỉ còn echo
  test trên args + read/write distinction là đáng tin.
- Danh sách verb lookup cho patch-verified writes (update/delete/
  cancel...): heuristic, dễ phân loại sai một verb và âm thầm mở
  lại lỗ hổng echo → giữ exclusion conservative, ghi residual.
- Bật lại G1/G3 sau khi sửa vài ví dụ: KHÔNG — verdict DROP giữ
  nguyên theo luật <95% (G1 90.5%, G3 literal fire 84.6%, G3 scoped
  50%); sửa vài ví dụ không đổi verdict.
- Dùng "45 proposals" cũ làm mẫu số shadow: KHÔNG — đếm lại từ
  trace (29 write / 16 monitored calls / 19 monitored args).

## 6. Residual & giới hạn (không ép PROVEN)

- Patch-verified exclusion (§1.3): cancel/update thành công đã
  lookup entity nhưng vẫn bị coi là echo khi id bằng đối số —
  false block tiềm ẩn trên chuỗi cancel/update → reference sau.
- Entity-choice ambiguity: G2 kiểm tra existence, prover kiểm tra
  derivation — không cái nào kiểm tra "user đã xác định DUY NHẤT
  entity nào" cho `*_id` (tương tự G1 cho contact nhưng tổng quát
  hơn). 3 ca passed ở shadow (email/book) thuộc đúng lỗ hổng này:
  entity tồn tại nhưng request không disambiguate. Hướng tương
  lai: ambiguity gate cho entity choice, hoặc grammar bắt slot
  định danh phải đến từ request.
- Biên monitored slot: threshold_kwh, channel, free-text body và
  các ask-param đặc thù tool chưa được monitor — 7 ca out-of-scope
  ở shadow là bằng chứng. Mở rộng monitored set cần định nghĩa
  từng tool, không làm ẩu bằng cách monitor mọi arg.
- Thứ tự adapter (ngoài scope round này, §1.5): validate schema
  trước rồi mới ground; adapter hiện ground trước validate và
  viết lại cả arg ngoài schema. Follow-up cho Codex/integration.
- Fuzzy 88/8 vẫn chưa validate trên ASR nhiễu (gold queries sạch
  không calibrate được) — không đổi từ Round 1.
- Giới hạn shadow: trace ask-only (không có gold write để đo
  precision/recall theo value); chỉ 20 mẫu chẩn đoán, không phải
  benchmark; 2 arms nhưng cùng guard (không so sánh arm); 3
  proposal unexecuted không rõ lý do trong trace (guard chặn 2/3,
  1 out-of-scope — trùng khớp định tính, không suy ra nhân quả).
- Gold anomaly train_1696 chat_6142 vẫn giữ trong audit (không
  drop mẫu để đẹp số).
- Sửa nguồn nghiên cứu (Round 1 §9, đã sửa trực tiếp trong file):
  TIMEX3/TimeML có DATE, TIME, DURATION, SET — không có DATETIME
  riêng; phân loại date/time/datetime là nội bộ, lấy cảm hứng từ
  temporal typing. Paper deterministic gates (arXiv:2607.07405)
  chỉ hỗ trợ cơ chế (gate đọc state trước mutating call, không
  model, không ground truth), KHÔNG phải bằng chứng G2 đúng hay
  đạt precision nào; G2 không dùng khả năng đọc state của harness
  khác để truy cập state ẩn LifeMate — chỉ dùng observation log +
  roster agent đã tự quan sát.

## 7. Readiness từng module

- Prover (lifemate_provenance.py): SHADOW-READY + đã shadow trên
  trace model thật (ask-samples: 0 false proof trên 19 monitored
  args). Chưa hard-enforce: chưa có trace với gold write để đo
  blocking precision trên proposal đúng (cần trace benchmark,
  không phải diagnostic ask-only).
- Gate 2 (lifemate_gates.py, v2 structured): SHADOW-READY, KEEP ở
  99.6% gold precision; trên trace: chặn đúng 2 id bịa, pass đúng
  các reference đã established. Chưa hard-enforce (cùng lý do).
- Gate 1, Gate 3 (literal + scoped): DROP / experimental — không
  bật, không dùng kết quả của chúng để chặn.
- AskBudget: chỉ unit-tested, chưa có model run.
- Tích hợp vào pipeline: cần phê duyệt riêng (không tự ý wire).

## 8. File thay đổi (so với e00c864c)

- `lifemate/lifemate_provenance.py` — bỏ clause contact_name khỏi
  `_roster_intent` (intent chỉ từ user text).
- `lifemate/lifemate_gates.py` — PriorCall `result_entries`, G2 v2
  structured (contacts-app, field-typed ids, read-verify /
  write-non-echo, bỏ app-family sau bằng chứng shared registry).
- `tests/test_lifemate_provenance.py` — test proposal contact_name
  không phải intent.
- `tests/test_lifemate_gates.py` — TestGate2 viết lại theo
  result_entries + 4 test mới (flat-string, read-lookup/noop,
  write-non-echo/patch-echo, shared-registry/message-history).
- `analysis/repro_codex_counterexamples.py` — sửa fixture H4/H5,
  thêm H5b, F5–F9 (23 ca).
- `analysis/gates_precision_audit.py` — PriorCall entries, flatten
  entries, old-vs-new so với module e00c864c.
- `analysis/downgrade_adjudication.py` (mới) — phân loại 72
  downgrades 355→284.
- `analysis/model_trace_shadow.py` (mới) — shadow trên trace E5
  V13 với causal prefix.
- `research/lifemate/round10-fix-report.md` — đính chính claim
  17/17 (3 chỗ) + §9 (TIMEX3 taxonomy, gates paper scope).
- `research/lifemate/round10-fix-report-round2.md` (mới) — báo cáo
  này.
- Không đổi: `analysis/e7_dag_shadow_audit.py` (re-run cho số
  identical), `research/lifemate/round10-measurement-report.md`,
  mọi file inference/simulator/scorer/config. Không data/audio/
  weights/raw evidence nào được push (trace JSON đã có sẵn trên
  nhánh từ trước, không phải file mới push trong round này).
