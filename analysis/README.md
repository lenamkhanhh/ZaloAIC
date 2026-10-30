> **Mốc tài liệu:** Nội dung dưới đây thuộc các vòng trước và giữ lại để tái lập. Trước khi chạy hoặc chọn cấu hình, đọc [trạng thái hiện tại](../docs/STATUS.md); không dùng số cũ làm kết quả của commit mới.

# analysis/ — Tài liệu chẩn đoán LifeMate (chỉ đọc, không phải code)

Mục riêng cho việc đối chiếu giữa bên phân tích và bên code (Codex).
Không chứa raw dataset, audio hay weights.

## Nội dung

- `dev_probe_ids.json` — Danh sách 26 probe, tất cả thuộc 1.237 mẫu
  dev (split `lifemate/splits/train_dev_heldout.json`), kèm lý do
  chọn, kỹ năng cần kiểm tra và lỗi cần phân biệt.
- `WAIT_ANALYSIS_2026-10-27.md` — Kiểm chứng probe bằng label thật,
  gold trace smoke-5, và 2 mẫu cần đọc kỹ (train_1696, train_0082).
- `OPTIMAL_PIPELINE_2026-10-27.md` — Tổng hợp pipeline tối ưu từ
  đề xuất ZAIC2 + số liệu đo trên data (ngân sách, latency,
  context, thí nghiệm phân biệt theo thứ tự rẻ → đắt). Đã sửa các
  kết luận quá mạnh ngày 2026-10-27 (xem §0/§2.2/§2.3/§2.4/§3):
  ASR sai cả intent/phủ định/điều kiện chứ không chỉ slot;
  latency A30 và context đủ đều là chưa đo; scorer là proxy, không
  phải evaluator chính thức; chọn trên dev, held-out chỉ kiểm sau
  khi chốt.
- `OBSERVATION_TRUNCATION_2026-10-27.md` — Replay gold 26 probe đo
  mất thông tin do `repr(result)[:300]`: 14/29 read dài quá 300 ký
  tự, 3 giá trị mất thật (845.000 của train_0003; light_bedroom2
  của train_0004 và train_0069), và đề xuất giữ thông tin theo
  schema.
- `EMPTY_VS_ASK_2026-10-27.md` — Phân tích empty-vs-ask bằng cặp
  đối chiếu dev (thiếu giờ → hỏi; trùng contact → hỏi trừ khi có
  yếu tố phân biệt; bị hủy / app không cài / history giải quyết →
  empty) kèm ngoại lệ và mâu thuẫn label.
- `CONTEXT_BUDGET_2026-10-28.md` + `measure_context_budget.py` —
  Nhánh độc lập 2026-10-28: đo prompt bằng tokenizer thật
  (Qwen3-4B-Instruct-2507 rev cdbee75) theo đúng code nhánh
  `codex/lifemate-baseline-integration` commit e79f9722, trên toàn
  bộ 1.237 mẫu dev. Kết luận: JSON compact đầy đủ vừa ngân sách
  (0/4.080 bước vượt, max 9.415 token), trong khi `repr[:300]` làm
  mất 312/1.168 giá trị bước sau cần dùng và 27,9% leaf phi-boolean.
  Đề xuất tối thiểu: thay `repr[:300]` bằng JSON compact đầy đủ,
  giữ nguyên guard raise khi vượt ngân sách. Script tái lập đã kiểm
  chứng khớp byte-identical với code nhánh trên 30 mẫu. Ràng buộc
  renderer vẫn giữ nguyên: không rút gọn list còn ID/tên, không xoá
  field vì thuộc FREE_TEXT_KEYS, không đổi pipeline đang chạy.
- `CONTEXT_BUDGET_A2E832B_2026-10-28.md` +
  `measure_context_budget_a2e832b.py` — Đo RIÊNG prompt thật của agent
  mới a2e832b (cùng nhánh, JSON đầy đủ đã có sẵn trong agent + action
  policy 455 token + outcome not_done), cùng tokenizer/revision/dev/
  ngưỡng. Kết quả riêng, không ghép với phép đo e79f9722: 0/1.237 mẫu
  và 0/4.080 bước vượt ngân sách, max 9.874 token (train_1636), không
  có ID nào vượt — nên chưa cần renderer phức tạp hơn cho phạm vi gold
  replay. Giới hạn ghi rõ: chưa bao phủ observation do model gọi sai
  hoặc lặp. Phép đo e79f9722 giữ nguyên làm đối chứng.
