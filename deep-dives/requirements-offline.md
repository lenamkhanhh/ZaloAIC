# requirements-offline.md — Dependency list cho Docker offline

> Nguyên tắc: mọi thư viện dưới đây phải có sẵn trong image Docker
> (wheelhouse đóng gói sẵn) trước khi nộp bài; **không `pip install`
> lúc chạy chấm, không tải extension/model/API lúc chạy**. Chỉ một
> phiên bản duy nhất cho mỗi thư viện được pin tại lúc build và ghi vào
> `requirements.lock` cùng với file LICENSE của đúng artifact đó.
>
> **Quy tắc phiên bản:** không bịa số phiên bản. Ở đâu bản nháp không
> xác minh được phiên bản, bảng dưới ghi rõ "pin at build time from the
> tested wheelhouse and record it in requirements.lock" thay vì một con
> số giả. Các số phiên bản duy nhất được ghi là những số đã xuất hiện
> trong venv thử của bản nháp chuyên đề 3 (DuckDB 2.0.0, pandas 3.1.0,
> openpyxl 3.1.5) — và ngay cả những số đó cũng phải kiểm tra lại lúc
> build, vì "mới nhất" tại lúc build có thể đã khác.

## 1. LifeMate — chuyên đề 1 + 2

| Thư viện | Vai trò | Licence (trạng thái xác minh) | Phiên bản |
|---|---|---|---|
| vLLM | Inference engine cho Qwen3-4B-Instruct-2507; backend constrained decoding mặc định là XGrammar | Apache 2.0 (thứ cấp đã kiểm chứng ngày 2026-09-23 — kiểm tra lại LICENSE trong wheel đã pin) | Pin at build time from the tested wheelhouse and record it in requirements.lock. **Bắt buộc:** API structured output đã đổi tên theo phiên bản (guided_* cũ → `StructuredOutputParams` từ vLLM 0.12 theo tài liệu thứ cấp); chỉ dùng đúng một phiên bản đã test trên A30 |
| XGrammar (mlc-ai/xgrammar) | Token-mask engine cho JSON Schema/regex/grammar, qua vLLM | Apache 2.0 (nhiều nguồn thứ cấp thống nhất — kiểm tra lại LICENSE trong wheel đã pin) | Pin at build time from the tested wheelhouse and record it in requirements.lock (thường đi kèm vLLM; kiểm tra wheel có sẵn cho đúng CUDA + Python của image) |
| Outlines (dottxt-ai/outlines) | Backend dự phòng số 1 cho constrained decoding (đổi bằng một flag) | Apache 2.0 open-source (thứ cấp; trang chủ .txt đồng thời quảng bá thư viện thương mại khác của công ty — không đồng nghĩa Outlines đổi licence; kiểm tra LICENSE của đúng phiên bản đã pin) | Pin at build time from the tested wheelhouse and record it in requirements.lock (chỉ cần nếu dùng làm dự phòng) |
| Guidance (guidance-ai/guidance) + llguidance | Backend dự phòng số 2 / nghiên cứu thêm; điều khiển sinh ở mức field | **MÂU THUẪN — CHƯA KẾT LUẬN:** trang GitHub của repo hiển thị "MIT License", bảng capability thứ cấp ghi "Apache-2.0". **Không đưa vào Docker cho tới khi đọc `LICENSE.md` của đúng commit/checkout đã pin và ghi kết quả vào `sources.md`** | Pin at build time from the tested wheelhouse and record it in requirements.lock (chỉ nếu quyết định dùng sau khi giải quyết licence) |
| Instructor (jxnl/instructor) | **Không phải dependency cho vLLM offline.** Chỉ dùng (nếu muốn) ở vai trò validate + retry ở client cho pipeline gọi API — không dùng làm lớp schema enforcement chính cho LifeMate | MIT (trang PyPI của package) | Pin at build time from the tested wheelhouse and record it in requirements.lock (không bắt buộc) |
| Pydantic | Không bắt buộc — validator trong code chuyên đề 1 viết tay bằng stdlib | MIT (thứ cấp) | Pin at build time from the tested wheelhouse and record it in requirements.lock (chỉ nếu dùng thêm) |
| RapidFuzz | Fuzzy matching cho grounding tiếng Việt (WRatio, token_sort) trong chuyên đề 2; fallback là `difflib` của stdlib nếu không có | MIT (trang PyPI của dự án, đã xác minh) | Pin at build time from the tested wheelhouse and record it in requirements.lock (phiên bản cụ thể không khẳng định — một nguồn thứ cấp nhắc 3.14.3 nhưng chưa đối chiếu trực tiếp) |
| Python stdlib (`unicodedata`, `re`, `difflib`, `dataclasses`, `json`, `sqlite3`) | NFC, tone key, fallback fuzzy, validator, đọc SQLite | Stdlib, không cần licence riêng | Theo phiên bản Python của image (ghi rõ trong Dockerfile) |

