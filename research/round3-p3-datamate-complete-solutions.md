# Round 3 — Ưu tiên 3: DataMate — solution hoàn chỉnh để đối chiếu kiến trúc

> Nghiên cứu bổ sung cho repo ZaloAIC, mốc so sánh commit `8d4721e`.
> KHÔNG viết vào repo trong đợt này; file này là bản nháp research tại
> `~/workspace/research_notes/round3-p3-datamate-complete-solutions.md`.
> Mọi số benchmark dưới đây là **tác giả tự báo cáo** trên benchmark gốc
> (BIRD/Spider 2.0/DABstep), không phải số trên ZAIC, không dùng làm mục
> tiêu PA. Nhãn: `CODE_READ` = đã đọc thân file (ghi file + commit);
> `PAPER_READ` = chỉ đọc paper; `SECONDARY` = nguồn thứ cấp.
> Ràng buộc DataMate nhắc lại: QA tiếng Việt trên CSV/Excel/SQLite,
> tổng tham số inference ≤ 15B, model công bố trước 01/10/2026, Docker
> offline hoàn toàn, toàn bộ private set ≤ 6 giờ trên 2× RTX 5090.

## 1. Repo đã biết gì, và khoảng trống chính xác cần khép

Repo ở `8d4721e` đã có (xem `research/datamate/{code-notes,solutions-papers,
deep-profiles,competitions-benchmarks}.md` và `deep-dives/03`):

- Pipeline 7 bước của riêng repo: profiler xác định → planner → coder
  (SQL DuckDB/SQLite và/hoặc Python) → executor → checker (sửa 1–2 vòng)
  → cross-check SQL-vs-pandas → formatter theo type → trả lời /
  unanswerable / abstain theo ngưỡng calibration trên `train_cal`.
- ReFoRCE là implementation nổi bật nhất, nhưng round 2 chỉ ghi
  `CODE_INSPECTED ở mức file` mà không thống nhất tên class, và mô tả
  vòng sửa/exploration ở mức tóm tắt.
- BASE-SQL: chỉ `PAPER_READ`; repo chính thức "chưa xác định".
- CHESS: chỉ mô tả thứ cấp (4 agent, ~20 lần gọi LLM/câu).
- DABstep baseline: **không phải** `CODE_INSPECTED` — round 2 fetch trang
  tree không liệt kê được file, nên mọi nhận định về code baseline đều
  là chưa có.

Khoảng trống đợt này phải khép, theo thứ tự quyết định:

1. DABstep baseline thực sự chạy cái gì (không phải mô tả)?
2. BASE-SQL có code không, và nếu không, code kế nhiệm nào của cùng nhóm
   mới là thứ tái sử dụng được?
3. CHESS: selector/tester thực sự làm gì trong code, và điểm nào của nó
   là bẫy khi mang sang DataMate?
4. ReFoRCE branch `o3`: luồng thật, khác gì mô tả round 2?
5. Có solution nào khác, đọc được code, mà cơ chế chọn/sửa của nó khác
   biệt đủ để thay đổi quyết định (không phải chỉ thêm một cái tên)?

## 2. Nguồn đã đọc thực sự (URL + commit + file + file đó làm gì)

### 2.1 ReFoRCE — branch `o3`, commit `d2658991`

- Repo: https://github.com/Snowflake-Labs/ReFoRCE — clone
  `--branch o3 --depth 1`, HEAD `d2658991882f06fa0658bb7782ee9ea515fbb10b`.
- License: `LICENSE` trong repo, Apache 2.0 (đọc trực tiếp).
- `methods/ReFoRCE/agent.py` — class `REFORCE` (tên class nay đã xác
  nhận, khác với do dự của round 2):
  - `__init__`: `max_try = 3`, `csv_max_len = 500` (cắt kết quả thăm dò
    ở 500 ký tự — điểm repo đã cảnh báo là cắt mù, giữ nguyên cảnh báo).
  - `execute_sqls(sqls, logger)`: chạy từng SQL thăm dò; SQL lỗi hoặc
    rỗng được sửa tối đa 3 lần, lần sửa sau khi rỗng bật
    `simplify=True` ("simplify some conditions"); sau 3 thất bại liên
    tiếp (`error_rec` 3 số 0 liên tiếp) thì trả về ngay — guard chống
    vòng lặp, đáng copy nguyên.
  - `exploration(task, table_struct, table_info, logger)`: **một lần
    gọi LLM phải cho ≥ 3 SQL thăm dò**, nếu ít hơn thì thử lại tối đa
    3 lần; nếu không có SQL thăm dò nào chạy thành công thì dừng
    exploration (không cố đấm ăn xôi); `pre_info` tích lũy tối đa
    < 100.000 ký tự, quá dài thì thử lại.
  - `self_refine(...)`: mỗi vòng sinh đúng 1 SQL, chạy thật; nếu
    `early_stop` bật và 4 kết quả liên tiếp giống hệt nhau và đều rỗng
    thì xóa file kết quả và dừng; nếu kết quả đã xuất hiện trước đó
    (so sánh qua `results_values`) thì dừng — đây là "self-consistency"
    của ReFoRCE: **dừng khi kết quả lặp lại, không phải bầu chọn đa số**.
    Số vòng tối đa lấy từ `args.max_iter` (mặc định 5, xem `run.py`).
  - `vote_result(...)`: chỉ chạy khi `--do_vote` (mặc định tắt) với
    `--num_votes` mặc định 3, mỗi vote là một lần chạy pipeline độc
    lập. So sánh các CSV kết quả bằng `compare_pandas_table(...,
    ignore_order=True)` + cùng shape. **Điểm quan trọng nhất cho PA:**
    khi hòa (`has_tie`) và không bật `--model_vote` và không bật
    `--random_vote_for_tie`, hàm **trả về mà không copy bất kỳ kết quả
    nào** — tức hệ thống hoãn/không chốt đáp án thay vì chọn ngẫu
    nhiên. Đây là bằng chứng từ code (không phải từ paper) cho quy tắc
    "hòa → abstain" mà repo đã đề xuất.
