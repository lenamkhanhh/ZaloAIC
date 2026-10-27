# RUN_LIFEMATE — Baseline LifeMate chạy được (Zalo AI Challenge 2026)

> Tài liệu tự chứa. Đọc file này là đủ để chạy lại toàn bộ pipeline từ
> đầu trên một máy khác. Mọi claim "đã chạy" trong file đều có lệnh và
> kết quả đi kèm; mọi thứ chưa chạy đều ghi rõ là CHƯA CHẠY, không gọi
> kiểm tra mechanics là baseline model.

## 0. Dữ liệu nằm ở đâu — và làm sao lấy lại đúng phiên bản

**Dữ liệu KHÔNG nằm trong repo này** (không push raw dataset/audio/
weights — đó là quy tắc bàn giao). Trên máy dev của tác giả, dữ liệu
nằm ở `workspace/zaic-data/lifemate/`, nhưng đó KHÔNG phải máy của bạn:
đừng coi file trong workspace đó là đã có trên máy bạn. Tải lại đúng
phiên bản bằng lệnh sau (link từ trang Data của portal sau đăng nhập):

```bash
mkdir -p data/lifemate && cd data/lifemate
curl -L -C - -o train+public_test.zip \
  https://dl-challenge.zalo.ai/2026/lifemate_argfzdgert/train+public_test.zip
# Xác minh (bắt buộc — HEAD 200 không tính là tải thành công):
ls -la train+public_test.zip            # phải đúng 876430231 byte
sha256sum train+public_test.zip         # phải đúng 57d371518996ec70d3af86402b7eba61208093c82955b9807a7ab39604b47320
unzip -t train+public_test.zip          # phải báo "No errors" (27254 entry)
unzip -q train+public_test.zip -d extracted   # -> extracted/train+public_test/ (1,2 GB)
```

Phiên bản đã xác minh: `VERSION` ghi `release: v3.2.0`, build
2026-10-24, `train 1545 / public_test 634`. Lưu ý: lần tải đầu tiên
trên máy dev bị đứt ở 99,4% (curl error 18, còn thiếu 5.276.829 byte)
— luôn kiểm tra size + SHA256, đừng tin progress bar. Nếu SHA khác,
tải lại bằng `curl -C -` (resume) rồi kiểm tra lại.

Từ đây trong tài liệu, `<data>` = thư mục `extracted/train+public_test/`
(chứa `train/` và `public_test/`).

## 1. Cấu hình khuyến nghị — và vì sao chọn nó

**Cấu hình chính: `lifemate/configs/recommended.json`**

| Thành phần | Chọn | Vì sao chọn / vì sao không chọn cái khác |
|---|---|---|
| ASR | PhoWhisper-small (vinai, 0,244B) qua faster-whisper, greedy, `language="vi"` | Đủ nhỏ để còn dư ngân sách; medium/large chỉ thử nếu small thua ở slot-error mà còn dư ≥ 10 s/mẫu (thí nghiệm E1, chưa chạy) |
| LLM | Qwen3-4B-Instruct-2507, HF revision `cdbee75`, Apache 2.0, qua vLLM (fallback transformers), chat template của model, temperature 0, seed 42 | Card-confirmed; tổng hệ thống 4,244B < 6B, LLM 4,0B < 5B, context 16.384 token |
| Prompt/tool format | Catalog đã lọc theo `installed_apps` của mẫu + `sys.ask_missing_info`; mỗi lượt model ra 1 JSON object `{"name","arguments"}` hoặc `{"stop": true}` | Prompt chứa full catalog vượt context và gây nhiễu; public catalog đã có app train không có nên lọc theo mẫu là bắt buộc |
| Grounding | Theo loại slot (tiền/ngày/ID cấm fuzzy; tên NFC exact → fuzzy ≥ 88, biên ≥ 8, ghi rõ backend) | Rule-based, 0 tham số thêm. **Sửa sai 2026-10-27:** candidate do read trả về chỉ chứng minh thực thể CÓ THẬT, không chứng minh đó là thực thể người dùng muốn — span khớp nhiều candidate hoặc context chỉ candidate khác thì AMBIGUOUS, phải dùng slot phân biệt/history/ask, không chọn candidate đầu tiên |
| Agent loop | Observation vào prompt NGAY lượt sau mỗi call; validator TRƯỚC mỗi call; loop guard (call lặp ≥ 2 lần bị chặn trước khi thực thi, replan 1 lần, dừng nguyên trace); tối đa 12 bước | Validator trước call là an toàn vì `validate()` của zaic_tools KHÔNG ghi log, KHÔNG đổi state (đọc code thật). Lọc call SAU khi thực thi là rủi ro vì call đã nằm trong log nộp |
| Reads | Chỉ khi cần grounding/precondition; KHÔNG verification read sau write theo mặc định; read trùng cache-blocked | Read có thể tính vào F1 hay không vẫn UNVERIFIED (Q-L3) — đọc thừa là rủi ro điểm, không phải miễn phí |
| Kết thúc | Model ra `{"stop": true}`, hoặc hết 12 bước, hoặc guard dừng | Dừng thì nộp nguyên trace đã thực thi — không append ask/`[]`, không write dọn dẹp |

