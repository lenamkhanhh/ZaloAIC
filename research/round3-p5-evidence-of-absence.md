# Ưu tiên 5 — Chứng minh thiếu dữ liệu khác với pipeline chưa tìm ra

> Bản nháp nghiên cứu, không phải tài liệu repo. Mốc so sánh: commit repo
> `8d4721e`. Không chỉnh sửa repo trong đợt này.
> Quy ước nhãn: **ĐÃ XÁC MINH** = đọc được từ nguồn ghi rõ; **CHƯA XÁC MINH**
> = chưa có bằng chứng, không được coi là luật chính thức.

## 1. Repo đã biết gì, và khoảng trống chính xác ở đâu

### 1.1. Những gì repo đã có (đúng, giữ lại)

- DataMate có ba đầu ra phân biệt: đáp án có type, `unanswerable` (dữ liệu
  không chứa thứ cần thiết), `abstain` (agent chủ động không trả lời)
  — `competition/datamate.md`, theo portal sau đăng nhập ngày 2026-10-26.
- Penalized Accuracy: đúng +1, abstain 0, sai −1, không điểm từng phần.
- `deep-dives/04` §5 tách hai quyết định: `unanswerable` là kết luận xác
  định (schema/rulebook), `abstain` là quyết định xác suất (độ tin cậy).
  Code kèm theo giữ `Decision` tách khỏi mã hóa submission — đúng, vì
  cách evaluator xử lý `unanswerable` vẫn **CHƯA XÁC MINH** (gaps.md Q-D2).
- Hai guard đã đúng hướng: (a) schema shortlist rỗng thì fallback một lần
  sang full schema trước khi kết luận thiếu; (b) lỗi/timeout thực thi thì
  abstain, không bao giờ suy ra unanswerable.
- Train có `answers.jsonl` và "câu unanswerable có answer null" — theo ghi
  nhận 2026-10-26, **CHƯA XÁC MINH** cho tới khi giải nén zip thật
  (repo tự ghi rõ bước này là bắt buộc).

### 1.2. Khoảng trống chính xác (vấn đề của đợt này)

Cây quyết định §5.2 của `deep-dives/04` kết luận `unanswerable` ở **bước 1,
trước khi sinh code**, chỉ từ "bảng/cột cần thiết vắng mặt, rule cần thiết
không có, hoặc câu hỏi ngoài phạm vi phủ". Ba lỗ hổng:

1. **"Cần thiết" do ai định nghĩa?** Nếu cột "cần thiết" là do planner tự
   chọn (ví dụ planner muốn cột `total_amount` trong khi doanh thu tính
   được từ bảng dòng), thì "thiếu cột" chỉ là planner thiếu, không phải
   dữ liệu thiếu. Repo chưa có quy tắc nào cấm việc này.
2. **Một lần linking lỗi = kết luận thiếu.** Fallback một lần sang full
   schema vẫn chưa kiểm tra: alias trong README, cột suy ra được (tính
   toán/join/lịch), đường join khác, hay rulebook định nghĩa lại khái
   niệm. Một lần linking thất bại không chứng minh không tồn tại.
3. **Query rỗng bị đọc thành "không có dữ liệu".** Repo §2.3 đã cảnh báo
   output rỗng "có thể là filter sai, join sai, hoặc dữ liệu trống thật",
   nhưng cây §5.2 vẫn để nhánh "hết vòng sửa mà vẫn rỗng → abstain" và
   nhánh schema-check → unanswerable chạy trước, nên một câu mà đáp án
   đúng là `0` hoặc `[]` vẫn có thể bị đẩy sang abstain/unanswerable
   mà không qua kiểm chứng phân biệt nào.

Hệ quả về điểm số (suy luận từ công thức PA, không phải tuyên bố của
evaluator): nếu trả `unanswerable` cho câu có đáp án cũng bị tính sai
(−1, theo Q-D2 đang chờ xác minh), thì `unanswerable` sai tốn đúng bằng
một đáp án sai, trong khi abstain tốn 0. Vì vậy **khi không chắc, abstain
luôn rẻ hơn unanswerable** — và ngưỡng để dám nói `unanswerable` phải
cao tương đương ngưỡng để dám trả lời (xem §4.5). Cây hiện tại, bằng
cách ưu tiên `unanswerable` ở bước 1, đang làm ngược lại: quyết định đắt
nhất lại được đưa ra với bằng chứng ít nhất.

## 2. Nguồn đã đọc thực sự

Mức đọc được ghi thẳng thắn: READ = đọc văn bản nguồn; SNIPPET = chỉ đọc
kết quả tìm kiếm/tóm tắt, không đủ để trích chi tiết.

