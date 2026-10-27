# E1 V10 Intent/Planning Analysis + E6 Proposal — đọc từ main b87bf9a

Nguồn: `E1_V10_AUDIT_2026-10-28.md`, `e1_v10_diagnostic_trace.json`,
`e1_v10_verified_comparison.json` (main b87bf9a), đối chiếu
`E1_DEPLOYMENT_BRIEF_2026-10-28.md` (tiêu chí đăng ký trước),
`E1_PREREQUISITE_CHECKLIST_2026-10-28.md` (21 quan hệ, frozen tại
main 71ad9334d) và ledger v6/v7. Chỉ phân tích + đề xuất — KHÔNG sửa
inference, KHÔNG chạy GPU, KHÔNG hardcode probe (mọi rule/ví dụ dưới
đây đều tổng quát, không chứa ID/amount của mẫu dev nào).

## 0. Verdict E1, đọc đúng phạm vi đã đăng ký

- **Format-scope: PARTIAL CONFIRMATION, không phải full.** Text arm
  tái tạo v7 đúng 8/8 submissions và raw generations (baseline đáng
  tin; V9 bị loại vì adapter đưa sai transcript — ghi nhận phương
  pháp, không phải kết quả). Native: 11 tagged tool calls, tất cả
  parse được, 0 multi-block, simulator validation rejections 3 → 0.
  Riêng 0003 chứng minh phần hẹp của giả thuyết: ask bẹt 3 lần ở text
  arm thành nested ask được chấp nhận ở native arm.
- **"Format-clean" là nói quá.** Native có 4 plain-text stops, trong
  đó 1 cái mang hình thức của một call (xem §2, 0116). Diagnostics
  của native vẫn đánh dấu plain-text stop là `format_valid: true` —
  đó là một lỗ đo, không phải một thành công.
- **Score mean 0.125 → 0.1875 KHÔNG phải một task mới được giải.**
  Toàn bộ +0.0625 đến từ 0004 (0 → 0.5): native bỏ optional arg
  `power` và bỏ write trùng; cả hai arm đều đã đạt đúng final device
  state từ trước. Đây là call-sequence cleanup, không phải outcome
  mới. Không mẫu nào khác đạt thêm full credit ở arm nào.
- **Prerequisite: 5/21 (text) → 4/21 (native) — GIẢM, không tăng.**
  Native làm 0016 tệ hơn (tạo reminder task mà text arm không chạy).
  Vì vậy không được mô tả native là "tốt hơn về planning" dưới bất kỳ
  hình thức nào. Native giữ ở dạng opt-in, không promote thành
  baseline — đúng như audit kết luận.
- **Attribution giới hạn:** contract changes đi theo bundle (schemas,
  roles, parser, EOS) nên V10 không tách được phần nào gây ra hiệu
  ứng. Đề xuất E6-C dưới đây cũng là một arm attribution cho riêng
  phần parser.

## 1. Lỗi intent/planning còn lại — theo mẫu, native arm