**Cấu hình tối giản làm mốc đối chiếu: `lifemate/configs/baseline.json`**
— giống hệt cấu hình chính nhưng tắt grounding. Mọi nâng cấp sau này
chỉ được giữ nếu thắng baseline này trên train held-out bằng metric
chính thức (mean của hash-đúng ? tool-F1 : 0), không phải bằng WER,
BFCL hay hash rate một mình.

**Vì sao KHÔNG chọn các ứng viên đã nghiên cứu:**
xLAM-2-3b-fc-r (irrelevance 57,94 dù relevance 94,44 — đúng tầng
ask/refuse của LifeMate — và licence CC BY-NC chưa xác minh trên card
gốc); Hammer2.1-3b (không có training code, licence/ngày chưa xác
minh, số BFCL chỉ ở dạng ảnh); Hammer-4B (format train single-turn,
không có bằng chứng stateful); Qwen2.5-Coder-7B (7,61B vượt trần LLM
< 5B của LifeMate); agent đa LLM (vượt trần 6B và latency).

**CHƯA nằm trong cấu hình chính (đề xuất, có thí nghiệm định nghĩa
sẵn, chưa đo — đừng trình bày chúng như tính năng đã có):**
acoustic rescoring bằng teacher-forced Whisper logprob (P1, thử đầu
tiên), contextual decoding 2-pass bằng `initial_prompt`/`hotwords`
(P1, thử thứ hai), SFT theo recipe blueprint-first + gold cố định
trước + rejection sampling (P2), PhoWhisper-medium A/B (E1),
verifier không phải LLM (P4, thuộc DataMate).

## 2. Cấu trúc code

```
lifemate/
  config.py            PipelineConfig + configs/baseline.json, recommended.json
  loader.py            Loader theo đúng schema thật (train 1545 / public 634)
  split.py             Split dev/held-out cố định (seed 42, stratify theo class)
  splits/train_dev_heldout.json   dev 1237 / held-out 308 (chỉ id, commit được)
  adapter.py           ZaicEnv — cầu nối duy nhất tới zaic_tools (không đọc state.json)
  grounding.py         Grounding theo loại slot (rule-based)
  agent.py             AgentLoop: observation sau mọi call, validator trước call, guard
  asr.py               FasterWhisperASR + TranscriptOracle (train-only, ghi rõ)
  llm.py               VLLMGenerator / TransformersGenerator / PromptReadingFake (test)
  scoring.py           Scorer theo mô tả portal — KHÔNG phải evaluator chính thức
  run.py               CLI: replay-gold / fake-run / check-submission / score / make-split / infer
  tests/test_lifemate.py   13 test (loader, split, adapter, grounding, scoring, mechanics)
```

Quy tắc bất di bất dịch trong code: không file nào trong `lifemate/`
mở đường dẫn `*_environment/`; chỉ `zaic_tools.ToolEnv` được nạp
state. Agent không bao giờ gọi `get_state()` — hàm đó chỉ xuất hiện
trong diagnostic replay-gold của `run.py`, ghi rõ là diagnostic.

## 3. Yêu cầu phần cứng và cài đặt

| Môi trường | Kết luận |
|---|---|
| Máy dev đã dùng (VM: không GPU, 2 CPU, 7,9 GB RAM, không swap, không torch/transformers) | **KHÔNG chạy được model.** Chỉ chạy được loader/adapter/scorer/test và fake/gold mechanics (§5). Đây là giới hạn đã đo, không phải phỏng đoán |
| Máy chạy model (local/Kaggle) | 1× GPU ≥ 16 GB VRAM (chuẩn chấm là 1× A30; giới hạn 30 s/mẫu đo trên A30, không lấy số GPU khác để kết luận), RAM ≥ 16 GB, ổ trống ≥ 10 GB (data 1,2 GB + model ~8 GB) |