| # | Nguồn | Đã đọc | Dùng cho |
|---|---|---|---|
| S1 | ABISS: Evaluating Text-to-SQL Systems Through Agent Interaction, arXiv HTML, §1–§4 (định nghĩa, taxonomy §3.2, pipeline validation §4.2) — https://arxiv.org/html/2607.23340 | READ (§1–§4, dòng 0–419 của bản HTML) | Định nghĩa hình thức của unanswerable/ambiguous; taxonomy; cách validation chứng minh một câu "thật sự" không giải được |
| S2 | ZAIC DataMate portal, trang public — https://challenge.zalo.ai/portal/datamate (truy cập đợt này; trang chỉ trả phần giới thiệu + input/output + 1 ví dụ, không có mục Evaluation) | READ (toàn bộ 37 dòng trả về) | Xác nhận lại: output gồm value, `unanswerable` khi "data cannot support the question", hoặc abstain khi agent chọn không trả lời. **Không** lấy được cách chấm chi tiết từ trang public này |
| S3 | Repo ZAIC tại `8d4721e`: `competition/datamate.md`, `competition/metrics-submission.md`, `deep-dives/04-confidence-abstain-datamate.md` §2.3/§5, `gaps.md` (Q-D1–Q-D6) | READ | Mốc so sánh; các câu hỏi evaluator còn mở |
| S4 | TriageSQL (Zhang et al. 2020), arXiv:2010.12634 — phân loại improper / external-knowledge / ambiguous / non-SQL / answerable | SNIPPET (kết quả tìm kiếm, bảng loại câu hỏi) | Gốc của phân loại "không trả lời được" trong text-to-SQL; chỉ dùng ở mức taxonomy, không trích số liệu |
| S5 | TrustSQL (Lee et al. 2024), arXiv:2403.15879 — reliability score +1/0/−c, pipeline 3 bước (infeasible detection → generation → error detection) và unified approach (entropy/MaxProb/Mahalanobis) | SNIPPET | Khung "abstain có giá" và hai vị trí đặt cổng abstain (trước sinh query / sau sinh query); **không** chuyển số RS của TrustSQL sang PA của ZAIC |
| S6 | SCARE (EHR QA, arXiv:2511.17559) — unanswerable gồm small-talk, out-of-scope, missing-column | SNIPPET | Xác nhận missing-column là một loại unanswerable được công nhận, nhưng chỉ khi cột thật sự không tồn tại |
| S7 | SQuAD 2.0 (Rajpurkar et al. 2018) qua tổng quan thứ cấp — 50.000+ câu unanswerable viết đối kháng để trông như trả lời được | SNIPPET (nguồn thứ cấp, không đọc paper gốc đợt này) | Bằng chứng ngược: giống-trả-lời-được ≠ trả-lời-được; cần classifier/kiểm chứng riêng, không suy từ "sinh không ra đáp án" |
| S8 | Selective QA: "Selectively Answering Ambiguous Questions" (EMNLP 2023) và luận án Kamath — abstain theo ngưỡng trên score, và tách bất định về denotation (cách hiểu) khỏi bất định về đáp án | SNIPPET | Cơ sở cho việc xử lý mơ hồ: liệt kê các cách hiểu, không chọn cách phổ biến nhất |
| S9 | Ngữ nghĩa SQL chuẩn về tập rỗng (COUNT(*) luôn trả 1 dòng = 0 khi không khớp; SUM/AVG/MIN/MAX trên tập rỗng trả NULL) | READ (tài liệu SQL chuẩn, không phải một paper) | Phân biệt 0 / NULL / tập rỗng — nền tảng kỹ thuật cho mục (d) |

**Không đọc được đợt này (ghi rõ, không bịa):** evaluator/README/rulebook
thật của ZAIC (chỉ có ghi nhận portal sau đăng nhập ngày 2026-10-26 trong
repo); code baseline DABstep (thuộc Ưu tiên 3, không đào lại ở đây); bất
kỳ số liệu ZAIC nào (chưa giải nén dữ liệu).

## 3. Taxonomy: sáu loại, và cách phân biệt từng loại

Định nghĩa hình thức mượn từ ABISS (S1, §3, Definition 2–3), chuyển sang
ngữ cảnh DataMate (D = dữ liệu business + README, K = rulebook + calendar
+ as-of date, S = tập hợp các chương trình/SQL hợp lệ):

- **Unanswerable** ⟺ không tồn tại chương trình nào trong S trên (D, K)
  trả lời đúng câu hỏi: `f(q, D, K) = ∅`.
