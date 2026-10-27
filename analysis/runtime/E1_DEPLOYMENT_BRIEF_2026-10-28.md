# E1 Deployment Brief — Native tool-calling contract cho agent a2e832b

Trạng thái: READY FOR CODEX IMPLEMENTATION + RUN. Tài liệu tự chứa:
một người chỉ đọc file này + code nhánh `codex/lifemate-baseline-integration`
tại `a2e832b` là triển khai được, không cần hỏi lại. Chỉ research/phân
tích và thiết kế thí nghiệm — brief này KHÔNG sửa code inference, KHÔNG
chạy model/GPU, KHÔNG dùng held-out. Mọi thay đổi code chỉ nằm trong bản
chạy thí nghiệm của Codex, không commit lên main, không merge tự động.

Nguồn phân tích: `E0_V8_AUDIT_2026-10-28.md`,
`e0_v8_diagnostic_trace.json`, `e0_v8_verified_comparison.json` (main
f833dd3), đối chiếu `V7_V6_FAILURE_LEDGER_2026-10-28.md` và code agent
tại `a2e832b` (đọc trực tiếp từ nhánh, không dùng code inference trên
main).

## 0. Kết luận E0 mà E1 kế thừa (đã kiểm chứng, không nhắc lại như giả thuyết)

- E0 = agent a2e832b, 8 mẫu v7, current transcript thay bằng GOLD,
  history ASR giữ nguyên v7. Proxy mean 8 mẫu: v7 0.125 → E0 0.125
  (ENGINEERING_PROXY_NOT_OFFICIAL). Giả thuyết "chỉ còn ASR" bị BÁC BỎ:
  transcript chuẩn mở thêm bước đúng nhưng không mẫu nào đạt thêm
  full credit; 0003 có history_turns = 0 nên lỗi của nó không thể đổ
  cho history ASR.
- E0 totals: 43 generations, 29 tool executions, 4 validation_rejected
  (tất cả ở 0003) — so với v7: 20 generations, 11 executions,
  3 validation_rejected (tất cả ở 0003). E0 làm nhiều hơn nhưng không
  tốt hơn: vấn đề còn lại là downstream (format/intent/planning), và
  E1 chỉ được phép kết luận trong phạm vi format (xem §5).

## 1. Contract chính thức của Qwen3-4B-Instruct-2507 rev cdbee75

### 1.1 Nguồn (ghi revision, không suy từ model Qwen khác)

- **[T1] Chat template — nguồn chính cho wire format.**
  `tokenizer_config.json`, snapshot `cdbee75f17c01a7cc42f958dc650907174af0554`
  của `Qwen/Qwen3-4B-Instruct-2507`, đã đọc trực tiếp (template dài
  2630 ký tự). Mọi khẳng định về `<tools>` / `<tool_call>` /
  `<tool_response>` dưới đây đều từ artifact này, không từ model khác.
- **[T2] Cấu hình sinh — cùng snapshot.** `config.json`:
  `model_type: qwen3`, `eos_token_id: 151645`, `bos_token_id: 151643`.
  Snapshot KHÔNG có `generation_config.json` → model artifact không
  cung cấp thêm stop string nào ngoài EOS; đừng trông chờ framework tự
  suy ra stop khác (xem M7).
- **[T3] Model card — cùng revision.**
  `Qwen/Qwen3-4B-Instruct-2507` tại revision `cdbee75f17c01a7cc42f958dc650907174af0554`
  (README.md): "Significant improvements in general capabilities,
  including instruction following, logical reasoning, text
  comprehension, mathematics, science, coding and tool usage";
  BFCL-v3 61.9; "Qwen3 excels in tool calling capabilities. We
  recommend using Qwen-Agent… [which] encapsulates tool-calling
  templates and tool-calling parsers internally". Card CHỈ khẳng định
  năng lực tool calling, KHÔNG mô tả wire format `<tool_call>` —
  format lấy từ [T1]. Quickstart của card dùng message thường không
  tools, nên đừng trích card để chứng minh cấu trúc tools.
- **Điểm thành thật về giới hạn của [T1]:** template KHÔNG kiểm tra
  cấu trúc của từng tool — nó chỉ `tojson` dump từng entry trong list
  `tools`. Vì vậy dạng dict function-object dưới đây là convention
  (transformers tool-calling / Qwen-Agent), không phải thứ template tự
  pin. CPU test R1 (§6) tồn tại chính để bắt lỗi ở điểm này: render
  xong phải đọc block `<tools>` bằng mắt và kiểm tra JSON hợp lệ.

