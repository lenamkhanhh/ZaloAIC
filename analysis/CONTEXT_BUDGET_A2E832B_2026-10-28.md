# Prompt thực tế của agent mới a2e832b: có vượt ngân sách 16.384 token không?

Ngày: 2026-10-28. Đo riêng phiên bản mới, KHÔNG ghép số liệu với phép đo
đối chứng e79f9722 (phép đo cũ vẫn giữ nguyên tại
`CONTEXT_BUDGET_2026-10-28.md`, không bị ghi đè hay bỏ đi).

## 0. Trả lời trước (ưu tiên)

- **Bản mới a2e832b: KHÔNG có mẫu nào và KHÔNG có bước nào vượt ngân sách
  16.384 token** trên gold replay của 1.237 mẫu dev (dự phòng 512 output
  token đã tính trong ngưỡng: prompt + 512 ≤ 16.384).
- **Max: 9.874 token** (mẫu train_1636, 2 call) → cộng 512 output = 10.386,
  còn headroom 5.998 token.
- **Danh sách ID vượt ngân sách: không có ID nào.**
- Vì bản mới đã vừa ngân sách trên gold replay, **chưa cần thiết kế renderer
  phức tạp hơn**. Xem §4 về giới hạn trước khi kết luận rộng hơn.

## 1. Đo cái gì — prompt thực tế của a2e832b, không phải giả lập

