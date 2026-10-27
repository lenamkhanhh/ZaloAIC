# Chuyên đề 4 — Đo độ tự tin & Cơ chế Abstain thực chiến cho DataMate

> Code đi kèm: [04-confidence-abstain-datamate.py](04-confidence-abstain-datamate.py)
> (659 dòng, stdlib thuần túy, không cần GPU/API/model; phần consensus
> và calibration kiểm thử được mà không cần checkpoint thật).
>
> Nhãn quan trọng, đọc trước khi dùng bất kỳ con số nào trong tài liệu
> này:
> - **ƯỚC LƯỢNG (ESTIMATE):** mọi con số thời gian trong §4 đều là tính
>   toán từ giả định, chưa đo trên máy chấm, chưa đo trên checkpoint
>   thật.
> - **SUY LUẬN (DERIVED):** ngưỡng hòa vốn p > 0,5 suy ra từ công thức
>   Penalized Accuracy, không phải tuyên bố của evaluator.
> - **CHƯA XÁC MINH (UNVERIFIED):** cách evaluator xử lý `unanswerable`,
>   câu thiếu trong submission, sai type, hòa thứ hạng, làm tròn — xem
>   §5.3, chưa được đọc từ evaluator/README thật.
> - **GIẢ THUYẾT CHUYỂN GIAO (HYPOTHESIS):** không phương pháp nào dưới
>   đây được khẳng định là hiệu quả trên ZAIC nếu chưa đo trên train
>   held-out của ZAIC.
> - **GIẢ ĐỊNH CỦA NGƯỜI DÙNG (USER ASSUMPTION):** "~600 câu hỏi" dùng
>   trong §4 là con số người dùng đưa ra để tính ngân sách, **không
>   phải** kích thước private test đã xác minh. Mọi kết quả ngân sách tỉ
>   lệ tuyến tính theo N — nếu N khác, tính lại theo công thức §4.1.

## 0. Tóm tắt cho người triển khai

1. **Trả lời chỉ khi kỳ vọng dương.** Với Penalized Accuracy (đúng +1,
   abstain 0, sai −1), một câu có xác suất đúng đã calibration là p thì
   kỳ vọng khi trả lời là `2p − 1`, kỳ vọng khi abstain là 0. Trả lời có
   lợi khi `p > 0,5`. Đây là toán học, không phải kinh nghiệm.
2. **Đồng thuận không phải là bằng chứng đủ.** 3/3 code cùng ra một đáp
   án vẫn có thể cùng sai một cách hiểu (fan trap, sai rulebook, sai
   cửa sổ ngày, cùng đọc nhầm schema). Vì vậy đồng thuận chỉ là **một**
   tín hiệu, phải đi kèm cổng kiểm tra độc lập: rule assertion, độ phủ
   bằng chứng, khoảng hợp lý, và (khi có thể) một đường tính thứ hai
   thật sự khác logic.
3. **Tách hai quyết định, hai bộ ngưỡng.** `unanswerable` là kết luận
   xác định: dữ liệu thiếu cột/bảng/rule cần thiết nên câu hỏi không
   thể trả lời từ dữ liệu. `abstain` là quyết định xác suất: dữ liệu đủ
   nhưng kết quả tính ra không qua cổng tin cậy. Hai quyết định này có
   code path khác nhau (§5, code kèm theo) và **không được gộp** thành
   một nút "không trả lời".
4. **Học ngưỡng ở đâu mới hợp lệ.** Mọi ngưỡng chỉ được học trên
   validation tách từ **train** (`train_cal`), khóa lại, rồi đo một lần
   trên `train_holdout` (ưu tiên tách theo business/loại hình). Public
   test — theo ghi nhận portal sau đăng nhập 2026-10-26 — không có
   `answers.jsonl` để tự chấm local, nên không được dùng để học hay
   chỉnh ngưỡng. Trước khi viết code đo, bước đầu tiên vẫn là giải nén
   gói dữ liệu thật và liệt kê file từng split; nếu public test thật sự
   có gold thì §3 phải viết lại theo bằng chứng file đó.
5. **Ngân sách thời gian: điểm hòa vốn là 24 giây/candidate.** Với mô
   hình nhân tuần tự (600 câu × 3 candidate ÷ 2 GPU, trần 6 giờ), một
   candidate trung bình quá 24 giây là vượt trần trước cả chi phí thực
   thi. Nhưng phép nhân tuần tự là **bi quan** khi dùng vLLM continuous
   batching — thời gian thật phải đo bằng tổng số token / throughput hệ
   thống (§4.3). Đừng chốt kiến trúc k=3 cho tới khi đo được latency
   sinh của checkpoint thật trên máy tương đương.

## 1. Bối cảnh và công thức quyết định

### 1.1. Bài toán DataMate, gói gọn

Hệ thống nhận câu hỏi tiếng Việt trên dữ liệu doanh nghiệp
(CSV/Excel/SQLite) kèm README, rulebook của đúng split, ngày as-of và
lịch âm–dương; trả ra một đáp án có type rõ ràng, hoặc `unanswerable`,
hoặc abstain. Điểm cuối dựa trên Docker rerun của ban tổ chức. Tổng tham
số inference ≤ 15B (kể cả model phụ), model công bố trước 01/10/2026,
chạy offline trong Docker, toàn bộ private test ≤ 6 giờ trên 2× RTX
5090 + 512GB RAM, private test có loại hình doanh nghiệp chưa xuất hiện
ở train. Xem [../competition/datamate.md](../competition/datamate.md),
[../plans/datamate.md](../plans/datamate.md).

### 1.2. Toán học của Penalized Accuracy

Với một câu hỏi, gọi p là xác suất đáp án đúng **sau khi đã
calibration** (không phải confidence miệng của LLM):

| Quyết định | Kỳ vọng điểm |
|---|---|
| Trả lời | `p×(+1) + (1−p)×(−1) = 2p − 1` |
| Abstain | `0` |

Trả lời có lợi khi `2p − 1 > 0`, tức `p > 0,5`. Hệ quả thực hành:

- Một hệ thống trả lời 100% câu với độ chính xác 55% được PA ≈
  `0,55 − 0,45 = 0,10`.
- Một hệ thống trả lời 60% câu với độ chính xác 80% trên số câu đã trả
  lời được PA = `0,6×0,8 − 0,6×0,2 = 0,36`.
- Ví dụ trên là minh họa số học, **không phải kết quả đo** của bất kỳ
  hệ thống nào.
- Ngưỡng 0,5 là điểm hòa vốn lý thuyết. Ngưỡng vận hành thực tế phải
  cao hơn hoặc thấp hơn tùy theo độ tin cậy của ước lượng p trên từng
  loại câu — đó chính là việc của §3. Ngưỡng học trên business train
  không tự đúng trên business mới (§3.5).