- **Ambiguous** ⟺ tồn tại ≥ 2 chương trình không tương đương cùng khớp
  câu hỏi: `|f(q, D, K)| ≥ 2`.

Hệ quả quan trọng nhất: **chứng minh unanswerable là chứng minh một phủ
định trên toàn bộ S** — một lần planner thất bại chỉ chứng minh "planner
này chưa tìm ra", không chứng minh `f = ∅`. Mọi kiểm chứng dưới đây đều
là xấp xỉ có kiểm soát của phủ định đó, và phải ghi rõ phần dư rủi ro.

### (a) Dữ liệu thực sự thiếu — kết luận `unanswerable` được phép

- **Định nghĩa.** Khái niệm hỏi tới không có trong D lẫn K, và không suy
  ra được từ bất kỳ dữ liệu nào khác. ABISS §3.2.4 chia hai dạng con:
  thiếu thực thể/thuộc tính (không có bảng/cột nào về "staff"), và thiếu
  quan hệ (có cả hai bảng nhưng không có liên kết nào biểu diễn quan hệ
  cần hỏi, ví dụ giáo viên–môn học mà không có bảng phân công).
- **Ví dụ DataMate.** Hỏi "doanh thu từ bán hàng online" trong khi business
  chỉ bán tại quầy và không có cột/kênh nào phân biệt online/offline;
  hỏi về một mặt hàng chưa từng xuất hiện trong bất kỳ bảng nào.
- **Kiểm chứng phân biệt (§4).** Full-schema scan + alias scan + derivation
  search + coverage probe đều âm tính. Đặc biệt: probe phải kiểm tra sự
  tồn tại của *khái niệm* (ví dụ `EXISTS` trên toàn bộ dữ liệu, không
  filter theo kỳ), không chỉ chạy query đầy đủ filter rồi thấy rỗng.
- **Bằng chứng ngược.** ABISS §4.2 Stage 3–4: ngay cả khi tạo câu hỏi
  "không giải được", pipeline của họ vẫn cần council vote để xác nhận câu
  hỏi thật sự khớp định nghĩa, vì nhiều câu "tưởng không giải được" thực
  ra giải được bằng join/phép tính không hiển nhiên. Nếu một benchmark
  chuyên về việc này còn cần vote, một planner đơn lẻ càng không đủ để
  kết luận một mình.

### (b) Dữ liệu có nhưng schema linking sai — KHÔNG phải unanswerable

- **Định nghĩa.** Cột/bảng tồn tại nhưng planner chọn sai (tên tương tự,
  alias, mã sản phẩm, cột tiếng Việt không dấu/dấu khác, sheet khác).
  Đây là lỗi của pipeline, không phải của dữ liệu.
- **Dấu hiệu nhận biết.** Câu hỏi nhắc tới một thực thể mà profiler thấy
  có mặt trong dữ liệu dưới tên khác; hoặc linking lần 2 (full schema,
  khác prompt, khác embedding) tìm ra cột mà lần 1 bỏ sót.
- **Kiểm chứng phân biệt.** Linking phải chạy ít nhất hai đường độc lập
  (shortlist + full-schema scan; hoặc lexical + embedding) và đối chiếu
  README/alias của business. Nếu đường thứ hai tìm ra → loại (b), quay
  lại trả lời. **Chính sách thay đổi:** repo hiện tại fallback "một lần"
  là chưa đủ tiêu chuẩn cho kết luận đắt đỏ như unanswerable; cần hai
  đường linking độc lập đều âm tính (xem §4, bước E2).
- **Bằng chứng ngược.** SQuAD 2.0 (S7): câu unanswerable được viết để
  trông giống câu trả lời được — tương tự, một cột "trông giống" không
  phải là cột đúng, và một cột đúng có thể "trông không giống" tên trong
  câu hỏi. Linking bằng tương tự bề mặt là nguồn lỗi hai chiều.

### (c) Thiếu cột trực tiếp nhưng suy ra được — KHÔNG phải unanswerable

- **Định nghĩa.** Không có cột nào chứa trực tiếp đáp án, nhưng đáp án
  tính được từ dữ liệu khác qua: phép tính (giá × số lượng, tổng dòng),
  join (bảng chi tiết → bảng tổng), tách ngày (từ ngày đầy đủ ra tháng/
  quý), join lịch (âm lịch qua `calendar.csv`), hoặc định nghĩa trong
  rulebook (ví dụ "bán chạy" = theo số lượng, không phải cột riêng).