- `runtime/V7_V6_FAILURE_LEDGER_2026-10-28.md` — Phân loại lỗi v6/v7
  theo bằng chứng đầu vào (đọc theo `runtime/README.md` tại main
  800c34f; giải thích bằng code nhánh a2e832b cho v7 và a9d48d2 cho
  v6, không dùng code inference trên main). Ledger xếp hạng: intent/
  entity/nhánh > ASR > thiếu observation > termination > format >
  proxy mismatch, kèm bảng v6→v7 trên 5 mẫu chung và 6 thí nghiệm nhỏ
  (E0 paired gold-current cho agent mới; E1 native tool-calling;
  E2 ví dụ condition-before-write; E3 small-vs-medium ASR; E4 guard/
  completion; E5 disambiguation nhắc-vs-gọi). Không sửa code, không
  chạy model, không held-out.
- `runtime/EXPERIMENT_BRIEF_E0_E5_2026-10-28.md` — Brief giao cho Codex
  chạy E0–E5: giao thức chung, từng arm, mẫu cố định (E5: 20 mẫu
  ask_only dev; E4: 2 mẫu đối chứng lặp hợp lệ 0922/1447), metric,
  tiêu chí falsify, thứ tự chạy, checklist trả về. Brief không chứa
  gold (tra theo ID từ train release) và không cho phép held-out,
  training, đổi model hay merge main.
- `runtime/E1_DEPLOYMENT_BRIEF_2026-10-28.md` — Brief triển khai E1 tự
  chứa sau E0 (main f833dd3, proxy vẫn 0.125, giả thuyết "chỉ còn ASR"
  bị bác): contract chính thức Qwen3-4B-Instruct-2507 rev cdbee75 từ
  chat template + config + model card cùng revision, bảng ánh xạ code
  a2e832b → thay đổi tối thiểu M1–M8 (bắt buộc) vs P1–P7 (loại khỏi
  E1), phân tích lỗi E0 theo contract-có-thể / contract-không-thể,
  thiết kế 2 arm trên cached ASR v7, metric từng tầng, tiêu chí kết
  luận có giới hạn ("format sạch nhưng intent sai" = partial
  confirmation, không phải bác bỏ), và 7 kiểm tra CPU/unit test làm
  GPU launch gate. Ví dụ message/parser đều synthetic, không lấy đáp
  án probe.
- `runtime/E1_PREREQUISITE_CHECKLIST_2026-10-28.md` — Checklist đo
  tầng prerequisite cho E1, build từ gold bằng replay + truy vết nguồn
  giá trị (21 quan hệ chấm điểm cho 8 mẫu: STRICT khi giá trị chỉ có
  trong output của một read trước, BRANCH cho điều kiện, cùng các
  rule NO-CALL/task-type/fallback-direction và regression guard
  0019/0116). FROZEN trước run: Codex copy nguyên vẹn vào hồ sơ run,
  chấm PASS/FAIL độc lập với format/hash/F1, không đưa vào input
  agent.
- `runtime/E1_V10_INTENT_ANALYSIS_2026-10-28.md` — Phân tích E1 V10
  (main b87bf9a): verdict PARTIAL cho format-scope (score 0.125 →
  0.1875 toàn bộ từ 0004 cleanup, prerequisite 5/21 → 4/21), phân rã
  0116 thành ba lớp (intent nhắc–gọi, grounding đã chặn ID bịa,
  pseudo-call text bị tính là clean stop), năm pattern intent còn
  lại, đối chiếu E2/E5, và đề xuất E6 một thí nghiệm ba arm
  (A control native V10, B evidence-first prompt rule, C pseudo-call
  parser rule) với tiêu chí đăng ký trước, negative control 0025,
  caveat vacuous-PASS và gate CPU P1–P4. Không sửa inference, không
  chạy GPU, không hardcode probe.
- `runtime/E5_DEPLOYMENT_BRIEF_2026-10-28.md` — Brief triển khai E5
  đầy đủ, GATED bởi E6-C (không chạy nếu channel chưa sửa, để đo
  intent không bị nhiễu pseudo-call): base native V10 + parser E6-C,
  rule nhắc–gọi với ví dụ synthetic (sửa lỗi brief gốc dùng ví dụ gần
  như nguyên văn transcript 0116), 20 mẫu ask_only với scoring key
  đã kiểm chứng (cue "nhắc" tách sạch 7 target vs 13 control theo
  kiểm tra không phân biệt hoa thường), metric chính ask-first
  accuracy, tiêu chí CONFIRMED/PARTIAL/INCONCLUSIVE/REFUTED/CONFOUNDED,
  2 mẫu WATCH spillover (0823, 0961), cột đo ASR cue, và gate CPU
  G1–G5. Bản sửa theo 4 điểm Codex nêu: hỏi time có điều kiện (chỉ
  khi thiếu), G1 chỉ kiểm tra block mới (không cấm tool-name
  catalog), tách pseudo-call caught khỏi silent, verdict
  INCONCLUSIVE khi target tăng đúng 1 mẫu. Không sửa inference,
  không chạy GPU, không held-out.