### 1.3. Vì sao "confidence của LLM" không dùng trực tiếp được

- LLM thường overconfident: confidence tự báo cáo không phải xác suất
  đúng thực. Phải calibration trên held-out trước khi so với 0,5.
- Confidence không nhạy với lượng bằng chứng: một câu có ít dòng dữ
  liệu sau filter, schema phủ không đầy đủ, hoặc rule không có trong
  rulebook vẫn có thể nhận confidence cao. Vì vậy tín hiệu abstain trong
  thiết kế này bao gồm cả **tín hiệu về bằng chứng** (độ phủ schema, số
  dòng sau filter, rule có trong rulebook không), không chỉ confidence.
- Đối với câu mơ hồ về ý nghĩa (ví dụ "bán chạy nhất" theo số lượng hay
  doanh thu), xác suất đúng phải tách thành P(đáp án | cách hiểu) ×
  P(cách hiểu | câu hỏi). Mơ hồ về ý nghĩa phải giải quyết bằng
  rulebook trước, không giải quyết bằng ngưỡng (theo hướng của Kamath
  và cộng sự về selective answering cho câu hỏi mơ hồ — xem Nguồn).

## 2. Self-Consistency Consensus: thiết kế

### 2.1. Định nghĩa đúng: so sánh output thực thi, không so sánh code

Self-consistency (Wang và cộng sự, ICLR 2023) là: lấy mẫu nhiều đường
suy luận độc lập từ cùng một model, rồi chọn đáp án nhất quán nhất bằng
cách marginalize qua các đường đó. Áp dụng cho DataMate, "đường suy
luận" là **một chương trình hoàn chỉnh (SQL hoặc Python)**, và "đáp án"
là **output sau khi thực thi chương trình đó**, không phải văn bản code:

- Hai code khác nhau về mặt văn bản nhưng cho cùng một output thì tính
  là đồng thuận.
- Hai code giống nhau về mặt văn bản nhưng chạy trên dữ liệu khác nhau
  thì không liên quan — ở đây cả ba chạy trên cùng một business, cùng
  một split.
- So sánh output phải dùng chuẩn hóa theo type (code kèm theo,
  `canonicalise_output`): số làm tròn về độ chính xác của đáp án khai
  báo, chuỗi NFC + lowercase + chuẩn hóa dấu câu theo quy ước của bài
  toán, list giữ thứ tự, table chuẩn hóa tên cột. **Lưu ý:** chuẩn hóa
  dùng để so sánh đồng thuận là heuristic của hệ thống; chuẩn hóa của
  evaluator có thể khác và vẫn CHƯA XÁC MINH (§5.3) — không được đồng
  nhất hai thứ này.

### 2.2. Pipeline k = 3

```
Câu hỏi + schema profile + rulebook trích theo câu hỏi
  → Sinh candidate 1, 2, 3 (temperature 0,2–0,5, seed khác nhau; ngoài ra decoding xác định)
  → Thực thi từng candidate trong sandbox chỉ đọc (timeout riêng)
  → Chuẩn hóa output của từng candidate
  → Đếm đồng thuận trên output đã chuẩn hóa (không đếm code)
  → Áp cổng kiểm tra độc lập (§2.4)
  → Quyết định: answer / abstain / unanswerable (§5)
```

Chi tiết vận hành:

- **Temperature 0,2–0,5, không phải 0,7–1,0.** Mục tiêu là đa dạng vừa
  đủ để phát hiện điểm không ổn định, không phải đa dạng tối đa.
  Temperature cao trên code sinh sẽ tăng tỉ lệ lỗi cú pháp và đáp án
  ngẫu nhiên, làm nhiễu tín hiệu đồng thuận. Nếu 3 candidate ở
  temperature 0,2 gần như giống hệt nhau, đó là tín hiệu cho thấy hệ
  thống thiếu đa dạng — giải pháp là đa dạng hóa bằng prompt (ví dụ: một
  candidate SQL, một candidate Python khi cả hai đường đều khả thi),
  không phải tăng temperature mù.
- **Seed khác nhau cho mỗi candidate, và ghi log seed.** Tính tái lập
  của Docker rerun (ngưỡng |PA(uploaded) − PA(rerun)| ≤ 0,03 theo ghi
  nhận portal) đòi hỏi log đầy đủ: code từng candidate, output từng
  candidate, quyết định cuối và lý do.
- **Timeout thực thi riêng cho mỗi candidate.** Một candidate treo
  không được kéo cả câu hỏi xuống. Candidate timeout tính là lỗi thực
  thi, không tính là một "output" để đồng thuận.
- **Không dùng lại candidate lỗi để vote.** Chỉ các output thực thi
  thành công mới tham gia đếm đồng thuận. Xem bảng quyết định §2.3.

### 2.3. Bảng quyết định đồng thuận

| Trường hợp (trên output đã chuẩn hóa) | Quyết định cơ sở | Điều kiện bổ sung |
|---|---|---|
| 3/3 đồng thuận, không lỗi | Trả lời đáp án đồng thuận | Vẫn phải qua cổng §2.4 (rule assertion, độ phủ bằng chứng, khoảng hợp lý). Đồng thuận 3/3 không miễn cổng. |
| 2/3 đồng thuận, 1 khác hoặc 1 lỗi | Trả lời đáp án của phe đa số | Phải qua cổng §2.4 **và** calibrated p của loại câu đó ≥ ngưỡng đã khóa (§3). Output thiểu số được log đầy đủ để phân tích lỗi. |
| 2/3 đồng thuận nhưng phe đa số là output rỗng | Abstain | Output rỗng có thể là filter sai, join sai, hoặc dữ liệu trống thật — không phân biệt được bằng vote. Cần kiểm tra bằng chứng riêng (số dòng sau filter, rule) trước khi kết luận "không có dữ liệu". |
| 1/3, 1/3, 1/3 (cả ba khác nhau) | Abstain | Không có cơ sở chọn. Log cả ba để phân tích: khác nhau ở join, ở filter, hay ở cách hiểu câu hỏi? |
| 0 output thành công (cả ba lỗi/timeout) | Abstain | Không phải unanswerable — lỗi thực thi không chứng minh dữ liệu thiếu. Xem §5. |
| 2/3 đồng thuận nhưng cổng §2.4 trượt | Abstain | Cổng là hard gate: trượt là abstain, không hạ ngưỡng để cứu. |

### 2.4. Cổng kiểm tra độc lập — phần bắt buộc, không phải tùy chọn

Đồng thuận mà không có cổng kiểm tra độc lập sẽ thất bại đúng ở những
câu nguy hiểm nhất. Mỗi đáp án trước khi trả lời phải qua:

