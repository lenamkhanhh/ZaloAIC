# Khoảng trống — những gì chưa xác minh hoặc chưa truy cập được

> Đọc file này trước khi chốt bất kỳ quyết định nộp bài nào. Không lấp các mục
> dưới đây bằng suy đoán.

## 1. File HTML đính kèm của người dùng — không tìm thấy trong phiên này

- Người dùng nói đã gửi kèm file "Zalo AI Challenge 2026.html" làm context ban đầu.
  Trong workspace của phiên làm việc này, file đó **không xuất hiện** (đã tìm trong
  `~/workspace`, kể cả thư mục media và các artifact trước đó).
- Tài liệu này vì vậy dùng **bản artifact Zalo AI Challenge 2026 đã làm trước đó,
  toàn bộ chi tiết người dùng ghi trong yêu cầu, và portal chính thức kiểm tra
  2026-10-26** làm context thay thế.
- **Hành động:** nếu file thật sự chưa đính kèm, người dùng gửi lại file để đối
  chiếu; nếu file đã đính kèm ở một kênh khác, cần chuyển file vào `~/workspace/`
  rồi đối chiếu và cập nhật các điểm khác với nguồn chính thức (ưu tiên nguồn
  chính thức mới nhất khi có mâu thuẫn).

## 2. Portal và dữ liệu sau đăng nhập — chưa tải/giải nén trong phiên nghiên cứu

- Các gói zip DataMate (train, public_test) và LifeMate (train+public_test) chỉ
  được ghi nhận từ mục Data sau đăng nhập ngày 2026-10-26; **kích thước zip, số
  doanh nghiệp/câu hỏi chính xác, nội dung đầy đủ của README/rulebook/calendar.csv
  chưa được xác minh** bằng cách tải và giải nén trong phiên này.
- Catalog tool LifeMate chính xác (tên, tham số, enum, format tiền/ngày/ID),
  Docker base image, inference script chính thức — chưa xác minh.
- Một subagent DataMate trong phiên này đã thử tải lại text portal và thất bại;
  theo chỉ đạo runtime, yêu cầu đó không được lặp lại trong phiên đó — vì vậy các
  luật DataMate trong tài liệu này được ghi theo đề bài được giao và bối cảnh
  portal 2026-10-26, không phải "đã tự xác minh lại portal" trong phiên đó.

## 3. Evaluator — cách xử lý từng trường hợp chưa xác minh

### LifeMate
- Cách chấm chính xác của `sys.ask_missing_info` (đúng/sai/thừa/thiếu tính thế nào).
- Failed call có được giữ trong trace nộp hay phải loại bỏ.
- Mọi ToolEnv call có bắt buộc xuất hiện trong submission không.
- Validator lọc sau thực thi có vi phạm luật log call không.
- Cách tính tham số: total hay active (với MoE, giả định an toàn là total cho tới
  khi xác minh được).

### DataMate
- Missing answer (câu hỏi thiếu trong submission): ghi nhận từ portal sau đăng
  nhập 2026-10-26 là tính như abstain — **chưa tự xác minh evaluator**.
- Agent trả `unanswerable` khi reference là giá trị, và ngược lại.
- Sai type (ví dụ trả number thay vì percent, table sai cột).
- Hòa ranking tại biên k hoặc tại hạng 1: ghi nhận các trường hợp hòa được loại
  khỏi test set — chưa xác minh chi tiết trong evaluator/rulebook của split.
- Sai thứ tự list, sai làm tròn số, sai format date.
- Định dạng percent (0–100 hay 0–1).
- "Rows as set" cho table: thứ tự hàng có quan trọng không.
- **Hành động:** đọc evaluator (nếu có trong gói dữ liệu), README và rulebook của
  từng split; nếu evaluator không có trong gói, hỏi aichallenge@zalo.me và ghi lại
  câu trả lời. Không chốt pipeline dựa trên suy đoán ở các điểm này.

## 3b. Câu hỏi gửi ban tổ chức — LIỆT KÊ, KHÔNG GỬI (aichallenge@zalo.me)

> Theo nhiệm vụ round 2: chỉ liệt kê câu hỏi chính xác, không liên hệ BTC
> trong đợt này. Mọi mục dưới đây đều là chưa xác minh từ nguồn chính thức
> mà round 2 truy cập được; portal sau đăng nhập và gói zip dữ liệu chưa được
> tải/giải nén trong round 2.

**LifeMate:**
- **Q-L1:** Với mẫu thiếu thông tin, `sys.ask_missing_info` được chấm như thế
  nào trong tool-call F1: hỏi đúng tham số được tính ra sao, hỏi thừa/thiếu
  có bị trừ không, và có cần hỏi đúng thứ tự không?
