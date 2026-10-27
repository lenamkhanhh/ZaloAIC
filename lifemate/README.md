# lifemate/ — Pipeline LifeMate chạy được

Đọc **`../RUN_LIFEMATE.md`** trước — đó là tài liệu tự chứa (cấu hình,
cách lấy data, lệnh chạy, phần đã/chưa chạy). File này chỉ là chỉ mục.

- `config.py` + `configs/` — cấu hình chính (`recommended.json`) và
  mốc tối giản (`baseline.json`).
- `loader.py`, `split.py` — loader theo schema thật v3.2.0, split
  dev/held-out cố định (`splits/train_dev_heldout.json`).
- `adapter.py` — cầu nối duy nhất tới zaic_tools (không đọc state.json).
- `agent.py` — loop: observation sau mọi call, validator trước call, guard.
- `grounding.py` — grounding theo loại slot (candidate ≠ intent).
- `asr.py`, `llm.py` — backend lazy (faster-whisper / vLLM /
  transformers) + test double. Không GPU thì `infer` fail fast.
- `scoring.py` — scorer theo mô tả portal, KHÔNG phải evaluator chính thức.
- `run.py` — CLI: replay-gold / fake-run / check-submission / score /
  make-split / infer.
- `tests/` — 13 test, skip khi chưa có data (biến `LIFEMATE_DATA`).
