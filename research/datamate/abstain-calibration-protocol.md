# Chiến lược tách validation, calibration và abstain cho DataMate

> Tài liệu đợt 4 — đi sâu hơn, không lặp lại `deep-dives/04-confidence-abstain-datamate.md`
> (04 đã có: chứng minh `2p−1`, bảng quyết định consensus k=3, score khởi đầu
> `0,5·consensus + 0,3·second_path + 0,2·evidence`, quét ngưỡng bước 0,05, min-support
> ~30, risk–coverage/AURC dạng chẩn đoán) và `deep-dives/03-duckdb-excel-datamate.md`
> (03 đã có: DuckDB làm engine thống nhất, LLM chỉ sinh 1 SQL SELECT/WITH, tiền dùng
> DECIMAL không dùng float, SQLite đọc bằng sqlite3 stdlib). Phần mới ở đây: chứng
> minh ngưỡng bằng lập luận biên, công thức lệch ngưỡng dưới domain shift, calibrator
> học được thay cho trọng số cố định, giao thức LOBO lồng nhau chi tiết, cơ chế abstain
> gắn ở code của 5 solution (DABstep, ReFoRCE, CHESS, CSC-SQL, XiYan-SQL), và pseudocode
> chuẩn hoá output ở cấp code.
>
> **Hệ thống nhãn bằng chứng (bắt buộc cho mọi kết luận trong tài liệu này):**
> - `[OFFICIAL]`: đối soát trực tiếp từ ban tổ chức hoặc README/`zaic_tools` của bộ dữ liệu.
> - `[CODE_INSPECTED]`: đã đọc trực tiếp tên file, commit, class/function trong repo nguồn.
> - `[LOCALLY_VERIFIED]`: đã chạy thử nghiệm và kiểm chứng log thực tế.
> - `[INFERENCE]`: nhận định kỹ thuật suy ra từ ngữ cảnh thi đấu. Kết luận nào chỉ dựa
> trên số benchmark (BIRD/Spider/DABstep) thì nhãn là `[INFERENCE]`, không được đọc
> thành bảo đảm cho DataMate.
> - Các fact về cuộc thi dưới đây lấy từ `competition/datamate.md` — repo tóm tắt lại
> từ portal sau đăng nhập ngày 2026-10-26, **không phải văn bản gốc của BTC** — nên
> gắn `[CODE_INSPECTED]`, không gắn `[OFFICIAL]`, và phải đối soát lại portal trước
> khi nộp. Dữ liệu DataMate đã được tải và kiểm kê local ngày 2026-10-28 (xem §6.11): train 3000 câu / 30 business (biz_101–biz_130), public_test 1000 câu / 14 business (dev_001–dev_014) và **không có `answers.jsonl`** (giao thức "không dùng public_test để tune" đứng vững); schema `calendar.csv` đã xác minh (cột `date,weekday,lunar_day,lunar_month,lunar_year,lunar_leap,holiday`, phủ 2024-01-01–2027-12-31); gold percent trên train là thang 0–100; gold number là số thuần; không có field type tường minh trong README từng business (LOBO chạy nhánh pseudo-type, §3.4). Những gì vẫn UNVERIFIED là mã hoá abstain của evaluator và mode làm tròn (xem §6)
>
> **Fact nền (từ `competition/datamate.md` [CODE_INSPECTED]):** output là 1 đáp án có
> type rõ ràng — `number`, `percent`, `string`, `date`, `boolean`, `list`, `table` —
> hoặc `unanswerable` (dữ liệu thiếu thứ cần thiết) hoặc `abstain` (agent chủ động
> không trả lời). Đúng chỉ khi type bằng type tham chiếu VÀ giá trị khớp: number khớp
> sau làm tròn 2 chữ số thập phân; percent khớp sau làm tròn 2 chữ số và đúng dấu;
> string chuẩn hoá NFC + lowercase + ký tự không phải chữ/số/khoảng trắng thành khoảng
> trắng + gộp khoảng trắng, **giữ dấu thanh**. Penalized Accuracy: đúng +1, abstain 0,
> sai −1, trọng số bằng nhau, không điểm từng phần; sai type hoặc sai giá trị đều là
> sai. Private test có loại hình doanh nghiệp chưa xuất hiện ở train/public test. Tổng
> tham số inference ≤ 15B (tính cả embedding/reranker/classifier và toàn bộ MoE, không
> tính theo active); model công bố trước 01/10/2026; offline Docker, được sinh và thực
> thi code; máy chấm tham chiếu 2× RTX 5090, 512GB RAM, toàn bộ private test trong 6 giờ
> wall-clock kể cả nạp model; tái lập |PA(uploaded) − PA(rerun)| ≤ 0,03.

## 0. Quyết định trước (binary first)

1. **Ngưỡng:** trên xác suất đã calibration, ngưỡng tối ưu luôn là `p > 0,5`
(chứng minh kỳ vọng + chứng minh biên, §1); ngưỡng vận hành = `0,5 + δ` với δ là
bias LOBO đo được, cộng thành phần LCB khi mẫu ít. **Không bao giờ so score thô
với 0,5.**
2. **Confidence:** bỏ score trọng số cố định, thay bằng **calibrator học trên
train_cal** với features (consensus fraction + execution rate + cross-path
agreement + evidence coverage + fluency tuỳ chọn). Vote share chỉ là tín hiệu
xếp hạng; map vote→P(đúng) phải học.
3. **Validation:** tách theo **business/type**, không tách theo câu hỏi; chạy LOBO
Variant B làm chính (m < 4) và Variant A làm chẩn đoán chuyển ngưỡng (m ≥ 4);
báo cáo per-type + PA tệ nhất + độ phân tán ngưỡng, không gộp mù.
4. **Abstain:** không solution nào trong 5 cái có cơ chế abstain thật (§4) — cơ chế
khả thi nhất là **gate bằng code gắn tại đúng một choke point**: sau bước
vote/gom cụm theo kết quả thực thi, trước khi ghi submission, với 5 điều kiện
abstain (§4.6). Không copy prompt "Not Applicable", không để abstain thành
"vắng file", không nộp sentinel/lỗi/placeholder.
5. **Chuẩn hoá:** code xác định, tách khỏi LLM (§5); mọi quy ước chưa verify
(format percent 0–100 vs 0–1, mode làm tròn, mã hoá abstain, schema calendar.csv)
đều có bước "đo trên gold train" thay vì đoán, và trường hợp mơ hồ không phân
giải được thì abstain, không đoán mò đáp án.

## 1. Công thức ngưỡng abstain tối ưu từ Penalized Accuracy

### 1.1. Chứng minh ngưỡng 0,5 — hai cách, cùng một đáp án [INFERENCE]

**Cách 1: kỳ vọng từng câu.** Với `p = P(đáp án đúng | mọi thông tin hệ thống có)`
— xác suất đúng **sau calibration**, không phải confidence miệng của LLM:

| Quyết định | Kỳ vọng điểm |
|---|---|
| Trả lời | `p·(+1) + (1−p)·(−1) = 2p − 1` |
| Abstain | `0` |

Trả lời có lợi khi `2p − 1 > 0`, tức **`p > 0,5`**. Tại đúng `p = 0,5` thì hoà vốn —
quy tắc thực hành: chỉ trả lời khi `p > 0,5` nghiêm ngặt; tại đúng 0,5 thì abstain
(tránh rủi ro phương sai mà không có kỳ vọng dương).

**Cách 2: lập luận biên — chứng minh mạnh hơn, và là cơ sở cho thuật toán chọn
ngưỡng.** Sắp xếp mọi câu hỏi theo `p` đã calibration giảm dần:
`p_(1) ≥ p_(2) ≥ … ≥ p_(N)`. Trả lời đúng `m` câu đầu thì PA kỳ vọng là
`PA(m) = (1/N) · Σ_{i≤m} (2·p_(i) − 1)`. Thêm câu thứ `m+1` làm PA tăng **khi và
chỉ khi** `2·p_(m+1) − 1 > 0`, tức `p_(m+1) > 0,5`. Hệ quả: ngưỡng tối ưu trên xác
suất đã calibration **luôn là 0,5**, không phụ thuộc phân phối `p`, không phụ thuộc
N, không phụ thuộc loại câu — miễn là `p` là xác suất đúng thật và các câu độc lập
về điểm (PA cộng tính theo câu, đúng theo định nghĩa [CODE_INSPECTED]).

**Đẳng thức PA theo coverage–risk** [INFERENCE]: với ngưỡng τ, coverage `c(τ)` =
tỉ lệ câu được trả lời, selective risk `r(τ)` = tỉ lệ sai trong số câu được trả lời,
accuracy trên câu đã trả lời `a(τ) = 1 − r(τ)`. Khi đó
`PA(τ) = c(τ)·(a(τ) − (1 − a(τ))) = c(τ)·(1 − 2·r(τ))`.
PA không phải accuracy: tăng coverage mà risk tăng quá nhanh sẽ **giảm** PA — thêm
một nhóm câu có accuracy `a` làm PA tăng khi và chỉ khi `a > 0,5` (lại ra 0,5, từ
một hướng khác). Đẳng thức này đã được kiểm chứng số học trên demo tổng hợp
[LOCALLY_VERIFIED trên dữ liệu tổng hợp, không phải DataMate: spot-check τ = 0,7
cho PA = 0,2310, coverage = 0,505, risk = 0,271, khớp chính xác].

### 1.2. Công thức ngưỡng tổng quát (khi bài toán lệch khỏi PA thuần) [INFERENCE]

Đặt `U_đúng`, `U_sai`, `U_abstain` là điểm/lợi ích của ba kết cục. Trả lời có lợi khi
`p·U_đúng + (1−p)·U_sai > U_abstain`, tức
`p > (U_abstain − U_sai) / (U_đúng − U_sai)` (khi `U_đúng > U_sai`).
Áp vào PA thuần (+1/−1/0): `p > (0 − (−1))/(1 − (−1)) = 1/2`. Các trường hợp lệch:

| Tình huống | Công thức ngưỡng | Ý nghĩa thực hành |
|---|---|---|
| Abstain bị phạt ngầm λ (tie-break ưu tiên coverage) | `p > (1 − λ)/2` | λ = 0,1 → 0,45. Chỉ dùng khi có quy tắc tie-break/coverage được xác minh — hiện tại **không có bằng chứng** về tie-break như vậy [UNVERIFIED], mặc định λ = 0 |
| Sai bị phạt nặng hơn PA | `U_sai = −(1+δ)` → `p > (1+δ)/(2+δ)` | δ = 0,5 → 0,6. Chỉ dùng khi quy tắc phụ được xác minh; hiện tại không dùng |
| Ràng buộc coverage tối thiểu `c ≥ c_min` | `τ* = argmax PA(τ) s.t. c(τ) ≥ c_min` | Ngưỡng là nghiệm bài toán tối ưu có ràng buộc, không còn là 0,5 thuần. Chỉ áp khi có yêu cầu coverage từ BTC — hiện tại không có |
| **Score thô `s` chưa phải xác suất** | Ngưỡng trên `s` KHÔNG phải 0,5; phải qua map calibration `p = f(s)` rồi áp 0,5 lên `p` | Trường hợp thực tế quan trọng nhất (§1.3A). Đừng bao giờ so score thô với 0,5 |
| **Domain shift: `p` train-calibration lệch trên type mới** | Ngưỡng vận hành trên score train-calibration phải cộng biên an toàn δ (§1.3B) | Trường hợp thực tế quan trọng thứ hai |

### 1.3. Khi nào ngưỡng thực tế lệch khỏi 0,5 — và lệch về hướng nào

**A. Score chưa calibration (luôn xảy ra với confidence miệng / vote share thô)**
[INFERENCE]. Ngưỡng 0,5 chỉ đúng trên xác suất thật. Nếu score `s` là vote share,
mean-logprob, hay confidence tự báo cáo, thì quan hệ `s ↦ P(đúng|s)` phải được
**học** trên tập calibration (isotonic hoặc Platt, §2.4). Sau khi có map `f`,
quyết định là `f(s) > 0,5` — tương đương một ngưỡng `τ_s` trên score thô mà **không
nhất thiết bằng 0,5**. Sai lầm phổ biến nhất là lấy ngưỡng 0,5 áp trực tiếp lên
score thô.

**B. Domain shift làm `p` train-calibration lệch trên type mới** [INFERENCE]. Giả sử
trên type mới, `p_thật ≈ p̂ − b(p̂)` với bias `b > 0` (overconfidence dưới shift —
hướng thường gặp vì schema/rule mới lạ hơn). Quy tắc đúng trên type mới là
`p_thật > 0,5`, tức `p̂ > 0,5 + b`. Vậy **ngưỡng vận hành phải DỊCH LÊN một lượng
bằng bias ước lượng**: `τ_vận_hành = 0,5 + δ`, với δ đo bằng (i) ECE có dấu (signed
calibration gap: mean(p̂) − accuracy) trên held-out type trong LOBO, hoặc (ii) độ
lệch ngưỡng tối ưu giữa các type (τ*_type − 0,5). Nếu LOBO cho thấy bias ≈ 0 thì
δ = 0 và giữ 0,5. Demo tổng hợp [LOCALLY_VERIFIED]: type overconfident (+0,2)
có ngưỡng tối ưu 0,70 so với 0,59 của type calibrated; áp ngưỡng 0,59 cho type
overconfident mất 0,025 PA — đúng như dự đoán (ngưỡng phải dịch lên).

**C. Bất định ước lượng `p` (calibration set nhỏ, type ít mẫu)** [INFERENCE]. Khi
`p̂` là ước lượng nhiễu, quyết định né rủi ro dùng cận dưới tin cậy: trả lời chỉ
khi `LCB(p̂) > 0,5`, với `LCB` là cận dưới khoảng Wilson (mức ~80–90%) của accuracy
trong bin/score-band chứa câu đó. Ngưỡng hiệu dụng trở thành
`τ_eff = 0,5 + z·σ(p̂)` — band càng ít mẫu → σ càng lớn → ngưỡng càng cao → abstain
nhiều hơn ở vùng thiếu dữ liệu. Đây là cách chính quy hoá "min-support ~30" của 04:
thay vì cấm ngưỡng riêng khi < 30 mẫu, dùng LCB để ngưỡng tự thận trọng theo lượng mẫu.

**D. Ngưỡng theo loại câu** [INFERENCE]. Ngưỡng 0,5 trên `p` đã calibration là phổ
quát, nhưng map `f(s)` và bias `δ` **khác nhau theo loại câu** (number/percent dễ
sai làm tròn hơn boolean; table khó hơn string). Triển khai đúng: **một ngưỡng xác
suất chung 0,5 + δ, nhưng map calibration và δ riêng theo loại câu** (và theo band
bằng chứng, §2). Đừng học "ngưỡng score thô riêng theo loại" mà không qua
calibration — hai cách tương đương về toán khi map đơn điệu, nhưng cách qua
calibration cho phép so sánh và chuyển giao giữa các loại, còn ngưỡng thô thì không.

### 1.4. Quy tắc chọn ngưỡng trên tập calibration nội bộ (không dùng public_test)

```
Đầu vào: train_fit (viết helper/prompt), train_cal (học map + ngưỡng),
train_holdout (đo 1 lần)
CẤM: mọi dạng dùng public_test để học/chỉnh ngưỡng — kể cả dùng điểm leaderboard
public, kể cả fit không giám sát trên input public_test (§2.4: vì sao).
```

1. **Fit map calibration `f` trên train_cal** (isotonic nếu ≥ ~200 mẫu có nhãn,
Platt/logistic nếu ít hơn — §2.4).
2. **Quét ngưỡng trên `p̂` (không phải score thô) theo cộng dồn biên (§1.1):**
sắp xếp giảm dần theo `p̂`, tính PA cộng dồn, chọn τ cho PA cực đại; hoà thì
chọn τ cho coverage cao hơn (PA đã tính cả sai nên hoà PA thì trả lời nhiều hơn
là hợp lý — khớp 04).
3. **Áp biên an toàn LOBO:** đo bias `δ` bằng LOBO (§3):
`δ = max(0, mean over held-out types của (mean p̂ − accuracy))` trên các câu được
trả lời ở ngưỡng τ, cộng thêm thành phần phương sai nếu mẫu/type ít (quy tắc LCB
§1.3C). Ngưỡng khoá: `τ_khoá = τ_cal + δ`. Nếu δ = 0 thì `τ_khoá = τ_cal`.
4. **Khoá và đo một lần trên train_holdout** (tách theo business, §3): báo PA,
coverage, accuracy trên câu đã trả lời, ECE, và phân rã theo loại câu + theo
business. **Không sửa ngưỡng từ kết quả holdout rồi báo lại số đó** (quy tắc đã
có trong `plans/datamate.md` [CODE_INSPECTED]).
5. **Ngưỡng theo loại câu:** chỉ tách riêng khi loại đó có đủ mẫu trong train_cal
(thực hành: ≥ 30 mẫu đã trả lời ở vùng lân cận ngưỡng; nếu ít hơn, dùng ngưỡng
toàn cục + LCB). Mọi ngưỡng riêng đều phải qua bước 3 (δ riêng theo loại nếu đo
được, nếu không thì δ toàn cục).

### 1.5. Đo ECE và đường risk–coverage — công thức và cách đọc đúng

**ECE** [INFERENCE — công thức chuẩn theo Guo et al. 2017]. Chia N dự đoán thành B
bin theo confidence `p̂` (thường B = 10–15, equal-width; phân phối lệch thì dùng
equal-mass/adaptive bins để mỗi bin đủ mẫu):
`ECE = Σ_{b=1..B} (|B_b| / N) · |acc(B_b) − conf(B_b)|`.
Bổ sung bắt buộc: **signed gap theo bin** (`conf − acc` dương = overconfident, âm =
underconfident) — ECE tuyệt đối che mất hướng lệch, mà hướng lệch mới quyết định δ.
Luôn báo reliability diagram kèm ECE; báo ECE **riêng từng held-out type** trong
LOBO, không chỉ ECE gộp; bin < 30 mẫu thì gộp bin hoặc báo kèm khoảng tin cậy
bootstrap. ECE ≠ mục tiêu: ECE thấp không đảm bảo PA cao. Báo thêm **Brier score**
`BS = (1/N)·Σ(p̂_i − y_i)²` và **NLL** để so sánh các calibrator.

**Đường risk–coverage và AURC** [INFERENCE — theo Geifman & El-Yaniv 2017].
`coverage(κ) = |{i: p̂_i ≥ κ}| / N`; `risk(κ) = |{i: p̂_i ≥ κ, sai}| / |{i: p̂_i ≥ κ}|`;
`AURC = ∫₀¹ risk(coverage) d(coverage)`. Cách đọc đúng cho DataMate: đường tốt thì
risk thấp ở coverage thấp, tăng dần khi coverage tăng (hệ thống xếp câu dễ lên
trước). Đường phẳng hoặc risk tăng vọt sớm = confidence không tách được đúng/sai →
vấn đề nằm ở tín hiệu confidence (§2), không phải ở việc chọn ngưỡng. AURC chỉ
dùng để so sánh hai hệ thống confidence trên cùng holdout. Vẽ thêm **đường
PA–coverage**: đỉnh của đường này chính là ngưỡng tối ưu; nếu đỉnh phẳng (PA thay
đổi < 0,01 trong một khoảng ngưỡng rộng) thì chọn điểm giữa khoảng phẳng để ổn
định dưới shift.

### 1.6. Kiểm chứng thủ tục bằng demo tổng hợp [LOCALLY_VERIFIED]

Chạy bằng Python stdlib (seed 42, N = 1000 câu/type tổng hợp): type A có score =
xác suất đúng thật (calibrated); type B có score = xác suất thật + 0,2
(overconfident, clip [0,01, 0,99]). Kết quả: ECE type A = 0,036; ECE type B = 0,203
→ ECE phát hiện được overconfidence. Fit temperature scaling trên type B cho
T* = 2,38, ECE giảm 0,203 → 0,145 — **không về gần 0**: temperature là họ 1 tham số,
không sửa được bias cộng thuần tuý (§2.4). Ngưỡng tối ưu trên A: τ = 0,59, PA =
0,242; trên B: τ = 0,70, PA = 0,231; áp τ_A cho B chỉ được PA = 0,206 — **mất 0,025
PA do không dịch ngưỡng**. Vote-share: trong mixture tổng hợp (60% câu "dễ" với
mỗi sample đúng 90%, 40% câu "bẫy" với mỗi sample đúng 10%), vote 2/3 map tới
P(majority đúng) = 1,0 chứ không phải 0,67 — minh hoạ trực quan rằng **vote share
không phải xác suất** (§2.2).
**Giới hạn của demo:** dữ liệu tổng hợp, phân phối tự đặt, không liên quan dữ liệu
DataMate thật. Nó chỉ kiểm chứng rằng công thức ECE / PA(τ) / dịch ngưỡng /
temperature scaling **chạy đúng như toán**, không phải bằng chứng rằng các con số
(0,025 PA, T* = 2,38) sẽ xuất hiện trên DataMate.

## 2. Thuật toán tính confidence score