- `methods/ReFoRCE/sql.py` — class `SqlEnv`:
  - SQLite mở `mode=ro` (`start_db_sqlite`), timeout 300 s qua
    `func_timeout` (`execute_sqlite_with_timeout`).
  - Ba trạng thái phân biệt rõ: thành công (chuỗi CSV), rỗng (chuỗi
    `"No data found for the specified query.\n"`), lỗi (dict
    `{"status": "error", ...}` với tiền tố `##ERROR##`). Không gộp lỗi
    và rỗng — đúng input cho quyết định unanswerable/abstain của repo.
  - Lưu ý: file này import cả `google.cloud.bigquery` và
    `snowflake.connector` ở đầu file; muốn dùng offline phải tách riêng
    phần SQLite, không import nguyên file (kèm credential Snowflake/
    BigQuery trong `run.py`/README — phải bỏ toàn bộ).
- `methods/ReFoRCE/run.py` — các flag mặc định đáng ghi: `--task`
  mặc định `snow`; `--max_iter 5`; `--num_votes 3`;
  `--random_vote_for_tie` là flag chọn vào (mặc định tắt);
  `--do_self_consistency`, `--do_vote`, `--final_choose` đều là flag
  chọn vào, không phải mặc định.
- `methods/ReFoRCE/schema_linking.py` — `reduce_ddl(...)` (cắt DDL
  theo linking, ngưỡng mặc định 200.000 ký tự) và `reduce_columns(...)`.
  Phần này round 2 đã mô tả đúng hướng; đợt này không đọc sâu thêm vì
  nó không thay đổi quyết định kiến trúc.
- README (cùng commit): tự báo cáo 35,83 (Spider 2.0-Snow) và 36,56
  (Spider 2.0-Lite) với backbone o3; đồng thời tự mô tả "majority-vote
  consensus … while deferring ambiguous cases". **Số này đi kèm o3
  (API thương mại) — không chuyển sang model ≤ 15B, không làm mục
  tiêu.**

Sửa mô tả round 2: (a) tên class là `REFORCE`, không còn mập mờ;
(b) exploration không phải "tối thiểu 3" một cách lỏng lẻo mà là điều
kiện cứng kèm retry; (c) "self-consistency" của ReFoRCE không phải
majority vote — majority vote chỉ nằm ở `vote_result` khi bật
`--do_vote`, còn self-refine dừng khi kết quả lặp lại.

### 2.2 DABstep baseline — HF Space, revision `d4431c2e` (lần đầu đọc được code)

- Space: https://huggingface.co/spaces/adyen/DABstep, revision
  `d4431c2e4a695cbe43c33aab2adaa304a37ae64a` (lấy qua HF API ngày
  nghiên cứu; Space có thể cập nhật sau đó — kiểm tra lại revision
  trước khi trích code).
