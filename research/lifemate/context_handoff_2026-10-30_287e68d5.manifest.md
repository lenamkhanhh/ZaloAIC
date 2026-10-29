# HANDOFF MANIFEST — LifeMate / G&G Context Handoff (2026-10-30)

Bàn giao kèm tài liệu `context_handoff_2026-10-30_287e68d5.md` (cùng thư mục).
Nhánh: `gg-phone-callback-lifecycle`. Commit được audit:
`287e68d5022aac243f2b5721029b6db6a17d93b5` (parent
`6030f760a973b6d813c7f9b178d278dda4801193`). Main không thay đổi
(`1caa885ac35f2719f85ef553db457b984e6d2131`); KHÔNG merge; KHÔNG sửa code;
KHÔNG sửa MEMORY.md trong task này.

## Files trong bàn giao này

| File (repo-relative) | Nội dung | SHA256 (local, trước push) |
|---|---|---|
| research/lifemate/context_handoff_2026-10-30_287e68d5.md | Tài liệu bàn giao đầy đủ (9 mục + TOC + bảng trạng thái + checklist + unknown + tóm tắt) | 123c6f87689d3f042f902cd33be419b7f106d3a607834408319f63ad3ad10b8e |
| research/lifemate/context_handoff_2026-10-30_287e68d5.manifest.md | Manifest này | (xem blob SHA sau push — manifest không thể chứa SHA của chính commit chứa nó, cùng self-reference note như các báo cáo trước) |

Kích thước tài liệu: 109,354 bytes (trước khi đổi tên; xem blob SHA sau push để
xác minh byte-identical).

## Source pins (đã đối chiếu trực tiếp trong task bàn giao)

- Nhánh `gg-phone-callback-lifecycle` tip = commit được audit (GitHub API:
  list_commits + get_commit; không có commit nào sau nó trên nhánh).
- Commit được audit: 7 files, blob SHA remote == local (xem §1.2 của tài liệu).
- Agent a2e832b: đọc trực tiếp worktree `lifemate/agent.py`, `llm.py`, `run.py`,
  `loader.py` (entry, loop, prompt, parse, ASR conditions).
- Zaic_tools: đọc trực tiếp package trong data dir (`executor.py`, `validate.py`,
  `apps/contacts.py`, `apps/phone.py`, `apps/sms.py`, `apps/base.py`, `apps/email.py`).
- Suites: chạy lại cả 10 file, cả 2 backend (system python3 + zaic-test-venv):
  528/528 OK, 0 fail/error/skip.
- Đếm lại: train.jsonl 1545 samples; 3491 history assistant turns (list 2981 /
  field absent 510 / str 0) — giải quyết mâu thuẫn "MISSING 4001" (xem §6.3).
- SFT manifest v2: directory listing + đọc đầu file qua API:
  `analysis/overnight_capability_audit/inner_split_seed1337_v2.json` trên nhánh
  sft-prototype-v2 (counts 866/185/186; eligible 1236 toàn dev vs 865 trong
  inner_train — khác universe, xem §6.2).
- Trace provenance: audit .md trong `analysis/runtime/` (E1_V10, E6_C_V11, E5_V13)
  — V13 base là a472006 (hiệu chính standing note "main e2245ab1", xem §6.6).
- Round10-fix-report-round3 §4.1: scope E7 (456 writes / 533 args; DAG PROVEN 276)
  và dòng denominator gates (971 → 957 / 976).

## Phương pháp xác minh (theo yêu cầu: ưu tiên bằng chứng thực tế)

Mọi khẳng định load-bearing trong tài liệu đều có một trong các dạng bằng chứng:
(a) đọc trực tiếp code/API trong task này (ghi file:dòng hoặc lệnh),
(b) chạy lại test/đếm trong task này (ghi command + kết quả),
(c) "trích kết quả cũ" kèm nguồn báo cáo cụ thể (không trình bày như đã xác minh
lại), hoặc (d) UNKNOWN + nguyên nhân (xem mục "Thông tin chưa biết" trong tài liệu).
Báo cáo cũ mâu thuẫn code được nêu rõ và ưu tiên code (2 hiệu chính lớn:
`__invalid__` thuộc về generator wrapper chứ không phải parser; V13 base là a472006
chứ không phải "main e2245ab1").

## Cam kết loại trừ (sanitize)

Tài liệu + manifest này KHÔNG chứa:
- Raw dataset, gold sample text, gold call text, held-out content (kể cả IDs kèm
  nội dung — chỉ có IDs trần trong danh sách un-fires, không kèm nội dung).
- Full prompt dumps, model weights, audio, environment state (state.json,
  train_environment/).
- Voucher codes, credentials, passwords, tokens, MSSV, số điện thoại thật, email
  cá nhân của user.
- Nội dung file local-only `sft_prototype_local.json` (chỉ ghi nhận sự tồn tại và
  lý do loại trừ).

Số X/Y/Z và tên vai trò (OWNER/OTHER) trong ví dụ đều là fixture synthetic của
probe/red-team, đã ghi rõ trong tài liệu — không phải dữ liệu thật.

## Điểm chưa xác minh (xem đầy đủ tại "Thông tin chưa biết" trong tài liệu)

Còn mở sau task này (không đoán): ý nghĩa của e2245ab1; fixed-field patches +
smart_home/home_automation shared registry (giữ nhãn "trích kết quả cũ");
người chạy zero-shot benchmark + vị trí kết quả (D6); các quyết định policy cần
user (channel cross-clause pin, relation synonyms scope, có gửi câu hỏi BTC không,
vòng 11 do Muse hay Codex làm); ngân sách GPU cho shadow on/off diff và E7 40-trial.

## Push

Commit chứa 2 files này: xem commit mới nhất trên nhánh sau push (manifest không
thể tự chứa SHA của chính nó). Verify sau push: commit listing + blob SHA compare
cho cả 2 files (tài liệu phải byte-identical với SHA256 ở trên).
