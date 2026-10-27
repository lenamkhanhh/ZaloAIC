# DataMate — Hồ sơ sâu các ứng viên mạnh (round 2)

> Mọi phương pháp dưới đây là **giả thuyết chuyển giao** cho tới khi đo trên
> held-out của train ZAIC. Không số benchmark nào được dùng làm mục tiêu PA.
> Nhãn: `CODE_INSPECTED` = đã đọc thân file (ghi file, không ghi tên class nếu
> nguồn không thống nhất); `README_READ` = chỉ đọc README; `PAPER_READ` = chỉ
> đọc paper/abstract; `SECONDARY` = nguồn thứ cấp.
> Giao thức đo: mọi thí nghiệm PA đều trên **train held-out tách theo business**
> (xem [../../plans/datamate.md](../../plans/datamate.md) R1–R8). Public test
> không có `answers.jsonl` theo ghi nhận 2026-10-26 — bước xác minh đầu tiên là
> giải nén zip thật và liệt kê file; nếu zip thật có đáp án thì viết lại giao thức.

## 1. ReFoRCE — ứng viên số 1 cho exploration + self-refinement

- **Repo:** https://github.com/Snowflake-Labs/ReFoRCE — **CODE_INSPECTED ở mức
  file** (không trích tên class, vì báo cáo round 2 không thống nhất về tên
  class; kiểm tra lại trước khi trích).
- **File đã đọc (round 2):** `methods/ReFoRCE/agent.py`,
  `methods/ReFoRCE/sql.py`, `methods/ReFoRCE/schema_linking.py`, `LICENSE`
  (Apache 2.0), `README.md`. Paper: https://arxiv.org/pdf/2502.00675.
- **Luồng chạy thực tế (từ code):**
  1. `reduce_ddl()` / schema linking: cắt DDL chỉ còn bảng/cột đã linking —
     trực tiếp giải schema lớn và context dài.
  2. `exploration()`: sinh SQL thăm dò (tối thiểu 3, `max_try = 3`), chạy thật,
     cộng kết quả thành công vào ngữ cảnh cho bước chính.
  3. `self_refine()`: mỗi vòng sinh đúng 1 SQL, chạy thật; kết quả rỗng giống
     nhau 4 lần liên tiếp + `early_stop` thì dừng và xóa file kết quả.
  4. `execute_sqls()` / self-correction: SQL lỗi hoặc rỗng được sửa tối đa 3
     lần; kết quả rỗng thì lần sửa sau bật `simplify = True`; 3 lần thất bại
     liên tiếp thì dừng — guard chống vòng lặp vô hạn, nên copy nguyên.
  5. `SqlEnv`: SQLite chỉ đọc (`mode=ro`), timeout 300 s cho SQLite, phân biệt
     **3 trạng thái: thành công / lỗi / rỗng** — không gộp lỗi và rỗng làm một,
     vì 3 trạng thái này là đầu vào cho quyết định unanswerable/abstain.
- **Số liệu — không chọn con cao nhất:** README tự báo cáo 35,83 (Spider
  2.0-Snow) và 36,56 (Spider 2.0-Lite) với backbone o3; các phiên bản paper cũ
  ghi thấp hơn. Số khác nhau theo phiên bản — không trích một con làm "kết
  quả ReFoRCE", và càng không suy ra PA trên ZAIC. Backbone o3 là API thương
  mại, vi phạm luật offline nếu dùng nguyên bản — chỉ chuyển giao cơ chế.
- **Lấy được gì:** SqlEnv rút gọn (chỉ đọc + timeout + 3 trạng thái); vòng
  execute → sửa tối đa 3 lần → simplify khi rỗng → dừng sau 3 thất bại liên
  tiếp; exploration bằng SQL thăm dò; `reduce_ddl()`; format restriction
  (tương đương formatter tách riêng theo type của DataMate).
