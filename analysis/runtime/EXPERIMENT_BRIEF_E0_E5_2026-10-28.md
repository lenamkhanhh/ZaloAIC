# Brief thí nghiệm E0–E5 cho Codex — sẵn chạy, chưa chạy

Trạng thái: READY FOR CODEX RUN. Tài liệu này là brief giao việc, không
phải kết quả. Mọi arm chạy trên nhánh thí nghiệm, không sửa code
inference trên main, không training, không held-out, không merge tự động
— kết quả mỗi thí nghiệm cần user duyệt riêng trước khi áp dụng.

Nguồn: `V7_V6_FAILURE_LEDGER_2026-10-28.md` (cùng thư mục) + hướng dẫn
tại `README.md` (runtime, main 800c34f). Brief này chỉ chứa ID mẫu và
quy tắc đo; gold (transcript/call) tra từ bản train release đã kiểm
chứng theo ID, KHÔNG đưa gold vào prompt agent. Artifact trace của mỗi
run tuân thủ cùng kỷ luật như v6/v7: `DIAGNOSTIC_ONLY_NEVER_AGENT_INPUT`,
chỉ gồm ASR của model, raw output, call đã chạy và tool feedback —
không full prompt, không gold, không state dump.

## 0. Giao thức chung cho mọi thí nghiệm

- Agent chạy: nhánh `codex/lifemate-baseline-integration`, commit
  `a2e832b` (trừ arm thử nghiệm ghi rõ thay đổi — thay đổi đó chỉ nằm
  trong bản chạy thí nghiệm, không commit lên main).
- ASR mặc định: vinai/PhoWhisper-small rev `a86b604` (trừ arm medium của
  E3 — medium chỉ dùng chẩn đoán; licence/date trên thẻ vinai chưa kiểm
  chứng nên chưa dùng cho submission).
- LLM: Qwen/Qwen3-4B-Instruct-2507 rev `cdbee75`, greedy, seed 42,
  Transformers 4.57.6, FP16/T4x2 như v6/v7. Không phải bằng chứng runtime
  A30; không báo latency A30 từ các run này.
- Dữ liệu: bản train release v3.2.0 đã kiểm chứng SHA256 (như v6/v7).
  Chỉ dùng dev. 8 mẫu smoke v7: 0019, 0116, 0025, 0003, 0008, 0016, 0049,
  0004 (ghi đủ `train_` prefix khi chạy).
- Báo cáo mỗi run: per-sample (submitted calls, state_hash đúng/sai, F1
  proxy, score = F1 nếu hash đúng else 0) + trace JSON định dạng như
  v6/v7 + một dòng verdict cho giả thuyết: CONFIRMED / REFUTED /
  UNRESOLVED + failure mode mới nếu có.

## E0 — Lặp lại paired diagnostic cho agent mới (LÀM TRƯỚC TIÊN)

- Giả thuyết đối thủ: "a2e832b đã sửa phần LLM, chỉ còn ASR là vấn đề."
- Thiết kế: đúng 8 mẫu v7, agent a2e832b, nhưng current transcript =
  GOLD (history ASR giữ nguyên như v7 — chỉ đổi current, giống thiết kế
  v6). Không arm nào khác.
- Đo: per-sample delta so với v7 live-ASR (call, hash, F1) + phân loại
  lỗi còn lại theo ledger (ASR/format/intent/prerequisite/termination/
  proxy mismatch).
- Kết luận được: mẫu nào vẫn sai với transcript chuẩn → lỗi thuộc
  LLM/policy/contract, không phải ASR; mẫu nào sửa được → ASR là nút
  thắt cho mẫu đó. Không có E0 thì E1/E3 tranh luận trên nền thiếu arm
  đối chứng — vì vậy E0 chạy trước, và E1/E3 chỉ nên kết luận sau E0.

## E1 — Native tool-calling vs text contract (giả thuyết contract)

- Giả thuyết: model sai format ask (0003: tool_name/params ở top-level
  thay vì trong `"arguments"`) vì bị dùng ngoài hợp đồng native: chat
  template của Qwen3-4B-Instruct-2507 rev cdbee75 CÓ nhánh
  `{% if tools %}` (system block `<tools>` + `<tool_call>`) và message
  role `tool` (`<tool_response>`), nhưng llm hiện tại không truyền tools
  vào template (chỉ 1 user message, tools=None) nên model phải theo
  hợp đồng prose + bare JSON.
