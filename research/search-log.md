# Nhật ký tìm kiếm — round 2 (2026-10-27)

> Không coi việc chưa tìm thấy trong một lượt search là bằng chứng nguồn không
> tồn tại. Ghi rõ đã tìm ở đâu và còn đường nào chưa kiểm tra. Ngày truy cập
> cho mọi nguồn round 2: 2026-10-27. Các nguồn round 1 (2026-10-26) được giữ
> trong [../sources.md](../sources.md).

## 1. Nhóm từ khóa — LifeMate

| # | Nhóm từ khóa | Nơi tìm | Nguồn mới / kết quả |
|---|---|---|---|
| L-K1 | `tau-bench / tau2 / tau3 voice agent benchmark tool calling state github` | GitHub repo pages (text-fetch), DeepWiki, arXiv | τ²-bench README (MIT, commit `70f71c`), τ-Elicitation (arXiv 2609.13602), τ-bench DeepWiki (ToolCallingAgent, Agent Implementations — DEEPWIKI_SUMMARY, không phải thân code) |
| L-K2 | `AppWorld agent benchmark code execution loop tool error recovery` | arXiv, tin tức | AppWorld paper chính thức (arXiv 2407.18901, appworld.dev, repo stonybrooknlp — repo chưa mở trực tiếp); ScholarEvolve (tin tức, model 27B vượt trần — chỉ lấy ý harness) |
| L-K3 | `PhoWhisper Vietnamese ASR Hugging Face vinai` | HF qua nguồn thứ cấp, SparkNLP | HF ID `vinai/PhoWhisper-small` (qua SparkNLP, SECONDARY); VieGem-ASR (loại tạm vì ngày chưa xác minh) |
| L-K4 | `Salesforce xLAM-2 function calling Hugging Face 3B` | HF card GGUF, báo chí, trang đo | Series table (GGUF card), licence CC BY-NC (báo chí, SECONDARY), BFCL v4 arena 83,7% (first-party, không phải leaderboard chính thức) |
| L-K5 | `speech to tool calling voice agent ASR entity error correction N-best` | arXiv | RECOVER (arXiv 2603.16411), GEC-RAG (2501.10734), RAC (2409.06062), acoustic neighbor embeddings |
| L-K6 | `github sierra-research tau-bench agent loop run.py` | DeepWiki | ToolCallingAgent + Agent Implementations (không phải thân code) |
| L-K7 | `github AppWorld benchmark stanford code agent execution shell` | Paper + tin tức | Paper + ScholarEvolve; repo AppWorld chính thức chưa mở trực tiếp |
| L-K8 | `Salesforce APIGen github function calling data generation` | arXiv, Distilabel | APIGen paper (2406.18518) + Distilabel pipeline (không phải repo APIGen gốc) |
| L-K9 | `Hammer function calling MadeAgents github ICLR 2025 irrelevance` | GitHub README, ICLR paper | Repo README (Apache-2.0, commit `ff415d`), paper ICLR 2025, dataset irrelevance 7,5k, mask ablation |
| L-K10 | `small language model tool calling agent loop retry error recovery` | GitHub, arXiv | Forge (README, MIT, commit `3e5a38`), FISSION-GRPO (ACL 2026, tên repo chưa xác minh URL) |
| L-K11 | `Vietnamese ASR negation number money date error voice assistant slot` | arXiv, dự án độc lập | Task-role paper (2610.17619, ngày vs cutoff chưa xác minh), Callona design rules, blog 'Why WER lies' |
| L-K12 | `Qwen3-4B-Instruct-2507 Hugging Face Apache license release` | KDnuggets, AIChina (secondary-corroborated) | Sau đó đã xác minh một phần qua HF card chính thức (commit `cdbee75`, Apache 2.0, 4,0B/3,6B, tháng 7/2025) — xem sources C16 |
| L-K13 | `raw.githubusercontent.com forge / Hammer` | Text-fetch | Không trả về thân file; chỉ trả README/mirror — vì vậy không repo nào trong round 2 là CODE_INSPECTED ngoài ReFoRCE (DataMate) |
| L-K14 | `tau2-bench voice entity intake exact entity capture` | README τ² | τ-Elicitation (Pass³ scaffold +14–31 điểm với chi phí 21–28 s — gần chạm trần 30 s/mẫu) |
| L-K15 | `faster-whisper CTranslate2 latency A30` | PyPI | Benchmark V100S/CPU (không có số A30) — không suy ra số LifeMate |

## 2. Nhóm từ khóa — DataMate

