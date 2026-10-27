# Kế hoạch thi đấu — LifeMate

> Mọi nâng cấp chỉ giữ lại nếu cải thiện **điểm chính thức**
> mean(hash đúng ? tool F1 : 0) trên **train held-out** (không phải WER, BFCL,
> hash rate một mình hay F1 trace), và không phá ngân sách 30 s/mẫu trên A30.
> Public test chỉ dùng để đo format/latency/determinism/số call và nộp sanity qua
> kênh chính thức (tối đa 5 file/ngày); không dùng điểm leaderboard public để
> chọn ngưỡng hay chọn hệ thống. Tỉ lệ hash đúng chỉ là metric chẩn đoán.

## Baseline thực dụng — đã hiện thực thành code (đợt LifeMate 2026-10-27)

Triển khai nằm ở `lifemate/` (chạy được, xem `RUN_LIFEMATE.md` ở root
repo); chuyên đề 1–2 là prototype nghiên cứu, `lifemate/` là bản chốt.

```
PhoWhisper-small → transcript → Qwen3-4B instruct (chưa fine-tune)
  → prompt: catalog tool đã lọc theo installed_apps + history + user context
  → constrained JSON + validator schema (validate TRƯỚC call, không ghi log)
  → gọi qua zaic_tools → observation vào prompt NGAY lượt sau mỗi call
  → lấy log + state_hash → nộp
```

- Cấu hình chính: `lifemate/configs/recommended.json` (= baseline +
  grounding theo loại slot, zero tham số thêm). Cấu hình tối giản làm
  mốc đối chiếu: `lifemate/configs/baseline.json` (không grounding).
  Acoustic rescoring, contextual decoding và SFT KHÔNG nằm trong hai
  config này — chúng là đề xuất có thí nghiệm định nghĩa sẵn (P1/P2),
  chỉ vào config chính khi thắng baseline trên train held-out.
- Dữ liệu thật đã đọc (v3.2.0): train 1.545, public_test 634; split
  cố định `lifemate/splits/train_dev_heldout.json` (dev 1.237 /
  held-out 308, seed 42, stratify theo empty/ask_only/ask_after/normal).
  Giới hạn đã ghi: cùng tool-sequence có thể xuất hiện ở cả dev và
  held-out (695 sequence khác nhau cho 1.545 mẫu), nên held-out đo
  khái quát trong họ template, không phải template chưa thấy.
- **Trạng thái chạy thật (không phóng đại):** trên VM dev (không GPU,
  2 CPU, 7,9 GB RAM, không torch/transformers) CHƯA chạy model nào.
  Đã chạy thật: loader + split + adapter + replay gold toàn bộ 1.545
  mẫu train (log và changed-apps khớp label 100%), fake-run +
  check-submission trên public_test, scorer sanity (empty policy trên
  100 mẫu train đầu = 0,06 đúng như dự đoán từ 6 mẫu empty). ASR trên
  CPU đã thử và THẤT BẠI có ghi nhận: faster-whisper cài được (1.2.1)
  nhưng weights PhoWhisper-small trên HF là transformers-format, không
  có model.bin cho CTranslate2; torch CPU wheel host không tới được từ
  VM này nên đường transformers cũng chưa cài được. Chạy model thật
  cần máy local/Kaggle có GPU — xem RUN_LIFEMATE.md §3–§5.

- Đo ngay: state đúng, tool F1, giây/sample (ASR riêng, LLM riêng, tổng), tỉ lệ
  mẫu > 30 s, determinism (chạy lại 1 lần với greedy/temperature 0/seed cố định,
  đếm mẫu đổi kết quả).
- **Đã xác minh một phần trước khi chốt baseline:** Qwen3-4B-Instruct-2507 — HF
  commit `cdbee75`, Apache 2.0, 4,0B tổng / 3,6B non-embedding, 36 layer, context
  native 262.144 (nhiệm vụ giới hạn 16K), non-thinking, series tháng 7/2025
  (KDnuggets 06/08/2025 là **ngày bài báo, không phải ngày phát hành model**).
  PhoWhisper từng size và catalog tool chính xác vẫn cần đối chiếu từ dữ liệu đã tải.

## Phân tích lỗi — đo theo nhóm, không đo chung chung