- Arm A (đối chứng): contract hiện tại, giữ nguyên.
- Arm B (thử): truyền tools vào `apply_chat_template` (system block
  `<tools>`), observation render thành message role `tool`
  (`<tool_response>`), parser chấp nhận JSON trong `<tool_call>`. Chỉ
  đổi contract, không đổi model/policy/grounding.
- Mẫu: 8 mẫu v7. Đo: số validation_rejected (format error), 0003 có
  vượt qua được ask để tới list_bills/search không, ask đúng
  tool_name/params không, per-sample hash/F1/score.
- Falsify: arm B vẫn bẹt ask ra top-level hoặc vẫn hỏi sai tool → giả
  thuyết contract sai, vấn đề nằm ở hiểu task, không phải format.
- Tách tầng (chỉ khi B có hiệu ứng và cần biết tầng nào gây ra): B1 chỉ
  đổi parser (chấp nhận `<tool_call>`, giữ text prompt); B2 chỉ đổi
  template (truyền tools). Mặc định chạy B gộp trước cho rẻ.

## E2 — Policy + ví dụ condition-before-write vs policy hiện tại (prompt-only)

- Giả thuyết: policy text hiện tại không ép được thứ tự điều kiện →
  write (0008 viết trước khi xem forecast ở cả hai bản); cần ví dụ minh
  hoạ, không phải thêm chữ chung chung.
- Arm A: policy hiện tại. Arm B: policy hiện tại + đúng 1 ví dụ TỔNG
  QUÁT sau (không lấy từ dev, không chứa ID/amount của mẫu nào):
  > Ví dụ (không phải yêu cầu thật): user nói "nếu mai mưa thì dời họp
  > muộn 30 phút" → bước đầu tiên phải là đọc dự báo ngày mai; chỉ khi
  > dự báo nói mưa mới dời họp, nếu không mưa thì dừng, không ghi gì.
- Mẫu: 8 mẫu v7, đo riêng 0008 + 0016 (hai mẫu conditional), kiểm tra
  regression trên 6 mẫu còn lại.
- Đo: 0008 có đọc forecast trước write không; 0016 có bắt đầu bằng
  forecast/list thay vì dừng ngay không.
- Falsify: arm B vẫn viết trước → vấn đề không phải thiếu ví dụ, cần
  cơ chế chặn write ngoài prompt (đề xuất sau, không làm ngay).

## E3 — Small-vs-medium ASR, đo slot quyết định + downstream

- Giả thuyết: một phần lỗi là ASR small; medium sửa được đúng các slot
  quyết định.
- Giai đoạn 1 (transcription, không cần agent): transcribe current +
  history audio của 8 mẫu bằng PhoWhisper-small và medium (cùng greedy).
  Chấm thủ công theo slot sau cho từng mẫu (không chấm WER chung chung
  vì WER không nói được slot nào chết): condition còn/mất, negation
  còn/mất, tên người chính xác?, tiền chính xác?, giờ/ngày chính xác?,
  địa điểm chính xác? Ghi bảng slot × mẫu × {small, medium}.
- Giai đoạn 2 (agent): chạy agent a2e832b trên cùng 8 mẫu với transcript
  medium (arm medium) so với transcript small (v7 đã có).
- Đo: bảng slot còn/mất + per-sample delta call/hash/F1 giữa hai arm.
- Falsify: medium không sửa được slot của 0025/0016, hoặc sửa slot mà
  agent vẫn sai như v6 gold-current → ASR không phải nút thắt cho các
  mẫu đó, dừng đầu tư ASR, quay lại E1/E2/E4.
- Lưu ý ngân sách (đã tính ở OPTIMAL_PIPELINE): medium + Qwen3-4B =
  4,769B, dưới cap 6B. Nhưng licence/date của medium chưa kiểm chứng —
  chỉ dùng chẩn đoán, chưa dùng cho submission.

## E4 — Guard/completion: siết max_repeats vs hiện tại, có đối chứng lặp hợp lệ

- Giả thuyết: model không dừng sau thành công lần đầu; guard hiện tại
  (cho lặp 2 lần) che giấu lỗi này thành "chỉ thừa 1 lần".
- Arm A: max_repeats=2 (hiện tại). Arm B: max_repeats=1 (chặn mọi lặp).
  Không đổi gì khác.
