# Chuyên đề 1 — Constrained Decoding & Schema Enforcement Offline cho LifeMate

> Code đi kèm: [01-constrained-decoding-lifemate.py](01-constrained-decoding-lifemate.py)
> (647 dòng, type hints, docstring, import được mà không cần GPU; chỉ
> `build_engine` và `ToolAgent.generate_tool_call` mới cần vLLM + GPU).
> Tài liệu này tổng hợp từ bản nháp nghiên cứu ngày 2026-10-27; các số
> latency dưới đây **không phải số đo trên A30 hay trên dữ liệu ZAIC**,
> trừ khi ghi rõ. Xem cuối báo cáo: phần đã xác minh / giả định / cần đo.

## 0. Khuyến nghị chính

**Dùng XGrammar qua vLLM làm mặc định; Outlines là dự phòng số 1
(đổi bằng một flag); Guidance chỉ cân nhắc sau khi pin phiên bản và
giải quyết mâu thuẫn licence; Instructor loại khỏi lớp constrained
decoding.** Constrained decoding chỉ giải quyết "parse được + đúng
shape"; đúng tool, đúng tham số, đúng thứ tự, đúng trạng thái cuối vẫn
phải do validator code, selective read và loop guard đảm nhiệm.

## 1. Bối cảnh và ràng buộc cứng — và một lỗi nền đã sửa

- LifeMate: audio tiếng Việt → agent gọi tool trong app mô phỏng qua
  `zaic_tools`, đầu ra là `tool_calls` + `state_hash`; `state_hash` sai
  = 0 điểm cho mẫu đó, đúng mới tính tool-call F1. Chạy offline trên
  1× NVIDIA A30, tối đa 30 giây/mẫu, context ≤ 16K, nộp bằng Docker
  offline. Xem [../competition/lifemate.md](../competition/lifemate.md),
  [../competition/metrics-submission.md](../competition/metrics-submission.md).
- **LLM của chuyên đề này là Qwen3-4B-Instruct-2507 (4,0B tổng /
  3,6B không tính embedding, Apache 2.0, series tháng 7/2025, trước mốc
  26/10/2026). Qwen2.5-Coder-7B-Instruct (7,61B) KHÔNG phải LLM cho
  LifeMate** — nó vượt trần LLM < 5B, dù là lựa chọn hợp lý cho
  DataMate (trần 15B). Mọi tính toán ngân sách dưới đây dùng 4,0B:
  + PhoWhisper-small 0,244B → hệ thống 4,244B; + medium 0,769B → 4,769B.
  Đây là điểm đã sửa so với bản yêu cầu gốc vốn liệt kê cả hai model
  cho LifeMate; xem thêm shortlist trong
  [../research/comparison.md](../research/comparison.md).

## 2. Constrained decoding bảo đảm / không bảo đảm điều gì

Constrained decoding (guided decoding / structured output) không phải
là "dặn model trả JSON trong prompt". Ở mỗi bước sinh token, engine áp
một mặt nạ (mask) lên phân phối token: chỉ những token giữ cho đầu ra
vẫn nằm trên một đường đi hợp lệ của schema/grammar mới được lấy mẫu.
Kết quả là đầu ra **hợp lệ về mặt cú pháp theo construction**, không cần
retry vì lỗi parse.

| Được bảo đảm (nếu schema và backend đúng) | KHÔNG được bảo đảm — vẫn phải xử lý bằng code |
|---|---|
| JSON parse được, đúng shape: đúng key, đúng kiểu cơ bản, đúng enum, đúng required | Chọn đúng tool cho intent của người dùng |
| Tên tool nằm trong enum lấy từ catalog | Tham số có đúng thực thể thật không (đúng contact/device/account, đúng số tiền/ngày) |
| Không sinh thêm key lạ (nếu schema đặt `additionalProperties: false`) | Thứ tự gọi có đúng dependency/precondition không |
| Không bị kẹt vì thiếu dấu `}` hay thừa dấu phẩy | Tác động lên trạng thái cuối có đúng không — `state_hash` vẫn có thể sai dù JSON đẹp |
| | Một số từ khóa JSON Schema nâng cao (`format`, `pattern`, một số range) có được backend nào cũng ép hay không — **không**: mức hỗ trợ khác nhau theo backend, nên validator bằng code sau sinh là bắt buộc |