- **Q-L2:** Submission có phải chứa toàn bộ ToolEnv call đã thực thi (kể cả
  failed call và read call) không, hay chỉ chứa các call cuối cùng tạo ra
  final state? Failed call có ảnh hưởng tới F1 không?
- **Q-L3:** Read call (ví dụ đọc contacts/devices/accounts trước khi write)
  có được tính trong tool-call F1 không? Nếu có, read thừa có bị trừ như
  write thừa không? (Quyết định trực tiếp bảng selective reads — xem
  research/lifemate/deep-profiles.md §0.1.)
- **Q-L4:** Nếu agent gọi một tool nhưng validator chặn không đưa call đó vào
  submission, có vi phạm quy định về log/trace không?
- **Q-L5:** Khi agent đạt giới hạn vòng lặp mà chưa hoàn thành task, submission
  nên chứa gì: trace đã thực thi tới thời điểm đó, `[]`, hay
  `sys.ask_missing_info`? Có quy định nào về số vòng lặp tối đa không?
- **Q-L6:** Tổng < 6B có bao gồm ASR và mọi model phụ không, và LLM < 5B được
  tính riêng như thế nào?

**Cập nhật 2026-10-27 — đã xác minh bằng cách đọc code zaic_tools thật
(trong gói dữ liệu v3.2.0, KHÔNG phải bằng evaluator, vì gói không kèm
evaluator):**
- **Q-L2 — GIẢI QUYẾT MỘT PHẦN:** `Session.call` ghi MỌI call vào
  `calls`, kể cả call bị từ chối schema (`ok: false`), và
  `get_tool_calls()` trả đúng danh sách đó làm `tool_calls` của dòng
  nộp. Vậy submission PHẢI chứa toàn bộ call đã thực thi. Phần còn mở:
  failed call có ảnh hưởng tới F1 không (evaluator không có trong gói).
- **Q-L4 — GIẢI QUYẾT:** `validate()` chỉ kiểm schema, KHÔNG ghi log,
  KHÔNG đổi state. Validator chặn TRƯỚC khi gọi là an toàn và không vi
  phạm log — vì call đó chưa bao giờ được thực thi. Lọc call SAU khi
  đã thực thi vẫn là rủi ro (call đã nằm trong log).
- **Q-L1, Q-L3, Q-L5 — VẪN MỞ:** cách chấm ask, read có tính F1 không,
  và submission khi hết vòng lặp — không có gì trong gói dữ liệu trả
  lời; scorer trong `lifemate/scoring.py` ghi rõ các giả định này và
  không trình bày kết quả của nó như điểm chính thức.

**DataMate:**
- **Q-D1:** Câu hỏi không có trong submission.jsonl được tính như abstain
  (0 điểm), như sai (−1), hay bị loại khỏi mẫu chấm?
- **Q-D2:** Nếu model trả `unanswerable` cho câu hỏi có đáp án, và trả giá trị
  cho câu hỏi unanswerable, mỗi trường hợp được tính bao nhiêu điểm?
- **Q-D3:** Sai type có được tính là sai hoàn toàn không? Với list, thứ tự có
  bắt buộc không? Với table, tên cột sai nhưng giá trị đúng có được điểm không?
- **Q-D4:** Percent được chấm theo thang 0–100 hay 0–1? Làm tròn tới bao nhiêu
  chữ số thập phân, và sai làm tròn có tính là sai hoàn toàn không?
- **Q-D5:** Tổng tham số được tính theo total hay active (với MoE)? Với
  checkpoint fine-tune từ một base trước mốc, ngày nào được dùng để xét mốc
  01/10/2026 (DataMate) / 26/10/2026 (LifeMate): ngày base hay ngày checkpoint
  phái sinh? Teacher dùng để sinh dữ liệu tổng hợp (không phải lúc inference)
  có bị tính vào mốc không?
- **Q-D6:** Tie-break chính xác là gì, và ngưỡng reproducibility 0,03 được áp
  dụng như thế nào (loại trực tiếp hay chỉ cảnh báo)?

**Giả định an toàn hiện tại (không phải luật, cho tới khi có đáp án):**
total (bao gồm embedding, mọi model phụ, toàn bộ MoE); checkpoint fine-tune
chưa rõ — giả định an toàn nhất là ngày checkpoint phái sinh phải trước mốc,
hoặc chỉ dùng model gốc chưa fine-tune; luôn nộp đủ mọi câu hỏi (kể cả abstain
tường minh) thay vì bỏ trống; giữ nguyên trace đã thực thi, không xóa failed
call để 'đẹp' trace.

## 4. Fine-tune checkpoint và mốc thời gian — chưa rõ cách ban tổ chức hiểu

