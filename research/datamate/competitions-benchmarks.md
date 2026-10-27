# DataMate — Cuộc thi và benchmark chuyển giao

> Số leaderboard ở đây chỉ dùng để chọn cơ chế, không dùng làm mục tiêu số học.
> Số thứ cấp mâu thuẫn theo phiên bản/tập đánh giá thì ghi rõ, không chọn một con
> tùy tiện.

## 1. BIRD — họ trung tâm cho text-to-SQL trên schema lớn, bẩn, đa bảng

- **Bài toán:** text-to-SQL trên database thật, bẩn, nhiều bảng — gần DataMate ở
  chỗ schema không sạch, cần liên kết giá trị thực tế, không chỉ tên cột.
- **Khác DataMate:** BIRD chấm execution accuracy (đúng/sai), không có rulebook
  nghiệp vụ, lịch âm, output type đa dạng, hay PA (sai bị trừ). Vì vậy selector của
  DataMate không được chọn "candidate hay nhất" mà phải chọn "trả lời hay abstain".
- **Các pipeline (secondary, mỗi cái là một họ con, không phải một bảng xếp hạng
  thống nhất):**
  - **RSL-SQL** — schema linking, information augmentation, binary candidate
    selection, self-correction + retrieved in-context examples. Nguồn thứ cấp nói
    67,2% trên BIRD và 87,9% trên Spider với GPT-4o. Code được nêu là
    https://github.com/Laqcce-cao/RSL-SQL — **chưa mở và xác minh license trong
    các phiên nghiên cứu, kiểm tra trước khi tái sử dụng.**
  - **CHESS** — 4 agent: information retriever, schema selector, candidate
    generator, unit tester; ~20 LLM call/câu hỏi trong một bản mô tả (3 candidate
    × 5 unit test). Một bản tóm tắt thứ cấp ghi 71,1% EX trên BIRD test với model
    mở — **chưa đối chiếu leaderboard chính thức, không trích làm kết quả đã xác
    minh.** Chi phí này phải cân đối với giới hạn 6 giờ private test của DataMate.
  - **BASE-SQL** — baseline mã nguồn mở: M-Schema, schema linking, candidate
    generation, SQL revision, SQL merge revision. Paper:
    https://arxiv.org/html/2502.10739v1 . Giá trị: kiến trúc gọn, dễ tái hiện bằng
    model nhỏ. Kết quả tác giả tự báo cáo: Qwen2.5-Coder 32B từ 56,84% lên 67,47%
    trên BIRD dev sau đầy đủ các bước; Spider test 88,87% — model 32B vượt luật
    DataMate, chỉ chuyển giao pipeline.
  - **CHASE-SQL / XiYan-SQL / Agentar-Scale-SQL** — họ "nhiều candidate + selector
    học được"; một bản tổng hợp thứ cấp nêu 73,0% / 75,63% / 81,67% EX trên BIRD
    test — **không so sánh trực tiếp được** vì khác thời điểm, backbone và tập
    đánh giá; giá trị là nguyên lý "sinh nhiều → chọn bằng thực thi + selector".
- **Bài học phòng ngừa:** lỗi chính của BIRD không phải cú pháp mà là schema lớn,
  join ngầm, fan trap (join đơn hàng 1–nhiều với dòng hàng rồi SUM sẽ nhân đôi),
  thiếu định nghĩa nghiệp vụ — đúng vai trò của rulebook trong DataMate.

## 2. Spider 2.0 — schema thật, task dài (đã sửa round 2)

- **Bài toán và nguồn chính thức:** Lei và cộng sự, ICLR 2025, arXiv 2411.07763
  — https://arxiv.org/pdf/2411.07763. **632 task** enterprise, trung bình
  **812 cột**, ground-truth SQL trung bình 144 token, hệ thống gồm
  SQLite/DuckDB/BigQuery/Snowflake. Ba setting (theo tổng hợp thứ cấp DeepWiki,
  ghi là Secondary): Snow 547 task (miễn phí), Lite 547 task, DBT 68 task.
  Repo chính thức được nhắc trong các tổng hợp thứ cấp là xlang-ai/Spider2
  (chưa mở trực tiếp trong round 2).