```bash
# Python 3.10+ (khuyến nghị 3.12). Core chỉ cần stdlib + jsonschema (tùy chọn).
pip install jsonschema rapidfuzz   # rapidfuzz tùy chọn (fallback difflib, ngưỡng không tương đương)
# Backend model (chỉ máy GPU):
pip install faster-whisper vllm transformers accelerate
# Model (tải 1 lần, KHÔNG commit vào repo):
#   vinai/PhoWhisper-small (ASR) và Qwen/Qwen3-4B-Instruct-2507 revision cdbee75 (LLM)
```

## 4. Lệnh chạy

```bash
cd <repo>
# Kiểm tra nhanh không cần model (chạy được cả trên máy CPU):
python -m lifemate.run replay-gold --data <data> --n 50
python -m lifemate.run fake-run --data <data> --split public_test --limit 20 --out /tmp/sub.jsonl
python -m lifemate.run check-submission --data <data> --split public_test --submission /tmp/sub.jsonl
python -m unittest discover -s lifemate/tests
python -m unittest discover -s deep-dives/tests

# Chạy đúng mẫu theo ID (thay cho --limit khi cần đúng tập mẫu):
#   --ids: danh sách id, giữ đúng thứ tự liệt kê; id lạ -> lỗi, không chạy lặng.
#   --ids-file: file JSON — danh sách trần, hoặc dict có smoke_ids / ids / probes.
#   --limit (nếu có) cắt ngắn SAU khi chọn theo ID.
python -m lifemate.run infer --data <data> --split train \
  --config lifemate/configs/recommended.json \
  --ids train_0025,train_0016,train_0049,train_0004,train_0019 \
  --out smoke_submission.jsonl
# Cùng nhóm smoke-5 (bộ probe dev của ZAIC2) qua file probe:
python -m lifemate.run infer --data <data> --split train \
  --config lifemate/configs/recommended.json \
  --ids-file dev_probe_ids.json --out smoke_submission.jsonl
# Lọc điểm theo ID (score chỉ tính các dòng có id trong danh sách):
python -m lifemate.run score --data <data> --split train \
  --submission smoke_submission.jsonl \
  --ids train_0025,train_0016,train_0049,train_0004,train_0019

# Chạy inference thật (cần GPU + backend §3):
python -m lifemate.run infer --data <data> --split public_test \
  --config lifemate/configs/recommended.json --out submission.jsonl
# Đánh giá trên train held-out (dùng split file; xem §6 về giới hạn metric):
python -m lifemate.run infer --data <data> --split train \
  --config lifemate/configs/recommended.json --out heldout_sub.jsonl
python -m lifemate.run score --data <data> --split train --submission heldout_sub.jsonl
```

Định dạng submission (theo README trong gói dữ liệu): UTF-8 JSONL,
mỗi dòng `{"id": ..., "tool_calls": [...], "state_hash": ...}` với
`tool_calls` = `env.get_tool_calls()` và `state_hash` =
`env.get_state_hash()`. Một dòng cho mỗi mẫu của split. Lịch sử user
trên public_test không có transcript nên `infer` tự transcribe cả
audio history trước khi build prompt (xem `run.py`).

## 5. Phần đã chạy thật — kết quả và log

Chạy trên máy dev CPU-only ngày 2026-10-27 (lệnh ở §4, không model):

- **Tải + xác minh data:** 876.430.231 byte, SHA256 khớp §0,
  `unzip -t` không lỗi, giải nén 1,2 GB. (Lần tải đầu đứt ở 99,4%,
  resume bằng `curl -C -` mới đủ — xem §0.)
- **Loader:** train 1.545 / public 634, đúng key-set; public không có
  label/audio_text; catalog train 147 tool / public 122 tool; audio
  WAV 16 kHz mono 16-bit (stdlib wave, 4 file mẫu).
- **Split:** dev 1.237 / held-out 308, stratify empty 89/22,
  ask_only 48/12, ask_after 126/31, normal 974/243; history trung bình
  4,52 / 4,51 lượt. File `lifemate/splits/train_dev_heldout.json`.
