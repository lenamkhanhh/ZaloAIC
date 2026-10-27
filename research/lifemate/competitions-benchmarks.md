# LifeMate — Cuộc thi và benchmark chuyển giao

> Số leaderboard ở đây chỉ dùng để chọn cơ chế, không dùng làm mục tiêu số học.
> Mọi số đều ghi mức bằng chứng; số thứ cấp mâu thuẫn theo phiên bản thì không
> chọn một con tùy tiện.

## 1. Benchmark gần LifeMate nhất: chấm bằng state cuối

### τ-bench / τ²-bench / τ³-bench

- **Bài toán:** agent trò chuyện với user mô phỏng, dùng tool theo policy của domain,
  chấm bằng **final database state** — gần nhất với cách LifeMate chấm bằng
  `state_hash`.
- **Repo:** https://github.com/sierra-research/tau-bench — commit
  `59a200c6d575d595120f1cb70fea53cef0632f6b`, MIT, 1.481 stars, 221 forks lúc mở.
  Paper: https://arxiv.org/abs/2406.12045. Các file agent cụ thể trong round 2
  chỉ ở mức DEEPWIKI_SUMMARY — xem deep-profiles.md §4.
- **Số τ-bench — bắt buộc ghi điều kiện (paper arXiv 2406.12045, Table 3):**
  GPT-4o pass¹ có policy: retail 61,2 / airline 33,2; bỏ policy khỏi system
  prompt: retail 56,8 / airline 10,8 (airline phụ thuộc policy mạnh hơn rất
  nhiều). Không trộn số README (Claude 0,692 retail) với số paper gốc — hai
  thời điểm/phiên bản task khác nhau; repo đã cảnh báo task cũ. Metric pass^k
  đo tính nhất quán qua k lần thử — quan trọng vì ZAIC chạy lại Docker 5 lần
  lấy trung bình khi kết quả không ổn định.
- **Tái sử dụng:** `auto_error_identification.py` phân loại lỗi thành
  `goal_partially_completed`, `used_wrong_tool`, `used_wrong_tool_argument`,
  `took_unintended_action` — mượn nguyên làm khung phân tích lỗi LifeMate.
- **Cảnh báo:** README τ-bench cảnh báo task trong repo đã lỗi thời và trỏ sang
  τ²/τ³-bench; τ³ có thêm voice evaluation modality — trực tiếp liên quan LifeMate.
  Ưu tiên τ³ khi tham khảo, không dùng số τ-bench cũ làm mục tiêu.
- **Bài học phản trực giác (secondary):** agent "không làm gì" vẫn có thể đạt điểm
  trên một số task không đổi trạng thái — vì vậy phải kiểm tra riêng mẫu gold rỗng
  và mẫu đổi trạng thái, không chỉ nhìn điểm tổng.

### AppWorld

- **Bài toán:** 750 task trên 9 app mô phỏng, 457 API, chấm bằng state-based unit
  test (cho phép nhiều đường đi đúng, phạt collateral damage — thay đổi ngoài ý muốn).
- **Kết quả (author-reported, abstract chính thức):** GPT-4o ~49% normal,
  ~30% challenge; các model khác thấp hơn ít nhất 16 điểm. **Đã bỏ con số
  "Test-C 30,2% → 35,2% khi cho sẵn API đáp án"** vì abstract chính thức không
  chứa nó — không trích lại cho tới khi đối chiếu được bảng gốc trong toàn văn.
  Nguồn chính thức: paper https://arxiv.org/pdf/2407.18901, site
  https://appworld.dev/, repo https://github.com/stonybrooknlp/appworld
  (repo chưa mở trực tiếp trong round 2 — không gắn CODE_INSPECTED).
- **Chuyển giao (transfer hypothesis):** selective reads (precondition read chỉ
  khi precondition chưa xác lập; grounding read khi cần ground ID; KHÔNG
  verification read sau write theo mặc định — xem deep-profiles.md §0.1),
  và **không gọi write thừa** — mỗi write thừa đều có thể phá `state_hash`.
  Không tự xây simulator riêng; dùng đúng `zaic_tools` của ban tổ chức.

### ToolSandbox

- **Bài toán:** benchmark tool-use có trạng thái, hội thoại, user simulator, đánh giá
  động bằng milestones/minefields trên quỹ đạo bất kỳ.
- **Repo (đã mở một phần):** https://github.com/apple/ToolSandbox — commit
  `c8571d7854316d2e1c5f288e59fe1e34e53f6dd1`, 290 stars, 33 forks lúc mở.
  Paper: https://arxiv.org/abs/2408.04682 (secondary). Không gắn CODE_INSPECTED
  cho ToolSandbox trong round 2.
- **Cảnh báo license:** trang hiển thị license "Other (NOASSERTION)" — **đọc file
  LICENSE thực tế trước khi copy code vào solution.**
- **Chuyển giao:** mượn khái niệm milestone (state trung gian phải đạt) và minefield
  (state cấm) làm harness đánh giá nội bộ; mượn 3 nhóm khó được đặt tên rõ:
  State Dependency, Canonicalization, Insufficient Information — trùng 3 nhóm lỗi
  của LifeMate.

### BFCL (Berkeley Function-Calling Leaderboard)