- Code đo theo: nhánh **`codex/lifemate-baseline-integration`**, commit
  **`a2e832b9bdbef63d6d7b5d1573a8d303a48f2664`** (2026-10-28 00:45:43
  +0700, "docs: record agent evidence policy, compatibility audit and
  unvalidated model behavior"). Đo bằng chính code nhánh này
  (`lifemate/agent.py` + `lifemate/adapter.py`), không dùng implementation
  main hay implementation cũ để giả lập.
- Renderer của bản mới **vốn đã là JSON compact đầy đủ**
  (`json.dumps(result, ensure_ascii=False, separators=(",", ":"))`) — đúng
  đề xuất tối thiểu từ phép đo e79f9722. Phép đo này vì vậy đo prompt thật
  của agent mới, không phải một renderer giả định gắn thêm.
- Những gì mới trong prompt của a2e832b (chỉ phần ảnh hưởng prompt):
  - `ACTION_POLICY` (6 điểm + dòng kết) chèn sau dòng instruction trong
    base prompt — tốn **455 token** đo độc lập.
  - Dòng instruction đổi đuôi thành "...or explicit user input."
  - Outcome observation: `"not_done"` khi `ok:true` nhưng `done:false`
    (thay vì ghi `ok`), còn lại giữ nguyên.
  - Config suffix (selective reads, no-verification-read) và cách wrap
    chat template **không đổi**: 1 user message, chat template của model,
    `add_generation_prompt=True`, `encode(add_special_tokens=False)`.
  - Grounding/evidence, ask early-return, stop-signal: ảnh hưởng validation
    và kết thúc trace, không ảnh hưởng text prompt của prefix gold replay
    nên không xuất hiện trong số đo này.
- Tokenizer/revision/ngưỡng giữ nguyên như phép đo đối chứng:
  Qwen/Qwen3-4B-Instruct-2507 rev `cdbee75` (chỉ tokenizer, không tải
  weights, không chạy LLM/GPU), 1.237 mẫu dev, held-out không đụng tới,
  transcript train chuẩn.

## 2. Kết quả riêng của a2e832b (bảng này chỉ chứa số của bản mới)

| | a2e832b (JSON đầy đủ + action policy) |
|---|---|
| Per-sample max, p50 | 5.555 |
| Per-sample max, p90 | 7.719 |
| Per-sample max, p99 | 9.037 |
| Per-sample max, max | 9.874 (train_1636, 2 call) |
| Per-step (4.080 prompt), p50 | 5.754 |
| Per-step, p90 | 7.833 |
| Per-step, p99 | 9.204 |
| Per-step, max | 9.874 |
| Mẫu vượt ngân sách (prompt + 512 > 16.384) | **0 / 1.237** |
| Bước vượt ngân sách | **0 / 4.080** |
| ID vượt ngân sách | **không có** |

Top max (để đối chiếu, không phải danh sách vượt): train_1636 9.874,
train_0134 9.844, train_0204 9.688, train_0156 9.612, train_0261 9.602,
train_0398 9.534, train_0256 9.470, train_1725 9.452, train_0236 9.391,
train_0203 9.338.

Token đến từ đâu (trung bình, prompt cuối): instruction + policy +
context 947, catalog 3.899, history 448 (header + các turn, không gồm
request), request 37, dòng config 32, observation section 294 (max
1.289). Catalog vẫn chiếm phần lớn prompt; action policy tốn 455 token
độc lập, observation vẫn chỉ là phần nhỏ.

Sửa 2026-10-28 (chỉ bảng breakdown, không đổi phép đo token toàn prompt):
cùng lỗi tách đoạn như bản đối chứng — `base_lines[-1]` không phải
request mà là dòng config verify, còn request và dòng selective nằm
trong đoạn history cũ (bảng cũ ghi history 501 / request 17 / config 33).
Cách tách mới neo theo dòng request, phân hoạch tái tạo đúng base trên
toàn bộ 1.237 mẫu (kiểm chứng 0 lệch); số token toàn prompt trong §2 giữ
nguyên vì text prompt không hề thay đổi. Script
`measure_context_budget_a2e832b.py` đã sửa theo cách tách mới.

## 3. Đối chứng e79f9722 — bảng riêng, không ghép

Phép đo đối chứng (agent cũ e79f9722 + renderer JSON đầy đủ gắn thêm,
cùng tokenizer/revision/dev/ngưỡng) đã báo cáo đầy đủ tại
`CONTEXT_BUDGET_2026-10-28.md`, tóm tắt riêng ở đây để tiện đối chiếu,
không gộp chung thành một bộ số:

| | e79f9722 + JSON đầy đủ (đối chứng) |
|---|---|
| Per-sample max, p50 / p90 / p99 / max | 5.096 / 7.260 / 8.578 / 9.415 |
| Per-step, p50 / p90 / p99 / max | 5.295 / 7.374 / 8.745 / 9.415 |
| Mẫu / bước vượt ngân sách | 0 / 1.237 ; 0 / 4.080 |

Hai bảng là hai phép đo độc lập trên hai commit khác nhau. Mức tăng từ
bảng đối chứng sang bảng mới (~459 token ở mẫu max) khớp với chi phí của
ACTION_POLICY (455 token) cộng hiệu ứng biên — tức bản mới đắt hơn chủ
yếu vì policy, không phải vì renderer JSON (renderer này đã có trong cả
hai phép đo).

## 4. Kết luận và giới hạn — đọc kỹ trước khi áp dụng rộng

- **Kết luận:** trên gold replay dev, prompt thật của a2e832b vừa ngân
  sách với headroom xấu nhất 5.998 token. Chưa cần thiết kế renderer phức
  tạp hơn (không cần cắt, tóm tắt hay phân tầng observation) cho phạm vi
  này. Guard raise khi vượt ngân sách trong `llm.py` vẫn giữ nguyên làm
  lưới an toàn, không cắt lén.
- **Giới hạn 1 — chưa bao phủ observation do model gọi sai hoặc lặp.**
  Gold replay chỉ tạo prefix từ call đúng của gold. Trace thật có thể gọi
  sai tool, gọi lặp, hoặc gọi nhiều read không cần thiết, tạo ra
  observation dài hơn/nhiều hơn bất kỳ gold trace nào — và vì vậy có thể
  vượt ngân sách dù gold replay không vượt. Chặn cấu trúc đã tính ở phép
  đo trước (base lớn nhất + 12 × observation JSON lớn nhất) vẫn vượt
  ngưỡng; đó là trường hợp guard phải nổ, không phải trường hợp renderer
  phải tự cắt.
- **Giới hạn 2 — transcript train chuẩn là ước lượng chẩn đoán**, không
  phải prompt ASR thực tế (ASR sai làm transcript khác độ dài/nội dung).
- **Giới hạn 3 — public_test khác dev** (không transcript, tập app khác);
  số dev không chuyển nguyên sang public.
- **Không thay đổi:** không sửa inference, không đổi model, không chạy
  GPU, không dùng held-out trong phép đo này.

## 5. Tái lập

Script: `analysis/measure_context_budget_a2e832b.py` (port trung thực của
prompt builder a2e832b; đã kiểm chứng khớp byte-identical với code nhánh
trên 30 mẫu cho base prompt và mọi prefix observation). Chạy:

```
python analysis/measure_context_budget_a2e832b.py --data-root <thư-mục-extracted>
```

Chỉ tải tokenizer, không tải weights, không chạy model, không cần GPU.
Output là bảng tổng hợp JSON (chỉ số đếm và id mẫu, không chứa prompt,
trace hay raw data). Dữ liệu không nằm trong repo; người chạy tự chỉ
`--data-root` tới bản package đã tải và kiểm chứng SHA256.
