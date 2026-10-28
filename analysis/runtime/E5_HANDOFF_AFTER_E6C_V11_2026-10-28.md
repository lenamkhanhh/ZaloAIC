# E5 Handoff — sau E6-C V11: cách đếm, bảng chẩn đoán, rà tiêu chí

Bản bàn giao NGẮN cho Codex chạy E5. Không sửa inference, không chạy
model, không thêm rule, không mở rộng tập mẫu. Mọi thay đổi so với
brief E5 (ab780806) đều được ghi rõ là ĐỀ XUẤT cần duyệt, không tự áp
dụng.

Nguồn: `E6_C_V11_AUDIT_2026-10-28.md`,
`e6_c_v11_diagnostic_trace.json`,
`e6_c_v11_verified_comparison.json` (main 4b2695a), đối chiếu
`E5_DEPLOYMENT_BRIEF_2026-10-28.md` (bản ab780806).

## 0. Gate E6-C: SATISFIED — E5 được phép vào G1–G5

- V11 verdict: **CONFIRMED, CHANNEL SCOPE ONLY**, qua nhánh
  explicit-format-failure (không phải khôi phục ask). Proxy 0.1875 →
  0.1875, prerequisite 4/21 → 4/21, hash đúng 3/8 → 3/8, submitted
  calls 10 → 10: E6-C không cải thiện task, chỉ biến silent stop
  thành failure tường minh. Đó đúng là điều gate yêu cầu (channel
  sạch để đo intent), không phải điều gate cấm.
- **Base E5 = code V11 chính xác:** experiment-branch commit
  `a472006441ec69aee1238153b0c7daf53ba41dee` (native V10 + opt-in
  `reject_pseudo_calls`), cả hai arm dùng chung. Commit khác = base
  khác = so sánh không hợp lệ. E6-B vẫn LOẠI KHỎI E5 như brief đã
  định (V11 cũng không chứa E6-B/E5 rule).
- E5 vẫn phải qua G1–G5 trước GPU (audit V11 nhắc lại, brief E5 yêu
  cầu). Handoff này không thay G1–G5, chỉ làm rõ cách đếm và chẩn
  đoán khi chạy.

## 1. Cách đếm — đơn vị là GENERATION, không phải EVENT

### 1.1 Phân loại mỗi generation đúng một lần, theo thứ tự pipeline

Parser chạy trước validator. Một generation chỉ thuộc đúng một loại:

1. **Tagged call** (`blocks ≥ 1`, `format_valid: true`) → đi tiếp tới
   grounding/validator. Nếu bị grounding/validator chặn thì đó vẫn
   là MỘT attempt (xem 1.2), không phải pseudo-call.
2. **Pseudo-call caught** (`blocks = 0`, `pseudo_call_caught: true`,
   `format_valid: false`) → parser-stage failure, tốn một attempt,
   trigger retry, KHÔNG BAO GIỜ là submitted call, KHÔNG BAO GIỜ
   là ask.
3. **Plain-text stop** (`blocks = 0`, `stop_kind: plain_text`, không
   có pseudo flag) → clean stop.
4. **Legacy stop** (bare stop JSON) → clean stop.
5. **Format error khác** (block JSON hỏng, v.v.) → tốn một attempt,
   không phải pseudo-call trừ khi có flag `pseudo_call_caught`.

### 1.2 Đừng cộng dồn event validator vào pseudo-call (bẫy V11)

Bằng chứng V11, mẫu 0116 arm boundary, theo đúng thứ tự trace:

- Attempt 1: tagged `phone.call{cont_01}` → grounding chặn (ID bịa).
- Attempt 2: pseudo-call text `sys.ask_missing_info("phone.call",
  ["contact_id"])` → parser bắt (`pseudo_call_caught: true`).
- Attempt 3: pseudo-call text lại, lần này params mở rộng thành
  `["contact_id", "phone_number"]` → parser bắt. Retry làm model
  elaboration thêm param, KHÔNG phải recovery.
- Hết budget 3 attempts của step → trace kết thúc với chẩn đoán
  `FORMAT_FAILURE_RETRY_EXHAUSTED`, submission rỗng.