- **Phải đổi gì:**
  - Bỏ toàn bộ GPT API (`chat.py`), credential Snowflake/BigQuery, setup
    Spider2 — thay bằng model local hợp lệ + DuckDB/SQLite của business.
  - **Bỏ "random vote" khi hòa.** Dưới PA, hòa → abstain (0 điểm) tốt hơn
    chọn ngẫu nhiên (kỳ vọng âm nếu xác suất đúng < 0,5).
  - Exploration LLM phải đứng sau **exploration xác định bằng code** (đếm
    dòng, distinct values, min/max ngày, tỉ lệ null); chỉ dùng LLM khi chẩn
    đoán xác định không đủ — nếu không exploration tự nó đã tốn hết 6 giờ.
  - Cắt kết quả thăm dò theo **mẫu có chủ đích + aggregate**, không cắt mù
    500 ký tự đầu như code gốc (`csv_max_len = 500`).
- **Thí nghiệm nhỏ nhất:** trên train_holdout tách theo business: baseline
  1 SQL vs + exploration xác định vs + exploration LLM vs + self-refinement
  tối đa 3 lần; đo PA, tỉ lệ abstain, giây/câu hỏi, và tỉ lệ câu đúng bị
  revision làm hỏng. Giữ exploration chỉ khi nó sửa được nhóm lỗi schema
  linking.

## 2. schemagate — README_READ, cơ chế tốt, bằng chứng yếu

- **Repo:** https://github.com/ashishsinha1602/schemagate — Apache 2.0,
  **README_READ** (đã đọc README + LICENSE qua GitHub API; chưa đọc file
  selector — không gắn CODE_INSPECTED).
- **Cơ chế:** chọn bảng trước khi viết SQL, và bảng không được phép thì
  **vắng mặt hoàn toàn khỏi prompt**, không phải xếp hạng thấp. Hỗ trợ
  Postgres/Oracle/MySQL/SQL Server/SQLite, LangChain/MCP; tác giả tự báo
  cáo giảm 75% prompt tokens (chưa đo độc lập).
- **Bằng chứng (tự báo cáo, không phải leaderboard chính thức):** trên BIRD
  Mini-Dev (500 câu, 11 database — không phải BIRD đầy đủ), schemagate +
  Claude Opus 5.5 đạt SQLite 81,0 / PostgreSQL 72,6 / MySQL 72,4; model nhẹ
  hơn thấp hơn nhiều. Claude Opus 5.5 là API thương mại — vi phạm luật
  offline, không dùng số này làm mục tiêu. Tác giả tự cảnh báo: Mini-Dev
  entries đều tự báo cáo, BIRD đã public từ 2023 nên LLM có thể đã thấy dữ
  liệu. Giá trị duy nhất: light model chạy dạng agent có thể vượt light
  model viết 1 query trên một số dialect — nhưng agent không thắng mọi
  dialect, phải đo theo từng loại dữ liệu.
- **Chuyển giao (bỏ phần access control, giữ phần selection):** DataMate
  không có phân quyền người dùng, nhưng có bài toán tương đương: **shortlist
  bảng/cột xác định từ profiler** trước khi đưa cho LLM. Lợi ích: giảm
  context, giảm bảng bịa, giảm join sai. Rủi ro đối nghịch: shortlist quá
  chặt loại mất bảng cần thiết → câu đúng thành abstain/unanswerable sai.
- **Guard bắt buộc:** nếu pipeline với shortlist cho kết quả rỗng/lỗi,
  fallback **một lần** sang schema đầy đủ (có ngân sách thời gian) trước khi
  kết luận unanswerable; đo recall shortlist (tỉ lệ câu mà bảng cần thiết
  nằm trong shortlist) trên train, không chỉ đo PA cuối.
- **Thí nghiệm nhỏ nhất:** trên train_holdout tách theo business: full
  schema vs shortlist xác định (top-k bảng theo profiler + từ khóa câu hỏi)
  vs shortlist + fallback; đo recall bảng, PA, giây/câu hỏi.