- **Số duy nhất được giữ (paper gốc, cùng một agent, cùng paper):** baseline
  o1-preview code agent **21,3% trên Spider 2.0 (full)**, 91,2% Spider 1.0,
  73,0% BIRD. **Đã bỏ con số 17,1%** — không xuất hiện trong abstract/snippet
  round 2 và không được trích nữa cho tới khi xác định được setting (rất có
  thể là một setting khác: Snow/Lite/DBT, hoặc một hệ thống khác). **Quy tắc:
  mọi số Spider 2.0 phải ghi kèm setting + backbone, không trích số trần.**
  GPT-4o 10,1% trên Spider 2.0 chỉ là Secondary, không phải số paper.
- **ReFoRCE** (arXiv:2502.00675, CODE_INSPECTED ở mức file — xem
  [deep-profiles.md](deep-profiles.md) §1): schema compression,
  self-refinement, column exploration; README tự báo cáo 35,83 trên Spider
  2.0-Snow và 36,56 trên Spider 2.0-Lite với backbone o3 — số khác nhau theo
  phiên bản, không chọn con cao nhất, không suy ra PA trên ZAIC. Cơ chế đáng
  mượn: **exploration bằng truy vấn chẩn đoán** — chạy query nhỏ để hiểu dữ
  liệu trước khi viết query chính, trực tiếp áp dụng khi README nghèo nàn.
- **ProSPy** (secondary): 60,15% Lite và 60,51% Snow nhờ profiling + tách SQL và
  Python. Cơ chế đáng mượn: **profiling tự động** trước khi sinh code.
- **PExA** (secondary yếu): một trang tin nói 70,2% trên Spider 2.0 và chấp nhận
  tại ACL 2026 — **chưa xác minh từ arXiv/ACL, không dùng làm kết luận.**

## 3. DABstep — benchmark gần DataMate nhất (dữ liệu + tài liệu nghiệp vụ)

- **Bài toán và nguồn chính thức:** Egg và cộng sự (Adyen × Hugging Face),
  arXiv 2506.23719 — https://arxiv.org/pdf/2506.23719; Space
  https://huggingface.co/spaces/adyen/DABstep; dataset
  https://huggingface.co/datasets/adyen/DABstep. Hơn 450 task trên dữ liệu
  payments/fees + tài liệu nghiệp vụ (SOP/manual) — gần DataMate nhất vì phải
  đọc tài liệu để biết quy tắc tính, giống rulebook của ZAIC.
- **Số duy nhất được giữ (tác giả tự báo cáo, paper gốc):** agent tốt nhất thời
  điểm paper đạt **14,55% trên Hard**. **Đã bỏ các số thứ cấp "77,78% easy /
  9,26% hard (ReAct + Claude 3.5)" và "Cascade 92,22%"** vì không đối chiếu được
  bảng gốc trong round 2; Cascade là vendor tự báo cáo, entry chưa validated —
  không dùng làm mục tiêu hay bằng chứng hiệu quả. Khoảng cách easy–hard cho
  thấy **đọc tài liệu và làm nhiều bước mới là nút thắt, không phải viết một
  câu SQL đơn.**
- **I2I-STRADA** (secondary): https://arxiv.org/pdf/2507.17874 — planning + xử lý
  lỗi khi viết code, nhạy với rule trong SOP. Cơ chế đáng mượn: plan trước khi
  code; khi code lỗi thì sửa theo lỗi thực thi thay vì viết lại từ đầu; trích
  rule từ SOP/rulebook thành assertion kiểm tra được. **Không trích số
  I2I-STRADA nếu chưa đối chiếu bảng gốc, và không so I2I-STRADA với o4-mini
  như cùng một thí nghiệm.**
- **Baseline trong HF Space: KHÔNG phải CODE_INSPECTED** (trang tree fetch về
  không liệt kê được file trong round 2) — xem deep-profiles.md §5.

## 4. SpreadsheetBench — chuẩn hóa output là nguồn lỗi độc lập

- **Bài toán:** 912 instruction, 2.729 test case, bảng có thể hơn 100 cột và 20.000
  dòng; 35,7% có nhiều bảng, 42,7% có bảng không chuẩn.
- **Metric OJ-style:** code phải pass mọi test case cùng cấu trúc mới tính là đúng
  — khắc nghiệt hơn PA của DataMate, nhưng cho thấy chuẩn hóa output (tên cột, thứ
  tự, định dạng số) là nguồn lỗi độc lập với tính toán đúng.
