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
| B2 | PhoWhisper — paper | https://arxiv.org/pdf/2406.02555 | Author (đọc qua snippet: Table 2 kích thước + WER); HF repo/licence/ngày từng checkpoint chưa xác minh |
| B3 | PhoWhisper — paper (ICLR 2024 Tiny Papers) | https://openreview.net/ (trích dẫn từ README PhoWhisper; URL bài cụ thể không được ghi đầy đủ) | Secondary, URL không đầy đủ — cần đối chiếu lại |
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
| C2 | τ-bench — repo | https://github.com/sierra-research/tau-bench | Code-read, commit `59a200c6d575d595120f1cb70fea53cef0632f6b`, MIT; README cảnh báo task cũ, trỏ sang τ²/τ³-bench |
| C3 | τ-bench — paper | https://arxiv.org/abs/2406.12045 | Author |
| C4 | τ²-bench — paper | https://arxiv.org/abs/2506.07982 | Secondary (trích dẫn từ README τ-bench) |
| C5 | ToolSandbox — repo | https://github.com/apple/ToolSandbox | Code-read một phần, commit `c8571d7854316d2e1c5f288e59fe1e34e53f6dd1`; license hiển thị NOASSERTION — đọc LICENSE thực tế trước khi tái sử dụng |
| C6 | ToolSandbox — paper | https://arxiv.org/abs/2408.04682 | Secondary (arXiv ID từ README ToolSandbox) |
| C7 | AppWorld — paper/tóm tắt | https://www.alphaxiv.org/abs/2407.18901 | Secondary (số TGC 48,8%/30,2% theo bản tóm tắt) |
| C8 | Symbolic Constraint Agents (SCA) | https://arxiv.org/html/2610.25552 | Secondary (đánh giá trên AppWorld test-challenge + τ²-bench) |
| C9 | Proxy State-Based Evaluation | https://arxiv.org/html/2602.16246v1/ | Secondary |
| C10 | Hammer — paper (ICLR 2025) | https://arxiv.org/pdf/2410.04587 | Secondary; checkpoint `MadeAgents/Hammer-*` chưa xác minh license |
| C11 | Hammer — proceedings | https://proceedings.iclr.cc/paper_files/paper/2025/file/d45e0bfb5a39477d56b55c0824200008-Paper-Conference.pdf | Secondary (cùng paper với C10) |
| C12 | xLAM-2-3B — bài blog thứ cấp | https://aichina.news/blog/a-3b-agent-for-your-laptop-salesforce-s-xlam-2-tool-caller-lands-on-a1zrpd/ | Secondary yếu (không phải nguồn Salesforce chính thức) — xác minh checkpoint/license/ngày trước khi dùng |
| C13 | APIGen | https://arxiv.org/pdf/2406.18518 | Author (đã đọc abstract: 3.673 API, 60.000 mẫu, verify 3 tầng) |
| C14 | DelegationBench | https://arxiv.org/html/2610.05532 | Secondary (khung Act/Ask/Request/Refuse); ngày so với cutoff chưa xác minh |
| C15 | DuplexSLA — native speech–language–action model | https://arxiv.org/pdf/2605.20755 | Author; không phải drop-in LifeMate, size/licence/checkpoint/A30 chưa xác minh |
| C16 | 5 Small Language Models for Agentic Tool Calling (KDnuggets, có Qwen3-4B-Instruct-2507) | https://www.kdnuggets.com/5-small-language-models-for-agentic-tool-calling | Secondary: ngày 06/08/2025, 4,0B, Apache 2.0 — cần xác minh trên HF/official |
| C17 | TinyLLM survey — small models for agentic tasks | https://arxiv.org/pdf/2511.22138v1 | Secondary (xLAM-2-3b-fc-r 65,74%, Qwen3-4B prompt 62,04% BFCL overall) — không phải leaderboard chính thức đã kiểm chứng |
| C18 | Qwen3-4B Function-Calling fine-tune (model card) | https://huggingface.co/sweatSmile/Qwen3-4B-Function-Calling-Pro | Secondary (LoRA SFT 1.000 mẫu, loss 0,518 — loss không phải accuracy) |
| C19 | Fine-tuned Qwen3-0.6B beats 120B LLM on structured function calling (blog) | https://openclawradar.com/article/fine-tuned-qwen3-0-6b-beats-120b-llm-structured-function-calling | Secondary, blog không peer-review, miền IoT — chỉ là giả thuyết |
| C20 | IFFC prompt-based router claim (LinkedIn/company post) | Không có URL xác minh trong đợt search — không trích link | **Chưa xác minh, không có code theo chính bài đăng** — chỉ lấy 2 ý test rẻ tiền |

## D. DataMate — text-to-SQL và data-analysis agent