- Mẫu: 8 mẫu v7 (nhóm vấn đề: 0004 ghi trùng, 0049 lặp done:false,
  0008 sửa trùng) + 2 mẫu đối chứng lặp HỢP LỆ sau (gold chứa cùng 1
  call 2 lần do user yêu cầu nhiều instance — KHÔNG được phá):
  - train_0922: loyalty.redeem cùng (prog_815, rw_02_1) ×2 — user nói
    "được mấy ly thì đổi hết mấy ly" (đổi hết, nhiều instance).
  - train_1447: loyalty.redeem cùng (prog_90, rw_01_1) ×2 — user nói
    "lấy hai vé" (hai instance).
- Đo: số lần ghi thừa trên 8 mẫu; tỉ lệ phá request ở 2 mẫu đối chứng
  (mẫu đối chứng còn ra đủ 2 lần redeem không?).
- Falsify: max_repeats=1 không giảm được ghi thừa (model đổi sang call
  khác tương đương) hoặc phá nhiều request hợp lệ → guard không phải
  đáp án, cần completion-check theo ngữ nghĩa (đã xong tất cả action
  của nhánh → stop), không phải đếm lặp.
- Không làm: dedup mù toàn cục (phá request lặp hợp lệ).

## E5 — Disambiguation "nhắc + hành động" vs policy hiện tại (prompt-only)

- Giả thuyết: 0116 sai vì model không phân biệt "nhắc làm X" (reminder
  cần time) với "làm X ngay" (call cần contact_id).
- Arm A: policy hiện tại. Arm B: policy hiện tại + đúng 1 quy tắc sau:
  > Quy tắc phân biệt nhắc–gọi: khi user nói "nhắc + <hành động>" (ví
  > dụ "nhắc tôi gọi điện cho mẹ"), đó là tạo reminder — thông tin
  > thiếu thường là thời gian, hỏi reminders.create/time. Chỉ khi user
  > nói gọi ngay/lập tức (ví dụ "gọi ngay cho mẹ") mới là phone.call —
  > khi đó mới hỏi contact_id.
- Mẫu: 20 mẫu ask_only dev sau (starter set cố định, sắp xếp theo ID;
  tổng số ask_only dev là 48, 28 mẫu còn lại chỉ mở rộng khi rẻ):
  train_0116, train_0219, train_0220, train_0287, train_0353,
  train_0360, train_0498, train_0653, train_0683, train_0684,
  train_0780, train_0823, train_0961, train_1029, train_1075,
  train_1104, train_1107, train_1111, train_1223, train_1234.
  (Định nghĩa ask_only: gold trace chỉ gồm đúng 1 call ask. Gold ask
  của từng mẫu tra từ train release theo ID, không ghi trong brief này.)
- Đo (chính): tỉ lệ ask đầu tiên đúng tool_name/params. Đo (phụ, nếu
  chạy full trace): per-sample hash/F1/score. Khi báo cáo phải ghi rõ
  đo ask-first khác với đo full task.
- Falsify: arm B vẫn hỏi phone.call ở các mẫu nhắc → vấn đề không phải
  thiếu quy tắc, model không áp dụng được quy tắc phân biệt (quay lại
  E1).

## Thứ tự chạy và điều kiện dừng

1. E0 trước (lấp lỗ phương pháp).
2. E1 và E3 song song (hai giả thuyết độc lập lớn nhất).
3. E2, E5 sau khi có E0 (chúng sửa intent/prerequisite mà E0 sẽ xác
   nhận còn tồn tại với transcript chuẩn).
4. E4 sau cùng (chỉ sau khi biết duplicate có còn là vấn đề dưới
   contract mới E1 hay không).
5. Không chạy: mẫu lớn hơn, training/SFT, đổi model, held-out, merge
   main. Đặc biệt: không đề xuất model khác trước khi E0–E5 phân loại
   xong — ledger cho thấy phần lớn lỗi là contract/intent/prerequisite/
   termination, không phải "model yếu" nói chung.

## Checklist trả về cho mỗi thí nghiệm (Codex điền)

- [ ] Source commit + data SHA + ASR/LLM revision đã dùng.
- [ ] Per-sample: submitted calls, hash đúng/sai, F1, score.
- [ ] Trace JSON định dạng v6/v7 (diagnostic-only, không prompt/gold).
- [ ] Verdict: CONFIRMED / REFUTED / UNRESOLVED + bằng chứng (ID mẫu,
      event, số liệu) + failure mode mới nếu có.
- [ ] So sánh trực tiếp với arm đối chứng cùng mẫu (không so mean
      khác mẫu số).