Nguyên tắc kiến trúc (đi xa hơn score trọng số cố định của 04): **score cuối phải
là xác suất đã calibration `p̂`, không phải điểm cộng có trọng số.** Trọng số
`0,5/0,3/0,2` của 04 là điểm khởi đầu chưa tune; thiết kế dưới đây thay nó bằng
calibrator học được trên train_cal, trong đó ba tín hiệu là **features**, không phải
thành phần cộng trực tiếp. Lý do: quan hệ giữa các tín hiệu và P(đúng) không tuyến
tính (vd: consensus 3/3 + second-path mâu thuẫn nguy hiểm hơn consensus 2/3 +
second-path đồng ý — tương tác, không cộng được), và trọng số tối ưu thay đổi theo
loại câu và theo type.

### 2.1. Tín hiệu (a): agreement giữa SQL và Python — định nghĩa đúng "độc lập"

Hai đường tính chỉ được tính là cross-check khi chúng **khác logic thật sự**,
không phải cùng một logic dịch sang hai ngôn ngữ [INFERENCE]. Kiểm tra độc lập
bằng code, không bằng cảm tính: SQL aggregate trước khi join (tránh fan trap) vs
Python join rồi aggregate rồi đối chiếu số dòng — khác thứ tự phép toán → độc lập
yếu. SQL tính theo định nghĩa rulebook A vs Python tính theo định nghĩa rulebook B
(khi rulebook có hai cách đọc) — khác cách hiểu → độc lập mạnh, nhưng mâu thuẫn lúc
này phản ánh mơ hồ rule, không phản ánh lỗi tính. SQL và Python cùng một prompt,
cùng một model, cùng một cách hiểu schema → **không độc lập** dù khác ngôn ngữ.
Trong trường hợp này, `second_path_agree` phải bị hạ trọng số trong calibrator
(dùng feature "cùng prompt/cùng model" làm biến điều tiết), hoặc tốt hơn: tạo đa
dạng bằng prompt khác (một path dùng rulebook trích, một path dùng schema profile
thuần) thay vì chỉ đổi ngôn ngữ.

```python
def cross_path_features(executed):
# executed: dict path -> list of (output_canonical, error)
# Chỉ output thực thi THÀNH CÔNG mới tham gia; output RỖNG không tính là giá trị.
succ_sql = [o for (o, e) in executed["sql"] if e is None and o is not EMPTY]
succ_py = [o for (o, e) in executed["py"] if e is None and o is not EMPTY]
if not succ_sql or not succ_py:
return {"agree": None, "n_sql": len(succ_sql), "n_py": len(succ_py)}
# So sánh trên output ĐÃ CHUẨN HOÁ theo type (§5), không so sánh code.
agree = canonical_majority(succ_sql) == canonical_majority(succ_py)
inter = fraction_equal_to(succ_py, canonical_majority(succ_sql))
return {"agree": agree, "cross_fraction": inter}
```

**Quy tắc output rỗng (quan trọng, bổ sung cho 04):** hai output rỗng "đồng ý" với
nhau không phải là bằng chứng — cùng một filter sai có thể cho rỗng cả hai đường.
Vì vậy: (i) output rỗng bị loại khỏi tử số consensus; (ii) nếu đáp án đa số là rỗng
→ abstain bất kể vote (04 đã có quy tắc này — giữ nguyên); (iii) trong cross-path,
rỗng–rỗng tính là `agree = None` (thiếu bằng chứng), không phải `agree = True`.

**Công thức kết hợp vote share + execution success** [INFERENCE]. Với `k`
candidate, `s` = số thực thi thành công, `m` = số thành công đồng ý với đáp án được
chọn: `consensus_fraction f = m / s` (không phải `m / k` — candidate lỗi không
vote); `execution_rate e = s / k`. Đừng dùng `m/k` vì nó gộp hai thất bại khác
nhau (lỗi thực thi vs bất đồng) thành một số — calibrator cần tách chúng: `f`
thấp + `e` cao = bất đồng thật (nghi ngờ logic); `f` cao + `e` thấp = mong manh
(ít bằng chứng, dù đồng thuận). Trong calibrator (§2.4), đưa cả `f`, `e`, và `s`
(số mẫu tuyệt đối — `f = 2/2` kém tin hơn `f = 3/3`) làm features riêng. Ngoài ra
đưa `evidence_coverage` (tỉ lệ bằng chứng xác định: bảng/cột có mặt, số dòng sau
filter > 0, rule có trong rulebook — tính từ profiler, không từ LLM, như 04) và
`gate_pass` (rule assertion là hard gate, không phải feature: trượt là abstain bất
kể score).

### 2.2. Tín hiệu (b): self-consistency k-sample — vote share là tín hiệu xếp hạng

Với k sample độc lập, vote share của đáp án được chọn: `v = m / s` (m = số sample
cho đáp án đa số, s = số sample thành công; xem §2.1 về mẫu số).

**Vì sao vote share ≠ P(đúng) — ba lý do, mỗi lý do đều có hệ quả thiết kế**
[INFERENCE]:

1. **Lỗi tương quan.** Lập luận Condorcet (đa số đúng với xác suất cao khi mỗi
sample đúng độc lập với p > 0,5) **không áp dụng** vì các sample cùng model,
cùng prompt, cùng schema profile, cùng cách hiểu sai → cùng sai một kiểu (fan
trap, sai rule, sai cửa sổ ngày — 04 §2.6 đã liệt kê). Khi lỗi tương quan hoàn
toàn, vote 3/3 vẫn có thể sai 100% trong nhóm câu bẫy. Hệ quả: vote share chỉ đo
**ổn định nội bộ**, không đo đúng; nó phải đi kèm cổng độc lập (§2.1, 04 §2.4)
và map calibration học trên dữ liệu thật.
2. **Map vote → P(đúng) phải học, không đọc trực tiếp.** Trên train_cal, lập bảng
reliability của vote: với mỗi giá trị vote có thể (`1/3, 2/3, 3/3`, cộng trường
hợp có lỗi), tính accuracy thực tế của đáp án đa số. Bảng này — không phải vote
share — mới là thứ đưa vào quyết định. Demo §1.6 cho thấy vote 2/3 có thể map
tới 1,0 trong một mixture — và trong dữ liệu thật nó có thể map tới 0,4 nếu nhóm
2/3 chứa nhiều bẫy. **Không bao giờ viết `p = v` trong code.**
3. **Độ hạt thô của k nhỏ.** Với k = 3, vote share chỉ có 4 giá trị có nghĩa → ngưỡng
trên vote share chỉ có thể nằm giữa 4 bậc → tuning thô. Nếu ngân sách cho phép,
k = 5 cho 6 bậc và ước lượng vote ổn định hơn, nhưng chi phí sinh tăng ~67%.
Quyết định k phải đo bằng AURC/PA trên train_holdout, không chọn theo cảm tính.
Đa dạng nên đến từ **prompt/path khác nhau** (SQL vs Python, rulebook-trích vs
schema-thuần) hơn là tăng temperature mù (04 đã nêu; bổ sung: đo "đa dạng hiệu
dụng" = tỉ lệ cặp candidate cho output khác nhau trên train_cal — nếu tỉ lệ này
≈ 0 ở temperature 0,2 thì tăng temperature không giúp, phải đổi prompt).

```python
def vote_reliability_table(cal_records):
# cal_records: list of (vote_share v, majority_correct y) trên train_cal
table = {}
for v in distinct_votes(cal_records):
subset = [y for (vv, y) in cal_records if vv == v]
table[v] = mean(subset) if len(subset) >= 30 else None
# thiếu mẫu -> dùng calibrator toàn cục, không bịa số
return table
```

### 2.3. Tín hiệu (c): logit-based calibration — dùng đúng chỗ, không ép

Với bài toán sinh code, "logit" không phải là logit phân loại nhị phân đúng/sai. Ép
softmax trên vocab thành P(đúng) là sai về mặt khái niệm: softmax đo xác suất token
tiếp theo, không đo xác suất chương trình đúng. Chia ba loại tín hiệu logit, mỗi
loại có cách dùng khác nhau [INFERENCE]:

| Tín hiệu logit | Định nghĩa thực hành | Dùng làm gì | Không dùng làm gì |
|---|---|---|---|
| (c1) Mean logprob của chương trình sinh ra | `mean log P(token_i \| context)` trên toàn bộ code, lấy từ vLLM `logprobs` (cần bật `logprobs` khi generate; logprobs làm tăng output payload, đo trước khi bật mặc định) | Feature cho calibrator (fluency/proxy độ "tự nhiên" của code) | Đừng biến thành P(đúng) trực tiếp; code trôi chảy vẫn sai logic |
| (c2) Length-normalized logprob của đáp án ngắn | Khi pipeline sinh đáp án scalar dưới dạng chuỗi ngắn (số/ngày/chuỗi): `exp(mean logprob của chuỗi đáp án)` | Đầu vào cho temperature scaling nhị phân khi đáp án là chuỗi ngắn | Không áp cho đáp án table/list dài (logprob trung bình trên chuỗi dài không so sánh được giữa các độ dài) |
| (c3) Calibrator trên features (khuyến nghị chính) | Platt/isotonic trên vector features (§2.1–2.2), không phải trên logit thô | **Đây mới là "logit-based calibration" đúng nghĩa cho bài toán này**: logistic regression trên features cho ra logit của P(đúng), rồi temperature/Platt hiệu chỉnh logit đó | Đừng gọi (c1) là "confidence từ logit" trong báo cáo — nó là fluency, không phải confidence |

**Temperature scaling — công thức và cách fit** [INFERENCE — phương pháp chuẩn
theo Guo et al. 2017]. Cho bài toán nhị phân "đáp án đúng hay sai" với logit `m_i`
(từ calibrator (c3), hoặc từ (c2) khi áp được):
`p̂_i(T) = σ(m_i / T)`, `σ(x) = 1 / (1 + exp(−x))`, `T > 0`.
Fit T trên tập calibration bằng cách cực tiểu NLL:
`T* = argmin_{T>0} −Σ_i [ y_i·log p̂_i(T) + (1−y_i)·log(1 − p̂_i(T))]`.
Cách fit thực hành: tối ưu 1 chiều (grid search T ∈ [0,1, 10] bước nhân 1,05 rồi
refine quanh cực tiểu, hoặc L-BFGS nếu có scipy — stdlib thuần cũng làm được bằng
grid + golden-section). T* > 1 nghĩa là overconfident (cần làm mềm); T* < 1 nghĩa
là underconfident. Temperature scaling **giữ nguyên thứ tự xếp hạng** (đơn điệu
theo m_i) nên không đổi đáp án được chọn, chỉ đổi ngưỡng áp được — vì vậy nó không
thay thế việc chọn ngưỡng, nó làm cho ngưỡng 0,5 trở nên có nghĩa. **Và nó không
sửa được shift:** demo §1.6 cho thấy T* giảm ECE nhưng không về 0 dưới bias cộng.
Dưới shift, margin δ + evidence-gating mới là công cụ đúng.

**Platt scaling vs isotonic — chọn theo lượng dữ liệu** [INFERENCE]:
- Platt (logistic trên score/logit: `p = σ(a·s + b)`, fit a, b bằng NLL trên cal):
2 tham số, ổn định với cal nhỏ (≥ ~100 mẫu), giả định quan hệ sigmoid — phù hợp
khi cal ít hoặc cần map mượt.
- Isotonic (hàm bậc thang đơn điệu, fit bằng PAVA): không giả định dạng, cần nhiều
mẫu hơn (≥ ~200–500, và mỗi bậc đủ mẫu) — phù hợp khi cal lớn và quan hệ
score→accuracy không sigmoid (thường gặp với vote share bậc thang).
- Quy tắc: thử cả hai trên train_cal, chọn bằng NLL/Brier trên **LOBO-held-out**
(không phải trên chính train_cal — fit trên cal rồi đo trên cal sẽ thiên vị
isotonic vì nó linh hoạt hơn). Nếu chênh lệch < nhiễu thì chọn Platt (đơn giản
hơn, chuyển tốt hơn).

**Vì sao cấm fit trên public_test — ba lý do độc lập, lý do nào cũng đủ**
[INFERENCE]:

1. **Không có nhãn:** calibrator là học có giám sát (cần y = đúng/sai). Public test
không có `answers.jsonl` theo ghi nhận [CODE_INSPECTED] nên không fit được theo
đúng nghĩa; mọi cách "fit" trên public_test đều phải dùng pseudo-label (tự gán)
— tức là fit vào chính sai lầm của hệ thống.
2. **Ngay cả fit không giám sát trên input public_test cũng là test-set adaptation:**
ví dụ fit T sao cho phân phối score trên public_test "trông calibrated" (khớp
phân phối train) là dùng thông tin test để chỉnh hệ thống — vi phạm giao thức
(plans/datamate.md cấm dùng public để chỉnh ngưỡng [CODE_INSPECTED]), và không
chuyển sang private test (private có type mới, phân phối khác public).
3. **Sai mục tiêu:** mục tiêu là private test (có type mới), không phải public test.
Mọi tham số fit trên public đều tối ưu cho phân phối public — dưới shift, đó là
tối ưu sai phân phối. LOBO trên train (§3) là proxy đúng cho private, public
không phải.

### 2.4. Pseudocode tổng hợp: từ 3 tín hiệu → quyết định cuối

```python
# Đầu vào mỗi câu hỏi: candidates (SQL + Python), executor, profiler evidence, rulebook
# Đầu vào đã khoá từ train_cal: calibrator f, ngưỡng tau_khoa, hard gates
# KHÔNG dùng public_test ở bất kỳ bước nào.

def decide_question(question, business, locked):
# 1. Thực thi, chỉ output thành công + không rỗng mới vote (§2.1)
results = [execute(c) for c in candidates] # timeout riêng từng candidate
succ = [r for r in results if r.error is None and r.output is not EMPTY]
if not succ:
return Abstain(reason="no_successful_execution") # lỗi thực thi!= unanswerable

# 2. Hard gates TRƯỚC score (trượt là abstain, không cứu bằng score cao)
if not rule_assertions_pass(chosen_prelim, question, business.rulebook):
return Abstain(reason="rule_assertion_failed")
if not schema_evidence_complete(question, business): # thiếu bảng/cột/rule
return Unanswerable(reason="missing_evidence") # xem phân biệt ở 04 §5

# 3. Features (không phải điểm cộng cố định)
majority, m, s = majority_output(succ) # trên output ĐÃ CHUẨN HOÁ (§5)
f_cons = m / s
e_rate = s / len(candidates)
cross = cross_path_features(...) # agree: True/False/None (§2.1)
ev = evidence_coverage(question, business) # từ profiler, xác định
flu = mean_logprob(majority_program) # (c1), có thể None
feats = [f_cons, e_rate, s, cross_fraction_or_0.5_if_None, ev, flu_or_None]
# Lưu ý: cross = None (thiếu một đường) mã hoá thành giá trị trung lập + cờ missing,
# để calibrator học được "thiếu đường thứ hai" khác với "đường thứ hai mâu thuẫn".

# 4. Calibrated probability (học trên train_cal, §2.3)
p_hat = locked.calibrator.predict_proba(feats) # Platt hoặc isotonic, đã khoá
# Nếu calibrator không có (cal quá ít): fallback = vote reliability table (§2.2),
# nếu cả bảng cũng thiếu mẫu: fallback = abstain khi f_cons < 1.0 (thận trọng tối đa).

# 5. Quyết định theo ngưỡng đã khoá (0.5 + delta LOBO, §1.4)
if p_hat > locked.tau_khoa:
return Answer(value=majority, p_hat=p_hat, audit={...})
else:
return Abstain(reason="p_below_threshold", p_hat=p_hat)
```

**Điểm khác biệt cốt lõi so với score trọng số cố định của 04:** calibrator học
được **tương tác** (vd: `f_cons = 1.0` nhưng `cross = False` có thể map tới `p̂`
thấp hơn `f_cons = 0,67` nhưng `cross = True` — điều mà cộng tuyến tính không biểu
diễn được), học được **thiếu mẫu** (qua cờ missing và LCB), và cho ra xác suất có
nghĩa để so với 0,5 + δ. Trọng số cố định chỉ nên giữ làm baseline đối chứng trong
thí nghiệm (so sánh calibrator vs weighted-sum trên cùng holdout, chọn bằng PA —
không chọn bằng cảm tính).

### 2.5. Chi phí tín hiệu (không thể bỏ qua dưới trần 6 giờ) [INFERENCE]

Mỗi tín hiệu tốn ngân sách: k candidate tốn k lần sinh; second path tốn thêm sinh
+ thực thi; logprobs tốn payload. Quy tắc: **đo AURC/PA tăng thêm của từng tín hiệu
trên train_holdout rồi mới giữ.** Nếu second path chỉ tăng PA < nhiễu đo mà tốn
~40% thời gian, bỏ nó và dùng ngân sách đó tăng k hoặc tăng coverage. Thứ tự ưu
tiên đo: (1) consensus k=3 (rẻ nhất, đã có); (2) evidence features (gần như miễn
phí, từ profiler); (3) cross-path (đắt, đo riêng); (4) logprobs (đo riêng, chỉ bật
khi calibrator chứng minh nó cải thiện NLL/Brier). Đừng bật mọi tín hiệu mặc định
rồi mới đo — trần 6 giờ cho toàn bộ private test [CODE_INSPECTED] không cho phép
xa xỉ đó.

## 3. Giao thức tách validation nội bộ mô phỏng domain shift (LOBO)

### 3.1. Đơn vị tách là business, không phải câu hỏi [INFERENCE]

Sai lầm nghiêm trọng nhất khi tách validation cho DataMate là tách ngẫu nhiên theo
**câu hỏi**: các câu hỏi cùng một business chia sẻ cùng schema, cùng README, cùng
rulebook, cùng phân phối giá trị — câu hỏi holdout vẫn "thấy" business qua câu hỏi
train cùng business. Dưới private test (business hoàn toàn mới), sự rò rỉ này biến
mất, nên random-split holdout **đánh giá quá lạc quan một cách có hệ thống**. Đơn vị
tách đúng là **business** (toàn bộ câu hỏi + dữ liệu của một doanh nghiệp đi cùng
nhau), và khi có thể, là **business type** (toàn bộ các business cùng loại hình đi
cùng nhau — vì các business cùng type chia sẻ quy ước schema/rule tương tự).
Chênh lệch `PA_random_holdout − PA_LOBO` chính là ước lượng thành phần sai số
giữa-type — báo cáo nó như một số, không chỉ nói "LOBO thấp hơn".

### 3.2. Giao thức LOBO lồng nhau — Variant A (nghiêm ngặt) và Variant B (thực dụng)

Ký hiệu: tập type `T = {T_1, …, T_m}` (type = loại hình doanh nghiệp; nếu dữ liệu
không có cột type tường minh thì xem §3.4 về pseudo-type). Mỗi type có các business
và câu hỏi của nó.

**Variant A — tune trên 1 type held-out, verify trên 1 type held-out khác (chưa từng
tune):**

```
for mỗi type verify v in T:
for mỗi type calibration c in T, c!= v:
fit_set = T \ {v, c} # viết helper/prompt trên các type còn lại
cal_set = c # học map calibration + ngưỡng tau trên type c DUY NHẤT
ver_set = v # đo PA/coverage/ECE MỘT LẦN, không sửa gì từ kết quả này
ghi: PA(v | tau_tuned_on_c), tau_c, ECE(v), coverage(v)
# Sau vòng lặp: với mỗi v, có (m-1) số PA (mỗi số ứng với một c khác nhau)
```

Báo cáo cho mỗi v: PA trung bình, PA min, PA max qua các c — **độ phân tán qua c
chính là độ bất định của ngưỡng khi chuyển type** (nếu tau tune trên type này cho
PA tốt trên v nhưng tune trên type khác cho PA tệ trên v, thì ngưỡng không chuyển
tốt — kết luận này quan trọng hơn PA trung bình). Ngưỡng triển khai cuối không lấy
từ một cặp (c, v) nào: lấy **median của các tau_c** qua các c (robust trước type
dị biệt), cộng biên δ LOBO (§1.4), rồi khoá.

**Variant B — tune trên pooled các type còn lại, verify trên type bị giấu (chuẩn
nested LOBO):**

```
for mỗi type verify v in T:
fit_set = T \ {v} # viết helper/prompt
cal_set = T \ {v} # học map + ngưỡng trên POOLED các type còn lại
ver_set = v # đo một lần
```

Variant B vẫn sạch cho v (ngưỡng chưa từng thấy v), nhưng ngưỡng được học trên
nhiều type nên ổn định hơn A. **Khuyến nghị:** chạy B làm giao thức chính khi m < 4
(xem §3.3); chạy A làm chẩn đoán chuyển ngưỡng khi m ≥ 4 (A đo trực tiếp "ngưỡng
học trên đúng 1 type lạ chuyển sang type lạ khác tốt tới đâu" — câu hỏi sát private
test nhất, vì private test cũng là type lạ đơn lẻ, không phải pooled). Hai variant
trả lời hai câu hỏi khác nhau, không thay thế nhau: B trả lời "hệ thống tốt tới đâu
trên type mới khi ngưỡng học từ nhiều type cũ", A trả lời "ngưỡng học từ một type cũ
chuyển sang type mới tệ tới đâu".

