# Phân bố lỗi / biểu thức cần grounding trên tập train LifeMate (E-asr-1)

> Audit đợt 5, chạy ngày 2026-10-28 bằng script `analysis/e_asr_1_audit.py`
> (stdlib thuần, không model, không đọc `train_environment/` hay `state.json`).
> Lệnh chạy lại:
> `python3 analysis/e_asr_1_audit.py --train-jsonl <đường dẫn tới train.jsonl>`
>
> **Hiệu chỉnh số mẫu trước mọi con số:** yêu cầu đợt 5 ghi "459 mẫu train",
> nhưng file `train/train.jsonl` thật có **1545 mẫu**, không phải 459. Con số 459
> trùng với số **monitored writes trên DEV** của E7 phase 0 (459/511 arguments
> trên 1237 mẫu dev), không phải số mẫu train. Audit này đếm trên **toàn bộ 1545
> mẫu train** — vì E-asr-1 theo roadmap là "đếm trên train". Nếu anh thực sự muốn
> một tập con 459 mẫu nào đó, cho em định nghĩa tập con đó (lọc theo tiêu chí gì)
> và em chạy lại đúng tập đó; đừng ngầm hiểu 459 là toàn bộ train.

## 0. Kết quả headline (mẫu = 1545)

| Nhóm | Mẫu (current) | % | Mẫu (current + history user) | % |
|---|---|---|---|---|
| Số/tiền đọc bằng chữ — broad (bất kỳ từ số nào) | 807 | 52,2% | 1047 | 67,8% |
| Số/tiền đọc bằng chữ — strong (chỉ từ số mạnh, xem §1) | 279 | 18,1% | — | — |
| Số/tiền: chữ số + đơn vị từ ("50 nghìn", "50k") | 56 | 3,6% | — | — |
| Số/tiền: từ số + đơn vị lớn ("trăm/nghìn/triệu/tỷ") | 137 | 8,9% | — | — |
| Biểu thức thời gian tương đối | 599 | 38,8% | 940 | 60,8% |
| Trong đó: daypart mơ hồ (sáng/chiều/tối + mai/nay — chỉ cho DATE, thiếu hour) | 294 | 19,0% | — | — |
| Trong đó: thứ trong tuần | 70 | 4,5% | — | — |
| Trong đó: lệch ngày ("mai", "hôm qua", "N ngày nữa") | 224 | 14,5% | — | — |
| Trong đó: lệch tuần/tháng | 94 | 6,1% | — | — |
| Gold có `contacts.search` | 224 | 14,5% | — | — |
| Gold có arg `contact_id` | 134 | 8,7% | — | — |
| Gold có `contact_id` nhưng KHÔNG có `contacts.search` cùng mẫu | 24 | 1,6% | — | — |
| Gold có arg `amount` | 109 | 7,1% | — | — |
| Gold có arg thời gian (`time`/`date`/`start`/`end`) | 386 | 25,0% | — | — |
| Gold có `sys.ask_missing_info` | 217 | 14,0% | — | — |
| Gold đúng 1 ask duy nhất | 60 | 3,9% | — | — |

Đọc nhanh: **vague-daypart 19,0%** là nhóm lớn nhất có hành vi quyết định rõ ràng
(thiếu hour → ask hour, đúng ranh giới date-vs-hour của E7); **strong number-word
18,1%** là nhóm mà parser typed phải xử lý đầu tiên; **contacts.search 14,5%** là
nhóm mà bộ lọc tên phải xử lý. Ba nhóm này — không phải "mọi từ số" broad 52,2% —
là thứ tự ưu tiên làm module đợt 5.

## 1. Số/tiền đọc bằng chữ — broad là upper bound, strong mới là lõi

Broad 807 mẫu (52,2%) đếm **bất kỳ token từ số nào**, kể cả "một" làm mạo từ
("nhắn một tin", "một người") — không phải lúc nào "một" cũng là số lượng. Vì vậy
52,2% là **cận trên**, không phải tỉ lệ "cần parse số". Ba lát cắt chính xác hơn:

- **Strong 279 mẫu (18,1%):** mẫu có ít nhất một token gần như luôn là số:
  `trăm, nghìn, ngàn, triệu, tỷ, tỉ, mươi, chục, rưỡi`. Đây là lõi mà parser typed
  phải pass trước — mọi token này đều gắn với giá trị số hoặc đơn vị.
- **Chữ số + đơn vị từ 56 mẫu (3,6%):** "50 nghìn", "2 triệu", "50k" — số đã là chữ
  số nhưng đơn vị vẫn là từ, vẫn cần nhân đơn vị trước khi so sánh (150 nghìn ≠
  150 ≠ 150 triệu).
- **Chỉ toàn "một" 106 mẫu (6,9%):** mẫu mà từ số duy nhất là "một" — lát cắt dễ
  nhiễm mạo từ nhất, cần phân biệt "một" = số lượng vs "một" = mạo từ bằng context
  (vd "một nửa" là số, "một tin" là mạo từ). Parser đợt 5 xử lý "một" theo cụm
  ("một nửa", "một trăm", "một nghìn") chứ không đếm token "một" đơn lẻ.

Top token từ số trong current text (số lần xuất hiện, không phải số mẫu):

| Token | Lần | Ghi chú |
|---|---|---|
| một | 246 | Nhiễm mạo từ mạnh nhất — xem lát cắt "chỉ toàn một" ở trên |
| hai | 236 | Đã loại "thứ hai" (Wednesday) nhờ consumed spans |
| ba | 114 | Đã loại "thứ ba" |
| bốn | 110 | |
| năm | 101 | Đã loại "thứ năm" và "năm nay/sau/trước" (year) |
| trăm | 100 | Strong |
| tám | 89 | |
| nghìn | 82 | Strong |
| sáu | 79 | |
| mười | 77 | |
| chín | 76 | |
| rưỡi | 75 | Strong (+0,5 đơn vị trước đó) |
| mươi | 53 | Strong |
| lăm | 40 | Biến thể sau "mươi" |
| chục | 25 | Strong |
| tư | 5 | Chỉ đếm khi không nằm trong "thứ tư" |
| tỷ / tỉ | 4 / 1 | Hiếm trong current text (hay nằm trong tên sản phẩm hơn là số tiền) |

Giao với gold: 91 mẫu (5,9%) vừa có từ số trong current text vừa có arg `amount`
trong gold — đây là tập **repair-relevant trực tiếp** (số phải parse từ lời nói
thành giá trị cho call). Ngược lại, 18 mẫu (1,2%) có arg `amount` trong gold nhưng
current text không có từ số nào — số lượng ở đó đến từ chữ số trong text, từ
history, hoặc từ observation (read trước). Parser không được giả định "amount luôn
đi kèm từ số".

## 2. Thời gian tương đối — daypart mơ hồ là nhóm lớn nhất có luật rõ

599 mẫu current (38,8%) chứa ít nhất một biểu thức thời gian tương đối; cộng
history user turns thì 940 mẫu (60,8%) — thời gian tương đối không phải edge case,
nó là **hình thái mặc định** của cách người dùng nói về thời gian. Top biểu thức
trong current text (số lần xuất hiện):