- `runtime/E5_HANDOFF_AFTER_E6C_V11_2026-10-28.md` — Bản bàn giao
  ngắn cho Codex chạy E5 sau khi E6-C V11 confirmed (main 4b2695a,
  nhánh explicit-format-failure, không phải khôi phục ask; proxy và
  prerequisite không tăng): gate E6-C satisfied, base pin commit
  a472006; cách đếm theo generation (không cộng dồn event validator
  — V11: 4 validation_rejected events = 2 attempts), budget attempts
  dùng chung, outcome theo trace, định nghĩa silent có soát mắt do
  parser chỉ bắt prefix lowercase app.tool(; cây chẩn đoán 7 nhánh
  (channel caught→failed/silent, premature stop, ASR cue loss, wrong
  intent, wrong ask params, pass); rà verdict/G1–G5 chỉ ra một lỗi
  cụ thể (format-failure làm nhiễu verdict rule) với một đề xuất báo
  cáo hai cột cần user duyệt, không đổi arms/mẫu/rule.
- `runtime/SOTA_ANALYSIS_ALL_ERRORS_2026-10-28.md` — Phân tích SOTA
  cho toàn bộ lỗi LifeMate (v7/E0/E1 V10/E6-C V11) từ 3 luồng research
  song song: verdict prompt/format/retry ĐÃ chạm trần (E0 gold
  transcript không sửa intent, E1 native format làm prerequisite
  giảm 5/21 → 4/21, E6-C bắt được nhưng recovery 0/1, rule trong
  prompt vẫn bị vi phạm); SOTA theo từng nhóm lỗi với nhãn trung
  thực (đo/paper/snippet/suy luận); xếp hạng 8 hướng khác theo
  division of labor (guard code E4 nâng cấp → constrained decoding →
  step-0 gate → N-best ASR → dynamic enum → SFT When2Call-style →
  RL shaped rewards → thu nhỏ decision space) kèm danh sách KHÔNG
  làm có bằng chứng chống và 2 câu phải hỏi organizers (XGrammar
  trên Docker A30, cách đếm params hệ thống).
- `runtime/E5_V13_DEEP_ANALYSIS_AND_NEXT_STEP_2026-10-28.md` — Phân
  tích sâu E5 V13 (main 8846ab1, 40/40 trial, verdict INCONCLUSIVE giữ
  nguyên): vì sao rule sửa được 0116 (intent switch + omission +
  validator chặn create thiếu time → ask) nhưng không sửa 6 target còn
  lại; truy nguồn từng time (0220 copy current_time; 0219/0287/0360
  current_time date + giờ tròn tiếp theo; 0353-control leak lịch ngày
  mai 14:00 đi công viên; 0780 mơ hồ giữa default/giờ ra viện đã bị thay
  thế/giờ ăn sáng); tách lỗi (fill-act 5, hỏi sai params 1, channel 0 ở
  rule arm); control net 0 che 5/13 đổi hành vi + 2 premature stop mới;
  pseudo-call key=value 0653 cả hai arm và giới hạn định nghĩa silent
  (registered 0 vì đã có submitted read; đọc rộng sẽ thành CONFOUNDED —
  công khai, không rescore); sửa 4 kết luận quá rộng trong bản SOTA
  (E0 chỉ gold-current không phải thông tin hoàn hảo; trần prompt/
  format/retry chưa chứng minh cho toàn họ; resolver ≠ ledger nguồn —
  V13 fill-act chính là H5 residue paper tự loại trừ; trích dẫn
  When2Call/SAGE/CAST/resolver đã verify lại kèm khoảng cách chuyển
  giao); so sánh A/B/C + dự bị D và CHỌN E7 guard nguồn time/amount.
- `runtime/E7_GUARD_DEPLOYMENT_BRIEF_2026-10-28.md` — Brief triển khai
  E7 (đề xuất, chờ duyệt riêng trước khi làm): giả thuyết falsifiable
  (guard chặn write thiếu provenance → chuyển fill-act thành ask);
  base a472006, control fresh = V13 control y hệt, đúng một biến là
  guard (không rule E5, không đổi parser/prompt/ASR); tập 20 mẫu E5 cố
  định; spec provenance generic (A1–A4 allow, B1–B5 block, partial
  provenance = block, reads/asks ngoài phạm vi); CPU gates G1–G5 +
  shadow audit 3 tập (40 traces V13, gold writes dev, ASR-vs-gold gap)
  là cửa bắt buộc trước GPU; key=value chỉ reporting, không đổi parser;
  metric ask-first + breakdown sau block; tiêu chí CONFIRMED/PARTIAL/
  REFUTED/INVALID; nguy cơ chặn nhầm (refer-back, supersession,
  date-vs-hour, ASR gap, amount derivations); chi phí ~643s GPU theo
  tốc độ V13 sau khi gates pass.

## Hai bộ smoke — đừng nhầm lẫn

- **Bộ smoke của Muse:** train_0025, train_0016, train_0049,
  train_0004, train_0019 (trường `smoke_ids` trong
  `dev_probe_ids.json`).
- **Bộ smoke của Codex:** train_0019, train_0116, train_0025,
  train_0003, train_0008.
- Giao nhau: train_0019, train_0025. Hợp của hai bộ (8 mẫu):
  train_0003, train_0004, train_0008, train_0016, train_0019,
  train_0025, train_0049, train_0116. Cả hai bộ đều là tập con của
  26 probe; không bộ nào chứa mẫu held-out.

## Cách chọn đủ 26 ID (chú ý hành vi của --ids-file)

`lifemate/run.py --ids-file` đọc `smoke_ids` TRƯỚC `probes`, nên
`--ids-file analysis/dev_probe_ids.json` chỉ chạy 5 mẫu smoke của
Muse, không phải 26 mẫu. Để chạy đủ 26 mẫu, dùng một trong hai
cách (không sửa code):

```bash
# Cách 1: liệt kê ID từ trường probes rồi đưa vào --ids
IDS=$(python3 -c "import json; print(','.join(p['id'] for p in json.load(open('analysis/dev_probe_ids.json'))['probes']))")
python3 -m lifemate.run infer --data <data> --split train \
  --config lifemate/configs/recommended.json --ids "$IDS" --out out.jsonl
# Cách 2: file JSON chỉ chứa danh sách trần 26 ID (định dạng bare list
# mà --ids-file cũng chấp nhận), rồi dùng --ids-file với file đó.
```

Chạy bộ smoke của Codex hoặc hợp hai bộ thì dùng `--ids` với danh
sách tương ứng ở trên.

## Metadata probe chỉ dành cho chẩn đoán — tuyệt đối không đưa vào input agent

File probe tuy KHÔNG có mảng gold calls, nhưng các trường `reason`
đã chứa ID/amount/chuỗi đáp án (ví dụ reason của train_0003 nêu
845.000 và c_06; reason của train_0004 nêu light_bedroom2 và 50).
Vì vậy TOÀN BỘ metadata probe — `reason`, `transcript_gold`,
`skill_to_test`, `error_to_distinguish` — và toàn bộ các file
phân tích trong mục này (vốn trích gold để đối chiếu) chỉ dùng để
chẩn đoán SAU khi chạy. Input của agent chỉ gồm audio + context +
history của mẫu, không bao giờ gồm metadata probe hay đáp án gold.

## Quy ước bắt buộc khi dùng các file này

- **Định nghĩa read:** tool có `kind: "read"` trong catalog
  (read = không đổi state; write = đổi state/tạo hành động;
  meta = `sys.ask_missing_info`). Trên gold dev: read 1.280 /
  2.843 (45,0%), write 1.389, meta 174. Không dùng heuristic đoán
  theo tên tool (con số 1.138 cũ theo tên là sai, đã sửa).
- **train_1696 là gold anomaly:** gold chứa luôn call
  `chat_ott.send_message` tới `chat_6142` không tồn tại
  (`ok: true, done: false`). KHÔNG hardcode id sai này vào agent
  hay prompt, không dạy model phát ra id không tồn tại. Khi đo,
  báo cáo mẫu này riêng (ghi chú anomaly).
- **Không hard-code đáp án probe:** file probe cố tình KHÔNG chứa
  gold tool calls. Chấm điểm từ label train bằng
  `lifemate/run.py score`. File trace gold chi tiết KHÔNG nằm
  trong repo (giữ ở máy phân tích) đúng theo thiết kế này.
- **Hỏi chưa có đáp án (Q-L1/Q-L3/Q-L5):** cách chấm ask, read có
  tính F1 không, và hết vòng lặp nộp gì — vẫn mở, xem `gaps.md`.


## E7 Phase 0 shadow result

- `runtime/E7_PHASE0_SHADOW_AUDIT_2026-10-28.md` — CPU_NOT_READY. Of459 monitored gold writes:31 ALLOW,428 UNKNOWN,0 BLOCK;5/6 known fills blocked. No inference integration/GPU;UNKNOWN is not a pass.
- `runtime/e7_phase0_verified_summary.json` — v1/v2/v3 results and source hashes;the initial40 candidate false-blocks remain disclosed.
- `e7_shadow/README.md` — reproducible pure-CPU guard/tests/runner/spec and bounded independent review.