### 1.2 Wire format theo [T1] (đọc từng nhánh template)

**Khi `tools` truthy, block system được render như sau:**

```
<|im_start|>system
{content của messages[0] nếu nó là system, cộng '\n\n'}
# Tools

You may call one or more functions to assist with the user query.

You are provided with function signatures within <tools></tools> XML tags:
<tools>
{tojson(tool) cho mỗi tool, mỗi cái một dòng}
</tools>

For each function call, return a json object with function name and arguments within <tool_call></tool_call> XML tags:
<tool_call>
{"name": <function-name>, "arguments": <args-json-object>}
</tool_call><|im_end|>
```

Hai hệ quả hay bị bỏ sót:

- Message system ĐẦU TIÊN chỉ render đúng một lần, nằm bên trong block
  tools (vòng lặp message bỏ qua system ở `loop.first`). Đặt
  instruction + policy vào message system đầu tiên là đủ, không sợ bị
  lặp, cũng không cần system message thứ hai.
- Nếu `tools` truthy nhưng messages[0] không phải system, block tools
  vẫn render (không có nội dung custom). Ngược lại, nếu `tools` falsy
  thì template đi nhánh else: không có block tools nào cả — đây chính
  là trạng thái hiện tại của agent (xem §2).

**Assistant turn (kể cả turn đã chạy trong history):**

```
<|im_start|>assistant
{content}
<tool_call>
{"name": "<name>", "arguments": <args-json-object>}
</tool_call>
... (mỗi tool_call thêm một block; block đầu tiên khi content rỗng không có '\n' dẫn)
<|im_end|>
```

**Tool turn:** các message role `tool` LIÊN TIẾP được gộp thành MỘT
user turn duy nhất:

```
<|im_start|>user
<tool_response>
{content}
</tool_response>
... (mỗi tool message thêm một block)
<|im_end|>
```

Agent hiện chạy một tool result mỗi turn nên mỗi tool message sẽ là
một user turn riêng — không cần xử lý gộp, nhưng parser/render phải
đúng luật này khi tái tạo history.

**Generation prompt:** `add_generation_prompt=True` thêm
`<|im_start|>assistant\n` ở cuối. Model sinh tiếp từ đó.

**Stop / EOS / arguments:**

- Model dừng sinh tại `<|im_end|>` = EOS id 151645 [T2]. Một turn tool
  call hoàn chỉnh trên wire là: `<tool_call>{...}</tool_call>` rồi
  `<|im_end|>`. Các tag `<tool_call>` là plain text, KHÔNG phải special
  token, nên chúng sống sót qua decode với `skip_special_tokens=True`
  (điều cả hai backend hiện tại đều làm).
- `arguments` trên wire là một JSON OBJECT (ví dụ trong block system
  ghi rõ `<args-json-object>`). Nhánh render history của template chấp
  nhận cả arguments dạng string (trường hợp API đưa tool_calls với
  arguments là chuỗi JSON) — nhưng đó là tính năng render, không phải
  format model nên sinh ra. Parser E1: yêu cầu object; nếu gặp string
  thì thử `json.loads` đúng một lần và ghi log (xem M6).
- Template nói "one or more functions": model CÓ THỂ sinh nhiều block
  `<tool_call>` trong một turn. E1 giữ ngữ nghĩa một-call-một-turn của
  loop hiện tại: chỉ block đầu tiên được chạy, các block thừa được đếm
  (metric `multi_block_turns`), không chạy. Chạy nhiều block một turn
  là arm follow-up, không phải E1 (§3, P3).

### 1.3 Ví dụ tổng quát (SYNTHETIC — không lấy từ mẫu dev nào)

Tool (tự bịa, không thuộc catalog LifeMate):

```json
{"type": "function", "function": {"name": "maps.search", "description": "Search nearby places by keyword.", "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}}}
```

Messages:

```json
[
  {"role": "system", "content": "You are a voice assistant."},
  {"role": "user", "content": "Tìm quán cà phê gần nhà."},
  {"role": "assistant", "tool_calls": [{"type": "function", "function": {"name": "maps.search", "arguments": {"query": "cà phê"}}}]},
  {"role": "tool", "content": "{\"places\": [\"Quán A\", \"Quán B\"]}"}
]
```

Render ra wire (rút gọn): system block chứa `<tools>` với function
trên; user turn chứa câu hỏi; assistant turn chứa
`<tool_call>\n{"name": "maps.search", "arguments": {"query": "cà phê"}}\n</tool_call>`;
tool turn chứa `<tool_response>` với JSON kết quả. Generation prompt
tiếp theo là `<|im_start|>assistant\n`.

