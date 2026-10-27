# Danh mục nguồn — Zalo AI Challenge 2026

> Ngày truy cập: **2026-10-27** cho mọi nguồn, trừ các mục ghi rõ lấy từ nghiên cứu
> portal 2026-10-26. Trạng thái xác minh: **Official** = portal/thể lệ chính thức;
> **Code-read** = đã mở repo/file; **Author** = tác giả tự báo cáo; **Secondary** =
> nguồn thứ cấp/tóm tắt; **Mirror** = bản mirror qua worker/proxy, cần đối chiếu bản
> gốc; **Missing-URL** = tên/tài liệu được nhắc trong ghi chú gốc nhưng URL đầy đủ
> không được ghi lại — không bịa URL. Các nguồn nói về cùng một solution đã gộp
> thành một mục.

## A. Nguồn chính thức ZAIC 2026

| # | Nguồn | URL | Trạng thái |
|---|---|---|---|
| A1 | ZAIC 2026 — trang chính | https://challenge.zalo.ai/ | Official, kiểm tra 2026-10-26 |
| A2 | ZAIC 2026 — portal LifeMate | https://challenge.zalo.ai/portal/lifemate | Official, kiểm tra 2026-10-26 (sau đăng nhập) |
| A3 | ZAIC 2026 — portal DataMate | https://challenge.zalo.ai/portal/datamate | Official, kiểm tra 2026-10-26 (sau đăng nhập) |
| A4 | Thể lệ ZAIC (EN PDF) | https://dl-challenge.zalo.ai/zalo-ai-challenge-regulations-en.pdf | Official, đã đọc §2.2/2.3 ngày 2026-10-26 |
| A5 | Thể lệ ZAIC (VI PDF) | https://dl-challenge.zalo.ai/zalo-ai-challenge-regulations-vi.pdf | Official |
| A6 | DataMate — train.zip | https://dl-challenge.zalo.ai/2026/datamate_dkewxftdzo/train.zip | Official, link tải sau đăng nhập 2026-10-26; chưa tải/giải nén trong phiên nghiên cứu |
| A7 | DataMate — public_test.zip | https://dl-challenge.zalo.ai/2026/datamate_dkewxftdzo/public_test.zip | Official, link tải sau đăng nhập 2026-10-26; chưa tải/giải nén |
| A8 | LifeMate — train+public_test.zip | https://dl-challenge.zalo.ai/2026/lifemate_argfzdgert/train+public_test.zip | Official, link tải sau đăng nhập 2026-10-26; chưa tải/giải nén |

## B. LifeMate — ASR tiếng Việt

| # | Nguồn | URL | Trạng thái |
|---|---|---|---|
| B1 | PhoWhisper — repo | https://github.com/VinAIResearch/PhoWhisper | Code-read, commit `b06f1937995cfee75b9e4ad3e2ae0798faf1a562`, BSD-3-Clause |
| B2 | PhoWhisper — paper (ICLR 2024 Tiny Papers) | https://arxiv.org/pdf/2406.02555 | Author (Table 2 đã đối chiếu qua snippet OpenReview: VIVOS tiny 10,41 / base 8,46 / small 6,33 / medium 4,97 / large 4,67; kích thước 39/74/244/769/1550M). VIVOS là read speech — KHÔNG phải audio LifeMate, không dùng WER VIVOS làm mục tiêu. HF repo/licence/ngày từng checkpoint chưa xác minh |
| B3 | PhoWhisper — paper (ICLR 2024 Tiny Papers) | Canonical OpenReview forum URL chưa có dạng verbatim (search chỉ trả về attachment link — không trích attachment link làm canonical) | Chưa có URL forum đầy đủ — mở OpenReview tìm 'PhoWhisper' thay vì trích attachment link |
| B4 | VIVOS — Vietnamese Speech Corpus (Zenodo) | https://zenodo.org/records/7068130 | Code-read (trang Zenodo): 15 giờ, read speech, CC BY-NC-SA 4.0 |
| B5 | Vietnamese ASR fine-tune cho lyrics (VietLyrics) | https://arxiv.org/html/2510.22295v1 | Author, miền lyrics — không chuyển sang LifeMate |
| B6 | ViMedCSS / code-switching medical ASR | https://arxiv.org/html/2602.12911 | Author, miền y tế — chỉ tham khảo entity/code-switch |
| B7 | TSPC — two-stage phoneme-centric Vietnamese–English ASR | https://arxiv.org/pdf/2509.05983 | Author, kiến trúc nghiên cứu — chưa xác minh code/checkpoint |
| B8 | RECOVER — agentic ASR entity correction | https://arxiv.org/pdf/2603.16411 | Author (8–46% giảm entity WER tương đối, tới +22pp recall, 5 dataset) — giả thuyết chuyển giao, chưa test ZAIC |
| B9 | When Does an ASR Error Matter? Task-Role Diagnostics | https://arxiv.org/pdf/2610.17619v1 | Author (khung chẩn đoán); ngày chính xác so với cutoff chưa xác minh — chỉ dùng khung |
| B10 | VietSuperSpeech (tổng quan corpus tiếng Việt) | https://arxiv.org/pdf/2603.01894 | Author (bảng tổng quan corpus) |
| B11 | DeRAGEC (repo được nhắc trong snippet) | https://github.com/solee0022/deragec | **Chưa xác minh:** chỉ xuất hiện ở mức snippet, chưa đọc code/commit |
| B12 | Faster-Whisper comparison (Gist) | https://gist.github.com/danielrosehill/278b1719598093767126e52105ae076e | Secondary (số 4–8× trên GPU khác, không phải A30) |

