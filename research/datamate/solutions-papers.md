# DataMate — Solutions và papers chuyển giao

> Mọi mục đều trả lời: bài toán gì, giống/khác DataMate ở đâu, pipeline và điểm
> cải thiện, kết quả so với baseline nào, code/license, tái dùng/sửa gì, phụ thuộc
> và luật, chi phí/rủi ro, thí nghiệm nhỏ nhất. Không mục nào được gọi là "hiệu quả
> trên ZAIC" nếu chưa đo trên dữ liệu ZAIC.

## 1. MCS-SQL — nhiều candidate + lọc thực thi + chọn bằng multiple-choice

- **Paper:** https://arxiv.org/html/2405.07467v1
- **Pipeline và điểm cải thiện (author-reported):** schema linking bằng nhiều prompt
  → sinh nhiều SQL candidate → lọc bằng thực thi → chọn bằng multiple-choice.
  Ablation trên BIRD dev: zero-shot 50,7%; + schema linking 52,8%; + sample table
  contents 55,2%; + few-shot 60,0%; + MCS 62,1–63,4%; trên Spider dev tới 89,5%.
- **Chuyển giao:** lấy (1) schema linking kèm giá trị mẫu, (2) sinh nhiều candidate,
  (3) loại candidate lỗi thực thi, (4) chọn bằng đồng thuận + kiểm tra chéo. Phải
  sửa: thay multiple-choice selection bằng đồng thuận SQL/pandas + kiểm tra rulebook;
  thêm bước format theo type; thêm bước unanswerable.
- **Luật:** thí nghiệm gốc dùng GPT-4 qua API — **vi phạm offline và cutoff nếu dùng
  nguyên bản**; chỉ chuyển giao ý tưởng pipeline, chạy bằng model nhỏ hợp lệ.
- **Rủi ro lớn nhất:** các candidate đều chạy được nhưng cho giá trị khác nhau
  (join sai vẫn ra số) — thực thi không bắt được lỗi này, chỉ kiểm tra chéo và
  rulebook mới bắt được.
- **Thí nghiệm nhỏ nhất:** 50 câu held-out: 1 candidate vs 5 candidate + lọc thực
  thi + đồng thuận; đo PA (không chỉ accuracy) và số câu chuyển từ sai sang abstain.

## 2. BASE-SQL — M-Schema + revision + merge revision

- **Paper:** https://arxiv.org/html/2502.10739v1
- **Pipeline:** M-Schema (mô tả schema có kèm mẫu), schema linking, SFT, SQL
  revision, SQL merge revision. Tác giả tự báo cáo: Qwen2.5-Coder 32B từ 56,84% lên
  67,47% trên BIRD dev; Spider test 88,87%.
- **Chuyển giao:** lấy M-Schema + sample, revision và merge revision. Bỏ model 32B
  (vượt 15B). Viết lại cho Qwen2.5-Coder-7B hoặc Qwen3-8B và cho cả pandas, không chỉ SQL.
- **Rủi ro:** revision làm tăng số lần gọi model — tính vào ngân sách 6 giờ;
  fine-tune trên schema train có thể làm giảm khái quát hóa sang business mới.
- **Thí nghiệm nhỏ nhất:** held-out train: không revision vs + revision vs + merge
  revision; đo PA và thời gian/câu hỏi.

## 3. CHESS — 4 agent + unit test tự nhiên (lấy ý tưởng, sửa cách kiểm tra)

- **Pipeline (secondary):** information retriever → schema selector → candidate
  generator → unit tester; khoảng 20 lần gọi LLM mỗi câu hỏi trong một bản mô tả.
- **Chuyển giao:** lấy ý tưởng unit test, nhưng đổi "unit test tự nhiên do LLM sinh"
  thành **kiểm tra thực thi bằng code/pandas/SQL + kiểm tra chéo + kiểm tra
  rulebook** — vì unit test tự sinh có thể "đồng lõa" với SQL sai (cùng một hiểu
  sai, test và SQL đều sai theo cùng một hướng).
- **Thí nghiệm nhỏ nhất:** đo thời gian/câu hỏi với 3 candidate + 1 vòng sửa; nếu
  vượt ngân sách 6 giờ khi nhân với số câu hỏi ước tính, cắt xuống 2 candidate +
  1 vòng sửa và đo lại PA.