| Nhóm lỗi | Cách đếm | Hành động nếu chiếm đa số |
|---|---|---|
| ASR slot-error (tên/tiền/ngày/địa chỉ) | So transcript ASR với `audio_text` (train) hoặc với argument đúng; tính slot-error, không chỉ WER | Entity correction (N-best + candidate list); thử PhoWhisper-medium; chuẩn hoá số/ngày |
| Hiểu yêu cầu sai (sai intent, nhầm app) | Phân loại `used_wrong_tool` (τ-bench) | Retrieval tool theo description, không theo tên; function masking khi fine-tune |
| Chọn tool sai / thiếu tool | So tập tool gold vs nộp | Planner tách bước: liệt kê tool cần → kiểm tra precondition → mới gọi |
| Sai tham số (đúng tool, sai giá trị) | Fuzzy-F1 argument + slot-error | Validator + candidate grounding + constrained decoding |
| Sai thứ tự / thiếu dependency | Trace so với gold, check precondition | ReAct + dependency check + selective reads (precondition/grounding, cache) |
| Gọi thừa write / side-effect | So state cuối với gold, liệt kê write thừa | Cấm write suy đoán; không verification read sau write theo mặc định (xem deep-profiles §0.1) |
| Thiếu thông tin / ngoài phạm vi sai | Confusion matrix execute / ask / refuse | Rule ask/refuse riêng, cân bằng dữ liệu clarify/refuse |
| Parse/format lỗi | Tỉ lệ JSON lỗi, thiếu trường | Constrained decoding + validator + 1 vòng sửa |
| Latency > 30 s | Tỉ lệ mẫu quá giờ | Giảm model ASR, cắt thought, cắt context, faster-whisper, quant |

## Nâng cấp ưu tiên (theo thứ tự, mỗi bước chỉ giữ nếu cải thiện state đúng)

1. **Validator + constrained decoding + selective reads.** Rẻ nhất, bắt buộc.
   Validator chạy TRƯỚC khi gọi ToolEnv; lọc call SAU khi đã thực thi là rủi ro
   (xem deep-profiles §0.1) — không tự ý giấu failed call hay read call khỏi submission.
2. **Entity correction rule-based** (N-best + candidate list đóng từ tool read).
   Số tiền/ngày không fuzzy đoán — không khớp chính xác thì hỏi lại.
3. **A/B PhoWhisper-small vs medium; A/B Qwen3-4B non-thinking vs Qwen3-4B
   thinking** (chỉ khi lỗi planning/multi-step chiếm đa số). xLAM-2-3b và
   Hammer2.1-3b chỉ là ứng viên A/B sau khi đọc licence/ngày/repo trên HF card
   gốc — không vào shortlist chính (xem deep-profiles §6–§7).
4. **Router tách riêng / few-shot đúng format** (nếu lỗi argument cao): tách prompt
   chọn tool khỏi prompt điền argument nếu context bị nhiễu; few-shot phải dùng đúng
   format giá trị thật mà tool yêu cầu.
5. **LoRA fine-tune trên dữ liệu tổng hợp đã verify qua `zaic_tools`** (nếu lỗi
   format/schema cao): sinh → verify 3 tầng kiểu APIGen (format → thực thi →
   semantic); chỉ giữ trajectory cho đúng state_hash; cân bằng execute/clarify/
   refuse theo tỉ lệ lỗi thực tế, không copy tỉ lệ blog.
6. **Tối ưu latency:** faster-whisper, quant LLM (INT8/FP16), cắt thought/context —
   nhưng vẫn đo theo sample vì giới hạn là /sample.

## Hướng ít được biết nhưng đáng thử

- **Validator ràng buộc kiểu SCA** từ catalog sẵn có (JSON Schema, `x-ref`,
  `x-one-of`, `installed_apps`) để chặn lỗi tham số trước khi gọi, không tốn thêm
  LLM call — nhưng chỉ chạy ở tầng lập kế hoạch trước khi gọi, đối chiếu thể lệ về
  luật log call trước khi triển khai lọc sau thực thi.
- **Harness milestone/minefield kiểu ToolSandbox:** định nghĩa state trung gian
  phải đạt và state cấm cho mỗi mẫu train, phát hiện agent "đúng hash nhưng đi
  đường nguy hiểm" trước khi nộp.
