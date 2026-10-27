# LifeMate — Hồ sơ sâu các ứng viên mạnh (round 2)

> Mọi phương pháp dưới đây là **giả thuyết chuyển giao** cho tới khi đo trên
> train held-out của ZAIC. Không số benchmark nào được dùng làm mục tiêu điểm
> chính thức. Nhãn: `README_READ` = chỉ đọc README; `DEEPWIKI_SUMMARY` = chỉ
> đọc tóm tắt DeepWiki; `PAPER` = paper/abstract; `SECONDARY` = nguồn thứ cấp;
> `ASSUMPTION` = điều kiện giả định vì evaluator ZAIC chưa truy cập được.
> **Không repo nào dưới đây là CODE_INSPECTED** — phần "file cần mở tiếp"
> ghi đúng tên file để mở bằng `git clone`, không giả vờ đã đọc code.

## 0. Hai sửa chữa bắt buộc, áp dụng cho mọi file khác trong repo

### 0.1. Selective reads thay cho "read-before-and-after mọi write" (ASSUMPTION)

Evaluator ZAIC chưa truy cập được, nên bảng dưới là **giả định làm việc**,
cần đối chiếu với regulations PDF, README trong zip LifeMate, tool catalog
và đặc tả submission trước khi chốt. Giả định: F1 tính trên toàn bộ
`tool_calls` đã nộp, mẫu số gồm cả call thừa; `state_hash` do evaluator tự
tính từ state cuối, không phụ thuộc việc agent tự verify. Nếu F1 thực tế
chỉ tính trên call thành công hoặc bỏ qua read, bảng này phải viết lại.

| Loại read | Khi nào làm | Lợi ích | Chi phí / rủi ro | Quyết định mặc định |
|---|---|---|---|---|
| Precondition read (trước write) | Precondition CHƯA được xác lập bởi context/history/read trước, và write không đảo ngược được hoặc đắt (chuyển tiền, đặt lịch, gửi, xóa) | Tránh write lỗi → tránh hash về 0 | +1 call trong trace; +latency; nếu gold không cần read này thì F1 có thể giảm nhẹ | LÀM, chỉ 1 lần, cache kết quả |
| Grounding read | Giá trị cần điền chưa có trong context/history, hoặc nhiều ứng viên cần phân biệt | Không có read này thì không thể ground → buộc phải đoán hoặc ask | +1 call; candidate list lớn tốn context — chỉ giữ trường cần thiết | LÀM, vì là read bắt buộc về mặt thông tin |
| Verification read (sau write) | Quyết định tiếp theo PHỤ THUỘC vào state mới (ví dụ write trả về ID mới mà bước sau cần dùng) | Cho bước sau dữ liệu thật thay vì suy đoán | +1 call + latency mà KHÔNG tăng điểm trực tiếp (evaluator đã tự tính hash); nếu gold không có read này thì F1 giảm | KHÔNG LÀM theo mặc định |
| Redundant read | Không bao giờ, trừ khi có bằng chứng state đã đổi bởi một write ở giữa | Không có | +call +latency +context, không thêm thông tin | CẤM bằng cache: key = (tên tool read + argument đã chuẩn hóa) trong cùng sample |

Hệ quả cho code: **validator TRƯỚC khi gọi là an toàn** (chặn call sai
schema trước khi chạm ToolEnv). **Lọc call SAU khi đã thực thi là rủi ro**
— mọi call đã chạy qua ToolEnv đều phải xuất hiện trong submission theo
luật ghi nhận; không tự ý giấu failed call hay read call khỏi submission
cho tới khi có đáp án cho câu hỏi Q-L2/Q-L4 trong [../../gaps.md](../../gaps.md).
Không có "read-before-write wrapper" mặc định cho mọi write.

### 0.2. Loop guard đúng giao thức + metric chọn hệ thống

**Loop không phải là thiếu thông tin, cũng không phải ngoài phạm vi.**
Phát hiện bằng code: exact loop (cùng tool + argument chuẩn hóa lặp ≥ 2
lần); cycle loop (chuỗi A → B → A mà không có state nào thay đổi);
stall loop (observation mới không thêm thông tin, model vẫn đề xuất cùng
hành động).

Thứ tự khi phát hiện loop, dừng ở bước đầu tiên thành công:
1. Dừng lặp ngay, không emit lại call đã lặp; ghi loop vào log nội bộ
   (không phải là một tool call).
