# Ghép harness với checkpoint fine-tune

## 1. Đã có gì và còn thiếu gì?

**Đã có:** loop, adapter simulator chính thức, catalog theo installed apps, observation sau call, validator, chống lặp, grounding tùy chọn, G&G shadow log và exporter. Runtime main giống source Run 7; xem `harness_manifest.json`.

**Chưa làm thay bạn:** nạp checkpoint fine-tune, ASR, tokenizer/chat template của SFT, parser output theo format đã train, kiểm tra tương thích và đo chất lượng sau ghép. G&G không bảo đảm mọi call đúng; giá trị bịa nhưng đúng định dạng vẫn là lỗi mở. G&G chưa bật chặn thật.

## 2. Cài phần cần thiết

Python >=3.10. Trong môi trường đã chạy được checkpoint của bạn:

```bash
python -m pip install --no-deps .
python -c "import lifemate; print(lifemate.__file__)"
python examples/integrate_checkpoint.py --self-check
```

Gói `zaic-lifemate-harness` chỉ cài namespace `lifemate`, không có dependency model. Nếu đã có thư mục/package cùng tên `lifemate`, kiểm tra đường dẫn import để tránh chạy nhầm. `--self-check` dùng loop thật nhưng model/env giả lập trên CPU, không đo model hay simulator BTC.

Không cần requirements từ prototype cũ. Không upgrade Torch/vLLM theo notebook của repo này. Dùng nguyên môi trường checkpoint đã chạy được của bạn. RapidFuzz tùy chọn; không có thì runtime dùng difflib. Khi đối chứng, giữ nguyên và ghi lại backend fuzzy.

Cần data giải nén và **`zaic_tools` trong gói BTC**, không phải package cùng tên từ pip:

```text
DATA_ROOT/
  train/train.jsonl
  train/train_tools_catalog.json
  train/zaic_tools/
  train/train_environment/...
  public_test/public_test.jsonl
  public_test/public_test_tools_catalog.json
  public_test/zaic_tools/
  public_test/public_test_environment/...
```

Audio theo đường dẫn trong JSONL. `ZaicEnv` là cầu nối duy nhất tới simulator; không đọc state trực tiếp để đưa vào prompt.

## 3. Điểm nối model

```python
from lifemate.agent import AgentLoop
from lifemate.adapter import ZaicEnv
from lifemate.config import PipelineConfig
from lifemate.loader import load_catalog, load_split, catalog_tools_for_sample

catalog = load_catalog(DATA_ROOT, SPLIT)
sample = next(s for s in load_split(DATA_ROOT, SPLIT) if s.id == SAMPLE_ID)
sample.label = None                 # nhãn không phải input agent
tools = catalog_tools_for_sample(catalog, sample)
transcript = my_asr(DATA_ROOT / SPLIT / sample.audio)
for turn in sample.history:
    if turn.role == "user" and turn.audio and turn.audio_text is None:
        turn.audio_text = my_asr(DATA_ROOT / SPLIT / turn.audio)

cfg = PipelineConfig()             # flags OFF cho đối chứng đầu tiên
env = ZaicEnv(DATA_ROOT, SPLIT, sample.id)   # env mới MỖI mẫu
loop = AgentLoop(cfg, tools)                # loop mới MỖI mẫu
submission = loop.run(sample, transcript, env, my_generate)
```

`DATA_ROOT` là `pathlib.Path`; `my_asr`, `my_generate` do bạn cung cấp. Với train, history có transcript sẵn; public_test phải ASR user-history chưa có transcript. Khi so model, giữ nguyên chính sách history. Không dùng current gold transcript làm input ASR system; gold-current chỉ là arm chẩn đoán riêng.

Khai báo metadata checkpoint/revision và số tham số thực tế khi dùng config/check_budget. Default parameter counts không phải phép đo checkpoint của bạn.

**Hợp đồng callback:**

