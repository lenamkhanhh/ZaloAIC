# 04 — Giao thức runtime shadow ON/OFF + evaluator

Trạng thái: **chưa có agent hook ở baseline** — không agent nào gọi G&G
(audit-script-only + tests). Phần làm được hôm nay là evaluator offline;
phần runtime ghi là PENDING, không bịa hook.

## 1. Mục tiêu của shadow ON/OFF

Trả lời 3 câu hỏi của task mà không can thiệp agent:

1. Lệnh sai có lọt không (miss) / lệnh đúng có bị chặn không (false block)?
2. G&G có làm đổi hành vi agent khi chỉ quan sát không?
3. Đóng góp của từng lớp (G2 baseline / adapter un-fire / suppression /
   prover) là gì?

## 2. Thiết kế giao thức (khi có hook)

- **Vị trí hook (đề xuất, chưa implement):** sau khi agent đề xuất 1 tool
  call, trước khi thực thi. Hook nhận đúng 4 thứ: proposal, prefix nhân
  quả (không chứa proposal hiện tại, không future), roster, current text.
- **Hai chế độ trên cùng input:** OFF = baseline Gate 2
  (`gate_read_before_write`); ON = candidate (`decide`). Ghi cả hai
  decision cho mỗi proposal; agent chỉ thấy decision của chế độ đang chạy
  (hoặc cả hai đều shadow-only nếu muốn đo thuần quan sát).
- **Không đổi hành vi:** hook chỉ trả về decision + reasons; không sửa
  proposal, không sửa state, không retry/terminate. Kiểm tra bằng
  observation-only check (mục 4).
- **Prefix nhân quả:** giống `gg_shadow.py` — model transcript (không phải
  gold audio_text), history ASR, tool events trước proposal; không bao giờ
  đưa gold/label vào evidence.
- **Dữ liệu:** chỉ dev1237 khi cần replay; held-out 308 khóa tuyệt đối.
- **Snapshot:** ghi commit SHA của code G&G cho mỗi run; không coi branch
  tip di động là cùng một version.
- **Metric:** paired diff (agreement / un-fire / new-fire), adjudication
  độc lập từng decision change (đúng-block / sai-block / đúng-pass /
  miss / out-of-scope / insufficient-evidence), precision/recall chỉ trên
  subset đã adjudicate.

## 3. Evaluator offline (đã chạy được ở baseline)

`shadow_evaluator.py` — so OFF vs ON trên fixture public của challenge
suite, không cần agent/simulator:

- Mỗi context chạy `decide()` một lần, lấy `baseline_fired` (OFF) và
  `fired` (ON) từ cùng một lần tính — đúng nghĩa paired.
- Kiểm tra applicability ổn định và observation-only (input không bị mutate).

Kết quả baseline `4bd95a5` (41 public contexts, `shadow_offline_baseline_4bd95a5.json`):

- Agreements: 32/41. Decision changes: 9 (8 un-fire, 1 new-fire), 0 raise.
- 8 un-fire là các control đúng-pass (bằng chứng + selection đúng).
- 1 new-fire duy nhất là IND-ATK-011 (deleted-entity): baseline pass vì
  Gate 2 không biết delete; candidate fire qua lifecycle suppression —
  đúng hành vi thiết kế của Adjustment 2.
- Observation-only: 0 violation — `decide()` không mutate proposal,
  prefix hay roster trong mọi context.

Lưu ý phạm vi (khớp mục 2): suppression chỉ fire được trên **id refs**
khi baseline đã pass; với contact/phone refs mà baseline pass (wrong-person
tới số trong roster, action mismatch, duplicate name, delegation,
money-as-target), adapter không có đường fire mới — đó là lỗ hổng phạm vi
đã ghi, không phải bug của evaluator.

## 4. PENDING (không bịa, không tự implement)

1. **Agent hook thật**: chưa tồn tại ở baseline; phía fix cần implement
   theo thiết kế mục 2 rồi mới đo runtime được.
2. **Candidate commit**: chưa được giao; khi có, chạy lại evaluator +
   challenge suite trên đúng commit đó, diff theo row key.
3. **Runtime proposals**: khi có hook, nạp proposals thật vào evaluator
   (thay fixture synthetic) và adjudicate độc lập từng decision change.
4. **Đo “đổi hành vi khi chỉ quan sát”**: cần chạy agent với hook ở chế độ
   shadow-only và so trace tool calls với khi tắt hook — chưa thể làm khi
   hook chưa tồn tại.