- **Ví dụ DataMate (từ rulebook mặc định trong repo).** Không có cột
  "doanh thu" vẫn tính được doanh thu = tổng tiền dòng sau chiết khấu
  dòng, loại đơn hủy và đơn có bất kỳ mặt hàng nào bị trả lại. Không có
  cột "tháng âm lịch" vẫn join được qua `calendar.csv`. Đây là dạng mà
  planner hay báo thiếu oan nhất, vì planner thường tìm cột đích thay vì
  tìm *đường suy ra*.
- **Kiểm chứng phân biệt.** Derivation search có checklist riêng (§4,
  bước E3): alias → công thức từ rulebook → join path (FK hoặc value
  join qua mã/tên) → aggregate trên bảng chi tiết → calendar join →
  date-part. Chỉ khi tất cả đều âm tính mới được xét sang (a).
- **Bằng chứng ngược.** BIRD cung cấp "external knowledge evidence" cho
  mỗi câu hỏi (mapping thuật ngữ → cột, công thức, diễn giải boolean);
  hiệu năng tăng mạnh khi có evidence (S5-snippet từ các nguồn thứ cấp
  về BIRD — **con số cụ thể không trích ở đây vì chỉ đọc snippet**).
  Bài học chuyển được: trong DataMate, rulebook + README đóng vai trò
  evidence đó; bỏ qua rulebook mà kết luận thiếu là bỏ qua đúng nguồn
  được thiết kế để lấp khoảng trống.

### (d) Không có giao dịch — đáp án đúng có thể là 0 hoặc danh sách rỗng

- **Định nghĩa.** Phạm vi (thực thể + kỳ + điều kiện) tồn tại trong dữ
  liệu, nhưng không có dòng nào thỏa điều kiện. Đây là một *giá trị*,
  không phải sự vắng mặt của dữ liệu.
- **Phân biệt kỹ thuật (S9, bắt buộc nhớ):**
  - Hỏi "có bao nhiêu" (COUNT) → `COUNT(*)` trên tập rỗng luôn trả **0**,
    một dòng, một số. Trả 0 là trả lời, không phải abstain.
  - Hỏi "tổng là bao nhiêu" (SUM) trên tập rỗng → **NULL**, không phải 0.
    Chuyển NULL thành 0 một cách tự động là bịa đáp án; chuyển NULL
    thành unanswerable cũng sai — đúng ra phải kiểm tra: câu hỏi có
    ngầm định "không bán = 0 đồng" theo rulebook không? Nếu rulebook
    không nói, và không có dòng nào, thì đây là trường hợp phải abstain
    (không đủ căn cứ chọn giữa 0 và "không xác định"), không phải
    unanswerable.
  - Hỏi dạng list ("liệt kê các đơn...") → `[]` là đáp án hợp lệ **khi**
    đã chứng minh được thực thể tồn tại và kỳ nằm trong phạm vi dữ liệu
    (xem probe ở §4, bước E6). Nếu chưa chứng minh được hai điều đó,
    `[]` có thể chỉ là filter sai — lúc đó abstain, không phải trả `[]`.
- **Bằng chứng ngược (quan trọng).** ABISS §4.2 Stage 2 yêu cầu SQL
  ground truth phải trả về tập **không rỗng** thì câu hỏi mới được giữ
  lại trong benchmark của họ. Quy tắc đó hợp lý cho việc *xây benchmark*,
  nhưng **không chuyển được sang DataMate**: nó sẽ loại đúng những câu
  mà đáp án là 0/`[]`. Đừng nhập quy tắc này vào pipeline ZAIC.
- **Chính sách thay đổi.** Tách ba nhánh rỗng: COUNT → trả 0; SUM/AVG
  trên tập rỗng → abstain trừ khi rulebook định nghĩa 0; list rỗng →
  chỉ trả `[]` khi coverage probe dương tính, còn không thì abstain.
  Hiện tại `deep-dives/04` §2.3 gộp chung "đồng thuận trên output rỗng →
  abstain", làm mất điểm các câu COUNT = 0.

### (e) Query lỗi hoặc timeout — luôn là abstain, không bao giờ là bằng chứng

- **Định nghĩa.** Lỗi cú pháp, cột không tồn tại trong query đã sinh
  (lỗi của *query*, khác với cột không tồn tại trong *dữ liệu*), join
  sai kiểu gây nổ tổ hợp, timeout trên bảng lớn.
- **Nguyên tắc.** Lỗi thực thi nói về chương trình, không nói về dữ liệu.
  Repo đã đúng ở điểm này (§5.2 bước 2). Bổ sung: trước khi abstain,
  thử một query probe tối giản (ví dụ `SELECT COUNT(*) FROM <bảng>`,
  hoặc bỏ bớt một filter) để tách "bảng/cột thật sự không có" khỏi
  "query vừa rồi viết sai". Probe thành công mà query đầy đủ lỗi →
  chắc chắn là (e), không phải (a).
