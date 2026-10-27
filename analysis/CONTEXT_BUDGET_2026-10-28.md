# Observation + context budget: đo bằng tokenizer thật, đề xuất tối thiểu

Ngày: 2026-10-28. Nhánh phân tích độc lập, không chờ kết quả paired Kaggle.
Không sửa inference, không đổi model, không chạy GPU, không dùng held-out.

## 1. Nguồn đo — ghi chính xác, không giả lập bằng implementation khác

- Code agent đo theo: nhánh **`codex/lifemate-baseline-integration`**, commit
  **`e79f972206e26282e7ebddb2c5eda095d44dcf7c`** (2026-10-28 00:22:41 +0700).
  - `lifemate/agent.py`: `build_base_prompt` + `render_observation_prompt`
    (renderer hiện tại: `output = repr(result)`; nếu dài hơn 300 ký tự thì
    `output[:300] + "..."`), và 2 dòng config từ `recommended.json`
    (selective_reads, no-verification-read).
  - `lifemate/llm.py` `_render`: 1 user message duy nhất, chat template của
    model, `add_generation_prompt=True`, `encode(add_special_tokens=False)`;
    kiểm tra `prompt + 512 > 16384` thì raise (không cắt lén).
  - `lifemate/loader.py` `catalog_tools_for_sample`: chỉ tool của các app đã
    cài trong sample + `sys.ask_missing_info`, không bao giờ đưa full catalog.
- Tokenizer: **Qwen/Qwen3-4B-Instruct-2507, revision `cdbee75`** (chỉ tokenizer,
  không tải weights, không chạy LLM). Template render kiểm chứng:
  `<|im_start|>user\n{prompt}<|im_end|>\n<|im_start|>assistant\n`.
- Dữ liệu: **1.237 mẫu dev** từ `lifemate/splits/train_dev_heldout.json`
  (held-out 308 mẫu không được đụng tới). Gold replay chỉ để tạo các
  observation prefix hợp lệ: tại mỗi bước chỉ dùng thông tin đã xuất hiện
  trước bước đó; renderer không bao giờ nhìn đáp án gold.
- **Cảnh báo đọc số:** transcript dùng để đo là **transcript train chuẩn**
  (`audio_text`). Đây là **ước lượng chẩn đoán, không phải số đo prompt ASR
  thực tế** — ASR sai sẽ làm transcript dài/ngắn và khác nội dung.

## 2. Kết quả đo token (prompt + 512 output ≤ 16.384)

Ba renderer so sánh, cùng định dạng dòng, chỉ khác cách render `output=`:

- (a) hiện tại: `repr(result)[:300] + "..."`.
- (b) JSON compact đầy đủ: `json.dumps(result, ensure_ascii=False,
  separators=(",", ":"))`, không cắt.
- (c) phương án có ngân sách do phân tích này đề xuất: **đồng nhất với (b)**.
  Lý do ở §4 — JSON đầy đủ đã vừa ngân sách trên toàn bộ dev nên không cần
  cơ chế phức tạp hơn. Bảng dưới ghi (c) = (b) theo đúng nghĩa đó, không phải
  thiếu số liệu.

### Token prompt (tokenizer thật, đã gồm template)

| | (a) repr[:300] | (b) JSON đầy đủ | (c) đề xuất (= b) |
|---|---|---|---|
| Per-sample max, p50 | 5.054 | 5.096 | 5.096 |
| Per-sample max, p90 | 7.205 | 7.260 | 7.260 |
| Per-sample max, p99 | 8.602 | 8.578 | 8.578 |
| Per-sample max, max | 9.416 | 9.415 | 9.415 |
| Per-step (4.080 prompt), p50 | 5.252 | 5.295 | 5.295 |
| Per-step, p90 | 7.341 | 7.374 | 7.374 |
| Per-step, p99 | 8.751 | 8.745 | 8.745 |
| Per-step, max | 9.416 | 9.415 | 9.415 |
| Mẫu vượt ngân sách | **0 / 1.237** | **0 / 1.237** | **0 / 1.237** |
| Bước vượt ngân sách | **0 / 4.080** | **0 / 4.080** | **0 / 4.080** |

Chênh lệch (b) − (a) ở prompt cuối: trung vị **−5 token**, p90 +204, max +730,
trung bình +34 token. JSON compact thường NGẮN hơn repr (repr thêm khoảng
trắng và quote đơn) — trực giác "đầy đủ thì đắt" là sai ở đây. Headroom xấu
nhất còn lại: 15.872 − 9.415 = **6.457 token**.

