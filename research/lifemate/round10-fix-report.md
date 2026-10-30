# Round 10 Fix Report: Provenance & Gates — Codex Counterexamples A–H

Branch: `round10-provenance-gates-fixes` (từ main, base commit
`219d7fec377ee4a94534b10baa041d4102cf15e1` — "Round 10: Provenance
DAG + deterministic gates"). Commit bàn giao cuối xem `git log` của
branch (ghi trong message bàn giao + MEMORY.md). Không merge vào main
trong đợt này; Codex đối chiếu bằng base + branch.

Phạm vi: chỉ `lifemate/lifemate_provenance.py`,
`lifemate/lifemate_gates.py`, tests của hai module,
`analysis/repro_codex_counterexamples.py`,
`analysis/e7_dag_shadow_audit.py`,
`analysis/gates_precision_audit.py`, và báo cáo này. Không sửa agent
inference, simulator, scorer, benchmark config; không chạy GPU/model,
không training, không dùng held-out.

## 0. Đặt tên đúng: rule engine, không phải DAG

Module vẫn được gọi là "Provenance DAG" từ Round 10, nhưng thực chất
nó là **typed-evidence rule engine trả về Verdict** (status + rule +
detail): không có node/edge được lưu, không có đồ thị invalidation.
Invalidation hiện tại là bằng thứ tự rule (supersede/cancel) và bằng
chứng minh lại đệ quy (recursive re-proof) cho offset/duration, không
phải lan truyền trên đồ thị. Báo cáo này dùng tên "prover" / "rule
engine". Nếu muốn gọi là DAG thật, cần lưu parent/derivation cho mỗi
verdict và cơ chế invalidate khi parent bị supersede — đó là việc
chưa làm, ghi ở §7.

## 1. Từng lỗi: trước / sau

Mỗi ca có input synthetic tối thiểu trong
`analysis/repro_codex_counterexamples.py` (17/17 PASS tại thời điểm
báo cáo này; ĐÍNH CHÍNH Round 2: con số này đã stale — sau khi
`_call_entry_succeeded` được siết (2-tuple = unknown, không phải
evidence), ca H5 fail vì fixture của nó dùng 2-tuple; xem báo cáo
Round 2, script hiện tại là 23/23).
"Trước" = code 219d7fec; "sau" = code branch này.

### A. Substring số — CONFIRMED, FIXED
- Input: text "chuyển 1500000 cho Minh", proposal amount=500000.
- Trước: PROVEN/verbatim (khớp chuỗi con "500000" trong "1500000").
- Nguyên nhân: verbatim so sánh chuỗi, không biên span.
- Sau: UNPROVEN/none. Verbatim chỉ còn cho string; số chỉ qua
  number spans (whole-span + đúng đơn vị).

### A2. Số điện thoại thành amount — CONFIRMED, FIXED
- Input: "gọi cho Minh số 0914061230 nhé", amount=914061230.
- Trước: PROVEN/verbatim (và cả span path nếu verbatim bị chặn).
- Sau: UNPROVEN/none. Digit-form regex bỏ qua digit run 9–11 chữ số
  bắt đầu bằng 0 không có đơn vị; word-run bỏ qua run chỉ có 1 token
  thuần digit (để filter của digit-form không bị word-run hồi sinh).

### A3. Chữ số trong identifier thành amount — CONFIRMED, FIXED
- Input: "mã đơn c_9526 giao rồi", amount=9526.
- Trước: PROVEN/verbatim (và span path: tokenizer tách "c_9526"
  thành "c" + "9526").
- Sau: UNPROVEN/none. Digit regex thêm left boundary
  `(?<![A-Za-z0-9_])` (số trong `c_9526`, `evt_02` không match);
  word-run single-digit skip như A2.

### A4. Substring id — CONFIRMED, FIXED
- Input: "nhắn cho c_100 nhé" + roster có c_10 "Minh",
  proposal contact_id=c_10.
- Trước: PROVEN/verbatim ("c_10" là chuỗi con của "c_100"; roster
  rule cũng fire vì chỉ kiểm tra tồn tại).
- Sau: UNPROVEN/roster_no_intent. Roster giờ cần intent mention
  độc quyền theo token (xem §2); "c_100" không phải mention của c_10.

### B. Date-only thành datetime 00:00 — CONFIRMED, FIXED
- Input: "Nhắc tôi sáng mai uống thuốc", proposal time = ngày mai
  00:00.
- Trước: PROVEN/relative_date (date-only span + exception cho phép
  midnight).
- Nguyên nhân: `_value_matches_datetime` có exception biến date-only
  thành 00:00.
- Sau: UNPROVEN/none. Typed dispatch: DATE gold so date part;
  TIME gold so time part; DATETIME gold cần cả hai; date-only span
  KHÔNG BAO GIỜ chứng minh datetime gold (exception đã xóa).
  Ngược lại, datetime span chứng minh date gold bằng date part
  (mới, hợp lệ).

### C. Giờ của việc khác trong history — CONFIRMED, FIXED
- Input: current "nhắc tôi lại ngày mai nhé" + history "đi công
  viên lúc 15 giờ hôm qua", proposal time = ngày mai 15:00.
- Trước: PROVEN/datetime_assembly (ghép date từ current + time từ
  history qua linker "lại").
- Sau: UNPROVEN/none. Mệnh đề linker "lại"/history-phrase đã xóa.
  Assembly giờ chỉ: (a) cùng current text, đúng 1 date span + 1
  time span khớp gold (forced unique pairing; text nhiều date/time
  không assemble), hoặc (b) một phía từ current text (unique) +
  phía còn lại từ primary time field (start, rồi time) của
  observation event có id-link. History text không tham gia assembly.

### D. Số dư banking chứng minh amount — CONFIRMED, FIXED
- Input: history observation ("banking.get_balance", 500000) dạng
  tuple cũ, proposal banking.transfer amount=500000.
- Trước: PROVEN/observation (cùng app + cùng scalar, bất chấp field).
- Sau: UNPROVEN/none. Observation giờ là quadruple
  (tool, field, value, entity): match cần cùng app family VÀ
  field == slot chính xác (balance không chứng minh amount) VÀ
  entity tương thích VÀ duy nhất. Tuple cũ (tool, scalar) → field
  unknown → không bao giờ chứng minh; scalar trần → app unknown →
  không bao giờ chứng minh. UNKNOWN source không mặc định same-app.

### E. Timestamp prior call không liên kết làm base offset — CONFIRMED, FIXED
- Input: prior_call_args [("alarm.create", {time 10:00})] + text
  "dời lịch họp mai muộn hơn nửa tiếng nhé", proposal
  calendar.update_event start=10:30, event_id evt_99 (không có event
  liên kết).
- Trước: PROVEN/offset (lấy base từ prior call bất kỳ).
- Sau: UNPROVEN/none. Prior-call base chỉ ở _depth==0, chỉ từ entry
  succeeded, chỉ khi entity-linked (ids ∩ write ids) HOẶC (write là
  create VÀ current text có đại từ "đó"), VÀ base phải tự được
  PROVEN bằng prove_argument đệ quy ở _depth+1 (ở depth ≥1 offset
  chỉ dùng event base → không có chuỗi guess, luôn dừng).

### F. Prior write args thành "contact established" — CONFIRMED, FIXED
- Input: G2 với prior_calls [("sms.send", {contact_id c_05})]
  (một WRITE trước), không roster/results.
- Trước: fired=False ("contact established") — argument của proposal
  trước được tính là bằng chứng.
- Sau: fired=True. G2 mới nhận `PriorCall` (tool, args, result_scalars,
  succeeded): argument không bao giờ tính; chỉ roster id/name hoặc
  string trong result của SUCCEEDED call mới tính.

### F2. Echo hazard — REFRAMED (không tái hiện đúng như Codex mô tả)
- Codex mô tả: contact id trong observation scalar được tính là
  established. Kiểm tra code cũ: nhánh contact của G2 cũ KHÔNG BAO
  GIỜ đọc prior_observations (chỉ roster ids + prior-call args),
  nên với input đúng như mô tả, G2 cũ cho fired=True (không tái
  hiện). Hazard thật trong code cũ nằm ở nhánh *_id: nó CÓ đọc raw
  prior_observations, nên result của một write trước echo lại chính
  argument của nó (vd open_savings result savings.account_id == arg
  from_account_id) sẽ pass call sau.
- Sau (cả hai nhánh): result scalar nào bằng argument của chính call
  đó (theo NFC-lower) bị loại là ECHO, không chứng minh gì. Bằng
  chứng: repro F2 (PriorCall sms.send args c_05 + result_scalars
  [c_05] → fired) và F3 (read thành công + result không echo → pass).
- Hệ quả đo được trên gold (§4): 3 gold FP cũ của G2 (contact từ
  context: "mạ", "gọi lại Vy", "Emily Carter") giờ PASS — vì id/name
  của họ nằm trong result của read thành công trước đó (không phải
  echo). Đây là cải thiện thật, không phải nới lỏng để cứu verdict:
  nguồn evidence mới hẹp hơn về loại (succeeded + non-echo) nhưng
  đúng hơn về ngữ nghĩa (result của read được tính cho contact, điều
  code cũ bỏ sót).

### G. Early return sau contact hợp lệ — CONFIRMED ở code, FIXED
- Input: call có contact_id c_05 (established) + event_id evt_99
  (chưa established).
- Trước: fired=False (return sớm sau contact).
- Sau: fired=True, reason liệt kê đủ mọi reference thiếu.
- Giới hạn schema thật (đã verify bằng cách duyệt cả 147 tool spec):
  KHÔNG CÓ tool nào vừa có contact reference vừa có *_id khác, nên
  G hôm nay có impact 0 trên schema thật. Fix là defence in depth,
  và báo cáo ghi rõ giới hạn này thay vì thổi phồng.

### H4. Cancel không chặn history reference — CONFIRMED, FIXED
- Input: current "thôi khỏi chuyển số tiền cũ" + history transfer
  500000.
- Trước: PROVEN/history_reference (không xử lý cancel).
- Sau: UNPROVEN/none. Cancel marker bất kỳ đâu trong current text
  (hủy/huỷ/không cần/thôi khỏi/bỏ qua/đừng/thôi đừng/không chuyển
  nữa/hủy bỏ/huỷ bỏ) disable history_reference.

### H5. Reference trong segment đã bị sửa — CONFIRMED, FIXED
- Input: current "chuyển số tiền cũ à không 700000" + history 500000.
- Trước: PROVEN/history_reference (trigger phrase nằm trong segment
  đã bị sửa vẫn fire).
- Sau: SUPERSEDED/supersede. History_reference chỉ tìm trigger trong
  latest correction segment khi có correction marker; và supersede
  check giờ cũng nhận biết history reference (segment chứa phrase +
  unique history candidate == value) nên giá trị bị sửa đi được báo
  SUPERSEDED (lỗi đã chứng minh) thay vì UNPROVEN lặng lẽ.

### H9. Duration dùng start chưa chứng minh — CONFIRMED, FIXED
- Input: "dời lịch đi" + id-linked event evt_02 (15:00–16:00) +
  call_args start=15:30 (không chứng minh được) end=16:30.
- Trước: PROVEN/duration (lấy start từ call_args + duration event).
- Sau: UNPROVEN/none. Duration yêu cầu start của chính call được
  PROVEN bằng prove_argument đệ quy ở _depth+1 trước khi dùng
  start + event duration.

### H10. Giờ của entity khác — CONFIRMED, FIXED
- Input: history observation ("calendar.list_events",
  "2026-11-10T16:00:00+07:00") scalar phẳng + update_event cho
  evt_01 với start=16:00.
- Trước: PROVEN/observation (cùng app + scalar bằng nhau).
- Sau: UNPROVEN/none (quadruple mới: entity evt_02 ≠ evt_01; và
  history observation cho write có ids cần entity link).

## 2. Cơ chế đã sửa (tóm tắt kỹ thuật)

- **Span/unit typing**: số chỉ qua whole-span match với đúng đơn
  vị; verbatim chỉ cho string; phone (9–11 digit bắt đầu 0, không
  đơn vị) và digit trong identifier không bao giờ thành span.
- **Temporal typing**: DATE / TIME / DATETIME phân biệt ở cả parse
  lẫn compare; hour_missing không thành 00:00 hay giờ mặc định
  nếu schema/policy không khai báo.
- **History linkage**: history chỉ chứng minh khi đúng task/entity/
  slot, từ call succeeded (hoặc span trong history user text), không
  bị cancel/supersede; trigger phrase chỉ xét ở latest segment khi
  có correction.
- **Observation provenance**: quadruple (tool, field, value, entity);
  field phải == slot; entity phải tương thích (write có ids →
  obs entity None-hoặc-trong-ids; create → chỉ turn observation);
  >1 entity khác nhau → AMBIGUOUS; contact slot không đi qua
  observation (chỉ roster/history).
- **Roster intent**: roster chứng minh contact tồn tại; chọn đúng
  người cần exclusive mention (contact_name match, full-name phrase
  match với void khi phrase nằm trong full name dài hơn của entry
  khác tại cùng vị trí, hoặc single name token không entry nào khác
  chia sẻ). Không mention → UNPROVEN/roster_no_intent; duplicate
  name mention → AMBIGUOUS/roster_ambiguous.
- **Offset/duration parent**: chỉ parent hợp lệ, đúng entity, phép
  biến đổi được instruction cho phép; base phải tự PROVEN đệ quy
  (depth ≥1 chỉ event base); start bịa không phải parent PROVEN.
- **G2**: signature mới `(call, prior_calls: list[PriorCall], rosters)`;
  tham số `prior_observations` đã XÓA (mọi caller/test/audit phải
  migrate). Evidence = roster ids/names ∪ non-echo string scalars từ
  SUCCEEDED PriorCall. Legacy (tool, args) tuple → succeeded=False,
  không establish gì. Bare-mutate cần SUCCEEDED read cùng app family.
  G1/G3 literal/G3 scoped/AskBudget KHÔNG ĐỔI (verdict DROP giữ nguyên).

## 3. Lệnh tái lập

```bash
cd ~/workspace/zalo-aic-round3
# Repro 17 ca tại thời điểm báo cáo này (expect: 17/17 PASS, exit 0;
ĐÍNH CHÍNH Round 2: xem ghi chú ở §1 — script hiện tại là 23/23)
python3 analysis/repro_codex_counterexamples.py
# Unit tests, cả hai backend (expect: 112 tests OK mỗi backend)
python3 -m unittest discover -s tests
/tmp/rfvenv/bin/python -m unittest discover -s tests
# Shadow audit dev 1237 (expect: scope 479 writes / 556 args)
python3 analysis/e7_dag_shadow_audit.py \
  --train-jsonl ~/workspace/zaic-data/lifemate/extracted/train+public_test/train/train.jsonl \
  --data-root ~/workspace/zaic-data/lifemate/extracted/train+public_test \
  --split lifemate/splits/train_dev_heldout.json \
  --out-json /tmp/e7_dag_audit_NEW.json
# Gates audit (expect: G2 KEEP 99.9%, G1/G3 DROP)
python3 analysis/gates_precision_audit.py \
  --train-jsonl ~/workspace/zaic-data/lifemate/extracted/train+public_test/train/train.jsonl \
  --data-root ~/workspace/zaic-data/lifemate/extracted/train+public_test \
  --split lifemate/splits/train_dev_heldout.json \
  --out-json /tmp/gates_audit_NEW.json
```

## 4. Số liệu (tách riêng ba loại)

### 4.1 Gold audit — dev 1237, scope giữ nguyên 479 writes / 556 args

Scope định nghĩa không đổi so với Round 10. Audit script có 3 thay
đổi evidence đã ghi trong docstring của nó: structured quadruple
observations, tách turn/history evidence window, trajectory-faithful
replay (gold calls theo thứ tự, kể cả write) với succeeded flag thật
và per-write prefix window (Round 10 chỉ lấy reads trước write đầu
tiên của sample). Baseline là narrow rule set (verbatim + observation
+ roster) dưới semantics MỚI, nghiêm hơn — nên baseline_old vs
baseline_new tự nó là một finding, không phải regression.

| | Round 10 (cũ) | Fix round (mới) | Thay đổi |
|---|---|---|---|
| DAG PROVEN / 556 | 355 (63.8%) | 284 (51.1%) | −71 |
| Baseline PROVEN / 556 | 140 | 93 | −47 |
| Conversion (DAG − baseline) | 215 | 191 | −24 |
| Value args PROVEN / 448 | 248 | 195 | −53 |
| Value baseline PROVEN | 33 | 4 | −29 |
| Contact PROVEN / 108 | 107 | 89 | −18 |
| Contact baseline PROVEN | 107 | 89 | −18 |
| UNPROVEN | 201 | 262 | +61 |
| AMBIGUOUS | 0 | 10 | +10 |

Per-arg before/after (join theo (sample, tool, slot), giữ thứ tự):
PROVEN→PROVEN 283, PROVEN→UNPROVEN 64, PROVEN→AMBIGUOUS 8,
UNPROVEN→PROVEN 1, UNPROVEN→AMBIGUOUS 2, UNPROVEN→UNPROVEN 198.
Baseline: PROVEN→PROVEN 93, PROVEN→UNPROVEN 41, PROVEN→AMBIGUOUS 6.

Rule attribution (DAG PROVEN theo rule, cũ → mới):
roster 95→89, datetime_assembly 82→53, relative_date 43→37,
observation 43→4, number_words 25→23, number_digits 17→17,
offset 23→34, duration 24→24, supersede 3→3.
Chuyển rule đáng chú ý: assembly→none 28 (xóa cross-text assembly),
observation→none 14 (field/entity tightening), observation→offset 10
(không còn observation fire trước, offset chứng minh thay — tái
gán nhãn hợp lệ, không phải mất mát), roster→ambiguous 5,
roster→no_intent 5, observation→roster_no_intent 5 (contact trước
đây được observation scalar "chứng minh", giờ đúng là chưa chứng
minh), relative_date→none 5 (midnight typing), duration→none 4,
number_words→none 2.

Gain duy nhất UNPROVEN→PROVEN: train_0707 calendar.update_event
end — duration fire nhờ start được chứng minh đệ quy (cơ chế mới),
không phải nới lỏng.

Residual UNPROVEN 262: cross-app observation candidate 57 (không đổi
so với Round 10 — vẫn bị chặn theo thiết kế), no source 195,
contact in roster no intent 10. Contact: PROVEN 89 (roster),
AMBIGUOUS 6 (roster_ambiguous), UNPROVEN 13 (10 roster_no_intent +
3 none). Value: PROVEN 195, UNPROVEN 249 (192 none + 57 cross_app),
AMBIGUOUS 4.

Đọc đúng con số: DAG PROVEN GIẢM là kết quả đúng, không phải thụt
lùi — 71 ca PROVEN cũ là false-PROVEN theo các nguyên tắc §2 (đặc
biệt 39 ca observation và 28 ca assembly). Mục tiêu của đợt này là
100% entry được audit đúng, không phải 100% PROVEN. Conversion mới
191 vẫn nằm trong khoảng trung thực 159–215 của Round 10 (và trên
cận dưới loose-baseline), dù baseline mới nghiêm hơn nhiều.

### 4.2 Synthetic counterfactuals

- Repro script: 17/17 PASS tại thời điểm báo cáo này (A, A2, A3, A4,
  B, C, D, E, F, F2, F3 control, F4 control, G synthetic-schema, H4,
  H5, H9, H10) — ĐÍNH CHÍNH Round 2: con số này đã stale sau khi
  `_call_entry_succeeded` siết 2-tuple (H5 fail, fixture dùng
  2-tuple); script hiện tại là 23/23 (thêm H5b, F5–F9).
- Unit tests: 112 tests, PASS trên cả hai backend (difflib và
  RapidFuzz). Gồm 13 regression tests mới cho các ca A–H10 +
  roster duplicate ambiguous, và các test cũ đã sửa expectation theo
  contract mới (observation quadruple, assembly same-text-only,
  history succeeded flags, G2 PriorCall). Test cũ duy nhất bị lật
  expectation vì chính nó là bug F:
  `test_entity_id_needs_observation` (prior snooze args establish id).
- Cảnh báo theo mandate: tỷ lệ TP/(TP+FP) trên bộ synthetic tự thiết
  kế KHÔNG được gọi là precision triển khai thực tế. Precision duy
  nhất có ý nghĩa triển khai là audit trên gold (§4.1, §4.3).

### 4.3 Gates audit — dev 1237, Wilson 95%, ngưỡng KEEP ≥ 95%

| Gate | Gold applicable | Gold FP | Synthetic TP | Precision | Verdict |
|---|---|---|---|---|---|
| G1 contact ambiguity | 105 | 10 | 95 | 90.5% [83.4, 94.7] | DROP (không đổi) |
| G2 read-before-write | 971 | 1 | 971 | 99.9% [99.4, 100.0] | KEEP |
| G3 literal | 91 transfers | 77 fired (84.6%) | — | — | DROP (không đổi) |
| G3 scoped | 87 | 87 | 87 | 50.0% | DROP (không đổi) |

G2 old-vs-new (module Round 10 nạp trực tiếp từ base copy):
both-applicable 971, old_passed_new_fired 0, old_fired_new_passed 3.
Nghĩa là: việc siết evidence (bỏ prior args + echo) KHÔNG làm mất
pass gold nào, và sửa được 3 FP cũ (nhờ result của read thành công
được tính cho contact — xem F2). FP duy nhất còn lại là gold anomaly
đã biết: train_1696 chat_ott.send_message chat_6142 — write mà chính
gold trajectory cũng fail replay ("không tìm thấy chat_id"); nếu
loại anomaly này, G2 đạt 100% trên audit này. G2 giữ verdict KEEP
theo đúng luật re-audit (không khôi phục cách đếm cũ để cứu verdict).

### 4.4 Model-trace shadow — BLOCKED

Không có raw model proposal + evidence nào trong workspace để chạy
shadow chặn giá trị bịa. Những gì đã kiểm tra:
- `~/workspace/zaic-analysis/probe_gold_traces.json`,
  `trace_dump.txt`: trace GOLD, không phải proposal của model.
- `~/workspace/dev-probes-lifemate/`, `analysis/`: các báo cáo phân
  tích, không có raw proposal kèm evidence.
- 45 proposal V13 của Codex nằm phía Codex/Kaggle, không có trong
  workspace này.
Kết luận: BLOCKED (thiếu raw proposal/evidence). Không tự tạo dữ
liệu thay rồi tuyên bố đã xác minh. Khi Codex cung cấp trace model
(proposal + prefix evidence + kết quả), chạy prover lên đó và đo
blocking precision riêng — đó là bước bắt buộc trước hard-enforce.

## 5. Hướng đã thử nhưng loại

- **Any-app observation** (bỏ ràng buộc cùng app): loại — chính là
  bug D/H10; scalar bằng nhau không phải intent.
- **Linker-based assembly** ("lại", "như lần trước" ghép date/time
  xuyên text): loại — chính là bug C; chỉ unique pairing cùng text
  hoặc event có id-link mới được assemble.
- **Success-aware prior-arg evidence cho G2** (tính argument của
  write trước nếu write đó succeeded): loại — argument của write
  succeeded vẫn là đề xuất của model, không phải observation của
  state; sms/phone không validate contact nên echo của chúng không
  chứng minh gì. Chỉ result scalar non-echo của succeeded call mới
  tính.
- **Giữ 2-tuple history call = assumed succeeded** (contract cũ):
  loại — outcome unknown không phải evidence; audit đã có flag thật
  từ replay/recorded results nên không mất gì.
- **Bật lại G1/G3 sau vài fix**: không làm — verdict DROP của chúng
  đến từ gold behaviour (relation-disambiguation; request chính là
  authorization), không phải từ vài ví dụ lẻ. G1 relation-aware v2
  vẫn là hướng mở nhưng cần audit mới hoàn toàn, không phải patch.
- **Kiến trúc DAG thật (lưu graph + invalidation)**: chưa làm —
  vượt scope "sửa nhỏ và tổng quát nhất"; recursive re-proof đạt
  cùng tính chất cho offset/duration với chi phí thấp hơn. Ghi là
  việc tương lai ở §7, không khoác tên DAG cho rule engine hiện tại.

## 6. Residual / blocker (trung thực, chưa biến thành PROVEN)

- **Amount↔recipient binding trong multi-transfer text**: "chuyển
  500000 cho Minh và 700000 cho Lan" — spans chứng minh amount bất
  kể recipient. Cần argument-role binding (gán span cho đúng
  recipient) — chưa làm.
- **Bare 4-digit year thành amount**: mention năm ("năm 2026") có
  thể trùng số amount nhỏ — span filter chưa loại year-context.
- **Event supersession trong history**: observation event bị sửa/hủy
  ở turn sau trong history chưa bị invalidate (không có graph).
- **Fuzzy thresholds 88/8**: vẫn chưa validate trên ASR nhiễu (gold
  query sạch không calibrate được) — chờ dev ASR predictions từ
  Kaggle, như đã ghi từ Round 6.
- **E7 scope gốc (459/511, 31 ALLOW + 428 UNKNOWN)**: vẫn không tái
  hiện được (guard code của Codex không ở repo này). Mọi số "X
  trong 428" đều không được phát ngôn; conversion chỉ đo trên scope
  tái hiện 479/556.
- **Model-trace shadow**: BLOCKED (§4.4) — blocker chính trước
  hard-enforce.
- **Gold anomaly giữ lại, không loại âm thầm**: train_1696
  (chat_6142 không tồn tại khi replay) — G2 fire là đúng; anomaly
  được phân loại, không bị xóa khỏi audit.

## 7. Module readiness

- **Prover (rule engine) + G2**: SHADOW-READY — chạy shadow trên
  gold + synthetic đã xong, số liệu sạch, không false-PROVEN nào
  trong các nhóm lỗi đã biết còn tồn tại. CHƯA hard-enforce: cần
  blocking precision trên model trace thật (§4.4) trước khi veto
  proposal live.
- **G1, G3 literal, G3 scoped**: EXPERIMENTAL / DROP — không bật,
  không hard-enforce. G1 relation-aware v2 cần audit mới nếu muốn
  làm tiếp.
- **AskBudget**: unit-tested only, chưa có model run — như Round 10.
- **Việc tương lai (không thuộc đợt này)**: DAG thật với parent
  pointer + invalidation; argument-role binding cho multi-transfer;
  year-context filter cho amount spans; G1 relation-aware v2 với
  audit mới; model-trace shadow khi có trace từ Codex.

## 8. File thay đổi (so với base 219d7fec)

- `lifemate/lifemate_provenance.py` — span/unit typing, temporal
  typing, history linkage (cancel/supersede/succeeded), observation
  quadruple, roster intent, recursive offset/duration, docstring
  rule-engine honesty.
- `lifemate/lifemate_gates.py` — PriorCall, G2 viết lại (all
  references, succeeded non-echo results, không prior_observations
  parameter); G1/G3/AskBudget không đổi.
- `tests/test_lifemate_provenance.py` — cập nhật expectation theo
  contract mới + 13 regression tests A–H10.
- `tests/test_lifemate_gates.py` — TestGate2 viết lại cho PriorCall
  (gồm F, F2 echo, G all-references, bare-mutate succeeded read).
- `analysis/repro_codex_counterexamples.py` (mới) — 17 ca tối thiểu.
- `analysis/e7_dag_shadow_audit.py` — structured observations,
  split turn/history, trajectory replay + succeeded flags, per-write
  prefix, dag_detail/base_detail, residual buckets mới.
- `analysis/gates_precision_audit.py` — PriorCall G2, synthetic
  empty-evidence, old-vs-new effect count (nạp module Round 10 từ
  base copy khi có).
- `research/lifemate/round10-fix-report.md` (mới) — báo cáo này.

## 9. Ghi chú SOTA (nguồn chính, áp dụng có chọn lọc)

Các fix trên không thêm model call, thư viện hay kiến trúc lớn. Mỗi
fix là một nguyên tắc đã có nguồn, áp dụng vào prover CPU nhỏ:

- **Typed evidence, không phải label propagation**: CaMeL
  (Debenedetti et al., arXiv:2503.18813) chứng minh SOURCE LABEL,
  không chứng minh giá trị đúng — đúng giới hạn mà Round 9 đã rút
  ra. Fix D/H10 áp dụng đúng bài học đó: label "cùng app" không đủ,
  cần field + entity + typed equality (re-derivation) mới PROVEN.
  [SOURCE: CaMeL; INFERENCE: áp dụng field/entity typing vào
  observation rule.]
- **Temporal typing DATE/TIME/DATETIME (phân loại nội bộ)**: chuẩn
  TIMEX3/TimeML phân biệt DATE, TIME, DURATION, SET — KHÔNG có type
  DATETIME riêng (đính chính Round 2: bản Round 1 ghi \"phân biệt
  ba loại giá trị thời gian\" là gán sai taxonomy cho chuẩn). Phân
  loại date-only / time-only / datetime trong code là phân loại NỘI
  BỘ lấy cảm hứng từ temporal typing đó: prover phải phân biệt ba
  dạng giá trị gold, và việc gán date-only thành 00:00 là lỗi typing
  (underspecification: phần chưa biết phải để trống, không bịa —
  TIMEX3 dùng placeholder XXXX cho phần chưa biết). Fix B áp dụng
  đúng phân biệt này, không phát minh gì mới. [SOURCE: TimeML/
  TIMEX3 (DATE/TIME/DURATION/SET, underspecification); INFERENCE:
  dispatch theo kind của gold value + phân loại datetime nội bộ.]
- **Span-exact matching, không substring**: chuẩn trong extractive
  QA/NER — một span phải khớp toàn bộ biên mới là bằng chứng.
  Fix A/A2/A3 áp dụng biên span + filter phone/identifier.
  [INFERENCE từ thực hành chuẩn; không claim paper nào "chứng minh"
  cho LifeMate.]
- **Deterministic preconditions trên effect, không trên intent**:
  Reddy et al., "Reason Less, Verify More: Deterministic Gates"
  (arXiv:2607.07405) + ToolGuards (arXiv:2507.16459): gate đọc state
  vận hành trước khi mutating call chạy, không gọi model, không dùng
  ground truth — chỉ hỗ trợ CƠ CHẾ, không phải bằng chứng G2 của
  mình đúng hay đạt precision nào (precision của G2 chỉ có từ audit
  §4). Và G2 KHÔNG dùng khả năng đọc state riêng của harness khác
  để truy cập state ẩn trong LifeMate: mọi evidence của G2 đều là
  observation log + roster mà agent đã tự quan sát trong session.
  τ-bench (Yao et al. 2024) cho thấy bỏ policy làm pass^1 rơi mạnh
  (retail 61.2→56.8, airline 33.2→10.8); τ² cho thấy gate tiền-thực-
  thi rẻ, đo được per-gate precision (airline gpt-4o-mini
  29.6%→42.0%, +12.4pp) — và nguyên tắc "proposal không phải
  evidence" tương ứng với việc precondition phải đọc state/effect
  đã thành công, không đọc intent đã đề xuất. Fix F/F2/G2 áp dụng:
  succeeded + non-echo + all-references.
  [SOURCE: gates paper 2607.07405 (cơ chế) + τ-bench policy ablation
  + τ² gate measurement; INFERENCE: hợp đồng succeeded/non-echo
  cho G2.]
- **Không lấy benchmark của paper làm kết quả LifeMate**: mọi con số
  paper (τ² +12.4pp, PolicyGuard +12/+6/+12pp) đều là evidence
  frontier-model/harness khác, không transfer sang ≤6B offline —
  như Round 9 đã cảnh báo. Báo cáo này không trích số paper nào làm
  kết quả của mình; số duy nhất có giá trị là §4.