**Quy tắc vàng áp cho cả hai variant (đã có trong `plans/datamate.md`
[CODE_INSPECTED], nhắc lại vì hay bị phá vỡ):** không đo trên dữ liệu đã dùng để
viết helper hoặc fine-tune — nếu một helper/rule được viết sau khi nhìn thấy một
câu train cụ thể, câu đó (và business/type chứa nó) không còn là holdout sạch cho
helper đó nữa. Trong LOBO, điều này có nghĩa: helper viết từ type X thì type X phải
bị loại khỏi cả fit lẫn cal lẫn ver của vòng đo đó — không chỉ loại khỏi ver.

### 3.3. Khi số lượng business type ít — điều chỉnh cụ thể

Số type danh nghĩa ≥ 8 [CODE_INSPECTED], nhưng số type **thực tế từng split và số
câu hỏi từng type chưa verify** — vì vậy mọi quy tắc dưới đây đều có nhánh "nếu đếm
thật khác":

- **m ≥ 6 (đủ):** chạy cả A và B đầy đủ. Báo cáo per-type (§3.5).
- **m = 4–5:** chạy B đầy đủ; A chạy rút gọn (mỗi v chỉ tune trên 2 type c đại diện:
một type gần v nhất và một type xa v nhất theo schema fingerprint — đo "chuyển
gần" vs "chuyển xa" thay vì đủ m−1 cặp).
- **m = 3:** chỉ chạy B (mỗi v: tune pooled trên 2 type còn lại). A suy biến thành 2
cặp/v, phương sai quá lớn để kết luận — báo rõ là "không đủ type để đo chuyển
ngưỡng đơn lẻ".
- **m = 2:** LOBO suy biến: mỗi v chỉ còn 1 type để tune/fit. Lúc này (i) không tách
tune/verify theo type được nữa — tune trên type còn lại và verify trên type bị
giấu, nhưng ghi rõ ngưỡng chỉ học từ 1 type nên độ bất định rất lớn; (ii) bổ sung
**split theo business trong type** (leave-one-business-out bên trong mỗi type) làm
phép đo thứ cấp; (iii) tăng biên δ (§1.4) lên mức thận trọng (ví dụ: δ lấy theo
worst-case thay vì mean) vì không đo được phân tán giữa các type.
- **m = 1 (chỉ một type trong train):** LOBO theo type không thực hiện được.
Fallback: leave-one-business-out + **tổng hợp type giả** (tạo business tổng hợp
bằng cách đổi tên bảng/cột, đổi đơn vị, đổi rulebook phrasing trên dữ liệu train —
augmentation có kiểm soát) để mô phỏng shift. Ghi rõ đây là mô phỏng yếu, không
thay thế LOBO thật, và δ phải lấy thận trọng nhất.
- **Type ít câu hỏi:** nếu một type có < 30 câu hỏi, PA trên type đó có phương sai
lớn — báo kèm khoảng tin cậy Wilson cho accuracy và không kết luận "type này tệ"
từ chênh lệch < nhiễu. Gộp type ít câu vào báo cáo chỉ khi đã báo riêng trước
(§3.5).

### 3.4. Business type: không có field tường minh — LOBO chạy nhánh pseudo-type

Đã kiểm kê dữ liệu thật ngày 2026-10-28 [LOCALLY_VERIFIED]: README từng business
(kiểm tra mẫu biz_103/biz_104, và grep toàn bộ README train) **không có field type
tường minh** — README mô tả file/cột/quy ước (vd "File Excel xuất từ phần mềm bán
hàng", "Ngày dạng dd/mm/yyyy", bảng quy đổi đơn vị), và gợi ý loại hình chỉ nằm
trong văn xuôi (vd "đơn ăn tại quán", "Bàn"). Vì vậy **nhánh pseudo-type dưới đây
là nhánh vận hành**, không phải nhánh dự phòng. Nhánh 1 chỉ còn ý nghĩa nếu metadata
nào khác ngoài README (chưa thấy) chứa type — và khi đó phải verify lại trước khi đổi nhánh.

- **Nhánh 1 (nếu có metadata type ở nơi khác):** dùng type từ metadata đó.
- **Nhánh 2 (vận hành — pseudo-type):** pseudo-type từ **schema fingerprint**: vector đặc trưng
gồm tên bảng, tập tên cột (chuẩn hoá), kiểu dữ liệu chủ đạo, và từ khoá README —
gom cụm (vd: Jaccard trên tập tên cột + TF-IDF trên README, hierarchical
clustering, số cụm chọn bằng silhouette hoặc đặt bằng số type danh nghĩa).
Pseudo-type là **proxy có nhiễu**: hai business cùng pseudo-type có thể khác type
thật và ngược lại — vì vậy báo cáo LOBO trên pseudo-type phải ghi rõ "pseudo-type,
chưa phải type thật" và độ nhạy của kết quả theo cách gom cụm (thử 2 cách gom
khác nhau, nếu kết luận đổi thì kết luận yếu). **Không bao giờ dùng nhãn
pseudo-type để tune ngưỡng triển khai mà không verify bằng metadata thật.**

### 3.5. Cách báo cáo — per-type riêng, không gộp mù

Mẫu bảng bắt buộc cho mỗi thí nghiệm LOBO (mỗi hàng là một type verify v):

```
| verify type | n_câu | tau_dùng | coverage | acc_trên_câu_trả_lời | PA | ECE | signed_gap (conf-acc) | LOBO_gap (PA_random - PA_LOBO) |
```

Và các số tổng hợp phải báo kèm, không thay thế bảng trên:

- **PA trung bình** qua các type (có trọng số theo số câu và không trọng số — báo
cả hai, vì chúng khác nhau khi type ít câu nhưng khó).
- **PA tệ nhất (min qua các type)** — đây mới là headline về robustness: private
test có thể chính là type khó đó. Một hệ thống PA trung bình 0,30 nhưng min −0,05
là hệ thống sẽ thua nếu private rơi vào type khó; báo cáo chỉ mean sẽ giấu điều này.
- **Độ phân tán ngưỡng:** std/range của tau_c qua các c (Variant A) — ngưỡng càng
phân tán thì càng cần δ lớn.
- **Độ phân tán ECE/signed gap:** type nào overconfident nhất (signed gap dương lớn
nhất) — đó là type cần δ riêng hoặc cần evidence-gating mạnh hơn.
- **So sánh với baseline random-split** trên cùng hệ thống: `PA_random_holdout` vs
`PA_LOBO` (mean và min). Chênh lệch dương lớn = bằng chứng định lượng rằng random
split lạc quan — dùng số này để biện minh cho việc dùng LOBO thay vì random split
trong mọi quyết định ngưỡng sau này.

**Cấm:** báo một con PA gộp duy nhất cho LOBO mà không có bảng per-type; chọn ngưỡng
từ kết quả LOBO rồi báo lại PA LOBO đó như kết quả độc lập (ngưỡng đã thấy các type
verify qua vòng tune — phải khoá ngưỡng từ một vòng, đo ở vòng khác, hoặc báo rõ là
"LOBO sau khi đã dùng LOBO để chọn ngưỡng" thì không còn là đo độc lập nữa).

## 4. Cơ chế abstain ở cấp độ code — 5 solution đã đọc nói gì

**Kết luận trước: không solution nào trong 5 cái có cơ chế abstain thật theo nghĩa
Penalized Accuracy (+1 đúng / 0 abstain / −1 sai).** Tất cả đều "luôn nộp 1 đáp án".
Bảng dưới đây là code đã đọc, không phải tóm tắt paper.

### 4.1. DABstep baseline — Space `adyen/DABstep`, revision `d4431c2e4a695cbe43c33aab2adaa304a37ae64a`

- Quyết định "Not Applicable" chỉ nằm ở 2 chỗ dạng text, không có code đo lường
[CODE_INSPECTED: `baseline/prompts.py`, `reasoning_llm_system_prompt`]: *"IF AND
ONLY IF you have exhausted all possibles solution plans you can come up with and
still can not find a valid answer, then provide 'Not Applicable' as a final
answer."* Không có đếm số plan, không ngưỡng, không biến trạng thái "đã exhausted".
- **Không có post-check khi ghi answers:** `run_single_task()` làm
`answer = agent.run(prompt)` rồi ghi nguyên văn vào `answers.jsonl` (qua
`append_answer()` chỉ `json.dumps` + append, có lock) — không kiểm tra
`answer == "Not Applicable"`, không map thành abstain, không ghi field confidence
[CODE_INSPECTED: `baseline/run.py:run_single_task`, `baseline/utils.py:append_answer`].
- **Scorer cũng không có trường hợp đặc biệt cho "Not Applicable":**
`question_scorer()` chỉ có 3 nhánh — số (tolerance `isclose` rel/abs `1e-4`), list
(tách `[,;]`, sort, so sánh đệ quy), chuỗi (`compare_strings`: xoá
punctuation/whitespace rồi so sánh, subset nếu một bên 1 từ, ngược lại
`SequenceMatcher.ratio() > 0.95`) [CODE_INSPECTED:
`dabstep_benchmark/evaluation/scorer.py:question_scorer`]. Hệ quả: "Not Applicable"
chỉ được điểm khi ground truth cũng là chuỗi đó; còn lại là đáp án sai bình thường.
DABstep vốn chỉ chấm 1/0, không có −1, nên "Not Applicable" ở đây **không tương
đương** abstain 0 điểm của PA [INFERENCE].
- **Điểm ngược với abstain, quan trọng nhất — hết max-steps thì ép đoán:** baseline
pin `smolagents==1.3.0` (`--max-steps` default 10). Trong smolagents v1.3.0,
`MultiStepAgent.direct_run()`: nếu `final_answer is None` và đủ `max_steps`, nó tạo
`ActionStep(error=AgentMaxStepsError(...))` rồi gọi `provide_final_answer(task)` —
**một lần gọi LLM thêm** với system prompt cố định *"An agent tried to answer a
user query but it got stuck and failed to do so…"* + toàn bộ memory; prompt này
**không nhắc lại** quy tắc "Not Applicable", nên đáp án ép buộc không có lý do gì
để tự thành abstain [CODE_INSPECTED: `huggingface/smolagents@v1.3.0`,
`src/smolagents/agents.py`]. Ngoại lệ duy nhất: `run_single_task()` không có
try/except quanh `agent.run()` — lỗi ngoài vòng step sẽ raise ở `f.result()` trong
`main()` và task đó không được ghi entry nào (vắng entry do crash, không phải
abstain có chủ đích).
- **Chỉ Python/pandas, không SQL** [CODE_INSPECTED: `baseline/utils.py`,
`baseline/constants.py:ADDITIONAL_AUTHORIZED_IMPORTS` — không có `sqlite3`,
`sqlalchemy` hay module SQL nào; `run.py` không chứa chuỗi `sql`]. Enforcement
chỉ-đọc duy nhất: `read_only_open()` ghi đè `open`, raise nếu mode khác `'r'`.
**Self-check: KHÔNG CÓ ở tầng baseline** — mỗi task chạy đúng một lần, không vote,
không lặp lại, không so sánh nhiều ứng viên, không field confidence. Feedback duy
nhất nằm bên trong smolagents: output/error của code Python thành observation cho
step sau.
- **Vị trí gắn ngưỡng duy nhất sạch** [INFERENCE]: trong `run_single_task()`, ngay
sau `answer = agent.run(prompt)` và trước khi tạo `answer_dict`/gọi
`append_answer()` — tại đây kiểm tra token abstain và/hoặc gắn bước tự chấm rồi
mới ghi. Không gắn vào `evaluate()`/`question_scorer()` được, vì đó là phía chấm
sau khi đáp án đã nộp và scorer hiện tại không phân biệt abstain với sai.
- **License mâu thuẫn, phải ghi rõ:** file `LICENSE` ở root Space ghi benchmark ©
2025 được cấp phép **CC BY 4.0**; ngược lại `setup.py` của package
`dabstep_benchmark` khai classifier **MIT License**. License áp cho *code baseline*
thì **UNVERIFIED nếu chỉ dựa vào LICENSE** — cần xác nhận thêm trước khi tái sử
dụng code nguyên văn [CODE_INSPECTED]. (Riêng smolagents: header `agents.py`
v1.3.0 ghi Apache 2.0 — đó là license của dependency, không phải của baseline.)

### 4.2. ReFoRCE — `Snowflake-Labs/ReFoRCE`, branch `o3`, commit `d2658991882f06fa0658bb7782ee9ea515fbb10b`, Apache 2.0

Trong `methods/ReFoRCE/agent.py` tìm trực tiếp hai chuỗi `unanswerable` và
`confidence`: **0 kết quả**; toàn bộ `methods/ReFoRCE/prompt.py` (class `Prompts`)
cũng không có câu nào hướng dẫn model trả "không trả lời được" [CODE_INSPECTED].

**`vote_result()` — công thức hoà chính xác** [CODE_INSPECTED:
`methods/ReFoRCE/agent.py:REFORCE.vote_result`]: với mỗi ứng viên, `same_ans` chỉ
đếm các file CSV *khác* mà `is_valid_result(...)` đúng **và**
`compare_pandas_table(v_df, c_df, ignore_order=True)` đúng **và**
`v_df.shape == c_df.shape`; `filter_bijection_like_dict()` lọc tiếp chỉ giữ quan hệ
bằng nhau hai chiều. Ứng viên đơn độc không vào `result` — chỉ nằm trong
`result_all` với giá trị 0. Công thức hoà: `max_vote = max(vote_counts)`;
`num_with_max_vote = vote_counts.count(max_vote)`; `has_tie = num_with_max_vote >
(max_vote + 1)`. Vì mỗi nhóm có kích thước = `max_vote + 1` (số phiếu "người khác
giống mình" + chính mình), nên `num_with_max_vote == max_vote + 1` nghĩa là chỉ một
nhóm đạt max → không hoà; lớn hơn → ≥2 nhóm cùng max → hoà.

**Khi hoà, hàm trả về cái gì:** `vote_result()` luôn trả `None` ngầm. Hoà +
`--model_vote` → gọi `model_vote()` (chỉ các ứng viên đạt max, tối đa 3 lần ép về
tên file `.sql` trong block plaintext; chỉ ghi `complete_csv_save_path` /
`complete_sql_save_path` khi SQL được chọn chạy lại thành công, thất bại thì in
"Empty" và không ghi gì); hoà + không `--model_vote` và không
`--random_vote_for_tie` → chỉ in log rồi return, **KHÔNG copy gì sang `result.csv` /
`result.sql`**; hoà + `--random_vote_for_tie` → **không bốc ngẫu nhiên thật**: copy
`first_key` — key đầu tiên sau sort giảm dần (thứ tự chèn giữ nguyên khi bằng nhau).
**Khi `result` rỗng** (không cặp nào bằng nhau): nếu `--model_vote` → model vote
trên `result_all`; nếu `--final_choose` → copy `all_values[0]` (file vote **đầu
tiên**, không phải file "tốt nhất"); nếu không → in "Empty, return".

**`run.py` ghi gì ra submission khi hoà/không có kết quả:** `process_sql_data()` —
nếu `--do_vote` thì chạy `num_votes` luồng `execute()`; nếu `"result.sql" not in
os.listdir(search_directory)` và có file `.sql` thì gọi `vote_result()`; nếu không
thì in `"Empty"` [CODE_INSPECTED: `methods/ReFoRCE/run.py:process_sql_data`]. Tức
`run.py` **không tự tạo submission entry nào** khi vote hoà mà không copy — thư mục
task đó đơn giản không có `result.sql`/`result.csv`. Tệ hơn,
`get_metadata.py:save_to_jsonl()` ghi một dòng cho **mọi** thư mục con với
`"answer_or_path": f"{name}.csv"` bất kể file có tồn tại hay không; `get_csv_from_dic()`
chỉ copy khi file tồn tại — kết quả là metadata trỏ tới file CSV không tồn tại
(dangling entry), không phải abstain sạch [CODE_INSPECTED].

**Điểm mấu chốt — pipeline đầy đủ cố tình không dừng ở hoà:**
`methods/ReFoRCE/scripts/run_main.sh` chạy 4 bước nối tiếp trên cùng `OUTPUT_PATH`:
Step 1 self-refine + vote (không `--random_vote_for_tie`, không `--model_vote`) →
task hoà còn trống; Step 2 self-refine + vote + column exploration +
`--rerun --overwrite_unfinished` → chạy lại task chưa xong; Step 3 `--do_vote
--random_vote_for_tie` → lấp đầy task còn hoà bằng `first_key`; Step 4 `--do_vote
--random_vote_for_tie --final_choose` → lấp nốt bằng file vote đầu tiên
[CODE_INSPECTED]. Vì vậy: chỉ copy Step 1 thì hoà ≈ abstain tạm thời; copy cả
`run_main.sh` thì **cuối cùng mọi task đều bị ép ra đáp án**. Muốn tie = abstain cho
DataMate thì phải dừng sau bước vote, **không chạy Step 3/4**, và tự ghi token
abstain thay vì để trống file.

**Khi exploration thất bại hoàn toàn và khi self_refine hết vòng** [CODE_INSPECTED:
`agent.py:exploration`, `run.py:execute`, `agent.py:self_refine`]: exploration yêu
cầu ≥3 SQL thăm dò (`len(response_pre) < 3` → retry, `max_try = 3` từ `__init__`,
cùng `csv_max_len = 500`); nếu `sql_count == 0` (không SQL thăm dò nào cho kết quả
dạng chuỗi hợp lệ): in `"Inadequate preparation, break."`, đặt `max_try = 0`, break,
trả `pre_info = ''` (rỗng). Và `run.py:execute()` — nếu `--do_column_exploration`
bật và `max_try <= 0` thì in `"Inadequate preparation, skip"` và **return trước
self_refine/gen** → nhánh vote này không có file kết quả nào. Trong
`execute_sqls()`: nếu 3 lần ghi lỗi liên tiếp thì return danh sách một phần ngay;
vòng lặp cũng dừng khi `len(result_dic_list) > 10` hoặc `len(chat_session_pre.messages)
> 20`. `self_refine()` không trả giá trị nào; hết `max_iter` (default 5 trong
`run.py`): nếu `itercount == args.max_iter and not args.save_all_results` → **xoá
`csv_save_path` nếu tồn tại**, log "Max Iter, remove file", không ghi SQL. Lỗi sinh
SQL (response không phải list hoặc rỗng sau `max_try = 3`): xoá CSV nếu có, in
"Error when generating final SQL.", break. Nhánh `gen()` (không self-refinement):
chỉ sinh đúng 1 SQL, chạy 1 lần; nếu thành công thì ghi SQL, ngược lại không ghi gì.
**Quirk cần đối soát lại bằng chạy thử trước khi port (ghi rõ, không dùng làm tiền
đề thiết kế chính):** trong đoạn text đọc được của `execute_sqls()`, nhánh thành
công ngay lần đầu có `result_dic_list.append(result_dic)`, còn nhánh "sửa thành
công" **không thấy dòng append** — chỉ gán `result_dic['sql']`/`result_dic['res']`,
cập nhật chat message, log "Successfully corrected", rồi quay lại vòng `while`. Nếu
đúng vậy thì SQL thăm dò phải sửa mới chạy được sẽ **không đóng góp vào `pre_info`**,
và exploration có thể kết luận `sql_count == 0` dù thực ra đã sửa được SQL
[CODE_INSPECTED với caveat — cần chạy thử để xác nhận].

**Sinh code, self-check, confidence** [CODE_INSPECTED]: **chỉ SQL, không sinh
Python; không có cross-check SQL-vs-Python.** Model chỉ được yêu cầu trả SQL trong
block ```sql; mọi lời gọi trong `agent.py` đều dùng `"sql"` (exploration,
self-correct, self-refine, gen), trừ `format_answer` dùng `"csv"` và `model_vote`
dùng `"plaintext"` cho tên file. Engine: `sql.py:SqlEnv.execute_sql_api()` rẽ nhánh
theo `api` — `sqlite`/`snowflake`/`bigquery`; SQLite: `start_db_sqlite()` mở
`f"file:{sqlite_path}?mode=ro"` (chỉ đọc), `execute_sqlite_with_timeout()` dùng
`func_timeout(timeout=300)`; thành công có rows + `save_path` → ghi CSV và trả `0`;
thành công có rows nhưng không `save_path` → trả chuỗi CSV đã `hard_cut`; không có
rows → `"No data found for the specified query.\n"`; lỗi → `"##ERROR##..."`, rồi
`execute_sql_api()` chuyển thành dict `{"status": "error",...}`. Pandas chỉ xuất
hiện ở phía host để đọc/so sánh CSV, **không phải code do model sinh**:
`utils.py:compare_pandas_table(pred, gold, ignore_order=True, tolerance=0.001)` so
sánh theo từng cột chuyển vị, và `vote_result()` yêu cầu thêm `v_df.shape ==
c_df.shape`. "Cross-check" duy nhất của ReFoRCE là **SQL-result vs SQL-result**,
không có hai engine khác nhau kiểm chứng nhau. Self-consistency thật chỉ ở tầng
vote; tầng self_refine chỉ lặp tuần tự và chỉ so **cột đầu tiên**. Vote:
`--do_vote` là flag (default tắt), `--num_votes` default 3 trong `run.py` nhưng
`run_main.sh` đặt `NUM_VOTES=8`; `--temperature` default 1.
**Confidence/threshold: KHÔNG CÓ.** Không biến/hàm/field nào tên confidence/score
trong `agent.py` (tìm `confidence`: 0 kết quả). Proxy gần nhất, **hiện không được
tính hay xuất ra**: vote share suy ra từ `vote_result()` — share nhóm thắng =
`(max_vote + 1) / len(all_values)` (3 votes: đồng thuận hoàn toàn → 1.0; 2+1 → ≈
0.67; hoà 1+1+1 thì không có `result` nên không có share theo công thức này). Bộ lọc
`utils.py:is_valid_result()` (False nếu có giá trị nested chứa `\n` trong ô, hoặc —
khi không bật CE — nếu có cột toàn "0"/rỗng) là bộ lọc chất lượng, không phải
ngưỡng confidence, và chỉ loại ứng viên khỏi đếm vote chứ không tạo abstain.

**Bẫy nếu port nguyên code:** `chat.py:BaseChat.get_model_response()` — nếu sau 3
lần thử vẫn không trích được code block đúng format thì gọi `sys.exit(0)`: toàn bộ
tiến trình thoát với mã 0 (trông như thành công) thay vì trả lỗi. Đừng copy pattern
này; phải trả lỗi/abstain tường minh [CODE_INSPECTED]. Quirk thêm: nhánh
`if args.save_all_results` trong `self_refine()` dùng biến `save_path` không tồn
tại trong hàm (tham số là `csv_save_path`) — bật `--save_all_results` cùng đường
consistency-thành-công sẽ gặp lỗi biến chưa gán [CODE_INSPECTED].

### 4.3. CHESS — `ShayanTalaei/CHESS`, commit `3d6e835f858d26885d21d4bc0215aeecf855efbe`, Apache 2.0

**KHÔNG CÓ nhánh abstain/unanswerable nào.** Hành vi khi không trả lời được, theo 3
nhánh suy biến trong `Evaluate._run` [CODE_INSPECTED:
`src/workflow/agents/unit_tester/tool_kit/evaluate.py:Evaluate._run`]:
- **0 candidate** → chèn chuỗi giả `"SELECT * FROM table_name"` (lưu ý: đây là `str`
thuần, không phải `SQLMetaInfo`), `scores = [0]`.
- **1 candidate** → trả candidate đó, `scores = [1]`, **không kiểm tra execution status**.
- **0 unit test** → trả candidate đầu tiên, `scores = [1]`, cũng không kiểm tra gì.

Hệ quả kiểu dữ liệu ở nhánh 0 candidate [INFERENCE từ code đã đọc]: các bước sau
đều truy cập `.SQL` (`Evaluate._get_updates`, `ExecutionAccuracy._run`). Một `str`
không có `.SQL` nên sẽ rơi vào nhánh exception của `ExecutionAccuracy` và cho ra
`PREDICTED_SQL = "--error--"`. Tức placeholder điểm 0 **không được chặn, cũng không
biến thành abstain** — nó biến thành một chuỗi không phải SQL ở đầu ra cuối.
Ngoài ra, `GenerateUnitTest._run` tự tạo ra nhánh 0-test rất dễ gặp: nếu
`len(target) <= 1` **hoặc** chỉ có 1 execution cluster thì `unit_tests = []` rồi
return [CODE_INSPECTED: `src/workflow/agents/unit_tester/tool_kit/generate_unit_test.py`].
Nghĩa là các candidate **đồng thuận hoàn toàn** (kể cả đồng thuận trên kết quả
rỗng/lỗi) sẽ **bỏ qua chấm unit test** và đi thẳng vào nhánh điểm 1 giả tạo ở trên.

**Điểm quan trọng nhất, sửa lại tóm tắt round 3:** enum có 6 giá trị, nhưng **chỉ 3
trạng thái còn sống trong code chạy** — `ZERO_COUNT_RESULT` và `ALL_NONE_RESULT`
đã bị comment out. Trong `get_execution_status` [CODE_INSPECTED:
`src/database_utils/execution.py:get_execution_status`]: nếu `execution_result`
là `None` hoặc `[]` thì trả `EMPTY_RESULT`; nếu rỗng ban đầu thì hàm tự chạy lại
SQL; timeout hoặc exception → `SYNTACTICALLY_INCORRECT`; còn lại →
`SYNTACTICALLY_CORRECT`. Và `NONE_RESULT` cũng không còn nhánh nào trả về.
**`Revise` KHÔNG phân biệt EMPTY vs ZERO_COUNT vs ALL_NONE** — vì 2 trạng thái sau
không bao giờ xảy ra. Cả `Revise._run` và `Revise.need_to_fix` dùng đúng một điều
kiện nhị phân [CODE_INSPECTED:
`src/workflow/agents/candidate_generator/tool_kit/revise.py`]:
`if execution_status!= ExecutionStatus.SYNTACTICALLY_CORRECT: SQL_meta_info.need_fixing
= True`. Bảng hành vi thực tế:

| Kết quả thực thi | Trạng thái thật | `need_fixing`? |
|---|---|---|
| Lỗi cú pháp / timeout / exception | `SYNTACTICALLY_INCORRECT` | Có |
| Rỗng `[]` / `None` | `EMPTY_RESULT` | Có |
| `COUNT` ra `(0,)` | `SYNTACTICALLY_CORRECT` (nhánh ZERO_COUNT đã comment) | **Không — được coi là đúng** |
| Toàn NULL, ví dụ `[(None, None)]` | `SYNTACTICALLY_CORRECT` (nhánh ALL_NONE đã comment) | **Không — được coi là đúng** |
| Có dòng dữ liệu bất kỳ | `SYNTACTICALLY_CORRECT` | Không |

Khi sửa, `Revise._run` đưa `get_formatted_execution_result()` (chỉ là
`{"execution_result":...}`) vào prompt cùng schema/câu hỏi/hint, rồi: nếu bản sửa
không chứa `"SELECT"` thì giữ nguyên SQL cũ; nếu LLM trả về ít bản sửa hơn số
candidate cần sửa thì các candidate còn lại cũng giữ nguyên qua nhánh exception
[CODE_INSPECTED]. Không có bước nào kiểm tra bản sửa có tốt hơn bản gốc không.
**Schema Selector không tham gia xử lý kết quả thực thi:** trong config, selector
chỉ có `filter_column / select_tables / select_columns` chạy bằng LLM, không có
bước execute nào [CODE_INSPECTED: `run/configs/CHESS_IR_SS_CG.yaml`].

**Khi Unit Tester chọn xong, main nộp candidate đó ra sao? Placeholder điểm 0 có bị
chặn không?** `main()` chỉ làm: parse args → load dataset → `RunManager.initialize_tasks`
→ `run_tasks` → `generate_sql_files` [CODE_INSPECTED: `src/main.py:main`]. Đối số
`--pick_final_sql` tồn tại nhưng không được dùng ở đâu trong `main`. Đường nộp thực
tế đi qua 2 chặng khác: (1) Node `evaluation` cuối graph (`ExecutionAccuracy`,
luôn được thêm sau agent cuối trong `team_builder.build()`): với mỗi key trong
`SQL_meta_infos`, nó chỉ lấy **phần tử đầu tiên** `state.SQL_meta_infos[key][0].SQL`
rồi so với gold bằng `compare_sqls` [CODE_INSPECTED:
`src/workflow/team_builder.py`, `src/workflow/agents/evaluation.py`]. Sau đó chọn
`final_SQL` bằng vòng lặp ghi đè liên tục — **kết quả là key cuối cùng thỏa điều
kiện**, không phải candidate tốt nhất theo UT. Chặng này **cần gold SQL** nên ở
DataMate (private test không nhãn) nó không thể chạy nguyên dạng — đây là bước đánh
giá BIRD, không phải bước chọn bài nộp cho môi trường không gold [INFERENCE]. (2)
`RunManager.task_done` ghi bài nộp: chỉ khi step có `"final_SQL"` thì gọi
`update_final_predictions(question_id, step["final_SQL"]["PREDICTED_SQL"], db_id)`
[CODE_INSPECTED: `src/runner/run_manager.py`]. Nếu không có step `final_SQL`, bài
nộp giữ nguyên giá trị khởi tạo từ `initialize_tasks` là `0`.
**Kết luận: không có chặn placeholder.** Nhánh 0-candidate không bị chặn ở
`Evaluate`, và ở `ExecutionAccuracy` nó còn có nguy cơ thành `"--error--"`.
`RunManager.pick_final_sql` tồn tại nhưng **chết trong main path** (không được gọi),
và bản thân nó cũng đáng ngờ: nó đọc `step["SQL"]` cho các step revise trong khi
`Revise._get_updates` chỉ trả `original_SQL_id / refined_SQL_id / candidates`,
không có key `"SQL"` [CODE_INSPECTED] — [INFERENCE] đây là code chết/không đồng bộ
với `_get_updates` hiện tại, không nên dựa vào.

**Sinh code, self-check, confidence** [CODE_INSPECTED]: **chỉ SQL, không sinh
Python.** Toàn bộ output là chuỗi SQL qua parser (trích `<FINAL_ANSWER>` / markdown
```sql). Engine thực thi: SQLite duy nhất (`sqlite3.connect(db_path, timeout=60)`,
chạy trong thread với `timeout` mặc định 60 giây); `DatabaseManager` ghép đường dẫn
dạng `<db_mode>_databases/<db_id>/<db_id>.sqlite`. Không có đọc Excel/CSV trực tiếp
— muốn dùng cho DataMate phải convert sang SQLite trước. Số lượng sample: config
`CHESS_IR_SS_CG.yaml` (không UT): **1 template `generate_candidate_one`,
`sampling_count: 1`, temperature 0.01** → 1 candidate ban đầu; config
`CHESS_IR_CG_UT.yaml` (có UT): **2 template × `sampling_count: 10`, temperature
0.5** → 20 candidate; UT config: `unit_test_count: 20, sampling_count: 1`,
temperature 0.8 cho sinh test. **`max_fixing`: KHÔNG có giá trị trong config nào đã
đọc, và cũng không được khởi tạo trong `Revise.__init__`.** `need_to_fix()` đọc
`self.fixing` / `self.max_fixing`, nhưng `__init__` chỉ set 3 trường
template/engine/parser, và trong các file đã đọc không thấy lời gọi `need_to_fix`
nào — graph là tuyến tính IR → SS → CG → UT → evaluation, không có conditional
edge nào dùng nó. [INFERENCE] Trong commit này `need_to_fix` thực chất là code chết
/ di sản: giới hạn vòng lặp thật sự là `Agent.workout` với `for i in range(10)`
(tối đa 10 lượt LLM chọn tool, dừng khi response chứa `"DONE"`) [CODE_INSPECTED:
`src/workflow/agents/agent.py:Agent.workout`]. **Không được trích "max_fixing = N"
cho CHESS ở commit này — con số đó không tồn tại trong code/config đã kiểm chứng.**
(Tóm tắt round 3 nói "dừng khi hết max_fixing" cần hiệu chỉnh theo điểm này. Kết
luận "code chết" là [INFERENCE] trên phạm vi file đã đọc — cần 1 lần grep toàn repo
cho `need_to_fix|fixing|max_fixing` để khẳng định tuyệt đối.)
**Clustering KHÔNG phải majority vote trong bước chọn.**
`execution_based_clustering` gom candidate theo key `repr(execution_result)` (giữ
nguyên thứ tự dòng — khác thứ tự là khác cluster; candidate nào truy cập
execution_result bị exception thì bị `continue` bỏ khỏi cluster) [CODE_INSPECTED:
`evaluate.py:Evaluate.execution_based_clustering`].
**LLM scoring theo unit test, cộng điểm thô, không chuẩn hoá.** Mỗi unit test là 1
LLM call với toàn bộ candidate + kết quả thực thi (cắt tối đa 20 dòng trong
`_format_sql_query_result`); parser cho mỗi candidate 1 nếu dòng chứa `"passed"`, 0
nếu không [CODE_INSPECTED: `src/llm/parsers.py:UnitTestEvaluationOutput.parse`].
`Evaluate._run` cộng dọc ma trận — **không chia cho số test**, nên điểm tuyệt đối
chỉ có nghĩa khi so trong cùng 1 câu hỏi với cùng số test thực tế (số test thực tế
= số test LLM trả về + 1 hard-coded test luôn được append trong
`GenerateUnitTest._run`). `test_case_filtering_based_on_inter_cluster_variance` đã
bị comment out trong `_run`, nên không có lọc test không phân biệt được cluster
[CODE_INSPECTED].
**Tie-break chính xác trong `pick_the_best_candidate`** [CODE_INSPECTED:
`evaluate.py`]: (1) `max_score = max(scores)`; lấy tất cả candidate có điểm = max.
(2) Nếu chỉ 1 → trả nó (cluster lớn nhất **không** được xét). (3) Nếu hoà → trả
candidate hoà đầu tiên **thuộc cluster lớn nhất** (`max(clusters, key=len)`); nếu
không candidate hoà nào thuộc cluster lớn nhất → trả candidate hoà đầu tiên theo
thứ tự gốc. `max()` trên dict khi hoà kích thước cluster sẽ lấy key gặp đầu tiên
theo thứ tự chèn — tức phụ thuộc thứ tự sample, không phải random có seed
[INFERENCE]. Phương thức `self_consistency()` (chọn phần tử đầu cluster lớn nhất)
**tồn tại nhưng không được gọi trong `_run`** — `_run` chỉ gọi
`pick_the_best_candidate` [CODE_INSPECTED].
**Điểm yếu khi LLM scoring lỗi:** nếu `async_llm_chain_call` exception →
`response = []` → `comparison_matrix = []` → dòng tính `comparison_matrix[0]` sẽ
lỗi và tool fail qua `Tool.__call__`, không có best candidate nào được append —
cuối cùng lại rơi về `"--error--"` ở node evaluation [INFERENCE từ chuỗi code đã
đọc]. Không có retry hay fallback điểm số.
**Confidence / threshold: KHÔNG CÓ.** Không biến confidence, không ngưỡng, không
so sánh margin nào trong `Evaluate`, `Revise`, `RunManager` hay config đã đọc. Điểm
`scores` chỉ dùng để `max`, và 2 nhánh suy biến còn gán điểm 1 giả tạo — **điểm 1 ở
đây không phải confidence**. Vị trí gắn ngưỡng (đề xuất, [INFERENCE] thiết kế mới):
(1) ngay sau `pick_the_best_candidate` trong `Evaluate._run`: tính
`norm = best_score / len(unit_tests_thực_tế)` và `margin = top1 - top2`; abstain
khi (a) rơi nhánh suy biến (0 candidate / 1 candidate / 0 test — phải gắn cờ riêng,
vì điểm 1 ở đó là giả), (b) `norm < τ` (ví dụ 0.5–0.7, cần calibrate trên dev có
nhãn, không lấy từ BIRD), (c) `margin` nhỏ (ví dụ ≤1 trên ~21 test, tức hoà gần như
tuyệt đối); cần lưu cờ abstain vào `SystemState`, **không** append best candidate
vào `SQL_meta_infos` như hiện tại; (2) chặn cuối ở `RunManager.task_done` / trước
`update_final_predictions`: nếu `PREDICTED_SQL` thuộc
`{"--error--", "SELECT * FROM table_name"}` hoặc execution status ≠
`SYNTACTICALLY_CORRECT` thì **không ghi** bài nộp đó, thay bằng định dạng abstain
của DataMate (định dạng này **UNVERIFIED** — không có trong repo CHESS, phải đối
soát `zaic_tools`/portal; không được tự gán `0` của CHESS vì `0` trong predictions
của CHESS chỉ là placeholder "chưa xử lý", không phải tín hiệu abstain của DataMate);
(3) ở tầng Revise: sau khi agent hết 10 lượt `workout` mà candidate cuối vẫn
`EMPTY_RESULT`/`SYNTACTICALLY_INCORRECT` thì abstain thay vì để node evaluation lấy
key cuối cùng.

### 4.4. CSC-SQL — `CycloneBoy/csc_sql`, commit `0fafdf3ee7f334bb11653d890b6e818bf813be`, Apache 2.0

Là code kế nhiệm cùng nhóm của BASE-SQL (repo chính thức `CycloneBoy/base_sql`
commit `065bfe17` không có file `.py` nào — kết luận âm tính của round 3, không kiểm
chứng lại trong luồng này). License Apache 2.0 qua trang repo [CODE_INSPECTED].

**Bước 1 — tất cả draft lỗi ở `major_voting2`** [CODE_INSPECTED:
`src/cscsql/utils/infer_utils.py:major_voting2`, nhánh `sum(valid) == 0`]: nếu
`return_random_one_when_all_errors` (mặc định `True`) thì
`mj_pred_sql = random.choice(execution_results_of_one_sample)["sql"]` — 1 draft
**lỗi** ngẫu nhiên; nếu caller truyền `False` thì `mj_pred_sql = "Error SQL"`.
`run_eval_major_vote` gọi `major_voting2` **không truyền** flag này nên luôn dùng
mặc định `True` [CODE_INSPECTED]. Tức mặc định: tất cả lỗi → nộp 1 draft lỗi ngẫu
nhiên, `votes=1, correctness=0`, không có cờ "không trả lời được". Chỉ khi caller chủ
động truyền `False` mới có sentinel `"Error SQL"` — và không caller inference nào
trong `pipeline_infer.py`/`infer.py` đã đọc làm vậy.

**Bước 2 — merge bỏ qua câu thiếu top-2, rồi fallback về chính draft lỗi đó.**
Trong `execute_batch_vote_sql_to_result` [CODE_INSPECTED:
`src/cscsql/utils/common_utils.py`]: mọi câu đều được append vào
`all_predict_results` với `sql = sql_list[0]` (top-1) **trước** khi kiểm tra độ dài;
nhưng nếu `len(sql_list) < 2` → `continue`: câu đó **không có mặt trong dict vote**,
nên không có `sql1/sql2/res1/res2` cho merge. Thêm điều kiện lọc: draft phải dài
≥10 ký tự và bắt đầu bằng `select` (không thỏa → cũng `continue`). Nhánh chèn gold
(`if is_train and item['correctness'] == 0:... sql_list = [.., gold]`) **chỉ chạy
khi `is_train=True`** — ở inference `infer.py` gọi với `is_train=False`
[CODE_INSPECTED], nên **không bao giờ chèn gold lúc inference** (đúng như round 3;
đây là bước tạo dữ liệu train, không phải gian lận inference — nhưng cũng có nghĩa
inference không có "cứu cánh" gold nào).

Trong `build_prompt` của merge [CODE_INSPECTED: `src/cscsql/model/infer.py`]: nếu
`index not in selection_vote_predict_sql_results` → `continue` (câu thiếu top-2 bị
**loại khỏi input_dataset của merge**). Rồi cuối `infer.py` có fallback tường minh
[CODE_INSPECTED]: nếu `all_predict_results` đủ số lượng thì với mỗi item chưa có
trong `infer_ids`, tạo `new_item['mode'] = "major_vote"`,
`new_item['pred_sqls'] = [item['sql'] for _ in range(opt.n)]` (top-1 lặp lại n lần),
append vào results.

**Chuỗi đầy đủ khi tất cả draft lỗi:** draft lỗi ngẫu nhiên (bước 1) → top-2 chỉ có
1 phần tử → bị loại khỏi merge → được append lại với `pred_sqls = [draft_lỗi × n]`
→ `run_eval_major_vote` trên output merge lại rơi vào nhánh all-error và chọn lại
chính draft đó. **Bài nộp cuối = SQL lỗi, không phải rỗng, không phải abstain.**
Trường hợp file vote thiếu hẳn (`selection_vote="none"`) thì khác:
`build_selection_vote_execute_sql_result` trả `(None, [])` ngay từ đầu [CODE_INSPECTED],
merge prompt trở thành prompt thường (không draft) qua `build_merge_generate_prompt`
trả nguyên instruction khi `predict_result is None` — tức **âm thầm suy biến thành
sinh thường, vẫn nộp**, chứ không báo thiếu dữ liệu.

**Trường hợp "rỗng" thì sao?** Trong `infer_utils.execute_sql`, `fetchall()` rỗng
cho `frozenset()` rỗng và `valid=1` (không exception) [CODE_INSPECTED:
`src/cscsql/utils/infer_utils.py:execute_sql`]. Nên **kết quả rỗng được tính là hợp
lệ và có thể thắng majority** — CSC không có khái niệm "rỗng = đáng ngờ" như CHESS.
Tương tự, `COUNT=0` cho key `frozenset({(0,)})`, toàn NULL cho key chứa `None` — đều
là cluster hợp lệ, không bị phân biệt hay phạt riêng.

**Sinh code, self-check, confidence** [CODE_INSPECTED]: **chỉ SQL.** Prompt bắt
"return the final SQLite SQL query that starts with keyword `SELECT`" trong thẻ
`<answer>`; `parse_response` lấy block ```sql cuối cùng hoặc nội dung `<answer>`.
Chặng `table_link` chỉ sinh danh sách bảng, không phải code. Engine: SQLite, đường
dẫn hard-code `.sqlite` — mọi nơi đều ghép `<db_root>/<db_id>/<db_id>.sqlite`.
Không có đọc Excel/CSV — DataMate phải convert trước, và tên DB phải khớp đúng quy
ước này. **Rollback — cần phân biệt 2 hàm `execute_sql` khác nhau:**
`infer_utils.execute_sql` (dùng cho major voting): `conn.execute("BEGIN
TRANSACTION;")`, `fetchall()` → `frozenset`, rồi `conn.rollback()` cả khi thành
công lẫn khi exception, rồi `close()`; timeout qua `execute_sql_wrapper` với
`func_timeout` → timeout cũng trả `(…, None, 0)`; mặc định ở `major_voting2` là
`num_cpus=30, timeout=30`. `common_utils.execute_sql` (dùng cho việc chạy lại 2 draft
của merge): chỉ `with sqlite3.connect(...)` rồi `execute` + `fetchall`, **không có
`BEGIN`/`rollback`** [CODE_INSPECTED]. Vì draft được kỳ vọng là SELECT nên thực tế
ít rủi ro, nhưng **không được khẳng định "CSC luôn rollback mọi DB"** — chỉ nhánh
major-voting mới rollback. Số lượng sample (pipeline, `pipeline_infer.py`): mặc
định `n_table_link=8, temp 0.8`; `n_sql_generate=8, temp 0.8`; `n_sql_merge=8, temp
0.8`; `greedy_search` thì ép `n=1, temp 0.0` ở mọi chặng [CODE_INSPECTED:
`run_eval_by_cmd` và khối `argparse` cuối file]. Tổng sample ở mode major-voting là
8+8+8=24 như round 3. **Bầu chọn theo execution result — chi tiết:** key bầu chọn
là `frozenset(cursor.fetchall())` [CODE_INSPECTED: `execute_sql`]. Hệ quả [INFERENCE
từ semantics của frozenset]: **mất thứ tự** (2 SQL trả cùng tập dòng khác thứ tự →
cùng cluster); **mất trùng lặp** (dòng trùng nhau bị collapse — 2 SQL khác nhau về
số lượng dòng trùng vẫn có thể cùng cluster); **NULL được xử lý như giá trị thường**
trong frozenset (`None` hash được), không có chuẩn hoá NULL đặc biệt; **lỗi/timeout
bị loại khỏi bầu chọn** (`valid=0` → `skip invalid SQLs` trong `major_voting2`), trừ
nhánh all-error ở trên. `major_voting2` đếm vote theo key frozenset, giữ SQL đại
diện đầu tiên gặp của mỗi key; khi hoà vote, `max` và vòng lặp thiên về key gặp
trước (thứ tự sample), không có random tie-break có seed ở đây (random chỉ dùng ở
nhánh all-error và nhánh chèn gold train). `top2_correctness_list` lưu `vote_list =
[top1_vote, top2_vote]` và `sql = [top1_sql, top2_sql]` — đây là file
`_pred_major_top2_sqls.json` mà merge đọc. **Không có vòng sửa lặp:** sau merge,
chỉ có thêm 1 lần `run_eval_major_vote` trên output merge; merge model không bị bắt
phải sinh SQL chạy được, không bị so execution với draft, không có retry nếu merge
output lỗi — nó chỉ được bầu chọn lại theo cùng luật majority [CODE_INSPECTED].
**Merge prompt dùng kết quả thực thi của 2 draft như thế nào:**
`build_merge_generate_prompt(instruction, predict_result)` đổi task message thành
bản "có draft SQL và execution result", rồi chèn đúng 2 mục theo format
`"{i+1}. {sql}\n\n{sql_res}\n"` [CODE_INSPECTED:
`CommonUtils.build_merge_generate_prompt`]. Cắt ngắn: SQL dài >500 ký tự bị cắt còn
500; kết quả qua `normal_execute_result`: >20 dòng thì chỉ lấy 20 dòng đầu, >1000
ký tự thì cắt + `"..."` [CODE_INSPECTED]. `res1/res2` đến từ
`common_utils.execute_model`: thành công thì là list dòng, lỗi thì là chuỗi
`"execute sql error message: <detail>"` (detail rút gọn về 1 trong các mẫu
`ambiguous column name / no such column / no such table / no such function /
syntax error / others`), timeout thì là chuỗi timeout [CODE_INSPECTED:
`CommonUtils.execute_model`, `find_detail`]. Tức merge model **có thấy thông báo
lỗi của draft**, nhưng chỉ khi draft đó lọt được vào top-2 (draft lỗi đơn lẻ đã bị
loại từ trước).
`extract_merge_schema_from_sql(sqls, db_uri, db_full_schema)` [CODE_INSPECTED]:
parse cả 2 draft bằng `ChessSchemaParser.get_sql_columns_dict`, gom cột qua
`aggregate_columns`, rồi `get_diff_merge_schema` **chỉ giữ lại cột nào thực sự tồn
tại trong full schema** (tra cả tên gốc và lowercase); cột lạ trong draft bị lặng lẽ
loại. Sau đó `build_merge_generate_prompt` gọi `build_link_table_from_ddl` để cắt
DDL trong prompt chỉ còn các bảng link đó (nếu danh sách rỗng thì giữ nguyên schema
đầy đủ) [CODE_INSPECTED].
**Confidence / threshold: KHÔNG CÓ.** `vote_list` (top-1/top-2 vote) **được tính và
lưu** trong top-2 file nhưng **không được dùng để quyết định gì ngoài việc chọn
top-2**: `run_eval_major_vote` chỉ lấy `item['sql']` từ `mj_pred_correctness_list`
để ghi file nộp, không đọc `votes` hay `vote_list` [CODE_INSPECTED:
`run_eval_major_vote`]. Không có ngưỡng share, không có margin check, không có cờ
valid nào được truyền tới bước nộp cuối.
**Vị trí gắn ngưỡng (đề xuất, [INFERENCE] thiết kế mới):** (1) sau
`run_eval_major_vote` ở chặng `sql_generate`, trước khi vào `sql_merge` — nhưng
phải sửa hàm để trả thêm vote: hiện tại khi không có gold (đúng trường hợp DataMate
private test, `gold_file="none"` → `ground_truth_sqls=None`), hàm trả
`(save_file, mj_pred_sqls, None, save_mj_top2_file)` — file top-2 chính là return
thứ 4 này [CODE_INSPECTED: `run_eval_major_vote`, nhánh
`if ground_truth_sqls is None`]. Đọc file đó, tính `share = top1_vote /
sampling_num` và `margin = top1_vote - top2_vote` cho từng câu; abstain khi
`share < τ` (ví dụ <0.5 với n=8, tức top-1 không quá bán) hoặc `margin == 0` (hoà
top-1/top-2), **thay vì** để nó trôi vào merge rồi fallback về draft lỗi. (2) Tại
nhánh all-error của `major_voting2`: đổi caller để truyền
`return_random_one_when_all_errors=False` thì sẽ nhận sentinel `"Error SQL"` — đây
là điểm gắn rẻ nhất: ở `infer.py`/`pipeline_infer.py`, nếu SQL cuối == `"Error SQL"`
(hoặc mọi draft `valid==0`) thì abstain thay vì ghi file. Hiện tại mặc định là
`True` nên điểm này đang tắt. (3) Sau merge, trước khi ghi file nộp cuối: áp lại
cùng kiểm tra share/margin trên output merge; đồng thời kiểm tra cờ
`mode == "major_vote"` (câu bị loại khỏi merge) mà nguồn top-1 của nó là draft lỗi
→ abstain thay vì lặp lại draft lỗi n lần. (4) Riêng cho kết quả rỗng: vì empty
frozenset là cluster hợp lệ, `share` cao trên cluster rỗng **không được coi là
confidence cao**. Cần thêm điều kiện riêng: nếu top-1 cluster là rỗng thì chỉ nộp
khi có bằng chứng độc lập rằng rỗng là đáp án hợp lý (ví dụ câu hỏi dạng kiểm tra
tồn tại / câu hỏi mà LLM-judge xác nhận "không có dòng nào" là đáp án đúng); nếu
không thì abstain. Đây là thiết kế mới, không có trong code CSC [INFERENCE].

### 4.5. XiYan-SQL — solution mới ngoài 4 cái của round 3 (cảnh báo repo trước khi dùng số liệu)

- Repo chính đã mở: `https://github.com/XGenerationLab/XiYan-SQL`, commit header lúc
mở `603dedac706d57ece47bc30d02f90744a537b6a0`, default branch `main`, 163 commits,
public, tạo 2024-11-12; license **Apache-2.0** (trang repo ghi rõ, chưa đọc nội
dung file LICENSE từng dòng) [CODE_INSPECTED cho trang repo/listing]. **Repo này
chỉ chứa README/README_zh/LICENSE/ảnh/PDF — không có thư mục code pipeline.**
Commit `603ded…` là commit của repo hub (chủ yếu README), **không phải commit của
code pipeline** — trích commit này mà không kèm cảnh báo sẽ gây hiểu lầm là "đã có
code tại commit đó".
- Code thật duy nhất đọc được ở phần schema: repo `XGenerationLab/M-Schema` (commit
header `755751451be841f7a54f8b08c0a1f818b041a1c0`, main, 35 commits, Apache-2.0)
với `m_schema.py`, `schema_engine.py`, `utils.py`, `example.py`, `aan_1.sqlite`,
`requirements.txt`, `pyproject.toml` [CODE_INSPECTED cho header/listing]. README
của nó cho đúng usage: `SchemaEngine(engine=db_engine, db_name=db_name)`,
`mschema = schema_engine.mschema`, `mschema_str = mschema.to_mschema()`,
`mschema.save(...)`; kết nối qua SQLAlchemy, ví dụ SQLite là
`create_engine(f'sqlite:///{abs_path}')`.
- Repo `XGenerationLab/xiyan_mcp_server` (commit header
`7d3ee1caab605c6e27628fe2a2f84ab0a7c222a8`, main, 67 commits, Apache-2.0): MCP
server single-model với tool `get_data` (NL → SQL → thực thi → trả kết quả dạng
text), resource `{dialect}://{table_name}` lấy sample, `{dialect}://` liệt kê bảng;
README ghi rõ chỉ hỗ trợ **MySQL và PostgreSQL** ("Support MySQL and PostgreSQL",
"more dialects soon") — **không phải pipeline XiYan đầy đủ, không có SQLite trong
MCP này** [CODE_INSPECTED cho header/listing].
- Repo training (mirror Alibaba) `alibaba/XiYan-SQL/XiYan-SQLTraining/`: `data/`,
`train/`, `evaluation/` với `data_processing.sh`, `data_assembler.sh`,
`xiyan_sft.sh`, `sql_infer.sh`, `sql_eval.sh` (theo README thư mục) — training +
inference/eval cho **một model**, không phải code orchestration của
ensemble/selection; `sql_infer.sh` nhận `model_name_or_path, expr_version,
test_set_path, batch_size`; `sql_eval.sh` nhận `pred_sql_path, test_sql_path,
db_conn_config, save_eval_path` [CODE_INSPECTED cho README thư mục; **commit của
repo alibaba: UNVERIFIED** — trang tree đã mở không hiển thị commit header trong
nội dung trả về].
- **Không tìm thấy file code nào cho:** Schema Filter (`Ms` keyword extraction +
PFKeyIdentifier), multi-generator orchestration, self-refine prompt, selection
model `Mc`, hay hàm `groupby/deformalize/schema_union` của Algorithm 3. Các tên này
chỉ tồn tại ở dạng **giả mã trong paper**, không phải file/function đã đọc.
DeepWiki (`deepwiki.com/alibaba/XiYan-SQL`) có trích dẫn số dòng kiểu
`XiYan-SQLTraining/data/data_utils/m_schema.py 212-250` cho `to_mschema(...)` và
`schema_engine.py 87-123` cho `init_mschema()` — đây là **chỉ mục thứ cấp, không
phải code đọc trực tiếp**, chỉ dùng như gợi ý vị trí, không gắn [CODE_INSPECTED].
Luồng XiYan **không mở được nội dung file `.py` dạng blob** qua công cụ đọc text
(chỉ trả về trang repo/README và trang DeepWiki tóm tắt) — vì vậy các claim
pipeline dưới đây ở mức **[OFFICIAL] theo paper**, không phải code đã đọc trực tiếp.
- **Kết luận cho tiêu chí "phải có code pipeline chạy được để copy": XiYan KHÔNG
ĐẠT ở repo đã mở** (chỉ có M-Schema + Training + MCP single-model). Nếu tiêu chí
này bắt buộc, bước tiếp theo nên là phân tích MAC-SQL (repo `wbbey/MAC-SQL`) như
task đã dự phòng — báo cáo này chưa phân tích MAC-SQL, không nên coi XiYan là thay
thế code cho MAC-SQL.

**Bản đồ pipeline theo paper (arXiv 2507.04701v2, §III-A–III-D) [OFFICIAL theo
paper]:**

```
Q (câu hỏi) + E (evidence) + DB
→ [Stage 1] Schema Filter: multi-path retrieval → iterative column selection
→ tập schema đã lọc S = {S1, …, S_ps}, ps = 2 trong cấu hình báo cáo
→ [Stage 2] Multiple SQL Generation: ps × pm candidate
→ mỗi candidate chạy thử; nếu lỗi thì self-refine đúng 1 lần
→ L = {l1, …, l_pl}, pl = ps × pm = 10
→ [Stage 3] SQL Selection: deformalize → groupby theo kết quả thực thi
→ sắp xếp liên-nhóm theo kích thước cụm, nội-nhóm theo thứ hạng generator
→ selection model Mc chọn 1 SQL duy nhất l*
```

- **Stage 1 — Schema Filter** (paper §III-B, Algorithm 1): LLM `Ms` trích keyword
`K = f_Ms(Q, E)`; retrieval bảng/cột: `Score(ki, cj) = <V_Q||E, V_Tab(cj)> ·
<V_ki, V_cj>` (cosine similarity, top-k cột/keyword); retrieval giá trị: edit
distance lấy top-k giá trị/cột, rồi RoBERTa tokenizer + LSH + cosine similarity có
ngưỡng; column selection lặp `i = 1..ps`: `S_slct_i ← f_Ms(S_rtrv, Q, E)`;
`P_i ← PFKeyIdentifier(S_slct_i)` (tự bổ sung đủ composite PK/FK để giữ join
path); `S_i ← (∪_{k<i} S_k) ∪ S_slct_i ∪ P_i`; rồi `S_rtrv ← S_rtrv \ (S_slct_i \
P_i)` (chỉ loại cột non-key đã chọn, giữ lại key). Hệ quả: precision giảm dần,
recall tăng dần qua các vòng — S1 và S2 là hai schema có trade-off khác nhau,
không phải một schema "tốt nhất".
- **Stage 2 — Multiple SQL Generation** (paper §III-C, Algorithm 2; xem §4.5 dưới).
- **Stage 3 — SQL Selection** (paper §III-D, Algorithm 3; xem §4.5 dưới).
- **Không có stage Python, không có stage decomposition thành sub-question, không có
agent Selector/Decomposer/Refiner kiểu MAC-SQL.** Đây là pipeline tuyến tính 3
stage, vòng lặp duy nhất là refine 1 lần trong Stage 2 và vòng lặp column-selection
`ps` lần trong Stage 1.

**Cơ chế unanswerable / abstain: KHÔNG CÓ.** Tìm từ khoá `unanswerable` trong toàn
bộ paper 2507.04701v2: **0 kết quả** [OFFICIAL theo paper]. Không có nhánh nào
trong Algorithm 1/2/3 trả về "không trả lời được", bỏ câu, hay output rỗng có chủ
đích: Algorithm 3 luôn trả về một `l*` — nếu `|C| = 1` thì trả SQL ngắn nhất; ngược
lại thì `l* ← f_Mc(Q, S^un, E, L')` (selection model luôn phải chọn một candidate
trong danh sách đã sắp xếp lại). Không có nhánh "nếu danh sách rỗng thì abstain".
Algorithm 2: candidate lỗi được refine 1 lần rồi **append vô điều kiện** — kể cả bản
refine vẫn lỗi cũng vào `L`. Sau đó Algorithm 3 lại mở đầu bằng giả định "ensuring
that any candidates with execution errors have already been excluded" — đây là
**mâu thuẫn/khe hở giữa hai thuật toán**, không phải một fallback được định nghĩa.
Hành vi khi mọi candidate đều lỗi là **UNVERIFIED**: paper không định nghĩa; khả
năng thực tế là crash ở bước `groupby`, hoặc selection model vẫn chọn một SQL lỗi
trong danh sách — tuyệt đối không được giả định là "nó sẽ tự abstain". Fallback
thực tế duy nhất trích được từ paper (không phải abstain): nếu mọi candidate cho
cùng một kết quả thực thi (`|C| = 1`): chọn `argmin |l|` — SQL ngắn nhất (heuristic
"đơn giản nhất thì đúng", không phải kiểm chứng đúng/sai); nếu không có cụm đa số:
chỉ lấy **một đại diện ngắn nhất mỗi cụm** đưa cho selection model — tức vẫn ép
chọn, chỉ thu hẹp danh sách.

**Sinh code, self-check, execution feedback** (paper §III-C, Algorithm 2):
`for i = 1..ps, for j = 1..pm: l_ij ← f_Mj(Q, E, S_i); r ← execute(l, D); nếu không
exception thì append l_ij; nếu không thì retry đúng 1 lần: l̂_ij ← f_Mj(Q, E, S_i,
l, r) (self-refine, input = Q + E + schema + SQL cũ + kết quả/lỗi thực thi); append
l̂_ij KHÔNG kiểm tra lại, không re-execute trong giả mã.` Không có điều kiện dừng
kiểu "lặp đến khi hết lỗi" hay "dừng khi kết quả lặp lại" — vì chỉ có đúng 1 lần
thử lại. Về mặt training, khả năng self-refine này được dạy qua multi-task
fine-tuning: một trong 4 task phụ là Self-Refine task — tức refine không phải prompt
engineering thuần tuý mà là năng lực được fine-tune vào generator. Điều kiện kích
hoạt (prose §III-C): "if the execution of the generated SQL encounters syntax
errors or anomalous values" — nhưng Algorithm 2 chỉ formal hoá thành "No exception
/ else". Hai khái niệm không khớp nhau: "anomalous values" (giá trị bất thường
nhưng không gây exception) không có định nghĩa executable nào trong giả mã.
**Phân biệt lỗi thực thi vs rỗng vs COUNT=0 — KHÔNG PHÂN BIỆT (điểm yếu chí mạng
khi chuyển sang DataMate):** lỗi thực thi (exception) trigger refine 1 lần — đây là
trường hợp duy nhất được xử lý; kết quả rỗng (0 dòng) **không gây exception → được
append như candidate hợp lệ**, không refine, không cảnh báo, và trong Algorithm 3
các SQL khác nhau nhưng cùng trả về tập rỗng sẽ bị **gom vào cùng một cụm**
(groupby theo kết quả thực thi), tạo ra "đa số giả"; COUNT = 0 / SUM = NULL tương
tự — vẫn là kết quả thực thi hợp lệ, không trigger gì cả; kết quả lặp lại không có
điều kiện dừng hay phát hiện lặp nào trong Algorithm 2/3 (lặp chỉ xuất hiện gián
tiếp ở Algorithm 3 dưới dạng "mọi candidate cùng một kết quả" (`|C| = 1`) → chọn SQL
ngắn nhất). [INFERENCE] cho DataMate: cụm rỗng/0 là cụm nguy hiểm nhất — câu hỏi
về doanh nghiệp mới (giá trị không tồn tại trong DB) rất dễ sinh ra nhiều SQL sai
nhưng cùng trả về rỗng → cụm rỗng phình to → XiYan sẽ tự tin chọn nó. Bất kỳ ngưỡng
abstain nào cũng **phải xử lý riêng cụm rỗng/0** (§4.6), không thể dùng kích thước
cụm thô.
**Self-consistency qua vote — CÓ nhưng chỉ là "prior trình bày", không phải quyết
định cuối** (Algorithm 3, paper §III-D): `L ← deformalize(L)` (chuẩn hoá format SQL
trước khi so sánh); `C = {C1..Cm} ← groupby(L, R)` (gom theo kết quả thực thi R,
không theo chuỗi SQL); `S^un ← schema_union(S)` (hợp tất cả schema đã lọc, đưa cho
selection model); nếu `|C| = 1`: return `argmin|l|` (nhất trí tuyệt đối → SQL ngắn
nhất, **không gọi selection model**); nếu không: `C' ← sort(C)` theo kích thước cụm
giảm dần (inter-group), `C'' ← sort` mỗi cụm theo thứ hạng generator `O`
(intra-group, `O` xếp theo performance eval); nếu `|C1''| ≥ ceil(|L|/2)` (có cụm đa
số tuyệt đối): `L'` = toàn bộ candidate theo thứ tự `C''` đưa cho selection model;
nếu không: `L'` = mỗi cụm chỉ lấy 1 đại diện ngắn nhất, theo thứ tự cụm; return
`l* ← f_Mc(Q, S^un, E, L')` (selection model Qwen2.5-Coder-7B fine-tune chọn 1).
**Vote share có tồn tại dưới dạng ẩn** (`|C1''| / |L|` và ngưỡng `ceil(|L|/2)`) —
nhưng chúng chỉ quyết định **cách trình bày danh sách** cho selection model,
**không quyết định đáp án** và **không trigger abstain**. Khi không có đa số, XiYan
không bỏ câu mà thu hẹp danh sách rồi vẫn ép selection model chọn. Tie-break: (1)
cụm lớn hơn trước; (2) trong cụm, generator có thứ hạng `O` cao hơn trước; (3) khi
cần 1 đại diện/cụm hoặc khi nhất trí tuyệt đối, chọn SQL ngắn nhất `argmin|l|`.
Không có tie-break bằng logit hay xác suất.
**Bằng chứng selection model thắng majority vote thuần tuý** [OFFICIAL theo paper,
§IV-G, Table VIII, BIRD dev — **không phải bảo đảm cho DataMate**]: majority voting
70.21% ở `pl=10`; selection model + reorganization (`s3`) 73.34%; selection model +
thứ tự ngẫu nhiên (`s1`) chỉ 68.19% (thua cả majority vote) — tức **thứ tự trình bày
là thành phần quan trọng, không phải chỉ có model**. Ablation tổng (§IV-C): bỏ
selection → chỉ còn majority vote → −3.13 điểm; bỏ multi-generator → −4.04; bỏ
Schema Filter → −1.24 (đều trên BIRD dev).
**Số candidate và tham số sampling:** cấu hình báo cáo trong paper (§IV-A):
`ps = 2` schema, `pm = 5` generator, `pl = ps × pm = 10` candidate. 5 generator gồm:
SQLG1 = multi-task fine-tune cơ sở; SQLG2 = structural variation (ưa CTE); SQLG3 =
stylistic variation (casing/alias); SQLG4 = mix tất cả; SQLG5 = ICL generator dùng
GPT-4o (§IV-H). **Temperature/top-p/n cho pipeline chính: UNVERIFIED** — paper chỉ
nhắc "ICL-Temp" và "FT-Temp" như một thí nghiệm đối chứng mà không công bố giá trị
dùng cho pipeline chính trong đoạn đã đọc. Con số `temperature=0.7, top_p=0.9` xuất
hiện trong một trang DeepWiki hướng dẫn load model đơn lẻ — đó **không phải** tham
số pipeline XiYan, không được dùng làm tham số pipeline.
**Điểm khác biệt cốt lõi về "sinh bao nhiêu":** XiYan **không lấy diversity từ
sampling** (cùng model sample nhiều lần) mà từ **diversity của generator** (4
fine-tune có "tính cách" khác nhau + 1 ICL) × **diversity của schema** (2 schema
precision/recall khác nhau). Mỗi generator chỉ sinh đúng 1 SQL/schema, không sample
n lần.

**Confidence / calibration và vị trí gắn ngưỡng** (paper không có; đề xuất
[INFERENCE], cần calibrate trên dev của DataMate, không phải hằng số của XiYan):
**KHÔNG CÓ** score tường minh nào: không vote share được xuất ra, không agreement
rate được trả về, không logit/probability, không ngưỡng abstain trong bất kỳ thuật
toán nào. Selection model `Mc` là một LLM fine-tune sinh ra lựa chọn (generative
listwise choice), không phải ranker trả điểm. Vị trí gần nhất có thể gắn ngưỡng —
chính xác là sau bước `groupby` của Algorithm 3, trước bước chọn: tức sau khi đã có
`C = groupby(L, R)` và `|L|` (số candidate còn lại sau khi loại lỗi), tính:
`share1 = |C1''| / |L|` (tỷ lệ cụm lớn nhất), `margin = |C1''| − |C2''|` (cách biệt
cụm 1 và cụm 2; nếu chỉ có 1 cụm thì margin = |L|), `exec_rate = |L| / pl` (tỷ lệ
candidate sống sót sau thực thi; `pl = 10` trong cấu hình gốc), `empty_share` = tỷ
lệ candidate trong cụm thắng mà kết quả là rỗng/COUNT=0/NULL (phải tính riêng, vì
groupby thô sẽ gộp chúng). Ngưỡng đề xuất dưới dạng [INFERENCE]: abstain khi
`exec_rate` thấp (phần lớn candidate lỗi/refine vẫn lỗi) **hoặc** `share1 < 0.5`
(không có đa số tuyệt đối, đúng ngưỡng `ceil(|L|/2)` mà XiYan đã dùng để đổi chế độ
trình bày) **kết hợp** `margin ≤ 1` (cụm 1 và cụm 2 gần như ngang nhau) **hoặc** cụm
thắng là cụm rỗng/0. Lý do dùng ngưỡng này cho PA (+1/0/−1): khi `share1 < 0.5`,
xác suất cụm thắng đúng thường < 0.5 trong các case không nhất trí (paper ghi ~45%
case là nhất trí tuyệt đối, phần còn lại mới cần chọn — chính phần này là nơi sai số
tập trung); đoán mò lúc đó có kỳ vọng âm, abstain (0) tốt hơn. Ngược lại, **không
nên abstain khi `|C| = 1`** (nhất trí tuyệt đối) trừ khi kết quả là rỗng — vì đó là
tín hiệu mạnh nhất mà XiYan có. Cảnh báo: `share1` trên `|L| = 10` rất nhiễu (mỗi
candidate = 10%); ngưỡng nên calibrate bằng dữ liệu dev có nhãn của DataMate (vì
public_test không có nhãn, không calibrate được trên đó), và nên kết hợp thêm tín
hiệu độc lập với XiYan: schema coverage (cột/giá trị trong SQL có thật trong DB
không), và "SQL có dùng đúng bảng của doanh nghiệp mới không".
**Một tín hiệu confidence khác có thể tái dùng mà XiYan không dùng:** thứ hạng
generator `O` (generator mạnh → candidate đáng tin hơn). Trong DataMate với model
≤15B, có thể thay `O` bằng thứ hạng đo trên dev (ví dụ XiYanSQL-QwenCoder-14B > 7B
> 3B trên dev của mình) và dùng nó làm tie-break trước khi abstain, thay vì dùng
thứ hạng trên BIRD.

**Điểm khác biệt so với ReFoRCE / CHESS / CSC-SQL — vì sao nó thay đổi quyết định
(và vì sao có chỗ không)** [INFERENCE]:

1. **Diversity đến từ training, không phải từ prompt/sampling — thay đổi quyết định
về cách phân bổ ngân sách model ≤15B.** ReFoRCE/CHESS/CSC chủ yếu tạo diversity
bằng prompt, decomposition hoặc sampling nhiều lần từ cùng một model. XiYan tạo
diversity bằng **4 fine-tune có tính cách khác nhau** (base multi-task /
structural-CTE / stylistic / mix) × **2 schema khác precision/recall**. Với
DataMate (≤15B, offline, 6 giờ), điều này gợi ý một cấu hình rẻ hơn sampling mù:
dùng 2–3 model nhỏ khác nhau (ví dụ XiYanSQL-QwenCoder-14B + 7B + 3B, đều ≤15B)
thay vì sample 20 lần từ một model — vì paper cho thấy sampling cùng model với
temperature khác nhau cho diversity và accuracy thấp hơn multi-generator.
[INFERENCE] khi áp sang model ≤15B: hiệu ứng này chưa được đo với các size nhỏ,
cần thử trên dev.
2. **Selection là learned listwise selector + reorganization, không phải majority
vote thuần — thay đổi quyết định ở case không có đa số.** CSC-SQL merge-revise
top-2; majority vote thuần sẽ thua khi đáp án đúng chỉ thuộc về thiểu số. XiYan
chứng minh trên BIRD dev: khi không có đa số, nó **không vứt thiểu số đi** mà đưa
1 đại diện/cụm cho selection model, và selection model + reorganization thắng
majority vote ~3 điểm. Quan trọng hơn cho DataMate: **chính case "không có đa số"
này lại là case nên cân nhắc abstain** — XiYan ép chọn, DataMate nên abstain. Tức
XiYan cho ta cả hai thứ: (a) một cách trình bày để cứu đáp án thiểu số đúng, và
(b) một tín hiệu (`share1 < 0.5`) để biết khi nào nên abstain thay vì cứu.
3. **Schema Filter sinh nhiều schema, không phải một schema tốt nhất — thay đổi
quyết định về schema linking cho doanh nghiệp mới.** CHESS-style thường lọc về
một schema tối ưu. XiYan cố tình giữ 2 schema (S1 precision cao, S2 recall cao)
vì doanh nghiệp mới = tên bảng/cột/giá trị lạ: schema precision cao có thể loại
mất cột đúng, schema recall cao giữ được nhưng nhiễu hơn. Cho DataMate, đây là
thiết kế đúng hướng: **đừng ép một schema duy nhất khi DB chưa từng thấy**; hãy
để mỗi schema sinh candidate riêng rồi gom cụm sau.
4. **Chỗ XiYan KHÔNG thay đổi quyết định (thua kém so với kỳ vọng):** refine chỉ 1
lần, không có vòng lặp kiểm thử kiểu agent (CHESS/ReFoRCE có thể mạnh hơn ở đây);
không có Python, không có self-check bằng cách viết lại câu hỏi từ SQL; tie-break
"SQL ngắn nhất" là heuristic yếu, có thể chọn sai khi SQL ngắn nhưng thiếu điều
kiện lọc — đặc biệt nguy hiểm cho câu hỏi doanh nghiệp mới, nơi điều kiện lọc mới
là phần khó; selection model gốc là Qwen2.5-Coder-7B fine-tune riêng — **không có
sẵn để tải dùng ngay** trong các repo đã mở (chỉ có generator họ QwenCoder), nên
nếu muốn tái hiện phải tự fine-tune selector hoặc thay bằng LLM judge ≤15B — lúc
đó hiệu năng selection của paper không còn giữ nguyên. License của selection
model / 4 generator fine-tune chuyên biệt: **UNVERIFIED** (không thấy file LICENSE
hay model card nào cho SQLG1–SQLG4 và selection model trong các trang đã mở; chỉ
biết model họ XiYanSQL-QwenCoder có các size 3B/7B/14B/32B).

**Transfer gap sang DataMate (XiYan)** [INFERENCE]:
- PA +1/0/−1, cần abstain: **gap lớn nhất** — không có abstain, luôn ép chọn. Gắn
ngưỡng ở §4.5 (sau `groupby`, trước selection): abstain khi `share1 < 0.5` +
margin nhỏ, hoặc exec_rate thấp, hoặc cụm thắng là rỗng/0. Calibrate ngưỡng trên
dev có nhãn, không dùng số BIRD.
- Tiếng Việt: paper/DB là tiếng Anh; DateResolver ghi "major for Chinese" trong
README hub; không có bằng chứng nào về tiếng Việt [INFERENCE] — rủi ro cao ở
keyword extraction cho Schema Filter (từ khoá tiếng Việt, tên doanh nghiệp có
dấu/không dấu), value retrieval bằng edit distance (tiếng Việt có dấu rất nhạy với
edit distance), và evidence bằng tiếng Việt. Phải chuẩn hoá dấu/chuẩn hoá tên riêng
trước khi retrieval; không giả định model QwenCoder hiểu tiếng Việt tốt như tiếng Anh.
- Excel/CSV/SQLite: chỉ làm việc với DB quan hệ qua SQLAlchemy; không có ingestion
Excel/CSV. Phải có bước chuyển đổi trước pipeline: Excel/CSV → SQLite (mỗi
sheet/file thành bảng, suy luận kiểu cột, giữ tên cột gốc + bản chuẩn hoá), rồi mới
dùng M-Schema (`sqlite:///`). Lỗi ở bước này (sai kiểu số/ngày, header 2 dòng) sẽ
lan sang mọi stage sau.
- Doanh nghiệp mới, chưa từng xuất hiện ở train: cross-domain là điểm mạnh được báo
cáo trên BIRD/Spider (DB mới), nhưng đó là DB quan hệ chuẩn, không phải doanh
nghiệp Việt với quy ước riêng. Schema Filter đa schema giúp ích, nhưng value
retrieval dựa vào giá trị mẫu trong DB sẽ yếu khi tên doanh nghiệp/sản phẩm mới
hoàn toàn. Cần bổ sung retrieval theo tên riêng (fuzzy match có chuẩn hoá dấu) và
**không** tin cụm rỗng (§4.6).
- Model ≤15B, offline hoàn toàn: cấu hình báo cáo dùng GPT-4o (Schema Filter `Ms` +
ICL generator SQLG5) + Qwen2.5-Coder-32B (4 generator) + 7B selector — **vượt 15B
và không offline**. Cấu hình DataMate khả thi: bỏ GPT-4o, bỏ 32B; dùng
XiYanSQL-QwenCoder-14B/7B/3B (đều ≤15B, đã thấy trong README hub) làm generator,
một model ≤15B làm selector/judge. Đánh đổi: mất diversity từ fine-tune chuyên
biệt (SQLG1–4 là fine-tune trên 32B, không rõ có bản ≤15B tương đương để tải) và
mất ICL generator mạnh — phải đo lại trên dev, không lấy số paper.
- 6 giờ private test: paper báo ~40.81 giây/sample end-to-end trên BIRD dev với 10
candidate (gồm cả gọi GPT-4o API) [OFFICIAL theo paper, **không phải đo trên
DataMate**]. Phép tính thô [INFERENCE]: 6 giờ = 21.600 giây; ở 40 giây/câu chỉ đủ
~540 câu nếu giữ nguyên latency — chưa kể model local ≤15B chạy offline có thể
chậm hơn hoặc nhanh hơn tuỳ GPU. Nếu private test nhiều hơn số đó, phải cắt: giảm
`ps` từ 2 xuống 1, giảm generator từ 5 xuống 3, hoặc cache M-Schema + retrieval.
- Public_test không có nhãn: không calibrate được trên public_test. Mọi ngưỡng ở
§4.5 phải calibrate trên dev tự tạo có nhãn (hoặc train split), rồi đóng băng
trước khi chạy private.

**Khuyến nghị triển khai tối thiểu từ XiYan (để parent quyết):** lấy đúng 3 thứ, bỏ
phần còn lại: (1) M-Schema + Schema Filter đa schema (2 schema precision/recall khác
nhau) qua SQLAlchemy/SQLite; (2) sinh candidate từ 2–3 model ≤15B khác nhau (không
sample mù); (3) gom cụm theo kết quả thực thi + ngưỡng abstain ở §4.5, với xử lý
riêng cụm rỗng/0. **Không** bê nguyên selection model fine-tune (không có sẵn),
**không** bê tie-break "SQL ngắn nhất" làm luật duy nhất, và **không** dùng số
BIRD/Spider để đặt kỳ vọng điểm DataMate.

### 4.6. Đối chiếu ngang: DuckDB SQL vs Pandas Python, và xử lý rỗng/0/NULL

**Ma trận engine sinh code — kết quả quan trọng: không solution nào dùng DuckDB,
không solution nào cross-check SQL-vs-Python:**

| Solution | Sinh SQL? | Sinh Python? | Engine thực thi | Cross-check hai đường tính? |
|---|---|---|---|---|
| DABstep baseline | Không | **Có — duy nhất** (smolagents CodeAgent, pandas/numpy) | Python executor (pandas), `open` chỉ-đọc | Không — một đường Python duy nhất, không vote, không cross-check |
| ReFoRCE | Có (duy nhất) | Không (pandas chỉ đọc/so sánh CSV ở host) | SQLite `mode=ro` / Snowflake / BigQuery, timeout 300s | Không — chỉ SQL-result vs SQL-result qua `compare_pandas_table` + shape |
| CHESS | Có (duy nhất) | Không | SQLite duy nhất, timeout 60s | Không — clustering theo `repr(execution_result)` + LLM scoring theo unit test, cùng một engine |
| CSC-SQL | Có (duy nhất) | Không | SQLite duy nhất, đường dẫn hard-code `.sqlite` | Không — bầu chọn theo `frozenset` kết quả SQL, cùng một engine |
| XiYan-SQL | Có (duy nhất) | Không | SQLAlchemy (SQLite/PostgreSQL/nGQL theo paper; MCP chỉ MySQL/PostgreSQL) | Không — gom cụm theo kết quả SQL, cùng một engine |

**Hệ quả cho tài liệu này:** lựa chọn DuckDB của DataMate **không có tiền lệ trong
5 codebase này** (SQLite mới là engine chung). Quan trọng hơn: **cross-check
SQL-vs-Python của pipeline repo là thiết kế gốc, không copy từ solution nào** — mọi
"agreement" trong 5 codebase đều là agreement giữa các candidate SQL trên cùng một
engine, tức chúng đều mù trước lỗi hiểu sai chung (sai join, sai filter, sai rule mà
mọi candidate cùng mắc). SQL-vs-Python có giá trị lý thuyết cao hơn đúng ở điểm này
(hai đường tính độc lập khó cùng sai một cách), nhưng giá trị đó **chưa được chứng
minh trong bất kỳ codebase nào ở đây** — nó phải được đo trên dev có nhãn của
DataMate (tỷ lệ SQL-vs-Python đồng thuận mà vẫn sai = thước đo trực tiếp của "đồng
loã"), chứ không được mặc định là tín hiệu confidence mạnh.

**Ma trận xử lý rỗng / COUNT=0 / NULL — nơi dễ sai nhất dưới PA:**

| Solution | Kết quả rỗng (0 dòng) | COUNT = 0 | Toàn NULL | Lỗi thực thi |
|---|---|---|---|---|
| DABstep | Không có trạng thái riêng — agent Python tự diễn giải; prompt không dặn rỗng nghĩa là gì | Không có trạng thái riêng | Không có trạng thái riêng | Observation cho step sau; hết steps → ép đoán |
| ReFoRCE | Chuỗi `"No data found..."` — trạng thái riêng; exploration: rỗng → `simplify=True` khi sửa; self_refine: rỗng lặp 4 lần (cột đầu) + early_stop → xoá CSV | Không phân biệt riêng trong code đã đọc (COUNT=0 trả 1 dòng nên không rơi vào nhánh rỗng) | Không phân biệt riêng (rơi vào nhánh có rows) | Dict `{"status": "error"}` tiền tố `##ERROR##`; sửa tối đa 3 lần/SQL thăm dò, tối đa `max_iter`=5 vòng self_refine |
| CHESS (code chạy thật) | `EMPTY_RESULT` → `need_fixing = True` (sửa) | `SYNTACTICALLY_CORRECT` (nhánh ZERO_COUNT đã comment) → **coi là đúng, không sửa** | `SYNTACTICALLY_CORRECT` (nhánh ALL_NONE đã comment) → **coi là đúng, không sửa** | `SYNTACTICALLY_INCORRECT` → `need_fixing = True` (sửa) |
| CSC-SQL | `frozenset()` rỗng, `valid=1` → **cluster hợp lệ, có thể thắng majority** | `frozenset({(0,)})` → cluster hợp lệ | Key chứa `None` → cluster hợp lệ | `valid=0` → loại khỏi bầu chọn; tất cả lỗi → nộp draft lỗi ngẫu nhiên (mặc định) |
| XiYan-SQL (paper) | Không exception → append như candidate hợp lệ; gom cùng cụm rỗng → **"đa số giả"** | Không trigger gì — kết quả hợp lệ | Không trigger gì — kết quả hợp lệ | Exception → refine đúng 1 lần, rồi append mù (kể cả vẫn lỗi) |

**Quy tắc rút ra cho DataMate (dùng cho protocol, [INFERENCE] từ ma trận trên):**
không được dùng một luật duy nhất cho "rỗng". Cần 4 trạng thái riêng trong gate:
(a) lỗi thực thi → sửa tối đa N vòng rồi abstain nếu vẫn lỗi; (b) rỗng 0 dòng → nghi
ngờ cao, chỉ nộp khi có bằng chứng độc lập rằng rỗng là đáp án đúng (câu hỏi dạng
kiểm tra tồn tại, hoặc SQL đã được kiểm chứng khớp với câu hỏi); (c) COUNT=0 /
SUM=NULL → là đáp án số hợp lệ, **không** được coi là rỗng-đáng-ngờ theo cùng luật
với (b) — nhưng vẫn phải qua gate share/margin như mọi đáp án khác; (d) toàn NULL →
nghi ngờ (thường là join sai hoặc cột sai), abstain trừ khi có bằng chứng độc lập.
CHESS hiện tại gộp (c)/(d) vào "đúng" và CSC/XiYan gộp (b) vào "hợp lệ" — cả hai cách
gộp đều sai theo hướng ngược nhau dưới PA.

### 4.7. Kết luận: cơ chế abstain khả thi nhất và gắn ở bước nào

**Choke point duy nhất: submission writer / final-choose step — sau khi mọi
candidate đã được thực thi và gom cụm, trước khi ghi đáp án.** Mọi đường (SQL path,
Python path, vote path, merge path) đều phải funnel qua gate này. Không gắn abstain
vào scorer (quá muộn — DABstep), không để abstain thành "vắng file" (ReFoRCE — gây
dangling metadata), không để abstain thành chuỗi factoid "Not Applicable"/"Error
SQL"/"--error--"/placeholder SELECT (DABstep/CSC/CHESS — sẽ bị chấm như đáp án sai
nếu scorer không hiểu token đó; định dạng abstain của DataMate là **UNVERIFIED**,
phải đối soát `zaic_tools`/portal trước khi chốt token).

**Gate gồm 5 điều kiện abstain, đánh theo thứ tự (điều kiện nào trúng trước thì
abstain, không cần xét tiếp):**

1. **Không candidate nào thực thi thành công** (mọi SQL lỗi/timeout, mọi Python
path lỗi/rỗng không giải thích được). Đây là trường hợp duy nhất mà cả 5 codebase
đều đồng ý là "thất bại" — nhưng chúng đều xử lý sai sau đó (CHESS nộp
placeholder, CSC nộp draft lỗi ngẫu nhiên, ReFoRCE để trống file, DABstep ép
đoán, XiYan chọn mù). DataMate: abstain trực tiếp, không fallback sang draft lỗi
hay đoán ép. Điểm gắn code: sau bước thực thi cuối cùng, trước final-choose;
tương đương vị trí `major_voting2` nhánh all-error của CSC (nhưng đổi mặc định
`return_random_one_when_all_errors` thành False và map sentinel thành abstain),
và vị trí cuối `self_refine()`/cuối `run_single_task()` của ReFoRCE/DABstep (đổi
"xoá file"/"ép đoán" thành "ghi token abstain").
2. **Top cluster share dưới ngưỡng τ.** Tín hiệu chính, lấy từ cả 3 codebase có
vote: ReFoRCE `(max_vote + 1) / len(all_values)` với quy tắc unique-max (hoà →
không chọn); CSC `share = top1_vote / sampling_num` từ file top-2 (hiện được lưu
nhưng không dùng để quyết định — chỉ cần đọc nó lên); XiYan
`share1 = |C1''| / |L|` với ngưỡng đổi chế độ `ceil(|L|/2)`. Đề xuất khởi điểm
[INFERENCE, cần calibrate]: abstain khi `share1 < 0.5` (không quá bán) — đúng
ngưỡng PA (chỉ trả lời khi P(đúng) > 0.5) nếu coi share là ước lượng thô cho
P(đúng); nhưng share **không phải xác suất đã calibrate** (xem cảnh báo ở §4.8),
nên τ cuối cùng phải đo trên dev có nhãn, không lấy 0.5 làm hằng số thiêng.
3. **Hoà ở top (margin = 0).** ReFoRCE `has_tie` (công thức §4.2); CSC hoà vote theo
thứ tự chèn (thiên về key gặp trước — phải sửa thành abstain thay vì thiên vị);
XiYan `margin = |C1''| − |C2''| ≤ 1` trên `|L| = 10` (mỗi candidate = 10%, rất
nhiễu — nên kết hợp với điều kiện 2, không dùng margin đơn độc). **Không chạy
bước lấp đầy kiểu Step 3/4 của ReFoRCE** (`random_vote_for_tie` thực chất là copy
`first_key`, `final_choose` là copy file đầu tiên) — đó là hai bước phá abstain.
4. **Cluster thắng là rỗng/0/NULL mà không có bằng chứng độc lập.** Đây là điều kiện
riêng, không gộp vào share: vì CSC và XiYan đều cho cluster rỗng thắng majority,
và CHESS coi COUNT=0/toàn NULL là "đúng", nên share cao trên cluster rỗng **không
phải confidence cao**. Bằng chứng độc lập chấp nhận được: câu hỏi thuộc dạng
kiểm tra tồn tại/không tồn tại (phân loại bằng code từ dạng câu hỏi, không phải
bằng cảm nhận của model), hoặc đường tính thứ hai độc lập (SQL-vs-Python) cũng
cho rỗng/0 với cùng lý do, hoặc LLM-judge riêng xác nhận "không có dòng nào" là
đáp án đúng. Không có bằng chứng nào trong 3 loại trên → abstain. Riêng
COUNT=0/SUM=NULL: vẫn qua gate share/margin như mọi đáp án khác, nhưng không được
miễn trừ khỏi gate rỗng một cách mù — phải phân biệt "0 là giá trị" với "0 dòng
là không có dữ liệu" (§4.6).
5. **Output là sentinel/lỗi/placeholder.** Bất kỳ output nào thuộc tập
`{"Error SQL", "--error--", "SELECT * FROM table_name", chuỗi lỗi thực thi, chuỗi
rỗng không giải thích được}` → abstain, không ghi. Đây là chặn cuối ở submission
writer, tương đương vị trí `RunManager.task_done` của CHESS (trước
`update_final_predictions`) và vị trí sau `vote_result()` của ReFoRCE (kiểm tra
sự tồn tại của `result.csv` cuối cùng).

**Tín hiệu phụ (chỉ dùng khi có, không bắt buộc):** nếu pipeline có UT-style
scoring như CHESS, thêm gate `norm = best_score / len(unit_tests_thực_tế)` và
`margin = top1 − top2` sau `pick_the_best_candidate` — nhưng phải gắn cờ riêng cho
3 nhánh suy biến (0 candidate / 1 candidate / 0 test), vì điểm 1 ở đó là giả tạo,
không phải confidence; và phải chuẩn hoá điểm (CHESS hiện cộng thô, không chia cho
số test). Nếu pipeline có nhiều model khác nhau như XiYan, thêm thứ hạng generator
đo trên dev làm tie-break **trước khi** abstain (không thay thế abstain).

**Thứ tự triển khai (rẻ trước, đắt sau):** (1) chặn cuối sentinel + all-error →
abstain (code thuần, 0 lần gọi model thêm); (2) gate share/margin/tie trên
vote/cluster đã có (code thuần, dùng lại file top-2 của CSC / `sorted_dict` của
ReFoRCE / `groupby` của XiYan — không cần thêm lần gọi model); (3) gate cluster
rỗng với bằng chứng độc lập (cần phân loại dạng câu hỏi bằng code + đường tính thứ
hai); (4) chỉ sau khi (1)–(3) bão hoà mới xét UT-style scoring hoặc selector LLM —
vì chúng tốn thêm lần gọi model và, theo bằng chứng CHESS, suy biến đúng ở các case
cần abstain nhất (≤1 candidate, 0 test, đồng thuận hoàn toàn).

### 4.8. Cảnh báo: vì sao vote share không phải là xác suất đã calibrate (đừng lấy τ = 0.5 làm hằng số)

- **Đồng loã (shared misunderstanding):** mọi candidate SQL trên cùng một engine,
cùng một schema linking, cùng một hiểu sai (sai join, sai filter, sai rule) sẽ
đồng thuận cao mà vẫn sai. Vote share đo "các candidate giống nhau", không đo
"candidate đúng". Đây là lý do SQL-vs-Python (hai đường tính độc lập) có giá trị
lý thuyết cao hơn vote SQL-vs-SQL — nhưng giá trị đó chưa được đo trong bất kỳ
codebase nào ở đây, nên không được dùng làm hệ số hiệu chỉnh cho tới khi đo được
tỷ lệ "SQL-vs-Python đồng thuận mà vẫn sai" trên dev có nhãn.
- **Nhiễu mẫu nhỏ:** với `|L| = 10` (XiYan) hay `num_votes = 3` (ReFoRCE default),
mỗi candidate là 10–33% share — ngưỡng 0.5 chỉ có 2–3 mức phân biệt. Tăng
`num_votes` lên 8 (như `run_main.sh`) giảm nhiễu nhưng nhân chi phí (8 pipeline ×
`max_iter` 5 × CE rerun) — cần cân bằng với ngân sách 6 giờ, bắt đầu từ 3 votes
rồi tăng khi còn dư giờ.
- **Hiệu ứng model nhỏ:** vote ở temperature 1 với model ≤15B sẽ làm tăng tỉ lệ hoà
và tỉ lệ "không có cặp bằng nhau" (rơi vào nhánh rỗng/final_choose của ReFoRCE) —
tức gate abstain sẽ kích hoạt thường xuyên hơn so với backbone lớn. Đó là hành vi
đúng dưới PA (thà bỏ qua còn hơn −1), nhưng phải đo abstain rate trên dev để tránh
abstain quá tay (PA = 0 cho mọi câu cũng không thắng được baseline trả lời).
- **Calibrate như thế nào (nguyên tắc, không phải hằng số):** trên dev có nhãn tách
theo business (hold-out 1–2 loại hình doanh nghiệp hoàn chỉnh để mô phỏng domain
shift, đúng yêu cầu của protocol), vẽ PA theo τ (và theo margin, và theo
empty-rule), chọn τ tối đa PA — không chọn τ theo cảm nhận, không chọn trên
public_test (không nhãn), không mượn τ từ BIRD/Spider. Mọi τ trong báo cáo này
(0.5, 0.5–0.7 cho UT norm, margin ≤1) đều là **điểm khởi đầu [INFERENCE]**, không
phải giá trị chốt.

### 4.9. Những gì KHÔNG được copy (danh sách cấm, có căn cứ code)

- **CHESS:** placeholder `"SELECT * FROM table_name"` điểm 0; điểm 1 giả tạo ở nhánh
1 candidate / 0 test; `pick_final_sql` chết; node `ExecutionAccuracy` cần gold
(không dùng cho private test); tie-break theo thứ tự chèn; `max_fixing` (không tồn
tại ở commit này — đừng trích).
- **CSC-SQL:** mặc định `return_random_one_when_all_errors=True` (nộp draft lỗi
ngẫu nhiên); fallback lặp top-1 n lần với `mode="major_vote"`; merge prompt cắt SQL
>500 ký tự / kết quả >20 dòng mà không báo; merge zero-shot không huấn luyện
(merge model của CSC được huấn luyện trên cặp top-2 có chèn gold — dùng prompt
merge với model chưa qua bước này là cơ chế khác, yếu hơn).
- **ReFoRCE:** Step 3/4 lấp đầy của `run_main.sh`; `random_vote_for_tie` (thực chất
là copy `first_key`, không phải random); `final_choose` (copy file đầu tiên);
`sys.exit(0)` trong `chat.py` khi trích block thất bại; nhánh `save_all_results`
dùng biến không tồn tại; `get_metadata.py` tạo metadata trỏ tới file không tồn tại.
- **DABstep:** prompt-only "Not Applicable" (không gate code);
`provide_final_answer` ép đoán khi hết steps; `open` chỉ-đọc ở mức hàm không thay
thế sandbox (và không có SQLite).
- **XiYan-SQL:** tie-break "SQL ngắn nhất" làm luật duy nhất; selection model
fine-tune (không có sẵn để tải dùng ngay trong các repo đã mở); refine 1 lần append
mù (kể cả bản refine vẫn lỗi); giả định "candidate lỗi đã bị loại" ở đầu Algorithm
3 trong khi Algorithm 2 append cả candidate lỗi; số BIRD/Spider (kể cả ~40.81
giây/sample và các ablation −3.13/−4.04/−1.24) để đặt kỳ vọng DataMate.

## 5. Module chuẩn hoá output bảng biểu (thiết kế code-level)

**Nguyên tắc 0** [INFERENCE]: chuẩn hoá là code xác định (deterministic), không
dùng LLM đoán. Nó chạy ở hai chỗ với hai mục đích khác nhau, **không được đồng
nhất**: (i) chuẩn hoá nội bộ để so sánh consensus (output các candidate có bằng
nhau không — heuristic của hệ thống, 04 đã nêu); (ii) chuẩn hoá cuối để khớp
evaluator (phải theo quy ước evaluator — phần lớn UNVERIFIED, xem dưới). Module
dưới đây thiết kế cho (ii), với mọi quy ước chưa verify đều có bước "đo trên gold
train" thay vì đoán, và mọi trường hợp mơ hồ không phân giải được đều có đường ra
là abstain (không đoán mò đáp án).

**Biểu diễn chuẩn (canonical value)** [INFERENCE]: mọi đáp án đi qua dạng chuẩn
trung gian trước khi mã hoá submission:

```
Canonical = (type, value, unit_hint, provenance_flags)
# type: number | percent | string | date | boolean | list | table
# value: Decimal (number/percent), str NFC-lowercase (string), ISO date (date),
# bool, list[Canonical], table = list[dict[str, Canonical]] (giữ thứ tự dòng gốc)
# unit_hint: đơn vị suy ra từ câu hỏi (VND, %,...), dùng để chọn nhánh chuẩn hoá
# provenance_flags: {merged_filled, header_guessed, ambiguous_parse,...}
```

`provenance_flags` không đi vào submission — nó đi vào audit log và vào **quyết
định abstain**: nếu flag `ambiguous_parse` bật trên đáp án chính (không phải field
phụ), hệ thống abstain thay vì nộp đáp án đoán (xem từng mục dưới).

### 5.1. Số âm: dấu trừ vs ngoặc đơn kế toán [INFERENCE]

```python
def parse_signed_number(raw: str) -> Decimal | Ambiguous:
s = raw.strip()
s = s.replace("\u2212", "-").replace("\u2013", "-").replace("\u2014", "-")
# Dạng kế toán: (1.234) = -1234. Chỉ áp khi nội dung trong ngoặc parse được
# thành số sau khi bỏ separator — nếu không parse được thì ngoặc là ghi chú,
# không phải số âm.
if s.startswith("(") and s.endswith(")"):
inner = parse_unsigned_number(s[1:-1])
return -inner if inner is not None else Ambiguous("paren_non_numeric")
# Dấu trừ ở cuối: 1234- = -1234 (định dạng xuất từ một số hệ kế toán)
if s.endswith("-") and not s.startswith("-"):
v = parse_unsigned_number(s[:-1])
return -v if v is not None else Ambiguous("trailing_minus_non_numeric")
return parse_unsigned_number(s) # parse_unsigned xử lý dấu trừ đầu + separator (§5.2)
```

Lưu ý: số âm trong đáp án DataMate có thể là kết quả tính (lỗ, giảm) — không được
"làm đẹp" thành số dương. Ngược lại, ngoặc đơn trong chuỗi (ví dụ tên sản phẩm
"(loại A)") không bao giờ đi qua hàm này vì hàm chỉ chạy trên field đã xác định là
số (theo type đáp án hoặc kiểu cột).

### 5.2. Tiền tệ VNĐ: separator, hậu tố, đơn vị [INFERENCE]

Quy ước Việt Nam phổ biến: chấm phân cách nghìn, phẩy thập phân (`1.234.567,89`),
hậu tố `đ / VNĐ / đồng / ₫`, đơn vị `nghìn / ngàn / triệu / tỷ`. Nhưng dữ liệu
thực tế có thể lẫn kiểu Mỹ (`1,234,567.89`). Thuật toán phân giải (thứ tự quan trọng):

```python
def parse_vnd(raw: str) -> Decimal | Ambiguous:
s = raw.strip()
# 1. Tách đơn vị nhân (phải làm TRƯỚC khi bỏ separator, vì "1,5 triệu" có phẩy thập phân)
mult = 1
for suffix, m in [("tỷ", 10**9), ("triệu", 10**6), ("nghìn", 10**3), ("ngàn", 10**3)]:
if s.endswith(suffix):
mult = m; s = s[:-len(suffix)].strip(); break
# "k" chỉ nhận khi đứng sau số và không có chữ khác (vd "50k"), nếu không thì ambiguous
# 2. Bỏ hậu tố tiền tệ (không phân biệt hoa thường, chuẩn NFC trước)
s = re.sub(r"\s*(đ|vnd|vnđ|đồng|₫)\s*$", "", s, flags=re.I)
# 3. Bỏ khoảng trắng/ngăn cách kiểu "1 234 567" (space, underscore, NBSP)
s = re.sub(r"[\s\u00a0_]", "", s)
# 4. Phân giải separator:
if "." in s and "," in s:
# Cả hai đều có: cái xuất hiện CUỐI là thập phân, cái còn lại là nghìn.
dec = "." if s.rfind(".") > s.rfind(",") else ","
elif s.count(".") > 1 or s.count(",") > 1:
dec = None # nhiều separator cùng loại -> toàn bộ là nghìn
elif "." in s or "," in s:
sep = "." if "." in s else ","
after = s.split(sep)[1]
# Một separator + đúng 3 chữ số sau + có chữ số trước -> nghìn (vd "1.234")
# Một separator + 1-2 chữ số sau -> thập phân (vd "1,5")
# Một separator + >3 chữ số sau -> thập phân (vd "1.23456" không phải nghìn)
dec = None if (len(after) == 3) else sep
else:
dec = None
if dec is None:
int_part = s.replace(".", "").replace(",", "")
return Decimal(int_part) * mult
int_part, frac_part = s.rsplit(dec, 1)
int_part = int_part.replace(".", "").replace(",", "")
return (Decimal(int_part + "." + frac_part)) * mult
```

**Các điểm phải đo trên gold train (không đoán)** [INFERENCE + hướng đo]:

- Gold answers cho câu tiền tệ dùng dạng nào (số thuần? kèm "đ"? đơn vị triệu/tỷ?)
— đếm trên `answers.jsonl` của train sau khi giải nén. Quy ước output của module
phải **khớp dạng gold**, không khớp thói quen người viết. Nếu gold dùng số thuần
(ví dụ `1234567`) thì module bỏ hậu tố/đơn vị và trả số thuần; nếu gold giữ đơn vị
thì module giữ nguyên đơn vị đó.
- Làm tròn: evaluator làm tròn number 2 chữ số [CODE_INSPECTED], nhưng **mode làm
tròn (half-up vs banker's) là UNVERIFIED**. Module dùng
`Decimal.quantize(0.01, ROUND_HALF_UP)` cho output (tránh lỗi float của `round()`
Python), và ghi rõ: nếu evaluator dùng banker's thì các case đúng-nửa (x.xx5) có
thể lệch — đo bằng cách so output module với gold train: nếu mọi gold đều khớp
half-up thì giữ, nếu có case lệch thì đổi mode và ghi lại.
- Trường hợp mơ hồ thật (`1.234` trong dữ liệu kiểu Mỹ lẫn kiểu Việt, không có
context): trả `Ambiguous` → abstain (nếu là đáp án chính) hoặc thử cả hai rồi
cross-check với dữ liệu khác (ví dụ: tổng các dòng phải khớp tổng đã biết — kiểm
tra độc lập, không phải đoán).

### 5.3. Tỷ lệ phần trăm: 12,5 vs 12,5% vs 0,125 [INFERENCE + UNVERIFIED]

**Điểm mấu chốt: format percent của evaluator là UNVERIFIED** (0–100 hay 0–1)
[CODE_INSPECTED: `competition/datamate.md` liệt kê là mục cần đối chiếu]. Vì vậy
module **không được hardcode một dạng**. Thiết kế:

```python
def normalize_percent(raw, question_text, gold_convention):
# gold_convention ĐÃ ĐO trên train (2026-10-28, [LOCALLY_VERIFIED] trên gold train):
# 'percent_0_100' — câu hỏi hỏi "là nhiêu %"/"bao nhiêu phần trăm" có gold 2.08,
# 1.21, 2.27 (thang 0–100, không phải 0–1). Nếu evaluator dùng thang khác với gold
# train thì encoder phải đổi — nhưng gold train là bằng chứng tốt nhất hiện có.
# Chỉ khi chưa đo mới dùng convention = UNKNOWN (chế độ "đo trước, nộp sau").
v = parse_number_loose(raw) # dùng §5.1 + §5.2 (bỏ dấu %, bỏ separator)
has_pct_sign = "%" in raw
# Chuẩn hoá về dạng "giá trị phần trăm" (vd 12.5 nghĩa là 12.5%):
if has_pct_sign:
pct = v # "12.5%" -> 12.5
elif looks_like_fraction(v, question_text):
pct = v * 100 # 0.125 + câu hỏi percent -> 12.5
else:
pct = v # 12.5 (không dấu) -> 12.5 theo mặc định VN
# Mã hoá cuối theo convention đã đo:
if gold_convention == "fraction_0_1":
return pct / 100 # -> 0.125
else: # 'percent_0_100'
return pct # -> 12.5
# Làm tròn cuối: 2 chữ số + đúng dấu [CODE_INSPECTED: percent khớp sau làm tròn
# 2 chữ số và đúng dấu]
```

`looks_like_fraction` heuristic (phải đo lại trên train, không coi là chân lý):
giá trị trong [0, 1] VÀ câu hỏi chứa từ chỉ tỉ lệ/phần trăm VÀ không có dấu % trong
dữ liệu gốc VÀ dữ liệu nguồn dùng tỉ lệ dạng thập phân (ví dụ cột tỉ lệ trong bảng
toàn giá trị < 1) → coi là fraction. Nếu heuristic không chắc chắn (giá trị trong
[0,1] nhưng không rõ là 0,5% hay 50%) → `Ambiguous` → abstain hoặc cross-check
bằng một đường tính khác (ví dụ: tỉ lệ = tử/mẫu tính lại từ dữ liệu thô — nếu
tử/mẫu cho 0,5 thì đáp án là 50%, không phải 0,5%).

**Quy tắc vàng:** với câu percent, **luôn tính lại tỉ lệ từ tử/mẫu thô khi có thể**
thay vì copy tỉ lệ có sẵn trong bảng — tỉ lệ copy có thể đã làm tròn, sai đơn vị,
hoặc tính trên mẫu khác. Cross-check này là một phần của cổng kiểm tra độc lập,
không phải của formatter.

### 5.4. Ngày tháng: dd/mm/yyyy vs yyyy-mm-dd vs âm lịch [INFERENCE + UNVERIFIED]

```python
def parse_date(raw: str) -> date | Ambiguous:
s = raw.strip()
# ISO trước: yyyy-mm-dd (không mơ hồ) — và Excel serial (xem §5.5 về serial).
if re.fullmatch(r"\d{4}-\d{2}-\d{2}", s):
return date.fromisoformat(s)
m = re.fullmatch(r"(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{2,4})", s)
if m:
a, b, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
y = 2000 + y if y < 100 else y
if a > 12 and b <= 12: return date(y, b, a) # chắc chắn dd/mm
if b > 12 and a <= 12: return date(y, a, b) # chắc chắn mm/dd
if a <= 12 and b <= 12:
# Mơ hồ (vd 03/04): mặc định dd/mm theo quy ước VN, NHƯNG gắn flag ambiguous.
return AmbiguousDate(date(y, b, a), flag="ddmm_vs_mmdd")
return Ambiguous("unparseable_date")
```

- **Mặc định dd/mm** cho trường hợp mơ hồ là quy ước Việt Nam, nhưng phải gắn flag:
nếu ngày này là đáp án chính (câu hỏi ngày) thì flag → abstain hoặc cross-check
bằng context khác (ví dụ: ngày trong cùng dòng dữ liệu có dạng ISO ở cột khác,
hoặc ngày phải nằm trong cửa sổ as-of/rulebook). Đừng nộp ngày mơ hồ mà không ghi flag.
- **Output date:** ISO `yyyy-mm-dd` theo quy ước formatter của repo (`format_date`
trong `research/datamate/code-notes.md` [CODE_INSPECTED] — lưu ý đây là quy ước
đề xuất của repo, chưa phải quy ước evaluator đã verify; nếu evaluator muốn dạng
khác thì encoder phải đổi, formatter nội bộ giữ ISO).
- **Tháng `yyyy-mm`:** câu hỏi theo tháng → output `yyyy-mm` (không thêm ngày 01 giả
tạo — ngày giả tạo là bịa dữ liệu).
- **Âm lịch / calendar.csv — thiết kế generic, KHÔNG bịa schema [UNVERIFIED]:**

```python
class LunarLookup:
# Schema calendar.csv ĐÃ XÁC MINH trên split train thật (2026-10-28,
# [LOCALLY_VERIFIED]): cột date,weekday,lunar_day,lunar_month,lunar_year,
# lunar_leap,holiday; phủ 2024-01-01–2027-12-31 (1461 dòng); weekday quan sát
# được 1=Thứ 2 (2024-01-01), 4=Thứ 5, 5=Thứ 6 — tức Thứ 2=1..Chủ nhật=7.
# Tết window tính trực tiếp từ cột lunar: 23 Chạp = (lunar_month=12,
# lunar_day=23); mùng 10 Tết = (lunar_month=1, lunar_day=10, lunar_year+1);
# cột holiday cũng ghi tên ngày lễ (vd "Tết Dương lịch"). Không cần đoán schema
# nữa — nhưng vẫn phải kiểm tra lại rằng split private dùng cùng schema này
# trước khi nộp (schema train không bảo đảm schema private).
def __init__(self, calendar_csv_path):
self.map = {} # solar_date -> (lunar_day, lunar_month, lunar_year, lunar_leap, holiday)
if calendar_csv_path is None: self.available = False; return
rows = read_csv(calendar_csv_path) # header phải đúng schema đã xác minh, xem §5.4
required = ["date", "lunar_day", "lunar_month", "lunar_year", "lunar_leap", "holiday"]
if any(c not in rows.header for c in required):
self.available = False # Schema khác với train -> KHÔNG đoán, KHÔNG tự sinh lịch
log("calendar.csv schema differs from verified train schema; lunar conversion unavailable")
return
self.available = True
for r in rows:
self.map[parse_date(r["date"])] = (r["lunar_day"], r["lunar_month"], r["lunar_year"], r["lunar_leap"], r["holiday"])
def to_lunar(self, solar):
if not self.available: return Unavailable("no_calendar")
return self.map.get(solar, Unavailable("date_not_in_calendar"))
def is_tet_window(self, solar):
# 23 Chạp (lunar_month=12, lunar_day>=23) tới mùng 10 Tết (lunar_month=1, lunar_day<=10, năm âm sau)
if not self.available: return Unavailable("no_calendar")
entry = self.map.get(solar)
if entry is None: return Unavailable("date_not_in_calendar")
ld, lm, ly, _, _ = entry
return (lm == 12 and ld >= 23) or (lm == 1 and ld <= 10)
```

Quy tắc sử dụng: câu hỏi cần âm lịch (Tết, 23 Chạp–mùng 10, tháng nhuận) mà
`available == False` hoặc ngày không có trong map → **abstain, không tự tính âm lịch
bằng thư viện TQ, không dùng lịch Trung Quốc thay lịch Việt** (nguyên tắc đã có
trong `research/datamate/code-notes.md` [CODE_INSPECTED]: lịch VN theo UTC+7, tháng
nhuận ~2–3 năm/lần, new moon lệch 1 ngày so với TQ là có thể). Thư viện chỉ là
fallback khi split không cung cấp calendar cho khoảng cần thiết, và phải log rõ "đã
dùng thư viện thay vì calendar.csv" (cùng doc). Mọi test Tết (2023: 22/01, 2024:
10/02, 2025: 29/01, 2026: 17/02 theo nguồn thứ cấp trong doc đó) phải đối chiếu lại
với calendar.csv thật trước khi tin.

### 5.5. Excel nhiều sheet: chọn sheet, merge cell, Excel serial [INFERENCE]

**Chọn sheet — hàm scoring, không lấy sheet đầu tiên mù** [INFERENCE]:

```python
def pick_sheet(workbook, question_text, required_columns):
# required_columns: các cột planner xác định là cần thiết (từ câu hỏi + rulebook)
cands = []
for ws in workbook.worksheets:
if ws.sheet_state!= "visible":
continue # sheet ẩn/veryHidden chỉ xét khi không còn sheet nào khác
header = detect_header(ws) # §5.6
name_score = keyword_overlap(normalize_vn(ws.title), question_text)
col_score = overlap(header, required_columns) # tỉ lệ cột cần thiết có mặt
row_score = min(1.0, ws.max_row / 1000) # tín hiệu yếu, tránh sheet rỗng
score = 0.4 * name_score + 0.5 * col_score + 0.1 * row_score
cands.append((score, ws))
cands.sort(reverse=True)
if not cands: return None
if len(cands) > 1 and (cands[0][0] - cands[1][0]) < 0.15:
return AmbiguousSheet(top2=cands[:2]) # chênh lệch nhỏ -> không chọn mù
return cands[0][1]
```

- `normalize_vn`: NFC + lowercase + bỏ dấu tiếng Việt (để "Doanh Thu" khớp
"doanh thu", "Hóa đơn" khớp "hoa don" nếu sheet đặt tên không dấu). Dùng bảng map
dấu chuẩn, không dùng LLM.
- Nếu `AmbiguousSheet`: thử cả hai sheet qua planner (mỗi sheet cho một candidate)
rồi để consensus + cổng bằng chứng quyết định — hoặc abstain nếu hai sheet cho
hai đáp án khác nhau và không phân biệt được. **Không mặc định lấy sheet đầu
tiên** (lỗi này đã được cảnh báo trong `research/datamate/code-notes.md`
[CODE_INSPECTED]: dòng đầu có thể là header lệch/merged/logo).
- Sheet ẩn: bỏ qua mặc định; nếu mọi sheet visible đều không có cột cần thiết thì
mới xét sheet ẩn (và log rõ).

**Merge cell — quy tắc phân biệt theo loại cột** [INFERENCE]:

```python
def unmerge_table(ws):
# Dùng openpyxl merged_cells ranges (đọc range, không đoán từ NaN).
table = read_values(ws) # pandas/openpyxl: merged -> chỉ top-left có giá trị, còn lại None
for (r1, c1, r2, c2) in ws.merged_cells.ranges:
top_left = table[r1][c1]
for r in range(r1, r2 + 1):
for c in range(c1, c2 + 1):
if (r, c) == (r1, c1): continue
if is_label_column(c): # cột phân loại/chuỗi (tên nhóm, loại, khu vực)
table[r][c] = top_left # fill-down: nhãn lặp lại là đúng ngữ nghĩa
flag(r, c, "merged_filled_label")
else: # cột số/ngày: KHÔNG fill (fill sẽ nhân đôi
table[r][c] = None # giá trị khi sum)
flag(r, c, "merged_numeric_left_empty")
return table
```

Lý do phân biệt: fill-down nhãn là an toàn (nhãn của nhóm áp cho mọi dòng trong
nhóm); fill-down số là sai nghiêm trọng (một giá trị 100 merge qua 3 dòng mà fill
thành 3×100 thì tổng sai gấp 3). Header merge nhiều dòng: gộp các phần header không
rỗng bằng `" / "` (ví dụ dòng 1 "Doanh thu" + dòng 2 "(triệu đồng)" → cột
`"Doanh thu / (triệu đồng)"` — và đơn vị trong header phải được parse theo §5.2,
không bỏ qua).

**Excel serial date** [INFERENCE]: số serial Excel (ngày = số ngày từ 1899-12-30, có
bug leap-year 1900 của Excel) phải convert qua hàm chuyên dụng (openpyxl
`from_excel` hoặc tự implement với epoch 1899-12-30 và ngoại lệ 1900) — không được
coi serial là số thuần. Cột nào là ngày phải xác định từ header/kiểu ô
(number_format chứa ngày) hoặc từ rulebook, không đoán từ giá trị (số 45000 có thể
là serial ngày hoặc là tiền).

### 5.6. Thiếu header: phát hiện header row bằng rule, LLM chỉ là fallback [INFERENCE]

```python
def detect_header(ws, max_scan=10):
# Quét max_scan dòng đầu, chấm điểm từng dòng làm header ứng viên.
best = None
for r in range(1, max_scan + 1):
cells = row_values(ws, r)
non_empty = [c for c in cells if c is not None and str(c).strip()!= ""]
if not non_empty: continue
str_frac = mean(1 for c in non_empty if isinstance(c, str)) # header thường là chuỗi
distinct = len(set(normalize(c) for c in non_empty)) / len(non_empty)
known_kw = overlap(normalize_list(non_empty), KNOWN_COLUMN_KEYWORDS)
numeric_frac = mean(1 for c in non_empty if isinstance(c, (int, float)))
score = 0.4 * str_frac + 0.3 * distinct + 0.2 * known_kw - 0.5 * numeric_frac
# Phạt dòng toàn số (đó là dữ liệu, không phải header) và dòng ít ô (tiêu đề/logo).
if len(non_empty) >= 2 and score > best_score: best = (r, score)
if best is None or best.score < 0.5:
# Fallback ladder: (1) thử LLM chỉ định dòng header (tốn 1 call, log rõ);
# (2) nếu vẫn không có: lấy dòng 1 làm header + flag header_guessed (gây abstain
# nếu đáp án phụ thuộc cột bị đoán); (3) nếu mọi dòng đều số -> header tổng hợp
# col_0, col_1,... + flag header_synthetic.
return fallback_header(ws)
return best.row
```

- `KNOWN_COLUMN_KEYWORDS`: tập từ khoá cột học từ profiler trên train (tên cột thật
trong dữ liệu: ngày, mã, tên, số lượng, đơn giá, thành tiền, trạng thái, …) — học
từ dữ liệu, không hardcode danh sách đóng. Ngưỡng 0,5 và trọng số trên là điểm khởi
đầu, phải tune trên train (đếm tỉ lệ detect đúng trên các file train có header lệch
đã biết).
- **Multi-row header:** nếu dòng k được chọn làm header nhưng dòng k+1 cũng có
str_frac cao và chứa đơn vị/ghi chú (ví dụ "(triệu đồng)", "(%)"), gộp hai dòng
thành header (xem §5.5). Không bỏ dòng k+1 mù (đơn vị trong đó quyết định §5.2/§5.3).
- **Dòng tiêu đề/logo:** dòng chỉ có 1 ô không rỗng, hoặc chứa từ khoá tiêu đề ("CÔNG
TY", "BÁO CÁO", "BẢNG") và không có từ khoá cột → bỏ qua, không tính là header.
- Flag `header_guessed`/`header_synthetic` đi vào audit và vào quyết định: nếu đáp
án phụ thuộc vào cột mà header bị đoán (không chắc), hệ thống abstain thay vì nộp
đáp án từ cột đoán.

### 5.7. Đáp án dạng table/list — thứ tự và tập hợp [INFERENCE + UNVERIFIED]

- Giữ **thứ tự dòng gốc** của dữ liệu, không sort trừ khi câu hỏi yêu cầu sort tường
minh ("sắp xếp theo…", "top N"). Lý do: semantics "rows as set" của evaluator là
UNVERIFIED [CODE_INSPECTED] — nếu evaluator so sánh có thứ tự mà mình sort sai thì
mất điểm oan; nếu evaluator so sánh dạng set thì giữ thứ tự gốc cũng không mất
điểm. Giữ gốc là chiến lược an toàn dưới cả hai giả thuyết.
- Chuẩn hoá tên cột của table output: NFC + lowercase theo quy ước string của
evaluator [CODE_INSPECTED] (phần string đã verify; phần tên cột table thì chưa
verify riêng — ghi rõ).
- List: giữ thứ tự; nếu câu hỏi hỏi "liệt kê" mà không nói thứ tự, vẫn giữ thứ tự
xuất hiện trong dữ liệu (không sort alphabet mù).

## 6. Rủi ro còn lại (chưa giải quyết trong tài liệu này)

1. **Mã hoá abstain chưa verify.** Tầng quyết định tách khỏi tầng encoder là đúng,
nhưng giá trị/mã cụ thể để nộp "abstain" (bỏ trống? chuỗi đặc biệt? field riêng?)
và cách evaluator xử lý missing answer / unanswerable-ngược đều UNVERIFIED
[CODE_INSPECTED]. Đây là blocker trước submission: phải đọc evaluator/README thật
trước khi khoá encoder. Cho tới lúc đó, mọi PA đo trên train_holdout đều giả định
abstain = 0 (theo định nghĩa PA) — nếu encoder sai thì PA thật khác.
2. **Format percent đã xác minh trên gold train (thang 0–100); mode làm tròn vẫn
chưa verify.** Gold percent train: câu hỏi "là nhiêu %"/"bao nhiêu phần trăm" có
gold 2.08, 1.21, 2.27 — thang 0–100 [LOCALLY_VERIFIED]. Mode làm tròn (half-up vs
banker's) vẫn UNVERIFIED: module dùng `ROUND_HALF_UP`, phải đo bằng cách so output
với gold train (nếu có case lệch đúng-nửa thì đổi mode và ghi lại). Mode làm tròn
là blocker còn lại cho câu percent, không phải format thang đo nữa.
3. **Schema calendar.csv đã xác minh trên train; còn phải xác nhận lại trên split
private.** Train: cột `date,weekday,lunar_day,lunar_month,lunar_year,lunar_leap,
holiday`, phủ 2024-01-01–2027-12-31 [LOCALLY_VERIFIED]. Module §5.4 đã viết theo
schema này. Rủi ro còn lại: split private có thể dùng schema khác — kiểm tra lại
trước khi nộp, không giả định schema train = schema private.
4. **Business type: đã xác minh là KHÔNG có field tường minh — LOBO chạy nhánh
pseudo-type.** README từng business không có field type [LOCALLY_VERIFIED]; LOBO
chạy trên pseudo-type (§3.4) — kết quả yếu hơn type thật và phải báo rõ là
pseudo-type. Việc còn lại: suy ra pseudo-type cho 30 business train (schema
fingerprint + từ khoá README) trước khi chạy LOBO.
5. **Threshold transfer dưới shift chỉ được giảm nhẹ, không được loại bỏ.** δ LOBO
đo được trên type train, nhưng private type có thể shift mạnh hơn mọi type train
(bias lớn hơn δ đã đo). Biện pháp bổ sung duy nhất có cơ sở: evidence-gating
(abstain khi evidence coverage thấp bất thường so với phân phối train — tín hiệu
đo được trên type mới mà không cần nhãn, như 04 §3.5 đã nêu) + δ thận trọng
(worst-case thay vì mean khi m nhỏ). Không có cách nào đảm bảo δ đủ cho type chưa
từng thấy.
6. **Consensus tương quan (fan trap, sai rule chung, sai cửa sổ).** Tài liệu này
không giải quyết — nó thuộc về cổng kiểm tra độc lập và rule assertion (04
§2.4/§2.6). Calibrator học trên train_cal cũng không sửa được lỗi hệ thống mà
train_cal không chứa (ví dụ: rule mới chỉ xuất hiện ở private). Đây là rủi ro dư
không thể triệt tiêu bằng calibration.
7. **Độ hạt của k = 3 và chi phí tín hiệu.** Vote share 4 bậc, cross-path tốn sinh +
thực thi, logprobs tốn payload — tất cả đều ăn vào trần 6 giờ [CODE_INSPECTED].
Chưa có số đo latency thật nên chưa chốt được k, có/không second path, có/không
logprobs. Đo latency trên checkpoint thật là bước bắt buộc trước khi khoá kiến
trúc tín hiệu.
8. **Nhiễu ước lượng khi cal/type ít mẫu.** Ngưỡng, map calibration, ECE, và PA
per-type đều nhiễu khi mẫu ít. Tài liệu này đưa ra LCB và min-support, nhưng
không thay thế được việc cần đủ dữ liệu: nếu một type chỉ có vài chục câu, mọi
kết luận về type đó đều yếu và phải ghi rõ khoảng tin cậy.
9. **Temperature scaling không sửa được shift.** Demo §1.6 cho thấy T* giảm ECE
nhưng không về 0 dưới bias cộng. Đừng dùng temperature scaling như "thuốc chữa
overconfidence dưới shift" — nó chỉ hiệu chỉnh trong-phân-phối. Dưới shift,
margin δ + evidence-gating mới là công cụ đúng.
10. **Table/list semantics chưa verify.** Thứ tự dòng, tên cột, "rows as set" đều
chưa có đáp án từ evaluator. Chiến lược giữ thứ tự gốc (§5.7) là an toàn nhất
trong các lựa chọn hiện có, nhưng vẫn là giả thuyết cho tới khi đọc evaluator.
11. **Bước xác minh đầu tiên — ĐÃ THỰC HIỆN ngày 2026-10-28 [LOCALLY_VERIFIED]
(không còn là bước "khi có dữ liệu"):** đã tải và giải nén `train.zip`
(128.118.095 bytes) và `public_test.zip` (64.149.714 bytes) từ đường dẫn trong
`competition/datamate.md`, liệt kê file từng split. Kết quả kiểm kê:
- Train: 3000 câu hỏi / 3000 đáp án, 30 business (biz_101–biz_130; phần lớn
  118–119 câu, 7 business có 40 câu: biz_101, 107, 110, 113, 114, 125, 126).
  Phân bố loại đáp án: number 1884, percent 578, string 88, list 193,
  unanswerable 70 (answer null), date 145, table 19, boolean 23.
- Public test: 1000 câu hỏi, 14 business (dev_001–dev_014), **không có
  `answers.jsonl`** — giao thức "không bao giờ dùng public_test để tune" trong tài
  liệu này **đứng vững, không cần viết lại**.
- Định dạng file train: 99 xlsx, 20 csv, 1 sqlite (biz_123/pos.sqlite, 18,6MB) —
  Excel chiếm đa số tuyệt đối, module §5.5 (sheet scoring, merge, header) là đúng
  trọng tâm; SQLite chỉ là trường hợp lẻ.
- Schema `calendar.csv`: `date,weekday,lunar_day,lunar_month,lunar_year,lunar_leap,
  holiday`, phủ 2024-01-01–2027-12-31 (1461 dòng) — xem §5.4.
- Dạng gold: percent thang 0–100 (xem §5.3); number là số thuần dạng chuỗi
  ('89526400', '7574100', '23'), không kèm đơn vị/hậu tố; date ISO cả hai dạng
  `yyyy-mm-dd` và `yyyy-mm` ('2025-12', '2025-10').
- Field type: **không có** trong README từng business — LOBO chạy nhánh pseudo-type
  (§3.4). Câu hỏi có keys `id, business_id, question, as_of_date`; đáp án có keys
  `id, type, answer, alias`.
- Hệ quả ngân sách: nếu private test cùng quy mô public_test (~1000 câu) thì trần
  6 giờ = 21.600 giây cho trung bình **21,6 giây/câu** — thấp hơn nhiều so với
  ~40,81 giây/sample của XiYan trên BIRD dev (xem §4.5). Mọi kiến trúc tín hiệu
  phải đo lại với mốc 21,6 giây/câu này, không lấy 40,81 giây làm chuẩn.
- Việc còn lại của bước này: suy ra pseudo-type cho 30 business train (schema
  fingerprint + từ khoá README) trước khi chạy LOBO; và kiểm tra lại rằng split
  private dùng cùng schema calendar/file như train trước khi nộp.