## 4. Alpha-SQL — MCTS + self-supervised reward (rút gọn, không copy nguyên)

- **Pipeline (secondary):** MCTS rollout (một bản mô tả: 24 rollout, mỗi lần mở rộng
  3 action, temperature 0,8; reward tính bằng 5 lần lặp; revision tối đa 10 vòng).
  Tác giả tự báo cáo qua bản tóm tắt thứ cấp: Qwen2.5-Coder-7B đạt 66,8% trung bình,
  tương đương hoặc hơn một số phương pháp dùng GPT-4o.
- **Chuyển giao:** lấy ý tưởng reward bằng thực thi (SQL chạy đúng + kết quả nhất
  quán). Không lấy nguyên MCTS 24 rollout — thay bằng beam/search nhỏ (3–5
  candidate) + revision có giới hạn.
- **Luật:** Qwen2.5-Coder-7B/14B đủ điều kiện về cỡ (cần kiểm tra tổng tham số thực).
  MCTS là rủi ro thời gian, không phải rủi ro luật.
- **Thí nghiệm nhỏ nhất:** greedy 1 candidate vs MCTS rút gọn (3 rollout) trên 50
  câu held-out; đo cả PA và giây/câu hỏi; chỉ giữ MCTS nếu PA tăng đủ bù thời gian.

## 5. SPFT-SQL và DB-Explore — synthetic data có kiểm chứng thực thi

- **SPFT-SQL:** https://arxiv.org/pdf/2509.03937 — tác giả tự báo cáo: Qwen2.5-Coder-7B
  base Spider dev EX 83,5%, BIRD dev EX 51,5%; sau SPFT-SQL: 87,2% và 61,0%.
  Ablation: Verification-Based Iterative Fine-Tuning đóng góp lớn nhất (+3,3–3,8%
  Spider, +6,8% BIRD), self-play thêm +0,6–0,8%.
- **DB-Explore (Findings EMNLP 2025):** sinh instruction từ database exploration,
  lọc bằng thực thi; từ 26.000 cặp Spider và 22.000 cặp BIRD ban đầu, sau lọc còn
  21.273 và 16.457 cặp hợp lệ (tỷ lệ thành công 81,8% và 74,8%) — tác giả tự báo cáo
  qua bản tóm tắt. Bản ACL chính thức cần đối chiếu lại (link trong phiên là bản
  mirror qua worker).
- **Chuyển giao:** sinh câu hỏi + SQL/code từ schema train → chạy thực thi → chỉ giữ
  cặp chạy đúng và cho kết quả khớp → fine-tune. Phải sửa: (1) thêm rulebook vào
  prompt sinh, (2) thêm các type output của DataMate, (3) thêm ví dụ unanswerable
  (sinh câu hỏi mà dữ liệu thiếu trường cần thiết), (4) **cấm tuyệt đối dùng
  public/private test để sinh train hoặc gán nhãn.**
- **Cảnh báo cutoff:** checkpoint phái sinh từ fine-tune có được tính là "model công
  bố trước 01/10/2026" hay không là **chưa xác minh** — hỏi ban tổ chức hoặc giữ
  phương án dự phòng bằng model gốc chưa fine-tune.
- **Thí nghiệm nhỏ nhất:** sinh 500 cặp từ 1 business train, lọc bằng thực thi,
  fine-tune LoRA nhỏ, đo PA trên held-out của cùng business và trên một business
  khác (đo generalization, không chỉ đo trên business đã sinh).

## 6. LYNX và Judge-Then-Solve — tách vai trò để bắt lỗi "chạy được nhưng sai"

- **LYNX:** https://arxiv.org/html/2610.14777 (chỉ mô tả tóm tắt từ kết quả tìm kiếm,
  chưa đọc toàn văn) — Generator–Critic–Reviser; tách grounding thành semantic và
  structural theo từng giai đoạn; Critic quản lý lịch sử sửa lỗi (delta-guided
  memory) để tránh sửa vòng quanh; bước kiểm tra logic cuối đối chiếu chương trình
  với ý định gốc — vì thực thi không bắt được lỗi "executable-but-incorrect".
