# Audit roster danh bạ qua ToolEnv (đợt 6)

> Chạy ngày 2026-10-28 bằng script `analysis/contacts_roster_replay.py`.
> Mọi quan sát roster đều đến từ `zaic_tools.ToolEnv('train', id).call(
> 'contacts.search', gold_args)` — đường truy cập state hợp lệ duy nhất của
> BTC. Script **không mở trực tiếp** `train_environment/` hay `state.json` ở
> bất kỳ bước nào. Số điện thoại bị loại khỏi bản ghi lưu trữ (chỉ giữ id,
> name, relation, local-only, không push).
>
> Phạm vi: chỉ 224/1545 mẫu có gold `contacts.search` mới quan sát được roster
> (234 lượt search). 1321 mẫu còn lại không có gold search nên roster của
> chúng không được đo — audit này **không tự bịa query** để lục roster các mẫu
> đó. Mọi tỉ lệ dưới đây có mẫu số ghi rõ.

## 0. Kết quả headline

| Đo | Số | Mẫu số | Tỉ lệ |
|---|---|---|---|
| Mẫu có gold `contacts.search` | 224 | 1545 mẫu train | 14,5% |
| Lượt gold search đã replay | 234 | — | — |
| Search trả về đúng 1 contact | 131 | 234 lượt | 56,0% |
| Search trả về 2 contact | 72 | 234 lượt | 30,8% |
| Search trả về ≥3 contact | 31 | 234 lượt | 13,2% (30 lượt là query rỗng = cả address book) |
| Search có trùng tên trong kết quả trả về (cùng tên chuẩn hoá, khác id) | 73 | 234 lượt | **31,2%** |
| Trong đó: tên trùng = đúng query | 68 | 73 lượt trùng | 93,2% |
| Mẫu query rỗng (full book) có trùng tên | 5 | 30 mẫu | 16,7% |
| Query là tên đầy đủ chính xác (exact) | 204 | 234 lượt | 87,2% |
| Query rỗng | 30 | 234 lượt | 12,8% |
| Query là first-word / initials / substring / relation / phone / nomatch | 0 | 234 lượt | **0%** |
| Search-then-use (gold dùng `contact_id` sau search) | 120 | 234 lượt | 51,3% |
| Trong đó id được dùng nằm trong kết quả search trả về | 111 | 120 cặp | 92,5% |
| Trong đó id được dùng KHÔNG nằm trong kết quả trả về | 9 | 120 cặp | 7,5% |
| Sau search trùng tên, gold gọi tiếp `sys.ask_missing_info` | 69 | 73 lượt trùng | **94,5%** |
| Sau search không trùng, gold dùng `contact_id` ngay | 108 | 161 lượt không trùng | 67,1% |

## 1. Trùng tên thật: phổ biến, và gold xử lý bằng ASK

**31,2% lượt search (73/234) trả về ≥2 contact cùng tên chuẩn hoá khác id.**
Dạng điển hình: query "Minh" trả về hai "Minh" (c_05, c_08) trong cùng một roster;
query "Lan" trả về hai "Lan" (c_05, c_10). 68/73 trường hợp tên trùng chính là
tên query — tức agent đối mặt trực tiếp với "có 2 Minh, chọn ai?" chứ không
phải trùng tên của một người khác trong danh sách.

Bằng chứng gold tự xác nhận luật xử lý trùng tên:

- Sau search trùng tên, gold gọi tiếp `sys.ask_missing_info` trong **69/73
  trường hợp (94,5%)**, và ask đó xin đúng slot contact của call đích:
  `phone.call/contact_id` (38), `sms.send/contact_id` (26),
  `email.create_draft/to` (3), `ewallet.transfer/contact_id` (1),
  `contacts.update/contact_id` (1). Tức gold KHÔNG đoán một trong hai "Minh"
  — gold hỏi lại. Đây là xác nhận trực tiếp cho luật `duplicate_name →
  AMBIGUOUS → ask` của `ContactFilter` đợt 5.