Hệ quả thiết kế: **constrained decoding + validator bằng code + kiểm
tra precondition bằng tool read là ba lớp khác nhau, không lớp nào thay
được lớp còn lại.** Bỏ validator vì "đã có XGrammar" là lỗi phổ biến
nhất trong chuyên đề này.

## 3. So sánh Outlines, XGrammar (vLLM), Guidance, Instructor

### 3.1. Bảng so sánh

| Tiêu chí | XGrammar (qua vLLM) — khuyến nghị chính | Outlines (qua vLLM) | Guidance (qua vLLM, backend llguidance) | Instructor — không phải lựa chọn cho vLLM offline |
|---|---|---|---|---|
| Bản chất | Engine C++ biên dịch JSON Schema/regex/grammar thành token mask, tích hợp sẵn làm backend của vLLM | Thư viện structured generation độc lập, cũng là một backend của vLLM; hỗ trợ JSON Schema, regex, CFG (kể cả Lark) | Ngôn ngữ/paradigm điều khiển LLM: xen kẽ logic Python với sinh có ràng buộc (regex, choice, grammar, JSON) | Lớp patch trên client của provider (OpenAI/Anthropic/…) + Pydantic: dùng native structured output của provider, validate rồi retry khi lỗi |
| Tương thích vLLM | **Backend mặc định của vLLM** theo engine args hiện tại (`--guided-decoding-backend`, default `xgrammar`; các backend hợp lệ còn có `outlines`, `lm-format-enforcer`) | Là một backend vLLM hợp lệ, nhưng không phải mặc định | Là một backend trong hệ structured output mới của vLLM (tài liệu vLLM mới liệt kê `xgrammar`, `guidance`, `outlines`, `lm-format-enforcer` cho regex) — nhưng API đổi tên theo phiên bản vLLM, phải pin đúng một phiên bản và test lại | Không phải engine của vLLM. Nó sống ở tầng client gọi API tương thích OpenAI; với vLLM offline, phần "constrained" thực chất vẫn do backend của server vLLM làm, còn Instructor chỉ thêm validate + retry ở client |
| Chạy offline, không internet | Có, toàn bộ chạy trong Docker nếu weights và wheel đã đóng gói sẵn | Có, với cùng điều kiện đóng gói | Có, với cùng điều kiện đóng gói (cần kiểm tra backend llguidance có wheel sẵn cho kiến trúc CPU/GPU của máy chấm không) | Về nguyên tắc có thể trỏ vào server vLLM local, nhưng **không giải quyết bài toán constrained decoding của vLLM**, và mode retry của nó tốn thêm lượt sinh trong trần 30 giây/mẫu — không nên dùng làm lớp chính |
| Latency / overhead | Thấp nhất trong các số báo cáo: paper XGrammar báo mask < 40 µs/token cho JSON Schema và CFG (JSON), < 200 µs cho XML/Python DSL, trên Llama-3.1-8B + RTX 4090 + CPU Ryzen 9 7950X (*báo cáo bởi tác giả, không phải A30/Qwen3-4B*); TPOT batch 1 gần như không đổi: 6,2 → 6,3 ms (JSON Schema), batch 16: 9,0 → 9,2 ms (*báo cáo bởi tác giả*). Diễn đàn vLLM cũng ghi xgrammar có first-token latency và throughput tốt hơn outlines rõ rệt (*báo cáo bởi cộng đồng*) | Chậm hơn xgrammar/guidance về first-token latency và throughput theo cùng diễn đàn vLLM (*báo cáo bởi cộng đồng*); điểm mạnh là độ chín về tính năng (nhiều định dạng grammar, regex, JSON Schema) chứ không phải tốc độ. Chi phí biên dịch schema (compile-once, reuse-many) khiến nó kém hợp nếu mỗi sample lại đổi schema hoàn toàn | Được diễn đàn vLLM báo cáo là nhanh, cạnh tranh hoặc nhanh hơn xgrammar với JSON Schema nhờ thời gian biên dịch gần bằng 0 và mask generation hiệu quả (*báo cáo bởi cộng đồng*); một số tùy chọn (ví dụ `disable_additional_properties`) chỉ có ở guidance | Overhead gần như không đáng kể ở tầng client, nhưng **không đo được "overhead của constrained decoding"** vì nó không làm constrained decoding ở local engine — chi phí thực là số lần retry khi validate lỗi, có thể nhân latency lên nhiều lần trong trần 30 giây |
| Bộ nhớ | Nhỏ so với model: mask/automaton của một schema tool-call (vài chục tool, mỗi tool vài tham số) là mức KB–MB, không đáng kể so với weights 4B BF16 (~8 GB) và KV cache trên A30 24 GB. Con số chính xác phụ thuộc số tool và độ sâu schema — phải đo bằng profiler trên schema thật, không lấy số của bài này làm cam kết | Tương tự về bản chất (automaton/FSM), nhưng chi phí biên dịch và bộ nhớ trung gian trong quá trình compile có thể lớn hơn với schema phức tạp; đo lại trên schema thật | Nhỏ; llguidance được thiết kế để mask generation nhanh và nhẹ | Không thêm bộ nhớ GPU đáng kể (chạy ở client), nhưng không giúp gì cho GPU budget của engine |
| Hỗ trợ JSON Schema | Tốt cho trường hợp LifeMate: enum, int/number range, regex pattern (theo diễn đàn vLLM). Một số từ khóa nâng cao vẫn cần validator code kiểm tra lại | Rộng nhất trong nhóm (tỉ lệ lớn của JSON Schema spec + regex + CFG) | Rộng, và có một số tùy chọn riêng (ví dụ `disable_additional_properties`) | Kế thừa từ provider/backend bên dưới, không tự định nghĩa |
| Rủi ro riêng | Trên một số phần cứng, xgrammar có thể gây overhead do đồng bộ CPU–GPU (diễn đàn vLLM ghi nhận trường hợp RTX 4090 mà outlines nhanh hơn) — phải benchmark trên chính A30, không suy từ RTX 4090. Ngoài ra, xgrammar có thể fallback sang outlines với một số tính năng/kiến trúc chưa hỗ trợ — nên đặt `xgrammar:no-fallback` trong lúc test để phát hiện sớm, và chỉ nới lỏng khi đã biết schema nào gây fallback | Schema thay đổi theo từng sample (ví dụ catalog lọc theo `installed_apps`) làm mất lợi thế compile-once nếu compile lại từ đầu mỗi lần — giải pháp là cache schema theo fingerprint của catalog đã lọc (xem code mẫu) | API và tên backend thay đổi theo phiên bản vLLM (guided decoding cũ → structured outputs mới); tài liệu thứ cấp có thể lỗi thời nhanh. Chỉ dùng khi đã pin phiên bản và test trên chính phiên bản đó | Dùng Instructor làm lớp chính sẽ tạo ảo giác "đã có schema enforcement" trong khi engine vẫn sinh tự do rồi retry — đúng kiểu lỗi mà LifeMate không được phép mắc vì mỗi retry tốn thời gian và vẫn có thể trả về tool call sai trạng thái |
| Kết luận cho LifeMate | **Chọn làm mặc định.** Lý do: là backend mặc định của vLLM, nhanh nhất trong các số báo cáo, đủ cho schema tool-call, không thêm dependency ngoài vLLM | **Dự phòng số 1.** Dùng khi xgrammar fallback hoặc gặp từ khóa schema mà xgrammar chưa hỗ trợ; đổi backend bằng một flag, không đổi code agent | **Dự phòng số 2 / nghiên cứu thêm.** Chỉ cân nhắc khi cần điều khiển sinh ở mức field (interleave logic Python + generation) hoặc khi benchmark trên A30 cho thấy nó nhanh hơn xgrammar với schema thật | **Loại khỏi lớp constrained decoding.** Giữ lại (nếu muốn) chỉ ở vai trò validate + retry ở client cho các pipeline gọi API, không phải cho vLLM offline của LifeMate |