| # | Nhóm từ khóa | Nơi tìm | Nguồn mới / kết quả |
|---|---|---|---|
| D-K1 | DABstep paper, baseline, leaderboard | arXiv, HF Space | Paper chính thức arXiv 2506.23719 (mới ở mức xác minh: đã có arXiv ID + ngày + bảng); baseline Space được trích trong paper nhưng fetch tree không liệt kê file → chưa CODE_INSPECTED |
| D-K2 | Spider 2.0 paper, số liệu | arXiv 2411.07763 | Xác nhận 632 task, trung bình 812 cột, o1-preview code agent 21,3% trong một phiên bản paper vs 17,0% trong phiên bản khác (v1/v2) — mâu thuẫn phiên bản, ghi rõ, không chọn một con; sau đó đã bỏ 17,1% theo quy tắc 'số phải có setting + backbone' |
| D-K3 | ReFoRCE code, agent, sql, schema linking | GitHub API (Snowflake-Labs/ReFoRCE) | CODE_INSPECTED 3 file + LICENSE; README tự báo cáo 35,83/36,56 (o3) vs số paper cũ thấp hơn — mâu thuẫn phiên bản, ghi rõ |
| D-K4 | DSR-SQL code | GitHub API, arXiv 2511.21402 | Paper READ; repo chính thức DMIRLAB-Group/DSR-SQL 404 trong phiên này; chỉ Lite có code, Snow/BIRD chưa công bố |
| D-K5 | schemagate, BIRD Mini-Dev | GitHub API, PyPI, DEV post | README_READ + LICENSE Apache 2.0; số Mini-Dev tự báo cáo, chưa có leaderboard chính thức |
| D-K6 | SpreadsheetBench 2 | arXiv 2606.29955 | URL đầy đủ đã có (sửa khoảng trống round 1); 321 task, best 34,89%, debugging 12,00%. **Xung đột giữa hai ghi chú round 2** (sources tìm không thấy vs datamate trích đầy đủ) đã được giải quyết bằng cách mở trực tiếp trang arXiv abs trong đợt áp dụng này: tiêu đề/tác giả/ngày/số khớp — claim được giữ với nhãn đã xác minh qua arXiv |
| D-K7 | Selective prediction, abstention, calibration | arXiv 2305.14613, 2601.00138 | Kamath formalism; bằng chứng vỡ calibration khi bằng chứng suy giảm (video QA, miền khác — chỉ dùng làm cảnh báo) |
| D-K8 | Self-debug, Data Interpreter, QualityFlow | arXiv 2402.18679, 2501.17167 | Vòng sửa theo lỗi thực thi + cảnh báo lệch quỹ đạo (verifier xác nhận sai 32/389 ca trong nghiên cứu 2026 về SpreadsheetBench v1) |
| D-K9 | Qwen2.5-Coder-7B HF | huggingface.co (chính thức) | 7,61B tổng / 6,53B non-embedding / 131k context / citation 2024; ngày commit đầu tiên chưa trích |
| D-K10 | Kaggle data-analysis winning solutions | Web search | Không tìm được winning solution nào đủ gần DataMate (kết quả là Titanic/feature engineering chung, PARC/AutoKaggle cho ML competition — không phải tabular QA có type exact + rulebook) → hướng này coi là chưa bão hòa nhưng kém ưu tiên hơn BIRD/DABstep/Spider 2.0 |

## 3. Nhóm từ khóa — kiểm chứng nguồn và model

| # | Nhóm từ khóa | Nơi tìm | Kết quả |
|---|---|---|---|
| M-K1 | Benchmark gốc: 'DABstep benchmark official site', 'Spider 2.0 benchmark official', 'SpreadsheetBench arXiv', 'BIRD benchmark official leaderboard' | arXiv, ACL Anthology, HF, blog chính thức | DABstep / Spider 2.0 / SpreadsheetBench gốc đã có nguồn chính thức; BIRD top ~82–83% (thứ cấp, thay đổi theo thời gian) |
| M-K2 | Phương pháp: 'DB-Explore ACL Anthology EMNLP 2025', 'Alpha-SQL MCTS arXiv', 'Bridging the Detection-to-Abstention Gap arXiv', 'RSL-SQL GitHub', 'AppWorld official paper 2407.18901', 'tau-bench official results', 'BFCL official v3 v4 methodology' | arXiv, ACL Anthology, GitHub | DB-Explore record ACL + DOI; Alpha-SQL arXiv + PMLR; Judge-Then-Solve ID sửa thành 2605.28070; AppWorld arXiv + site + repo; τ-bench Table 3; BFCL v4 (17/07/2025, trọng số agentic 40% — theo tổng hợp DeepWiki từ CHANGELOG, Secondary) |
| M-K3 | Model: 'Qwen3-4B-Instruct-2507 HF', 'Qwen2.5-Coder-7B-Instruct HF', 'Qwen3-8B/14B parameters license', 'Salesforce xLAM-2-3b-fc-r HF', 'MadeAgents Hammer HF license', 'PhoWhisper VinAI HF', 'VinAI PhoBERT HF', 'Llama 3.2 3B Instruct HF' | HF card (snippet), blog chính thức Qwen/Adyen, OpenReview snippet, README PhoBERT (raw.githubusercontent) | Xem bảng shortlist model trong research/comparison.md và plans: Qwen3-4B card chính thức; Qwen2.5-Coder bảng chính thức; PhoBERT README chính thức; các mục còn lại vẫn chưa xác minh đầy đủ (xem gaps.md) |