- 2 trường hợp còn lại sau trùng tên gold dùng `contact_id` ngay (n=2, đều là
  id đầu tiên trong kết quả trả về) — quá ít để kết luận "chọn đầu tiên là
  đúng" (2/2 nhưng n=2 không có ý nghĩa thống kê, và 69 ask đối chứng cho thấy
  policy chuẩn là ask).
- Query rỗng (full book) cũng có trùng tên ở 5/30 mẫu (16,7%) — trùng tên là
  thuộc tính của roster, không phải artifact của query.

Hệ quả: **không bao giờ ground lặng khi tên trùng**. Mọi policy "chọn đầu
tiên", "chọn contact có relation giống nhất", hay "chọn theo history" đều cần
bằng chứng riêng trước khi dùng; mặc định là ask.

## 2. Viết tắt thật: 0% trong gold — và vì sao vẫn giữ luật abbreviation

**Không có lượt gold search nào dùng viết tắt hay initials**: 204 lượt exact
(tên đầy đủ, kể cả tên một từ như "Lan", "Minh" — đó là tên đầy đủ của contact
một từ, không phải viết tắt), 30 lượt rỗng, 0 lượt first-word/initials/
substring/relation/phone/nomatch. Nói cách khác, gold search luôn dùng tên đầy
đủ chính xác; không có bằng chứng gold nào cho thấy người dùng (qua transcript
sạch) viết tắt tên khi search.

Điều này KHÔNG có nghĩa luật abbreviation trong `ContactFilter` là sai — nó có
nghĩa luật đó **chưa được gold kiểm chứng** (zero positive examples). Nó tồn
tại cho deployment, nơi input là ASR (có thể mất dấu, cụt từ) chứ không phải
transcript sạch của gold. Vì vậy:

- Giữ luật abbreviation, nhưng ghi rõ trạng thái: **UNVALIDATED on gold**.
- Luật chỉ kích hoạt khi fuzzy không kích hoạt VÀ đúng 1 ứng viên khớp initials/
  substring — tức nó không thể override một exact match hay một fuzzy match
  tốt. Rủi ro còn lại duy nhất là abbreviation khớp 1 ứng viên nhưng sai người
  (không đo được từ gold); giảm rủi ro bằng cách: abbreviation chỉ ground khi
  candidate đó là ứng viên duy nhất trong toàn bộ roster trả về khớp luật, và
  pipeline vẫn phải validate sau đó.
- Con số 142 lượt query 1 token ở E-asr-1 KHÔNG phải tỉ lệ viết tắt — replay
  chứng minh chúng là tên đầy đủ một từ (exact). Đừng trích 142 lượt đó thành
  "viết tắt" ở bất kỳ đâu.

## 3. Search-then-use: 92,5% id nằm trong kết quả, 7,5% nằm ngoài

Trong 120 cặp search-then-use, 111 id được dùng nằm trong kết quả search trả
về, 9 id nằm ngoài. 9 trường hợp ngoài này KHÔNG phải lỗi của search hay của
filter: gold search một tên rồi dùng một id khác lấy từ history/context (vd
search "Lan" rồi nhắn cho một id khác). Hệ quả cho thiết kế:

- Filter giải quyết **query** (tên được hỏi → contact nào khớp tên đó), không
  phải dự đoán "gold sẽ dùng id nào tiếp theo". Đánh giá filter bằng
  "grounded id == gold-used id" là sai metric cho 9 trường hợp này.
- Adapter đợt 6 vì vậy KHÔNG chặn `contact_id` nằm ngoài roster trả về (nó có
  thể đến từ history, đúng pattern 9 trường hợp này) — chỉ ghi note.
- Ngược lại, khi filter ground một query exact tới đúng 1 contact, đó luôn là
  đáp án đúng cho query đó (0 trường hợp exact-grounding sai tên trong 234
  lượt — 9 "wrong-id" trong sweep thô đều là exact-grounding đúng tên, gold
  dùng id khác sau đó vì lý do ngoài search).

## 4. Hiệu chuẩn ngưỡng: sweep phẳng — giữ 88/8, và vì sao đó là kết luận đúng