1. **Rule assertion (xác định, không dùng LLM).** Viết từ rulebook của
   split: định nghĩa doanh thu, loại trừ đơn hủy/đơn có hàng trả, cửa sổ
   as-of, tuần thứ Hai–Chủ nhật, cửa sổ Tết, best-seller theo số lượng,
   giá mua bình quân gia quyền — các ví dụ này lấy từ tóm tắt rulebook
   round trước, **phải đối chiếu lại với rulebook thật của split**
   trước khi đóng code. Một đáp án vi phạm rule assertion thì abstain,
   không sửa bằng LLM.
2. **Độ phủ bằng chứng.** Các bảng/cột cần thiết có trong schema
   không? Số dòng sau filter là bao nhiêu? Có giá trị distinct nào cho
   trường phân loại không? Nếu bằng chứng mỏng (ví dụ chỉ 1–2 dòng sau
   filter cho một câu tổng hợp), hệ thống phải đánh dấu độ tin cậy thấp
   — ngưỡng cụ thể học trên `train_cal`, không đặt tay mù.
3. **Khoảng hợp lý từ profiler.** Đáp án có nằm trong khoảng hợp lý suy
   từ dữ liệu không (không âm khi đại lượng không thể âm, không vượt
   tổng toàn bộ khi là thành phần, ngày không vượt as-of)? Vi phạm →
   abstain hoặc vòng sửa có giới hạn (§2.5).
4. **Đường tính thứ hai (khi có thể).** Một đường tính viết logic thật
   sự khác (ví dụ SQL trên DB và pandas trên DataFrame, hoặc aggregate
   trước khi join so với join rồi aggregate) đồng ý với đáp án thì tăng
   tin cậy. **Cảnh báo:** hai đường chỉ là cùng một logic dịch sang hai
   ngôn ngữ thì không phải là kiểm tra độc lập — cùng hiểu sai thì cùng
   sai. Đo riêng trên `train_holdout`: trong các ca hai đường mâu thuẫn,
   bên nào đúng nhiều hơn? Nếu không đo được điều này thì không được coi
   cross-check là bằng chứng mạnh.

### 2.5. Vòng sửa có giới hạn (revision) — và khi nào cấm sửa

Đồng thuận không thay thế sửa lỗi thực thi, nhưng sửa không giới hạn sẽ
phá PA:

- Sửa tối đa 2 vòng cho mỗi candidate, mỗi vòng kèm lỗi thực thi cụ thể
  (lỗi cú pháp, sai tên cột, kết quả rỗng do filter quá chặt, vi phạm
  rule assertion).
- **Đóng băng kết quả đúng đầu tiên:** một candidate đã chạy đúng, qua
  rule assertion và nằm trong khoảng hợp lý thì không được sửa tiếp vì
  "trông hay hơn". Sửa code đúng thành sai là failure mode đã biết của
  vòng self-debug không có checker độc lập.
- Hết vòng sửa mà vẫn lỗi/rỗng/vi phạm rule → abstain, không đoán đáp
  án.
- Mọi revision đều log code trước/sau, lỗi, output — phục vụ đối chiếu
  Docker rerun.

### 2.6. Failure mode trung tâm: đồng thuận trên một hiểu sai chung

Đây là rủi ro lớn nhất của self-consistency trong DataMate, và là lý do
§2.4 tồn tại:

| Hiểu sai chung | Vì sao cả 3 candidate cùng mắc | Cách bắt (không phải vote) |
|---|---|---|
| Fan trap (join nhân đôi doanh thu) | Cùng một schema, cùng một đường join "tự nhiên" | Rule assertion + tính thứ hai aggregate-trước-khi-join + đếm đối chiếu số dòng |
| Sai rule nghiệp vụ (ví dụ trừ voucher ở cấp đơn trong khi rule chỉ trừ ở cấp dòng) | Cùng một prompt chứa cùng một cách diễn đạt rule (hoặc không có rule) | Trích rulebook theo câu hỏi + assertion xác định từ rule |
| Sai cửa sổ thời gian (vượt as-of, nhầm tuần, nhầm Tết âm lịch) | Cùng một cách hiểu "tháng này" | Assertion as-of + calendar.csv của split làm chuẩn |
| Cùng đọc nhầm schema (bảng/cột tương tự nhau) | Cùng một schema profile | Schema shortlist có fallback + đo recall bảng trên train |
| Cùng hiểu sai câu hỏi mơ hồ | Cùng một prompt, cùng một model | Tách P(cách hiểu) bằng rulebook; nếu rulebook không phân giải được thì abstain thay vì chọn cách hiểu phổ biến nhất |

Kết luận: **đồng thuận đo độ ổn định của hệ thống, không đo độ đúng.**
Một hệ thống ổn định nhưng sai vẫn cho 3/3 đồng thuận. Vì vậy trong báo
cáo thử nghiệm, luôn báo đồng thời: tỉ lệ đồng thuận, độ chính xác trên
số câu đã trả lời, PA, và tỉ lệ "đồng thuận nhưng sai" — chỉ số cuối
cùng này mới cho biết consensus đang giúp hay đang củng cố lỗi hệ
thống.

## 3. Calibration: học ngưỡng ở đâu, đo ở đâu, và đo cái gì

### 3.1. Tách dữ liệu đúng giao thức

```
train (có answers.jsonl — nguồn nhãn duy nhất chắc chắn)
  ├── train_fit       — viết helper, viết prompt, mọi thứ "nhìn thấy" được
  ├── train_cal       — học và khóa mọi ngưỡng (theo loại câu, theo độ khó)
  └── train_holdout   — đo MỘT LẦN, không sửa ngưỡng từ kết quả này rồi báo lại số đó
```

- **Ưu tiên tách theo business/loại hình** (leave-one-business-type-out):
  giấu toàn bộ một loại hình khỏi cả fit lẫn cal, đo trên loại hình đó.
  Đây là phép đo gần private test nhất mà train cho phép, vì private có
  loại hình mới. Nếu PA sụt lớn khi giấu một loại hình thì ưu tiên
  exploration/profiling tự động và dữ liệu tổng hợp cho business mới
  trước khi fine-tune — mức "lớn" phải đọc kèm số câu hỏi của loại hình
  đó, không dùng ngưỡng cứng như một kết luận.
- **Public test không tham gia học ngưỡng.** Nó chỉ dùng để kiểm tra
  format/latency và nộp sanity chính thức (tối đa 5 file/ngày theo ghi
  nhận trước). Dùng điểm leaderboard public để chỉnh ngưỡng vẫn là
  fitting vào public, dù không trực tiếp train trên nó.
- **Không đo trên dữ liệu đã dùng để viết helper hoặc fine-tune.** Nếu
  một rule helper được viết ra sau khi nhìn thấy một câu train cụ thể,
  câu đó không còn là holdout sạch cho rule đó nữa.