### 3.2. Tương thích với vLLM trên Ampere (A30)

- A30 là kiến trúc **Ampere**, 24 GB HBM2, băng thông 933 GB/s, BF16/FP16
  165 TFLOPS (330 TFLOPS với sparsity), PCIe Gen4. Đây là GPU được vLLM
  hỗ trợ chính thống qua CUDA — không có vấn đề kiến trúc đặc biệt nào
  như với một số backend chỉ tối ưu cho x86 hay cho GPU đời mới hơn.
  Rủi ro thực tế không nằm ở "Ampere có chạy được xgrammar không" mà ở:
  (a) wheel của xgrammar/llguidance có sẵn cho đúng phiên bản CUDA +
  Python trong Docker không, (b) schema thật có gây fallback không,
  (c) tổng thời gian (ASR + LLM + tool execution) có vượt 30 giây/mẫu
  không.
- Qwen3-4B BF16 nặng khoảng 8 GB (4,0B × 2 byte), cộng KV cache cho
  context ≤ 16K và activation — vừa thoải mái trong 24 GB nếu chỉ chạy
  một engine, không chạy đồng thời ASR lớn trên cùng GPU mà không tính
  toán. Công thức KV cache phụ thuộc số layer, hidden size, số KV head
  và dtype — **không lấy một con số KV cụ thể trong tài liệu này làm cam
  kết**; phải đo `gpu_memory_utilization` và peak memory trên chính A30
  với prompt dài nhất (catalog đầy đủ + history dài nhất) trước khi chốt
  `max_model_len = 16384`.