## 3. DSR-SQL — PAPER_READ, thiết kế dual-state, không có code dùng được

- **Paper:** https://arxiv.org/html/2511.21402 (27/11/2025). Cơ chế
  Dual-State Reasoning: (1) trạng thái ngữ cảnh thích ứng — nén schema lớn
  thành môi trường gọn, trung thực về ngữ nghĩa; (2) trạng thái sinh tiến
  triển — sinh SQL theo chuyển đổi trạng thái có phản hồi, tự sửa theo lỗi.
  Không post-training, không few-shot theo tác giả.
- **Bằng chứng (tác giả tự báo cáo, đúng split):** 35,28% execution accuracy
  trên Spider 2.0-Snow và 68,32% trên BIRD dev. Tác giả tự cảnh báo: trong
  thời gian review, cả hai benchmark đều nâng cấp phiên bản đánh giá (BIRD
  sửa disambiguation và lỗi gán nhãn) — không đặt số này cạnh số của paper
  khác như cùng một bảng.
- **Trạng thái code:** repo chính thức theo paper (`DMIRLAB-Group/DSR-SQL`)
  **trả 404 qua GitHub API trong round 2**; chỉ task Spider2.0-Lite được công
  bố code đầy đủ, còn Snow và BIRD "sẽ công bố sau khi paper được chấp
  nhận". **Kết luận: không có code DSR-SQL để tái sử dụng; chỉ lấy thiết
  kế dual-state.** Không trích code từ repo fork (ví dụ fork 2 stars tìm
  thấy qua search) như code gốc.
- **Thí nghiệm nhỏ nhất:** chỉ ở mức thiết kế — cài "nén schema trước, sinh
  theo trạng thái có phản hồi sau" dưới dạng hai bước prompt riêng, đo trên
  train_holdout xem bước nén có làm mất bảng cần thiết hay không; nếu có,
  giữ lại bước fallback sang schema đầy đủ như schemagate.

## 4. BASE-SQL — PAPER_READ, ablation là bằng chứng "không phải bước nào cũng giúp"

- **Paper:** https://arxiv.org/html/2502.10739v1. Repo chính thức **chưa xác
  định trong round 2** — không gắn link repo, không gắn nhãn code.
- **Ablation trên BIRD dev (tác giả tự báo cáo, backbone Qwen2.5-Coder 32B
  — vượt luật 15B, chỉ dùng để học thứ tự bước):** baseline 56,84 →
  +M-Schema 58,21 (+1,37) → +Data Samples 59,71 (+1,50) → +Schema Linking
  61,54 (+1,83) → +SFT 64,21 (+2,67) → +SQL Revision 66,04 (+1,83) → +SQL
  Merge Revision 67,47 (+1,43).
- **Bằng chứng ngược, cùng một bảng ablation, backbone DeepSeek-Coder 33B:**
  +Data Samples làm **giảm** từ 49,54 xuống 44,26 (**−5,28**), và +Schema
  Linking làm giảm Spider test 0,51. Data Samples giúp Qwen nhưng hại
  DeepSeek trong cùng nghiên cứu — hiệu ứng phụ thuộc backbone và cách lấy
  mẫu. **Hệ quả cho ZAIC: đo từng bước riêng trên model ZAIC thực tế, trên
  train_holdout tách theo business; không mặc định "thêm bước = tốt hơn".**
- **Chuyển giao:** lấy M-Schema (mô tả schema kèm mẫu giá trị + kiểu) và
  revision/merge revision có giới hạn; bỏ SFT nặng và model 32B; viết lại
  cho Qwen2.5-Coder-7B và cho cả pandas, không chỉ SQL. Revision chỉ chạy
  khi lần đầu lỗi/rỗng/không hợp lý (xem quy tắc revision an toàn trong
  [../../plans/datamate.md](../../plans/datamate.md)), không chạy mặc định
  cho mọi câu.

