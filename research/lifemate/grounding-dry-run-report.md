# Grounding dry-run trên 1545 mẫu train (đợt 7)

> Chạy ngày 2026-10-28 bằng script `analysis/grounding_dry_run_replay.py`
> (CPU thuần, không GPU, không sửa `lifemate/agent.py`).
> Lệnh chạy lại:
> `python3 analysis/grounding_dry_run_replay.py --train-jsonl <train.jsonl>
> --data-root <thư mục chứa train/>`
>
> **Ngưỡng fuzzy: giữ nguyên 88/8** (chỉ đạo đợt 7, mục 1). Không có thay đổi
> ngưỡng nào trong đợt này — ngưỡng chỉ hiệu chuẩn lại khi có predictions
> nhiễu từ ASR PhoWhisper trên Kaggle (xem đợt 6: sweep trên gold query sạch
> là phẳng, không hiệu chuẩn được).

## 0. Kết quả headline — cổng an toàn 100% đạt

| Nhánh | Đo | Kết quả |
|---|---|---|
| Arm A (gold calls nguyên bản) | Tổng gold calls qua adapter | 3541 |
| Arm A | Calls bị adapter thay đổi | **0** (3541/3541 UNCHANGED, 0 key đổi, 0 needs) |
| Arm A | Grounded calls pass `ToolEnv.validate()` | **3541/3541 (100%)** |
| Arm A | Gold calls gốc fail validate (đối chứng) | 0 |
| Arm B (proposals tổng hợp, xem §2) | Tiền/số khôi phục đúng | 146/146 (100%) |
| Arm B | Ngày tương đối khôi phục đúng ISO | 112/112 (100%) |
| Arm B | Giờ tương đối khôi phục đúng (date, hour, minute) | 378/378 (100%) |
| Arm B | Daypart mơ hồ → NEEDS_ASK(hour) | 294/294 (100%) |
| Arm B | Daypart + giờ ghi rõ → GROUNDED | 294/294 (100%) |
| Arm B | Trùng tên query → NEEDS_ASK(ambiguous) | 68/68 (100%) |
| Arm B | Query sạch (không trùng) → GROUNDED đúng | 136/136 (100%) |
| Tổng | Failures (validate + activity) | **0** |

Đọc nhanh: adapter **không phá bất kỳ gold call nào** (Arm A 0 thay đổi,
100% validate) và **hoạt động đúng trên mọi proposal tổng hợp** (Arm B 100%
trên 7 nhóm đo). Cổng "100% an toàn" cho tích hợp (§4) đã đạt trên train —
quyết định bật hook vẫn thuộc về anh, không tự động.

## 1. Arm A — gold calls: adapter không chạm vào gì đã đúng

3541 gold calls (toàn bộ `label.tool_calls` của 1545 mẫu) chạy qua
`ground_tool_call()` với `current_time` thật của mẫu và `roster=None`, sau đó
mỗi call sau grounding được kiểm tra bằng `ToolEnv.validate()` chính thức
(không gọi `env.call()`, không đổi state, không nộp gì).

- 3541/3541 trả về UNCHANGED: không key nào đổi giá trị, không needs nào
  phát sinh. Lý do là cấu trúc, không phải may mắn: gold calls đã chuẩn hoá
  sẵn (ISO date/datetime, amount int, contact_id) nên mọi nhánh pass-through
  của adapter đều kích hoạt đúng.
- 3541/3541 pass validate, và 3541/3541 gold calls gốc cũng pass validate
  (đối chứng: không có gold call nào vốn đã sai schema — nếu có, đó đã là
  phát hiện về data/tooling, không phải về adapter).
- Kết luận Arm A: adapter là **safety net thuần túy** — nó không viết lại
  gold, không "cải tiến" call đã đúng, và không thể phá schema của call tốt.
  Mọi giá trị của adapter nằm ở proposal nhiễu của LLM (Arm B), không phải ở
  gold.

## 2. Arm B — proposals tổng hợp từ tình huống gold thật (KHÔNG phải gold calls)

Arm B không đo trên gold calls — nó đo trên **proposals tổng hợp**, tức giá
trị gold được render lại thành dạng nhiễu mà LLM có thể đề xuất. Mọi con số
Arm B dưới đây phải được trích dẫn kèm nhãn "proposal tổng hợp", không được
trích thành "tỉ lệ trên gold calls":

- **B-money (146 probes):** mỗi gold amount int được render thành từ tiếng
  Việt ("150 nghìn" → "một trăm năm mươi nghìn"; hàm render nội bộ của
  script, có xử lý tỷ/triệu/nghìn/trăm/mươi/mốt/tư/lăm/linh) rồi đưa qua
  adapter. Kết quả cuối: **146/146 khôi phục đúng int gốc**.
- **B-date (112 probes):** mỗi gold ISO date được render thành biểu thức
  tương đối theo anchor ("hôm qua", "ngày mai", "15/11", có năm khi khác
  năm anchor) rồi đưa qua adapter. **112/112 khôi phục đúng ISO gốc.**