| Mẫu | Native làm gì (trace) | Lỗi thuộc tầng nào | Prerequisite |
|---|---|---|---|
| 0019 | Stop, 0 calls | Không lỗi — regression guard giữ được | 1/1 cả hai arm |
| 0116 | Tagged call `phone.call{cont_01}` (ID bịa, bị grounding chặn, không chạy) → text `sys.ask_missing_info("phone.call", ["contact_id"])` → stop sạch, 0 submitted calls, hash true (vô nghĩa: không đổi state), F1 0 | Intent (nhắc vs gọi) + channel (pseudo-call) — xem §2 | 0/1 cả hai arm |
| 0025 | Stop ngay, 0 calls, trên cached ASR garbled | ASR-blocked (E3), không phải planning — E0 với gold-current đã mở được 6 calls (F1 0.5455), nên đây là nút ASR, không phải nút intent | 1/4 cả hai arm (chỉ R25.4 no-call, pass vacuously vì không làm gì) |
| 0003 | 1 generation duy nhất: nested ask `{ewallet.transfer, [contact_id, phone, amount]}` → ask chạy, kết thúc turn, 0 read | Ask-as-escape: hỏi thay cho đọc. Format đã sửa nhưng prerequisite vẫn 0 | 0/3 cả hai arm |
| 0008 | `alarm.update{alm_02, 07:30, label: "họp sớm (nếu mưa)", enabled: true}` rồi stop; không forecast ở arm nào | Condition-before-write + label-condition fallacy (viết điều kiện vào label như thể write đã thành conditional) | 1/3 cả hai arm (chỉ R08.3 pass: không dùng get_current như E0) |
| 0016 | `get_current{TP.HCM}` + `reminders.create` (content echo lại ASR garbled, time bịa, repeat daily) | Task-type confusion (calendar → reminder) + ASR echo + bịa time/repeat. Native TỆ HƠN text arm (text stop 0 calls) | Text 1/4 → native 0/4 (R16.4 fail vì tạo reminder) |
| 0049 | `get_balance{}` + `list_beneficiaries{}` + `list_transactions{acc_01}` + `open_savings{acc_01, 100000, 12}`; không list_bills, không transfer | Thiếu transfer + fallback đảo ngược (mở savings TỪ tài khoản thanh toán thay vì chuyển TỪ tiết kiệm). F1 0.5 (2 reads khớp gold) nhưng score 0 vì hash sai — reads tốt hơn, task vẫn sai | 0/4 cả hai arm (R49.2/R49.3 ở native là NOT_EXECUTED: read có chạy nhưng transfer mà chúng là prerequisite cho thì không tồn tại) |
| 0004 | Minimal write, không power, không trùng | Không lỗi intent — cải thiện sequence | 1/1 cả hai arm |

## 2. 0116 — phân rã ba lớp, và vì sao pseudo-call không phải là ask

Trace native của 0116 có đúng 2 generations (đọc nguyên văn từ trace
JSON, không suy diễn):

1. `<tool_call>{"name": "phone.call", "arguments": {"contact_id": "cont_01"}}</tool_call>`
   — tagged call hợp lệ về format, nhưng `cont_01` là ID bịa (ID thật
   có dạng `c_01`); nó được grounding chặn trước khi chạy nên không
   có submitted call nào, và cũng không có simulator validation
   rejection nào được log (grounding rejection đi đường retry, không
   phải đường simulator).
2. `sys.ask_missing_info("phone.call", ["contact_id"])` — plain text,
   `blocks: 0`, `stop_kind: "plain_text"`, `format_valid: true` theo
   diagnostics. Parser native chấp nhận nó như một clean stop. Trace
   kết thúc với submission 0 calls.

Ba lớp lỗi, không được gộp:

- **Lớp intent (E5):** cả hai arm đều nhầm "nhắc gọi điện cho mẹ"
  thành gọi ngay (text arm hỏi `phone.call/contact_id`; native arm
  gọi `phone.call`). Gold muốn `reminders.create/time`. Đây là lỗi
  phân biệt nhắc–gọi, không phải lỗi format.
- **Lớp grounding (đã hoạt động):** ID bịa bị chặn. Đừng tính đây là
  lỗi cần sửa bằng contract hay prompt — nó là bằng chứng grounding
  làm đúng việc.
- **Lớp channel (mới, do native contract tạo ra):** sau khi call bị
  chặn, model "hỏi" bằng cú pháp gọi hàm dạng văn bản thay vì bằng
  một tagged ask call. Nó BIẾT mình cần hỏi (nội dung pseudo-call
  chính là ask target theo intent sai của nó), nhưng không dùng đúng
  channel. Parser coi đó là stop sạch nên không có ask nào được
  submit, không có retry nào xảy ra, và diagnostics còn đánh dấu
  `format_valid: true`. **Kết luận đo lường: bất kỳ báo cáo nào viết
  "native 0116 đã ask" đều sai — submission có 0 calls, F1 0, và hash
  true chỉ vì không đổi state (ask cũng không đổi state, nên hash
  không phân biệt được "đã ask" với "không làm gì").**

Hệ quả cho thứ tự thí nghiệm: đo intent của 0116 (E5) trong khi
pseudo-call vẫn được tính là clean stop sẽ làm nhiễu phép đo — ta
không phân biệt được "model định hỏi sai target" với "model định hỏi
đúng nhưng rớt channel". Vì vậy channel fix (E6-C) phải đi TRƯỚC E5,
không phải sau.

## 3. Năm pattern intent/planning còn lại (xếp theo khối lượng mẫu)