| Biểu thức | Lần | Nhóm |
|---|---|---|
| mai (đứng riêng) | 169 | Lệch ngày — dạng dominant, KHÔNG phải "ngày mai" (chỉ 2 lần) |
| sáng mai | 129 | Daypart mơ hồ — chỉ cho DATE, thiếu hour |
| tháng này | 69 | Lệch tháng |
| tối nay | 58 | Daypart mơ hồ |
| chiều nay | 51 | Daypart mơ hồ |
| hôm nay | 40 | Lệch ngày |
| sáng nay | 26 | Daypart mơ hồ |
| tối mai | 24 | Daypart mơ hồ |
| tuần sau | 19 | Lệch tuần |
| chiều mai | 15 | Daypart mơ hồ |
| hôm qua | 15 | Lệch ngày |
| thứ hai | 14 | Thứ trong tuần |
| thứ bảy | 13 | Thứ trong tuần |
| thứ sáu | 12 | Thứ trong tuần |
| thứ ba | 11 | Thứ trong tuần |
| thứ tư | 11 | Thứ trong tuần |
| thứ năm | 8 | Thứ trong tuần |
| tuần này | 7 | Lệch tuần |
| mốt | 7 | Lệch ngày |
| cuối tuần | 7 | Lệch tuần |
| chủ nhật | 6 | Thứ trong tuần |
| tháng sau | 3 | Lệch tháng |
| ngày mai | 2 | Lệch ngày |
| hôm kia / ngày kia | 2 / 2 | Lệch ngày |
| cuối tháng / đầu tuần / tuần trước | 2 / 1 / 1 | Lệch tuần/tháng |

Hệ quả thiết kế (đã đưa vào module đợt 5):

1. **Daypart mơ hồ 294 mẫu (19,0%)** — cứ 5 request thì gần 1 cái chỉ nói
   "sáng mai / chiều nay / tối mai" mà không có hour. Theo ranh giới date-vs-hour
   của E7: daypart cho DATE (ngày suy ra được), hour vẫn thiếu → **ask hour** là
   hành vi đúng, không phải fill hour từ current_time hay history. Đây là nhóm
   E5/E7 đã gặp ở dạng lẻ tẻ; audit cho thấy nó chiếm gần 1/5 train.
2. **"mai" đứng riêng (169 lần) là dạng dominant**, "ngày mai" chỉ 2 lần. Resolver
   phải xử lý "mai" trần như tomorrow, không được chỉ nhận dạng "ngày mai".
3. **262 mẫu (17,0%)** vừa có biểu thức tương đối trong current text vừa có arg
   thời gian trong gold — tập mà resolver ngày phải pass để write đúng (còn lại:
   biểu thức tương đối nhưng gold không có arg thời gian = câu hỏi/tham chiếu,
   không phải slot cần resolve).
4. Thứ trong tuần chỉ 70 mẫu (4,5%) — nhỏ nhưng bắt buộc phải đúng (weekday
   "thứ hai tới" cần neo vào current_time, không đoán từ wall-clock).

## 3. Danh bạ: tra cứu, trùng tên, viết tắt

- **224 mẫu (14,5%)** có `contacts.search` trong gold; tổng 234 lượt search.
  Phân bố số token của query: 0 token (query rỗng) 30 lượt, 1 token 142 lượt
  (60,7%), 2 token 54 lượt, 3 token 7 lượt, 4 token 1 lượt. Query rỗng 30 lượt là
  pattern đáng chú ý (search không query = liệt kê/duyệt danh bạ, hoặc gold artifact
  — cần xem riêng khi làm bộ lọc, không tự suy diễn).
- **Top query** (số lượt): Lan 35, Minh 33, (rỗng) 30, Sếp Dũng 18, Tuấn 16,
  Bố 15, Hương 15, Mẹ 9, Bác Ba 7, Cô giáo Mai 6. Dataset dùng lại một số tên
  xuyên suốt (Lan, Minh) — bộ lọc tên phải xử lý tên phổ biến, không phải tên hiếm
  một lần.
- **134 mẫu (8,7%)** có arg `contact_id` trong gold; **24 mẫu (1,6%)** có
  `contact_id` nhưng không có `contacts.search` cùng mẫu — ID lấy từ
  history/context chứ không phải từ search trong lượt này (đúng pattern E1 đã thấy:
  entity từ history). Bộ lọc phải chấp nhận ID từ history là nguồn hợp lệ, không
  bắt buộc mọi ID đều phải qua search trong cùng lượt.