### Token đến từ đâu (trung bình, prompt cuối, đo từng đoạn độc lập)

| Đoạn | Token |
|---|---|
| Instruction + context | 488 |
| Catalog (tool của riêng sample) | 3.899 (~75%) |
| History | 501 |
| Request hiện tại | 17 |
| Dòng config | 33 |
| Observation (a) / (b) | 260 / 295 |

Tổng các đoạn ≈ tổng prompt thực (chênh ~25 token là overhead template +
hiệu ứng biên BPE). **Kết luận ngân sách: catalog mới là thứ tốn ngân sách,
không phải observation (chỉ ~5–6%).** Nếu sau này ngân sách bị siết, đòn bẩy
là lọc catalog, không bao giờ là cắt observation.

### Observation nào bị cắt bởi [:300] hiện tại

- 747 / 2.843 observation (26,3%) dài hơn 300 ký tự; 614 / 1.237 mẫu có ít
  nhất 1 observation bị cắt. Độ dài repr của các observation bị cắt: p50 495,
  p90 1.303, max 2.439 ký tự.
- Key cấp cao bị mất hoàn toàn (lần xuất hiện đầu tiên đã nằm ngoài 300 ký
  tự): `members` 19, `stations` 16, `playlists` 8, `alert_threshold_kwh` 6,
  `channels` 5. Phần bị lược dưới (a) là **đuôi repr**: các item cuối list và
  các field về sau — mô tả đầy đủ ở §3, không có ngoại lệ nào được giấu.

## 3. Kiểm tra bảo toàn thông tin (không chỉ ID/tên)

### M1 — giá trị mà bước sau thực sự dùng (từ gold trace, chẩn đoán)

1.168 giá trị đối số ở bước sau bắt nguồn từ observation trước đó (khớp leaf
chính xác). Cách đếm thận trọng: chỉ tính là "còn" nếu giá trị xuất hiện
trong dòng render của chính observation chứa nó (giá trị vô tình xuất hiện
lại ở observation khác không được tính là còn).

| Loại field | Tổng | Mất dưới (a) | Mất dưới (b)/(c) |
|---|---|---|---|
| id | 800 | 205 | 0 |
| other (power on/off, brightness, locked, assignee, …) | 231 | 76 | 0 |
| amount | 50 | 20 | 0 |
| time | 32 | 6 | 0 |
| location | 29 | 1 | 0 |
| phone | 14 | 4 | 0 |
| content | 12 | 0 | 0 |
| enum | 0 (không có giá trị enum nào bắt nguồn từ observation trong gold dev) | — | — |
| **Tổng** | **1.168** | **312 (26,7%)** | **0** |

Ví dụ mất mát quyết định dưới (a): amount `845000` (train_0003, đã biết từ
báo cáo truncation), `light_bedroom2` / `light_office` / `light_kitchen` /
`ac_bedroom` lặp lại hàng loạt, các amount 146.000–855.000, phone, và các
`end` dạng `2026-11-25T11:00:00+07:00`. Nhóm quyết định (id + amount + time +
phone) chiếm 235 / 312 giá trị mất.

### M2 — toàn bộ leaf scalar của observation ở prompt cuối

31.158 leaf scalar. Dưới (a) mất 11.913 (38,2%) theo đếm thô; trong đó 4.463
là artifact đo (leaf boolean lưu dạng JSON `true/false` nhưng repr viết
`True/False`, nên kiểm tra chuỗi thô báo mất oan). Sau khi loại leaf
boolean: 26.695 leaf, **mất 7.450 (27,9%) dưới (a), 0 mất thật dưới (b)/(c)**.
5 "mất" còn lại dưới (b) đều là artifact escape JSON: content chứa ký tự
xuống dòng thật (đã kiểm chứng từng case: train_0883, 1057, 1174, 1557,
1687) — giá trị vẫn nằm trong JSON dưới dạng `\n`, không hề mất.

Theo key (mất dưới (a) / (b)): `id` 1.435/0, `name` 1.076/0, `room` 485/0,
`type` 375/0, `amount` 129/0, `phone` 93/0, `relation` 87/0, `location`
171/0, `content` 50/5-artifact, `mode` (dạng enum) 23/0. Riêng `balance`:
245/245 còn nguyên dưới cả hai renderer (kết quả get_balance nhỏ, không
bao giờ vượt 300 ký tự) — balance không phải là vấn đề, id/amount/phone/
relation mới là vấn đề.