2. Replan 1 lần từ state đã biết (call đã thực thi + kết quả read đã
   cache), liệt kê slot đã đủ / còn thiếu / tool chưa thử mà catalog cho
   phép; replan bằng LLM 1 lần với prompt đã nén (kết quả read gần nhất +
   danh sách call đã làm, bỏ thought dài).
3. Nếu replan cho ra hành động mới có căn cứ (tool khác, hoặc cùng tool
   với argument đã đổi theo kết quả read/lỗi) → thực thi và tiếp tục.
4. Nếu replan vẫn cho ra cùng hành động, hoặc không còn hành động có căn
   cứ → **KẾT THÚC TRACE NGUYÊN TRẠNG.** Nộp đúng các call đã thực thi
   (kể cả failed call — không lọc trace). Không append
   `sys.ask_missing_info`, không append `[]`, không append write "dọn dẹp".
5. Ngoại lệ duy nhất được append ask: khi CHƯA CÓ WRITE NÀO được thực thi,
   và slot bắt buộc không thể ground bằng bất kỳ read nào trong catalog
   (đã thử grounding read rồi) → `sys.ask_missing_info` là quyết định
   terminal hợp lệ, không phải "thoát loop".
6. Ngoại lệ duy nhất được append `[]`: khi sau khi kiểm tra lại catalog
   (tên + description + `installed_apps`), không có app nào xử lý được yêu
   cầu → `[]` là quyết định terminal hợp lệ. Kiểm tra này phải xảy ra
   TRƯỚC bất kỳ write nào; nếu đã write rồi thì không còn đường về `[]`.

**Metric chọn nâng cấp (chính thức):** điểm trung bình =
mean(hash đúng ? tool F1 : 0), kèm tỉ lệ mẫu ≤ 30 s và giây/sample trung
bình. Một nâng cấp chỉ giữ nếu cải thiện metric này. **Tỉ lệ hash đúng là
metric chẩn đoán, không dùng một mình để chọn hệ thống** — hai hệ thống
cùng hash rate có thể khác F1 rất xa (một gọi thừa nhiều read, một gọi
đúng và đủ).

## 1. RECOVER — sửa entity có căn cứ, không phải đoán

- **Paper:** https://arxiv.org/pdf/2603.16411 (arXiv 2603 = tháng 3/2026,
  trước cutoff 26/10/2026 về mặt ngày cho ý tưởng; không có checkpoint nào
  từ paper này được đề xuất dùng trực tiếp). Nhãn: `PAPER`, chưa test ZAIC.
- **Pipeline thật (từ tóm tắt paper):** (1) sinh N hypothesis từ một ASR
  model (trong thí nghiệm: 5 hypothesis bằng temperature sampling với
  Whisper-small); (2) Dynamic Entity Candidate Retrieval chọn top-K ứng
  viên entity (K = 200 trong paper); (3) ba tool theo thứ tự: Fuse
  Hypotheses → Propose Corrections (LLM prompt có ràng buộc) → Verify &
  Apply (guardrail xác định, deterministic). Điểm mấu chốt là bước 3:
  correction chỉ được apply khi qua được guardrail, không phải cứ LLM đề
  xuất là sửa.
- **Kết quả tác giả báo cáo (AUTHOR, 5 dataset của tác giả, không phải
  ZAIC):** giảm tương đối 8–46% entity-phrase WER, recall tăng tới 22 điểm
  phần trăm; LLM-Select đạt tốt nhất trong khi vẫn giữ nguyên WER tổng.
  Khoảng 8–46% rất rộng — phụ thuộc dataset, không lấy một con số làm kỳ
  vọng cho ZAIC.
- **Chuyển sang LifeMate (HYPOTHESIS):**
  - N-best: lấy 5 hypothesis từ PhoWhisper (beam hoặc temperature
    sampling; cần đo xem N-best từ beam có đủ đa dạng không, vì beam
    thường chỉ khác nhau ở vài từ — nếu N-best quá giống nhau thì RECOVER
    không có gì để fuse).
  - Candidate list: KHÔNG dùng entity DB ngoài. Candidate list phải là
    danh sách đóng lấy từ tool read trong chính sample đó (contacts,
    devices, accounts, địa chỉ đã lưu). Đây là điểm khác biệt lớn nhất với
    paper gốc.
  - Verify & Apply: chỉ sửa khi (a) ứng viên khớp chính xác hoặc khớp âm
    vị/edit-distance dưới ngưỡng chặt, và (b) slot đó là entity/name —
    **KHÔNG áp dụng fuzzy cho số tiền, ngày, ID** (xem §2).
  - Thí nghiệm nhỏ nhất: trên train held-out, so 1-best vs N-best +
    closed candidate, đo slot-error theo role (negation/number/entity),
    không đo WER tổng.