### 3.2. Điểm tin cậy (score) nào để học ngưỡng?

Không dùng confidence miệng của LLM. Score đề xuất cho mỗi câu (đây là
**đề xuất khởi đầu, chưa được tune** — trọng số phải được kiểm chứng
trên `train_cal`, không được coi là hằng số đã tối ưu):

```
score = 0,5 × consensus_fraction + 0,3 × second_path_agree + 0,2 × evidence_coverage
```

Trong đó:

- `consensus_fraction` = số candidate đồng thuận với đáp án được chọn /
  số candidate thực thi thành công (2/3 ≈ 0,67; 3/3 = 1,0).
- `second_path_agree` = 1 nếu đường tính thứ hai độc lập cho cùng output,
  0 nếu mâu thuẫn, 0,5 nếu không có đường thứ hai (không phạt cũng không
  thưởng mù).
- `evidence_coverage` = tỉ lệ bằng chứng cần thiết đã xác nhận được
  (bảng/cột có mặt, số dòng sau filter > 0, rule tương ứng có trong
  rulebook) — tính xác định từ profiler, không phải từ LLM.
- **Rule assertion là hard gate, không phải thành phần của score.**
  Trượt assertion → abstain bất kể score cao bao nhiêu.

Ngoài ra, một biến thể đáng thử trên `train_cal` là học ngưỡng trực tiếp
trên `consensus_fraction` theo từng loại câu (không qua score tổng hợp),
vì nó đơn giản hơn và ít nguy cơ overfit hơn. So sánh hai biến thể trên
cùng một `train_holdout` rồi chọn — không chọn bằng cảm tính.

### 3.3. Học ngưỡng theo loại câu

Thủ tục (code kèm theo, module calibration):

1. Trên `train_cal`, với mỗi loại câu (theo answer type: số, phần trăm,
   chuỗi, ngày, boolean, list, table; và khi đủ dữ liệu thì thêm nhóm độ
   khó), quét ngưỡng trên score theo bước 0,05.
2. Với mỗi ngưỡng, tính PA trên `train_cal` cho loại câu đó: PA = (đúng
   − sai) / tổng số câu của loại đó (câu abstain đóng góp 0).
3. Chọn ngưỡng cho PA cao nhất; hòa thì chọn ngưỡng cho coverage cao
   hơn (trả lời nhiều hơn khi PA bằng nhau là hợp lý vì PA đã tính cả
   sai).
4. **Ràng buộc hỗ trợ tối thiểu (đề xuất):** một loại câu có dưới ~30
   mẫu trong `train_cal` thì không học ngưỡng riêng — dùng ngưỡng toàn
   cục. Con số 30 là quy tắc thực hành đề xuất, không phải kết quả đo;
   nếu loại câu đó ít mẫu thì báo rõ trong kết quả là ngưỡng của nó kém
   tin cậy.
5. Khóa ngưỡng. Đo một lần trên `train_holdout`, báo PA, coverage, độ
   chính xác trên số câu đã trả lời, và phân rã theo loại câu.

### 3.4. Đo cái gì: risk–coverage và ECE (chẩn đoán, không phải mục tiêu)

- **Coverage** = số câu đã trả lời / tổng số câu.
- **Selective risk** = Số câu trả lời sai / số câu đã trả lời (= 1 − độ
  chính xác trên số câu đã trả lời).
- **Đường risk–coverage:** quét ngưỡng từ cao xuống thấp, vẽ risk theo
  coverage. Một hệ thống calibration tốt cho risk thấp ở coverage thấp
  và risk tăng dần khi coverage tăng. So sánh hai hệ thống bằng diện
  tích dưới đường risk–coverage (AURC) trên cùng một holdout — nhưng mục
  tiêu cuối cùng vẫn là PA, không phải AURC.
- **ECE (Expected Calibration Error)** chỉ là chẩn đoán: chia score
  thành các bin, so sánh tỉ lệ đúng thực tế trong bin với score trung
  bình của bin. ECE thấp không đảm bảo PA cao, và ECE đo trên business
  train không đảm bảo ECE trên business mới. Báo ECE kèm PA, không thay
  PA bằng ECE.
- **Báo cáo bắt buộc cho mỗi thí nghiệm:** PA, coverage, độ chính xác
  trên câu đã trả lời, số câu theo từng chuyển đổi (đúng→sai, sai→đúng,
  đúng→abstain, sai→abstain khi so với baseline), và phân rã theo loại
  câu + theo business. Một con PA lẻ không kèm số câu từng nhóm không đủ
  để kết luận "cải thiện".

### 3.5. Generalization: vì sao ngưỡng train không tự đúng trên business mới

- Ngưỡng học trên business train phản ánh cả độ khó của business đó lẫn
  độ tin cậy của hệ thống trên schema đó. Business mới có schema khác,
  README nghèo hơn, phân loại giá trị khác — cùng một score có thể tương
  ứng với xác suất đúng khác hẳn.
- Vì vậy: (a) luôn báo PA trên leave-one-business-type-out, không chỉ PA
  holdout ngẫu nhiên; (b) tín hiệu abstain phải bao gồm tín hiệu về bằng
  chứng (evidence coverage) — thứ có thể đo được trên business mới mà
  không cần nhãn; (c) khi evidence coverage thấp bất thường so với phân
  phối train (ví dụ schema phủ thấp, số dòng sau filter nhỏ), hệ thống
  nên thận trọng hơn ngưỡng toàn cục — cơ chế chính xác (ví dụ: hạ
  score một lượng, hay nâng ngưỡng theo nhóm) phải được học trên
  `train_cal` tách theo business, không đặt tay.
- Fine-tune trên train có nguy cơ overfit loại hình train và làm
  calibration tệ hơn trên loại hình mới. Trước khi fine-tune, đo baseline
  chưa fine-tune trên leave-one-business-type-out làm mốc; chỉ giữ
  fine-tune nếu nó cải thiện PA trên loại hình bị giấu, không chỉ trên
  holdout ngẫu nhiên.

## 4. Ngân sách thời gian: tính từ nguyên lý, không đoán

### 4.1. Công thức cơ sở (mô hình nhân tuần tự — bi quan, dùng làm trần)

```
T_gen_seq  = N × k × t_gen / G
T_total    ≈ T_gen_seq + T_exec + T_overhead
```

Trong đó: N = số câu hỏi, k = 3 candidate, t_gen = thời gian sinh một
candidate (giây, wall-clock khi chạy tuần tự), G = số GPU chạy song song
dưới dạng replica độc lập (= 2 nếu mỗi GPU chạy một bản model riêng; nếu
dùng tensor-parallel gộp 2 GPU cho một model thì G = 1 cho công thức này
và t_gen phải đo lại trong cấu hình đó), T_exec = tổng thời gian thực thi
+ format + kiểm tra, T_overhead = load model + load dữ liệu + profiler
(xem §4.4 về việc 6 giờ có bao gồm load model hay không — cần xác minh).