- **Cơ chế chấm:** AST matching + executable evaluation; có hạng mục
  relevance/irrelevance, multi-turn, multi-step, live.
- **Dùng đúng:** chỉ để sàng lọc ứng viên ban đầu và học các dạng lỗi (sai tên, sai
  kiểu, thiếu trường, gọi thừa). Mượn hạng mục relevance/irrelevance làm test riêng
  cho ask/refuse, và AST matching làm metric debug nội bộ nhanh.
- **Không dùng để chốt model:** số BFCL mâu thuẫn theo phiên bản/tập model giữa các
  nguồn thứ cấp; BFCL không đo state cuối, không đo tiếng Việt, không đo
  ask/refuse của LifeMate. Thắng BFCL không suy ra thắng ZAIC.

## 2. Vietnamese ASR

### PhoWhisper — lựa chọn mặc định (code-read)

- **Repo:** https://github.com/VinAIResearch/PhoWhisper — commit
  `b06f1937995cfee75b9e4ad3e2ae0798faf1a562`, BSD-3-Clause. Fine-tune Whisper
  trên 844 giờ giọng Việt. Paper: ICLR 2024 Tiny Papers, arXiv
  https://arxiv.org/pdf/2406.02555 (canonical OpenReview forum URL vẫn chưa có
  dạng verbatim — mở OpenReview tìm 'PhoWhisper' thay vì trích attachment link).
- **Kích thước và WER (bảng README, code-read):**

  | Model | Tham số | VIVOS | VLSP 2020 Task-2 |
  |---|---|---|---|
  | tiny | 39M | 10,41 | 49,85 |
  | base | 74M | 8,46 | 43,01 |
  | small | 244M | 6,33 | 32,96 |
  | medium | 769M | 4,97 | 26,85 |
  | large | 1,55B | 4,67 | 26,68 |

- **Ngân sách với LLM 4B (tính toán từ luật, transfer hypothesis):** small + 4B ≈
  4,24B (an toàn); medium + 4B ≈ 4,77B; large + 4B ≈ 5,55B (sát trần, tốn latency).
  Bắt đầu bằng small/medium, không lấy large làm mặc định.
- **Giới hạn:** WER trên VIVOS/VLSP không chuyển thành tỉ lệ state đúng; chênh lệch
  lớn giữa benchmark (VIVOS 6,33% vs VLSP Task-2 32,96% cho small) cho thấy domain
  mismatch có thể lớn hơn chênh lệch giữa các checkpoint. **VIVOS là read speech,
  không phải audio LifeMate — không bao giờ dùng WER VIVOS làm mục tiêu cho
  LifeMate;** đo slot-error theo role trên train ZAIC (xem deep-profiles §3).
- **Chưa xác minh:** HF repo, licence và ngày phát hành từng checkpoint PhoWhisper
  — kiểm tra trước khi đưa vào Docker nộp bài.
- **VIVOS:** corpus 15 giờ, read speech, 46 speaker train / 19 test, CC BY-NC-SA
  4.0 (Zenodo: https://zenodo.org/records/7068130). Dùng để sanity check ASR,
  không chứng minh ASR tốt trên lệnh app tự nhiên của LifeMate.

### Các hướng ASR khác — chỉ ở mức giả thuyết

- **Fine-tune Whisper cho lyrics (author-reported, miền khác):** fine-tune
  Whisper-large-v2 được báo cáo 24,61% WER so với PhoWhisper-large 38,3% trên tập
  lyrics — không kết luận fine-tune thắng PhoWhisper cho LifeMate.
- **Code-switching / entity-heavy ASR (ViMedCSS, TSPC):** kiến trúc nghiên cứu,
  chưa xác minh code/checkpoint dùng ngay — chỉ rút ra ý: nếu LifeMate có tên
  riêng/tiếng Anh xen tiếng Việt thì test riêng nhóm sample đó.
- **faster-whisper / CTranslate2 (secondary):** được mô tả nhanh hơn Whisper 4–8×
  nhờ quantisation và VAD — hướng tối ưu latency đáng thử, nhưng **chưa có số đo
  trên A30**; phải đo trên chính Docker/A30 của submission.
- **RECOVER — agentic ASR entity correction (author-reported, chưa test ZAIC):**
  N-best → retrieve ứng viên entity → LLM chọn/sửa trong ràng buộc; được báo cáo
  giảm tương đối 8–46% entity-phrase WER và tăng tới 22 điểm phần trăm recall trên
  5 dataset của tác giả. Áp dụng cho LifeMate: N-best + candidate list đóng từ
  tool read (contacts, devices, accounts); số tiền/ngày phải khớp chính xác hoặc
  hỏi lại, không fuzzy đoán. Paper: https://arxiv.org/pdf/2603.16411.
- **DeRAGEC / G-SPIN:** chỉ xuất hiện ở mức snippet thứ cấp, chưa đọc code/commit
  — backlog, không đưa vào pipeline chính.
- **Task-role diagnostics ("When Does an ASR Error Matter?"):** khung phân loại lỗi
  ASR theo vai trò (số/ngày/ID, named entity, phủ định, cue ý định) — dùng để chẩn
  đoán, không dùng checkpoint từ paper này cho tới khi xác minh ngày so với cutoff.
  Paper: https://arxiv.org/pdf/2610.17619v1.
