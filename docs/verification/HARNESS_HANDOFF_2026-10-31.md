# Kiểm tra gói harness bàn giao — 31/10/2026

Phạm vi: đóng gói và hướng dẫn tích hợp, không sửa runtime/guard/scorer/simulator/config/split. 23 file runtime trong `harness_manifest.json` trùng source `ddbe0a0b18a6fb9f6e7d261628a51e7a2c6c10c6`.

## Kết quả đã chạy

- Build wheel `zaic_lifemate_harness-0.1.0-py3-none-any.whl`, 261.843 byte.
- Wheel chỉ chứa 23 file runtime/config/split và metadata. Đối chiếu SHA256 từng file với manifest khớp. Không có Requires-Dist, tests, research, notebook, data, audio hay weights.
- Cài wheel bằng `--no-deps --no-compile --target` vào thư mục artifacts riêng, không đổi môi trường model.
- Chạy bản đã cài bằng `python -S` (không site-packages): không Torch, không RapidFuzz; self-check read → observation → write → stop PASS; observer OFF/ON cùng prompts/calls/state, observer ON có records không lỗi. Đây là model/env giả lập.
- Bản đã cài + simulator thật: fake-run policy rỗng trên 3 dev IDs smoke; check-submission **3 dòng / 0 mismatch**. Chỉ chứng minh cài đặt và replay, không đo chất lượng model.
- `tests.test_r4_pending_ask` + `tests.test_shadow_export`: **34 test PASS, 0 fail/error/skip**. Log lỗi observer trong negative control là cố ý.
- Runtime source/config/split không đổi. Số CPU 849/paired 976 cũ giữ nguyên phạm vi/ngày của báo cáo cũ, không gọi là suite mới chạy lại.

## Các lệnh chính đã chạy

Từ repo:

```powershell
python -m build --wheel --no-isolation --outdir ..\artifacts\harness-handoff\wheels
python -m unittest tests.test_r4_pending_ask tests.test_shadow_export -q
git diff --check
git diff --stat ddbe0a0b18a6fb9f6e7d261628a51e7a2c6c10c6 -- lifemate
```

Từ thư mục dự án chứa `repo/` và `artifacts/`:

```powershell
python -m pip install --no-deps --no-compile --target artifacts/harness-handoff/installed artifacts/harness-handoff/wheels/zaic_lifemate_harness-0.1.0-py3-none-any.whl
```

Các kiểm tra Python riêng đã đọc manifest và wheel ZIP, kiểm tra không model dependencies, so từng hash, xác nhận import `lifemate` từ target đã cài. Process `python -S` thêm target đó vào sys.path và chạy `examples/integrate_checkpoint.py --self-check` bằng runpy; kiểm tra `find_spec('torch')` và `find_spec('rapidfuzz')` đều None.

Process khác `python -B -S` dùng target đã cài và `lifemate.run.main`:

```text
fake-run --data <DATA_ROOT> --split train --ids train_1446,train_1703,train_1453 --out <PRIVATE_ARTIFACT>/fake_submission.jsonl
check-submission --data <DATA_ROOT> --split train --submission <PRIVATE_ARTIFACT>/fake_submission.jsonl
```

Đã fetch origin, đọc status/diff runtime, lấy trạng thái/log Kaggle v2 và đối chiếu kết quả aggregate. Không khởi động thêm GPU hoặc chạy training.

## File bàn giao

Mới: `pyproject.toml`, `harness_manifest.json`, `examples/integrate_checkpoint.py`, `docs/INTEGRATION.md`, báo cáo này, `docs/verification/SMOKE20_2026-10-31.md`.

Cập nhật: `README.md`, `lifemate/README.md`, `.gitignore` (bỏ build/dist khỏi Git), `docs/STATUS.md`, `docs/REPOSITORY_MAP.md`.

Các thư mục lịch sử không bị xóa khỏi repo; chúng bị loại khỏi gói cài và có thể không checkout bằng sparse clone. Không nhập thư mục `kaggle/` untracked của công việc khác, không nhập artifacts hoặc raw model traces.

Giới hạn: chưa nạp checkpoint fine-tune của bạn, chưa xác minh native template/parser của checkpoint đó, chưa có training manifest để kiểm tra leakage; G&G vẫn shadow-only, không tuyên bố đã tăng điểm.