## 4. Hướng đã bão hòa (không tìm thêm theo cùng từ khóa)

- Khung ReAct / ToolCallingAgent cơ bản; WER tổng của PhoWhisper; số BFCL tổng quát.
- Text-to-SQL pipeline tổng quát (MCS/BASE/CHESS/Alpha-SQL đã đủ để chọn cơ chế).
- DABstep ở mức paper (đã đủ, thiếu chỉ là file baseline cụ thể trong HF Space).
- Các tổng hợp thứ cấp về BIRD/Spider 2.0 leaderboard top (số thay đổi theo thời gian, không giúp chọn pipeline).
- Các blog giới thiệu Qwen chung chung (không có số config); các bài 'top small models' không ghi version BFCL.
- Danh sách model > 5B (LifeMate) / > 15B (DataMate) — đã loại, không cần tìm thêm.

## 5. Hướng còn thiếu (chưa kiểm tra — không được kết luận là không tồn tại)

1. Thân file code của Forge (`response_validator.py`, `step_enforcer.py`,
   `error_tracker.py`, `runner.py`), τ-bench (`tool_calling_agent.py`,
   `chat_react_agent.py`, `auto_error_identification.py`), Hammer
   (`train/data_processing.py`), ToolSandbox — cần `git clone` tại commit đã
   ghi rồi đọc thật.
2. HF card trực tiếp của: `vinai/PhoWhisper-*`,
   `Qwen/Qwen3-4B-Instruct-2507` (đã xác minh một phần), `Salesforce/Llama-xLAM-2-3b-fc-r`,
   `MadeAgents/Hammer-4b`, `MadeAgents/Hammer2.1-3b` (licence, ngày, config
   tổng tham số, format tool).
3. Evaluator ZAIC thật: regulations PDF, README trong zip LifeMate, tool
   catalog, đặc tả submission/trace/F1 — quyết định về selective reads và
   loop guard có đúng hay không (câu hỏi Q-L1..Q-L6, Q-D1..Q-D6 trong gaps.md).
4. Đo thực tế: latency A30, slot-error tiếng Việt trên audio ZAIC, N-best
   diversity của PhoWhisper, tỉ lệ loop thật trên train.
5. Repo nhỏ độc lập về small-model tool loop (ngoài Forge) và về Vietnamese
   speech-to-action end-to-end (ngoài PhoWhisper + LLM) — mới tìm qua search
   chung, chưa quét GitHub topic/language có hệ thống.
6. ToolSandbox code + AppWorld repo chính thức (chỉ mới đọc paper/tin tức).
7. File baseline DABstep trong HF Space (mở từng file, không chỉ trang tree).
8. Repo chính thức BASE-SQL và CHESS (chưa xác định URL trong round 2).
9. Evaluator + README + rulebook trong gói dữ liệu ZAIC đã tải (giải nén và
   đọc — việc quan trọng nhất, vì nó quyết định mọi giả định còn lại).
10. Ngày commit đầu tiên trên HF của từng checkpoint shortlist + cách BTC tính
    tổng tham số (total vs non-embedding) + cách tính checkpoint phái sinh.
11. Winning solutions thực sự cho tabular QA trên Kaggle/AIcrowd/Codabench kèm
    code và license.
12. Chuẩn hóa Excel bẩn ở mức file/commit (openpyxl/mở file thật, header lệch,
    merged cells) — round 2 chỉ dừng ở mức thiết kế profiler, chưa đọc code
    thư viện nào cho phần này.
13. Toàn văn ReAct (bảng ALFWorld 71% vs 79% vẫn mâu thuẫn), toàn văn Spider 2.0
    (bảng setting Snow/Lite/DBT), toàn văn DABstep (bảng easy/hard theo backbone).