| # | Nguồn | URL | Trạng thái |
|---|---|---|---|
| D1 | MCS-SQL | https://arxiv.org/html/2405.07467v1 | Author (đọc qua tìm kiếm); chưa kiểm tra code |
| D2 | BASE-SQL | https://arxiv.org/html/2502.10739v1 | Author |
| D3 | SPFT-SQL | https://arxiv.org/pdf/2509.03937 | Author; chưa kiểm tra code |
| D4 | DB-Explore (Findings EMNLP 2025) | https://poe.shuhuigeng.workers.dev:443/https/aclanthology.org/2025.findings-emnlp.1032.pdf | **Mirror** — cần đối chiếu bản ACL chính thức; chưa kiểm tra code |
| D5 | Alpha-SQL (MCTS) | https://round-lake.dustinice.workers.dev:443/https/raw.githubusercontent.com/mlresearch/v267/main/assets/li25dt/li25dt.pdf | **Mirror** — cần đối chiếu bản gốc; chưa kiểm tra code |
| D6 | LYNX | https://arxiv.org/html/2610.14777 | Author (chỉ mô tả tóm tắt từ kết quả tìm kiếm); chưa đọc toàn văn, chưa kiểm tra code |
| D7 | Judge-Then-Solve / Bridging the Detection-to-Abstention Gap (preprint 2026) | https://pub-fad10fba280c45dba0823fd585acc08c.r2.dev/pdf/2605.28070.pdf?v=1789253425 | **Mirror** — cần đối chiếu arXiv chính thức (arXiv 2602.04755 được nhắc trong ghi chú gốc) |
| D8 | CHESS và các pipeline text-to-SQL — survey | https://arxiv.org/html/2408.05109v5 | Secondary (bảng so sánh pipeline) |
| D9 | Simple ReAct cho text-to-SQL | https://arxiv.org/html/2608.22651 | Secondary (ReAct đơn giản vs CHESS ~20 call/câu; batching 8 call/lượt) |
| D10 | ReToolSQL (tổng hợp pipeline BIRD) | https://arxiv.org/html/2608.27796 | Secondary (số EX theo bản tổng hợp này, không so sánh trực tiếp) |
| D11 | RSL-SQL — repo được nêu | https://github.com/Laqcce-cao/RSL-SQL | **Chưa mở/xác minh license** trong các phiên nghiên cứu |
| D12 | I2I-STRADA (DABstep) | https://arxiv.org/pdf/2507.17874 | Secondary (planning + xử lý lỗi code, nhạy với rule SOP) |
| D13 | DABstep — benchmark (tổng quan, kết quả) | URL đầy đủ chưa được ghi lại trong phiên nghiên cứu — cần đối chiếu lại | **Missing-URL** — không bịa link; chỉ dùng bài học, không trích số làm kết quả đã xác minh |
| D14 | Spider 2.0 — benchmark (tổng quan, kết quả) | URL đầy đủ chưa được ghi lại trong phiên nghiên cứu — cần đối chiếu lại | **Missing-URL**; số liệu mâu thuẫn giữa các nguồn thứ cấp (xem competitions-benchmarks) |
| D15 | SpreadsheetBench 2 (arXiv 2606.29955) | URL đầy đủ chưa được ghi lại trong phiên nghiên cứu — cần đối chiếu lại | **Missing-URL** — không bịa link |
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

## E. Tiếng Việt cho DataMate

| # | Nguồn | URL | Trạng thái |
|---|---|---|---|
| E1 | ViText2SQL — paper | https://ar5iv.labs.arxiv.org/abs/2010.01891 | Secondary (qua ar5iv); ~10k cặp, PhoBERT > XLM-R, tách từ cải thiện kết quả |
| E2 | PhoBERT — slide tác giả | https://datquocnguyen.github.io/resources/DatQuocNguyen_AIDay2020_FinalVersion.pdf | Secondary (base 135M / large 370M) |
| E3 | ViR² — paper (VJSTE) | https://vietnamscience.vjst.vn/index.php/vjste/article/download/1364/603/2926 | Secondary (DOI 10.31276/VJSTE.2025.0089; 23,33% EM, 87,83% component F1 theo tác giả) |

## F. Các mùa ZAIC trước — khoảng trống đã xác minh bằng tìm kiếm

| # | Nguồn | URL | Trạng thái |
|---|---|---|---|
| F1 | ZAIC 2023 Elementary Maths Solving — repo baseline `Reasoning-Lab/Elementary-Math-Solving-Zalo-AI-2023` | URL đầy đủ không có trong kết quả tìm kiếm (chỉ có bản mirror cache, không dùng được) | **Missing-URL, chưa xác minh trực tiếp, chưa xác minh license**; transfer thấp sang 2026 |
| F2 | ZAIC 2025 — đội thắng CtelAI / AIO_C3A | Không tìm thấy repo/write-up chính thức | **Khoảng trống** — ghi nhận để tránh tìm lại; không bịa link |

## Nguồn không thể hợp nhất vì URL thiếu trong các ghi chú gốc

1. **DABstep** — chỉ có mô tả và số liệu thứ cấp, không có URL đầy đủ (mục D13).
2. **Spider 2.0** — chỉ có mô tả và số liệu thứ cấp mâu thuẫn, không có URL đầy đủ
   (mục D14).
3. **SpreadsheetBench 2** — chỉ có arXiv ID 2606.29955 và mô tả, không có URL đầy đủ
   (mục D15).
4. **ZAIC 2023 repo baseline** — chỉ có tên repo, không có URL đầy đủ dùng được
   (mục F1).
5. **PhoWhisper paper trên OpenReview** — chỉ có domain openreview.net, không có URL
   bài cụ thể (mục B3).
6. **IFFC router claim** — bài đăng LinkedIn/company, không có URL xác minh
   (mục C20).
7. **AppWorld trong ghi chú LifeMate gốc** — không có URL xác minh; ở đây đã dùng
   URL alphaxiv từ ghi chú chuyển giao (mục C7, secondary) thay vì bịa link mới.
8. **vLLM guided_json / Outlines / XGrammar / llama.cpp GBNF** — hướng dẫn thứ cấp
   tổng hợp, không trích một URL duy nhất chưa xác minh; không liệt kê thành nguồn
   riêng.