## C. LifeMate — function calling, agent có trạng thái

| # | Nguồn | URL | Trạng thái |
|---|---|---|---|
| C1 | ReAct (ICLR 2023) | https://arxiv.org/pdf/2210.03629 | Author (PaLM-540B few-shot); mâu thuẫn ALFWorld 71% vs 79% giữa các tóm tắt — đối chiếu bảng gốc |
| C2 | τ-bench — repo | https://github.com/sierra-research/tau-bench | Commit `59a200c6d575d595120f1cb70fea53cef0632f6b`, MIT; README cảnh báo task cũ, trỏ sang τ²/τ³-bench. File agent cụ thể trong round 2 chỉ DEEPWIKI_SUMMARY — mở bằng git clone trước khi trích code |
| C3 | τ-bench — paper | https://arxiv.org/abs/2406.12045 | Author (Table 3: GPT-4o pass¹ có policy retail 61,2 / airline 33,2; bỏ policy: 56,8 / 10,8 — bắt buộc ghi pass version + policy + domain + backbone khi trích số) |
| C4 | τ²-bench — paper | https://arxiv.org/abs/2506.07982 | Secondary (trích dẫn từ README τ-bench) |
| C5 | ToolSandbox — repo | https://github.com/apple/ToolSandbox | Code-read một phần, commit `c8571d7854316d2e1c5f288e59fe1e34e53f6dd1`; license hiển thị NOASSERTION — đọc LICENSE thực tế trước khi tái sử dụng |
| C6 | ToolSandbox — paper | https://arxiv.org/abs/2408.04682 | Secondary (arXiv ID từ README ToolSandbox) |
| C7 | AppWorld — paper chính thức | https://arxiv.org/pdf/2407.18901 (site https://appworld.dev/, repo https://github.com/stonybrooknlp/appworld — repo chưa mở trực tiếp trong round 2) | Author (abstract: GPT-4o ~49% normal, ~30% challenge; chấm bằng state-based unit test + collateral damage). ĐÃ BỎ số 'Test-C 30,2% → 35,2%' — abstract không chứa nó. |
| C8 | Symbolic Constraint Agents (SCA) | https://arxiv.org/html/2610.25552 | Secondary (đánh giá trên AppWorld test-challenge + τ²-bench) |
| C9 | Proxy State-Based Evaluation | https://arxiv.org/html/2602.16246v1/ | Secondary |
| C10 | Hammer v1 — paper (ICLR 2025) | https://arxiv.org/pdf/2410.04587 | Paper (7.500 mẫu irrelevance + function masking, đã xác nhận). Repo https://github.com/MadeAgents/Hammer — README_READ, Apache-2.0, commit `ff415d`. Hammer-7B loại (vượt 5B); Hammer-4B chỉ là ứng viên A/B (base/licence/ngày chưa đọc trên HF card). |
| C11 | Hammer — proceedings | https://proceedings.iclr.cc/paper_files/paper/2025/file/d45e0bfb5a39477d56b55c0824200008-Paper-Conference.pdf | Secondary (cùng paper với C10) |
| C12 | xLAM-2-3b-fc-r — series Salesforce + APIGen-MT | https://arxiv.org/html/2504.03601v4 (series trong card GGUF https://huggingface.co/Salesforce/Llama-xLAM-2-8b-fc-r-gguf) | Series đã xác minh, nhưng checkpoint 3B cụ thể CHƯA xác minh licence/ngày/tên repo chính xác; BFCL v4 83,7% là first-party (trang đo), không phải leaderboard chính thức; rủi ro CC BY-NC (báo chí) — NGOÀI shortlist chính. Blog cũ aichina.news chỉ còn là nguồn phụ. |
| C13 | APIGen | https://arxiv.org/pdf/2406.18518 | Author (đã đọc abstract: 3.673 API, 60.000 mẫu, verify 3 tầng) |
| C14 | DelegationBench | https://arxiv.org/html/2610.05532 | Secondary (khung Act/Ask/Request/Refuse); ngày so với cutoff chưa xác minh |
| C15 | DuplexSLA — native speech–language–action model | https://arxiv.org/pdf/2605.20755 | Author; không phải drop-in LifeMate, size/licence/checkpoint/A30 chưa xác minh |
| C16 | Qwen3-4B-Instruct-2507 — HF card chính thức | https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507 (commit `cdbee75`) | Official (card): Apache 2.0, 4,0B tổng / 3,6B non-embedding, 36 layer, context native 262.144, non-thinking, series tháng 7/2025. KDnuggets 06/08/2025 là NGÀY BÀI BÁO, không phải ngày phát hành model. |
| C17 | TinyLLM survey — small models for agentic tasks | https://arxiv.org/pdf/2511.22138v1 | Secondary (xLAM-2-3b-fc-r 65,74%, Qwen3-4B prompt 62,04% BFCL overall, KHÔNG RÕ VERSION) — không dùng để xếp hạng model; mọi số BFCL từ nay phải ghi version + mode + ngày, thiếu một trong ba thì không trích số. |
| C18 | Qwen3-4B Function-Calling fine-tune (model card) | https://huggingface.co/sweatSmile/Qwen3-4B-Function-Calling-Pro | Secondary (LoRA SFT 1.000 mẫu, loss 0,518 — loss không phải accuracy) |
| C19 | Fine-tuned Qwen3-0.6B beats 120B LLM on structured function calling (blog) | https://openclawradar.com/article/fine-tuned-qwen3-0-6b-beats-120b-llm-structured-function-calling | Secondary, blog không peer-review, miền IoT — chỉ là giả thuyết |
| C20 | IFFC prompt-based router claim (LinkedIn/company post) | Không có URL xác minh trong đợt search — không trích link | **Chưa xác minh, không có code theo chính bài đăng** — chỉ lấy 2 ý test rẻ tiền |