- **Chiến lược pin phiên bản (bắt buộc, vì API vLLM đã đổi tên):** các tài
  liệu thứ cấp ghi rằng từ vLLM 0.12, các trường `guided_*` cũ đã bị gỡ
  và thay bằng đối tượng `structured_outputs`/`StructuredOutputParams`.
  Code mẫu trong chuyên đề này therefore thử `StructuredOutputParams`
  trước, rồi `GuidedDecodingParams`, rồi `guided_json` cũ — nhưng **đây
  là shim tương thích, không phải giấy phép để không pin phiên bản**.
  Quy trình đúng: chọn một phiên bản vLLM duy nhất, build Docker một
  lần, chạy test schema thật trên A30, ghi phiên bản đó vào
  `requirements.txt`/`requirements.lock` và vào Dockerfile, và mang theo
  wheelhouse offline (không `pip install` lúc chạy chấm). Không ghi một
  số phiên bản cụ thể vào tài liệu này nếu chưa build thử, vì ghi số
  chưa build là bịa.

### 3.3. Licence — đã kiểm chứng tới đâu, còn mâu thuẫn ở đâu

| Thư viện | Licence ghi trong tài liệu này | Căn cứ / trạng thái xác minh |
|---|---|---|
| vLLM | Apache 2.0 | Tài liệu tổng hợp thứ cấp đã kiểm chứng (ghi vllm-project/vllm Apache-2.0, 2026-09-23) — **kiểm tra lại file LICENSE trong wheel đã pin trước khi đóng Docker** |
| XGrammar (mlc-ai/xgrammar) | Apache 2.0 | Nhiều nguồn thứ cấp thống nhất (EveryDev, bài tổng hợp đã kiểm chứng 2026-09-23) — kiểm tra lại LICENSE trong wheel đã pin |
| Outlines (dottxt-ai/outlines) | Apache 2.0 (open-source) | Nhiều nguồn thứ cấp thống nhất; lưu ý trang chủ của .txt đồng thời quảng bá "commercially-licensed libraries" của công ty — đó là sản phẩm thương mại khác, **không đồng nghĩa Outlines open-source đổi licence**; kiểm tra LICENSE của đúng phiên bản đã pin |
| Guidance (guidance-ai/guidance) | **MÂU THUẪN — chưa kết luận** | Trang GitHub của repo hiển thị "MIT License", trong khi bảng capability thứ cấp ghi "Apache-2.0". **Không chọn một trong hai để ghi vào báo cáo chính thức.** Trước khi đưa Guidance vào Docker, mở `LICENSE.md` trong đúng commit/checkout đã pin và ghi kết quả vào `sources.md` |
| Instructor (jxnl/instructor) | MIT | Trang PyPI của package ghi rõ "licensed under the terms of the MIT License" (nhiều phiên bản 0.3.x–0.6.x đều ghi vậy) |
| Pydantic (chỉ dùng nếu cần, code mẫu không bắt buộc) | MIT (thứ cấp) | Không phải dependency bắt buộc của code mẫu — validator trong code mẫu viết tay bằng stdlib để tránh thêm dependency |