**Điểm hòa vốn (break-even) cho t_gen, mô hình tuần tự:**

```
t_gen_max = T_budget × G / (N × k) = 21.600 × 2 / (600 × 3) = 24 giây/candidate
```

Nghĩa là: nếu một candidate trung bình tốn quá 24 giây khi chạy tuần tự
thì riêng phần sinh đã vượt 6 giờ, chưa tính thực thi. Đây là **ƯỚC
LƯỢNG từ công thức**, không phải kết quả đo.

### 4.2. Bảng kịch bản (ƯỚC LƯỢNG — mọi ô đều từ công thức §4.1, chưa đo)

N = 600 câu (giả định người dùng), k = 3, G = 2, chưa tính
T_exec/T_overhead:

| t_gen / candidate (giả định) | T_gen = 600×3×t_gen/2 | Đánh giá |
|---|---|---|
| 2 giây | 1.800 giây = 0,50 giờ | Dư dả |
| 5 giây | 4.500 giây = 1,25 giờ | Dư dả |
| 10 giây | 9.000 giây = 2,50 giờ | Trong trần, còn chỗ cho thực thi + overhead |
| 15 giây | 13.500 giây = 3,75 giờ | Trong trần, cần kiểm soát T_exec |
| 20 giây | 18.000 giây = 5,00 giờ | Sát trần, T_exec + overhead chỉ còn < 1 giờ |
| 24 giây | 21.600 giây = 6,00 giờ | Hòa vốn — vượt ngay khi cộng bất kỳ overhead nào |
| 30 giây | 27.000 giây = 7,50 giờ | **Vượt trần** (mô hình tuần tự) |

Cộng thêm chi phí thực thi/format (ước lượng, chưa đo — thực thi trên
~300.000 dòng có thể tốn hàng giây mỗi câu nếu query kém):

| T_exec trung bình / câu (giả định) | Cộng thêm cho 600 câu |
|---|---|
| 0,5 giây | 300 giây = 0,08 giờ |
| 2 giây | 1.200 giây = 0,33 giờ |
| 5 giây | 3.000 giây = 0,83 giờ |

Quy tắc tỉ lệ: nếu N thực tế gấp đôi (1.200 câu), mọi thời gian trên gấp
đôi và t_gen hòa vốn giảm một nửa còn 12 giây/candidate. Nếu N chỉ bằng
một nửa (300 câu), t_gen hòa vốn tăng gấp đôi lên 48 giây/candidate.
**Không dùng bảng này với N khác mà không tính lại.**

### 4.3. Vì sao phép nhân tuần tự là bi quan: continuous batching

vLLM dùng continuous batching (lịch ở cấp độ từng bước decode: một
sequence xong thì sequence chờ sẽ chiếm slot ngay, không chờ cả batch)
và PagedAttention (KV cache theo block). Hệ quả cho bài toán này:

- Khi chạy 1.800 candidate generation như một **batch job offline**
  (không phải 1.800 lần gọi tuần tự), thời gian wall-clock không bằng
  `1800 × t_gen_latency_đơn`. Công thức đúng cho batch là:
  ```
  T_batch ≈ (N × k × avg_output_tokens) / system_throughput_tokens_per_sec + T_prefill
  ```
  trong đó `system_throughput_tokens_per_sec` là throughput đo được của
  hệ thống (phụ thuộc checkpoint, quantization, độ dài prompt, cấu hình
  batch) — **chưa đo, không được điền số mù vào công thức này**.
- Prefix caching (nếu bật và prompt chia sẻ phần đầu giống nhau, ví dụ
  cùng system prompt + cùng schema profile) có thể giảm đáng kể thời
  gian prefill cho các candidate sau — nhưng mức giảm phải đo, không
  được giả định.
- Hai GPU nên dùng như **hai replica độc lập** (mỗi GPU một bản model,
  chia đôi số câu hỏi) thay vì tensor-parallel, trừ khi một bản model
  không vừa một GPU. Replica độc lập cho G = 2 trong công thức §4.1;
  tensor-parallel không cho speedup tuyến tính và phải đo lại.
- **Kết luận vận hành:** bảng §4.2 là trần bi quan để ra quyết định an
  toàn. Nếu bảng tuần tự đã cho thấy vượt trần (t_gen > 24 giây) thì
  không được hy vọng batching sẽ cứu — phải giảm k, giảm độ dài output,
  hoặc dùng checkpoint nhanh hơn. Nếu bảng tuần tự còn dư, batching chỉ
  làm thời gian thật ngắn hơn, và vẫn phải đo kiểm chứng trước deadline.

### 4.4. Biến thể tiết kiệm chi phí: early-stop có điều kiện (tùy chọn, tách khỏi thiết kế gốc)

Thiết kế gốc là k = 3 đầy đủ. Biến thể tiết kiệm (chỉ áp dụng sau khi đo
baseline k = 3 trên `train_holdout`):

1. Sinh candidate 1 và 2. Nếu cả hai đồng thuận **và** qua cổng §2.4
   **và** calibrated p ≥ ngưỡng đã khóa → trả lời luôn, bỏ qua candidate
   3 (tiết kiệm ~1/3 chi phí sinh).
2. Nếu 1 và 2 mâu thuẫn, hoặc cổng trượt → sinh candidate 3 làm
   tie-break, áp bảng §2.3 như bình thường.
3. Biến thể này thay đổi phân phối của tín hiệu đồng thuận (các câu "dễ"
   sẽ không bao giờ có 3/3), nên ngưỡng học cho biến thể này phải học
   lại trên `train_cal` với đúng quy trình early-stop — không được tái
   dùng ngưỡng của k = 3 đầy đủ.

### 4.5. Checklist đo đạc bắt buộc trước khi chốt kiến trúc (chưa đo = chưa chốt)

- [ ] Latency sinh một candidate của checkpoint thật
  (Qwen2.5-Coder-7B-Instruct hoặc đối chứng) ở quantization sẽ dùng,
  trên GPU tương đương RTX 5090, với độ dài prompt thật (schema profile
  + rulebook trích) và độ dài output thật.
- [ ] Throughput batch của vLLM với 1.800 candidate (tokens/giây hệ
  thống) và hiệu quả prefix caching trên prompt thật.
- [ ] Thời gian thực thi trung bình mỗi câu trên business lớn nhất
  (~300.000 dòng), kể cả query tệ nhất trong holdout.