### Model LifeMate (không phải thư viện pip — đóng gói weights trong image)

| Model | Vai trò | Tổng tham số | Licence / ngày — trạng thái xác minh |
|---|---|---|---|
| Qwen3-4B-Instruct-2507 (Qwen) | LLM duy nhất cho LifeMate | 4,0B tổng / 3,6B không tính embedding | Apache 2.0, HF commit `cdbee75`, series tháng 7/2025 (trước mốc 26/10/2026) — xem [../research/comparison.md](../research/comparison.md). Đọc lại `config.json` + LICENSE trên HF trước khi đóng Docker |
| PhoWhisper-small (vinai) | ASR tiếng Việt | 244M | Paper ICLR 2024 Tiny Papers, arXiv 2406.02555; licence của checkpoint trên HF **chưa xác minh** — đọc card HF trước khi đóng Docker |
| PhoWhisper-medium (vinai) | ASR dự phòng (đổi khi slot-error là nhóm lỗi lớn nhất) | 769M | Như trên; tổng hệ thống với LLM 4B là 4,769B (small: 4,244B) |

## 2. DataMate — chuyên đề 3 + 4

| Thư viện | Vai trò | Licence (trạng thái xác minh) | Phiên bản |
|---|---|---|---|
| DuckDB (Python client) | Execution engine duy nhất ở luồng chính (SQL SELECT/WITH); đăng ký view thống nhất, nạp `calendar.csv` | MIT (thứ cấp — chưa đối chiếu file LICENSE gốc trong phiên này; metadata gói trong venv thử không có trường License nên không kết luận từ đó; kiểm tra lại LICENSE khi đóng Docker) | 2.0.0 trong venv thử ngày 2026-10-27 — **kiểm tra lại lúc build**; snippet trang tổng quan cũ ghi "latest stable 1.4.2", không tin snippet cũ. **Không dùng DuckDB sqlite extension** (cần tải về lần đầu) và không dùng `read_xlsx` qua extension chưa có sẵn — Excel đi qua openpyxl |
| pandas | Tầng kiểm chứng độc lập (khi logic thật sự khác SQL) và hỗ trợ tiền xử lý; **không** phải engine chính | BSD-3-Clause (thứ cấp — chưa đối chiếu file LICENSE gốc; kiểm tra lại LICENSE khi đóng Docker) | 3.1.0 trong venv thử ngày 2026-10-27 — **kiểm tra lại lúc build** |
| polars | Chỉ là phương án dự phòng ở tầng kiểm chứng nếu đo thấy pandas chậm một cách có ý nghĩa (giây/câu hỏi trên cùng held-out và cùng máy) | MIT (thứ cấp — kiểm tra lại LICENSE khi đóng Docker) | Pin at build time from the tested wheelhouse and record it in requirements.lock (không đưa vào ngay từ đầu) |
| openpyxl | Đọc Excel bẩn: merged cells, header nhiều cấp, format số/ngày VN (`data_only=True` cho giá trị đã tính) | MIT (xác nhận từ metadata gói trong venv thử) | 3.1.5 trong venv thử ngày 2026-10-27 — **kiểm tra lại lúc build**. Chỉ đọc `.xlsx`/`.xlsm`; file `.xls` cũ cần chuyển đổi riêng, ghi lại ngày/giờ, công cụ, số dòng trước/sau |
| Python stdlib (`sqlite3`, `re`, `unicodedata`, `json`, `math`, `collections`) | Đọc SQLite (không qua DuckDB extension), parse số/ngày, consensus/calibration (chuyên đề 4 dùng stdlib thuần túy) | Stdlib, không cần licence riêng | Theo phiên bản Python của image |