- Checkpoint phái sinh từ fine-tune (trên train ZAIC hoặc trên dữ liệu tổng hợp)
  có được tính là "model công bố trước 01/10/2026" (DataMate) / "trước 26/10/2026"
  (LifeMate) hay không — **chưa xác minh**.
- **Hành động:** hỏi ban tổ chức trước khi đầu tư nhiều vào fine-tune, hoặc chuẩn
  bị phương án dự phòng bằng model gốc chưa fine-tune.
- Teacher dùng để sinh dữ liệu tổng hợp phải ghi rõ (tên, ngày phát hành) để tránh
  tranh cãi về nguồn gốc dữ liệu, kể cả khi teacher chỉ dùng lúc tạo dữ liệu
  offline, không phải lúc inference.

## 5. Checkpoint, licence và ngày phát hành — chưa xác minh trên Hugging Face

- PhoWhisper từng size (tiny/base/small/medium/large) — HF repo/licence/ngày
  từng checkpoint chưa xác minh; paper ICLR 2024 Tiny Papers và WER VIVOS đã
  đối chiếu Table 2 (xem sources B2).
- Qwen3-4B-Instruct-2507 — ĐÃ XÁC MINH MỘT PHẦN: HF commit `cdbee75`,
  Apache 2.0, 4,0B tổng / 3,6B non-embedding, series tháng 7/2025.
  (KDnuggets 06/08/2025 là ngày bài báo, không phải ngày phát hành.)
- Qwen2.5-Coder-7B-Instruct — ĐÃ XÁC MINH MỘT PHẦN: 7,61B tổng / 6,53B
  non-embedding, 28 layer, context 131.072, paper arXiv 2409.12186, Apache 2.0,
  blog chính thức 19/09/2024; ngày commit đầu tiên trên HF chưa trích được.
  Qwen3-8B (8,19B) và Qwen3-14B (~14,8B) vẫn là Secondary — chưa mở card gốc.
  Qwen2.5-Coder-14B 14,7B + PhoBERT-base 0,135B = 14,835B (dư 0,165B).
- PhoBERT: base 135M MIT và large 370M MIT đã xác minh qua README chính thức;
  base-v2 AGPL v3 — không dùng trừ khi chấp nhận copyleft. Bắt buộc input đã
  tách từ (chi phí bộ tách từ chưa tính).
- xLAM-2-3b-fc-r: series đã xác minh từ Salesforce + APIGen-MT, nhưng
  checkpoint 3B cụ thể chưa xác minh licence/ngày/tên repo chính xác; rủi ro
  CC BY-NC (báo chí) — ngoài shortlist chính.
- Hammer checkpoints: Hammer v1 (paper + README_READ, Apache-2.0, commit
  `ff415d`); Hammer2.1-3b chưa xác minh licence/ngày/base trên card gốc
  (mirror báo CC-BY-NC-4.0 cho bản 0.5b) — ngoài shortlist chính.
- RSL-SQL repo (chưa mở/xác minh license).
- ToolSandbox (license hiển thị NOASSERTION — đọc file LICENSE thực tế trước khi
  copy code).
- **Hành động:** đọc model card + `config.json` của checkpoint sẽ dùng, cộng tổng
  tham số thực (bao gồm embedding nếu không tie, cộng mọi model phụ), ghi lại
  commit/ngày/license trước khi đưa vào Docker.

## 6. Giải thưởng theo từng track — suy luận, chưa xác nhận

- Việc nhất 3.500 USD / nhì 2.500 USD là **theo từng track** chỉ là suy luận từ
  (3.500 + 2.500) × 2 = 12.000 USD tổng giải — chưa xác nhận trực tiếp trong thể lệ.
- **Hành động:** đối chiếu PDF thể lệ EN/VI trước khi dùng con số này làm căn cứ.

## 7. ZAIC 2025 — không tìm thấy repo/write-up chiến thắng

- Đội thắng CtelAI (RoadBuddy) và AIO_C3A (AeroEyes) năm 2025: không tìm thấy
  repo/write-up chính thức trong các tìm kiếm đã làm. Bài toán 2025 cũng không
  liên quan trực tiếp đến LifeMate/DataMate 2026 — chỉ ghi nhận để tránh tìm lại.

## 8. ZAIC 2025 và các vấn đề riêng không ảnh hưởng kỹ thuật thi đấu

- Định nghĩa và nơi hiển thị ZAIC_ID sau đăng nhập: chưa xác minh công khai (vấn
  đề của form đăng ký đội, không ảnh hưởng đến kỹ thuật thi đấu).

## 9. Số liệu benchmark — mâu thuẫn giữa các nguồn thứ cấp