- **B-time (378 probes):** mỗi gold ISO datetime được render thành biểu thức
  tương đối + "lúc H giờ [M]" rồi đưa qua adapter; so sánh theo
  (date, hour, minute). **378/378 đúng.** 20 giá trị `time` gốc là time-only
  ("19:00") được skip theo thiết kế (không có ngày để relativize).
- **B-daypart (294 probes):** mỗi mẫu mà request hiện tại chứa daypart mơ hồ
  (sáng/chiều/tối + mai/nay — đúng 294 mẫu như E-asr-1 đã đếm, kiểm chứng
  chéo độc lập) được build proposal `{time: <phrase>}`. **294/294 trả về
  NEEDS_ASK(time:hour)** — không case nào bị fill giờ từ context.
- **B-daypart+hour (294 probes):** cùng phrase + "lúc 8 giờ" (giờ là tổng hợp,
  ngày là thật). **294/294 GROUNDED** — chứng minh ranh giới đúng: giờ lấy
  từ chuỗi của user thì compose được, giờ không có trong chuỗi thì hỏi.
- **B-dup (68 probes):** mỗi gold search mà roster trả về trùng đúng tên
  query được build proposal `{contact_name: query}` (tool lấy từ ask target
  của gold sau search đó, `to` cho email) với roster = kết quả search đó.
  **68/68 trả về NEEDS_ASK(contact:ambiguous)** — khớp policy ask của gold
  (69/73, đợt 6).
- **B-clean (136 probes):** các search còn lại (không trùng tên query) build
  proposal tương tự. **136/136 GROUNDED đúng** — adapter không ask thừa khi
  tên không trùng.
- **Không đo được ở Arm B:** other-dup (trùng tên khác, không phải tên query)
  = 0 probe, vì 5 trường hợp other-dup duy nhất ở đợt 6 đều là search query
  rỗng (full book) — không có tên để build proposal. Đây là giới hạn ghi rõ,
  không phải số 0 đẹp.

## 3. Lỗi thật do dry-run bắt được — và đã sửa trong đợt này

Trước khi sửa, B-money chỉ đạt 137/146. 9 case thất bại đều cùng một dạng:
"hai triệu tám trăm nghìn" → adapter trả 2.000.800.000 thay vì 2.800.000.
Nguyên nhân: `parse_money()` strip suffix đơn vị cuối ("nghìn") rồi nhân,
nhưng chuỗi đã chứa đơn vị lớn hơn bên trong ("triệu") — double-scaling
(2.000.800 × 1000). Đây là lỗi nghiêm trọng đúng dạng "tiền sai 1000 lần"
mà dry-run sinh ra để bắt, và nó chỉ cắn khi chuỗi có NHIỀU đơn vị lớn
("X triệu Y nghìn" — dạng tiền Việt rất phổ biến), nên unit test đợt 5
(chỉ có đơn vị đơn) không bắt được.

- Sửa: chỉ strip suffix khi phần còn lại không chứa đơn vị lớn nào khác;
  nếu còn, parse toàn bộ chuỗi bằng group parser (xử lý đúng mọi đơn vị).
- Regression test thêm vào `tests/test_lifemate_grounding.py` với đúng 9 dạng
  đã thất bại + "một tỷ hai trăm triệu" + "năm mươi nghìn".
- Chạy lại: B-money **146/146**, unit tests **48/48 cả 2 backend**
  (RapidFuzz và difflib fallback). Module thay đổi duy nhất trong đợt 7 là
  fix này (+ docstring); `agent.py` không bị sửa.

## 4. Đề xuất hook gắn vào inference (CHƯA kích hoạt — chờ anh bấm nút)

### 4.1 Vị trí chèn chính xác (main `lifemate/agent.py`, `AgentLoop.run`)

Hiện tại, mỗi vòng lặp: generator đề xuất `call` → `check =
env.validate(call["name"], call["arguments"])` (validate trước mọi call, không
log, không đổi state) → nếu ok thì qua loop guard → `env.call(...)`.
Hook chèn vào **giữa đề xuất và validate**, tức thay đoạn:

```python
call = {"name": gen["name"], "arguments": gen.get("arguments", {}) or {}}
check = env.validate(call["name"], call["arguments"])
```

bằng:

```python
call = {"name": gen["name"], "arguments": gen.get("arguments", {}) or {}}
if self.config.grounding:  # default False — xem §4.2
    grounded = ground_tool_call(
        call,
        {"current_time": sample.context.get("current_time")},
        roster=self._roster,
    )
    self.grounding_log.append({"raw": call, "grounded": grounded})
    if grounded.status == "NEEDS_ASK" or _has_leftover_name(grounded.call):
        call = {"name": "sys.ask_missing_info",
                "arguments": {"tool_name": call["name"],
                              "params": _needs_to_params(grounded.needs,
                                                         grounded.call)}}
    else:
        call = grounded.call
check = env.validate(call["name"], call["arguments"])
```