- **Timeout riêng.** Timeout trên 300.000 dòng không chứng minh dữ liệu
  thiếu; nó chứng minh query chưa tối ưu. Thử lại với aggregate trước
  khi join / giới hạn phạm vi theo kỳ trước khi abstain. (Chi phí thử
  lại phải tính vào ngân sách 6 giờ — xem Ưu tiên 4, không bàn sâu ở đây.)

### (f) Câu hỏi mơ hồ về nghiệp vụ — abstain, không phải unanswerable

- **Định nghĩa (ABISS Definition 2).** Tồn tại ≥ 2 chương trình không
  tương đương cùng khớp câu hỏi: hai cột cùng tên gọi ("email" cá nhân
  vs cơ quan, §3.2.2), hai cách hiểu phạm vi ("gần đây" không có ngưỡng,
  §3.2.3), hai định nghĩa xung đột trong rulebook (§3.2.7), hoặc thiếu
  thông tin chỉ người hỏi mới có (§3.2.6 — trong ZAIC không có vòng hỏi
  lại, nên dạng này cũng rơi về abstain).
- **Phân biệt với (a).** (a) là `f = ∅` (không có chương trình nào); (f)
  là `|f| ≥ 2` (quá nhiều chương trình). Nhầm hai loại này theo cả hai
  hướng đều tốn điểm: gọi (f) là unanswerable thì mất cơ hội abstain an
  toàn 0 điểm; đoán một trong hai cách hiểu thì rủi ro −1.
- **Kiểm chứng phân biệt.** Liệt kê các denotation (cách hiểu) dưới dạng
  các query ứng viên khác nhau; nếu rulebook phân giải được về một (ví
  dụ rulebook định nghĩa "tháng này" = tháng chứa as-of) → trả lời theo
  rulebook; nếu không phân giải được → abstain và log cả hai cách hiểu.
  Đây chính là phần "tách P(cách hiểu) bằng rulebook" mà repo §2.4 đã
  nhắc, nhưng chưa thành thủ tục bắt buộc.
- **Bằng chứng ngược cho việc "chọn cách phổ biến nhất".** Nghiên cứu
  selective QA (S8) cho thấy xác suất đáp án của model không phát hiện
  được bất định về denotation: model có thể rất tự tin vào một đáp án
  trong khi câu hỏi vốn có hai đáp án đều đúng theo hai cách hiểu.
  Vì vậy đồng thuận cao (k=3 cùng chọn một cách hiểu) **không** chứng
  minh câu hỏi không mơ hồ — cả ba candidate chia sẻ cùng một cách hiểu
  mặc định. (Liên hệ Ưu tiên 4: consensus cùng sai.)

### Bảng tóm tắt quyết định

| Loại | Bản chất | Quyết định đúng | Lỗi hay gặp nếu xử lý vội |
|---|---|---|---|
| (a) Thiếu thật | `f = ∅`, đã kiểm chứng | `unanswerable` | — |
| (b) Linking sai | Cột có, planner không thấy | Trả lời (sau linking lại) | Báo thiếu oan → mất +1, có thể −1 |
| (c) Suy ra được | Không có cột đích, có đường suy ra | Trả lời theo đường suy ra | Báo thiếu oan |
| (d) Không giao dịch | Phạm vi có, dòng = 0 | COUNT → 0; list → `[]` nếu probe dương; SUM rỗng → abstain trừ khi rulebook định 0 | Abstain oan (mất +1) hoặc bịa 0 từ NULL |
| (e) Lỗi/timeout | Chương trình sai/chậm | Abstain (sau probe tối giản) | Suy thành thiếu dữ liệu |
| (f) Mơ hồ | `|f| ≥ 2`, rulebook không phân giải | Abstain, log cả hai cách hiểu | Đoán một cách hiểu → rủi ro −1 |

## 4. Chuẩn "bằng chứng thiếu dữ liệu" (evidence-of-absence checklist)

### 4.1. Nguyên tắc cấm

**Không bao giờ coi một yêu cầu do planner tự đặt ra là điều kiện bắt
buộc của bài toán.** Mỗi mục "cần thiết" trong schema check phải kèm
nguồn gốc: token nào trong câu hỏi, hoặc điều khoản nào trong rulebook,
đòi hỏi nó. Nếu nguồn gốc duy nhất là "kế hoạch của tôi cần cột này",
xóa mục đó khỏi danh sách required và chạy lại derivation search. Ghi
nguồn gốc này vào log của mỗi quyết định `unanswerable` — một quyết định
không truy vết được nguồn gốc thì không được phát hành.