- File đã đọc (qua HF API tree + raw):
  - `baseline/run.py` (290 dòng): vòng chạy chính. Mặc định
    `--model-id openai/o3-mini`, `--max-steps 10`, `--concurrency 4`,
    split `default`/`dev`; mỗi task chạy một agent, ghi `answers.jsonl`
    + `logs.txt`; ở split dev thì chấm ngay bằng
    `dabstep_benchmark.utils.evaluate`.
  - `baseline/utils.py`: `create_code_agent_with_reasoning_llm` và
    `create_code_agent_with_chat_llm` — đều là **smolagents `CodeAgent`
    với `tools=[]`**, tức agent chỉ viết Python, không có tool riêng.
    `open` bị ghi đè bằng `read_only_open` (chỉ cho `mode='r'`) — đây
    là enforcement chỉ-đọc duy nhất của baseline, ở mức hàm `open`
    của Python executor, không phải sandbox OS. `download_context`
    tải đúng 6 file context: `payments.csv`,
    `acquirer_countries.csv`, `merchant_category_codes.csv`,
    `fees.json`, `merchant_data.json`, `manual.md`,
    `payments-readme.md` (5 file dữ liệu + 2 tài liệu, tính cả readme).
  - `baseline/prompts.py`: hai prompt. Prompt reasoning bắt agent theo
    workflow gốc `Explore → Plan → Execute → Conclude`, mỗi bước theo
    `Thought → Code → Observation`, và chỉ cho phép trả `"Not
    Applicable"` **khi đã cạn mọi plan** ("IF AND ONLY IF you have
    exhausted all possibles solution plans"). Prompt task chèn
    `guidelines` của task — tức **rule nghiệp vụ được đọc bằng cách
    dán toàn bộ guideline vào prompt**, không trích thành assertion
    kiểm tra được, không có bước kiểm tra rule sau thực thi.
  - `baseline/constants.py`: `ADDITIONAL_AUTHORIZED_IMPORTS =
    ["numpy", "pandas", "json", "csv", "glob", "markdown", "os"]`.
- Luồng thật: ingestion = tải context (dữ liệu + manual) → không có
  bước profiler/schema linking riêng → agent Python tự khám phá bằng
  code (tối đa 10 bước) → `final_answer(...)` bắt buộc → output là
  chuỗi đáp án, không có formatter theo type, không có cross-check,
  không có abstain theo ngưỡng. Model mặc định là API thương mại.
- License của Space: file `LICENSE` ở root Space tồn tại (nội dung
  chưa đọc kỹ trong đợt này — **không trích license cho DABstep
  baseline**; chỉ dùng code làm tài liệu tham khảo luồng, không copy
  nguyên baseline vào Docker thi đấu).

### 2.3 BASE-SQL — kết luận âm tính có giá trị: repo chính thức KHÔNG có code

- Repo theo paper: https://github.com/CycloneBoy/base_sql — clone
  `--depth 1`, HEAD `065bfe17e5c2cd54816f356eaa7063aa1b65dc04`.
- Cây repo chỉ có `README.md`, `LICENSE`, `image/` (3 ảnh kết quả/
  ablation). **Không có file `.py` nào.** README ghi todo chưa đánh
  dấu: "Organize the code and publish it to github" và "Release
  model".
- Hệ quả: mọi mô tả "BASE-SQL code" từ nay phải dừng ở `PAPER_READ`.
  Không chờ BASE-SQL nữa. Code kế nhiệm dùng được của cùng nhóm là
  CSC-SQL (mục 2.4) — và đó mới là nơi đọc revision/merge revision
  thật.

### 2.4 CSC-SQL — code kế nhiệm của nhóm BASE-SQL (đọc được, có bẫy)

- Repo: https://github.com/CycloneBoy/csc_sql — clone `--depth 1`,
  HEAD `0fafdf3ee7f334bb11653d890b6e818bf813be1d4bc04`.
- License: `LICENSE` trong repo, Apache 2.0 (đọc trực tiếp).
- `src/cscsql/model/pipeline_infer.py` — pipeline 3 chặng, mỗi chặng
  là một lần gọi `infer.py` qua `os.system`:
  1. `table_link`: model chọn bảng, mặc định `n=8`, temperature 0,8.
  2. `sql_generate`: sinh SQL, mặc định `n=8`, temperature 0,8.
  3. `sql_merge`: lấy file vote của chặng 2 làm `selection_vote`,
     sinh SQL mới (không phải chọn A/B) từ 2 draft đứng đầu.
  Ở chế độ `greedy_search`, mỗi chặng chỉ `n=1`, temperature 0 —
  tức pipeline gọn còn 3 lần gọi. Ở chế độ `major_voting`, tổng cộng
  24 lần sample (8×3) — đắt, chỉ hợp lý khi vLLM batch được.
- `src/cscsql/model/infer.py` + `src/cscsql/utils/common_utils.py`
  (`build_merge_generate_prompt`, `extract_merge_schema_from_sql`):
  merge prompt đưa cho model 2 draft SQL + kết quả thực thi của chúng
  + schema rút ra **từ chính 2 draft đó**, rồi yêu cầu sinh SQL mới.
  Điểm này khác majority vote thuần: merge model được phép viết lại,
  không bị khóa vào 1 trong 2 draft — mạnh khi cả 2 draft đều gần
  đúng ở những chỗ khác nhau, nguy hiểm khi nó "hòa trộn" hai lỗi
  thành một SQL mới sai cả hai chiều.
- `src/cscsql/utils/infer_utils.py` — `execute_sql(...)`: chạy SQL
  trong `BEGIN TRANSACTION` rồi `rollback` (không ghi được dữ liệu —
  một dạng guard chỉ-đọc ở mức transaction, áp dụng cho SQLite), timeout
  qua `func_timeout`; `run_eval_major_vote(...)`: bầu chọn theo kết
  quả thực thi (frozenset rows), giữ lại top-2 để đưa vào merge.
- **Bẫy lớn nhất (đọc từ code, không phải suy đoán):**
  `execute_batch_vote_sql_to_result(..., is_train=True)` có nhánh
  chèn gold SQL vào cặp top-2 khi draft sai (đổi `correctness` và
  thay một draft bằng gold, ngẫu nhiên thứ tự). Đây là bước **tạo dữ
  liệu huấn luyện cho merge model**, không phải inference. Ai lấy
  prompt merge của CSC-SQL mà chạy zero-shot với model chưa qua bước
  này thì đang dùng một cơ chế khác, yếu hơn, so với số báo cáo của
  CSC-SQL — và không được trích số CSC-SQL để bảo chứng cho bản
  zero-shot đó.
- Số trên trang HF của model `cycloneboy/CscSQL-Merge-Qwen2.5-Coder-7B-
  Instruct` (SECONDARY, chưa đối chiếu leaderboard độc lập): 71,72%
  execution accuracy trên BIRD test với model 7B. **Chưa xác minh:**
  ngày công bố của checkpoint này trên HF (quyết định nó có qua
  cutoff 01/10/2026 của ZAIC hay không), và nó có phải checkpoint
  merge đã qua GRPO hay chỉ là merge SFT. Vì vậy CSC merge checkpoint
  chỉ nằm ở dạng "ứng viên cần xác minh ngày + license sử dụng",
  không nằm trong shortlist chốt.

### 2.5 CHESS — code thật, 4 agent, và 3 bẫy đã đọc được

- Repo: https://github.com/ShayanTalaei/CHESS — clone `--depth 1`,
  HEAD `3d6e835f858d26885d21d4bc0215aeecf855efbe`.
- License: `LICENSE` trong repo, Apache 2.0 (đọc trực tiếp).
- Luồng thật (đọc `src/main.py`, `src/workflow/team_builder.py`,
  các file agent, và 2 file config `run/configs/`):
  1. **Information Retriever**: `extract_keywords` (LLM) →
     `retrieve_entity` (tìm giá trị thực trong DB) →
     `retrieve_context` (top-5 cột giống câu hỏi nhất theo mô tả
     cột, `top_k: 5` trong config).
  2. **Schema Selector**: `filter_column` → `select_tables` →
     `select_columns`, đều hỏi model (config dùng gpt-4o-mini cho
     filter, gpt-4o cho select bảng/cột — model API, phải thay bằng
     model local khi chuyển giao).
  3. **Candidate Generator**: `generate_candidate` (theo config
     `CHESS_IR_SS_CG.yaml`: `sampling_count: 1` cho mỗi template —
     tức số candidate đến từ nhiều template/config, không nhất thiết
     là sample nhiều lần cùng prompt) → `revise` lặp lại cho tới khi
     không còn candidate cần sửa hoặc hết `max_fixing`.
  4. **Unit Tester** (chỉ trong config `CHESS_IR_CG_UT.yaml`):
     `generate_unit_test` (LLM sinh test ngôn ngữ tự nhiên) →
     `evaluate` (xem dưới).
- `src/workflow/agents/candidate_generator/tool_kit/revise.py` —
  class `Revise`: candidate bị đánh dấu `need_fixing` khi
  `execution_status != SYNTACTICALLY_CORRECT`; `need_to_fix()` dừng
  khi hết `max_fixing`. Prompt sửa nhận SQL cũ + kết quả thực thi đã
  format. Candidate không cần sửa được giữ nguyên — revise không viết
  lại toàn bộ danh sách.
- `src/database_utils/execution.py` — `execute_sql(...)` timeout mặc
  định 60 s (thread + `func_timeout`); `get_execution_status(...)`
  phân biệt 6 trạng thái, trong đó có 3 trạng thái "rỗng" khác nhau:
  `EMPTY_RESULT`, `ZERO_COUNT_RESULT` (COUNT ra 0), `ALL_NONE_RESULT`
  (toàn NULL). **Đây là bằng chứng từ code cho luận điểm của Ưu tiên
  5: COUNT = 0 là một trạng thái riêng, không phải "rỗng", không
  phải "không trả lời được".** CHESS vẫn đưa cả 3 trạng thái vào diện
  cần revise (vì khác `SYNTACTICALLY_CORRECT`) — và đó chính là chỗ
  CHESS có thể sửa hỏng một đáp án 0 đúng thành đáp án khác nếu
  revise không phân biệt chúng (xem §3, bằng chứng ngược).
- `src/workflow/agents/unit_tester/tool_kit/evaluate.py` — class
  `Evaluate`, cơ chế chọn thật gồm 2 lớp:
  1. `execution_based_clustering`: gom candidate theo kết quả thực
     thi (dạng chuỗi của `execution_result`) — tức majority theo
     output, giống MCS/CSC.
  2. LLM chấm điểm từng candidate theo từng unit test (prompt nhận
     schema + câu hỏi + hint + toàn bộ candidate kèm kết quả thực thi
     đã cắt 20 dòng đầu), cộng điểm qua các test, chọn điểm cao nhất,
     hòa thì chọn candidate thuộc cluster lớn nhất
     (`pick_the_best_candidate`).
  **Ba trường hợp suy biến đọc từ code, rất quan trọng:**
  - Chỉ có 1 candidate → điểm tự động là 1, không có chọn lựa thật.
  - Không có unit test nào → candidate đầu tiên điểm 1, không chọn
    lựa thật.
  - Không có candidate nào → chèn SQL giả `"SELECT * FROM
    table_name"` với điểm 0 (placeholder, không được để lọt vào
    submission).
  Nói cách khác, Unit Tester chỉ có ý nghĩa khi có ≥ 2 candidate và
  ≥ 1 unit test; còn lại nó là pass-through đội lốt selector.
- Số tác giả tự báo cáo (paper arXiv 2405.16755, SECONDARY qua README
  của repo): 71,10% trên BIRD test ở cấu hình ngân sách cao, và Schema
  Selector giúp +~2% accuracy đồng thời giảm ~5× token. Con số ~20
  lần gọi LLM/câu hỏi đến từ mô tả thứ cấp độc lập (3 candidate × 5
  unit test + các bước IR/SS/CG/UT), khớp với cấu trúc code nhưng
  **không phải con số đếm từ một lần chạy code** — ghi là ước tính
  cấu trúc, không phải đo.

### 2.6 RSL-SQL — code thật, cơ chế chọn nhị phân + self-correction, có 1 lỗi gộp

- Repo: https://github.com/Laqcce-cao/RSL-SQL — clone `--depth 1`,
  HEAD `fb1dcf02923e5fd89171cc6cfe1ae3e4e5bc3b94`.
- License: `LICENSE` trong repo, Apache 2.0 (đọc trực tiếp).
- Luồng thật, 4 bước nối tiếp bằng file trung gian (không phải agent
  vòng lặp):
  1. `src/step_1_preliminary_sql.py`: SQL sơ bộ.
  2. `src/step_2_information_augmentation.py`: SQL thứ hai sau khi bổ
     sung thông tin (schema/value).
  3. `src/step_3_binary_selection.py` (`prompt_construct` +
     `sql_generation`): đưa cả 2 SQL **kèm kết quả thực thi của chúng**
     cho LLM chọn một — chọn nhị phân bằng LLM, không phải vote.
     Không có vòng lặp: LLM chọn xong là xong bước này.
  4. `src/step_4_self_correction.py`: vòng tối đa 5 lần; mỗi vòng chạy
     SQL qua `src/utils/util.py::execute_sql` (timeout 30 s bằng
     thread); **chỉ sửa tiếp khi `row_count == 0 and column_count
     == 0`**; nếu kết quả có dòng thì dừng và giữ nguyên.
- **Lỗi gộp đọc từ `execute_sql`:** hàm này trả về `(0, 0, error)`
  cả khi SQL lỗi và khi SQL chạy đúng nhưng ra 0 dòng — tức bước 4
  **không phân biệt được "lỗi cú pháp" với "kết quả rỗng"**. So với
  ReFoRCE (3 trạng thái) và CHESS (6 trạng thái), đây là bước lùi về
  mặt thông tin cho quyết định, và là lý do không copy nguyên vòng
  sửa của RSL-SQL sang DataMate: một SQL đúng nhưng ra 0 dòng (đáp
  án COUNT = 0, hoặc danh sách rỗng đúng) sẽ bị sửa cho tới khi ra
  dòng — tức sửa hỏng đáp án đúng. Ngược lại, điểm đáng lấy của RSL:
  chọn nhị phân có kèm kết quả thực thi rẻ hơn nhiều so với Unit
  Tester của CHESS (1 lần gọi LLM thay vì 1 lần gọi cho mỗi test),
  và self-correction chỉ chạy khi cần (không sửa mặc định mọi câu).

### 2.7 I2I-STRADA — chỉ paper, không có code công khai tìm được

- Paper: arXiv 2507.17874 (Sundar và cộng sự, 23/07/2025).
  Kiến trúc: Goal Construction (không nhìn dữ liệu) → Contextual
  Reasoner (gắn schema + SOP) → Workflow Scaffolding (plan toàn cục
  trước khi chạy code) → Adaptive Planning and Executor (chạy code
  trong sandbox, điều chỉnh theo observation) → Communication Handler
  (format đáp án). Điểm chuyển giao duy nhất đủ cụ thể: **plan toàn
  cục trước khi chạy code, và SOP được gắn ở bước Contextual
  Reasoner chứ không phải nhét vào prompt coder** — khớp với Planner
  tách riêng của repo.
- Bảng leaderboard trong paper (dùng để hiệu chỉnh, không dùng làm
  mục tiêu): Mphasis-I2I-Agents 80,56% easy / 28,04% hard (Claude 3.5
  Sonnet); Claude 3.5 Sonnet ReAct baseline 77,78% / 9,26%; o4-mini
  reasoning baseline 76,39% / 14,55%. **Hiệu chỉnh cho repo:** con số
  14,55% hard mà repo đang ghi là "agent tốt nhất thời điểm paper"
  thực ra khớp với dòng o4-mini baseline trong bảng này, trong khi
  I2I-STRADA sau đó báo 28,04% hard — tức "tốt nhất thời điểm paper"
  là cách ghi gây hiểu lầm nếu không kèm ngày/bảng; không dùng 14,55%
  làm mốc "tốt nhất" nữa, chỉ dùng làm mốc baseline.
- Không tìm thấy repo code công khai của I2I-STRADA trong các tìm kiếm
  đợt này (chỉ paper + bảng leaderboard) — ghi là `PAPER_READ`,
  không trích code.

### 2.8 Không đọc sâu thêm (ghi rõ để khỏi tìm lại)

- **CHASE-SQL** (arXiv 2410.01943): paper mô tả multi-path generation
  (divide-and-conquer, chain-of-thought theo execution plan, synthetic
  example) + selection agent so sánh từng cặp bằng model đã fine-tune
  theo preference. Trang lab Stanford chỉ liệt kê paper, không liệt
  kê link code CHASE trong kết quả đợt này — **không gắn code**,
  không dùng số 73,0% BIRD test của nó làm bằng chứng code. Cơ chế
  pairwise selection của nó về bản chất trùng với RSL binary selection
  (chọn 1 trong 2 bằng model) + CSC top-2 merge, nên không thêm quyết
  định mới ngoài việc "selector học được cần dữ liệu preference" —
  và dữ liệu đó DataMate không có.
- **MCS-SQL** (arXiv 2405.07467): chỉ đọc paper (không clone repo
  riêng trong đợt này vì cơ chế của nó đã được code khác bao phủ):
  nhiều prompt → nhiều candidate → lọc lỗi/timeout khi thực thi →
  gom theo kết quả thực thi, giữ query nhanh nhất mỗi nhóm → LLM
  chọn theo multiple-choice (thứ tự theo confidence, vì LLM thiên vị
  đáp án đứng trước) → majority vote qua nhiều lần sample. Số tác giả
  tự báo cáo: BIRD dev 63,4% (GPT-4), Spider dev 89,5% (GPT-4) — model
  API, không chuyển số.
- **DSR-SQL**: giữ nguyên kết luận round 2 — repo chính thức 404,
  chỉ lấy thiết kế dual-state, không có code.

## 3. Bằng chứng ủng hộ và bằng chứng ngược cho 3 kiến trúc

### Kiến trúc A — một chương trình trực tiếp (1 lần sinh + formatter)

Ủng hộ:

- Rẻ nhất và dễ kiểm chứng nhất: 1 lần gọi model cho coder + 0 lần
  gọi cho formatter xác định. Trong ngân sách 6 giờ, đây là kiến trúc
  duy nhất chắc chắn đủ thời gian cho mọi câu hỏi kể cả khi model
  chậm, và là baseline bắt buộc để đo mọi thứ khác (không có A thì
  không biết B/C cải thiện được bao nhiêu).
- DABstep baseline, dù là agent, thực chất chứng minh phần ngược:
  nó không có bước chọn/sửa nào ngoài vòng agent 10 bước, và vẫn là
  baseline chính thức của benchmark gần DataMate nhất — tức "chương
  trình trực tiếp + agent tự sửa trong cùng một vòng" đã đủ để làm
  baseline, không cần pipeline nhiều chặng mới có đáp án.
- CSC-SQL ở chế độ greedy (3 lần gọi, mỗi chặng 1 lần) cho thấy
  pipeline nhiều chặng vẫn có thể gọn nếu mỗi chặng chỉ lấy 1 mẫu —
  tức A và B không cách nhau một trời một vực về chi phí khi tắt
  sampling.

Ngược:

- Không có cơ chế nào bắt lỗi "chạy được nhưng sai": SQL/Python chạy
  ra số, formatter format đúng type, nhưng join sai, filter sai cửa
  sổ, hoặc rule sai vẫn cho ra đáp án — và dưới PA thì đáp án sai
  = −1, tệ hơn abstain = 0. Mọi code đã đọc đều đồng ý ở điểm này
  theo cách riêng: ReFoRCE phải thêm self-refine, CHESS phải thêm
  revise + unit test, RSL phải thêm binary selection + self-correction.
  Không có solution hoàn chỉnh nào trong đợt này chỉ dùng A mà đạt
  số cao trên BIRD/Spider 2.0/DABstep.
- A phụ thuộc hoàn toàn vào chất lượng 1 lần sinh: với model 7B
  (không phải GPT-4/o3), 1 lần sinh là điểm yếu nhất, không phải
  điểm mạnh. BASE-SQL ablation (xem §3B) cho thấy ngay cả pipeline
  đầy đủ cũng chỉ cộng từng bước 1–2 điểm — tức A cách B không xa
  về số, nhưng khoảng cách đó chính là phần PA bị trừ khi sai.

### Kiến trúc B — exploration + một chương trình + sửa lỗi có điều kiện

Ủng hộ (bằng chứng từ code, không phải từ paper):

- **ReFoRCE `execute_sqls`**: sửa có điều kiện theo đúng trạng thái
  (lỗi → sửa lỗi; rỗng → simplify; 3 thất bại liên tiếp → dừng) là
  cơ chế sửa rẻ nhất trong các code đã đọc, vì nó không sửa câu đã
  đúng và không sửa vô hạn. Đây là thành phần duy nhất trong đợt này
  mà bằng chứng code trực tiếp ủng hộ việc copy nguyên (đã trừ phần
  cắt 500 ký tự và phần API).
- **CHESS `Revise`**: chỉ sửa candidate có trạng thái khác
  `SYNTACTICALLY_CORRECT`, giữ nguyên candidate đã đúng — cùng
  nguyên tắc "sửa có điều kiện", và `max_fixing` chặn vòng lặp.
- **RSL-SQL bước 4**: sửa tối đa 5 vòng nhưng chỉ khi kết quả rỗng/
  lỗi — rẻ, nhưng xem bằng chứng ngược về việc gộp trạng thái.
- **BASE-SQL ablation** (paper 2502.10739, tác giả tự báo cáo, backbone
  Qwen2.5-Coder 32B — vượt luật, chỉ dùng để học thứ tự): baseline
  56,84 → +M-Schema 58,21 (+1,37) → +Data Samples 59,71 (+1,50) →
  +Schema Linking 61,54 (+1,83) → +SFT 64,21 (+2,67) → +SQL Revision
  66,04 (+1,83) → +SQL Merge Revision 67,47 (+1,43). Revision và
  merge revision cộng lại +3,26 điểm — tức "sửa sau sinh" là thành
  phần có đóng góp đo được, không phải trang trí. Nhưng xem ngay
  bằng chứng ngược dưới đây trước khi tin con số.

Ngược (bằng chứng ngược mạnh, cũng từ cùng một bảng ablation):

- **Cùng bảng ablation BASE-SQL, backbone DeepSeek-Coder 33B:**
  +Data Samples làm **giảm** từ 49,54 xuống 44,26 (**−5,28**), và
  +Schema Linking làm giảm Spider test 0,51. Tức cùng một bước, đổi
  backbone là đổi dấu tác dụng. Với model ZAIC thực tế (Qwen2.5-Coder
  7B, không phải 32B/33B), không được mặc định "thêm exploration/
  revision = tốt hơn" — phải đo từng bước riêng trên train_holdout
  tách theo business, đúng như repo đã ghi, và đợt này củng cố thêm:
  exploration của ReFoRCE yêu cầu ≥ 3 SQL thăm dò và có thể tốn cả
  vòng retry — với business mới, exploration LLM có thể tốn nhiều
  thời gian hơn cả chương trình chính mà không sửa được lỗi nào nếu
  lỗi nằm ở rule (không nằm ở schema).
- **RSL-SQL gộp lỗi và rỗng** (mục 2.6): sửa có điều kiện chỉ đúng
  khi điều kiện phân biệt được các trạng thái. Copy nguyên vòng sửa
  của RSL sẽ sửa hỏng đáp án COUNT = 0 / danh sách rỗng đúng.
- **CHESS revise trên trạng thái rỗng**: vì CHESS đánh dấu cả
  `EMPTY_RESULT`/`ZERO_COUNT_RESULT`/`ALL_NONE_RESULT` là cần sửa,
  một đáp án 0 đúng cũng bị đưa vào revise — tức B có thể làm hỏng
  câu đúng nếu trigger sửa không loại trừ "rỗng đúng". Đây là lỗi
  cùng họ với RSL, chỉ tinh vi hơn (có phân biệt trạng thái nhưng
  vẫn sửa tất cả trạng thái không phải "đúng cú pháp").
- **Chi phí**: ReFoRCE self-refine tối đa 5 vòng + exploration retry
  tối đa 3 lần + correction tối đa 3 lần mỗi SQL thăm dò — trong
  trường hợp xấu, một câu hỏi có thể tốn gấp nhiều lần A. Với 7B
  local và 6 giờ, B chỉ an toàn nếu (a) exploration xác định bằng
  code chạy trước exploration LLM (repo đã đề xuất), và (b) sửa chỉ
  chạy khi trigger đúng (lỗi/rỗng-sai/không hợp lý), không chạy mặc
  định mọi câu.

### Kiến trúc C — agent / multi-candidate với verification

Ủng hộ:

- **Đa dạng thật sự giúp khi các candidate khác nhau ở chỗ cần
  khác**: CSC-SQL merge cho thấy top-2 theo kết quả thực thi rồi
  sinh lại có thể sửa được trường hợp mỗi draft đúng một nửa;
  CHESS clustering + unit-test scoring cho thấy selector có thể
  dùng thông tin ngoài kết quả thực thi (test ngôn ngữ tự nhiên) để
  phân biệt hai candidate cho cùng một output (trường hợp output
  trùng nhau nhưng SQL khác nhau về mặt ngữ nghĩa — vote thuần sẽ
  không phân biệt được).
- **Vote theo kết quả thực thi là selector rẻ và không cần model
  học thêm**: MCS-SQL (gom theo execution result, giữ query nhanh
  nhất mỗi nhóm, rồi LLM chọn + majority vote), CSC-SQL (top-2 theo
  vote rồi merge), ReFoRCE `vote_result` (so sánh CSV, cùng shape,
  hòa thì hoãn) đều dùng chung nguyên lý này với biến thể khác nhau.
  Đây là thành phần duy nhất của C mà bằng chứng lặp lại ở 3 code
  độc lập — đáng tin hơn các selector học được.
- **CHESS Schema Selector +~2% / −5× token** (tác giả tự báo cáo):
  nếu đúng, phần "chọn schema trước" của C giúp cả A và B, không
  riêng C — tức một phần của C nên được tách ra làm bước chung
  (shortlist xác định từ profiler), không nên đi kèm cả bộ máy agent.

Ngược (bằng chứng ngược đủ mạnh để bác bỏ C nguyên bản):

- **Chi phí gọi LLM**: CHESS ~20 lần gọi/câu (mô tả thứ cấp, khớp cấu
  trúc code: IR + SS + CG + revise + UT generate + UT evaluate);
  CSC-SQL major_voting 24 lần sample; DABstep baseline tối đa 10 bước
  agent. Với model 7B local và 6 giờ, C nguyên bản là kiến trúc duy
  nhất trong 3 kiến trúc có nguy cơ vượt ngân sách ngay cả khi mỗi
  lần gọi đều nhanh — vì số lần gọi nhân với số câu hỏi, và vLLM
  batching không cứu được nếu mỗi câu hỏi phụ thuộc tuần tự vào kết
  quả bước trước (agent loop không batch được theo chiều sâu).
- **Unit Tester suy biến** (đọc từ code CHESS, mục 2.5): khi chỉ có
  1 candidate hoặc 0 unit test, UT là pass-through đội lốt selector.
  Với DataMate, nhiều câu hỏi sẽ chỉ có 1–2 candidate khả thi sau
  lọc thực thi — tức UT thường xuyên rơi vào trường hợp suy biến mà
  vẫn tốn 1–2 lần gọi LLM để sinh test và chấm điểm.
- **Selector LLM "đồng lõa"**: RSL binary selection, CHESS UT
  evaluate, và CSC merge đều dùng cùng một họ model để chọn/sửa
  output của chính nó (hoặc của model cùng họ). Khi lỗi là hiểu sai
  hệ thống (sai rule, sai join, sai cửa sổ), selector có cùng hiểu
  sai sẽ chọn candidate sai một cách tự tin — và PA không tha cho
  sự tự tin này. Không có code nào trong đợt này chứng minh selector
  LLM bắt được lỗi ngữ nghĩa mà generator không bắt được, khi cả hai
  dùng cùng một model nhỏ. Bằng chứng duy nhất chống lại "đồng lõa"
  là khi selector dùng thông tin khác generator: kết quả thực thi
  (vote), rule assertion bằng code, hoặc đường tính thứ hai độc lập
  (SQL-vs-pandas) — tức phần verification nên là code, không phải
  LLM thứ hai.
- **CSC merge cần huấn luyện**: merge model của CSC-SQL được huấn
  luyện trên cặp top-2 có chèn gold (mục 2.4). Dùng prompt merge
  zero-shot với Qwen2.5-Coder-7B gốc là một cơ chế khác, chưa có bằng
  chứng nào trong đợt này cho thấy nó tốt hơn majority vote thuần —
  và nó tốn thêm 1 lần gọi model cho mỗi câu hỏi.

## 4. So sánh 3 kiến trúc và quyết định thay đổi so với 8d4721e

| | A: 1 chương trình | B: exploration + 1 chương trình + sửa có điều kiện | C: agent / multi-candidate + verification |
|---|---|---|---|
| Lần gọi model / câu (7B local, greedy) | 1 | 2–6 (exploration 1 + chính 1 + sửa 0–3, chỉ khi trigger) | 10–24 (CHESS ~20; CSC voting 24 sample; DABstep ≤ 10 bước) |
| Thành phần thực sự tạo cải thiện (theo code đã đọc) | — (baseline) | Sửa theo trạng thái thực thi (ReFoRCE `execute_sqls`); schema rút gọn trước khi sinh (`reduce_ddl`, CHESS SS) | Vote theo kết quả thực thi (MCS/CSC/ReFoRCE vote); shortlist schema (phần tách được của C) |
| Thành phần không có bằng chứng chuyển giao | — | Exploration LLM trước exploration xác định; sửa mặc định mọi câu | Unit Tester LLM (suy biến khi ≤ 1 candidate); selector LLM cùng model; merge zero-shot không huấn luyện |
| Rủi ro lớn nhất dưới PA | Sai mà không biết → −1 | Sửa hỏng câu đúng (trigger sai: rỗng đúng, COUNT = 0) | Tốn hết 6 giờ; selector đồng lõa củng cố đáp án sai |
| Khả năng chuyển sang model 7B | Cao (đây là cách model 7B được dùng trong mọi code) | Cao nếu sửa có điều kiện + exploration xác định trước | Thấp ở dạng nguyên bản (số lần gọi, model API trong code gốc) |

### Quyết định thay đổi (so với 8d4721e)

1. **Kiến trúc chốt cho vòng đầu tiên là B-thu-gọn, không phải C,
   và không phải pipeline 7 bước đầy đủ ngay từ đầu.** Thứ tự triển
   khai mới, theo bằng chứng code:
   1. A (1 chương trình + formatter + profiler xác định) — đo PA,
      giây/câu, và phân loại lỗi trên train_holdout tách theo
      business. Không có số này thì mọi so sánh sau đó đều vô nghĩa.
   2. B1: + shortlist schema xác định từ profiler (CHESS SS tách ra,
      schemagate fallback 1 lần) — đo recall shortlist trước khi đo PA.
   3. B2: + sửa có điều kiện theo đúng 3 trạng thái của ReFoRCE
      (lỗi / rỗng / thành công), tối đa 3 lần, rỗng → simplify, 3 thất
      bại liên tiếp → dừng; **loại trừ rỗng-đúng khỏi trigger sửa**
      (COUNT = 0, danh sách rỗng đã kiểm chứng bằng profiler là
      đáp án hợp lệ — xem Ưu tiên 5, không thuộc đợt này nhưng quyết
      định trigger sửa phải chờ nó).
   4. Chỉ sau khi B2 bão hòa mới thử C-thu-gọn: vote theo kết quả
      thực thi với k = 2–3 (không phải 8 như CSC), và chỉ dùng
      merge/vote khi các candidate cho output khác nhau; khi các
      candidate đồng thuận thì không tốn thêm lần gọi nào cho selector.
2. **Bỏ BASE-SQL khỏi danh sách "code cần đọc"** — repo chính thức
   không có code (mục 2.3). Thay bằng CSC-SQL ở vai trò "code tham
   khảo cho merge", với cảnh báo huấn luyện gold-injection (mục 2.4).
   Nếu sau này cần merge model thật, phải huấn luyện/tinh chỉnh riêng
   trên cặp top-2 của ZAIC train (không dùng checkpoint CSC nếu chưa
   xác minh ngày cutoff).
3. **Bỏ Unit Tester dạng LLM khỏi shortlist selector.** Lý do từ
   code CHESS: suy biến khi ≤ 1 candidate hoặc 0 test, và không có
   bằng chứng nào cho thấy nó bắt lỗi ngữ nghĩa tốt hơn vote theo
   kết quả thực thi + rule assertion bằng code. Thay selector LLM
   bằng: vote theo output → nếu hòa thì abstain (theo
   `vote_result` của ReFoRCE khi tắt random vote) → nếu cần phân
   biệt hai candidate cùng output thì dùng rule assertion + đường
   tính thứ hai bằng code, không dùng LLM chấm điểm.
4. **DABstep baseline không còn là "chưa đọc"** — nó là agent Python
   tối đa 10 bước, rule dán vào prompt, không có formatter/checker/
   abstain. Quyết định thay đổi: **không copy DABstep baseline** làm
   khung DataMate; chỉ lấy 2 chi tiết: (a) `read_only_open` làm mẫu
   cho enforcement chỉ-đọc ở mức hàm (bổ sung cho DuckDB read-only
   của repo, không thay sandbox); (b) guideline của task phải được
   đưa vào prompt coder **và** đồng thời trích thành assertion code
   (baseline chỉ làm nửa đầu, và đó chính là chỗ nó yếu).
5. **Sửa cách ghi số DABstep trong repo**: 14,55% hard không còn được
   ghi là "agent tốt nhất thời điểm paper" — nó khớp dòng o4-mini
   baseline trong bảng I2I-STRADA; I2I-STRADA báo 28,04% hard sau đó.
   Cả hai đều là số leaderboard theo thời điểm, không phải mốc cố
   định. (Hiệu chỉnh này thuộc về file competitions-benchmarks.md /
   deep-profiles.md §5 khi parent agent cập nhật repo — không sửa
   trong đợt research này theo đúng phân công.)
6. **Không thay đổi (giữ nguyên từ 8d4721e, nay có thêm bằng chứng
   code)**: profiler xác định trước mọi bước LLM; helper cố định
   viết từ rulebook + unit test; formatter tách riêng theo type;
   hòa → abstain thay vì random vote; ngưỡng calibration chỉ trên
   train_cal, không học trên public test.

## 5. Phép thử nhỏ nhất để phân biệt các phương án (trên train ZAIC)

Chạy trên `train_holdout` tách theo business (không dùng public test
để chọn), cùng một checkpoint Qwen2.5-Coder-7B-Instruct, cùng một
formatter, đo **PA (không chỉ accuracy), tỉ lệ abstain, giây/câu**,
và phân loại lỗi (schema / join / rule / format). Mỗi bước chỉ giữ
khi PA tăng và giây/câu còn trong ngân sách 6 giờ khi nhân với số
câu private (giả định N phải ghi rõ khi chạy; không mặc định N).

1. **A vs B2 (sửa có điều kiện)**: 50–100 câu holdout. A: 1 SQL/Python.
   B2: A + sửa tối đa 3 lần chỉ khi lỗi/rỗng-sai, rỗng → simplify.
   Phân biệt: B2 thắng nếu số câu "lỗi → đúng" vượt số câu "đúng →
   hỏng do sửa" và PA tăng; nếu B2 chỉ sửa được lỗi cú pháp mà model
   7B ít mắc thì bỏ B2, giữ A + formatter.
2. **Shortlist có/không fallback**: cùng tập câu, đo recall bảng/cột
   cần thiết trong shortlist trước khi đo PA. Phân biệt: shortlist
   chỉ được giữ nếu recall ≥ ngưỡng do parent đặt (đề xuất: đo và
   báo, không đặt số mù ở đây) và PA không giảm; nếu recall thấp thì
   shortlist là nguyên nhân gây unanswerable sai, phải nới hoặc bỏ.
3. **Vote k = 2–3 vs chọn nhị phân bằng LLM**: trên tập câu mà các
   candidate cho output khác nhau (tập con, không phải toàn bộ
   holdout — vì khi đồng thuận thì không cần chọn). Phân biệt: vote
   theo output thắng nếu PA cao hơn và rẻ hơn; chọn nhị phân bằng
   LLM chỉ thắng khi nó sửa được trường hợp "cùng output, khác ngữ
   nghĩa" — đếm trực tiếp số câu đó, nếu ≈ 0 thì bỏ selector LLM.
4. **Merge zero-shot vs vote thuần**: cùng top-2 candidate. Phân
   biệt: merge chỉ được giữ nếu số câu "cả 2 draft sai một nửa →
   merge đúng" vượt số câu "merge hòa trộn thành sai mới"; nếu
   không, merge zero-shot bị loại (vì merge có huấn luyện của CSC
   không áp dụng được ở đây).
5. **Trigger sửa trên rỗng**: tập câu có đáp án đúng là 0 hoặc rỗng
   (lấy từ train_holdout, lọc bằng gold). Phân biệt: pipeline nào
   giữ nguyên đáp án 0/rỗng đúng thì đạt; pipeline nào sửa nó thành
   đáp án khác thì bị loại ngay, không cần đo PA tổng.

Mỗi phép thử đều có thể chạy bằng code thuần + model 7B local, không
cần training dài, không cần GPU A30 (chỉ cần 1 GPU chạy vLLM cho
7B; thời gian đo là giây/câu trên máy thử, rồi ngoại suy theo công
thức ngân sách của deep-dives/04 với giả định ghi rõ).

## 6. Những gì chưa đủ bằng chứng để chốt

- **Số PA của B/C trên model 7B cho DataMate**: mọi số trong file này
  đều là BIRD/Spider 2.0/DABstep với backbone khác (o3, GPT-4, GPT-4o,
  Qwen 32B). Không có số nào suy ra được PA trên ZAIC. Phép thử §5
  là bắt buộc trước khi chốt B2 hay C-thu-gọn.
- **Ngày công bố + license sử dụng của checkpoint CSC-SQL 7B trên
  HF**: chưa xác minh (xem §2.4). Không dùng checkpoint này cho tới
  khi xác minh xong, hoặc dùng model gốc Qwen2.5-Coder-7B với prompt
  merge zero-shot và đo riêng (§5.4).
- **DABstep baseline license**: file LICENSE ở root Space chưa đọc
  kỹ; không trích license, không copy code baseline vào Docker.
- **CHASE-SQL code**: chưa xác định được repo code trong đợt này;
  không dùng số hay cơ chế pairwise-selection-học-được của nó làm
  bằng chứng code.
- **I2I-STRADA code**: không tìm thấy repo công khai; chỉ lấy thiết
  kế (plan toàn cục trước code, SOP gắn ở bước reasoner).
- **Ngân sách 6 giờ với 2× RTX 5090**: chưa đo throughput vLLM cho
  7B trên máy đó; số lần gọi trong §4 là số lần gọi logic, không phải
  thời gian tường. Không mặc định 2 GPU = gấp đôi throughput (thuộc
  Ưu tiên 4, không kết luận ở đây).
- **Evaluator ZAIC thật (cách tính unanswerable, format percent,
  tie-break)**: vẫn chưa xác minh — mọi quyết định abstain/unanswerable
  trong file này đều dựa trên khung PA đã ghi trong repo (`gaps.md`
  Q-D), không phải trên evaluator thật.
- **Dữ liệu ZAIC train thật**: chưa giải nén/đo trong đợt này; mọi
  phép thử §5 đều chờ bước giải nén và liệt kê file của parent agent.