Phần còn lại của vòng lặp (validate → guard → `env.call` → observation →
guard record) giữ nguyên 100%, kể cả với ask call (ask cũng qua guard, nên
ask lặp quá `max_repeats` sẽ dừng trace như mọi call khác — chống vòng lặp
ask vô hạn).

### 4.2 Cờ bật/tắt và roster

- **Cờ `grounding: bool = False` thêm vào loop config, mặc định TẮT.**
  Dry-run 100% không tự bật hook. Anh bật bằng cách duy nhất là đổi flag
  thành True (hoặc tham số chạy) — không có đường bật ngầm nào khác.
- **Roster** (`self._roster`): khởi tạo rỗng mỗi `run()` (mỗi mẫu một roster
  mới, không rò rỉ giữa các mẫu). Sau mỗi `env.call` thành công có
  `name == "contacts.search"`, cộng dồn `result["contacts"]` vào roster
  (dedup theo id). Khi chưa có search nào, roster = None → adapter để nguyên
  tên + note, và hook chuyển thành ask theo luật leftover-name (§4.3).
- **Log audit:** `self.grounding_log` (list, ngoài `submission_line`) ghi
  cặp (raw proposal, grounded result + notes) mỗi bước. Format submission
  không đổi — log chỉ để debug/audit, không nộp kèm.

### 4.3 Hai luật hook-level (không nằm trong adapter)

1. **Leftover-name → ask.** Đã kiểm chứng: `validate()` **bỏ qua arg thừa
   không báo lỗi** (test trực tiếp: `reminders.create` kèm `contact_name`
   lạ vẫn `ok: True`). Vì vậy hook KHÔNG được dựa vào validate để bắt tên
   chưa ground — sau grounding, nếu grounded call vẫn còn key
   `contact_name` hoặc `to` không chứa "@" (trường hợp roster=None), hook
   ép thành ask xin `contact_id`/`to` thay vì validate. Đây là luật bắt buộc,
   không phải tuỳ chọn.
2. **Needs → ask params mapping** (để ask call khớp dạng gold):
   `amount` → `["amount"]`; `contact:ambiguous` → `["contact_id"]`
   (riêng `email.create_draft` → `["to"]`, đúng ask target của gold);
   `time:hour`/`time:unresolved`/`time:context_time` → `["time"]`;
   `date:*` → `["date"]`; `start:*`/`end:*` → `["start"]`/`["end"]`.
   Ask call dùng `tool_name` = tool gốc bị chặn, đúng dạng gold
   (`sys.ask_missing_info{tool_name, params}`).

### 4.4 Bất biến an toàn mà đề xuất này giữ (checklist cho nút bấm của anh)

1. Flag mặc định tắt → hành vi khi tắt là **byte-identical** với hiện tại
   (nhánh grounding bị skip hoàn toàn, không import thêm cũng không đổi
   đường đi).
2. Không đổi format `submission_line`, không đổi prompt, không đổi guard,
   không đổi số attempt (3) hay `max_steps`.
3. Mọi grounded call vẫn qua `validate()` + guard như cũ — hook không bypass
   bất kỳ lớp kiểm tra nào.
4. NEEDS_ASK không bao giờ nộp giá trị đoán (giờ, id, amount) — chỉ nộp ask.
5. Raw proposal được log đầy đủ để audit ngược mọi quyết định grounding.
6. Roster reset mỗi mẫu; không dùng roster mẫu này cho mẫu khác.

### 4.5 Những gì đề xuất này KHÔNG làm (để khỏi hiểu lầm khi bấm nút)

- Không đổi model, prompt, hay decoding; không thêm tool mới; không đổi
  scorer hay state hash.
- Không hiệu chuẩn lại ngưỡng fuzzy (vẫn 88/8, chờ predictions ASR).
- Không xử lý trường hợp LLM đề xuất sai tool hoàn toàn (grounding chỉ
  chuẩn hoá args của tool đã chọn, không chọn lại tool).
- Không đo lại trên dev — dry-run này là train-only. Trước khi bật hook cho
  bất kỳ đánh giá dev nào, nên chạy lại dry-run tương tự trên dev split
  (cùng script, đổi `--train-jsonl` sang dev) để xác nhận 100% giữ nguyên.

## 5. Tệp thay đổi trong đợt 7 (agent.py không nằm trong số đó)

- MỚI: `analysis/grounding_dry_run_replay.py` (script dry-run, 2 nhánh).
- MỚI: `research/lifemate/grounding-dry-run-report.md` (báo cáo này, kèm
  đề xuất hook §4).
- SỬA: `lifemate/lifemate_grounding.py` — chỉ fix double-scaling tiền
  (§3) + ghi chú docstring; không đổi API, không đổi ngưỡng.
- SỬA: `tests/test_lifemate_grounding.py` — thêm regression test 9 dạng
  tiền đa đơn vị (47 → 48 tests, pass cả 2 backend).