1. **Act/ask-before-evidence (0003, 0008, 0016, 0049 — 4 mẫu, nặng
   nhất).** Model viết/hỏi/mở savings trước khi đọc cái mà action đó
   cần: 0003 hỏi thay cho list_bills + search; 0008 update trước
   forecast; 0016 tạo reminder mà không forecast/list; 0049 mở
   savings mà không list_bills/transfer. Policy rule 4 ("read a
   bill/balance/event when the request refers to its value") và rule
   2 ("evaluate conditions BEFORE dependent writes") đã nói đúng mà
   model vẫn vi phạm — đây là lỗi áp dụng rule, không phải thiếu
   rule. E2 chỉ bao phủ phân tập conditional (0008, 0016-branch);
   không bao phủ 0003/0049.
2. **Condition-into-label (0008).** Viết "(nếu mưa)" vào label rồi coi
   như write đã thành conditional. Policy rule 5 đã cấm rõ ("A
   condition written into a label does not make an immediate write
   conditional") mà model vẫn làm ở native arm.
3. **Task-type confusion (0016).** Reschedule calendar → tạo +
   (ở E0) hoàn thành reminder; ở native E1 còn echo ASR garbled vào
   content reminder và bịa time/repeat. Đây là nhầm loại task, không
   phải thiếu read.
4. **Entity-pick vs ask (0025, 0116).** 0025 ở E0 chọn bừa một Minh;
   0116 ở cả hai arm E1 đều đi về hướng phone.call thay vì hỏi
   reminders/time. 0025 trên cached ASR thì bị chặn ở tầng ASR trước
   cả khi tới được quyết định này.
5. **ASR-blocked stop (0025).** Cả hai arm stop 0 calls trên cached
   ASR garbled. Không thuộc E2/E5 — thuộc E3 (và E0 đã chứng minh
   gold-current mở được task này).

## 4. Đối chiếu E2/E5 — vì sao chưa chạy chúng ngay

- **E2 (ví dụ condition-before-write):** bao phủ đúng 0008 và nhánh
  conditional của 0016/0025. Nhưng 0025 đang ASR-blocked nên E2 không
  đo được gì trên nó với cached ASR; và E2 không chạm tới 0003/0049
  (không có điều kiện, chỉ có read-before-write). E2 vẫn có giá trị,
  nhưng nó là thí nghiệm hẹp hơn pattern số 1.
- **E5 (quy tắc nhắc–gọi):** bao phủ đúng lớp intent của 0116. Nhưng
  như §2, nếu chạy E5 trước khi sửa channel thì phép đo bị nhiễu:
  model có thể "định hỏi đúng" nhưng vẫn rớt thành pseudo-call text
  và được tính là stop sạch — ta sẽ kết luận sai là rule không có
  tác dụng. E5 nên chạy SAU E6-C.
- **Kết luận thứ tự:** pattern số 1 (act/ask-before-evidence, 4 mẫu)
  lớn hơn cả E2 và E5 cộng lại về số mẫu, và nó bao hàm E2 như một
  trường hợp riêng (forecast là một read). Vì vậy thí nghiệm tiếp
  theo nên là evidence-first tổng quát (E6-B), kèm arm channel fix
  (E6-C) để gỡ nút 0116 trước E5.

## 5. Đề xuất E6 — một thí nghiệm, ba arm, mỗi arm một biến duy nhất

Tên: **E6 — Evidence-first prompt rule + pseudo-call boundary.**
Base chung cho cả ba arm: native contract V10 (opt-in) nguyên vẹn,
cùng 8 mẫu, cùng cached ASR v7, cùng model/revision/seed/config như
V10 (grounding BẬT, max_steps 12, max_repeats 2, scorer proxy).
Không model mới, không held-out, không training, không merge main.

### Arm A — Control (native V10 as-is)

Không đổi prompt, không đổi parser. Kỳ vọng: tái tạo đúng kết quả
native V10 (proxy 0.1875, prerequisite 4/21, 1 pseudo-call). Nếu drift
lớn thì baseline không đáng tin và phải báo trước khi kết luận về
B/C. (V10 đã chứng minh text arm tái tạo v7 8/8, nên drift lớn ở đây
sẽ là tín hiệu lạ cần điều tra, không phải nhiễu thường.)

### Arm B — Evidence-first prompt rule ONLY (parser giữ nguyên V10)

Thêm đúng MỘT rule + MỘT ví dụ tổng quát vào system message (không
sửa rules 1–6, không sửa grounding/guard/scorer). Rule (diễn đạt
tổng quát, không chứa dữ liệu probe):

> Before any write or ask, list each value the action needs and check
> it against an observation you already have. If a value can be
> supplied by a read in the catalog, do that read first; never ask
> for a value you have not tried to read, and never write with a
> value you have not observed or derived from the request. Ask only
> for values no catalog read can supply.

Ví dụ tổng quát kèm theo (SYNTHETIC — scenario bịa, không thuộc
catalog LifeMate, không dùng tool/ID/amount của mẫu nào):

> Example (not a real request): to reserve a book, first check the
> catalog for its availability and shelf code; only if the catalog
> has no record of the book do you ask the user for the code. Do not
> reserve with a guessed code, and do not ask for a code the catalog
> can show you.

Arm B được kỳ vọng tác động pattern số 1 (0003, 0008-read-part,
0016, 0049), KHÔNG được kỳ vọng sửa 0116-intent (thuộc E5), 0025
(ASR-blocked), hay 0004 (đã tốt). Nếu B chỉ cải thiện 0008 mà không
cải thiện 0003/0049 thì đó là bằng chứng rule tổng quát chưa đủ mạnh
cho read-before-write phi điều kiện — và E2 hẹp vẫn còn nguyên giá
trị sau đó.

### Arm C — Pseudo-call boundary parser ONLY (prompt giữ nguyên V10)

Đổi đúng một luật parser: plain-text output khớp pattern call-like
dạng hàm — ví dụ `name(...)` với tên dạng `app.tool` (như
`sys.ask_missing_info("phone.call", ["contact_id"])`) — KHÔNG còn
được tính là clean stop mà đi đường validation_rejected + retry
(tối đa 3 attempts/step như các format error khác). Luật này HẸP
một cách có chủ đích:

- Chỉ khớp cú pháp gọi hàm (`^[a-z_][a-z0-9_]*\.[a-z_][a-z0-9_]*\s*\(`),
  không khớp prose tự do ("Tôi sẽ hỏi bạn…") — prose thật vẫn là
  stop sạch.
- Bare JSON có `"name"` đã là format error từ M6(b) của E1 brief, giữ
  nguyên, không đổi.
- Sau 3 attempts vẫn pseudo-call thì trace kết thúc as-is và được
  đếm là FORMAT FAILURE, không phải clean stop. Đây là điểm mấu chốt
  của arm: biến một silent stop thành một failure có thể đo được.

Arm C được kỳ vọng tác động duy nhất 0116 (và bất kỳ mẫu nào khác
rớt channel tương tự). Nó KHÔNG được kỳ vọng sửa intent: nếu sau
retry model vẫn hỏi sai target (phone.call thay vì reminders.create)
thì đó là bằng chứng lớp intent còn nguyên và E5 vẫn cần — nhưng
lúc đó ta đo được intent một cách sạch (vì ask đã thực sự được
submit hoặc fail một cách tường minh).

### Metric và tiêu chí kết luận (đăng ký trước)

- Đo sáu tầng như E1 (format, tool choice, arguments/ask target,
  prerequisite theo checklist 21 quan hệ, termination, outcome) +
  thêm metric riêng `pseudo_call_count` (không gộp vào format_valid).
- **B CONFIRMED (phạm vi evidence-first)** nếu prerequisite PASS
  tăng trên 0003/0049/0016/0008 mà không phá 0019 (vẫn 0 calls) và
  0004 (vẫn minimal write). **B PARTIAL** nếu chỉ tăng ở mẫu
  conditional (0008) mà không tăng ở 0003/0049 → rule tổng quát chưa
  đủ, E2 hẹp vẫn cần. **B REFUTED** nếu prerequisite không đổi trên
  cả 4 mẫu → rule dạng text không điều khiển được hành vi đọc-trước
  của model, cần cơ chế khác (không phải thêm chữ).
- **C CONFIRMED (phạm vi channel)** nếu pseudo-call của 0116 chuyển
  thành tagged call được submit (dù đúng hay sai target) HOẶC thành
  format failure tường minh sau retry — tức là không còn silent
  clean stop nào mang hình thức call. **C REFUTED** nếu model vẫn
  dừng sạch sau khi retry (parser không bắt được pattern) hoặc nếu
  luật mới phá stop sạch chính đáng (0019 bị ép thành call, hoặc
  prose thật bị tính là format error) — trường hợp sau là REGRESSION
  và arm phải dừng, không được "sửa" bằng cách nới pattern trong
  cùng run.
- **0025 là negative control:** trên cached ASR garbled, cả ba arm
  đều được kỳ vọng vẫn stop 0 calls. Nếu arm nào "sửa" được 0025 thì
  phải nghi ngờ rule/example đang dạy hành vi theo mẫu (leak) chứ
  không phải cải thiện thật — kiểm tra lại prompt bằng grep probe
  data trước khi tin.
- **Caveat vacuous-PASS (đọc kỹ khi chấm):** các quan hệ NO- (R25.4,
  R16.4, R08.3, R49.4) PASS một cách vacuous khi submission rỗng
  (0025 text/native đều 1/4 chỉ nhờ R25.4). Vì vậy KHÔNG được kết
  luận từ tổng điểm 21 quan hệ một mình — phải đọc kèm secondary
  annotation (PASS vs NOT_EXECUTED vs FAIL) và chỉ tính positive
  relations (read-trước-write có write đi kèm) là bằng chứng cải
  thiện thật.
- **Không kết luận thống kê, không khái quát ngoài 8 mẫu, không
  promote baseline từ E6 một mình.** Native vẫn opt-in cho tới khi
  có thêm bằng chứng.

### Kiểm tra CPU trước GPU (gate, như E1)

- **P1 — Parser-pattern unit test (synthetic):** chuỗi pseudo-call
  dạng hàm → reject; prose thật → stop; stop kiểu 0019 → stop;
  bare JSON có name → reject (đã có từ E1, giữ regression).
- **P2 — Prompt hygiene test:** grep toàn bộ prompt mới của Arm B
  (rule + example) để đảm bảo không chứa ID/amount/tool-name của 8
  mẫu (đặc biệt không chứa tên tool LifeMate thật trong ví dụ —
  ví dụ dùng scenario ngoài catalog).
- **P3 — Budget test:** prompt Arm B (thêm rule + example) đo bằng
  tokenizer rev cdbee75 + 512 reserve ≤ 16384 cho 8 mẫu, first-turn
  và bound worst-case.
- **P4 — Loop test (text-level fake):** fake trả pseudo-call →
  retry → tagged call; fake trả prose → stop; fake trả stop kiểu
  0019 → stop.
- GPU chỉ chạy khi P1–P4 pass. Một run GPU với CPU test fail là run
  không hợp lệ.

### Sau E6 (thứ tự đã rõ, không chạy trước)

1. Nếu C confirmed → chạy E5 (nhắc–gọi) trên nền parser đã sửa, đo
   intent sạch.
2. Nếu B partial (chỉ conditional cải thiện) → chạy E2 hẹp.
3. Nếu B refuted → dừng hướng "thêm rule text", cân nhắc cơ chế
   khác (ví dụ chặn write/ask khi prerequisite read chưa có — nhưng
   đó là thiết kế mới, cần brief riêng, không làm trong E6).
4. 0025 vẫn thuộc E3 (ASR), không thuộc E2/E5/E6.
5. E4 (guard) vẫn đợi sau cùng như brief E0–E5 đã định.

## 6. Giới hạn của phân tích này

- 8 mẫu hand-picked, không thống kê; mọi kết luận gắn với ID mẫu và
  event cụ thể, không khái quát.
- Contract V10 là bundle nên hiệu ứng parser-only (C) cũng là một
  phần attribution cho V10 — nhưng C không tách được schemas vs
  roles; B-roles/B-tools từ E1 brief vẫn còn mở nếu cần.
- Checklist prerequisite có vacuous-PASS ở quan hệ NO- (xem §5);
  đọc tổng điểm mà không đọc secondary sẽ kết luận sai.
- Không có evaluator chính thức; mọi score đều là engineering proxy,
  hash-gated, và 0049 cho thấy F1 có thể tăng trong khi score vẫn 0.