### Model DataMate (đóng gói weights trong image)

| Model | Vai trò | Tổng tham số | Licence / ngày — trạng thái xác minh |
|---|---|---|---|
| Qwen2.5-Coder-7B-Instruct (Qwen) | Code generator duy nhất ở luồng chính | 7,61B tổng / 6,53B không tính embedding | Apache 2.0; ngày commit đầu tiên trên HF **chưa xác minh** (chỉ có citation paper 2024 làm bằng chứng "trước 01/10/2026" ở mức khá chắc) — ghi lại ngày commit đầu tiên trước khi nộp; cách BTC tính tổng tham số (total vs non-embedding) **chưa xác minh** |
| vinai/phobert-base | Encoder phụ cho schema/value linking (tùy chọn) | 0,135B | MIT (README chính thức VinAIResearch/PhoBERT). **Không dùng `phobert-base-v2` (GNU AGPL v3)** trừ khi chấp nhận copyleft. Input bắt buộc đã tách từ tiếng Việt (chi phí + licence của bộ tách từ chưa tính trong ngân sách) |
| Tổng ngân sách DataMate (mẫu) | Qwen2.5-Coder-7B + PhoBERT-base | 7,61 + 0,135 = **7,745B** (dưới trần 15B, dư 7,255B) | Quantization không làm giảm tổng tham số; checkpoint fine-tune tính theo ngày nào **chưa xác minh** — xem [../gaps.md](../gaps.md) |

## 3. Những gì KHÔNG có trong Docker (và vì sao)

- **Không API thương mại, không model gọi qua mạng:** cả hai track đều
  chạy offline hoàn toàn; mọi model phải là open-source trước mốc cutoff
  của track đó (LifeMate 26/10/2026, DataMate 01/10/2026) và đã đóng gói
  trong image.
- **Không DuckDB extension tải lúc chạy, không thư viện âm lịch làm
  chuẩn:** lịch âm Việt Nam lấy từ `calendar.csv` của đúng split; thư
  viện âm lịch (nếu dùng) chỉ là fallback và mọi ngày từ fallback phải
  gắn cờ trong audit; không thay lịch Việt Nam bằng lịch Trung Quốc.
- **Không FuzzyWuzzy:** licence GPL là rủi ro không cần thiết khi
  RapidFuzz (MIT) làm cùng việc nhanh hơn.
- **Không Double Metaphone tiếng Việt, không Levenshtein có trọng số
  thanh điệu cho tiếng Việt:** không tìm thấy thư viện đã xác minh cho
  hai thứ này — chuyên đề 2 thay bằng quy tắc trần điểm + ngưỡng/biên
  bằng code thuần (thiết kế, chưa đo).

## 4. Checklist trước khi đóng Docker

1. Pin đúng một phiên bản cho mỗi thư viện trong bảng trên; ghi vào
   `requirements.lock` kèm hash wheel (nếu wheelhouse hỗ trợ).
2. Đọc file LICENSE của đúng artifact đã pin cho: vLLM, XGrammar,
   Outlines, Guidance (nếu dùng — giải quyết mâu thuẫn MIT vs
   Apache-2.0 trước), RapidFuzz, DuckDB, pandas, openpyxl, polars (nếu
   dùng).
3. Đọc `config.json` + LICENSE trên Hugging Face cho Qwen3-4B-Instruct-2507,
   PhoWhisper từng size, Qwen2.5-Coder-7B-Instruct, PhoBERT-base trước
   khi đóng weights vào image.
4. Kiểm tra wheel của xgrammar/llguidance có sẵn cho đúng phiên bản CUDA
   + Python của image; test fallback backend (outlines) với cùng schema.
5. Xác minh không có bước nào trong 4 file code của deep-dives gọi mạng
   lúc chạy: chuyên đề 1 import vLLM lazy (chỉ khi build engine);
   chuyên đề 2 fallback `difflib` khi thiếu RapidFuzz; chuyên đề 3 không
   dùng DuckDB extension; chuyên đề 4 dùng stdlib thuần túy.