Số liệu V11: `pseudo_caught = 2` (generations) nhưng
`validation_rejected = 4` (events). Audit ghi rõ: 4 events đó là 2
attempts, không phải 4 — mỗi proposal sinh thêm event validator
hạ nguồn (echo), không phải attempt mới. **Luật đếm: pseudo_caught
chỉ đếm từ generations có flag; validation_rejected chỉ báo riêng
dạng informational, KHÔNG BAO GIỜ cộng vào pseudo_caught.**

### 1.3 Budget attempts dùng chung, không tách riêng theo loại lỗi

Một step tối đa 3 attempts TỔNG CỘNG (1 generation + tối đa 2
retry), tính chung grounding rejection và parser failure. V11 0116:
1 grounding + 2 parser = hết budget. Đừng báo cáo dạng "3 parser
retry" khi một attempt đã bị grounding tiêu thụ — báo attempts đã
dùng và loại lỗi tiêu thụ từng attempt.

### 1.4 Outcome của trace (đếm theo TRACE, tách khỏi đếm generation)

Mỗi trace chỉ thuộc một outcome sau (dựa trên cách trace kết thúc
và số submitted calls):

- **COMPLETED_WITH_CALLS:** ≥ 1 submitted call (bất kể kết thúc
  bằng stop hay format failure sau đó — ask-first vẫn chấm trên
  first submitted call).
- **CLEAN_STOP:** 0 submitted calls, generation cuối là plain-text
  hoặc legacy stop, và không generation nào có raw text mang hình
  thức call (xem định nghĩa silent dưới đây).
- **SILENT_PSEUDO:** 0 submitted calls, trace kết thúc sạch (không
  phải format failure) NHƯNG có generation mà raw text mang hình
  thức call và KHÔNG bị parser flag.
- **FORMAT_FAILURE:** trace kết thúc `FORMAT_FAILURE_RETRY_EXHAUSTED`
  (hết attempts trong một step mà không có valid call).

### 1.5 Định nghĩa silent sau V11 (parser hẹp — phải soát bằng mắt)

Parser V11 chỉ đăng ký prefix lowercase `app.tool(` — audit nói rõ
KHÔNG chứng minh được detection cho mọi cách viết pseudo-code khác
(fenced, uppercase, prose-wrapped). Vì vậy "parser không flag" một
mình KHÔNG đủ để kết luận clean. Luật cho E5:

- **Silent** = trace kết thúc sạch + 0 submitted calls + có generation
  mà raw text khớp pattern call-like — pattern đã đăng ký
  (lowercase `app.tool(`) HOẶC bất kỳ cách viết function-like nào
  khác phát hiện khi soát raw text của mọi plain-text stop.
- Nếu soát thấy cách viết mới: đếm là silent, và báo cáo riêng như
  một parser-scope gap (không lặng lẽ gộp vào clean stop).
- **Caught ≠ ask, silent ≠ ask, format failure ≠ ask.** Ask-first
  chỉ chấm FIRST SUBMITTED call. V11 0116: caught = 2, submitted = 0
  → ask-first FAIL (không phải "đã ask").

### 1.6 Bảng đối chiếu số liệu (dùng để tự kiểm tra report E5)

Tổng generations = tagged + caught + plain-text stops + legacy stops
+ format error khác (phải khớp). Riêng ba cột sau KHÔNG BAO GIỜ
cộng với nhau: `pseudo_caught` (generations), `pseudo_silent`
(traces), `explicit_format_failure_samples` (traces).
`validation_rejected` (events) là cột riêng, chỉ để đối chiếu echo.

## 2. Bảng chẩn đoán E5 — một mẫu, một primary, theo thứ tự sau

Áp dụng cây quyết định theo ĐÚNG thứ tự dưới đây (dừng ở nhánh đầu
tiên khớp). Secondary được ghi thêm nhưng không đổi primary count.

