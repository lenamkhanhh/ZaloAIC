# Zalo AI Challenge 2026 — Tài liệu nghiên cứu và triển khai

Executable LifeMate handoff: [RUN_LIFEMATE.md](RUN_LIFEMATE.md).
Integration fixes, actual CPU checks and remaining GPU limitations:
[VALIDATION_LIFEMATE.md](VALIDATION_LIFEMATE.md). Research proposals below
are not evidence of model performance on ZAIC.

> **Trạng thái:** Tài liệu nghiên cứu, chưa phải code thi đấu. Chưa có thực nghiệm nào
> chạy trên dữ liệu ZAIC 2026 trong bộ tài liệu này — mọi phương pháp dưới đây là
> **giả thuyết chuyển giao** cho tới khi được đo trên train held-out chính thức (public test không có đáp án kèm theo theo ghi nhận 2026-10-26 — xem competition/datamate.md và gaps.md).
> Đọc `gaps.md` trước khi chốt bất kỳ quyết định nộp bài nào.

## Cuộc thi là gì

Zalo AI Challenge 2026 (mùa 8), chủ đề "Advancing AI Agents for Real Life", nhà tài trợ
LEADTEK Việt Nam, hỗ trợ: aichallenge@zalo.me. Trang chính:
https://challenge.zalo.ai/ — xem chi tiết ở
[competition/rules.md](competition/rules.md) và [competition/schedule.md](competition/schedule.md).

Hai track, hai bài toán khác nhau hoàn toàn — không dùng chung một pipeline:

| Track | Bài toán | Metric quyết định | Trần tài nguyên |
|---|---|---|---|
| **LifeMate** | Nghe yêu cầu tiếng Việt, gọi tool trong app mô phỏng để đạt trạng thái cuối đúng | `state_hash` đúng mới tính điểm; sai hash = 0, rồi mới tính tool-call F1 | Hệ thống < 6B, LLM < 5B, context ≤ 16K, 1× A30, ≤ 30 s/mẫu, model trước 26/10/2026 |
| **DataMate** | Trả lời câu hỏi tiếng Việt trên CSV/Excel/SQLite của doanh nghiệp, theo README + rulebook từng split | Penalized Accuracy: đúng +1, abstain 0, sai −1, không điểm từng phần | Tổng inference ≤ 15B (kể cả model phụ), model trước 01/10/2026, Docker offline, 2× RTX 5090, toàn bộ private test ≤ 6 giờ |

Hồ sơ từng track: [competition/lifemate.md](competition/lifemate.md),
[competition/datamate.md](competition/datamate.md). Metric và cách nộp:
[competition/metrics-submission.md](competition/metrics-submission.md).

## Phát hiện đáng giá nhất

### LifeMate — final state là tất cả, JSON đẹp không cứu được hash sai

1. **Validator + selective reads là nâng cấp rẻ nhất và bắt buộc.** Ép JSON schema lúc
   decode, kiểm tra tên tool/tham số/`x-ref`/`x-one-of`/`installed_apps` bằng code; chỉ
   đọc khi cần xác lập precondition chưa biết hoặc ground thực thể (cache kết quả),
   không đọc lại sau write theo mặc định — xem research/lifemate/deep-profiles.md §0.1
   (ASSUMPTION: evaluator chưa truy cập được, F1 có thể tính cả read thừa). Lỗi format
   hoặc một write thừa đều có thể làm lệch `state_hash` về 0.
   *Mức bằng chứng: giả thuyết chuyển giao, từ bài học AppWorld và τ-bench — xem
   [research/lifemate/solutions-papers.md](research/lifemate/solutions-papers.md).*
2. **ASR phải đo bằng slot-error, không phải WER tổng.** Lỗi ở tên, số tiền, ngày giờ,
   địa chỉ mới là lỗi mất điểm. PhoWhisper-small (244M) + LLM 4B ≈ 4,24B là điểm khởi
   đầu an toàn; medium (769M) + 4B ≈ 4,77B; large (1,55B) + 4B ≈ 5,55B — sát trần và
   rủi ro latency, không lấy làm mặc định.
   *Mức bằng chứng: code-read (repo PhoWhisper, BSD-3-Clause) cho kích thước và WER
   trên VIVOS/VLSP; WER trên audio ZAIC chưa đo — xem
   [research/lifemate/competitions-benchmarks.md](research/lifemate/competitions-benchmarks.md).*
3. **Tách ask khỏi refuse và đo riêng.** Thiếu tham số không ground được bằng tool read
   → `sys.ask_missing_info`; không app nào xử lý được → `[]`. Đoán thay vì hỏi và từ
   chối khi app xử lý được là hai lỗi khác nhau.
   *Mức bằng chứng: giả thuyết chuyển giao từ Hammer (irrelevance augmentation) và
   DelegationBench — chưa xác minh checkpoint/license của Hammer.*
4. **"Gọi thừa cho chắc" là sai lầm trực tiếp.** Một write ngoài yêu cầu đổi state và
   phá hash. Đừng tối ưu số tool call; tối ưu state cuối.
   *Mức bằng chứng: tác giả báo cáo AppWorld (nguồn thứ cấp).*

### DataMate — abstain có kỷ luật thắng trả lời bừa

1. **Ngưỡng hòa vốn lý thuyết là p > 0,5, nhưng ngưỡng thật phải hiệu chuẩn.**
   Kỳ vọng trả lời = 2p − 1 với p là xác suất đúng đã calibration; LLM thường
   overconfident nên confidence miệng không dùng được. Ví dụ minh họa trong nghiên cứu:
   trả lời 100% với độ chính xác 55% cho PA ≈ 0,10; trả lời 60% với độ chính xác 80%
   (abstain 40%) cho PA = 0,36.
   *Mức bằng chứng: suy luận từ công thức PA (portal chính thức) — không phải tuyên
   bố của evaluator; cách evaluator xử lý từng trường hợp vẫn chưa xác minh, xem
   [gaps.md](gaps.md).*