- **Replay gold toàn bộ train (1.545 mẫu):** log tool_calls khớp label
  1.545/1.545; changed-apps khớp `label.final_state` 1.545/1.545.
  Đây là kiểm chứng adapter + semantics của zaic_tools, KHÔNG phải
  điểm của model.
- **Fake-run + check-submission (public_test, 20 mẫu):** 0 mismatch
  khi replay lại submission (submission tự nhất quán).
- **Scorer sanity (empty policy, 100 mẫu train đầu):** mean 0,06,
  hash_rate 0,15, đúng như dự đoán (6 mẫu empty → 1,0; còn lại 0) —
  chứng tỏ scorer tính đúng, không phải model đạt 0,06.
- **Test:** `lifemate/tests` 13/13 pass; `deep-dives/tests` 54/54 pass
  (sau khi sửa observation sau mọi call + test bắt generator đọc ID
  từ prompt; 2 lần test tự sai đã sửa theo semantics/code, ghi trong
  log đợt này).
- **Thử ASR trên CPU — THẤT BẠI, có ghi nhận:** faster-whisper 1.2.1
  cài được nhưng weights PhoWhisper-small trên HF là
  transformers-format (không có `model.bin` cho CTranslate2) nên load
  lỗi; torch CPU wheel host không tới được từ VM này (read timeout)
  nên đường transformers cũng chưa cài được. Kết luận: không chạy ASR
  thật trên VM này; cần GPU/Kaggle theo §3.

## 6. Phần CHƯA chạy — và bước tiếp theo chính xác

1. **Chạy inference thật trên GPU** (local/Kaggle, §3–§4): `infer`
   với `recommended.json` trên train held-out (308 mẫu) trước, lấy
   metric chính thức + giây/mẫu + phân bố lỗi theo nhóm trong
   `plans/lifemate.md` (ASR slot-error, sai intent, sai tham số, sai
   thứ tự, ask/refuse confusion). Baseline prompt-only
   (`baseline.json`) chạy cùng held-out để có mốc đối chiếu.
2. **Chỉ sau bước 1 mới xét nâng cấp**, theo thứ tự P1/P2: acoustic
   rescoring → contextual decoding → SFT blueprint-first; mỗi bước
   giữ lại chỉ khi thắng baseline trên held-out.
3. **Chốt public submission:** chạy `infer` trên toàn public_test,
   kiểm tra format bằng `check-submission`, nộp sanity qua kênh chính
   thức (tối đa 5 file/ngày) — public chỉ đo format/latency, không
   dùng để chọn hệ thống.
4. **Câu hỏi evaluator vẫn mở** (gaps.md): Q-L1 (cách chấm ask),
   Q-L3 (read có tính F1 không), Q-L5 (hết vòng lặp nộp gì). Scorer
   trong `lifemate/scoring.py` đếm mọi call đã nộp (kể cả read và
   call bị từ chối schema) vì chúng đều nằm trong trace — nếu evaluator
   thật loại read thì điểm scorer là bi quan, không phải lạc quan.
   Đừng gửi câu hỏi cho ban tổ chức khi chưa có phê duyệt của bạn.

## 7. Những gì đã thay đổi so với repo trước đợt này

- Sửa review còn lại: (a) observation vào prompt sau MỌI call (cả
  `deep-dives/01` và `lifemate/agent.py`), test bắt generator đọc ID
  từ prompt thay vì trả sẵn ID theo bước; (b) sửa claim RSL-SQL sau
  khi đọc lại code gốc tại HEAD fb1dcf0 — `execute_sql` PHÂN BIỆT
  được lỗi/rỗng qua trường thứ ba (`(0,0,"")` vs `(0,0,error)`), lỗi
  thật ở trigger bước 4 bỏ qua trường đó; COUNT=0 không bị ảnh hưởng
  (trả về 1 dòng) — xem `research/round3-p3` §2.6 và
  `deep-dives/research-updates` §3 đã sửa; (c) sửa tiền đề
  candidate=ground truth thành candidate=thực thể có thật, intent do
  agent quyết (xem `deep-dives/02` appendix + `lifemate/grounding.py`);
  (d) đồng bộ README/kế hoạch theo bản chốt (`competition/lifemate.md`,
  `plans/lifemate.md`, file này).
- Tài liệu nghiên cứu mới vs tính năng đã hiện thực được phân biệt rõ
  trong §1 và §6 của file này — nghiên cứu P1–P5 vẫn nằm ở
  `research/round3-p*.md`, không tự biến thành code.