## D. DataMate — text-to-SQL và data-analysis agent

| # | Nguồn | URL | Trạng thái |
|---|---|---|---|
| D1 | MCS-SQL | https://arxiv.org/html/2405.07467v1 | Author (đọc qua tìm kiếm); chưa kiểm tra code |
| D2 | BASE-SQL | https://arxiv.org/html/2502.10739v1 | Author |
| D3 | SPFT-SQL | https://arxiv.org/pdf/2509.03937 | Author; chưa kiểm tra code |
| D4 | DB-Explore (Findings EMNLP 2025) | ACL Anthology ID 2025.findings-emnlp.1032, DOI 10.18653/v1/2025.findings-emnlp.1032 (trang 18969–18979) — thay mirror workers.dev | Author (BIRD EX 67,0%, SPIDER 87,8%, implementation Qwen2.5-Coder-7B); 'dùng GPT-4' là bước tạo dữ liệu offline, không phải inference; chưa kiểm tra code, licence chưa xác minh |
| D5 | Alpha-SQL (MCTS) | https://arxiv.org/abs/2502.17248 (v2, sửa 15/06/2025) và ICML 2025 PMLR v267 https://proceedings.mlr.press/v267/li25dt.html — thay mirror | Author: BIRD dev 69,7% với LLM 32B (không fine-tune); tổng hợp thứ cấp ghi 66,8% với Qwen2.5-Coder-7B, 24 rollout — hai backbone khác nhau, không so như một thí nghiệm |
| D6 | LYNX | https://arxiv.org/html/2610.14777 | Author (chỉ mô tả tóm tắt từ kết quả tìm kiếm); chưa đọc toàn văn, chưa kiểm tra code |
| D7 | Judge-Then-Solve / Bridging the Detection-to-Abstention Gap | https://arxiv.org/pdf/2605.28070 (Gu và cộng sự, nộp 27/05/2026 — ID cũ 2602.04755 là SAI, đã sửa; mirror r2.dev đã bỏ) | Paper, trước cả hai mốc cutoff; miền medical, chưa có checkpoint xác minh |
| D8 | CHESS và các pipeline text-to-SQL — survey | https://arxiv.org/html/2408.05109v5 | Secondary (bảng so sánh pipeline) |
| D9 | Simple ReAct cho text-to-SQL | https://arxiv.org/html/2608.22651 | Secondary (ReAct đơn giản vs CHESS ~20 call/câu; batching 8 call/lượt) |
| D10 | ReToolSQL (tổng hợp pipeline BIRD) | https://arxiv.org/html/2608.27796 | Secondary (số EX theo bản tổng hợp này, không so sánh trực tiếp) |
| D11 | RSL-SQL — repo được nêu | https://github.com/Laqcce-cao/RSL-SQL | **Chưa mở/xác minh license** trong các phiên nghiên cứu |
| D12 | I2I-STRADA (DABstep) | https://arxiv.org/pdf/2507.17874 | Secondary (planning + xử lý lỗi code, nhạy với rule SOP) |
| D13 | DABstep — benchmark (Egg và cộng sự, Adyen × HF) | https://arxiv.org/pdf/2506.23719 ; Space https://huggingface.co/spaces/adyen/DABstep ; dataset https://huggingface.co/datasets/adyen/DABstep | Official (paper). Số duy nhất được giữ: agent tốt nhất thời điểm paper đạt 14,55% Hard (author-reported). ĐÃ BỎ '77,78%/9,26%' và 'Cascade 92,22%' (không đối chiếu được bảng gốc; Cascade là vendor tự báo cáo, chưa validated). Baseline trong Space KHÔNG phải CODE_INSPECTED (trang tree không liệt kê được file). |
| D14 | Spider 2.0 — benchmark (Lei và cộng sự, ICLR 2025) | https://arxiv.org/pdf/2411.07763 | Official (paper): 632 task, trung bình 812 cột; o1-preview code agent 21,3% full (cùng paper: 91,2% Spider 1.0, 73,0% BIRD). ĐÃ BỎ 17,1% (không rõ setting). Mọi số phải ghi setting + backbone. |
| D15 | SpreadsheetBench 2 (Zhu và cộng sự) | https://arxiv.org/abs/2606.29955 (submitted 29/06/2026 — đã xác minh trực tiếp qua arXiv trong đợt áp dụng round 2, giải quyết xung đột giữa hai ghi chú round 2) | Author: 321 task, 11,8 worksheet/instance, 593,5 lần sửa ô, best 34,89%, debugging 12,00%. Transfer chỉ ở inspection + xác định đích; benchmark này là SỬA workbook, không phải QA trên Excel như DataMate. SpreadsheetBench gốc: arXiv 2406.14991, https://spreadsheetbench.github.io, 912 instruction / 2.729 test case, 0,05%–23,65%. |
| D16 | Evidence-Calibrated RAG (SQuAD 2.0) | https://jtie.stekom.ac.id/index.php/jtie/article/view/536 | Author (AUROC calibration 0,5475, ECE 0,1144) |
| D17 | AbstentionBench (NeurIPS 2025) | https://proceedings.neurips.cc/paper_files/paper/2025/file/fb122bfc3f0127a94ded048b5b03496f-Paper-Datasets_and_Benchmarks_Track.pdf | Author |
| D18 | BAS — Decision-Theoretic Approach to Evaluating LLM Confidence | https://arxiv.org/html/2604.03216v1 | Author (ngưỡng rủi ro, phạt overconfidence) |
| D19 | Reinforced hesitation (abstention bằng penalty) | https://arxiv.org/pdf/2511.11500 | Author (kết quả trên task của paper đó, không phải trên DataMate) |
| D20 | Toward Robust RALMs — Impact of Imperfect Retrieval | https://arxiv.org/html/2410.15107v1 | Author (đọc qua tìm kiếm) |
| D21 | Qwen2.5-Coder series — thông số và license (nguồn thứ cấp) | https://www.alibabacloud.com/blog/qwen2-5-coder-series-powerful-diverse-practical_601765 | Secondary — cần đối chiếu Hugging Face chính thức cho checkpoint cụ thể |
| D22 | Qwen family — lịch sử phát hành và license | https://www.taskade.com/blog/alibaba-qwen-history | Secondary |
| D23 | Qwen family — bảng so sánh | https://computingforgeeks.com/open-source-llm-comparison/ | Secondary |
| D24 | DuckDB vs SQLite/Polars/BigQuery — giải thích | https://www.alekseialeinikov.com/en/blog/topics/data/duckdb-explained-vs-sqlite-polars-bigquery | Secondary |
| D25 | lunar-vn (PyPI) | https://pypi.org/project/lunar-vn/1.3.0/ | Secondary (trang PyPI; chưa đọc code, chưa chạy kiểm tra) |
| D26 | vi-lunaire (PyPI) | https://pypi.org/project/vi-lunaire/ | Secondary (trang PyPI; chưa đọc code, chưa chạy kiểm tra) |
| D27 | Vietnamese lunar calendar — giải thích UTC+7 vs UTC+8 | https://calendar.webtech360.com/en/vietnamese-calendar-2026/ | Secondary |
| D28 | ReFoRCE — repo + paper | https://github.com/Snowflake-Labs/ReFoRCE ; https://arxiv.org/pdf/2502.00675 | CODE_INSPECTED ở mức file: `methods/ReFoRCE/agent.py`, `methods/ReFoRCE/sql.py`, `methods/ReFoRCE/schema_linking.py`, `LICENSE` (Apache 2.0) — KHÔNG trích tên class (báo cáo round 2 không thống nhất). Số Spider 2.0 khác nhau theo phiên bản — không chọn con cao nhất, không suy ra PA. |
| D29 | schemagate — repo | https://github.com/ashishsinha1602/schemagate | README_READ, Apache 2.0; chưa đọc file selector — KHÔNG phải CODE_INSPECTED. Số BIRD Mini-Dev là tự báo cáo, backbone API — không dùng làm mục tiêu. |
| D30 | DSR-SQL — paper | https://arxiv.org/html/2511.21402 | PAPER_READ. Repo chính thức theo paper (`DMIRLAB-Group/DSR-SQL`) trả 404 trong round 2 — không có code để tái sử dụng; chỉ lấy thiết kế dual-state. Số 35,28% Spider 2.0-Snow / 68,32% BIRD dev là tác giả tự báo cáo, phiên bản đánh giá đã thay đổi theo cảnh báo của tác giả. |
| D31 | BASE-SQL — ablation | https://arxiv.org/html/2502.10739v1 | PAPER_READ. Ablation BIRD dev với Qwen2.5-Coder 32B (vượt luật, chỉ học thứ tự bước); bằng chứng ngược DeepSeek-Coder 33B: +Data Samples −5,28. Repo chính thức chưa xác định — không gắn link repo. |
| C21 | Forge — repo (guardrail patterns) | https://github.com/antoinezambelli/forge | README_READ, MIT, commit `3e5a38aed55504a71e5461b9873ca1979709ab50`, tạo 2026-02-16. KHÔNG phải CODE_INSPECTED — file cần mở tiếp: `src/forge/guardrails/response_validator.py`, `step_enforcer.py`, `error_tracker.py`, `src/forge/core/runner.py`. |
| C22 | τ²-bench — repo | https://github.com/sierra-research/tau2-bench | README_READ, MIT, commit lúc mở round 2 `70f71c6b3c57164841a23cab124910c54f9cd7bf`. Cảnh báo: 2.0 KHÔNG input-identical với 1.x — không so số 2.0 với 1.x. |
| C23 | Hammer2.1-3b — HF card | https://huggingface.co/MadeAgents/Hammer2.1-3b | CHƯA XÁC MINH licence/ngày/base trên card gốc; mirror Dataloop báo CC-BY-NC-4.0 cho bản 0.5b (chưa xác minh) — NGOÀI shortlist chính cho tới khi đọc card gốc. |
| C24 | xLAM-2 series — card GGUF + APIGen-MT | https://huggingface.co/Salesforce/Llama-xLAM-2-8b-fc-r-gguf ; https://arxiv.org/html/2504.03601v4 | README_READ (card GGUF, không phải card 3B trực tiếp). Checkpoint 3B cụ thể chưa xác minh licence/ngày/tên repo — NGOÀI shortlist chính. |