**Quy tắc chung:** licence trong bảng này là điểm khởi đầu để kiểm tra,
không phải chứng nhận pháp lý. Với cuộc thi có giải tiền mặt, chỉ tin
file LICENSE trong đúng artifact đã đóng gói.

## 4. Thiết kế schema từ `tools_catalog.json`

Catalog thật của ZAIC có các trường như `kind` (read/write/meta),
`x-ref` (tham số phải là ID hợp lệ), `x-match` (fuzzy), `x-one-of`, và
chỉ được gọi tool của app trong `context.installed_apps`. JSON Schema
**không biểu diễn được** "ID này có tồn tại trong dữ liệu thật không"
hay "app này có được cài không" — hai kiểm tra đó thuộc về validator
bằng code và về việc lọc catalog trước khi sinh (xem code mẫu:
`filter_catalog_by_installed_apps` + `validate_tool_call` với
`allowed_refs`).

Schema cho một lần sinh nên là:

```json
{
  "type": "object",
  "oneOf": [
    {"type": "object",
     "properties": {"name": {"const": "contacts.search"},
                    "arguments": {"type": "object", "properties": {}, "required": []}},
     "required": ["name", "arguments"], "additionalProperties": false},
    "... một nhánh cho mỗi tool ..."
  ],
  "additionalProperties": false
}
```

- Dùng `oneOf` + `const` cho tên tool để ràng buộc arguments theo đúng
  tool đó, thay vì một schema chung với `arguments` là object tự do
  (schema chung sẽ cho phép arguments của tool A đi kèm tên tool B —
  đúng JSON nhưng sai ngữ nghĩa).
- **Fallback nếu backend từ chối `oneOf`:** dùng schema chung
  `{"name": {"enum": [...]}, "arguments": {"type": "object"}}` + validator
  code kiểm tra arguments theo tool. Khi đó constrained decoding chỉ còn
  bảo đảm parse được và tên tool hợp lệ, còn lại validator code gánh —
  phải ghi rõ fallback này trong log build, không được im lặng chấp nhận
  schema yếu hơn.
- Cache schema theo fingerprint (hash của catalog đã lọc + phiên bản
  schema builder) để tránh biên dịch lại mỗi sample. Catalog lọc theo
  `installed_apps` thay đổi theo sample, nên cache key phải bao gồm đúng
  tập tool đã lọc, không cache theo tên sample.

## 5. Loop guard — thiết kế an toàn, không mặc định fallback

### 5.1. Nguyên tắc (đã thống nhất trong phân tích giao thức round 2)

- **Loop ≠ thiếu thông tin ≠ ngoài phạm vi.** Một agent lặp có thể đang
  gặp tool error, precondition chưa thỏa, hoặc đang chọn sai tool — không
  có căn cứ nào để kết luận "người dùng thiếu thông tin" hay "yêu cầu
  ngoài phạm vi" chỉ vì hết vòng lặp.