- [ ] Thời gian load model + load dữ liệu + profiler, và xác minh 6 giờ
  có bao gồm phần này không (ghi nhận portal trước đó nói "trong 6 giờ
  kể cả load model" — **cần đối chiếu lại với README/rulebook của split
  trước khi tin**).
- [ ] Tổng thời gian end-to-end trên toàn bộ `train_holdout` ngoại suy
  ra N private (nếu N private chưa biết thì báo theo công thức, không
  báo một con số tuyệt đối).

## 5. Phân biệt bằng code: `unanswerable` vs `abstain`

### 5.1. Hai quyết định, hai bản chất

| | `unanswerable` | `abstain` |
|---|---|---|
| Bản chất | Kết luận xác định từ dữ liệu và rulebook | Quyết định xác suất từ độ tin cậy |
| Câu hỏi đặt ra | "Dữ liệu có đủ để trả lời câu này không?" | "Kết quả tính ra có đủ tin cậy để trả lời không?" |
| Bằng chứng | Schema linking xác định: bảng/cột/rule cần thiết vắng mặt; câu hỏi nằm ngoài phạm vi phủ của dữ liệu (ví dụ hỏi về khoảng thời gian dữ liệu không có, hoặc về một loại giao dịch không tồn tại trong business đó) | Consensus, cổng kiểm tra, calibrated score — xem §2–§3 |
| Thứ tự trong pipeline | **Trước** khi sinh code: nếu schema check đã kết luận thiếu thì không sinh code đoán | **Sau** khi sinh và thực thi code: kết quả không qua cổng thì abstain |
| Lỗi nguy hiểm nhất | Báo `unanswerable` cho câu trả lời được (mất điểm, và tùy evaluator có thể tính như sai — CHƯA XÁC MINH) | Trả lời câu không chắc (sai −1) hoặc abstain oan câu chắc (mất +1) |
| Guard bắt buộc | Nếu schema shortlist cho rỗng/lỗi thì fallback một lần sang schema đầy đủ trước khi kết luận `unanswerable` — không kết luận thiếu dữ liệu từ một lần linking lỗi | Xem §2.5: hết vòng sửa mà vẫn lỗi/rỗng/vi phạm rule → abstain, không đoán |

### 5.2. Cây quyết định (đọc từ trên xuống, dừng ở lá đầu tiên khớp)

```
1. Schema/rulebook check (xác định):
   - Bảng/cột cần thiết vắng mặt, hoặc rule cần thiết không có trong rulebook của split,
     hoặc câu hỏi ngoài phạm vi phủ của dữ liệu
     → UNANSWERABLE (không sinh code)
2. Sinh k = 3 candidate, thực thi:
   - Cả ba lỗi/timeout → ABSTAIN (lỗi thực thi không chứng minh dữ liệu thiếu)
3. Đồng thuận + cổng §2.4 + ngưỡng đã khóa (§3):
   - Qua hết → ANSWER (đáp án đồng thuận, đã chuẩn hóa theo type)
   - Trượt bất kỳ cổng nào, hoặc đồng thuận không đạt, hoặc calibrated p < ngưỡng
     → ABSTAIN
```

Lưu ý về thứ tự: một câu có thể vừa thiếu dữ liệu vừa cho kết quả không
chắc — cây trên ưu tiên `unanswerable` vì schema check chạy trước. Điều
này chỉ đúng nếu schema check có độ chính xác cao (đo recall bảng/cột
trên train); nếu schema check hay báo thiếu oan thì thứ tự này sẽ biến
câu trả lời được thành `unanswerable` hàng loạt — phải đo tỉ lệ "báo
thiếu oan" trên `train_holdout` trước khi tin cây quyết định này.

### 5.3. Cách evaluator xử lý từng trường hợp — CHƯA XÁC MINH, câu hỏi phải trả lời trước khi chốt

Code kèm theo giữ ba loại quyết định tách biệt (`answer` /
`unanswerable` / `abstain`) và **không tự gán điểm** cho chúng. Trước khi
đóng submission, phải trả lời các câu sau bằng cách đọc evaluator/README/
rulebook của split (không suy đoán):

- **Q1.** Trả `unanswerable` cho một câu có đáp án thì được bao nhiêu
  điểm — 0, −1, hay bị loại khỏi tính điểm?