## 2. Code hiện tại (a2e832b) đang ở đâu — và nó lệch contract chỗ nào

Đọc từ `lifemate/llm.py` và `lifemate/agent.py` tại `a2e832b`:

| Thành phần | Hiện tại | Lệch contract ở điểm nào |
|---|---|---|
| `llm._render` | `messages = [{"role": "user", "content": prompt}]`, KHÔNG truyền `tools` | Template đi nhánh else → không có block `<tools>`, model không bao giờ thấy format native |
| Cả hai generator (`VLLMGenerator`, `TransformersGenerator`) | Nhận tham số `tools` nhưng KHÔNG DÙNG (chỉ render prompt string) | Đường ống đã có sẵn tham số tools — chỉ cần nối nó vào template, không cần phát minh interface mới từ đầu |
| `llm.parse_model_output` | Toàn bộ output phải là MỘT JSON object (có thể fenced); `{"stop": true}` hoặc `{"name": "stop"}` không arguments → stop; còn lại → ValueError → `{"name": "__invalid__", "arguments": {}}` | Không biết `<tool_call>`; output đúng format native hôm nay sẽ bị reject |
| `agent.build_base_prompt` | Một string duy nhất: instruction "Output exactly one JSON object per turn … or `{"stop": true}`" + ACTION_POLICY + current_time + profile + FULL context JSON + danh sách tool dạng prose (mỗi tool một dòng JSON gồm name/kind/description/parameters/returns) + history dạng text (`user: …`, `assistant: … calls=… results=…`) + current transcript; cộng thêm 2 dòng suffix config | Tools chỉ tồn tại dạng prose trong user message; history assistant/tool không phải turn thật; instruction mâu thuẫn với wire format native |
| `agent.render_observation_prompt` | Nối `- name(args) -> outcome; output=<compact JSON>` vào base (outcome: `not_done` nếu ok và done False, `ok`, hoặc `error: …`) | Observation là text, không phải tool message; chữ `not_done`/`ok` là diễn giải của loop, còn JSON result gốc đã chứa `ok`/`done` — chuyển sang native phải giữ JSON result, không cần giữ chữ diễn giải |
| `AgentLoop` | Protocol `gen(prompt: str, tools: dict) -> dict \| None`; validate trước mỗi call; grounding (flag); LoopGuard max_repeats=2; ask kết thúc turn; stop khi generator trả None hoặc `is_stop_signal` | Protocol phải đổi từ string sang messages (M1); còn lại giữ nguyên |
| Tools dict đưa vào loop | `catalog_tools_for_sample`: tool của sample + luôn có `sys.ask_missing_info` (loader tự append); mỗi spec có name/kind/description/parameters/returns/app | `sys.ask_missing_info` ĐÃ là một function bình thường trong dict — dưới native contract, ask không còn là trường hợp đặc biệt về format, nó chỉ là một tool call với arguments `{tool_name, params}` đúng schema |
| Sampling / stop | `SamplingParams(temperature=0.0, seed, max_tokens)` không stop; Transformers `generate(do_sample=False)` dựa vào EOS mặc định của config | Không có stop tường minh; snapshot không có generation_config.json nên không được trông chờ default nào khác ngoài EOS 151645 |

## 3. Bảng ánh xạ: thay đổi tối thiểu → native contract

Nguyên tắc: Arm B = a2e832b + đúng các mục M1–M8. Mọi thứ khác giữ
nguyên: model, revision, seed, grounding, simulator, scorer,
max_steps 12, max_repeats 2, config suffix lines, ACTION_POLICY rules
1–6. Nếu một thay đổi không nằm trong M1–M8 thì nó không thuộc E1.

### Bắt buộc (contract)

- **M1 — Messages thay cho prompt string.** Loop build messages thay
  vì một string: `[system_msg, user_msg] + [assistant(tool_call),
  tool(result)] × số call đã chạy`. Generator render bằng
  `tokenizer.apply_chat_template(messages, tools=function_defs,
  tokenize=False, add_generation_prompt=True)`. Protocol generator đổi
  từ `gen(prompt: str, tools)` sang `gen(messages: list, tools)` — đây
  là thay đổi interface bắt buộc, ghi rõ trong report.
