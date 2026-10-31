# Runtime LifeMate

Ghép checkpoint của nhóm: **[docs/INTEGRATION.md](../docs/INTEGRATION.md)** và [ví dụ callback](../examples/integrate_checkpoint.py).

- `agent.py`: proposal → grounding (nếu bật) → validate → tool call → observation.
- `adapter.py`: dùng `zaic_tools` chính thức; env mới cho mỗi mẫu.
- `loader.py`: sample/context/history và catalog của đúng mẫu.
- `config.py`: flag runtime, không tự bật variant.
- `lifemate_grounding.py`: chuẩn hóa, có thể thay proposal khi bật grounding.
- `lifemate_observer.py`, `lifemate_gates_adapter.py`, các module evidence/provenance/callback: G&G **chỉ ghi log**, chưa chặn thật.
- `shadow_export.py`: schema/export log riêng, không thêm vào submission.
- `scoring.py`, `split.py`: kiểm tra cục bộ, không phải evaluator BTC.
- `asr.py`, `llm.py`, `run.py`: backend/CLI model gốc cũ, không bắt buộc khi tự nạp model. Parser cũ chưa mặc nhiên tương thích format SFT khác.

Raw data, simulator và weights không được đóng gói. `tests/` không nằm trong wheel.