| # | Điều kiện (kiểm tra theo thứ tự) | Primary diagnosis | Bằng chứng quan sát trong trace |
|---|---|---|---|
| 1 | Trace kết thúc FORMAT_FAILURE và 0 submitted calls | **CHANNEL (caught→failed)** | `explicit_format_failure: true`, có generations `pseudo_call_caught: true`, submission rỗng. V11 0116 là ví dụ mẫu: intent (phone.call) chỉ thấy trong raw text, KHÔNG được tính là "đã ask" |
| 2 | Trace kết thúc sạch, 0 submitted calls, có generation raw text mang hình thức call mà không bị flag | **CHANNEL (silent)** | Stop sạch + raw text khớp pattern §1.5. Khác nhánh 1 ở chỗ: không có format failure tường minh |
| 3 | 0 submitted calls, không có text mang hình thức call | **PREMATURE STOP** | Stop sạch, raw text là prose/stop thường, không có generation nào giống call |
| 4 | ≥ 1 submitted call, mẫu TARGET, cached ASR thiếu cue "nhắc" (không phân biệt hoa thường) | **ASR CUE LOSS** (primary); ghi intent thực tế làm secondary | Cột ASR (§4 brief E5) = cue mất. Rule không thể được kỳ vọng sửa mẫu này — không tính là rule fail |
| 5 | First submitted call không phải ask, hoặc ask sai tool_name so với gold | **WRONG INTENT** | First call là write/call, hoặc ask tool_name ≠ gold (ví dụ phone.call khi gold là reminders.create) |
| 6 | Ask đúng tool_name nhưng params set ≠ gold | **WRONG ASK PARAMS** | Tool_name khớp, params thừa/thiếu/sai |
| 7 | Không nhánh nào trên khớp | **PASS** | First submitted call = gold ask (tool_name + params set) |

Lưu ý áp dụng:

- Nhánh 4 đứng TRƯỚC nhánh 5–6 có chủ đích: nếu cue đã mất thì lỗi
  intent sau đó được giải thích bằng ASR, không phải bằng rule.
  Ngược lại, nếu cue còn mà vẫn sai intent thì đó mới là bằng chứng
  chống lại rule.
- Nhánh 1–3 đứng trước nhánh 4–6 vì: chưa có submitted call thì
  không có gì để chấm intent/params — mọi kết luận intent từ raw
  text chưa submit đều là secondary, không phải primary.
- Với mẫu CONTROL, nhánh 4 không áp dụng (không có cue kỳ vọng) —
  đi thẳng từ nhánh 3 sang nhánh 5.
- Hash true với 0 submitted calls là vacuous (không đổi state) —
  không được dùng làm bằng chứng PASS hay "đã ask" ở bất kỳ nhánh
  nào.

## 3. Rà tiêu chí verdict và G1–G5 — chỉ một lỗi cụ thể, một đề xuất

### 3.1 Verdict partition: đầy đủ, KHÔNG mâu thuẫn nội bộ

Sau bản ab780806, bảng verdict đã phân hoạch kín (TARGET net /
CONTROL net / silent): CONFIRMED (≥ +2 / ≥ −1 / 0), PARTIAL (≥ +1 /
≤ −2 / 0), INCONCLUSIVE (+1 / ≥ −1 / 0), REFUTED (≤ 0 / silent 0),
CONFOUNDED (silent > 0, override mọi số khác). Không còn khoảng
trống như lỗi +1 trước đây. Ask-first PASS (first submitted call =
gold ask) nhất quán với cây chẩn đoán §2 (nhánh 5–7).

### 3.2 Lỗi cụ thể duy nhất: format-failure làm nhiễu verdict rule

Brief viết "pseudo-call caught > 0 vẫn được" cho CONFIRMED — đúng
khi caught dẫn tới recovery, nhưng V11 cho thấy nhánh thực tế là
**caught → exhausted → format failure, recovery = 0/1 quan sát
được**. Một mẫu TARGET kết thúc format failure sẽ FAIL ask-first
(0 submitted calls) DÙ rule có thể đã sửa đúng intent trong đầu
model — vì model không emit được tagged call sau retry. Nếu nhiều
mẫu TARGET rơi vào nhánh này, verdict REFUTED sẽ phản ánh channel
failure chứ không phải rule failure, trong khi brief không có luật
nào tách hai thứ đó ra. Đây là lỗi attribution cụ thể, không phải
vấn đề diễn đạt.