### Relation — trường hợp phân biệt cần đối chiếu

6 mẫu exemplar trong EMPTY_VS_ASK (0025, 0069 hỏi; 0509, 0751, 0776, 1015
tiếp tục) đều có kết quả `contacts.search` ngắn hơn 300 ký tự nên relation
còn nguyên dưới cả hai renderer. Rủi ro relation thật nằm ở trường hợp
tổng quát: list nhiều contact dài hơn 300 ký tự — M2 đo được 87 relation
mất dưới (a), 0 dưới (b). Nói cách khác: exemplar không chứng minh (a) an
toàn; đo toàn dev mới thấy chỗ vỡ.

### Không dùng FREE_TEXT_KEYS làm danh sách xoá — tuân thủ

Renderer (b)/(c) giữ **mọi field của mọi kết quả**, không rút gọn list còn
ID/tên, không xoá field vì thuộc FREE_TEXT_KEYS. Mọi phần bị lược dưới (a)
đã mô tả ở trên; dưới (b)/(c) không có phần nào bị lược (trừ escape JSON
chuẩn, không phải lược nội dung).

## 4. Đề xuất triển khai tối thiểu (cho Codex)

Vì JSON compact đầy đủ đã vừa ngân sách trên toàn bộ dev (0/4.080 bước
vượt, headroom xấu nhất 6.457 token), **ưu tiên phương án đơn giản nhất**:

1. Trong `lifemate/agent.py`, hàm `render_observation_prompt`, thay:
   ```python
   output = repr(result)
   if len(output) > 300:
       output = output[:300] + "..."
   ```
   bằng:
   ```python
   output = json.dumps(result, ensure_ascii=False, separators=(",", ":"))
   ```
   (`json` đã được import trong file.) Giữ nguyên định dạng dòng, header,
   và mọi thứ khác. Không thêm cơ chế ngân sách nào khác.
2. Giữ nguyên guard ngân sách trong `lifemate/llm.py` `_render` (raise khi
   prompt + 512 > 16.384). Không thêm fallback cắt lén ở bất kỳ đâu.

## 5. Rủi ro còn lại (chưa giải quyết, không giấu)

- **Observation do model gọi sai/lặp có thể khác gold replay.** Gold trace
  tối đa 6 call; một trace 12 bước (max_steps) với observation cực đại sẽ
  vượt ngân sách theo chặn cấu trúc: base lớn nhất 8.849 + 12 × observation
  JSON lớn nhất 812 = 18.593 > 15.872. Chặn thực tế theo dev (≤6 call):
  8.849 + 6 × 812 = 13.721 < 15.872, vẫn vừa. Nếu guard nổ ở đường submission,
  code hiện tại **raise thay vì nộp** — Codex cần quyết riêng (gợi ý: dừng
  trace as-is và nộp) — phân tích này KHÔNG đổi hành vi đó.
- **Prompt ASR thật khác ước lượng chẩn đoán** (transcript sai, dài/ngắn
  khác). Số đo trên dùng transcript train chuẩn.
- **public_test khác dev** (không có transcript, tập app khác) — số dev
  không chuyển nguyên sang public.
- 2 mẫu gold có call lặp y hệt (train_0922, train_1447): vòng lặp thật sẽ
  replan ở đó, nhưng prefix đo vẫn hợp lệ cho mục đích đo.
- Đoạn catalog chiếm ~75% prompt: nếu model/backend khác có context nhỏ hơn
  hoặc catalog phình ra, thứ vỡ đầu tiên là catalog, không phải observation.

## 6. Tái lập

Script: `analysis/measure_context_budget.py` (port trung thực của prompt
builder nhánh trên; đã kiểm chứng khớp byte-identical với code nhánh trên
30 mẫu cho base prompt và renderer (a), cấu trúc (b) khớp). Chạy:

```
python analysis/measure_context_budget.py --data-root <thư-mục-extracted>
```

Chỉ tải tokenizer, không tải weights, không chạy model, không cần GPU.
Output là bảng tổng hợp dạng JSON (chỉ số đếm và id mẫu, không chứa prompt,
trace hay raw data). Dữ liệu không nằm trong repo; người chạy tự chỉ
`--data-root` tới bản package đã tải và kiểm chứng SHA256.