### 4.2. Checklist theo thứ tự (dừng ngay khi một bước cho kết quả dương)

Giả định: profiler đã chạy xong trên toàn bộ dữ liệu của business (bảng,
cột, kiểu, min/max ngày, số dòng, mẫu giá trị, alias từ README).

- **E0 — Phân tích câu hỏi, tách yêu cầu.** Liệt kê: thực thể hỏi, kỳ
  thời gian (đã resolve qua as-of + calendar), điều kiện lọc, loại đáp
  án. Mỗi yêu cầu gắn nguồn (token câu hỏi / điều khoản rulebook).
  *Nếu không tách được (câu hỏi không hiểu nổi) → abstain, không phải
  unanswerable.*
- **E1 — Coverage probe cho thực thể và kỳ.** `EXISTS`/COUNT không filter
  theo điều kiện chi tiết: thực thể (sản phẩm/khách hàng/…) có xuất hiện
  trong dữ liệu không? Kỳ hỏi có nằm trong [min_date, max_date] của bảng
  fact không? Probe âm tính ở đây là bằng chứng mạnh nhất cho (a);
  probe dương tính mà query đầy đủ rỗng → chuyển sang (d)/(b)/(e).
- **E2 — Linking hai đường độc lập.** Shortlist (prompt/embedding) và
  full-schema scan (lexical + duyệt toàn bộ tên bảng/cột/README) đều
  phải âm tính. Một đường âm tính + một đường dương tính = (b), trả lời.
- **E3 — Derivation search.** Theo thứ tự: alias (README + trường `alias`
  trong train — **CHƯA XÁC MINH** alias có mặt ở private hay không) →
  công thức rulebook → join path (FK, rồi value join qua mã/tên) →
  aggregate trên bảng chi tiết → tách ngày / join `calendar.csv`.
  Tìm được đường nào → (c), trả lời theo đường đó, ghi đường đó vào log.
- **E4 — Kiểm tra quan hệ, không chỉ thực thể.** Cả hai bảng đều có
  nhưng không có join key và không có value join → (a) dạng thiếu quan
  hệ. Chỉ kiểm tra "có bảng" mà không kiểm tra "có nối được không" là
  chưa đủ cho kết luận thiếu.
- **E5 — Kiểm tra rule, không chỉ dữ liệu.** Khái niệm hỏi tới có được
  rulebook định nghĩa không? Nếu rulebook của split không định nghĩa và
  không có dữ liệu nào cho phép suy ra → (a) dạng thiếu rule. Nếu
  rulebook định nghĩa nhưng planner không đọc → lỗi pipeline, quay lại.
- **E6 — Phân loại rỗng.** Query đầy đủ chạy được nhưng rỗng: chạy
  COUNT(*) không filter chi tiết + COUNT(*) có filter từng lớp (bóc
  từng điều kiện một) để xác định lớp filter nào làm rỗng. COUNT = 0
  với filter đầy đủ nhưng probe E1 dương → (d). SUM = NULL → xem §3(d).
  List rỗng + E1 dương → trả `[]`; E1 âm → đã là (a) từ E1, không cần
  tới đây.
- **E7 — Liệt kê denotation.** Viết ra ≥ 1 cách hiểu khác có thể (cột
  khác, phạm vi khác, định nghĩa khác). Nếu có ≥ 2 cách hiểu không
  tương đương và rulebook không phân giải → (f), abstain. Nếu chỉ có
  đúng một cách hiểu và các bước trên đều âm → (a).
- **E8 — Ngưỡng xác suất cho `unanswerable`.** Chỉ phát hành
  `unanswerable` khi checklist E0–E7 đều âm tính **và** tỉ lệ báo thiếu
  oan đo được trên train_cal (số câu trả lời được nhưng checklist kết
  luận thiếu / tổng số câu checklist kết luận thiếu) đủ thấp để
  P(thật sự unanswerable | checklist âm) > 0,5 — ngưỡng hòa vốn của PA
  (xem §1.2). Nếu không đo được tỉ lệ này, mặc định **abstain** thay vì
  `unanswerable`, vì abstain không bao giờ tốn −1 trong khi
  `unanswerable` sai thì có thể tốn −1 (Q-D2, **CHƯA XÁC MINH** — nếu
  evaluator xác nhận trả `unanswerable` sai chỉ tốn 0 thì ngưỡng này
  được nới lỏng, xem §6).

### 4.3. Quyết định nào thay đổi so với `8d4721e`