```python
def my_generate(prompt: str, tools: dict) -> dict | None:
    # Nạp model một lần ngoài callback. Render đúng template đã train.
    # tools: mapping tên -> spec BTC, không phải OpenAI functions list.
    raw = my_backend_generate(prompt, tools)
    return my_checkpoint_parser(raw)

# Một bước gọi tool:
{"name": "contacts.search", "arguments": {"query": "Lan"}}
# Kết thúc: None hoặc {"stop": True}
```

Callback **chỉ đề xuất**, không gọi tool, không đọc env và không lọc call đã thực thi. Mỗi callback trả một call. Nếu checkpoint xuất `<tool_call>...`, prose hay nhiều call, bridge/parser phải xử lý theo contract đã train và kiểm tra riêng; không chọn call đầu rồi bỏ phần còn lại. Không coi sai parser là stop sạch.

Prompt là chuỗi text do `AgentLoop` dựng: context/history/transcript và observation trước đó. Nó không xuất sẵn native system/assistant/tool messages của format SFT khác. Nếu checkpoint đòi cấu trúc đó, cần bridge riêng; `lifemate/llm.py` cũ không giải quyết việc này. Tokenizer của bạn phải kiểm tra prompt render + output reserve vừa context; chars/4 trong loop không phải token guard chính xác.

## 4. Ghép chạy được rồi mới bật từng thành phần

| Cấu hình | Tác dụng |
|---|---|
| Các flag mặc định OFF | Đối chứng parser/model/env trước |
| `shadow_observer=True` | G&G ghi log, không đổi call; phải kiểm tra lỗi trong records |
| `grounding=True` | Có thể sửa số/ngày/contact hoặc chuyển proposal thiếu thông tin thành ask; đo riêng |
| `pending_ask_stop=True` | Ask thực thi thành công kết thúc lượt ngay; variant, không tự bật |
| `history_presentation_v2=True` | Đổi trình bày history; giữ OFF khi ghép đầu tiên |

Đọc `loop.observer.records` **ngay sau** `run()`, copy và lưu JSONL riêng. Không dùng `.log`. Submission chỉ gồm `id`, `tool_calls`, `state_hash` lấy nguyên từ env; không thêm diagnostics, không xóa read/ask/call lỗi đã thực thi. `lifemate.shadow_export` có schema log chuẩn.

Chạy 3–20 mẫu dev trước, so observer OFF/ON trên cùng transcript, output model và seed. Calls/state phải khớp; observer phải có records không lỗi. Sau đó mới A/B grounding, ask-stop hoặc prompt. Không mở held-out để dò lỗi.

## 5. Gửi lại gì sau khi ghép?

- SHA harness (hoặc hash manifest), checkpoint/revision/tokenizer, số tham số thực tế và config.
- Sample IDs/split, cách tạo current/history transcript, seed/decoding/backend.
- Raw output + parsed call + observation + toàn bộ submitted calls + state_hash + lỗi và thời gian.
- Training manifest để kiểm tra checkpoint đã thấy mẫu đánh giá chưa. Split của repo này không tự chứng minh dữ liệu unseen đối với model bên bạn.

Chưa có các artifact này thì chỉ kết luận “ghép chạy được”, chưa kết luận “tăng điểm”. Scorer cục bộ là proxy, không phải evaluator BTC.

## 6. Không cần copy phần nào?

Wheel chỉ có `lifemate` cùng JSON config/split. Có thể copy nguyên `lifemate/` (trừ cache/tests) thay pip. Ví dụ callback không tự nạp checkpoint. Research, analysis, plans, deep-dives, Kaggle notebooks và các nhánh cũ không cần để import harness; giữ ngoài gói để tái lập lịch sử.

CLI `lifemate.run infer` là đường model gốc cũ, không tự nạp bộ fine-tune của bạn. PhoWhisper Transformers không tự dùng được với faster-whisper nếu chưa convert; dùng ASR đã chạy được của bạn qua callback.