## 5. DABstep + I2I-STRADA — PAPER_READ + SECONDARY, chưa CODE_INSPECTED

- **Paper chính thức:** Egg và cộng sự (Adyen × Hugging Face), arXiv
  2506.23719 — https://arxiv.org/pdf/2506.23719. Benchmark: > 450 task phân
  tích dữ liệu tài chính thật, kết hợp code + tài liệu nghiệp vụ (SOP/
  manual), đáp án factoid chấm đúng/sai. Space:
  https://huggingface.co/spaces/adyen/DABstep — dataset:
  https://huggingface.co/datasets/adyen/DABstep. Blog chính thức Adyen:
  https://www.adyen.com/knowledge-hub/data-agent-benchmark-for-multi-step-reasoning-dabstep
- **Số duy nhất được giữ (tác giả tự báo cáo, paper gốc):** agent tốt nhất
  thời điểm paper đạt **14,55% trên Hard**. Các số thứ cấp "77,78% easy /
  9,26% hard (ReAct + Claude 3.5)" và "Cascade 92,22%" đã **bỏ khỏi repo**
  vì không đối chiếu được bảng gốc; Cascade là vendor tự báo cáo, entry
  chưa validated — không dùng làm mục tiêu hay bằng chứng hiệu quả. Bài
  học duy nhất rút từ Cascade ở mức tiêu cực: phần thắng nằm ở helper xác
  định + rule đã kiểm chứng, không nằm ở model lớn hơn.
- **Baseline trong HF Space: KHÔNG phải CODE_INSPECTED.** Đường dẫn baseline
  trong paper là `https://huggingface.co/spaces/adyen/DABstep/tree/main/baseline`,
  nhưng trang tree fetch về trong round 2 không liệt kê được file — mọi nhận
  định về code baseline là chưa có; phải mở trực tiếp từng file trong Space
  trước khi tái sử dụng.
- **I2I-STRADA:** https://arxiv.org/pdf/2507.17874 (SECONDARY trong repo
  này). Cơ chế: planning trước khi code + sửa theo lỗi thực thi + nhạy với
  rule trong SOP. **Không trích số I2I-STRADA nếu chưa đối chiếu bảng gốc,
  và không so I2I-STRADA (Claude 3.5) với o4-mini như cùng một thí nghiệm.**
- **Lấy được gì:** (1) trích rule từ SOP/rulebook thành assertion kiểm tra
  được, không để rule nằm trong prompt rồi hy vọng model nhớ; (2) plan ngắn
  trước khi code, và khi code lỗi thì sửa theo lỗi thực thi thay vì viết lại
  từ đầu; (3) developer set có ground truth của DABstep là mô hình đúng cho
  `train_holdout` của ZAIC — nhưng **không được dùng dữ liệu DABstep để
  train model ZAIC rồi coi đó là đo trên ZAIC**; DABstep chỉ là nơi học cơ
  chế và kiểm tra pipeline ngoài miền.
- **Failure modes theo paper (trực tiếp đúng với DataMate):** planning kém,
  code mức thấp thay vì idiom, khó kết hợp reasoning với format chính xác,
  nhạy cảm với prompt — đặc biệt "format chính xác" = formatter theo type.

## 6. Khi nào planner–coder–checker và SQL-vs-pandas cross-check giúp, khi nào hại

Bảng đầy đủ và hai failure case ("chạy được nhưng sai", "checker đồng lõa")
được giữ trong kế hoạch thử nghiệm — xem
[../../plans/datamate.md](../../plans/datamate.md). Tóm tắt điều kiện:

| Bước thêm | Giúp khi | Hại khi |
|---|---|---|
| Planner tách riêng | Câu cần nhiều bảng/rule; câu thiếu dữ liệu cần dừng sớm | Planner sai ở bước đầu khóa luôn đáp án đúng; cùng model mù cùng lỗi |
| Checker sửa 1–2 vòng theo lỗi thực thi | Lỗi cú pháp, sai tên cột, kết quả rỗng do filter quá chặt | Checker sửa code đúng thành sai; checker cùng model "đồng lõa" |
| Multi-candidate 3–5 + lọc thực thi | Candidate khác nhau ở join/filter, thực thi loại được candidate lỗi | Candidate đều chạy được nhưng cho giá trị khác nhau; tốn 3–5× thời gian |
| SQL-vs-pandas cross-check | Hai đường tính độc lập thật sự, logic viết khác nhau | Hai đường chỉ là cùng logic dịch sang 2 ngôn ngữ; hoặc đường yếu kéo câu đúng xuống abstain |
| Self-consistency (vote) | Model không ổn định, cùng prompt cho đáp án khác nhau | Vote củng cố đáp án sai có cùng hiểu sai hệ thống; tốn thời gian |
| Exploration | README nghèo, schema mới, cột lạ | Tốn context/thời gian; exploration query sai làm nhiễm ngữ cảnh |
| Fine-tune/SFT | Đủ cặp train có kiểm chứng thực thi; model yếu ở format/schema linking | Overfit loại hình train; checkpoint phái sinh chưa rõ cách tính cutoff |

**Quy tắc revision an toàn dưới PA (đề xuất, chưa phải luật BTC):**
revision chỉ chạy khi lỗi thực thi, kết quả rỗng, vi phạm rule assertion,
vi phạm as-of/đơn vị, hoặc kết quả ngoài khoảng hợp lý từ profiler; tối đa
2 vòng sửa, mỗi vòng kèm lỗi thực thi cụ thể, không sửa mù; sau khi hết vòng
sửa: vẫn lỗi/rỗng → abstain (0), không đoán giá trị; hai đường tính mâu
thuẫn và không giải quyết được → abstain, không chọn ngẫu nhiên; ghi log
mọi revision (code trước/sau, lỗi, kết quả) để đối chiếu Docker rerun.

## 7. Answerability vs abstention — hai quyết định, hai bộ ngưỡng

- **Answerability (đủ dữ liệu hay không):** quyết định xác định, dựa trên
  profiler + rulebook, không dựa trên confidence của LLM. Điều kiện đủ:
  (a) mọi bảng/cột cần thiết tồn tại trong profiler của business đó,
  (b) có giá trị trong cửa sổ thời gian của câu hỏi (tới as-of),
  (c) rule cần thiết có trong rulebook của split đó. Thiếu bất kỳ điều kiện
  nào → `unanswerable`. **Không gộp abstain thành unanswerable để "ăn" +1:**
  nếu câu đó thực ra trả lời được mà hệ thống báo unanswerable thì vẫn mất
  điểm theo khung (điểm này vẫn UNVERIFIED về cách evaluator tính — xem
  [../../gaps.md](../../gaps.md) Q-D2).
- **Abstention (đủ dữ liệu nhưng không chắc phép tính):** quyết định xác
  suất, dựa trên tín hiệu đã calibration trên `train_cal` tách theo
  business (xem kế hoạch R-CAL trong plans). Tín hiệu phải bao gồm **tín
  hiệu về bằng chứng** (schema coverage, số dòng sau filter, distinct
  values, rule có trong rulebook không), không chỉ confidence của model —
  vì confidence không nhạy với lượng bằng chứng (bằng chứng từ nghiên cứu
  abstention trong video QA, arXiv 2601.00138, tác giả tự báo cáo, miền
  khác — chỉ dùng làm cảnh báo, không copy số sang DataMate).
- **Không dùng:** confidence miệng của LLM; retrieval coverage đơn độc
  (AUROC 0,5475 trong nghiên cứu SQuAD 2.0 — gần như đoán mò); logprob thuần
  túy làm tín hiệu duy nhất.