- **Q2.** Trả một giá trị cụ thể cho một câu unanswerable thì được bao
  nhiêu điểm (ghi nhận trước đó nói "bất kỳ đáp án nào cho câu
  unanswerable cũng là sai" — cần đối chiếu lại với evaluator thật)?
- **Q3.** Câu hỏi thiếu trong file submission thì tính như abstain (0),
  như sai (−1), hay submission bị coi là không hợp lệ?
- **Q4.** Sai type, sai thứ tự list, sai tên cột trong table có phải sai
  hoàn toàn không? Percent tính theo thang 0–100 hay 0–1, làm tròn bao
  nhiêu chữ số?
- **Q5.** Hòa thứ hạng (tie-break) tính thế nào, và ngưỡng tái lập
  |PA(uploaded) − PA(rerun)| ≤ 0,03 áp dụng ra sao?
- **Q6.** 6 giờ private test có bao gồm load model, load dữ liệu và
  profiler không?
- **Q7.** Tổng tham số tính theo total hay non-embedding (đối với MoE
  là total hay active)? Checkpoint fine-tune tính theo ngày base hay
  ngày checkpoint phái sinh?

Cho tới khi có đáp án, mọi bảng điểm trong tài liệu này chỉ tính PA trên
các câu **đã trả lời** theo công thức §1.2, và coi `unanswerable`/
`abstain` là hai loại "không trả lời" khác nhau về mặt chẩn đoán chứ
không gán điểm khác nhau cho chúng.

### 5.4. Mã hóa submission: tách quyết định khỏi mã hóa

Trong code kèm theo, hàm quyết định trả về đối tượng `Decision` với
`kind` tách biệt, còn việc mã hóa `Decision` thành dòng trong
`submission.jsonl` nằm ở một hàm riêng nhận tham số mã hóa do người
triển khai cung cấp sau khi đọc evaluator. Thiết kế này cố tình không
"tiện" — nó ngăn việc một giả định về evaluator bị chôn trong code
quyết định rồi quên mất.

## 6. Rủi ro, giới hạn và những gì tài liệu này KHÔNG khẳng định

- **Không khẳng định self-consistency cải thiện PA trên ZAIC.**
  Self-consistency cải thiện độ chính xác trên các benchmark suy luận
  trong paper gốc (điều kiện khác, model khác, không có PA, không có
  rulebook doanh nghiệp). Trên ZAIC nó là giả thuyết cần đo trên
  `train_holdout` với bảng chuyển đổi đầy đủ (§2.6).
- **Không khẳng định trọng số score §3.2 là tối ưu.** Đó là điểm khởi
  đầu để học ngưỡng, không phải kết quả tune. Nếu trên `train_cal` mà
  biến thể "chỉ dùng consensus_fraction theo loại câu" cho PA ngang bằng
  với score tổng hợp thì chọn biến thể đơn giản hơn.
- **Không khẳng định vLLM batching sẽ đưa k = 3 vào trong 6 giờ.**
  Batching giúp, nhưng mức giúp phụ thuộc throughput đo được (§4.5).
  Nếu latency sinh đơn lẻ đã quá 24 giây/candidate thì không hy vọng
  batching cứu.
- **Không khẳng định public test không có gold.** Đó là ghi nhận portal
  2026-10-26, chưa xác minh lại từ zip thật trong đợt này. Bước giải nén
  và liệt kê file là bắt buộc trước khi viết code đo.
- **Không khẳng định bất kỳ checkpoint, quantization hay cấu hình vLLM
  cụ thể nào.** Code kèm theo cố tình chỉ dùng thư viện chuẩn Python và
  nhận hàm thực thi từ bên ngoài, để phần consensus/calibration có thể
  kiểm thử mà không cần GPU, API, hay model thật.
- **Rủi ro vận hành lớn nhất:** ngưỡng học trên business train nhưng
  private là business mới (xem §3.5); đồng thuận củng cố lỗi hệ thống
  (xem §2.6); và mã hóa `unanswerable` sai vì chưa đọc evaluator (xem
  §5.3). Cả ba đều không sửa được bằng cách tăng k hay tăng temperature.

## 7. Kế hoạch thử nghiệm nhỏ nhất (trên train, chưa chạy trong đợt này)

| ID | Giả thuyết | Dữ liệu | Metric / tiêu chí giữ–dừng (ĐỀ XUẤT, không phải kết luận) |
|---|---|---|---|
| C1 — Baseline | 1 chương trình + ngưỡng khởi đầu 0,5 | `train_holdout` tách theo business | PA, coverage, độ chính xác trên câu đã trả lời, giây/câu — đường cơ sở cho mọi nâng cấp, cùng một holdout |
| C2 — Consensus | k = 3 + bảng §2.3 + cổng §2.4 thắng baseline | Cùng holdout với C1 | PA và bảng chuyển đổi 4 chiều; giữ nếu PA tăng và tỉ lệ "đồng thuận nhưng sai" không tăng |
| C3 — Calibration | Ngưỡng theo loại câu học trên `train_cal`, khóa rồi đo trên holdout | `train_cal` (học) → `train_holdout` (đo, một lần) | PA theo loại câu, risk–coverage; không sửa ngưỡng từ holdout rồi báo lại số đó |
| C4 — Generalization | Leave-one-business-type-out | Train, giấu toàn bộ 1 loại hình khỏi fit+cal | PA trên loại hình bị giấu vs loại hình đã thấy; nếu sụt lớn thì ưu tiên exploration + synthetic business mới trước khi fine-tune (đọc kèm số câu của loại hình đó, không dùng ngưỡng cứng) |
| C5 — Thời gian | Cấu hình đầy đủ vừa 6 giờ private | Toàn bộ `train_holdout`, ngoại suy theo công thức §4.1 | Tổng thời gian, giây/câu, thời gian sinh/thực thi tách riêng; nếu vượt: cắt candidate trước (early-stop §4.4), giảm vòng revision sau, giữ profiler + formatter + abstain |
| C6 — Unanswerable | Schema check + fallback một lần sang full schema | Holdout gồm cả câu unanswerable đã biết từ train | Tỉ lệ unanswerable đúng, tỉ lệ câu trả lời được bị báo thiếu oan, PA tổng |

Thứ tự làm việc đề xuất: C1 → C2 → C3 → C4 → C5 → C6. Không nhảy sang
fine-tune hay multi-candidate phức tạp hơn trước khi C1–C3 có số đo
trên cùng một holdout.

## 8. Nguồn

Ngày truy cập cho mọi nguồn dưới đây: 2026-10-27. Trạng thái xác minh:
**Đã đọc tóm tắt/abstract qua kết quả tìm kiếm** (không phải toàn văn)
trừ khi ghi khác. Không trích số leaderboard nào từ các nguồn này làm
mục tiêu ZAIC.

- Wang, X. và cộng sự. "Self-Consistency Improves Chain of Thought
  Reasoning in Language Models." ICLR 2023, arXiv:2203.11171.
  https://arxiv.org/abs/2203.11171 — Nguồn gốc của self-consistency:
  lấy mẫu nhiều đường suy luận rồi chọn đáp án nhất quán nhất; paper
  báo cải thiện trên GSM8K, SVAMP, AQuA, StrategyQA, ARC-challenge với
  các model lớn (điều kiện khác ZAIC, không suy ra PA).
- Kamath, A., Jia, R., Liang, P. và cộng sự (hướng nghiên cứu selective
  answering cho câu hỏi mơ hồ, arXiv:2305.14613).
  https://ar5iv.labs.arxiv.org/html/2305.14613 — Khung P(đáp án | câu
  hỏi) = Σ P(đáp án | cách hiểu) × P(cách hiểu | câu hỏi); confidence
  dùng cho selective prediction với ngưỡng τ và abstention ∅; nhấn mạnh
  calibration cho câu hỏi mơ hồ.
- Guo, C. và cộng sự. "On Calibration of Modern Neural Networks"
  (2017) — được trích dẫn trong các nguồn trên về việc confidence hiện
  đại thường overconfident và cần calibration; tài liệu này không mở
  trực tiếp toàn văn trong đợt này, chỉ dùng ở mức bối cảnh.
- vLLM: continuous batching và PagedAttention — khái niệm được mô tả
  trong tài liệu và các bài tổng hợp về vLLM (continuous batching ở cấp
  độ từng bước decode, KV cache theo block). Tài liệu này không điền bất
  kỳ con số throughput nào của vLLM vì chưa đo trên checkpoint và cấu
  hình thật; mọi con số thời gian trong §4 đều từ công thức với giả
  định ghi rõ, không lấy từ các bài tổng hợp đó.
- Ghi nhận portal ZAIC sau đăng nhập 2026-10-26 (từ các đợt nghiên cứu
  trước trong repo, chưa xác minh lại trong đợt này): DataMate
  `answers.jsonl` chỉ có trong train; public test có `questions.jsonl`
  nhưng không có đáp án kèm theo để tự chấm local; nộp public tối đa 5
  file/ngày; tối đa 2 lần nộp Docker, chỉ lần cuối được chấm; ngưỡng tái
  lập |PA(uploaded) − PA(rerun)| ≤ 0,03. Tất cả các điểm này phải đối
  chiếu lại với gói dữ liệu và evaluator thật trước khi chốt submission.