- **Bằng chứng gián tiếp cho ranking candidate:** GEC-RAG
  (https://arxiv.org/html/2501.10734v1, PAPER) và RAC
  (https://arxiv.org/pdf/2409.06062, PAPER) đều cho thấy retrieval bằng
  acoustic neighbor / phonetic similarity vượt semantic embedding cho lỗi
  tên riêng; RAC báo cáo acoustic neighbor embeddings cho entity recall
  cao hơn semantic hơn 4 điểm phần trăm (trên tập synthetic voice-assistant
  của tác giả, không phải ZAIC). Vì vậy candidate ranking cho LifeMate
  nên là: (1) khớp chính xác, (2) edit-distance/phonetic, (3) mới đến
  semantic — không dùng embedding ngữ nghĩa làm tiêu chí chính.

## 2. Sửa có căn cứ vs đoán — quy tắc phân loại slot

| Loại slot | Sửa được khi nào | Không bao giờ |
|---|---|---|
| Tên người / thiết bị / tài khoản (entity) | Khớp chính xác với candidate từ tool read, hoặc khớp âm vị/edit-distance chặt VÀ chỉ có 1 ứng viên duy nhất trong ngưỡng | Có ≥ 2 ứng viên gần nhau → ask (nếu chưa write) hoặc dừng nguyên trạng (nếu đã write) |
| Số tiền, số lượng, ngày, giờ, ID | Khớp chính xác tuyệt đối (sau chuẩn hóa định dạng: "năm trăm nghìn" = 500000; "ngày mai" phải resolve theo context ngày — nếu không resolve được thì coi là không khớp) | Fuzzy đoán, làm tròn, suy ra từ N-best khác nhau mà không có căn cứ |
| Địa chỉ | Khớp chính xác từng thành phần đã có trong candidate (số nhà, đường, quận) hoặc khớp toàn bộ chuỗi | Ghép địa chỉ từ nhiều hypothesis khác nhau thành một địa chỉ "mới" chưa từng xuất hiện |
| Phủ định | N-best đồng thuận về phủ định (tất cả hypothesis đều có/không có từ phủ định) | N-best phân vân về phủ định → không write; đây là trường hợp nguy hiểm nhất theo §3 |
| Intent cue (động từ chính: chuyển/hủy/đặt/xem) | N-best đồng thuận, hoặc grounding read xác nhận được hành động đó là khả thi | Intent cue mơ hồ + write không đảo ngược được → ask/dừng |

## 3. Task-role diagnostics — vì sao WER tổng là metric sai

- **Paper:** "When Does an ASR Error Matter?"
  https://arxiv.org/html/2610.17619v1 — nhãn `PAPER` (đọc qua tóm tắt tìm
  kiếm, chưa đọc toàn văn). **Cẩn trọng ngày:** arXiv ID 2610.xxxx gợi ý
  tháng 10/2026; ngày chính xác so với cutoff 26/10/2026 CHƯA xác minh, nên
  chỉ dùng khung chẩn đoán, KHÔNG dùng checkpoint nào từ paper này.
- **Kết quả chính (paired JCA loss, điểm phần trăm — mức tăng lỗi hành
  động khi role đó bị hỏng, so với transcript gốc đúng):** negation 25,7
  (sensitivity 23,3) > number 21,9 (19,0) > entity 17,1 (15,7) > intent cue
  12,4 (10,5) > other slot value 9,5 (8,6) > function word 2,9 (3,3) >
  other non-critical 1,4 (1,0). Phân loại lỗi output cuối trong 216 cặp bị
  hại: argument value 47,7%, argument structure 22,2%, wrong tool 19,4%,
  call/no-call decision 7,9%, malformed output 2,8% — gần một nửa lỗi cuối
  là sai giá trị argument, không phải sai tên tool.
- **Giới hạn áp dụng (tác giả tự ghi):** dữ liệu tiếng Anh, tool schema
  hiện tại, speech tổng hợp — vì vậy thứ tự negation > number > entity là
  tín hiệu để đo lại trên tiếng Việt, **không phải con số để copy sang
  ZAIC**. Đo slot-error theo role, không đo WER tổng: một hệ thống giảm
  WER 2 điểm nhờ sửa function word nhưng để lọt negation thì vẫn thua.
- **Bằng chứng bổ sung (SECONDARY, ví dụ minh họa, không phải đo lường):**
  blog "Why WER lies to you in production IVR"
  (https://dev.to/sridharanvijaykumar/why-wer-lies-to-you-in-production-ivr-4204)
  và dự án Callona (https://taneemishere.github.io/callona/) với 3 quy tắc
  đáng mượn dưới dạng code: check-before-book (chỉ book slot mà availability
  lookup thật đã trả về) → "check-before-write" của LifeMate; negation-aware
  confirmation; digit path bypass ASR (số callback lấy từ số caller/keypad,
  không tin hoàn toàn vào speech model).

## 4. τ-bench / τ² / τ³ — phân biệt benchmark, framework, model, solution

- **τ-bench (v1)** là benchmark + framework đánh giá, không phải solution
  thi đấu. Repo: https://github.com/sierra-research/tau-bench (MIT, commit
  vòng 1 `59a200c6d575d595120f1cb70fea53cef0632f6b` — nhãn cho repo này
  trong round 1 là code-read; trong round 2, các file agent cụ thể dưới
  đây chỉ ở mức `DEEPWIKI_SUMMARY`, chưa đọc thân file).
  Agent mẫu: `ToolCallingAgent`
  (`tau_bench/agents/tool_calling_agent.py`, theo tóm tắt DeepWiki — file
  cần mở tiếp bằng git clone): vòng lặp native tool calling qua
  `litellm.completion`, mỗi bước chỉ xử lý tool call đầu tiên (index 0),
  nếu không có tool call thì tạo action `respond`; loop dừng khi
  `env_response.done`. `run.py` chạy theo trial/task, mỗi task có env riêng
  để tránh rò state, checkpoint ghi JSON.
- **Số τ-bench — bắt buộc ghi điều kiện:** paper arXiv 2406.12045
  (https://arxiv.org/html/2406.12045v1), Table 3: khi bỏ domain policy khỏi
  system prompt, GPT-4o pass¹ retail **61,2 → 56,8**, airline **33,2 →
  10,8** (airline phụ thuộc policy mạnh hơn retail rất nhiều). Không trích
  số trần "τ-bench ~60%". Số README (Claude 0,692 retail) thuộc thời điểm/
  phiên bản task khác — không trộn với số paper gốc; repo đã cảnh báo task
  cũ. **Bài học transfer quan trọng nhất:** LifeMate phải đưa policy/rule
  của app vào prompt (tương tự rulebook của DataMate), đặc biệt với app có
  rule phức tạp.
- **τ²-bench:** repo https://github.com/sierra-research/tau2-bench (MIT,
  commit lúc mở round 2 `70f71c6b3c57164841a23cab124910c54f9cd7bf`,
  README_READ). Điểm mới: domain telecom dual-control (cả agent và user
  đều có tool), domain `banking_knowledge` (retrieval), và **τ-Entity**
  (`--domain intake`, 200 task, exact entity capture). README cảnh báo:
  **τ-bench 2.0 KHÔNG input-identical với v1.0.1** (50 task retail/telecom
  được thay, prompt thêm language clause và entity-order rule, judge đổi
  sang semantic LLM judge, lookup fold case/accent/format) — **không được
  so sánh số 2.0 với số 1.x như cùng một thí nghiệm.**
- **τ³ / τ-Voice / τ-i18n** là các benchmark con trong cùng repo τ²:
  voice full-duplex (realtime API), multilingual (6 ngôn ngữ, KHÔNG có
  tiếng Việt: English, Spanish, Portuguese, Hindi, Chinese, Korean). τ³-voice
  là **benchmark**, không phải model, và voice full-duplex khác hẳn
  LifeMate (audio file offline + ToolEnv): không lấy agent realtime, chỉ
  lấy ý về entity capture và judge.
- **τ-Elicitation (τ-Entity):** paper https://arxiv.org/abs/2609.13602
  (submitted 11/09/2026, trước cutoff 26/10/2026 về mặt ngày, PAPER).
  Kết quả tác giả báo cáo (AUTHOR, không phải ZAIC): text agent matched
  pass toàn bộ task, nhưng 4 cấu hình voice chỉ đạt robust exact success
  0,14–0,41; scaffold quy định spelling + read-back + correction +
  confirmation làm tăng robust Pass³ thêm 14–31 điểm, với chi phí 21–28
  giây/call; chỉ 24–37% lỗi đã verify được sửa thành công.
  **Chuyển giao có điều kiện (HYPOTHESIS):** LifeMate không có user thật
  để đánh vần/read-back, nên scaffold nhiều vòng KHÔNG áp dụng được; chi
  phí 21–28 s/call cũng gần chạm trần 30 s/mẫu. Chỉ mượn được một ý:
  **verify trước write có thực thể** (kiểm tra entity đã capture có khớp
  candidate không trước khi write), và **đo recovery rate riêng** (tỉ lệ
  lỗi đã phát hiện mà sửa được), không đo chung accuracy.
- **Lấy được từ τ-bench:** khung loop, khung phân loại lỗi
  (`auto_error_identification.py`: `CALLED_WRONG_TOOL`,
  `USED_WRONG_TOOL_ARGUMENT`, `GOAL_PARTIALLY_COMPLETED` — file cần mở tiếp
  bằng git clone, nhãn hiện tại là DEEPWIKI_SUMMARY), và metric pass^k
  (độ ổn định qua k lần thử, gần với việc ZAIC chạy lại Docker khi không
  ổn định).

## 5. Forge — guardrail patterns, không phải model, không phải CODE_INSPECTED

- **Repo:** https://github.com/antoinezambelli/forge — **README_READ**
  (commit lúc mở `3e5a38aed55504a71e5461b9873ca1979709ab50`, MIT, 2.263
  stars, tạo 2026-02-16 — trước cutoff). Thân các file dưới đây CHƯA được
  đọc; tên file lấy từ mục Project Structure trong README, không phải từ
  việc mở file. **File cần mở tiếp bằng git clone tại commit trên, rồi mới
  được gắn CODE_INSPECTED:**
  `src/forge/core/runner.py` (WorkflowRunner),
  `src/forge/core/inference.py` (`run_inference()`: compact, fold,
  validate, retry), `src/forge/guardrails/response_validator.py`
  (ResponseValidator, ValidationResult),
  `src/forge/guardrails/step_enforcer.py` (StepEnforcer, StepCheck),
  `src/forge/guardrails/error_tracker.py` (ErrorTracker),
  `src/forge/context/manager.py` + `strategies.py` (ContextManager,
  TieredCompact giữ recent 2, SlidingWindowCompact),
  `src/forge/tools/respond.py` (synthetic respond tool),
  `src/forge/proxy/` (proxy OpenAI/Anthropic-compatible).
- **Cơ chế lấy được (từ README, HYPOTHESIS khi áp sang ZAIC):**
  1. Response validation trước khi trả về: call tới tool không tồn tại
     hoặc shape sai bị chặn trước khi thực thi — đúng vai trò validator
     LifeMate, nhưng forge chặn ở tầng proxy còn LifeMate chặn ở tầng trước
     ToolEnv.
  2. Rescue parsing: trích structured call từ format sai (JSON trong
     fence, Mistral `[TOOL_CALLS]`, Qwen `<tool_call>` XML) và re-emit theo
     schema chuẩn — đáng mượn nguyên cho model nhỏ hay viết sai format.
  3. Retry loop với error tracking: nếu validation fail, retry tối đa 3
     lần kèm corrective message — nhưng sang ZAIC phải sửa: retry chỉ cho
     lỗi PARSE/VALIDATION (chưa gọi ToolEnv), KHÔNG retry call đã fail qua
     ToolEnv bằng cùng argument (đó là exact loop, §0.2).
  4. StepEnforcer: `required_steps`, `prerequisites`, `terminal_tool` —
     tương đương "dependency check": một write chỉ được gọi khi
     prerequisite read/step đã xong. Đây là dạng khai báo của precondition,
     rẻ và không cần LLM.
  5. Context compaction: TieredCompact giữ recent 2, budget tokens — áp
     sang LifeMate: giữ transcript ASR + kết quả read gần nhất + danh sách
     call đã làm, nén thought cũ, không nén kết quả read chưa dùng. Lưu ý:
     compaction trong forge được đo là "statistically indistinguishable"
     trên eval suite của forge — không phải trên ZAIC, nên phải A/B lại.
- **Không lấy:** model eval của forge (Ministral-3-8B, 8B — vượt trần LLM
  5B); con số "8B từ single digits lên 84% trên 26-scenario suite của
  forge" là AUTHOR trên suite riêng của forge, không so được với ZAIC;
  proxy mode (LifeMate chạy offline trong Docker, không cần proxy HTTP).

## 6. Hammer — kỹ thuật transplant + ứng viên checkpoint (chưa thăng hạng)

- **Repo code:** https://github.com/MadeAgents/Hammer — **README_READ**
  (commit lúc mở `ff415d9998180b5a68bbfdda3309ec04b472fb49`, Apache-2.0,
  125 stars, tạo 2024-10-02). Thư mục: `client/`, `data/`, `evaluation/`,
  `scripts/`, `train/` (README nhắc `train/data_processing.py` và dùng
  LLaMA-Factory để train — thân file CHƯA đọc, nhãn vẫn README_READ).
  **File cần mở tiếp:** `train/data_processing.py` và các file trong
  `evaluation/`.
- **Paper:** Hammer v1, ICLR 2025, https://arxiv.org/pdf/2410.04587.
  Hai kỹ thuật đã xác nhận từ paper:
  1. **Function masking:** thay tên function/tham số bằng chuỗi ngẫu nhiên
     trong lúc train, ép model đọc description thay vì nhớ tên; tỉ lệ mask
     là siêu tham số — paper ghi mask quá cao làm chậm học trong cùng
     scenario (Seal-Tools) nhưng giúp generalization cross-scenario
     (API-Bank). Khi transplant sang Qwen3-4B: bắt đầu mask thấp (ví dụ
     0,33 theo ký hiệu paper — 33% instance trong batch bị mask), đo trên
     train ZAIC, không copy tỉ lệ mù.
  2. **Irrelevance augmentation:** 7.500 instance từ xLAM-60k mà function
     đúng bị loại khỏi candidate list, label thay bằng danh sách rỗng.
     Paper còn ghi một quan sát quan trọng: fine-tune chỉ trên dữ liệu
     function-calling có thể LÀM GIẢM khả năng irrelevance detection
     (trade-off giữa "gọi đúng" và "biết khi nào không gọi") — đúng với
     LifeMate, nơi ask/refuse là hai lớp riêng. Dữ liệu irrelevance phải
     được trộn với dữ liệu execute theo tỉ lệ đo được trên train, không
     phải cứ thêm nhiều là tốt.
- **Dataset:** `MadeAgents/xlam-irrelevance-7.5k` trên Hugging Face (được
  nhắc trong paper và README Hammer; URL đầy đủ dạng
  https://huggingface.co/datasets/MadeAgents/xlam-irrelevance-7.5k — dạng
  này suy từ tên dataset trong README, cần mở trực tiếp để xác nhận trước
  khi tải).
- **Tách thế hệ — Hammer v1 vs Hammer2.1:**
  - Hammer v1 (ICLR 2025): 7B/1,5B/4B. Hammer-7B **loại trực tiếp** (vượt
    trần 5B). Hammer-4B nằm dưới trần, nhưng base model, licence weights,
    ngày phát hành, format tool và khả năng tiếng Việt đều CHƯA đọc trên
    HF card → giữ ở "ứng viên A/B", chỉ thử sau khi đọc HF card và đo
    trên train.
  - Hammer2.1-3b: https://huggingface.co/MadeAgents/Hammer2.1-3b — thế hệ
    sau, dựa trên Qwen2.5-Coder, các size 0,5/1,5/3/7B, hỗ trợ multi-step +
    multi-turn + irrelevant inspection. **KHÔNG vào shortlist chính** cho
    tới khi: (1) đọc licence trên card HF gốc, (2) xác nhận ngày phát hành
    trước 26/10/2026, (3) xác nhận base Qwen2.5-Coder-3B (licence Qwen
    Research, không phải Apache) có ảnh hưởng gì tới checkpoint phái sinh.
    Licence của Hammer2.1-0.5b được **một mirror (Dataloop) báo là
    CC-BY-NC-4.0 — chưa xác minh trên card HF gốc**. Nếu licence đúng là
    CC-BY-NC, việc dùng trong cuộc thi có giải tiền mặt cần được xem là
    rủi ro pháp lý, không tự kết luận "NC thì được/không được".
- **Tái sử dụng / viết lại:** lấy quy trình data processing (mask +
  irrelevance) và client vLLM/HF usage pattern từ README; phải viết lại
  hoàn toàn phần sinh dữ liệu theo catalog ZAIC (tool ZAIC khác hẳn API
  tổng quát trong xLAM-60k), và viết lại evaluation theo điểm chính thức
  ZAIC (§0.2) thay vì BFCL.

## 7. xLAM-2-3b — đã xác định nguồn kiểm tra, vẫn để sau vì licence

- **Nguồn chính thức cần mở (đã xác định, chưa mở trực tiếp card 3B):**
  HF org Salesforce, model series trong card GGUF
  https://huggingface.co/Salesforce/Llama-xLAM-2-8b-fc-r-gguf (README_READ,
  bảng series liệt kê `xLAM-2-3b-fc-r`: 3B, context 32k (max 128k bằng
  YaRN), base Qwen2.5, hậu tố `-fc` = fine-tune function calling, `-r` =
  research release, tương thích vLLM/Transformers). Paper của series:
  APIGen-MT, arXiv 2504.03601 — https://arxiv.org/html/2504.03601v4.
  Bảng so sánh trong card ghi benchmark BFCL v3 tính đến 04/02/2025 cho các
  model 8B–70B — tức họ 2 đã tồn tại trước tháng 2/2025, trước cutoff,
  nhưng **đây không phải bằng chứng trực tiếp về ngày phát hành của
  checkpoint 3B cụ thể**.
- **Rủi ro licence (SECONDARY nhưng có nguồn):** bài báo
  https://en.zicos.com/tech/i31988340-Decoding-Salesforces-open-source-APIGen-xLAM-for-enterprises.html
  dẫn lời quản lý nghiên cứu Salesforce rằng APIGen/xLAM được phát hành
  dưới "Creative Commons Attribution Non Commercial 4.0 International"
  (CC BY-NC 4.0) — tức KHÔNG cho dùng thương mại. Đối với ZAIC: cuộc thi
  yêu cầu "model mã nguồn mở" — CC BY-NC có được tính là đủ điều kiện hay
  không là câu hỏi phải hỏi BTC hoặc đọc trực tiếp licence trên HF card
  của checkpoint 3B; không được mặc định "có trên HF là open-source".
- **Số BFCL v4 83,7% cho xLAM-2-3b** trên trang Model Spend Arena
  (https://msa.millaguie.net/providers/l-xlam-2-3b.html, SECONDARY,
  first-party test của trang đó, GGUF F16 qua llama.cpp, n=1150) và **ngày
  2026-10-23 trên trang đó là ngày của trang/bài đo, KHÔNG phải ngày phát
  hành model** — không được trích 2026-10-23 làm ngày phát hành, và không
  được so số này với số BFCL phiên bản khác.
- **Tên repo gây nhầm lẫn:** 3B được bảng Salesforce ghi là Qwen-2.5-based,
  trong khi tên "Llama-xLAM-2" gợi Llama-based; phải mở đúng repo trước khi
  dùng.
- **Kết luận:** xLAM-2-3b là ứng viên A/B hợp lý về kích thước (3B, còn dư
  ngân sách cho ASR medium: 3B + 0,77B = 3,77B), nhưng thứ tự ưu tiên vẫn
  sau Qwen3-4B vì (a) licence chưa rõ, (b) base Qwen2.5 tiếng Việt yếu hơn
  Qwen3 về mặt giả thuyết, (c) chưa có đo nào trên train ZAIC.

## 8. APIGen / ToolACE — chỉ lấy quy trình sinh dữ liệu, không lấy checkpoint

- **APIGen:** paper https://arxiv.org/pdf/2406.18518 (PAPER); dataset
  https://huggingface.co/datasets/Salesforce/xlam-function-calling-60k
  (được nhắc trong paper/README, chưa mở trực tiếp trong round 2). Quy
  trình 3 tầng verify: (1) format checking, (2) thực thi thật qua function,
  (3) semantic verification; 3.673 API thực thi được trên 21 category,
  60.000 entry. Phiên bản triển khai bằng Distilabel
  (https://distilabel.argilla.io/latest/sections/pipeline_samples/papers/apigen/,
  SECONDARY) gồm: DataSampler → PrepareExamples → APIGenGenerator (LLM) →
  APIGenExecutionChecker → APIGenSemanticChecker. Sang ZAIC: thay "thực thi
  API" bằng "chạy qua zaic_tools trên state mô phỏng và kiểm tra state cuối
  khớp intent"; dữ liệu không qua tầng 2 thì loại. Không dùng dataset
  xLAM-60k nguyên bản để fine-tune model ZAIC (tool khác hẳn), chỉ dùng quy
  trình.
- **ToolACE:** chỉ ở mức SECONDARY trong vòng 1 (pool 26.507 API,
  verification 2 lớp, fine-tune Llama-3.1-8B — 8B vượt trần). Không có thêm
  bằng chứng mới trong round 2 → giữ nguyên mức SECONDARY, không thăng hạng.
- **FISSION-GRPO (ACL 2026, tháng 7/2026, trước cutoff):** ý chính qua tóm
  tắt tìm kiếm — khi gặp lỗi, mở rộng thành recovery attempt song song
  bằng cách resample rollout từ context đã bổ sung chẩn đoán lỗi; dùng
  Error Simulator được fine-tune để tạo chẩn đoán giống runtime. Repo được
  nhắc là `zxzadm/Fission-GRPO` (tên repo thấy trong snippet, URL đầy đủ
  CHƯA xác minh — không trích URL). Chuyển sang LifeMate ở mức rẻ hơn:
  (a) dữ liệu recovery từ trajectory train (lỗi tool → hành động sửa
  đúng) làm dữ liệu fine-tune hoặc few-shot cho "bước sau lỗi";
  (b) error simulator nội bộ: khi sinh trajectory tổng hợp, cố tình chèn
  lỗi tool rồi chỉ giữ trajectory nào sửa được và về đúng state cuối.
  Không dùng FISSION-GRPO làm "solution": không có checkpoint nào được xác
  minh, và GRPO training vượt ngân sách thời gian tới 16/11.
- **Scaffold kiểu τ-Elicitation KHÔNG chuyển nguyên sang LifeMate** vì
  LifeMate nộp `tool_calls` một lần, không có user thật để đánh vần/read-back
  nhiều vòng (§4). Chỉ mượn ý "verify trước write có thực thể".

## 9. Các ứng viên KHÔNG nên đưa vào shortlist chính

| Ứng viên | Lý do loại / để sau |
|---|---|
| VieGem-ASR (https://huggingface.co/5CD-AI/VieGem-ASR) | Model card tự báo cáo mean WER 6,34 trên 8 tập (scorer của chính tác giả) và tốt hơn PhoWhisper-large (7,21) trên cùng scorer — nhưng **ngày phát hành chưa xác minh**, kích thước/tham số chưa ghi, và scorer là của tác giả. KHÔNG dùng cho tới khi xác minh ngày ≤ 26/10/2026 và đọc config. Số tốt hơn không đủ để vượt qua kiểm tra ngày. |
| Whisper large-v3 nguyên bản, PhoWhisper-large làm mặc định | Large + LLM 4B ≈ 5,55B sát trần, tốn latency; chỉ thử nếu small/medium fail ở slot-error và còn dư thời gian/mẫu (tiêu chí đề xuất, không phải ngưỡng cứng). |
| Model > 5B làm LLM, MoE tổng > 6B, API ngoài lúc inference, checkpoint sau 26/10/2026, đọc `state.json` | Vi phạm luật — loại trực tiếp, không cần A/B. |
| τ³-voice realtime agent, DuplexSLA end-to-end | LifeMate là audio file + ToolEnv offline, không phải hội thoại full-duplex realtime; không lấy agent realtime. |
| Forge proxy mode, ScholarEvolve model 27B, FISSION-GRPO training | Vượt trần hoặc vượt ngân sách thời gian; chỉ lấy pattern harness/dữ liệu. |
| Dùng điểm BFCL/VIVOS/WER để chốt model | Benchmark khác miền, khác cách chấm (không có state_hash gate). |