- **SpreadsheetBench 2** (đã xác minh trực tiếp qua arXiv trong round 2 này,
  khác với ghi chú round 2-sources tìm không thấy — xem ghi chú cuối file):
  arXiv 2606.29955 — https://arxiv.org/abs/2606.29955 (submitted 29/06/2026,
  trước cả hai mốc cutoff về mặt ngày cho ý tưởng; không có checkpoint nào từ
  paper này được đề xuất dùng trực tiếp). 321 task workflow doanh nghiệp, trung
  bình 11,8 worksheet và 593,5 lần sửa ô mỗi instance; model tốt nhất đạt
  34,89% tổng thể, debugging chỉ 12,00% (tác giả tự báo cáo); nút thắt chính là
  kiểm tra spreadsheet chưa đủ và chọn ô đích sai.
  **Giới hạn transfer:** SpreadsheetBench yêu cầu *sửa* workbook; DataMate chỉ
  yêu cầu *đọc* và trả đáp án — không mang cơ chế sửa ô sang, chỉ mang cơ chế
  inspection + xác định đích + exact-value checking.
- **SpreadsheetBench gốc** (Ma và cộng sự, arXiv 2406.14991 —
  https://arxiv.org/html/2406.14991v2, site https://spreadsheetbench.github.io):
  912 instruction thật từ forum Excel, 2.729 test case, 35,7% sheet đa bảng,
  42,7% bảng phi chuẩn, bảng tới > 100 cột / 20.000 dòng; điểm OJ-style:
  model dao động 0,05%–23,65% (tác giả tự báo cáo).
- **Chuyển giao:** DataMate không yêu cầu sửa workbook, nhưng bài học "kiểm tra đủ
  sheet/cột, xác định bảng đích trước khi tính, chấm exact value" rất gần với yêu
  cầu exact type/value của DataMate. Profiler phải liệt kê **mọi** sheet, không chỉ
  sheet đầu tiên.

## 5. Các mùa ZAIC trước — chỉ giữ những gì thực sự liên quan

- **ZAIC 2025:** 1.060 đội (secondary). RoadBuddy nhất là CtelAI; AeroEyes nhất
  theo các bài tổng kết là AIO_C3A. **Không tìm thấy repo/write-up chiến thắng
  chính thức của 2 đội này trong các tìm kiếm đã làm — không bịa link, không suy
  ra pipeline của họ.** Bài toán 2025 (video dashcam, cảm biến) cũng không liên quan
  trực tiếp đến LifeMate/DataMate 2026 ngoài bài học chung về "đội thắng thường là
  tổ chức/lab có sẵn pipeline" — chỉ ghi nhận để tránh tìm lại, không đưa vào
  shortlist kỹ thuật.
- **ZAIC 2023 Elementary Maths Solving:** repo xuất hiện trong kết quả tìm kiếm là
  `Reasoning-Lab/Elementary-Math-Solving-Zalo-AI-2023` (tiếp tục pretrain
  Llama-2 7B/Mistral-7B/Zephyr-7B và fine-tune trên dữ liệu toán tiếng Việt) nhưng
  **đường link đầy đủ không có trong kết quả tìm kiếm, chưa xác minh trực tiếp,
  chưa xác minh license.** Transfer sang 2026: thấp — bài toán toán tiểu học khác
  hẳn tabular QA; không đưa vào shortlist.

> **Ghi chú về xung đột SpreadsheetBench 2:** ghi chú round 2-sources
> (tìm bằng search) không tìm thấy bằng chứng cho ID 2606.29955 và đề nghị bỏ
> claim, trong khi ghi chú round 2-datamate trích arXiv 2606.29955 đầy đủ.
> Xung đột này đã được giải quyết bằng cách mở trực tiếp trang arXiv abs
> trong đợt áp dụng này (2026-10-27): tiêu đề khớp đúng 'SpreadsheetBench 2:
> Evaluating Agents on End-to-End Business Spreadsheet Workflows', tác giả Jian
> Zhu và cộng sự, submitted 29/06/2026, abstract khớp các số 321 task / 11,8
> worksheet / 593,5 lần sửa ô / 34,89% / 12,00%. Vì vậy claim được giữ với nhãn
> đã xác minh qua arXiv, thay vì bị bỏ theo đề nghị ban đầu của round 2-sources.
