# Kế hoạch thi đấu — LifeMate

> Mọi nâng cấp chỉ giữ lại nếu cải thiện **state đúng** (không phải WER, BFCL hay
> F1 trace) trên public test, và không phá ngân sách 30 s/mẫu trên A30.

## Baseline thực dụng (ngày 1–2, trước mọi fine-tune)

```
PhoWhisper-small → transcript → Qwen3-4B instruct (chưa fine-tune)
  → prompt: catalog tool đã lọc theo installed_apps + history + user context
  → constrained JSON + validator schema
  → gọi qua zaic_tools → lấy log + state_hash → nộp
```

- Đo ngay: state đúng, tool F1, giây/sample (ASR riêng, LLM riêng, tổng), tỉ lệ
  mẫu > 30 s, determinism (chạy lại 1 lần với greedy/temperature 0/seed cố định,
  đếm mẫu đổi kết quả).
- **Chưa xác minh trước khi chốt baseline:** HF repo + licence + ngày phát hành của
  PhoWhisper từng size và Qwen3-4B-Instruct-2507 (nguồn thứ cấp ghi 06/08/2025,
  Apache 2.0); catalog tool chính xác từ dữ liệu đã tải.

## Phân tích lỗi — đo theo nhóm, không đo chung chung

| Nhóm lỗi | Cách đếm | Hành động nếu chiếm đa số |
|---|---|---|
| ASR slot-error (tên/tiền/ngày/địa chỉ) | So transcript ASR với `audio_text` (train) hoặc với argument đúng; tính slot-error, không chỉ WER | Entity correction (N-best + candidate list); thử PhoWhisper-medium; chuẩn hoá số/ngày |
| Hiểu yêu cầu sai (sai intent, nhầm app) | Phân loại `used_wrong_tool` (τ-bench) | Retrieval tool theo description, không theo tên; function masking khi fine-tune |
| Chọn tool sai / thiếu tool | So tập tool gold vs nộp | Planner tách bước: liệt kê tool cần → kiểm tra precondition → mới gọi |
| Sai tham số (đúng tool, sai giá trị) | Fuzzy-F1 argument + slot-error | Validator + candidate grounding + constrained decoding |
| Sai thứ tự / thiếu dependency | Trace so với gold, check precondition | ReAct + dependency check + read-before-write |
| Gọi thừa write / side-effect | So state cuối với gold, liệt kê write thừa | Cấm write suy đoán, post-write verification |
| Thiếu thông tin / ngoài phạm vi sai | Confusion matrix execute / ask / refuse | Rule ask/refuse riêng, cân bằng dữ liệu clarify/refuse |
| Parse/format lỗi | Tỉ lệ JSON lỗi, thiếu trường | Constrained decoding + validator + 1 vòng sửa |
| Latency > 30 s | Tỉ lệ mẫu quá giờ | Giảm model ASR, cắt thought, cắt context, faster-whisper, quant |

## Nâng cấp ưu tiên (theo thứ tự, mỗi bước chỉ giữ nếu cải thiện state đúng)

1. **Validator + constrained decoding + read-before-write.** Rẻ nhất, bắt buộc.
2. **Entity correction rule-based** (N-best + candidate list đóng từ tool read).
   Số tiền/ngày không fuzzy đoán — không khớp chính xác thì hỏi lại.
3. **A/B PhoWhisper-small vs medium; A/B Qwen3-4B vs xLAM-2-3b** (chỉ khi xLAM-2
   đã xác minh eligible trước 26/10/2026).
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
| E1 — ASR | PhoWhisper-medium giảm slot-error đủ bù latency | 100 mẫu train | WER tổng + WER thực thể + giây/mẫu | Tiếp tục với bản thắng nếu WER thực thể tốt hơn ≥ 2 điểm; nếu không, lấy bản nhỏ hơn |
| E2 — Baseline | Baseline prompt-only cho đường cơ sở đo được | Toàn bộ public test | F1 + tỉ lệ hash đúng + phân bố 6 nhóm lỗi + thời gian/mẫu | Đây là đường cơ sở cho mọi nâng cấp sau |
| E3 — Validator | Validator chặn lỗi tham số trước khi gọi | Public test, A/B với E2 | Số mẫu sai → đúng, số mẫu đúng → sai | Giữ nếu số mẫu sai → đúng tăng mà không làm mẫu đúng → sai |
| E4 — Irrelevance | Dữ liệu irrelevance tổng hợp giảm false-positive call | Mẫu gold rỗng/thiếu trong public test | False-positive call, F1 mẫu bình thường | Giữ nếu false-positive giảm ≥ 20% mà F1 mẫu bình thường không giảm |
| E5 — Fine-tune | LoRA trên trajectory đã verify cải thiện state đúng | Public test (không đo trên dữ liệu tổng hợp) | State đúng, thời gian/mẫu | Dừng nếu F1 public test không tăng sau 1 vòng hoặc thời gian/mẫu vượt 30 s |

**Chi phí:** chưa có số đo latency trên A30 cho bất kỳ tầng nào — mọi quyết định
latency phải đo trên chính Docker/A30 của submission, không lấy số trên GPU khác
(faster-whisper 4–8× là nguồn thứ cấp trên GPU khác).