- BFCL: các nguồn thứ cấp nói về phiên bản/tập model khác nhau — không chọn một
  con làm "đầu bảng BFCL". Mọi số BFCL phải ghi version + mode + ngày, thiếu
  một trong ba thì không trích số. TinyLLM 65,74%/62,04% không rõ version —
  không dùng để xếp hạng; xLAM-2-3b BFCL v4 83,7% là first-party của trang đo,
  không phải leaderboard chính thức.
- BIRD/Spider 2.0: số EX theo bản tổng hợp khác nhau, khác thời điểm/backbone/tập
  đánh giá — không so sánh trực tiếp. BIRD top leaderboard ~82–83% (thứ cấp,
  09–10/2026, thay đổi theo thời gian), human 92,96%.
- Spider 2.0: **đã sửa round 2** — nguồn chính thức arXiv 2411.07763: o1-preview
  code agent 21,3% full (cùng paper: 91,2% Spider 1.0, 73,0% BIRD). Con số 17,1%
  đã bỏ (không rõ setting). Mọi số Spider 2.0 phải ghi setting + backbone.
- DABstep: **đã sửa round 2** — nguồn chính thức arXiv 2506.23719: agent tốt
  nhất thời điểm paper đạt 14,55% Hard (author-reported). Các số thứ cấp
  '77,78%/9,26%' và 'Cascade 92,22%' đã bỏ (không đối chiếu được bảng gốc;
  Cascade là vendor tự báo cáo, chưa validated).
- PExA (Spider 2.0): tin chưa xác minh từ arXiv/ACL — không dùng làm kết luận.
- ReAct: ALFWorld 71% vs 79% (khi kết hợp CoT-SC) giữa các tóm tắt — đối chiếu bảng
  gốc trước khi trích.
- **Quy tắc chung:** mọi số benchmark trong tài liệu này chỉ dùng để chọn cơ chế,
  không dùng làm mục tiêu số học cho ZAIC.

## 10. Thực nghiệm trên ZAIC — chưa có

- **Chưa có thực nghiệm nào chạy trên dữ liệu ZAIC 2026** trong bộ tài liệu này:
  chưa đo WER thực thể trên audio ZAIC, chưa đo ngưỡng abstain tối ưu, chưa đo
  latency trên A30 / thời gian trên 2× RTX 5090, chưa đo PA/state đúng của bất kỳ
  baseline nào.
- Mọi phương pháp trong tài liệu này là giả thuyết chuyển giao cho tới khi có kết
  quả trên **train held-out tách theo business** (và, với DataMate, trên business
  mới leave-one-business-out). Public test không có đáp án kèm theo theo ghi nhận
  2026-10-26 nên không tự tính PA/điểm chính thức trên public test tại chỗ —
  public test chỉ đo format/latency và nộp sanity qua kênh chính thức; nếu zip
  thật có đáp án thì giao thức này phải viết lại.
- Các ngưỡng đề xuất (abstain khởi đầu 0,5; WER thực thể tốt hơn ≥ 2 điểm để đổi
  bản ASR; false-positive call giảm ≥ 20%; PA tăng ≥ 0,03 để giữ hiệu chuẩn; PA
  giảm > 0,15 khi giấu loại hình để ưu tiên exploration) đều là **tiêu chí đề xuất
  trong kế hoạch thử nghiệm**, không phải con số của ban tổ chức, không phải kết
  luận thực nghiệm, và không phải điều kiện cứng — mọi quyết định giữ/bỏ phải
  báo kèm số câu hỏi từng nhóm, không chốt từ một con số lẻ.

## 11. Phạm vi tìm kiếm — không tuyên bố đã tìm hết

- Nghiên cứu đã tìm rộng nhưng không tuyên bố đã tìm hết Internet. Các hướng chưa
  đào sâu đủ: winning solutions thực sự cho tabular QA trên Kaggle/AIcrowd/Codabench
  kèm code và license (search round 2 không trả về ứng viên đủ gần — các kết quả
  là Titanic/feature engineering chung, PARC/AutoKaggle cho ML competition, không
  phải tabular QA có type exact + rulebook); chuẩn hóa Excel bẩn ở mức file/commit
  (merged cells, header lệch) ngoài mô tả; các benchmark data-analysis agent mới
  nhất sau 2026-10-27; HF card trực tiếp của xLAM-2-3b-fc-r, Hammer2.1-3b,
  Qwen3-8B/14B (config.json); LICENSE thực tế của ToolSandbox và RSL-SQL; toàn văn
  ReAct (bảng ALFWorld 71% vs 79% vẫn mâu thuẫn, chưa đối chiếu bảng gốc).
- Các nguồn trong [sources.md](sources.md) có URL thiếu được liệt kê riêng ở cuối
  file đó — không bịa URL cho chúng.