- **Judge-Then-Solve (preprint 2026, chỉ dựa trên mô tả tóm tắt, chưa đọc toàn
  văn):** bắt model phán quyết answerability trong một block riêng trước khi giải;
  nếu UNANSWERABLE thì dừng và abstain ngay; nếu ANSWERABLE thì mới giải. Điểm đáng
  lấy: tách bước "đủ dữ liệu hay không" thành quyết định có thể đo, kiểm tra và
  calibration riêng.
- **Áp dụng cho DataMate:** cài 3 vai trò bằng cùng một model nhỏ nhưng prompt khác
  nhau (tiết kiệm tham số): (a) Planner liệt kê cột/bảng/cửa sổ/quy tắc cần thiết và
  kết luận đủ/thiếu dữ liệu; (b) Coder viết code từ plan; (c) Checker đối chiếu code
  + kết quả với plan và rulebook, chỉ sửa tối đa 1–2 vòng. Nếu Planner kết luận thiếu
  dữ liệu, đi thẳng tới `unanswerable` (không sinh code đoán).
- **Rủi ro:** Critic/Planner cùng model với Coder có thể mù cùng một lỗi; phán quyết
  sai ở bước đầu sẽ khóa luôn đáp án đúng. Giảm rủi ro bằng kiểm tra không dùng LLM:
  Planner phải liệt kê tên cột/bảng thực sự tồn tại trong profiler, và Checker phải
  chạy code thật.
- **Thí nghiệm nhỏ nhất:** pipeline không Planner vs có Planner trên 50 câu held-out
  gồm cả câu unanswerable đã biết; đo unanswerable đúng, câu đúng bị chuyển nhầm
  thành unanswerable, và PA tổng.

## 7. Evidence calibration và AbstentionBench — calibration bằng retrieval coverage là yếu

- **Evidence-Calibrated RAG trên SQuAD 2.0 (author-reported):** Hybrid top-25
  retrieval + lexical reranking + extractive answering + evidence sufficiency
  calibration trên 43.482 ví dụ; validation 11.873 câu: exact match 31,65%, F1
  34,74%, answerability accuracy 53,01%, refusal F1 53,71%, hallucination-proxy
  37,49%. Calibration bằng retrieval coverage làm giảm hallucination-proxy từ
  77,80% (forced-answer) xuống 37,49%, nhưng bản thân evidence calibration vẫn yếu:
  AUROC 0,5475, ECE 0,1144.
- **AbstentionBench (NeurIPS 2025):** các câu hỏi thiếu dữ liệu trong context được
  coi là nên abstain; bao gồm context mơ hồ/thiếu, câu hỏi không thể biết, đại từ
  mơ hồ, tiền đề sai, đáp án thay đổi theo thời gian.
  https://proceedings.neurips.cc/paper_files/paper/2025/file/fb122bfc3f0127a94ded048b5b03496f-Paper-Datasets_and_Benchmarks_Track.pdf
- **Chuyển giao:** đừng chỉ dùng "tìm thấy bằng chứng hay không" làm tín hiệu abstain
  duy nhất (AUROC 0,5475 gần như đoán mò trong nghiên cứu đó). Kết hợp nhiều tín
  hiệu và calibration trên held-out của chính ZAIC — xem [../../plans/datamate.md](../../plans/datamate.md).

## 8. Tiếng Việt: ViText2SQL, PhoBERT, ViR²

- **ViText2SQL:** ~10.000 cặp câu hỏi–SQL tiếng Việt trên ~200 database; nghiên cứu
  pilot cho thấy word segmentation tiếng Việt cải thiện kết quả, NPMI hữu ích cho
  schema linking, PhoBERT giúp hiệu quả cao hơn XLM-R trong thí nghiệm đó
  (author-reported). Paper: https://ar5iv.labs.arxiv.org/abs/2010.01891
