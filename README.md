# LifeMate harness — ghép ASR/LLM của nhóm

Repo cung cấp vòng gọi tool, adapter `zaic_tools`, grounding và G&G ghi log.
**Model ASR/LLM fine-tune do bên tích hợp tự nạp.** Không cần môi trường Kaggle hay backend model cũ của repo này để dùng harness.

## Bắt đầu

```bash
git clone --depth 1 --filter=blob:none --sparse https://github.com/lenamkhanhh/ZaloAIC.git
cd ZaloAIC
git sparse-checkout set lifemate examples docs
python -m pip install --no-deps .
python examples/integrate_checkpoint.py --self-check
```

Lệnh cài chỉ đóng gói `lifemate/` cùng config/split JSON. Không cài Torch, Transformers, vLLM, CUDA hay weights; không cài nghiên cứu, notebook hoặc tests. Dùng môi trường model hiện có của bạn.

1. **[Hướng dẫn tích hợp](docs/INTEGRATION.md)**: cài gì, callback model, dữ liệu và kiểm tra.
2. **[Ví dụ chạy một mẫu](examples/integrate_checkpoint.py)**, hoặc gọi thẳng `AgentLoop.run`.
3. **[Manifest source](harness_manifest.json)**: hash từng file runtime; lưu SHA checkpoint/config của bạn riêng.

## Trạng thái trước khi ghép

- `main` **đã chứa source Run 7** (`ddbe0a0b18a6fb9f6e7d261628a51e7a2c6c10c6`); không cần tìm các nhánh sửa cũ.
- G&G **shadow-only**: ghi quyết định, chưa chặn tool. Grounding là cơ chế khác, có thể sửa proposal nếu bật.
- `grounding`, `shadow_observer`, `history_presentation_v2`, `pending_ask_stop` mặc định False. Không tự bật khi đổi checkpoint.
- Harness nhận **một dict tool call mỗi bước**. Checkpoint sinh native tool tags/nhiều call/messages khác cần bridge ở backend của bạn; parser JSON cũ không tự tương thích SFT.
- CPU đã có kiểm tra; GPU smoke 20 mẫu với **model gốc** đã COMPLETE, nối tiếp/gom nhóm khớp. Điểm chẩn đoán chỉ **0,05**; chưa chứng minh chất lượng với checkpoint fine-tune của bạn.

[Kết quả gói cài](docs/verification/HARNESS_HANDOFF_2026-10-31.md) · [Smoke GPU 20 mẫu](docs/verification/SMOKE20_2026-10-31.md).

## Không cần mang sang repo model

`analysis/`, `research/`, `plans/`, `deep-dives/`, `competition/`, notebook Kaggle và lịch sử nhánh không phải dependency. Chúng giữ để đối chiếu và **không nằm trong wheel**.

Không muốn dùng pip: copy nguyên `lifemate/` (trừ `__pycache__` và `lifemate/tests`). Không copy từng module G&G rời vì chúng phụ thuộc nhau.

Lịch sử: [trạng thái/lỗi mở](docs/STATUS.md), [bản đồ repo](docs/REPOSITORY_MAP.md), [nhánh](docs/BRANCHES.md), [CLI model gốc cũ](RUN_LIFEMATE.md). Đường tích hợp hiện tại là `docs/INTEGRATION.md`.
