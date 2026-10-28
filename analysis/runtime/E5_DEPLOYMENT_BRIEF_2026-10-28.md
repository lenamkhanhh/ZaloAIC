# E5 Deployment Brief — Nhắc–gọi disambiguation, chạy ngay sau E6-C

Trạng thái: READY, NHƯNG BỊ GATE BỞI E6-C. Tài liệu tự chứa: một người
chỉ đọc file này + code nhánh thí nghiệm là triển khai được, không
cần hỏi lại. Chỉ research/phân tích và thiết kế thí nghiệm — brief
này KHÔNG sửa code inference, KHÔNG chạy model/GPU, KHÔNG dùng
held-out, KHÔNG hardcode probe.

Nguồn: `EXPERIMENT_BRIEF_E0_E5_2026-10-28.md` (E5 gốc),
`E1_V10_INTENT_ANALYSIS_2026-10-28.md` (§2 0116 ba lớp, §5 thứ tự
E6-C trước E5), `E1_DEPLOYMENT_BRIEF_2026-10-28.md` (phương pháp đo
từng tầng + gate CPU). Scoring key dưới đây build từ gold bằng code
(chạy 2026-10-28, kiểm tra lại ở §6 G5) và được gắn nhãn diagnostic
— KHÔNG đưa scoring key, hay bất kỳ nội dung nào của file này, vào
input của agent dưới mọi hình thức.

## 0. Gate khởi động — đọc trước khi làm gì khác

- **E5 chỉ chạy sau khi E6-C CONFIRMED.** Lý do (từ phân tích V10):
  0116-native cho thấy pseudo-call dạng text được tính là clean stop,
  nên nếu đo intent khi channel còn hỏng thì không phân biệt được
  "model định hỏi sai target" với "model định hỏi đúng nhưng rớt
  channel". Nếu E6-C REFUTED (parser không bắt được pseudo-call,
  hoặc luật mới phá stop sạch chính đáng) thì E5 DỪNG — thiết kế lại
  channel trước, không chạy E5 để "lấy số tạm".
- **Base của E5 = native V10 + parser E6-C.** Cả hai arm đều dùng
  base này, để biến duy nhất giữa hai arm là rule disambiguation.
  E5 KHÔNG cộng thêm rule evidence-first của E6-B (dù E6-B có
  confirmed hay không) — cộng thêm là gộp hai biến, phá attribution.
- **E5 không block E2/E3:** E2 dùng mẫu 0008/0016/0025 (không trùng
  với 20 mẫu E5), E3 độc lập về ASR — hai thí nghiệm đó có thể chạy
  song song. E4 vẫn đợi sau cùng như brief E0–E5 đã định.

## 1. Giả thuyết, viết đúng phạm vi

**Giả thuyết:** model nhầm "nhắc + hành động" thành "làm hành động đó
ngay" vì nó không có quy tắc phân biệt hai cấu trúc này. Một rule
tường minh (nhắc → reminder, hỏi time; ngay/lập tức → action, hỏi
entity) sẽ sửa được lớp intent này trên các mẫu mang cue "nhắc".

**KHÔNG được kỳ vọng:** sửa lỗi ASR (cue "nhắc" bị ASR phá thì rule
không có gì để bám — đo riêng ở §4), sửa prerequisite reads, sửa
termination, sửa ask target cho các tool không liên quan tới nhắc
(13 mẫu control), hay sửa task-type confusion (0016 thuộc E2/E6-B,
không thuộc E5).

