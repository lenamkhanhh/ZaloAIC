# Deep-dives — 4 chuyên đề kỹ thuật kèm code mẫu (offline)

> Tổng hợp từ 4 bản nháp nghiên cứu ngày 2026-10-27. Đây là tài liệu
> kỹ thuật kèm code mẫu, **không phải pipeline thi đấu hoàn chỉnh** và
> **không có thực nghiệm nào chạy trên dữ liệu ZAIC thật** trong các
> chuyên đề này. Mọi phương pháp dưới đây là giả thuyết chuyển giao cho
> tới khi đo trên train held-out của ZAIC. Không push, không đổi
> visibility repo, không liên hệ ban tổ chức trong đợt tổng hợp này.

## Chỉ mục

| # | Chuyên đề | Báo cáo | Code mẫu | Khuyến nghị chính |
|---|---|---|---|---|
| 1 | Constrained Decoding & Schema Enforcement Offline cho LifeMate | [01-constrained-decoding-lifemate.md](01-constrained-decoding-lifemate.md) | [01-constrained-decoding-lifemate.py](01-constrained-decoding-lifemate.py) | XGrammar qua vLLM làm mặc định; Outlines dự phòng số 1; Guidance chỉ sau khi pin phiên bản và giải quyết mâu thuẫn licence; Instructor **không** phải engine constrained decoding |
| 2 | Entity Grounding & Sửa lỗi ASR cho Tiếng Việt (LifeMate) | [02-asr-grounding-lifemate.md](02-asr-grounding-lifemate.md) | [02-asr-grounding-lifemate.py](02-asr-grounding-lifemate.py) | Chỉ ground slot quyết định từ candidate trong sample, NFC giữ dấu, tiền/ngày/ID cấm fuzzy, phủ định chặn bằng guard code |
| 3 | DuckDB làm Execution Engine & Xử lý "Excel bẩn" cho DataMate | [03-duckdb-excel-datamate.md](03-duckdb-excel-datamate.md) | [03-duckdb-excel-datamate.py](03-duckdb-excel-datamate.py) | DuckDB là engine duy nhất ở luồng chính (SQL SELECT/WITH); Python chỉ tiền xử lý Excel bẩn và kiểm chứng; tiền thật dùng DECIMAL/số nguyên đồng, **không dùng float** |
| 4 | Thuật toán Đo độ tự tin & Cơ chế Abstain thực chiến (DataMate) | [04-confidence-abstain-datamate.md](04-confidence-abstain-datamate.md) | [04-confidence-abstain-datamate.py](04-confidence-abstain-datamate.py) | Consensus k=3 trên output thực thi + cổng kiểm tra độc lập; `unanswerable` (thiếu dữ liệu, xác định) tách khỏi `abstain` (không đủ tin cậy, xác suất); ngưỡng học trên `train_cal`, đo một lần trên `train_holdout` |

Danh sách dependency offline đầy đủ: xem
[requirements-offline.md](requirements-offline.md).

## Cập nhật đợt 3 (2026-10-27)

- **Sửa code + test hồi quy:** 4 file `.py` đã sửa các lỗi thực sự
  (không chỉ sửa diễn giải) và có bộ test chạy thật tại
  [tests/test_regressions.py](tests/test_regressions.py) — 54 test,
  `python3 -m unittest discover -s deep-dives/tests` → OK. Chi tiết
  từng lỗi trước/sau nằm ở mục "Cập nhật đợt 3" cuối mỗi chuyên đề.
  Chú ý: mục 3 và 7 ở trên (trọng số score 0,5/0,3/0,2; demo float cho
  tiền) giờ đã lỗi thời theo hướng mới — score trọng số không còn là
  cổng quyết định được khuyến nghị (xem research-updates §4), và tiền
  giờ có đường `parse_vn_money` riêng trả `Decimal` (xem cập nhật
  chuyên đề 3). Các mục cũ được giữ lại để thấy lịch sử, không xóa.
- **Tổng hợp research đợt 3:**
  [research-updates-2026-10-27.md](research-updates-2026-10-27.md)
  (chỉ ghi quyết định đổi hướng, không viết lại 4 chuyên đề) và 5 bản
  nháp đầy đủ trong `../research/`:
  [round3-p1-asr-repair-vs-ask.md](../research/round3-p1-asr-repair-vs-ask.md),
  [round3-p2-lifemate-models-recipe.md](../research/round3-p2-lifemate-models-recipe.md),
  [round3-p3-datamate-complete-solutions.md](../research/round3-p3-datamate-complete-solutions.md),
  [round3-p4-consensus-compute.md](../research/round3-p4-consensus-compute.md),
  [round3-p5-evidence-of-absence.md](../research/round3-p5-evidence-of-absence.md).
  Mọi claim SECONDARY/SNIPPET/UNVERIFIED trong các bản nháp vẫn giữ
  nguyên nhãn trong bản tổng hợp — không nâng cấp.

## Các sửa đổi / hiệu chỉnh đã áp dụng khi tổng hợp

1. **Model LifeMate đã sửa:** LLM LifeMate là Qwen3-4B-Instruct-2507
   (4,0B). Qwen2.5-Coder-7B-Instruct (7,61B) **không** phải LLM LifeMate
   (vượt trần < 5B) — nó chỉ là code generator cho DataMate. Điểm này đã
   sửa trong chuyên đề 1 so với bản yêu cầu gốc vốn liệt kê cả hai cho
   LifeMate.