**Đề xuất sửa duy nhất (CẦN user duyệt trước khi E5 chạy GPU; nếu
không duyệt thì chạy nguyên văn brief ab780806 và ghi format-failure
là limitation):** báo cáo TARGET net gain theo HAI cách, không đổi
arms/mẫu/rule/denominator:

- (a) overall như brief (mọi mẫu TARGET đều tính).
- (b) channel-recovered-only: chỉ các mẫu TARGET mà trace KHÔNG kết
  thúc format failure (tức channel cho phép intent thể hiện).
- Nếu (a) và (b) cho verdict khác nhau (ví dụ overall REFUTED nhưng
  (b) CONFIRMED/INCONCLUSIVE) thì verdict báo cáo phải ghi rõ
  **CHANNEL-CONFOUNDED** (rule effect chưa đo được trên các mẫu
  rớt channel), không được báo REFUTED sạch. Đây là luật báo cáo
  bổ sung, không phải verdict mới, không loại mẫu khỏi denominator
  chính, không đổi arms hay rule.

### 3.3 G1–G5: không mâu thuẫn, chỉ hai lưu ý thực thi

- **G1 (scoped block):** nhất quán với V11 — parser scope (detection)
  và prompt hygiene (leak check) là hai việc khác nhau, không xung
  đột. G1 vẫn chỉ grep block §2 mới; tên tool catalog tổng quát vẫn
  được phép.
- **G2 (ASR cache):** V11 dùng cache của 8 mẫu smoke — E5 KHÔNG
  được tái dùng cache đó (mẫu khác nhau). Transcribe một lần cho 20
  mẫu E5 (current + history), hash-check giữa hai arm, ghi cột cue
  cho 7 mẫu TARGET. ASR rev giữ nguyên `a86b604` như V11.
- **G3 (budget):** không mâu thuẫn; nhưng budget phải đo trên prompt
  E5 THỰC TẾ (native V11 + rule ở Arm B), không suy từ V10.
- **G4 (loop test):** nhất quán; bổ sung KHÔNG ĐỔI TIÊU CHÍ: fake
  loop test thêm trường hợp fake trả pseudo-call → retry → tagged
  ask, để chứng minh đường parser E6-C đã nối đúng trong base E5
  (chứ không chỉ test ask → submission).
- **G5 (scoring key):** nhất quán; tính lại gold ask của 20 mẫu từ
  train release, dừng nếu mismatch với bảng §3 của brief.

### 3.4 Những thứ KHÔNG phải lỗi — đừng sửa

- Proxy/prerequisite không tăng ở V11 không phải lỗi của E6-C: gate
  chỉ yêu cầu channel sạch (silent → explicit failure), và V11 đạt
  đúng nhánh đó. Đừng "sửa" E6-C để ép recovery.
- Control arm tái tạo V10 8/8 và 7 mẫu boundary còn lại tái tạo V10
  đúng — baseline ổn định, không cần chạy lại V10.
- Retry làm model elaboration thêm param (`phone_number`) không
  phải bằng chứng rule hoạt động hay hỏng — nó chỉ cho thấy retry
  không sửa channel; chẩn đoán vẫn là CHANNEL (caught→failed).

## 4. Checklist chạy E5 (theo thứ tự)

1. Pin base = commit `a472006` (V11); xác nhận cả hai arm cùng base,
   không E6-B, không rule E5 ở arm control.
2. Qua G1–G5 (kèm G4 bổ sung §3.3); ghi log CPU trước GPU.
3. Chạy GPU hai arm trên 20 mẫu, ASR cache chung đã hash-check.
4. Chấm ask-first theo §1.5 + cây chẩn đoán §2 (một primary/mẫu);
   báo cáo caught/silent/format-failure theo §1.6, KHÔNG cộng dồn
   validation_rejected events.
5. Tính verdict theo §3.1; nếu user đã duyệt đề xuất §3.2 thì báo
   thêm cột (b) và qualification CHANNEL-CONFOUNDED khi (a)/(b)
   khác verdict; nếu chưa duyệt thì chạy nguyên văn ab780806 và ghi
   limitation.
6. Report per-sample + bảng chẩn đoán + verdict; không promote
   baseline, không adopt rule nếu chưa qua user duyệt riêng.
