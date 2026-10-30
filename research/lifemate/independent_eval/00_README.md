# Đánh giá độc lập G&G (LifeMate) — mục lục

Baseline: `4bd95a5` (= `287e68d5` + file handoff). Mọi run đều ghi snapshot;
không coi branch tip di động là cùng một version.

- **01_evaluation_audit.md** — Kiểm toán phần đánh giá hiện tại: 528 tests
  synthetic của tác giả (điểm mạnh/yếu), 3 script gold/shadow
  (`gates_precision_audit.py`, `gg_paired_audit.py`, `gg_shadow.py`),
  và những gì chưa được đo (tích hợp agent, fire mới, adjudication).
- **03_trace_evaluation.md** — Đánh giá 3 trace đã lưu (e1_v10, e6_c_v11,
  e5_v13): metadata đã xác minh, adjudication độc lập từng proposal,
  train_0004 là correct-pass phụ thuộc evidence.
- **04_shadow_protocol.md** — Giao thức runtime shadow ON/OFF (PENDING:
  chưa có agent hook ở baseline) + evaluator offline đã chạy được.
- `../../analysis/gg_independent_eval/` — challenge suite độc lập
  (41 public + 15 sealed, manifest + sealed_manifest băm muối),
  `shadow_evaluator.py` và kết quả offline baseline.

Sealed cases và SALT chỉ nằm local, không push.

## PENDING PUSH (2026-10-30 ~02:40 +07)
Branch `independent-eval-gg-2026-10-30` (từ `gg-phone-callback-lifecycle`)
chưa được tạo: `create_branch` cần approval của user và card đã timeout.
Mọi file đã sẵn sàng trong `~/workspace/zaic-eval/work/`
(10 files, không __pycache__, không sealed). Lệnh push khi user duyệt:
`github call-tool --name create_branch` rồi `github push-files --owner
lenamkhanhh --repo ZaloAIC --branch independent-eval-gg-2026-10-30
--source-dir ~/workspace/zaic-eval/work --paths-file /tmp/push_paths.nul`.