2. **Loop guard đã thống nhất với round 2:** looping **không** đồng
   nghĩa thiếu thông tin hay ngoài phạm vi. Cơ chế: dừng, replan đúng
   1 lần từ dữ liệu đã đọc/cache, chỉ thực thi hành động mới có căn cứ,
   nếu không thì kết thúc trace nguyên trạng — không append
   `sys.ask_missing_info`, không append `[]`, không ghi write dọn dẹp,
   không lọc failed call. `ask_missing_info` chỉ khi chưa write gì và
   slot không ground được bằng bất kỳ read nào; `[]` chỉ sau khi kiểm
   tra catalog cho thấy không app đã cài nào xử lý được. Áp dụng cho
   chuyên đề 1 và 2 (guard phủ định trong chuyên đề 2 là quyết định
   chặn write độc lập, không phải fallback của loop guard).
3. **Ngưỡng DataMate đã thống nhất với round 2:** mọi ngưỡng học trên
   `train_cal` và đo một lần trên `train_holdout` (ưu tiên tách theo
   business/loại hình); public test không có gold để tự chấm local theo
   ghi nhận portal 2026-10-26 (phải xác minh bằng cách giải nén file
   thật; viết lại nếu file thật mâu thuẫn). Tất cả các ngưỡng — fuzzy
   88 / biên 8 / trần khác thanh 85 (chuyên đề 2), trọng số score
   0,5/0,3/0,2 (chuyên đề 4), PA +0,03 và các tiêu chí giữ/dừng khác —
   đều là **điểm khởi đầu đề xuất, chưa phải kết quả đo trên ZAIC**.
4. **Tiếng Việt — không strip dấu để ra quyết định:** so sánh trên NFC
   giữ dấu; khóa tách thanh chỉ là tín hiệu phụ để phát hiện khác
   thanh. Tiền/ngày/số tài khoản không bao giờ được fuzzy-guess. **Không
   tìm thấy thư viện Double Metaphone tiếng Việt hay thư viện
   Levenshtein có trọng số thanh điệu cho tiếng Việt** — ghi rõ trong
   chuyên đề 2, thay bằng quy tắc trần điểm + ngưỡng/biên (thiết kế,
   chưa đo). Ngoại lệ duy nhất: tên cột SQL nội bộ trong chuyên đề 3
   được chuyển thành dạng ASCII để làm định danh kỹ thuật, nhưng tên gốc
   đầy đủ dấu luôn giữ trong `header_mapping` — đây không phải strip
   dấu để matching giá trị.
5. **Instructor đã hạ đúng vai trò:** Instructor là lớp patch client +
   validate + retry cho provider API, **không phải engine ép token của
   vLLM offline** — không bao giờ trình bày nó như lớp schema
   enforcement chính cho vLLM.
6. **Số latency/ngân sách đều là ước lượng có giả định:** mọi con số A30
   (30s/mẫu), 6 giờ, break-even 24 giây/candidate tại N=600, k=3, G=2
   đều là **ước lượng từ công thức với giả định ghi rõ, chưa đo**;
   600 câu hỏi là giả định của người dùng, **không phải kích thước
   private test đã xác minh** — nếu N khác, tính lại theo công thức.
7. **Tiền tệ trong code chuyên đề 3:** demo dùng `float` chỉ để gọn.
   Báo cáo chuyên đề 3 đã gắn cảnh báo ở đầu: pipeline thật phải dùng
   `DECIMAL` (DuckDB) hoặc số nguyên đồng cho đáp án cuối, không bao
   giờ dùng float.
8. **Licence Guidance còn mâu thuẫn:** trang repo Guidance hiển thị MIT,
   bảng thứ cấp ghi Apache-2.0 — **chưa kết luận**. Đọc `LICENSE.md`
   của đúng checkout đã pin trước khi đưa Guidance vào Docker (xem
   [requirements-offline.md](requirements-offline.md)).
9. **Không trùng lặp với round 2:** các báo cáo này không chép lại
   shortlist model round 2 mà chỉ tham chiếu tới
   [../research/comparison.md](../research/comparison.md),
   [../plans/lifemate.md](../plans/lifemate.md),
   [../plans/datamate.md](../plans/datamate.md),
   [../research/lifemate/deep-profiles.md](../research/lifemate/deep-profiles.md),
   [../research/datamate/deep-profiles.md](../research/datamate/deep-profiles.md)
   và [../gaps.md](../gaps.md); mỗi báo cáo kết thúc bằng mục đã xác
   minh / giả định / cần đo / câu hỏi evaluator còn mở.

## Tài liệu liên quan trong repo (đọc trước khi dùng deep-dives)

- Cuộc thi và luật từng track:
  [../competition/lifemate.md](../competition/lifemate.md),
  [../competition/datamate.md](../competition/datamate.md),
  [../competition/metrics-submission.md](../competition/metrics-submission.md)
- Kế hoạch thử nghiệm trên held-out hợp lệ:
  [../plans/lifemate.md](../plans/lifemate.md),
  [../plans/datamate.md](../plans/datamate.md)
- Hồ sơ sâu round 2:
  [../research/lifemate/deep-profiles.md](../research/lifemate/deep-profiles.md),
  [../research/datamate/deep-profiles.md](../research/datamate/deep-profiles.md)
- Khoảng trống và câu hỏi evaluator:
  [../gaps.md](../gaps.md)