2. **Pipeline baseline phải là: profiler → planner → coder → thực thi → kiểm tra chéo
   → formatter tách riêng.** LLM không tự tính nhẩm; mọi số đều qua code chạy thật
   (SQL/DuckDB hoặc pandas). Formatter phải có test riêng từng type — tính đúng mà
   format sai vẫn bị −1.
   *Mức bằng chứng: giả thuyết chuyển giao tổng hợp từ BIRD, DABstep, SpreadsheetBench.*
3. **Private test có loại hình doanh nghiệp chưa xuất hiện ở train/public.**
   Thí nghiệm leave-one-business-type-out là bắt buộc trước khi fine-tune; nếu PA giảm
   nhiều khi giấu một loại hình thì ưu tiên exploration/profiling trước.
   *Mức bằng chứng: portal chính thức (2026-10-26); mọi ngưỡng số trong repo này
   (ví dụ PA giảm 0,15) chỉ là tiêu chí đề xuất, không phải kết luận thực nghiệm
   hay điều kiện cứng — phải báo kèm số câu hỏi từng nhóm.*
4. **Rulebook của đúng split thắng mọi thứ khác.** Doanh thu, đơn hủy/trả, voucher,
   VAT, tuần Mon–Sun, "tháng này" tới as-of, chi phí bình quân gia quyền, cửa sổ Tết
   23 Chạp–mùng 10 — viết thành helper có unit test, không để LLM "nhớ" rule trong
   prompt. Khi mâu thuẫn: `calendar.csv` của split > rulebook của split > thư viện lịch.
   *Mức bằng chứng: portal chính thức (2026-10-26), cần đối chiếu lại rulebook từng
   split trong gói dữ liệu đã tải.*

## Nguồn đáng đọc nhất (bắt đầu từ đây)

- Portal chính thức LifeMate: https://challenge.zalo.ai/portal/lifemate
- Portal chính thức DataMate: https://challenge.zalo.ai/portal/datamate
- Thể lệ EN: https://dl-challenge.zalo.ai/zalo-ai-challenge-regulations-en.pdf
- PhoWhisper (ASR tiếng Việt, BSD-3-Clause): https://github.com/VinAIResearch/PhoWhisper
- τ-bench (chấm bằng final state, MIT): https://github.com/sierra-research/tau-bench
- BIRD / DABstep / SpreadsheetBench: chỉ dùng để chọn cơ chế, không dùng số leaderboard
  làm mục tiêu — danh mục đầy đủ và trạng thái xác minh ở [sources.md](sources.md).

## Bắt đầu từ đâu

- **LifeMate:** [plans/lifemate.md](plans/lifemate.md) — baseline PhoWhisper-small →
  LLM ≤ 4B instruct (chưa fine-tune) + constrained JSON + validator + selective reads
  → `zaic_tools`, đo bằng điểm chính thức mean(hash đúng ? tool F1 : 0) trên train
  held-out (không đo trên public test, không chọn bằng tỉ lệ hash đúng một mình)
  trước khi fine-tune bất cứ thứ gì.
- **DataMate:** [plans/datamate.md](plans/datamate.md) — profiler + helper từ rulebook +
  formatter có test → Qwen2.5-Coder-7B (7,61B) + 1 chương trình thực thi + ngưỡng
  abstain khởi đầu 0,5 (lý thuyết), rồi hiệu chuẩn mọi ngưỡng trên train_cal tách
  theo business, khóa ngưỡng và đo một lần trên train_holdout — không học/chọn
  ngưỡng trên public test, không dùng điểm leaderboard public để sửa ngưỡng.
- **So sánh và shortlist:** [research/comparison.md](research/comparison.md).
- **Những gì chưa biết:** [gaps.md](gaps.md) — đọc trước khi nộp bài.

## Cấu trúc tài liệu

```
competition/   luật, lịch trình, hồ sơ từng track, metric và submission
research/lifemate/   cuộc thi/benchmark, solutions/papers, ghi chú code, deep-profiles (round 2)
research/datamate/   cuộc thi/benchmark, solutions/papers, ghi chú code, deep-profiles (round 2)
research/search-log.md   nhật ký tìm kiếm round 2
research/comparison.md   bảng so sánh + shortlist từng track
plans/   lộ trình baseline, nâng cấp và thử nghiệm từng track
sources.md   danh mục nguồn đã hợp nhất, kèm trạng thái xác minh
gaps.md   những gì chưa xác minh hoặc chưa truy cập được
```

## Quy tắc trích dẫn trong toàn bộ repo này

- **Official portal (2026-10-26):** dữ kiện ZAIC đã đọc từ portal sau đăng nhập.
- **Author-reported:** tác giả tự báo cáo trên paper/blog của họ, chưa đối chiếu
  leaderboard chính thức.
- **Secondary:** nguồn thứ cấp/tóm tắt; số liệu có thể mâu thuẫn theo phiên bản.
- **Code-read:** đã mở repo/file, ghi commit khi có.
- **Transfer hypothesis:** suy luận chuyển giao, chưa có thực nghiệm trên ZAIC.
- **Unverified:** chưa xác minh — không dùng làm căn cứ chốt submission.
- Không repo nào được gọi là "chạy được" chỉ vì đã thấy source; không phương pháp nào
  được gọi là "hiệu quả trên ZAIC" nếu chưa đo trên dữ liệu ZAIC.