- Do đó **không được** tự động fallback sang `sys.ask_missing_info`
  hoặc `[]` khi hết vòng lặp. Hai đầu ra đó chỉ hợp lệ trong hai điều
  kiện riêng, kiểm tra độc lập với loop:
  - `sys.ask_missing_info`: chỉ khi **chưa có write nào được thực thi**
    và một slot không ground được bằng bất kỳ read nào (đã thử các read
    có căn cứ, không phải "đoán là thiếu").
  - `[]`: chỉ khi **đã kiểm tra catalog** và không app nào xử lý được
    yêu cầu (kiểm tra này làm ở pre-flight, trước vòng lặp, không phải
    sau khi loop).
- **Không lọc failed call, không append write dọn dẹp.** Trace đã thực
  thi là bằng chứng cho evaluator; xóa hoặc sửa nó sau khi gọi là rủi ro
  về tính toàn vẹn của submission.

### 5.2. Cơ chế guard (xem code mẫu: `LoopGuard`)

1. **Phát hiện lặp:** cùng một (tool, arguments đã chuẩn hóa) xuất hiện
   lần thứ 2 → nghi ngờ lặp; lần thứ 3 → dừng vòng lặp ngay (không gọi
   lần thứ 3). Song song, đếm số bước liên tiếp không làm tiến triển
   trạng thái (tool trả về cùng kết quả / lỗi giống nhau).