- **Task-role diagnostics cho ASR:** phân loại lỗi ASR theo vai trò (số/ngày/ID,
  named entity, phủ định, cue ý định) — phủ định là nhóm nguy hiểm riêng ("không
  chuyển tiền" nghe thành "chuyển tiền" sẽ tạo write sai hoàn toàn).

## Để sau hoặc loại bỏ

| Quyết định | Lý do |
|---|---|
| ASR large làm mặc định | Sát trần 6B, tốn latency; chỉ thử nếu small/medium fail ở slot-error mà còn dư ≥ 10 s/mẫu |
| Agent đa LLM | Vượt trần 6B và latency |
| Prompt chứa toàn bộ catalog không lọc | Vượt 16K context và gây nhiễu |
| Fine-tune ASR quy mô lớn ngay từ đầu | Tốn thời gian tới 16/11; chỉ làm nếu phân tích lỗi chứng minh lỗi ASR hệ thống |
| DuplexSLA end-to-end | Không phải dạng bài LifeMate (audio file + ToolEnv offline); size/licence/checkpoint/A30 chưa xác minh |
| Dùng điểm BFCL/VIVOS/WER để chốt model | Benchmark khác miền, khác cách chấm |

## Kế hoạch thử nghiệm

| ID | Giả thuyết | Dữ liệu kiểm tra | Metric | Tiêu chí tiếp tục / dừng |
|---|---|---|---|---|
| E1 — ASR | PhoWhisper-medium giảm slot-error đủ bù latency | 100 mẫu train held-out | Slot-error theo role (negation/number/entity) + giây/mẫu (không dùng WER tổng để chọn) | Tiêu chí đề xuất: giữ bản thắng nếu slot-error giảm rõ và còn dư thời gian/mẫu; nếu không, lấy bản nhỏ hơn. Báo kèm số mẫu từng nhóm. |
| E2 — Baseline | Baseline prompt-only cho đường cơ sở đo được | Train held-out (gold `tool_calls`/`final_state`) | Điểm chính thức mean(hash ? F1 : 0), tỉ lệ ≤ 30 s, giây/mẫu (ASR riêng, LLM riêng), phân bố lỗi | Đây là đường cơ sở cho mọi nâng cấp sau. Public test chỉ đo format/latency, không dùng để chọn hệ thống. |
| E3 — Validator | Validator chặn lỗi tham số trước khi gọi | Train held-out, A/B với E2 | Điểm chính thức, số mẫu sai → đúng, số mẫu đúng → sai | Giữ nếu điểm chính thức tăng mà không làm mẫu đúng → sai tăng đáng kể |
| E4 — Irrelevance | Dữ liệu irrelevance tổng hợp giảm false-positive call | Mẫu gold rỗng/thiếu trong train held-out | False-positive call, confusion execute/ask/refuse, điểm chính thức | Tiêu chí đề xuất: giữ nếu false-positive giảm mà điểm execute không giảm; các ngưỡng số chỉ là đề xuất, không phải kết luận |
| E5 — Fine-tune | LoRA trên trajectory đã verify cải thiện điểm chính thức | Train held-out (không đo trên dữ liệu tổng hợp) | Điểm chính thức, thời gian/mẫu, confusion ask/refuse | Dừng sau 1 vòng nếu điểm chính thức không tăng hoặc thời gian/mẫu vượt 30 s |
| E6 — Read ablation (mới) | Bỏ verification read mặc định và bỏ redundant read (cache) không làm giảm điểm | Train held-out: đếm read theo loại | Điểm chính thức, số call/sample, giây/sample | Giữ cấu hình read có điểm chính thức cao nhất với số call thấp nhất |
| E7 — Loop guard (mới) | Loop guard §0.2 tốt hơn loop → ask/[] cũ | Train held-out, tách riêng mẫu có loop | Điểm chính thức, tỉ lệ loop, confusion ask/refuse | Giữ nếu điểm trên mẫu loop tăng và confusion ask/refuse không bị méo (loop không bị gán nhầm thành ask/refuse) |

**Chi phí:** chưa có số đo latency trên A30 cho bất kỳ tầng nào — mọi quyết định
latency phải đo trên chính Docker/A30 của submission, không lấy số trên GPU khác
(faster-whisper 4–8× là nguồn thứ cấp trên GPU khác).