- **PhoBERT:** base 135M, large 370M tham số (theo slide tác giả:
  https://datquocnguyen.github.io/resources/DatQuocNguyen_AIDay2020_FinalVersion.pdf).
  Cả hai đều nhỏ, có thể nằm trong ngân sách 15B nếu dùng làm encoder phụ — nhưng
  phải kiểm tra giấy phép và ngày phát hành của checkpoint cụ thể, và phải cộng
  tham số vào tổng.
- **ViR² (DOI 10.31276/VJSTE.2025.0089):** retrieval ngữ nghĩa rồi rerank theo cú pháp
  bằng beam search; trên ViText2SQL đạt 23,33% Exact Match và 87,83% component-level
  F1, vượt Random, Skill-KNN, ASTRES và DICL tới 5 điểm EM theo báo cáo của tác giả.
  Cơ chế đáng mượn: khi đưa ví dụ train vào prompt, **đừng chọn ví dụ chỉ vì giống
  ngữ nghĩa** — rerank theo cấu trúc (dạng câu hỏi, dạng output, loại rule) và đa dạng.
- **Chuyển giao:**
  - Giữ dấu thanh tiếng Việt khi chuẩn hóa string (theo đúng cách evaluator chuẩn
    hóa) — đừng dùng chuẩn hóa bỏ dấu.
  - Dùng alias/mã sản phẩm trong dữ liệu làm dạng chấp nhận được, không tự suy ra
    tên chuẩn duy nhất.
  - Dùng PhoBERT/encoder nhỏ cho schema/value linking, trong khi LLM chính làm
    planning/code — tiết kiệm ngân sách tham số.
  - Rủi ro: linking tốt không cứu được phép tính sai; ViText2SQL là text-to-SQL,
    không có rulebook/lịch âm/type output của DataMate.

## 9. Model nhỏ và mốc thời gian — shortlist và cạm bẫy đếm tham số

*Shortlist dưới đây theo nguồn thứ cấp, cần xác minh lại checkpoint cụ thể trên
Hugging Face trước khi dùng.*

| Model | Cỡ / license (secondary) | Ngày (secondary) | Kết luận tạm thời |
|---|---|---|---|
| Qwen3-8B (dense) | 8B, Apache 2.0 | 2025-04-28 | Đủ điều kiện về ngày và cỡ theo nguồn thứ cấp; còn dư ngân sách cho encoder/reranker nhỏ |
| Qwen2.5-Coder-7B-Instruct | 7,61B, Apache 2.0, context 128K | 2024-09-19 | **Lựa chọn an toàn nhất cho vai trò Coder** |
| Qwen2.5-Coder-14B-Instruct | 14,7B, Apache 2.0, context 128K | 2024-09 | **Cẩn thận:** cộng PhoBERT-base 0,135B là 14,835B — sát trần 15B; cộng thêm reranker khác là vượt |
| Qwen2.5-Coder-32B | 32,5B | 2024-09 | **Loại trực tiếp** (vượt 15B); chỉ dùng kết quả BASE-SQL làm bằng chứng pipeline |
| Qwen3 MoE 30B-A3B, 235B-A22B | Tổng 30B / 235B, chỉ kích hoạt 3B / 22B | 2025-04 | **Loại trực tiếp:** luật tính toàn bộ tham số MoE |
| gpt-oss-20B (MoE, tổng 21B) | Tổng 21B | 2025-08 | **Loại** nếu tính tổng tham số MoE (21B > 15B) |
| Qwen 3.5 / 3.6 / 3.8 và các model 2026 khác | Tùy checkpoint | 2026 | Kiểm tra riêng từng checkpoint: phát hành sau 2026-10-01 thì loại trực tiếp |

**Cạm bẫy đếm tham số (làm trước khi chốt):** đọc `config.json` của checkpoint cụ
thể, cộng tổng tham số (bao gồm embedding nếu không tie); cộng mọi model inference
khác; fine-tune/quantization không làm giảm "tổng tham số"; nếu dùng hai checkpoint
khác nhau (Planner + Coder) thì cộng cả hai.

**Bằng chứng về model nhỏ trên BIRD (author-reported, cần đối chiếu):** Qwen2.5-Coder
7B base 39,05% trên BIRD dev; + self-correct 42,50%; + lexical schema-link 39,31% —
bài học: schema linking bằng từ vựng đơn thuần không luôn giúp model nhỏ;
self-correction dựa trên thực thi có giá trị hơn trong ngân sách nhỏ. BASE-SQL cho
thấy fine-tune ít mẫu cũng có hiệu quả: 14B/32B ổn định sau khoảng 150 bước
(~1,2k mẫu), 7B sau khoảng 250 bước (~4k mẫu) theo mô tả của BASE-SQL — vẫn phải
đo trên held-out của ZAIC.
