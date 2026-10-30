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
- **06_baseline_vs_candidate_d1090d1d.md** — So sánh baseline
  `4bd95a5` ↔ candidate `d1090d1d` (2026-10-30): 1 bug cũ đã sửa
  (IND-ATK-018), 0 regression, 3 lỗi cũ chưa sửa (SEAL-003/004,
  IND-ATK-019), 8 scope gaps không đổi, 10 case adjudication không đổi;
  observer runtime: agent không đổi hành vi nhưng observer CHƯA tính
  được decision ở entry path thực tế (ModuleNotFoundError).
- `../../analysis/gg_independent_eval/` — challenge suite độc lập
  (41 public + 15 sealed, manifest + sealed_manifest băm muối),
  `shadow_evaluator.py` và kết quả offline baseline.

Sealed cases và SALT chỉ nằm local, không push.

## PUSH DONE (2026-10-30 ~07:50 +07)
- Branch `independent-eval-gg-2026-10-30`, base đúng `4bd95a5`
  (eval baseline, không phải branch tip di động).
- Push commit: `6e640c521863b8ec209fb2c158a92793ba031c1f` (đã verify
  remote: đủ 10 files, không có sealed_cases.py).