1. **Thứ tự đảo ngược một phần.** `unanswerable` không còn là lá đầu
   tiên của cây §5.2. Nó chỉ được kết luận sau khi đã chạy E0–E8, tức
   là sau ít nhất một lần sinh + thực thi query probe (không phải đoán
   đáp án, mà là probe kiểm chứng). Schema check "trước khi sinh code"
   chỉ được giữ vai trò *sàng lọc nhanh*: nếu nó báo thiếu, pipeline
   vẫn phải chạy E1–E3 trước khi phát hành `unanswerable`.
2. **Abstain trở thành mặc định khi không chắc.** Mọi trường hợp checklist
   chưa hoàn tất (timeout ở một bước, profiler chưa chạy xong, linking
   đường thứ hai chưa chạy) đều rơi về abstain, không phải unanswerable.
3. **COUNT = 0 được cứu.** Nhánh "output rỗng → abstain" trong §2.3 thu
   hẹp lại: chỉ áp dụng cho list rỗng chưa có probe và SUM/AVG NULL;
   COUNT = 0 trả lời thẳng.
4. **Mơ hồ có thủ tục riêng.** Thay vì "rulebook không phân giải được
   thì abstain" nói chung, bắt buộc liệt kê các denotation ứng viên và
   log chúng — để trên train_holdout đo được tỉ lệ mơ hồ thật so với
   tỉ lệ model tự cho là mơ hồ.
5. **Log bắt buộc cho mỗi `unanswerable`.** Nguồn gốc của từng required
   item (E0), kết quả từng bước E1–E7, và tỉ lệ báo thiếu oan trên
   train_cal. Không có log này thì quyết định đó không đạt chuẩn, dù
   đáp án cuối có đúng hay không (vì không kiểm chứng được trên
   private).

### 4.4. Những gì checklist KHÔNG chứng minh được

- Checklist là xấp xỉ của `f = ∅`, không phải chứng minh hình thức:
  luôn còn khả năng một đường suy ra kỳ lạ (ví dụ mã ẩn trong ghi chú
  tự do) mà checklist bỏ sót. Phần dư này chính là tỉ lệ báo thiếu oan
  đo được trên train — phải báo cáo nó, không được tuyên bố "đã chứng
  minh tuyệt đối".
- Checklist không giải quyết được trường hợp gold của ZAIC tự nó định
  nghĩa "unanswerable" khác với định nghĩa ở đây (ví dụ gold coi câu mơ
  hồ là unanswerable). Xem §6.

## 5. Phép thử nhỏ nhất trên dữ liệu train ZAIC (không cần GPU)

Điều kiện tiên quyết (repo đã ghi, nhắc lại): giải nén zip train thật,
liệt kê file, xác nhận `answers.jsonl` và ý nghĩa của answer null. Nếu
answer null **không** có nghĩa là unanswerable thì toàn bộ thí nghiệm
dưới đây phải thiết kế lại — đó là phép thử số 0.

1. **Ma trận nhầm lẫn của chính sách hiện tại.** Chạy cây §5.2 hiện tại
   trên train_holdout (chia theo business/type, theo giao thức repo):
   hàng = quyết định (answer/unanswerable/abstain), cột = gold (có đáp
   án/unanswerable). Số liệu cần nhất: **tỉ lệ báo thiếu oan** (gold có
   đáp án nhưng hệ thống nói unanswerable) và **tỉ lệ abstain oan trên
   câu COUNT = 0 / list rỗng**. Hai số này quyết định §4.3 có đáng làm
   hay không, trước mọi cải tiến khác.
2. **Ablation "bỏ lá unanswerable sớm".** Cùng train_holdout, chuyển mọi
   quyết định `unanswerable` từ bước 1 thành abstain (không đổi gì khác),
   đo PA thay đổi. Nếu PA tăng → cây hiện tại đang tốn điểm vì báo
   thiếu oan, và §4.2/E8 là bắt buộc. Nếu PA giảm → ngược lại, checklist
   hiện tại đã đủ tốt và chỉ cần bổ sung E3/E6.
3. **Gán nhãn thủ công 30–50 câu gold-unanswerable.** Mỗi câu gán một
   loại trong taxonomy §3 (a/b/c/d/e/f) bằng cách đọc dữ liệu business
   tương ứng. Kết quả cho biết phân bố thật của gold: nếu đa số là (a)
   thuần thì checklist E1–E2 là đủ; nếu nhiều (c)/(b) thì derivation
   search và linking hai đường là ưu tiên số một.