## E. Tiếng Việt cho DataMate

| # | Nguồn | URL | Trạng thái |
|---|---|---|---|
| E1 | ViText2SQL — paper | https://ar5iv.labs.arxiv.org/abs/2010.01891 | Secondary (qua ar5iv); ~10k cặp, PhoBERT > XLM-R, tách từ cải thiện kết quả |
| E2 | PhoBERT — README chính thức | https://github.com/VinAIResearch/PhoBERT | Official (README): vinai/phobert-base 135M MIT; vinai/phobert-large 370M MIT; vinai/phobert-base-v2 135M GNU AGPL v3 — dùng base, KHÔNG dùng base-v2 trừ khi chấp nhận copyleft. Bắt buộc input đã tách từ tiếng Việt. |
| E3 | ViR² — paper (VJSTE) | https://vietnamscience.vjst.vn/index.php/vjste/article/download/1364/603/2926 | Secondary (DOI 10.31276/VJSTE.2025.0089; 23,33% EM, 87,83% component F1 theo tác giả) |

## F. Các mùa ZAIC trước — khoảng trống đã xác minh bằng tìm kiếm

| # | Nguồn | URL | Trạng thái |
|---|---|---|---|
| F1 | ZAIC 2023 Elementary Maths Solving — repo baseline `Reasoning-Lab/Elementary-Math-Solving-Zalo-AI-2023` | URL đầy đủ không có trong kết quả tìm kiếm (chỉ có bản mirror cache, không dùng được) | **Missing-URL, chưa xác minh trực tiếp, chưa xác minh license**; transfer thấp sang 2026 |
| F2 | ZAIC 2025 — đội thắng CtelAI / AIO_C3A | Không tìm thấy repo/write-up chính thức | **Khoảng trống** — ghi nhận để tránh tìm lại; không bịa link |