**Sửa chữa so với brief E0–E5 gốc:** ví dụ trong rule gốc ("nhắc tôi
gọi điện cho mẹ") gần như nguyên văn transcript của 0116 — đó là
dạng hardcode probe trá hình, brief này LOẠI BỎ và thay bằng ví dụ
synthetic (§2). Mọi ví dụ dưới đây đều dùng nhân vật/hành động bịa,
không xuất hiện trong 20 mẫu.

## 2. Rule thử nghiệm (Arm B) — nguyên văn, đặt đúng chỗ

**Vị trí:** thêm thành một block RIÊNG SAU ACTION_POLICY trong system
message, KHÔNG sửa rules 1–6 từng chữ (nguyên tắc như M3 của E1
brief: đổi format thì được, đổi nội dung rule thì không — ở đây rule
mới là block cộng thêm, không phải sửa rule cũ). Block này chỉ có ở
Arm B; Arm A không có nó.

**Nội dung block (tiếng Việt, giữ nguyên khi implement):**

> Quy tắc phân biệt nhắc–gọi: khi user nói "nhắc + <hành động>" thì
> đó là tạo reminder, không phải làm hành động đó ngay. CHỈ hỏi time
> khi time thực sự thiếu — tức không có giờ cụ thể nào trong request,
> history hay observation. Nếu user đã cho giờ cụ thể thì dùng giờ
> đó, không hỏi lại. Khi time thiếu thì hỏi reminders.create với
> params ["time"]. Chỉ khi user nói hành động ngay/lập tức thì mới
> là làm ngay — khi đó mới hỏi entity của action đó (ví dụ phone.call
> thì hỏi ["contact_id"], và cũng chỉ hỏi khi entity đó thiếu).
>
> Ví dụ tổng quát (không phải yêu cầu thật): "nhắc tôi chúc mừng
> sinh nhật Lan" → tạo reminder, thiếu giờ thì hỏi
> reminders.create/time. Ngược lại, "nhắc tôi gọi cho Lan lúc 9 giờ
> tối" → giờ đã có cụ thể nên tạo reminder với giờ đó, KHÔNG hỏi
> time. Và "gọi ngay cho Lan" → gọi ngay, thiếu liên hệ thì hỏi
> phone.call/contact_id. Một mốc thời gian mơ hồ (như "sáng mai")
> không phải là giờ cụ thể — vẫn tính là thiếu, vẫn phải hỏi time.

Ba điểm trong rule cần giữ khi implement, không được lược:

1. Phân biệt dựa trên CẤU TRÚC câu (nhắc vs ngay/lập tức), không dựa
   trên tên hành động (gọi, họp, uống thuốc đều có thể là reminder).
2. Target ask cho nhánh nhắc LUÔN là reminders.create/time (không
   phải tool của hành động được nhắc tới).
3. Hỏi time CÓ ĐIỀU KIỆN theo thiếu đủ: giờ cụ thể đã cho thì dùng,
   không hỏi lại; mốc thời gian mơ hồ (như "sáng mai") vẫn tính là
   thiếu nên vẫn phải hỏi — đây là lỗi E0 của 0116 (tự điền giờ khi
   thiếu) và của 0780-dạng (transcript có "sáng mai" nhưng gold vẫn
   hỏi time). Rule cũ viết "thiếu thường là time" dễ bị đọc thành
   "luôn hỏi time cho mọi reminder" — bản sửa này chặn cách đọc đó
   (điểm Codex nêu: chỉ hỏi time khi thiếu).

## 3. Mẫu và scoring key (build từ gold, diagnostic-only)

**Tập mẫu cố định:** 20 mẫu ask_only dev (định nghĩa: gold trace chỉ
gồm đúng 1 call ask; đã kiểm chứng cả 20 đều thuộc dev, không mẫu
nào held-out). 28 mẫu ask_only còn lại chỉ mở rộng khi rẻ — đợt
chạy đầu dùng đúng 20 mẫu này, không tự ý thêm/bớt.

**Tính chất đo được của tập mẫu (không phải giả định):** với kiểm tra
không phân biệt hoa thường, cue "nhắc" xuất hiện trong đúng 7 mẫu có
gold là reminders.create/time và KHÔNG xuất hiện trong 13 mẫu còn
lại. Tức là trigger của rule tách sạch target vs control trên tập
này — phần khó không nằm ở trigger mà nằm ở ACTION (hỏi đúng tool
hay nhầm sang tool của hành động). Nếu ASR làm mất cue ở một mẫu
target thì mẫu đó chuyển sang nhóm ASR-blocked (§4), không tính là
rule fail.

**Scoring key (tool_name + params của gold ask; KHÔNG đưa vào
prompt):**

| Mẫu | Gold ask tool_name | Gold params | Nhóm | Ghi chú đo |
|---|---|---|---|---|
| train_0116 | reminders.create | ["time"] | TARGET | Đã phân tích ở V10 (pseudo-call); subgroup gọi |
| train_0219 | reminders.create | ["time"] | TARGET | Subgroup họp |
| train_0220 | reminders.create | ["time"] | TARGET | Subgroup gọi |
| train_0287 | reminders.create | ["time"] | TARGET | Subgroup gọi |
| train_0353 | reminders.create | ["time"] | TARGET | Subgroup họp |
| train_0360 | reminders.create | ["time"] | TARGET | Subgroup gọi |
| train_0780 | reminders.create | ["time"] | TARGET | Subgroup uống thuốc; có mốc mơ hồ "sáng mai" nhưng gold vẫn hỏi time |
| train_0498 | ewallet.transfer | ["amount"] | CONTROL | Không cue nhắc; rule không được làm đổi kết quả |
| train_0653 | flights.search | ["date"] | CONTROL | Như trên |
| train_0683 | video_meeting.create | ["start"] | CONTROL | Như trên |
| train_0684 | maps.get_route | ["origin"] | CONTROL | Như trên |
| train_0823 | calendar.create_event | ["start"] | CONTROL — WATCH | Nguy cơ spillover: nhầm calendar event với reminder |
| train_0961 | bill_payment.schedule_autopay | ["type"] | CONTROL — WATCH | Nguy cơ spillover: transcript có yếu tố "sợ quên" (không phải cue "nhắc", nhưng gần nghĩa) |
| train_1029 | email.archive | ["email_id"] | CONTROL | |
| train_1075 | home_energy.set_alert | ["threshold_kwh"] | CONTROL | |
| train_1104 | tv.tune | ["channel"] | CONTROL | |
| train_1107 | library.reserve | ["book_id"] | CONTROL | |
| train_1111 | email.archive | ["email_id"] | CONTROL | |
| train_1223 | loyalty.redeem | ["reward_id"] | CONTROL | |
| train_1234 | email.create_draft | ["to"] | CONTROL | |

Mọi gold ask đều chỉ có đúng 1 param — so sánh exact = tool_name
bằng nhau VÀ params set bằng nhau (thứ tự không quan trọng).

## 4. Arms và input (cố định ASR trước, giống V10)

**Bước 0 — ASR cache (làm một lần, dùng chung hai arm):** transcribe
current audio + toàn bộ history audio của 20 mẫu bằng
vinai/PhoWhisper-small rev `a86b604`, greedy — cùng ASR và revision
như v7/E0/E1. History turns: 6 mẫu có 0 turns, còn lại 2–12 turns
(0116 nhiều nhất, 12). Cache chuỗi ASR, hash-check để đảm bảo Arm A
và Arm B dùng byte-identical input. Không dùng gold transcript cho
arm nào (E5 đo intent trên ASR thật, không phải trên oracle).

**Arm A (control):** base native V10 + parser E6-C, policy hiện tại
(không có block §2). **Arm B (trial):** base giống hệt + block §2.
Cùng model/revision/seed 42/config (grounding BẬT, max_steps 12,
max_repeats 2)/scorer proxy như V10. Không held-out, không training,
không model mới.

**Cột đo ASR (ghi kèm, không dùng để loại mẫu sau run):** với mỗi
mẫu TARGET, ghi ASR có giữ cue "nhắc" (không phân biệt hoa thường)
hay không. Mẫu TARGET mất cue → gắn cờ ASR-BLOCKED và phân tích
riêng (giống 0025 ở V10): rule không thể được kỳ vọng sửa nó, và nó
không được tính vào verdict rule (xem §5).

## 5. Metric và tiêu chí kết luận (đăng ký trước)

### Metric chính — ask-first accuracy (per-sample, rồi tổng hợp)

- **PASS cho một mẫu** khi và chỉ khi FIRST submitted call bằng đúng
  gold ask (tool_name + params set). Định nghĩa này xử lý đúng các
  trường hợp biên của V10:
  - Model stop với 0 calls → FAIL (stop ≠ ask; hash true trong
    trường hợp này không được tính là pass — bài học 0116-native).
  - Model write trước rồi mới ask → FAIL (first call là write, dù
    ask sau đó có đúng).
  - Model ask sai target (ví dụ phone.call/contact_id khi gold là
    reminders.create/time) → FAIL.
- Báo cáo: bảng per-sample cho cả hai arm + tổng hợp theo nhóm
  (TARGET 7, CONTROL 13). Không báo mean chung 20 mẫu làm verdict
  chính — mean chung trộn target với control và che spillover.

### Metric phụ (đo riêng, không gộp)

| Metric | Định nghĩa |
|---|---|
| Ask-vs-act rate | Tỉ lệ mẫu mà first call là write/call thay vì ask (lỗi 0116-dạng: tự làm thay vì hỏi) |
| Tool_name-only accuracy | First call đúng tool_name nhưng sai params — chẩn đoán: model chọn đúng tool nhưng sai param |
| Pseudo-call caught | Số output text mang hình thức call mà parser E6-C BẮT được → validation_rejected + retry (không phải silent stop). Đây là bằng chứng channel fix đang hoạt động; caught KHÔNG làm FAIL ask-first vì nó chưa bao giờ là submitted call — ask-first chỉ chấm FIRST SUBMITTED call |
| Pseudo-call silent | Số output text mang hình thức call mà KHÔNG bị bắt và kết thúc trace thành clean stop (E6-C không bắt được pattern đó). Silent mới là nhiễu đo: mẫu đó có 0 submitted calls → ask-first FAIL, và verdict toàn cục chuyển thành CONFOUNDED (xem dưới) |
| Premature stop rate | Tỉ lệ mẫu 0 calls |
| Full-trace (secondary) | Hash/F1/score — chỉ để tham khảo. Với mẫu ask_only, ask đúng → score 1; stop 0 calls → hash true nhưng F1 0 → score 0; write → thường hash sai → score 0. Vì vậy full-trace score gần như trùng ask-first, trừ trường hợp stop — lý do metric chính là ask-first chứ không phải score |
| Spillover | Thay đổi ask-first trên nhóm CONTROL, báo riêng từng mẫu WATCH (0823, 0961) |

### Tiêu chí kết luận

- **CONFIRMED (phạm vi disambiguation)** nếu đồng thời: (a) net gain
  trên nhóm TARGET ≥ 2 mẫu (correct_B − correct_A ≥ 2); (b) net
  change trên nhóm CONTROL ≥ −1 (không phá control); (c)
  pseudo_call_silent = 0 ở cả hai arm. (Pseudo-call caught > 0 vẫn
  được — đó là channel fix đang hoạt động, không phải nhiễu.)
- **PARTIAL** nếu TARGET net ≥ +1 nhưng CONTROL net ≤ −2 (và silent
  = 0): rule giúp target nhưng leak sang control — cần thu hẹp
  trigger, ví dụ chỉ kích hoạt khi cue "nhắc" xuất hiện nguyên vẹn,
  không kích hoạt với từ gần nghĩa như "quên".
- **INCONCLUSIVE (bổ sung theo Codex nêu)** nếu TARGET net = +1,
  CONTROL net ≥ −1, silent = 0: tín hiệu yếu trên n = 7, chưa đủ để
  kết luận theo hướng nào — khoảng trống trước đây (không thuộc
  CONFIRMED vì < +2, không thuộc REFUTED vì > 0). Hành động đã đăng
  ký trước tại đây (trước khi E5 chạy): MỞ RỘNG tập mẫu với 28 mẫu
  ask_only còn lại (cùng hai arm, cùng base, cùng metric) rồi tính
  lại verdict trên tập mở rộng — không adopt rule, không kết luận
  rule vô dụng, chỉ vì +1.
- **REFUTED** nếu TARGET net ≤ 0 trong khi silent = 0 (channel sạch
  mà rule vẫn không đổi hành vi → rule text không đủ sức điều khiển
  disambiguation; cần cơ chế khác, không phải thêm chữ).
- **CONFOUNDED** nếu pseudo_call_silent > 0 ở arm nào (bất kể các số
  khác) — phép đo bị nhiễu channel, các verdict khác không có giá
  trị. Đây là lý do E5 bị gate bởi E6-C (§0): E6-C confirmed chính
  là điều kiện để silent về 0.
- **Không kết luận thống kê, không khái quát ngoài 20 mẫu.** Mọi câu
  trong report phải gắn với ID mẫu. E5 một mình không promote rule
  thành policy mặc định — adoption cần user duyệt riêng sau khi đọc
  report (kèm spillover).

## 6. Kiểm tra CPU trước GPU (gate)

GPU chỉ chạy khi tất cả pass. Một run GPU với CPU test fail là run
không hợp lệ.

- **G1 — Prompt hygiene (phạm vi: CHỈ block mới §2, không phải toàn
  bộ prompt):** prompt nền vốn đã chứa catalog tool, context và
  history một cách hợp lệ, nên cấm tool-name trên toàn prompt là sai
  và sẽ tự làm rule trượt kiểm tra (rule cần nhắc tên
  reminders.create và phone.call). Vì vậy G1 chỉ grep block §2 mới
  thêm (rule + ví dụ) và cấm trong đó: sample IDs (train_XXXX), giá
  trị cụ thể từ mẫu (amount, giờ, số điện thoại, contact IDs),
  fragment/quote transcript của mẫu nào (đặc biệt câu "nhắc tôi gọi
  điện cho mẹ" của 0116 — ví dụ đã thay bằng synthetic "Lan"), tên
  người/thực thể trong mẫu, và mọi liệt kê gold ask theo từng mẫu.
  ĐƯỢC PHÉP trong block: tên tool catalog tổng quát mà rule cần
  (reminders.create, phone.call) và tên param tổng quát (time,
  contact_id) — đây là từ vựng của task, không phải đáp án mẫu.
  Kiểm tra thêm: không cụm từ đặc trưng nào trong ví dụ xuất hiện
  trong transcript của 20 mẫu (kiểm tra theo cụm, không phải theo
  từ thường như "gọi" hay "nhắc").
- **G2 — Sample/ASR integrity:** 20 mẫu đều thuộc dev (không
  held-out); ASR cache hash giống hệt giữa hai arm; ghi lại cue
  "nhắc" còn/mất cho 7 mẫu TARGET.
- **G3 — Budget:** prompt Arm B (thêm block §2) đo bằng tokenizer
  rev cdbee75 + 512 reserve ≤ 16384 cho cả 20 mẫu (first-turn; cộng
  bound worst-case nếu cần).
- **G4 — Loop test (text-level fake, CPU):** fake trả ask → submission
  = [ask] và turn kết thúc; fake trả write → submission chứa write;
  fake trả stop → 0 calls. Đảm bảo ask-first được đo đúng từ
  submission, không suy từ hash.
- **G5 — Scoring-key verification:** Codex tự tính lại gold ask của
  20 mẫu từ train release theo ID (không copy bảng §3 một cách mù)
  và dừng lại nếu có bất kỳ mismatch nào với bảng này.

## 7. Checklist trả về (Codex điền sau run)

- [ ] Xác nhận E6-C CONFIRMED (kèm commit/report) trước khi chạy;
      nếu E6-C refuted thì E5 không chạy và report ghi rõ là ON HOLD.
- [ ] Log pass G1–G5 (CPU) trước GPU.
- [ ] Bảng per-sample cho mỗi arm: first call, ask-first PASS/FAIL,
      ask-vs-act, pseudo-call caught/silent riêng biệt, ASR cue
      còn/mất (TARGET), full-trace hash/F1/score (secondary).
- [ ] Trace JSON định dạng v6/v7/E0/E1 (diagnostic-only: ASR của
      model, raw output, call đã chạy, tool feedback — không full
      prompt, không gold, không state dump).
- [ ] Verdict theo đúng §5: CONFIRMED / PARTIAL / INCONCLUSIVE /
      REFUTED / CONFOUNDED + bằng chứng theo ID mẫu; báo riêng
      subgroup gọi/họp/uống thuốc và 2 mẫu WATCH.
- [ ] So sánh trực tiếp cùng mẫu giữa hai arm; không dùng mean
      chung 20 mẫu làm verdict; không đề xuất model khác, training,
      held-out hay merge main từ kết quả E5.

## 8. Sau E5

- Nếu CONFIRMED → user duyệt adoption của rule vào policy (không tự
  promote); sau đó E2 có thể chạy trên nền có rule (mẫu khác nhau
  nên không confound).
- Nếu PARTIAL → thu hẹp trigger rule rồi chạy lại E5 (chỉ đổi trigger,
  không đổi base).
- Nếu INCONCLUSIVE → mở rộng 28 mẫu ask_only còn lại rồi tính lại
  verdict; không adopt, không bỏ rule.
- Nếu REFUTED → dừng hướng rule text cho disambiguation; xem xét cơ
  chế khác (brief riêng, không làm trong E5).
- E4 (guard) vẫn đợi sau cùng; E3 (ASR) độc lập, chạy song song được.