2. **Dừng và replan đúng 1 lần:** replan dùng dữ liệu đã đọc/cache và lỗi
   tool đã thấy, với prompt rút gọn ("đã thử X, kết quả Y, lỗi Z — chọn
   hành động khác có căn cứ hoặc dừng"). Replan vẫn phải qua cùng
   constrained decoding + validator.
3. **Chỉ thực thi hành động mới có căn cứ:** hành động sau replan phải
   khác (tool hoặc arguments) so với các hành động đã thử và phải có
   precondition đã kiểm tra (bằng read hoặc bằng dữ liệu đã có). Nếu
   replan trả về đúng hành động cũ → không thực thi, kết thúc.
4. **Kết thúc trace nguyên trạng:** nếu không có hành động mới có căn cứ,
   trả về danh sách các tool call **đã thực thi** (kể cả failed call,
   giữ nguyên thứ tự) và dừng. Không append `ask_missing_info`, không
   append `[]`, không gọi thêm write "dọn dẹp".
5. **Trường hợp đặc biệt duy nhất được append:** nếu **chưa có write
   nào** và slot không ground được bằng bất kỳ read nào, thì việc gọi
   `sys.ask_missing_info` là một hành động hợp lệ theo đúng định nghĩa
   của nó — nhưng đây là kết luận từ bước grounding, không phải từ việc
   "hết vòng lặp". Code mẫu tách riêng hai đường này thành
   `request_missing_info()` (quyết định ask) và `ToolAgent.run` (trả về
   trace nguyên trạng khi dừng) để không lẫn.

Trong code, `ToolAgent.run` còn chặn trước khi thực thi: một call đã
thực thi đủ `max_repeats` lần sẽ không bao giờ được thực thi lại — kiểm
tra chỉ sau khi thực thi sẽ để lọt lần gọi thứ ba.

### 5.3. Những gì còn là giả định — phải xác minh trước khi chốt

Evaluator và đặc tả submission của ZAIC **chưa được truy cập trực tiếp
trong nghiên cứu này**, nên toàn bộ §5 mang nhãn **ASSUMPTION** cho tới
khi đối chiếu được:

- F1 tính trên toàn bộ `tool_calls` đã nộp hay chỉ call thành công?
  Failed call có bắt buộc phải nộp không? Submitted list có phải bằng
  đúng log của ToolEnv không?
- Read call có tính vào F1 không, và read thừa có bị trừ như write thừa
  không? (Quyết định này ảnh hưởng trực tiếp tới chiến lược selective
  read ở §4 và tới việc có nên cache read.)
- Validator lọc sau khi gọi (giấu call đã gọi) có vi phạm luật log
  không? Giả định làm việc: validator **trước khi gọi** là an toàn, lọc
  **sau khi gọi** là rủi ro — chưa xác minh.
- `sys.ask_missing_info` được chấm như một tool bình thường trong F1 hay
  có cách chấm riêng?
- Khi agent hết vòng lặp mà chưa đạt trạng thái cuối, submission kỳ vọng
  là gì: trace đã thực thi, `[]`, hay ask? (Giả định của tài liệu này là
  trace đã thực thi, theo nguyên tắc bảo toàn bằng chứng — cần xác minh
  bằng evaluator/README trong zip LifeMate.)

## 6. Code mẫu — bản đồ hàm

| Hàm / lớp trong file `.py` | Vai trò |
|---|---|
| `ToolSpec`, `normalize_catalog`, `filter_catalog_by_installed_apps` | Đọc catalog, chỉ giữ tool của app đã cài |
| `build_tool_call_schema`, `build_fallback_schema`, `schema_fingerprint` | Schema `oneOf` theo từng tool, schema chung dự phòng, cache key |
| `ToolCall`, `validate_tool_call`, `parse_tool_call` | Validator bằng code: tên tool, required, kiểu, range, `x-ref` theo `allowed_refs` |
| `build_engine`, `build_sampling_params` | Khởi tạo vLLM (lazy import, không cần GPU khi import), shim tương thích `StructuredOutputParams` → `GuidedDecodingParams` → `guided_json` |
| `LoopGuard`, `request_missing_info`, `empty_if_no_app`, `ToolAgent` | Guard lặp, hai quyết định ask/`[]` tách riêng, vòng lặp generate–validate–execute |
| `demo()` | Demo offline không GPU: fingerprint schema, validate một call đúng và một call sai, hành vi guard |

Chạy demo: `python3 01-constrained-decoding-lifemate.py` (không cần
vLLM/GPU cho phần schema + validator + guard; phần engine chỉ chạy khi
có vLLM và GPU).

## 7. Checklist triển khai offline trên A30 (trước deadline nộp Docker 16/11/2026)

1. Pin một phiên bản vLLM duy nhất; build Docker một lần; chạy test
   schema thật (catalog đầy đủ + catalog đã lọc theo `installed_apps`)
   trên A30; ghi phiên bản, backend (`xgrammar`, kèm flag `no-fallback`
   trong lúc test), và kết quả vào log build.
2. Đo, không đoán: thời gian sinh 1 tool call (TTFT + TPOT), peak GPU
   memory với prompt dài nhất, tổng thời gian/sample (ASR + LLM + tool
   execution) so với trần 30 giây; đo trên train held-out, không đo trên
   public test để chọn ngưỡng (public test không có gold để tự chấm theo
   ghi nhận portal 2026-10-26 — xác minh lại bằng cách giải nén zip
   thật).
3. Test fallback backend: tắt xgrammar, chạy outlines với cùng schema;
   đảm bảo agent vẫn chạy được nếu máy chấm thiếu wheel xgrammar.
4. Test loop guard bằng các kịch bản cố tình gây lặp: cùng tool+args
   3 lần, tool error lặp, precondition không bao giờ thỏa — kiểm tra
   trace trả về giữ nguyên failed call và không append ask/`[]` sai.
5. Kiểm tra licence của đúng artifact đã đóng gói (đặc biệt Guidance
   nếu dùng, và mọi wheel trong wheelhouse offline) trước khi nộp.

## 8. Nguồn

| Nguồn | URL | Ngày truy cập | Trạng thái xác minh |
|---|---|---|---|
| vLLM Engine Arguments (guided-decoding-backend, default xgrammar) | https://docs.vllm.ai/en/v0.8.1/serving/engine_args.html | 2026-10-27 | Tài liệu chính thức (phiên bản 0.8.1; API có thể đổi ở phiên bản mới hơn — pin phiên bản và đối chiếu lại) |
| vLLM OpenAI-Compatible Server | https://docs.vllm.ai/en/v0.8.1/serving/openai_compatible_server.html | 2026-10-27 | Tài liệu chính thức (phiên bản 0.8.1) |
| XGrammar paper (mask < 40 µs/token JSON/CFG; TPOT 6,2 → 6,3 ms batch 1) | https://arxiv.org/pdf/2411.15100 | 2026-10-27 | Báo cáo bởi tác giả; phần cứng RTX 4090 + Llama-3.1-8B, không phải A30/Qwen3-4B |
| vLLM structured-output backend discussion (xgrammar/guidance nhanh hơn outlines; outlines chín về tính năng; CPU–GPU sync) | https://discuss.vllm.ai/t/general-questions-on-structured-output-backend/1444/2 | 2026-10-27 | Báo cáo bởi cộng đồng (diễn đàn vLLM), không phải benchmark chính thức |
| Outlines — trang chủ (vLLM/vLLM offline trong danh sách hỗ trợ) | https://dottxt-ai.github.io/outlines/latest/ | 2026-10-27 | Tài liệu chính thức của dự án |
| Guidance — repo GitHub (trang repo hiển thị MIT) | https://github.com/guidance-ai/guidance | 2026-10-27 | Tài liệu chính thức của dự án về tính năng; **licence mâu thuẫn với bảng thứ cấp (Apache-2.0) — chưa kết luận** |
| Instructor — trang PyPI (MIT, patch client, retry khi validate lỗi) | https://pypi.org/project/instructor/0.6.1/ | 2026-10-27 | Trang PyPI chính thức của package; xác nhận vai trò patch client + retry, không phải engine constrained decoding local |
| A30 specs (Ampere, 24 GB HBM2, 933 GB/s, BF16 165 TFLOPS) | https://lenovopress.lenovo.com/lp1774-thinksystem-nvidia-a30-24gb-pcie-gen4-passive-gpu | 2026-10-27 | Thông số nhà sản xuất (qua Lenovo Press) |
| Bài tổng hợp đã kiểm chứng licence (vLLM/XGrammar/Outlines Apache-2.0; lm-format-enforcer MIT) | https://fr.zeststream.ai/stack/structured-output | 2026-10-27 | Nguồn thứ cấp đã kiểm chứng ngày 2026-09-23; chỉ dùng làm điểm khởi đầu, kiểm tra lại LICENSE trong artifact đã pin |

## 9. Đã xác minh / giả định / cần đo / câu hỏi evaluator còn mở

- **Đã xác minh (trong phạm vi bản nháp):** Qwen3-4B là LLM duy nhất
  hợp trần LifeMate trong hai ứng viên (Qwen2.5-Coder-7B vượt trần 5B);
  XGrammar là backend mặc định của vLLM theo tài liệu vLLM 0.8.1;
  Instructor là patch client + retry, không phải engine ép token local;
  licence Guidance còn mâu thuẫn (MIT trên repo vs Apache-2.0 trong
  bảng thứ cấp) — chưa kết luận.
- **Giả định:** toàn bộ phân tích read/F1/loop-guard trong §5 (evaluator
  chưa truy cập được); mask/automaton của schema tool-call chỉ ở mức
  KB–MB; KV cache và tổng thời gian/sample vừa trong 24 GB / 30 giây
  nếu chỉ chạy một engine.
- **Cần đo trên dữ liệu/phần cứng ZAIC thật:** TTFT + TPOT với schema
  thật trên A30; peak GPU memory với prompt dài nhất; tổng thời gian
  (ASR + LLM + tool execution) trên train held-out; trường hợp xgrammar
  fallback trên schema thật; hành vi guard trên các kịch bản lặp thật.
- **Câu hỏi evaluator còn mở:** xem §5.3; đồng thời xem danh sách đầy đủ
  Q-L1..Q-L6 trong [../gaps.md](../gaps.md). Không gửi câu hỏi cho ban
  tổ chức trong đợt này.