- **M2 — Chuyển catalog spec thành function definitions.**
  `{"type": "function", "function": {"name": spec["name"],
  "description": spec["description"], "parameters": spec["parameters"]}}`.
  BỎ `kind`, `returns`, `app` (metadata nội bộ, không thuộc function
  schema). QUAN TRỌNG: strip MỌI key `x-*` khỏi parameter schemas
  trước khi đưa cho model — catalog hiện có 108 param mang annotation
  `x-ref` (metadata grounding) và `x-match` (metadata scoring); đưa
  chúng vào prompt là leak metadata nội bộ vào contract và tốn token.
  `sys.ask_missing_info` giữ nguyên như một function (schema của nó đã
  có sẵn `tool_name` + `params` required).
- **M3 — System message (đầu tiên, duy nhất).** Nội dung = instruction
  line + ACTION_POLICY + 2 dòng suffix config, với ĐÚNG MỘT câu đổi:
  câu format output đổi từ "Output exactly one JSON object per turn …
  or `{"stop": true}`" sang dạng native, ví dụ: "Output one
  `<tool_call>` block per turn; when done, reply with plain text and
  no tool call." Rules 1–6 của ACTION_POLICY giữ NGUYÊN từng chữ —
  kể cả câu cuối của policy về output cũng chỉ được sửa phần diễn đạt
  format cho khớp wire (một `<tool_call>` block; dừng = text không kèm
  tool call), không được sửa nội dung quy tắc. Template tự đặt system
  message này vào trong block tools (§1.2); không thêm system message
  thứ hai, không lặp lại format instruction trong user message.
- **M4 — User message.** = context JSON + history-dạng-text + current
  transcript (giữ đúng nội dung như `build_base_prompt` hiện tại, trừ
  phần danh sách tool prose — phần đó đã chuyển thành function defs
  ở M2 — và trừ câu instruction format — đã chuyển lên system ở M3).
  History GIỮ DẠNG TEXT trong user message ở E1 (lựa chọn tối thiểu có
  chủ đích; history-thành-turn-thật là follow-up, xem P2).