- Các quy tắc nghiệp vụ ví dụ trong §2.4 (định nghĩa doanh thu, loại
  trừ đơn hủy/trả, tuần thứ Hai–Chủ nhật, cửa sổ Tết, best-seller theo
  số lượng, giá mua bình quân gia quyền) lấy từ tóm tắt rulebook các
  đợt trước — **phải đối chiếu lại với rulebook thật của từng split**;
  chúng là ví dụ minh họa cho cơ chế assertion, không phải rulebook
  chính thức.

## 9. Đã xác minh / giả định / cần đo / câu hỏi evaluator còn mở

- **Đã xác minh (trong phạm vi bản nháp):** công thức hòa vốn
  p > 0,5 suy ra từ PA; công thức ngân sách tuần tự cho điểm hòa vốn
  24 giây/candidate tại N=600, k=3, G=2 (số học, chưa phải số đo);
  self-consistency gốc so sánh output sau thực thi, không so sánh code;
  code tách quyết định khỏi mã hóa submission.
- **Giả định:** public test không có gold local (ghi nhận portal
  2026-10-26, chưa xác minh lại từ zip thật); quy tắc nghiệp vụ ví dụ
  trong §2.4 khớp với rulebook của split; 6 giờ có bao gồm load model
  hay không vẫn cần đối chiếu; trọng số score 0,5/0,3/0,2 là điểm khởi
  đầu, chưa tune.
- **Cần đo trên dữ liệu/phần cứng ZAIC thật:** C1–C6 trên
  `train_holdout` tách theo business; latency sinh candidate của
  checkpoint thật trên GPU tương đương RTX 5090; throughput batch vLLM
  và hiệu quả prefix caching; thời gian thực thi trên business lớn
  nhất; tổng thời gian end-to-end ngoại suy ra N private thật.
- **Câu hỏi evaluator còn mở:** xem §5.3 (Q1–Q7); đồng thời xem danh
  sách đầy đủ Q-D1..Q-D6 trong [../gaps.md](../gaps.md). Không gửi câu
  hỏi cho ban tổ chức trong đợt này.

---

## Cập nhật đợt 3 (2026-10-27) — sửa code, đã kiểm chứng bằng test

Các thay đổi trong `04-confidence-abstain-datamate.py`:

- **Canonical form gắn tag type.** Trước đây bool trả về bare `True`
  và number trả về bare float, mà trong Python `True == 1.0` nên
  `outputs_equal(True, 1)` sai thành True. Giờ mọi dạng đều có tag:
  bool → `("bool", …)`, number → `("number", …)`, string →
  `("string", …)`, date/datetime → `("date", isoformat)`. Khác type
  không bao giờ bằng nhau theo construction. Int/float vẫn tương đương
  khi cùng giá trị sau làm tròn 2dp (`1` = `1.0`); NaN/inf là giá trị
  đặc biệt riêng, không bằng số nào. Date object và chuỗi ngày vẫn
  khác type — caller muốn chúng khớp thì phải chuẩn hóa type trước
  consensus, code không tự gộp.
- **Consensus đổi sang đa số tuyệt đối.** Trước đây
  `best_count >= 2` nên 2/5 (thiểu số) và hòa 2/2 trong 4 candidate đều
  bị trả lời. Giờ thắng chỉ khi `best_count * 2 > n_successful`.
  Mẫu số là số candidate thành công, và reasons luôn ghi số attempted
  và số failed (`2/3 successful (5 attempted, 2 failed)`), nên "2/3"
  không bao giờ lặng lẽ nghĩa là "2 trên 5 thử, 3 hỏng". k=1 là trường
  hợp suy biến (1 candidate tự nhiên đa số tuyệt đối) và reason ghi
  rõ "không có bằng chứng consensus".
- **Calibration thêm ngưỡng reject-all.** Lưới ngưỡng giờ gồm [0, 1]
  cộng ngưỡng `1.0 + step` (không trả lời gì cả). Ca một record
  (score=1.0, correct=False) trước đây bắt buộc trả lời với PA=-1; giờ
  reject-all thắng với PA=0. Ngưỡng reject-all chỉ thắng khi PA tốt
  hơn hẳn (hòa thì giữ coverage cao hơn). Tập calibration rỗng → ngưỡng
  reject-all (fail-closed) thay vì 0,0 bịa đặt. Ba hàm
  `learn_thresholds` / `evaluate_holdout` / `decide_question` dùng
  chung semantics: trả lời ⟺ `score >= threshold`.
- **Schema coverage từ full scan, không tin shortlist.** Thêm
  `check_schema_coverage()`: một item yêu cầu được coi là có nếu nó
  hoặc alias của nó xuất hiện trong schema đầy đủ (so khớp không phân
  biệt hoa/thường và space/underscore). Chỉ item còn thiếu sau scan này
  mới được báo, và `fallback_tried=True` là đúng theo construction —
  caller không được tự build `SchemaCoverage` từ shortlist của planner
  rồi gắn `fallback_tried=True`. Hàm này KHÔNG chứng minh: cột có trong
  schema vẫn có thể không có dòng trong khoảng cần hỏi, và giá trị suy
  ra được (ví dụ revenue từ price × quantity khi không có cột revenue)
  là quyết định modelling riêng của caller.
- **Rỗng được xử lý phân biệt, không gộp.** `COUNT=0` là số 0, trả lời
  bình thường (test đã chạy). List/chuỗi rỗng đồng thuận vẫn abstain
  theo mặc định vì có thể là filter sai, nhưng caller đã kiểm chứng
  filter và kiểu đáp án rỗng thì truyền `allow_empty_answer=True`.
  Rỗng không tự động thành `unanswerable` — đó là kết luận khác, xem
  `../research/round3-p5-evidence-of-absence.md` và
  `research-updates-2026-10-27.md` §5 (đảo thứ tự: `unanswerable` chỉ
  sau checklist E0–E8, abstain là mặc định khi không chắc).
- **Liên hệ đợt research 3:** score trọng số 0,5/0,3/0,2 bị đề xuất bỏ
  (thay bằng cổng xác định + verifier logistic nhỏ trên đặc trưng quan
  sát được), pool candidate đổi từ seed-only sang đa dạng chiến lược,
  và compute đổi sang adaptive 1 → 3 → 3+1 — xem
  `../research/round3-p4-consensus-compute.md` và
  `research-updates-2026-10-27.md` §4. Code hiện tại vẫn giữ hàm
  `combined_score` cho tương thích, nhưng tài liệu này không còn coi
  nó là cổng quyết định được khuyến nghị; thí nghiệm phân biệt A0→A5
  trong bản nháp P4 là bước tiếp theo.