Sweep `ContactFilter` trên 234 triple (query, candidates trả về, gold-used-id)
với threshold ∈ {80, 84, 88, 92, 96} × margin ∈ {0, 4, 8, 12} cho **cùng một kết
quả ở mọi setting**: correct 108, wrong 28 (xem §3 về cách đọc "wrong"),
abstain 98. Lý do phẳng là cấu trúc, không phải bug (đã kiểm chứng độ nhạy:
cùng một query typo "Trần Thị Hươn" ground ở threshold 88 nhưng UNKNOWN ở
threshold 99 — sweep machinery hoạt động, chỉ là gold không chứa case fuzzy
nào để phân biệt):

- Mọi gold query đều exact → nhánh exact bypass threshold/margin hoàn toàn.
- Vì vậy **gold không thể hiệu chuẩn threshold/margin của fuzzy** — bất kỳ con
  số nào "tối ưu trên gold" cũng là ảo giác (mọi setting đều "tối ưu" như nhau).
- Quyết định: **giữ FUZZY_THRESHOLD = 88.0, FUZZY_MARGIN = 8.0** (default của
  branch grounding, đã dùng từ đợt 4) — không đổi số chỉ để "có thay đổi".
  Ngưỡng fuzzy chỉ có thể hiệu chuẩn thật trên **dev ASR output** (nơi query
  mang lỗi ASR), không phải trên gold query sạch. Đó là việc của đợt sau, khi
  có dev predictions.
- Những gì gold HIỆU CHUẨN ĐƯỢC — và đã hiệu chuẩn xong — là: exact → ground
  (108/111 cặp used-in-returned ground đúng id; 3 abstain còn lại gồm 2 trường
  hợp trùng tên → AMBIGUOUS đúng luật — gold chọn một trong hai duplicate ở 2
  case này, nhưng n=2 không đủ sức nặng trước 69 ask ở §1 — và 1 trường hợp
  query rỗng → UNKNOWN, đúng vì query rỗng không có tên để ground),
  duplicate → ask (69/73, §1), empty query → UNKNOWN (không ground từ
  "không tên").

## 5. Định dạng gold cho adapter (đo từ label.tool_calls, không cần env)

- `amount`: 146/146 giá trị là **int** — adapter xuất int khi giá trị nguyên,
  float chỉ khi có phần thập phân thật.
- `time`: 226 datetime đầy đủ ISO, 20 giá trị **chỉ giờ** ("19:00", "22:30",
  "21:04", ...) — tức slot `time` của một số tool chấp nhận time-only hợp lệ.
  Adapter vì vậy pass-through cả ISO datetime lẫn HH:MM, không ép mọi `time`
  thành datetime đầy đủ.
- `date`: 112/112 ISO (yyyy-mm-dd hoặc yyyy-mm) — adapter xuất yyyy-mm-dd.
- `start`/`end`: 89/63, toàn datetime ISO.
- `contacts.update` xuất hiện trong gold ở 10 mẫu — nhưng update chỉ patch
  phone/email, không đổi name/id, nên đo trùng tên/viết tắt theo tên không bị
  ảnh hưởng bởi việc replay trên initial state.

## 6. Giới hạn và bước tiếp theo

- Đo trùng tên là **cận dưới**: search chỉ trả về matches, nên roster có thể
  chứa trùng tên mà query không chạm tới (trừ 30 mẫu query rỗng cho thấy full
  book). Tỉ lệ trùng tên thật của toàn roster ≥ 31,2% trên các lượt đã quan sát.
- 1321 mẫu không có gold search chưa được đo — muốn đo cần query mới ngoài
  gold, ngoài phạm vi phê duyệt đợt 6 (chỉ replay gold search).
- Ngưỡng fuzzy (88/8) chờ hiệu chuẩn trên dev ASR output — chưa làm, và không
  được "hiệu chuẩn" giả trên gold query sạch.
- Adapter đợt 6 (xem `lifemate_grounding.py` §5) áp dụng đúng các luật đã xác
  nhận ở đây: duplicate → NEEDS_ASK, exact → ground, id ngoài roster → note
  (không chặn), time-only pass-through, daypart thiếu hour → NEEDS_ASK.