- **M5 — Observation thành message sequence.** Thay block text
  `- name(args) -> outcome; output=…` bằng cặp message:
  `assistant(tool_calls=[call])` rồi `tool(content=<result JSON
  compact>)`. Tool content giữ NGUYÊN result JSON đầy đủ (chứa
  `ok`/`done`/message) — thông tin `not_done` không mất, nó nằm trong
  JSON thay vì nằm trong chữ diễn giải. Dòng replan "Choose a
  different, evidence-backed action or stop." trở thành một user
  message append sau các tool message (không nhét vào tool content).
  Dòng retry khi output không hợp lệ cũng trở thành user message với
  nội dung viết lại cho native ("Your last output was not a valid
  `<tool_call>` block. Output one `<tool_call>` block, or plain text
  with no tool call when done.").
- **M6 — Parser native.** Trích các block `<tool_call>…</tool_call>`
  bằng regex DOTALL trên output đã decode:
  - ≥1 block: parse block ĐẦU TIÊN bằng `json.loads`; yêu cầu `name`
    là string và `arguments` là object (nếu arguments là string thì
    thử `json.loads` đúng một lần, ghi log; thất bại → reject).
    Các block thừa: đếm vào `multi_block_turns`, không chạy.
  - 0 block: phân biệt ba trường hợp, không gộp chung thành stop:
    (a) bare `{"stop": true}` hoặc `{"name": "stop"}` không arguments
    → STOP (stop-signal legacy được dung thứ như stop, không phải
    như call); (b) bare JSON object có `"name"` là tên tool (tức một
    call không có tag) → FORMAT ERROR, đi đường validation_rejected
    như block hỏng, KHÔNG được chạy, KHÔNG được tính là stop;
    (c) plain text không phải JSON → STOP (text-only = tín hiệu hoàn
    thành theo convention native; ghi lại raw text vào trace để
    audit). Điểm (b) là then chốt: chấp nhận bare JSON thành call sẽ
    làm Arm B không phân biệt được với Arm A, phá falsifiability
    (§5).
  - Block JSON hỏng: đi đường validation_rejected như hiện tại (tối
    đa 3 attempt/step), không tự sửa, không đoán call.
  - `is_stop_signal` legacy chỉ còn dùng ở Arm A; Arm B không cần nó
    (stop = không có block).
- **M7 — Stop tường minh.** vLLM: `SamplingParams(…, stop_token_ids=[151645])`.
  Transformers: truyền `eos_token_id=151645` tường minh vào generate.
  Không dựa vào default của framework (snapshot không có
  generation_config.json).
- **M8 — Budget check giữ nguyên.** `_render` encode text đã render
  (không special tokens) + 512 token reserve ≤ 16384, raise loud khi
  vượt — áp dụng cho prompt native như cho prompt text. Không silent
  cut ở bất kỳ tầng nào.

### Tuỳ chọn / LOẠI KHỎI E1 (ghi rõ để không gộp arm)

- **P1 — Sửa nội dung ACTION_POLICY rules 1–6** (thuộc E2/E5).
- **P2 — History thành turn thật** (user/assistant/tool) thay vì
  history-dạng-text. Là follow-up nếu Arm B thất bại và cần loại trừ
  "history prose làm nhiễu format".
- **P3 — Chạy nhiều tool_call trong một turn.** Giữ một-call-một-turn.
- **P4 — Đổi max_repeats / guard / completion** (thuộc E4).
- **P5 — Đổi grounding, validator, scorer, simulator, evidence ledger.**
  Grounding GIỮ BẬT ở cả hai arm (E0 chứng minh nó chặn invented ID;
  tắt nó sẽ tạo confound).
- **P6 — Cắt catalog, viết lại description tool.**
- **P7 — Constrained decoding (XGrammar/token masking).** Thiết kế
  hiện tại là validate-and-retry; E1 đo contract, không đo masking.

### Về attribution (chỉ khi Arm B khác Arm A mới cần)

Contract thay đổi cả hai đầu (render + parse) nên không thể tách
thành "chỉ parser" hay "chỉ template" mà vẫn chạy được. Nếu Arm B có
hiệu ứng và cần biết phần nào gây ra, hai arm follow-up (KHÔNG chạy
trong đợt E1 đầu) là:

- **B-roles:** tool messages cho observation, nhưng tools vẫn mô tả
  bằng prose (template với `tools=None`, parser native). Tách hiệu
  ứng của message roles.
- **B-tools:** block `<tools>` có mặt, nhưng observation vẫn là text
  nối vào user message (parser native). Tách hiệu ứng của function
  schema theo format đã train.

## 4. Phân tích riêng lỗi E0: contract tác động được gì, không được gì

Bảng này là giả thuyết có giới hạn, không phải lời hứa. Mỗi dòng ghi
rõ cơ chế: contract chỉ đổi HÌNH THỨC output, không đổi khả năng chọn
tool, suy luận điều kiện, hay phân biệt entity của model.

### Contract CÓ THỂ tác động (phạm vi format)

| Lỗi E0 | Cơ chế contract tác động |
|---|---|
| **0003: ask bị bẹt** — 4 lần sinh `{"name": "sys.ask_missing_info", "tool_name": …, "params": […]}` ở top-level, không có `"arguments"` → 4 validation_rejected trong E0 (v7: 3 lần, cùng mẫu) | Dưới native, ask là một function bình thường với schema `{tool_name, params}` nằm trong block `<tools>`; wire format bắt buộc là `{"name": "sys.ask_missing_info", "arguments": {"tool_name": …, "params": […]}}` trong `<tool_call>`. Đây là lỗi format thuần túy nhất trong E0 và là ứng viên số 1 mà E1 phải đo. Nếu Arm B vẫn bẹt ask → giả thuyết format bị bác bỏ (xem §5). |
| **Output không phải JSON / stop-as-tool** (v6 đã gặp; a2e832b đã vá bằng `is_stop_signal`, nhưng vẫn là triệu chứng dùng ngoài contract) | Native cho model một shape duy nhất đã train để sinh; stop = text không kèm block, không cần JSON stop đặc biệt. Đo bằng `validation_rejected` và `text_only_stop`. |
| **0003 chết ở bước ask** nên không bao giờ tới được transfer — tức format chặn cả task | Nếu format được sửa, 0003 có cơ hội đi tiếp tới list_bills/search; nhưng việc nó CÓ đi tiếp hay không lại thuộc §4.2, không được tính vào verdict format. |

### Contract KHÔNG tác động (cần intent/planning/policy — thí nghiệm khác)

| Lỗi E0 | Vì sao không phải format | Thí nghiệm nào xử lý (không phải E1) |
|---|---|---|
| **0003: không bao giờ gọi list_bills** dù transcript nhắc tới số tiền của bill; search "cô Mai" rỗng rồi lặp lại y hệt, không mở rộng query | Thiếu bước prerequisite và thiếu chiến lược khi search rỗng — là planning, không phải shape output. Policy rule 4 đã nói "read a bill when the request refers to its value" mà model vẫn không làm. | E2-style (ví dụ prerequisite) hoặc tăng cường evidence policy; đo riêng bằng prerequisite checklist (§5) |
| **0003: invented phone / invented contact ID** (bị provenance chặn trước khi chạy, E0 audit) | Grounding đã làm đúng việc của nó; format không sinh ra ID đúng. Native không thay thế grounding — giữ grounding BẬT cả hai arm. | Không phải lỗi cần sửa bằng contract; là bằng chứng grounding hoạt động |
| **0116: tự điền giờ thay vì hỏi** — E0: `reminders.create{content: "gọi điện cho mẹ", time: "2026-11-19T10:30:00+07:00"}` thay vì ask; hash chuyển từ đúng (v7, ask không đổi state) sang sai (E0, write đổi state) | Quyết định ask-vs-act, không phải format: call sinh ra hoàn toàn well-formed. Policy rule 4 ("do not assume the current time is a requested reminder time") đã bị vi phạm về nội dung. | E5 (quy tắc phân biệt nhắc–gọi) |
| **0008: write trước điều kiện** — E0 vẫn `alarm.update` trước, rồi đọc `weather.get_current` (thời tiết hiện tại) thay vì forecast ngày mai; `alarm.update` lặp ×2 | Thứ tự condition-before-write + chọn sai tool đọc (get_current vs get_forecast) là planning/tool-choice. Policy rule 2 đã nói đúng mà model vẫn viết trước. | E2 (ví dụ condition-before-write); duplicate ×2 thuộc E4 |
| **0025: tự chọn một trong hai Minh** — E0: search "Minh" rồi `phone.call{c_05}` trong khi gold yêu cầu hỏi phân biệt (audit: đọc hai ứng viên rồi chọn một) | Phân biệt entity khi nhiều ứng viên — rule 3 ("several candidates require a unique explicit discriminator or ask; do not pick the first") bị vi phạm về nội dung, không phải format. | E5-style (disambiguation) |
| **0025: ghi cụm điều kiện vào title** — `calendar.update_event{title: "đá bóng (nếu không mưa)"}` trước khi kiểm tra mưa | Nhánh điều kiện được thực thi trước khi điều kiện được kiểm tra — planning, không format. | E2 |
| **0016: đọc forecast đúng rồi vẫn tạo + hoàn thành reminder** thay vì đổi calendar event | Nhầm loại task (reschedule calendar vs create reminder) — intent, không format. | Ngoài E1 (intent classification) |
| **0049: bịa 1200000, bỏ qua bill read, thêm savings actions** | Prerequisite + intent + số tiền bịa — format không sinh ra số đúng. | E2-style (bill read trước transfer) |
| **0004: hash đúng nhưng F1 = 0** (read có filter, light_set thừa `power: "on"`, ghi trùng) | Đây là proxy-mismatch/scorer scope (matcher đòi key set giống hệt; semantics của read/optional arg chưa được organizer xác nhận) — không phải lỗi model theo nghĩa state sai, và không liên quan contract. | Câu hỏi organizer Q-L (chưa gửi, cần duyệt riêng); E1 KHÔNG được tính 0004 là intent failure |
| **Duplicate calls** (0008 update ×2, 0049 open_savings ×2, 0004 light_set ×2) | Termination/guard — format không quyết định dừng. | E4 |

**Giả thuyết E1, viết đúng phạm vi:** "Native contract được kỳ vọng
giảm LỖI FORMAT (ask bẹt, non-JSON, stop confusion) và nhờ đó gỡ tắc
cho các bước hiện đang chết vì format (điển hình 0003). Nó KHÔNG
được kỳ vọng sửa tool choice, bịa argument, thứ tự prerequisite,
chọn entity, hay termination." Bất kỳ báo cáo E1 nào viết "native
tool-calling chữa intent" đều là vượt phạm vi.

## 5. Thiết kế thí nghiệm E1 tối thiểu

### Arms (đúng 2 arm cho đợt chạy đầu)

- **Arm A (đối chứng):** a2e832b nguyên vẹn (text contract, legacy
  parser, prose tool list, observation text). Input = cached ASR v7
  (xem dưới). Arm A phải tái tạo v7 trong sai số nhỏ; nếu drift lớn
  thì baseline không đáng tin và phải báo trước khi kết luận về B.
- **Arm B (thử):** a2e832b + M1–M8, KHÔNG thêm P1–P7. Cùng input, cùng
  config, cùng seed, cùng scorer như Arm A.
- **Config:** cả hai arm dùng cùng config như v7/E0 — grounding BẬT
  (run.py mặc định `recommended.json`: grounding True, max_steps 12,
  max_repeats 2; và E0 có provenance block nên grounding đã bật ở E0).
  Codex PHẢI ghi tên file config thực tế dùng vào report; nếu v7/E0
  dùng file khác thì match file đó và ghi rõ, không tự ý đổi.
- **Input (cố định, không đổi giữa hai arm):** đúng 8 mẫu v7
  (0019, 0116, 0025, 0003, 0008, 0016, 0049, 0004) với đúng cached ASR
  current + history từ v7 — byte-identical giữa Arm A và Arm B.
  Dùng cached ASR chứ không dùng gold vì E0 đã tách ASR xong
  (gold-current vẫn 0.125); E1 tách contract nên ASR phải giữ cố định
  ở mức v7, không nâng lên gold (nâng lên là đổi hai biến cùng lúc).
  Model, revision, seed 42, FP16/T4x2 placement như v7/E0. Không
  held-out, không training.

### Đo riêng từng tầng (không gộp thành một số duy nhất)

| Tầng | Metric (per-sample, rồi mới tổng hợp) |
|---|---|
| Format | `validation_rejected` count; `malformed_ask` count (ask có tool_name/params ở top-level, thiếu `"arguments"`); `parse_success_rate` (generations cho ra call hợp lệ hoặc stop / tổng generations); `multi_block_turns`; `text_only_stop` count |
| Tool choice | First-call name có khớp gold first-call name không; tỉ lệ call name khớp gold (per-call, order-ignored như proxy nhưng báo riêng) |
| Arguments / ask target | Ask target đúng không (tool_name + params so với gold ask, cho mẫu ask); argument key-set khớp gold không; fuzzy value khớp không (dùng cùng luật fuzzy của proxy nhưng báo riêng từng phần) |
| Prerequisite | Checklist theo mẫu, build TỪ GOLD LABELS (tra theo ID) và freeze trước run — ví dụ đã xác lập: 0003 list_bills trước ewallet.transfer; 0008 get_forecast(ngày mai) trước alarm.update; 0049 list_bills trước transfer. Codex tự build checklist đầy đủ cho 8 mẫu từ gold, không suy từ output model. Đo: prerequisite được thỏa trước write phụ thuộc hay không |
| Termination | Số call thừa/trùng so với gold; dừng sớm 0-call trên mẫu action; số lần guard trigger |
| Outcome | state_hash đúng/sai; F1 proxy; score (= F1 nếu hash đúng else 0). Báo per-sample; mean 8 mẫu chỉ để tham khảo, KHÔNG dùng làm verdict (8 mẫu không có ý nghĩa thống kê) |
| Regression guards | 0019 vẫn phải stop với 0 call; grounding vẫn chặn invented ID (spot-check: nếu 0003 lại invent phone/ID ở generation đầu, nó phải bị chặn như E0); không có context-budget error (budget check loud, không silent cut) |

### Tiêu chí kết luận (đăng ký trước, có giới hạn)

- **Format-scope CONFIRMED** nếu Arm B đưa `validation_rejected` +
  `malformed_ask` về ~0 trên 8 mẫu VÀ Arm A tái tạo được lỗi format
  ở mức v7 (delta là thật, không phải baseline drift). Khi đó E1
  thành công trong phạm vi của nó, dù score không đổi.
- **Format-scope REFUTED** nếu Arm B vẫn bẹt ask / vẫn reject ở mức
  ≈ Arm A (model phớt lờ template) → dừng hướng contract, không đổ
  thêm GPU vào B-roles/B-tools.
- **"Format đã sửa nhưng intent còn sai" là PARTIAL CONFIRMATION,
  KHÔNG phải bác bỏ.** Đây là kết quả được dự báo trước ở §4: format
  xong thì các lỗi intent/planning (§4.2) vẫn còn đó và thuộc về
  E2/E5/E4. Báo cáo nào viết "E1 thất bại vì score không lên" trong
  khi format đã sạch là đọc sai tiêu chí.
- **Score/hash tăng mà format không cải thiện thì KHÔNG xác nhận
  contract** (có thể là noise/drift) — verdict format luôn cần delta
  format, không lấy score thay thế.
- **Không kết luận thống kê, không khái quát hoá ngoài 8 mẫu.**
  Mọi câu trong report E1 phải gắn với ID mẫu và event cụ thể.

## 6. Những thứ kiểm được bằng CPU / unit test TRƯỚC KHI dùng GPU

GPU launch gate: tất cả các mục dưới pass thì mới chạy GPU. Một run
GPU được launch khi CPU test còn fail là run không hợp lệ, phải báo
như vậy trong report.

- **R1 — Render test (tokenizer only, không cần weights).** Với
  tokenizer rev cdbee75: render `[system, user] + tools` → block
  `<tools>` có mặt, function defs là JSON hợp lệ, system content xuất
  hiện đúng một lần; render chuỗi assistant+tool → vị trí
  `<tool_call>` / `<tool_response>` đúng §1.2, tool message liên tiếp
  gộp đúng luật; generation prompt kết thúc bằng `<|im_start|>assistant\n`.
- **R2 — Parser test (unit test, synthetic).** Input: single block;
  text + block; multi-block (chỉ block đầu được lấy, đếm thừa); bare
  JSON không tag → reject ở Arm B (không fallback legacy); block JSON
  hỏng → reject; text-only/empty → stop; arguments dạng string →
  parse một lần + log. Ví dụ negative (synthetic, không phải probe):
  `{"name": "sys.ask_missing_info", "tool_name": "notes.create",
  "params": ["title"]}` (tool_name/params ở top-level) → PHẢI reject
  ở Arm B.
- **R3 — Conversion test.** Với tool set của cả 8 mẫu (13–59 tools
  mỗi mẫu, ask luôn có mặt): defs hợp lệ, schema giữ nguyên
  properties/required, mọi key `x-*` đã strip, `kind`/`returns`/`app`
  đã bỏ, không tool nào mất khỏi defs so với dict gốc.
- **R4 — Budget test (tokenizer only, phương pháp như context-budget
  work).** Render Arm B first-turn prompt cho 8 mẫu (cached ASR) +
  512 reserve ≤ 16384; cộng thêm bound worst-case multi-turn (12
  steps) theo cùng phương pháp đã dùng cho e79f9722/a2e832b. Nếu prompt
  native phình hơn do block tools thì phải thấy con số, không đoán.
- **R5 — Equivalence test.** Mọi chuỗi input của Arm A first prompt
  (context, history text, transcript, policy rules) đều xuất hiện ở
  đâu đó trong messages của Arm B — trừ đúng hai thứ được thay thế có
  chủ đích: danh sách tool prose (→ defs) và câu instruction format
  (→ câu native ở system). Mất mát nào khác = bug, không phải thiết
  kế.
- **R6 — Loop test (text-level fake, CPU).** Fake generator trả về
  chuỗi `<tool_call>` canned → loop chạy, validation-retry, ask-stop,
  guard đều hoạt động qua protocol messages mới. (Fake cũ trả dict
  không test được đường native.)
- **R7 — Stop-config test (code-read + assert).** `SamplingParams`
  có `stop_token_ids=[151645]`; Transformers generate có
  `eos_token_id=151645` tường minh. Không dựa vào default.

## 7. Checklist trả về (Codex điền sau run)

- [ ] Tên file config thực tế + source commit + ASR/LLM revision +
      seed + placement đã dùng cho cả hai arm.
- [ ] Log pass R1–R7 (CPU) trước GPU; nếu mục nào fail mà GPU vẫn
      chạy thì ghi rõ là run không hợp lệ.
- [ ] Per-sample cho mỗi arm: format metrics, calls, hash, F1, score,
      prerequisite checklist (freeze từ gold trước run).
- [ ] Trace JSON định dạng v6/v7/E0 (diagnostic-only: ASR của model,
      raw output, call đã chạy, tool feedback — không full prompt,
      không gold, không state dump).
- [ ] Verdict theo đúng §5: format-scope CONFIRMED / REFUTED /
      PARTIAL (format sạch, intent còn sai) + bằng chứng theo ID mẫu
      và event; không viết verdict dạng "E1 thành công/thất bại" chung
      chung, không dùng mean 8 mẫu làm verdict.
- [ ] So sánh trực tiếp cùng mẫu giữa hai arm (không so mean khác
      mẫu số); ghi rõ Arm A drift so với v7 nếu có (greedy/seed 42
      nhưng vLLM batching có thể gây nondeterminism nhỏ).
- [ ] Không đề xuất model khác, không training, không held-out, không
      merge main từ kết quả E1. Hướng tiếp theo (nếu có) là E2/E5/E4
      theo §4.2, hoặc B-roles/B-tools nếu cần attribution (§3).

## 8. Giới hạn còn mở (không giả vờ đã giải quyết)

- Dạng dict function-object là convention, không phải thứ template
  pin (§1.1) — R1/R3 là biện pháp giảm thiểu, không phải chứng minh.
- History vẫn là text trong E1 (M4) — nếu Arm B thất bại, P2 là ứng
  viên follow-up đầu tiên, không phải kết luận "contract vô dụng".
- Stop behavior thực tế trên vLLM vs Transformers có thể khác nhau
  dù cùng EOS — report phải ghi backend thực tế đã chạy.
- 8 mẫu, không thống kê, không A30: E1 không chứng minh gì về latency
  hay về tập test riêng tư.