## Nguồn không thể hợp nhất vì URL thiếu trong các ghi chú gốc (đã cập nhật round 2)

Các mục DABstep, Spider 2.0 và SpreadsheetBench 2 **đã được giải quyết trong
round 2** (xem D13/D14/D15 ở trên) và không còn ở danh sách thiếu URL này nữa.
Còn thiếu:

1. **ZAIC 2023 repo baseline** — chỉ có tên repo, không có URL đầy đủ dùng được
   (mục F1). Không bịa URL dạng github.com/Reasoning-Lab/... dù dạng này
   'trông đúng'.
2. **PhoWhisper paper trên OpenReview** — chỉ có domain openreview.net, không có URL
   forum cụ thể (mục B3).
3. **IFFC router claim** — bài đăng LinkedIn/company, không có URL xác minh
   (mục C20).
4. **vLLM guided_json / Outlines / XGrammar / llama.cpp GBNF** — hướng dẫn thứ cấp
   tổng hợp, không trích một URL duy nhất chưa xác minh; không liệt kê thành nguồn
   riêng.
5. **Hammer irrelevance dataset** — tên dataset `MadeAgents/xlam-irrelevance-7.5k`
   được nhắc trong paper/README; URL đầy đủ dạng
   huggingface.co/datasets/MadeAgents/xlam-irrelevance-7.5k suy từ tên, cần mở
   trực tiếp để xác nhận trước khi tải.
6. **FISSION-GRPO** — tên repo `zxzadm/Fission-GRPO` thấy trong snippet, URL đầy
   đủ chưa xác minh — không trích URL.
7. **BASE-SQL và CHESS repo chính thức** — chưa xác định URL trong round 2 —
   không gắn link, không gắn nhãn code.
8. **Qwen3-8B / Qwen3-14B config.json** — chưa mở card gốc trực tiếp trong round 2;
   số 8,19B / ~14,8B hiện là Secondary.