4. **Kiểm tra giả thuyết "gold coi mơ hồ là unanswerable".** Trong số
   câu gold-unanswerable, tìm những câu có ≥ 2 cách hiểu hợp lệ theo
   rulebook (làm bằng tay trên mẫu nhỏ). Nếu tỉ lệ này cao, chính sách
   "mơ hồ → abstain" (§3(f)) sẽ mất điểm +1 trên private và cần xem lại
   khi có evaluator thật — đây là điểm chưa quyết được từ dữ liệu train
   một mình.
5. **Probe rỗng có kiểm soát.** Trên các câu gold = 0 hoặc `[]` (nếu có
   trong train), chạy E6 (bóc filter từng lớp) và ghi lại: bao nhiêu câu
   hệ thống hiện tại đã trả đúng, bao nhiêu bị abstain oan, bao nhiêu
   bị unanswerable oan. Đây là phép thử rẻ nhất và trực tiếp nhất cho
   mục (d).

Tất cả các phép thử trên chỉ cần Python + DuckDB/SQLite trên dữ liệu
train đã giải nén; không cần model, không cần GPU, không cần training.

## 6. Những gì còn chưa đủ bằng chứng để chốt

1. **Cách evaluator tính điểm `unanswerable` sai (Q-D2) và mã hóa
   submission của nó.** Nếu trả `unanswerable` sai chỉ tốn 0 (như
   abstain) thì toàn bộ §4.2/E8 thay đổi: có thể nói `unanswerable`
   rộng rãi hơn mà không tốn điểm. Nếu tốn −1 thì checklist nghiêm
   ngặt ở §4 là bắt buộc. **Đây là câu hỏi có ảnh hưởng lớn nhất tới
   chính sách, và hiện chưa có đáp án.**
2. **Ý nghĩa thật của answer null trong train** (xem §5, phép thử số 0).
3. **Gold của ZAIC có coi câu mơ hồ là unanswerable hay không** (§5.4).
4. **Rulebook từng split có định nghĩa 0 cho SUM rỗng hay không**, và
   có định nghĩa nào khác với rulebook mặc định trong repo không.
5. **Private test có business type chưa từng xuất hiện ở train** (repo
   đã ghi): checklist E1–E3 dựa vào profiler + README; nếu README của
   business mới gần như trống (repo ghi "có nơi gần như không có gì"),
   linking hai đường và derivation search sẽ yếu đi — tỉ lệ báo thiếu
   oan trên private có thể cao hơn trên train_holdout, và ngưỡng E8
   phải đo lại theo leave-one-business-type-out, không chỉ holdout
   ngẫu nhiên.
6. **Số liệu từ các benchmark khác không chuyển trực tiếp sang ZAIC.**
   ABISS/TriageSQL/TrustSQL làm việc trên schema SQL tiếng Anh, có
   evidence riêng; DataMate là Excel/CSV/SQLite tiếng Việt đời thường,
   có rulebook và lịch âm. Taxonomy và thủ tục kiểm chứng chuyển được;
   ngưỡng, tỉ lệ lỗi và hiệu năng thì không.

## Kết luận cho parent agent (chỉ những điểm làm thay đổi chính sách)

1. **Đảo thứ tự:** `unanswerable` không được là lá đầu tiên của cây
   quyết định; nó chỉ phát hành được sau checklist E0–E8, trong đó có
   ít nhất một query probe đã thực thi. Schema check trước-code chỉ còn
   là sàng lọc, không phải kết luận.
2. **Abstain là mặc định khi không chắc**, vì dưới PA (+1/0/−1) và giả
   định Q-D2 (unanswerable sai = −1, **CHƯA XÁC MINH**), abstain không
   bao giờ tốn điểm còn unanswerable sai thì tốn. Mọi checklist dở
   dang đều rơi về abstain.
3. **Cứu các câu đáp án 0/`[]`:** COUNT = 0 trả thẳng; list rỗng chỉ trả
   `[]` khi coverage probe dương; SUM rỗng là NULL, không tự đổi thành
   0 và không tự đổi thành unanswerable.
4. **Cấm "required do planner tự đặt":** mỗi required item phải truy vết
   được tới token câu hỏi hoặc điều khoản rulebook, và phải qua
   derivation search (alias → công thức rulebook → join → aggregate →
   calendar) trước khi gọi là thiếu.
5. **Mơ hồ ≠ thiếu:** `|f| ≥ 2` mà rulebook không phân giải → abstain
   kèm log các cách hiểu; đồng thuận k=3 không chứng minh hết mơ hồ.
6. **Câu hỏi mở lớn nhất:** Q-D2 (điểm của `unanswerable` sai) quyết
   định ngưỡng E8; và phép thử số 0 (answer null trong train có thật
   là gold-unanswerable không) quyết định mọi thí nghiệm còn lại.