- **Trùng tên: KHÔNG ĐO ĐƯỢC từ `audio_text` + `label.tool_calls`.** Tỉ lệ trùng
  tên thật (cùng một tên → 2+ ID khác nhau trong roster của đúng mẫu đó) cần roster
  từng mẫu, mà roster nằm trong `train_environment/` — audit này cố tình không đọc
  file đó (luật thi: mọi truy cập state phải qua ToolEnv). Con số duy nhất liên
  quan đo được ở đây là 24 mẫu contact_id-without-search (ID ngoài lượt search),
  nhưng đó KHÔNG phải tỉ lệ trùng tên — đừng trích nó thành tỉ lệ trùng tên.
- **Viết tắt: cũng KHÔNG ĐO ĐƯỢC từ hai trường này.** Proxy yếu nhất: 142 lượt
  query 1 token — nhưng 1 token bao gồm cả tên đầy đủ dạng một từ (Lan, Minh) và
  từ thân mật (Bố, Mẹ), không phải viết tắt. Viết tắt thật (initials, substring của
  tên đầy đủ) chỉ xác minh được khi đối chiếu query với display name trả về từ
  roster — tức cần pass ToolEnv.
- **Bước đo tiếp theo (đề xuất, chưa làm trong đợt 5 này):** pass ToolEnv-based —
  replay gold `contacts.search` qua ToolEnv (đường truy cập state hợp lệ duy nhất),
  đối chiếu query với danh sách trả về: (a) đếm mẫu có ≥2 contact cùng tên chuẩn
  hoá khác ID → tỉ lệ trùng tên thật; (b) đếm query là initials/substring của
  đúng 1 display name → tỉ lệ viết tắt thật. Không đọc trực tiếp
  `train_environment/` ở bất kỳ bước nào.

## 4. Bối cảnh gold ask

217 mẫu (14,0%) có `sys.ask_missing_info` trong gold; 60 mẫu (3,9%) có đúng 1 ask
duy nhất. Tức ask là hành vi gold có thật nhưng thiểu số — phần lớn gold là write
hoặc read. Điều này khớp với luật kỳ vọng của round 4: ask trên mẫu gold-write = 0
điểm, nên repair có bằng chứng luôn ≥ ask; ask chỉ đúng khi thông tin genuinely
missing (daypart thiếu hour là trường hợp điển hình, §2).

## 5. Phương pháp (để tái lập và để bắt lỗi audit)

- Nguồn text: current `audio_text` + history **user turns** (`audio_text`).
  Assistant text và tool_results trong history bị loại (đó là output hệ thống,
  không phải lời người dùng — đếm chúng sẽ thổi phồng số từ số/giờ, vd alarm
  06:15 trong tool_results).
- Chuẩn hoá: NFC + lowercase, **giữ dấu thanh** (không fold). Fold dấu sẽ gộp từ
  khác nghĩa và phá tone-digit — audit đếm từ, không đếm âm.
- Khớp biểu thức: token hoá thành token chữ/số unicode; khớp cụm token theo thứ tự
  dài trước, không chồng lấp ("ngày mai" = 1 match, không phải "ngày mai" + "mai";
  "thứ hai" không đếm "hai" làm từ số).
- Loại trừ đã áp dụng: token từ số ngay sau "tháng" bị bỏ (tên tháng: "tháng một"
  = January); token từ số nằm trong cụm thời gian đã khớp bị bỏ ("thứ tư" không
  đếm "tư").
- Giới hạn đã biết: (1) broad number-word là cận trên (nhiễm "một" làm mạo từ) —
  dùng lát cắt strong 18,1% cho quyết định; (2) "mai" đứng riêng được đếm là
  tomorrow — trong dataset này đúng với đa số ngữ cảnh, nhưng có thể có trường hợp
  "mai" là tên riêng (vd "cô Mai") — audit không phân biệt được "mai" là ngày hay
  tên khi đứng riêng; con số 169 lần "mai" vì vậy cũng là cận trên nhẹ; (3) query
  rỗng 30 lượt chưa phân loại nguyên nhân; (4) trùng tên và viết tắt chưa đo được
  (§3) — cần pass ToolEnv riêng.
