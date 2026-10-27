# Chuyên đề 2 — Entity Grounding & Sửa lỗi ASR cho Tiếng Việt (LifeMate)

> Code đi kèm: [02-asr-grounding-lifemate.py](02-asr-grounding-lifemate.py)
> (555 dòng, stdlib + RapidFuzz tùy chọn, chạy offline không GPU, không
> internet, dữ liệu demo tổng hợp — không phải dữ liệu ZAIC).
> Tài liệu này tổng hợp từ bản nháp nghiên cứu ngày 2026-10-27. Mọi
> phương pháp dưới đây là **giả thuyết chuyển giao** cho tới khi được đo
> trên dữ liệu train held-out của ZAIC; không có phương pháp nào được
> khẳng định là "hiệu quả trên ZAIC".

## 0. Khuyến nghị chính

Đừng sửa toàn bộ transcript bằng LLM. Chỉ ground **slot quyết định**
(find/replace có kiểm chứng) từ candidate lấy bằng tool `read` trong
chính sample, trên chuỗi NFC giữ nguyên dấu, với tầng bằng chứng
EXACT → FUZZY_GROUNDED → AMBIGUOUS → UNKNOWN; tiền/ngày/ID chỉ khớp
digit chính xác, cấm fuzzy; phủ định tiếng Việt được chặn bằng guard
code, không bằng fuzzy-sửa và không bằng prompt đơn thuần.

## 1. Bối cảnh và ràng buộc cứng

- LifeMate: audio tiếng Việt → agent gọi tool trong app mô phỏng →
  trạng thái cuối phải khớp (`state_hash` sai = 0 điểm cho mẫu đó, đúng
  mới tính tool-call F1). Hệ thống < 6B tham số, LLM < 5B, context
  ≤ 16K, chạy offline trên 1× A30, ≤ 30 giây/mẫu, model mã nguồn mở
  phát hành trước 26/10/2026. Xem
  [../competition/lifemate.md](../competition/lifemate.md) và
  [../research/lifemate/deep-profiles.md](../research/lifemate/deep-profiles.md).
- Lỗi ASR nguy hiểm nhất không phải WER tổng thể, mà là lỗi ở **slot
  quyết định**: tên người/thiết bị/app, số tiền, ngày giờ, số tài khoản.
  Một ký tự sai ở số tài khoản là một tool call sai hoàn toàn, không
  phải "gần đúng".
- Candidate chỉ được lấy từ **tool `read` trong chính sample đó**
  (danh bạ `contacts`, thiết bị `devices`, tài khoản `accounts`). Không
  dùng cơ sở dữ liệu thực thể ngoài, không dùng API, không dùng dữ liệu
  của sample khác. Đây là ràng buộc của thiết kế này, không phải giới
  hạn của các paper được trích (nhiều paper dùng datastore thực thể
  ngoài — phần đó **không** chuyển giao nguyên vẹn sang LifeMate).
- Ngân sách tham số tham khảo (từ vòng nghiên cứu trước, cần xác minh
  lại trên card HF trước khi đóng Docker): PhoWhisper-small 244M + LLM
  4B ≈ 4,24B; PhoWhisper-medium 769M + LLM 4B ≈ 4,77B. Grounding trong
  tài liệu này là code thuần (0 tham số LLM), nên không làm tăng ngân
  sách tham số; chi phí của nó là thời gian CPU cho fuzzy matching trên
  danh sách ứng viên của một sample — nhỏ so với một lần gọi LLM, nhưng
  phải đo trên A30.

## 2. Phonetic matching / fuzzy token matching cho tiếng Việt: khảo sát trung thực

### 2.1. Kết luận trước: không có "Vietnamese Double Metaphone" đã xác minh

Trong lượt tìm kiếm ngày 2026-10-27, **không tìm thấy thư viện Double
Metaphone riêng cho tiếng Việt** (không có repo, paper hay package nào
được xác minh là mã hóa âm vị tiếng Việt). Những gì tìm thấy là:

- Double Metaphone **gốc (tiếng Anh)**: thuật toán tạo 2 mã âm vị
  (primary / secondary) cho tên, được thiết kế cho âm vị tiếng Anh và
  các tên gốc châu Âu. Các trang tra cứu tên (ví dụ trang namediscoveries)
  chỉ áp dụng thuật toán gốc này lên tên tiếng Việt đã viết không dấu
  (ví dụ "Anhthu" → `AN0`, "Trung" → `TRNK`), tức là **mã hóa cách đọc
  tiếng Anh của chuỗi không dấu**, không phải âm vị tiếng Việt. Dùng nó
  trực tiếp cho tiếng Việt là sai về mặt ngôn ngữ học: nó không biết
  thanh điệu, không biết `đ`, `ơ`, `ư`, `ê`, và không phân biệt các cặp
  tối thiểu chỉ khác thanh.
- Soundex / NYSIIS / Caverphone / Cologne: cùng vấn đề — thiết kế cho
  tiếng Anh (hoặc tiếng Đức với Cologne), không cho tiếng Việt.
- Các thư viện matching đa chiến lược (ví dụ CanonMap trên PyPI) dùng
  Double Metaphone + Soundex như một bước blocking chung, không có biến
  thể tiếng Việt nào được ghi nhận.

**Hệ quả thiết kế:** không đưa "Vietnamese Double Metaphone" vào
pipeline như một thư viện có sẵn. Thay vào đó, §3 xây dựng matching
tiếng Việt từ 3 lớp đã kiểm chứng được bằng code:

1. **Chuẩn hóa NFC giữ nguyên dấu** (chuẩn Unicode, không phải thư viện
   tiếng Việt): gộp các dạng mã hóa tương đương của cùng một ký tự
   (ví dụ `ế` ở dạng tổ hợp và dạng tiền tổ hợp) thành một dạng duy
   nhất, **không** bỏ dấu. Với tiếng Việt, mọi tổ hợp nguyên âm + dấu
   thanh đều có dạng tiền tổ hợp, và thực tế dữ liệu tồn tại ở cả NFC,
   NFD và dạng "Windows" (nguyên âm tiền tổ hợp + thanh rời) — vì vậy
   bước NFC là bắt buộc trước mọi so sánh chuỗi, nếu không cùng một từ
   có thể so sánh khác nhau chỉ vì cách mã hóa.
2. **Khóa phụ tách thanh (tone-stripped key) chỉ để phát hiện khác
   thanh**, không để quyết định: hai chuỗi chỉ khác thanh (ví dụ
   `bàn`/`bán`/`bạn`/`bận`, hay `ma`/`má`/`mà`/`mả`/`mã`/`mạ` — ví dụ
   cổ điển về 6 thanh tiếng Việt) được phát hiện là "chỉ khác thanh"
   và bị **hạ cấp**, không được coi là khớp. Ngược lại, chuỗi mất hết
   dấu (ví dụ `Nguyen Van An`) còn mất cả dấu nguyên âm (`ê` → `e`,
   `ơ` → `o`), nên **không** phải là "chỉ khác thanh" và không được tự
   động ground — code mẫu chứng minh trường hợp này trả về UNKNOWN
   (điểm 84,6 < ngưỡng 88, xem §3.3).
3. **Fuzzy matching bằng RapidFuzz** (xem §2.2) trên chuỗi NFC giữ dấu,
   cộng với một hình phạt trần (cap) cho trường hợp chỉ khác thanh.

### 2.2. RapidFuzz — thư viện fuzzy matching chính (đã xác minh licence)

- **RapidFuzz**: fuzzy string matching Python/C++ dùng khoảng cách
  Levenshtein, là bản viết lại nhanh của FuzzyWuzzy. Trang PyPI của dự
  án ghi rõ: **MIT licensed** (khác FuzzyWuzzy bị ràng buộc GPL), viết
  chủ yếu bằng C++, có các scorer `fuzz.ratio`, `fuzz.WRatio`,
  `fuzz.token_sort_ratio`, `process.extractOne`. Không cần internet khi
  chạy (thuần CPU, không model, không API) nên phù hợp Docker offline.
- **Phiên bản:** không khẳng định một phiên bản cụ thể trong tài liệu
  này (các trang PyPI trong lượt tìm hiển thị nhiều phiên bản khác nhau
  theo thời điểm crawl; một nguồn thứ cấp nhắc tới 3.14.3 nhưng chưa đối
  chiếu trực tiếp). Quy tắc cho Docker: pin phiên bản tại lúc build, ghi
  vào `requirements.lock`, và đọc lại licence trong wheel đã cài trước
  khi nộp — không ghi phiên bản chưa xác minh vào báo cáo.
- **Fallback:** nếu RapidFuzz không có trong image, code dùng
  `difflib.SequenceMatcher` của stdlib (chậm hơn, nhưng đủ cho danh
  sách ứng viên cỡ một sample). Code mẫu tự phát hiện điều này, không
  crash.
- **Không dùng FuzzyWuzzy** cho Docker thi đấu: licence GPL của nó là
  rủi ro không cần thiết khi RapidFuzz (MIT) làm cùng việc nhanh hơn.
- **Embedding-based retrieval** (dùng embedding của audio hoặc transcript
  để truy vấn datastore): có trong literature (ví dụ paper về
  speech-text embeddings cho voice search, giảm WER tương đối 6% trên các
  utterance có trong candidate set), nhưng nó đòi thêm một model
  embedding (tốn ngân sách tham số, tốn thời gian) và một datastore đã
  tính trước — **không phù hợp** với ràng buộc "candidate chỉ từ read
  trong sample" và ngân sách A30/30s của LifeMate. Ghi nhận ở đây để khỏi
  tìm lại, không đưa vào pipeline chính.

### 2.3. Tone-weighted Levenshtein: thiết kế thay vì thư viện

Không tìm thấy thư viện Levenshtein có trọng số thanh điệu cho tiếng
Việt đã xác minh. Thiết kế trong code mẫu đạt hiệu ứng tương đương bằng
2 quy tắc đơn giản, minh bạch, không cần học tham số:

- **Quy tắc 1 — trần điểm cho khác thanh:** nếu hai chuỗi bằng nhau sau
  khi tách thanh nhưng khác nhau ở dạng NFC, điểm tối đa là 85, dưới
  ngưỡng fuzzy 88. Nghĩa là: khác thanh không bao giờ tự động ground,
  dù các ký tự còn lại giống hệt nhau.
- **Quy tắc 2 — ngưỡng + biên:** một fuzzy match chỉ được ground khi
  điểm ≥ 88 **và** hơn ứng viên thứ hai ít nhất 8 điểm. Nếu có đối thủ
  gần kề, kết quả là AMBIGUOUS (hỏi lại), không phải chọn bừa ứng viên
  cao nhất.
- Cả hai ngưỡng đều là **điểm khởi đầu đề xuất, chưa đo trên ZAIC**.
  Thí nghiệm nhỏ nhất để hiệu chuẩn chúng nằm ở §6 (đo slot-error trên
  train held-out, vẽ đường cong điểm vs. tỉ lệ ground đúng/sai theo từng
  loại slot, rồi mới khóa ngưỡng).

### 2.4. Vì sao không strip dấu để matching

Một số pipeline tiếng Việt strip dấu rồi mới so sánh ("chuẩn hóa không
dấu"). Với LifeMate, đây là **lỗi thiết kế**, vì:

- Strip dấu biến các từ khác nhau thành một: `bàn` (cái bàn), `bán`
  (bán hàng), `bạn` (bạn bè), `bận` (bận rộn) đều thành `ban`. Một slot
  tên thiết bị "bàn" bị sửa thành "bán" là sai tham số, không phải gần
  đúng.
- Strip dấu còn mất dấu nguyên âm (`ê`→`e`, `ơ`→`o`, `ư`→`u`, `đ`→`d`),
  nên không khôi phục được chuỗi gốc từ khóa đã strip — giá trị đưa vào
  tool call sẽ sai chính tả so với candidate trong tool.
- Quy tắc đúng: **so sánh trên NFC giữ dấu; khóa tách thanh chỉ là tín
  hiệu phụ để phát hiện khác thanh; giá trị đưa vào tool luôn là giá trị
  canonical của candidate** (chuỗi mà tool đã trả về), không bao giờ là
  chuỗi ASR thô hay chuỗi đã strip.

## 3. Pipeline Candidate Grounding (thiết kế chính)

```
audio ──► PhoWhisper ──► N-best transcripts (nếu có)
                                │
                                ▼
                 read tools trong sample ──► candidate lists
              (contacts / devices / accounts, chỉ sample này)
                                │
                                ▼
              ┌─────────────────────────────────────────┐
              │ 1. NFC normalize (giữ dấu)              │
              │ 2. Slot extraction (từ LLM hoặc rule   │
              │    theo tool schema, xem §3.1)          │
              │ 3. ground_slot() cho từng slot:        │
              │    EXACT → FUZZY_GROUNDED →             │
              │    AMBIGUOUS → UNKNOWN                  │
              │ 4. Slot nhạy cảm (tiền/ngày/ID):        │
              │    chỉ exact digit match, cấm fuzzy    │
              │ 5. Negation guard (§4) chặn write      │
              │    mâu thuẫn phủ định                   │
              └─────────────────────────────────────────┘
                                │
                                ▼
        LLM input: slot GROUNDED (kèm giá trị canonical + bằng chứng)
                   slot UNKNOWN (đánh dấu rõ, không tự điền)
                   → LLM chỉ được gọi write với slot GROUNDED;
                     slot UNKNOWN → sys.ask_missing_info
```

### 3.1. Slot extraction: tách khỏi grounding

Tài liệu này cố tình **không** gộp trích slot và ground slot vào một
bước LLM duy nhất, vì hai lỗi khác nhau cần đo riêng:

- **Lỗi trích slot:** LLM (hoặc rule theo schema) xác định sai *vị trí*
  của slot trong transcript (ví dụ lấy nhầm "phòng khách" thành tên
  người). Đo bằng: tỉ lệ span trích đúng / tổng số slot cần trích.
- **Lỗi ground:** span trích đúng nhưng gán nhầm candidate (ví dụ
  "Bình" thành "Bính"). Đo bằng: tỉ lệ ground đúng / tổng số slot đã
  trích đúng.

Trong code mẫu, `ground_slot()` nhận `raw_span` đã trích và danh sách
`Candidate` — tức là nó giả định bước trích đã xong. Bước trích thực tế
có thể là: (a) LLM trích span theo tool schema, rồi code ground; hoặc
(b) rule trích span bằng cách quét transcript tìm các substring khớp
candidate (nhanh, xác định, nhưng bỏ sót cách diễn đạt gián tiếp). Thí
nghiệm §6 nên đo cả hai cách trên cùng held-out trước khi chốt.

### 3.2. N-best fusion (mượn từ RECOVER, thu gọn cho LifeMate)

RECOVER (arXiv 2603.16411, tháng 3/2026 — trước mốc cutoff 26/10/2026)
là framework sửa entity cho ASR gồm: sinh nhiều giả thuyết (trong thí
nghiệm của họ: 5 giả thuyết bằng temperature sampling với
Whisper-small), truy vấn ứng viên thực thể động (top-K = 200), rồi 3 công
cụ theo thứ tự — Fuse Hypotheses, Propose Corrections (LLM bị ràng buộc
chỉ đề xuất find/replace cho entity), Verify & Apply (guardrail xác
định, chỉ áp dụng edit vượt qua kiểm tra). Thiết kế LifeMate mượn **khung**
này nhưng thu gọn cho phù hợp ràng buộc:

- **Fuse:** `fuse_nbest()` trong code mẫu — chọn giả thuyết chứa nhiều
  substring candidate exact nhất; hòa thì giữ giả thuyết đầu tiên. Không
  dùng LLM cho bước fuse (tiết kiệm 1 lần gọi model và 1 nguồn lỗi).
- **Propose:** thay LLM đề xuất edit bằng `ground_slot()` xác định
  (code, không LLM). Điều này làm mất khả năng sửa các entity không có
  trong candidate list, nhưng đó là đánh đổi có chủ ý: với LifeMate, sửa
  entity không có bằng chứng trong sample chính là đoán — và đoán sai
  một write thì `state_hash` về 0.
- **Verify & Apply:** guardrail trong `ground_slot()` (exact → fuzzy có
  ngưỡng + biên → cấm fuzzy cho slot nhạy cảm) cộng với negation guard
  (§4). Chỉ edit nào vượt qua cả hai mới được áp dụng; còn lại giữ nguyên
  transcript và đánh dấu UNKNOWN.
- **Khác biệt quan trọng với RECOVER gốc:** RECOVER dùng datastore thực
  thể ngoài (K = 200 từ danh sách thực thể đã biết) và agent Agno;
  LifeMate ở đây dùng **chỉ candidate từ read trong sample** (thường nhỏ
  hơn nhiều), và không dùng framework agent ngoài. Vì vậy các con số cải
  thiện của RECOVER (giảm tương đối entity-phrase WER 8–46% theo báo cáo
  của tác giả trên 5 dataset của họ) **không được suy ra** thành cải
  thiện trên ZAIC — chúng chỉ chứng minh khung Fuse → Propose → Verify
  là hợp lý, còn hiệu quả thực tế phải đo lại (§6).

Các công trình liên quan khác, ghi nhận để khỏi tìm lại:

- **DeRAGEC** (arXiv 2506.07510): mở rộng RAGEC bằng rationale tổng hợp
  để lọc ứng viên nhiễu trước khi sửa, dùng phonetic similarity + định
  nghĩa bổ sung; tác giả báo cáo giảm tương đối WER 28% so với ASR không
  hậu xử lý trên CommonVoice và STOP. Đây là số **tác giả báo cáo, trên
  tập của họ**, không phải số LifeMate. Ý tưởng chuyển giao duy nhất là
  "lọc ứng viên trước khi sửa" — trong thiết kế này, lọc đó chính là
  bước candidate từ read trong sample + ngưỡng/biên.
- **Generative error correction với N-best (CoVoGER, EMNLP 2025):**
  benchmark cho thấy chiến lược decode hỗn hợp (beam search + temperature
  sampling) cho ra 5-best list tốt nhất cho việc sửa lỗi bằng LLM. Ý
  nghĩa cho LifeMate: nếu chỉ dùng greedy decoding (temperature 0, 1 giả
  thuyết), N-best fusion không có gì để fuse — muốn dùng §3.2 thì phải
  cấu hình Whisper sinh nhiều giả thuyết (tốn thời gian, phải đo trong
  ngân sách 30s/mẫu). Nếu ngân sách không cho phép, fallback là 1-best +
  grounding bằng candidate list (vẫn tốt hơn không grounding).
- **Speech-text embedding retrieval** (xem §2.2): không dùng, vì tốn
  model phụ và vi phạm ràng buộc candidate-trong-sample.

### 3.3. Các tầng bằng chứng (confidence tier) và hành động tương ứng

| Tier | Điều kiện | Hành động |
|---|---|---|
| `EXACT` | Khớp NFC chính xác với một candidate trong sample; hoặc với slot nhạy cảm thì khớp digit chính xác | Dùng giá trị canonical của candidate cho tool call |
| `FUZZY_GROUNDED` | Điểm ≥ 88 và hơn ứng viên thứ hai ≥ 8 điểm; không phải trường hợp chỉ khác thanh | Dùng giá trị canonical; ghi log điểm + biên để kiểm tra sau |
| `AMBIGUOUS` | Có đối thủ gần kề (dưới biên), hoặc chỉ khác thanh (điểm bị trần 85) | **Không** dùng cho write; đánh dấu UNKNOWN cho LLM, hoặc hỏi lại qua `sys.ask_missing_info` |
| `UNKNOWN` | Không candidate nào vượt ngưỡng; hoặc slot nhạy cảm không khớp digit | **Không** đoán; LLM phải hỏi lại, không gọi write với tham số này |

Quy tắc vàng: **giá trị đưa vào tool call luôn là giá trị canonical của
candidate, không bao giờ là chuỗi ASR thô.** Nhờ vậy, mọi slot đã ground
đều truy vết được về một `read` cụ thể trong sample.

### 3.4. Code minh họa (trích yếu — code đầy đủ trong file đi kèm)

```python
# Các hàm dưới đây nằm trong file đi kèm 02-asr-grounding-lifemate.py
# (nạp file đó làm module rồi dùng các tên hàm này):
#   Candidate, SlotKind, ground_slot, fuse_nbest, guard_tool_call

contacts = [Candidate("Nguyễn Văn An", "contacts"),
            Candidate("Trần Thị Bình", "contacts")]
# Transcript thô: "Bính" (sai thanh) thay vì "Bình"
slot = ground_slot("Trần Thị Bính", contacts, SlotKind.NAME)
# -> value=None, tier=AMBIGUOUS ("tone-only match; tone changes meaning")
#    => không gọi write, hỏi lại qua sys.ask_missing_info

# Số tài khoản sai 1 chữ số: không bao giờ fuzzy
slot = ground_slot("0901234568",
                   [Candidate("0901234567", "accounts")],
                   SlotKind.ACCOUNT_ID)
# -> value=None, tier=UNKNOWN ("fuzzy guessing is forbidden")

# N-best: giả thuyết chứa candidate exact thì thắng
fused = fuse_nbest(["Chuyển tiền cho Trần Thị Bính",
                    "Chuyển tiền cho Trần Thị Bình"], contacts)
# -> "Chuyển tiền cho Trần Thị Bình"
```

Chạy demo đầy đủ: `python3 02-asr-grounding-lifemate.py` (không cần
RapidFuzz, không cần GPU, không cần internet; dùng dữ liệu demo tổng
hợp, **không phải dữ liệu ZAIC**).

## 4. Phủ định tiếng Việt: bẫy ASR và guard bằng code

### 4.1. Các dạng phủ định / hủy cần phân biệt (không được gộp)

| Dạng | Ví dụ | Ý nghĩa thật | Lỗi guard thường gặp |
|---|---|---|---|
| Phủ định động từ | "không chuyển", "không bật" | Không thực hiện hành động đó | ASR rớt mất "không" → agent thực hiện đúng hành động bị cấm |
| Cấm đoán | "đừng bật", "chớ tắt", "cấm mở" | Lệnh cấm, mạnh hơn "không" | Coi "đừng" như từ đệm, bỏ qua |
| Tương phản | "không phải A mà là B" | A bị phủ định, B được khẳng định | Coi cả câu là phủ định → từ chối cả B; hoặc coi cả câu là khẳng định → thực hiện cả A |
| Chưa xảy ra | "chưa chuyển", "chưa đặt" | Hành động chưa làm, **không phải** từ chối | Coi "chưa" như "không" → từ chối một yêu cầu hợp lệ |
| Hành động hủy | "hủy đơn", "huỷ lịch" | Bản thân nó **là** một write (cancel) | Coi "hủy" như phủ định → chặn luôn hành động hủy hợp lệ; ngược lại "không hủy" mới là phủ định của hủy |
| Phủ định kép / hàm ý | "không phải không chuyển" (hiếm trong lệnh ngắn) | Nghĩa đảo ngược, dễ đọc sai | Guard đơn giản theo từ khóa sẽ đảo ngược sai |

Bằng chứng ngôn ngữ học cơ bản (đã xác minh qua tài liệu ngữ pháp tiếng
Việt): `không` là từ phủ định chính, đặt trước động từ/tính từ bị phủ
định ("cô ấy không đọc nhanh"). Các dạng còn lại trong bảng là phân tích
thiết kế cho LifeMate (giả thuyết chuyển giao, chưa đo trên audio ZAIC),
không phải kết quả thực nghiệm.

### 4.2. Các bẫy ASR phổ biến với phủ định

1. **Rớt từ phủ định (deletion):** "không" là âm tiết ngắn, không trọng
   âm, dễ bị ASR bỏ qua nhất khi nói nhanh hoặc nhiễu. Hậu quả là nghiêm
   trọng nhất trong tất cả các loại lỗi ASR: một write bị cấm biến thành
   write được thực hiện, làm lệch `state_hash` về 0 **và** gây tác dụng
   phụ thật (chuyển tiền, hủy đơn) mà gold không có.
2. **Nghe nhầm phủ định thành từ khác:** "đừng" → "đường", "không" →
   "khong" (mất dấu, rồi bị đọc thành từ khác), "chớ" → "chợ". Đây là
   nơi fuzzy matching **không được** dùng để "sửa" phủ định: sửa "đường"
   thành "đừng" bằng fuzzy là đoán về ý định — đoán sai thì chặn oan
   hoặc thực hiện oan, cả hai đều mất điểm.
3. **Mâu thuẫn giữa các N-best:** một giả thuyết có "không", một giả
   thuyết không có. Đây là tín hiệu **không chắc chắn**, không phải tín
   hiệu để chọn giả thuyết "đẹp" hơn. Guard trong code xử lý trường hợp
   này bằng cách chặn write và hỏi lại (xem §4.3).
4. **Phạm vi phủ định (scope):** "không chuyển tiền cho An mà chuyển cho
   Bình" — phủ định chỉ bao phủ "chuyển cho An", không bao phủ "chuyển
   cho Bình". Guard theo từ khóa toàn câu sẽ chặn sai; guard trong code
   dùng scope (các từ sau cue tới biên mệnh đề) và kiểm tra riêng cho
   tương phản (chỉ chặn target bị phủ định).
5. **Phủ định trong tên/thực thể:** "không" có thể là một phần của tên
   (hiếm) hoặc của cụm từ khác ("không gian", "không khí"). Guard chỉ
   kích hoạt khi cue đi kèm động từ hành động trong scope, không kích
   hoạt với mọi lần xuất hiện của chuỗi "không".

### 4.3. Cơ chế guard (code) + prompt assertion (LLM)

Guard bằng code chạy **trước** mọi tool write, độc lập với LLM — vì LLM
có thể "quên" assertion trong prompt khi context dài. Luật:

1. **Phát hiện:** quét transcript (và từng N-best nếu có) tìm cue
   `đừng`/`chớ`/`cấm` (PROHIBITION), `không` + động từ (NEGATION),
   `không phải A mà là B` (CONTRAST), `chưa` (NOT_YET, không chặn).
2. **Mâu thuẫn N-best → chặn:** nếu các giả thuyết không thống nhất về
   sự hiện diện của cue phủ định, write bị chặn và trả về
   `sys.ask_missing_info`. Không chọn giả thuyết theo đa số cho phủ định
   — đa số không phải bằng chứng khi một từ ngắn bị rớt một cách có hệ
   thống.
3. **Phạm vi → chặn:** nếu scope của cue chứa động từ của hành động đề
   xuất (bảng ánh xạ động từ → action trong code, cố tình giữ nhỏ và
   tường minh: chuyển/gửi/bật/tắt/đặt/mua/hủy/xóa/thanh toán), write bị
   chặn.
4. **Tương phản → chặn có chọn lọc:** chỉ chặn write nhắm vào target bị
   phủ định (A); write nhắm vào target được khẳng định (B) vẫn được
   phép.
5. **Không bao giờ đảo ngược thầm lặng:** guard không tự biến "không
   chuyển" thành "chuyển" hay ngược lại, không tự thay target A bằng B,
   không tự điền slot UNKNOWN. Đầu ra duy nhất khi bị chặn là
   `sys.ask_missing_info` (khi chưa write gì) hoặc yêu cầu xác nhận tường
   minh — và trong khuôn khổ LifeMate, vì không có người dùng thật để
   xác nhận giữa chừng, `ask_missing_info` là lựa chọn an toàn mặc định
   (xem lưu ý về evaluator ở §7: cách chấm `ask_missing_info` vẫn cần
   đối chiếu với đặc tả chính thức).
6. **Prompt assertion** (chuỗi `PROMPT_ASSERTION_VI` trong code) được đưa
   vào prompt của LLM như lớp phòng thủ thứ hai, với cùng 5 luật trên
   bằng tiếng Việt. Prompt không thay thế guard bằng code; guard không
   thay thế prompt — hai lớp này bắt các lỗi khác nhau (prompt bắt lỗi
   hiểu sai ý định; guard bắt lỗi LLM bỏ qua prompt).

Ví dụ kiểm chứng trong code (đã chạy, xem §7 của bản nháp):

| Proposed write | Transcript | Guard |
|---|---|---|
| transfer → Bình | "Chuyển tiền cho Trần Thị Bình" | Cho phép |
| transfer → Bình | "Không chuyển tiền cho Trần Thị Bình" | **Chặn → ask_missing_info** |
| turn_on → Đèn phòng khách | "Đừng bật đèn phòng khách" | **Chặn → ask_missing_info** |
| turn_on → Đèn phòng ngủ | "Không phải đèn phòng khách mà là đèn phòng ngủ, bật lên" | Cho phép (B được khẳng định) |
| turn_on → Đèn phòng khách | cùng câu tương phản trên | **Chặn** (A bị phủ định) |
| transfer → Bình | "Chưa chuyển tiền cho Trần Thị Bình" | Cho phép (`chưa` ≠ từ chối) |
| transfer → Bình | N-best mâu thuẫn về "không" | **Chặn → ask_missing_info** |

Lưu ý về vòng lặp: guard phủ định là một quyết định chặn write độc lập,
không phải fallback của loop guard. Nếu agent lặp sau khi bị chặn, áp
dụng đúng quy tắc trong chuyên đề 1: dừng, replan 1 lần từ dữ liệu đã
đọc, nếu không có hành động mới có căn cứ thì kết thúc trace nguyên
trạng — không tự chuyển thành `[]` hay ask chỉ vì hết vòng.

## 5. Bảng tổng hợp: loại lỗi ASR → chiến lược sửa → rủi ro

| Loại lỗi ASR | Ví dụ minh họa (tổng hợp, không phải dữ liệu ZAIC) | Chiến lược sửa | Rủi ro nếu sửa sai |
|---|---|---|---|
| Sai thanh ở tên | "Bình" → "Bính" | Tone-only → AMBIGUOUS, hỏi lại; không auto-ground | Ground nhầm sang người khác có tên chỉ khác thanh → sai người nhận, hash 0 |
| Mất dấu nguyên âm / mất dấu hoàn toàn | "Nguyễn" → "Nguyen" | Không coi là tone-only (mất cả `ê`); UNKNOWN, hỏi lại | Strip dấu rồi ground bừa → sai chính tả candidate, tool có thể từ chối hoặc sai thực thể |
| Sai phụ âm đầu / vần | "Trần" → "Chần", "Nam" → "Lam" | Fuzzy ≥ 88 + biên ≥ 8 trên NFC giữ dấu | Fuzzy quá thấp → ground nhầm tên gần giống; fuzzy quá cao → bỏ lỡ sửa đúng |
| Sai số tiền / ngày / số tài khoản | 1 chữ số sai, "15" → "50" | **Cấm fuzzy**; chỉ exact digit match; sai 1 chữ số = UNKNOWN | Đoán số tiền/tài khoản = write sai, không thể cứu bằng hash; rủi ro cao nhất |
| Rớt từ phủ định | "không chuyển" → "chuyển" | Negation guard + N-best disagreement → chặn + ask | Không guard → thực hiện hành động bị cấm, hash 0 + tác dụng phụ |
| Nghe nhầm từ cấm | "đừng" → "đường" | Không fuzzy-sửa phủ định; N-best disagreement → chặn | Sửa fuzzy phủ định → chặn oan hoặc thực hiện oan |
| Tương phản bị đọc phẳng | "không phải A mà là B" → chỉ "B" hoặc chỉ "A" | Guard tương phản: chặn A, cho phép B | Chặn cả B → mất điểm mẫu đúng; thực hiện A → sai trạng thái |
| Thực thể không có trong sample | Tên người ngoài danh bạ | UNKNOWN, hỏi lại; không tra cứu ngoài | Tra cứu ngoài = vi phạm ràng buộc candidate-trong-sample; đoán = sai |
| Nhiều candidate gần giống nhau | Hai "An" khác họ trong danh bạ | Biên < 8 → AMBIGUOUS, hỏi lại | Chọn bừa người cao điểm nhất → sai người nhận |
| Lỗi ở từ không phải slot | "hôm nay" → sai dấu ở từ đệm | Không sửa toàn câu; chỉ ground slot quyết định | Sửa toàn câu bằng LLM → có thể sửa hỏng cả slot đúng |

## 6. Những gì KHÔNG làm, và vì sao

- **Không sửa toàn bộ transcript bằng LLM.** Sửa toàn câu là cách làm
  phổ biến trong generative error correction, nhưng với LifeMate nó có 2
  rủi ro: (a) LLM có thể "sửa" cả những phần ASR đã đúng (đặc biệt là
  tên và số), biến đúng thành sai; (b) tốn một lần gọi LLM trước cả lần
  gọi tool chính, trong ngân sách 30s/mẫu. Thiết kế này chỉ sửa **slot**
  (find/replace có kiểm chứng), giữ nguyên phần còn lại của transcript
  — đúng tinh thần "Verify & Apply" của RECOVER.
- **Không dùng embedding / datastore ngoài.** Vi phạm ràng buộc
  candidate-trong-sample và tốn ngân sách tham số/thời gian (§2.2).
- **Không fuzzy cho tiền/ngày/ID.** Không có "gần đúng" cho số tài khoản:
  một chữ số sai là một tài khoản khác. Đây là quy tắc an toàn, không
  phải tham số có thể hiệu chuẩn.
- **Không strip dấu để matching.** Xem §2.4.
- **Không dùng điểm fuzzy làm xác suất.** Điểm RapidFuzz là độ tương tự
  chuỗi, không phải xác suất ground đúng. Ngưỡng 88/biên 8 là điểm khởi
  đầu đề xuất; xác suất thật phải đo trên train held-out (§7) rồi mới
  nói tới calibration.
- **Không giả định cách chấm `ask_missing_info`.** Tài liệu này dùng
  `ask_missing_info` làm đầu ra an toàn khi slot UNKNOWN hoặc phủ định
  mâu thuẫn, theo mô tả đề bài (thiếu thông tin → hỏi qua
  `sys.ask_missing_info`). Cách evaluator tính điểm cho một lần hỏi đúng /
  hỏi thừa / hỏi thiếu, và việc failed call có phải nộp trong trace hay
  không, **vẫn cần đối chiếu** với regulations PDF, README trong zip
  LifeMate, tool catalog và đặc tả submission trước khi chốt — đây là
  khoảng trống lớn nhất của thiết kế này (xem §8).

## 7. Thí nghiệm nhỏ nhất để biết hướng này có đáng theo tiếp

Tất cả đều chạy trên **train held-out** (train là nguồn nhãn duy nhất
được ghi nhận là có gold `tool_calls`/`final_state`; public test chỉ có
`sample_submission.jsonl` làm mẫu format theo ghi nhận trước — **phải
xác minh lại bằng cách giải nén zip thật trước khi chạy**, nếu zip thật
khác ghi nhận thì viết lại kế hoạch này theo file thật). Không đo trên
dữ liệu đã dùng để viết rule hoặc chọn ngưỡng, rồi báo lại số đó.

1. **E-slot-1 — đo slot-error, không đo WER tổng.** Trên train held-out,
   chạy PhoWhisper-small, trích slot theo schema, phân loại lỗi theo
   bảng §5 (sai thanh, mất dấu, sai phụ âm/vần, sai số, rớt phủ định,
   tương phản). Đầu ra là một bảng tần suất lỗi theo loại slot, không
   phải một con WER chung. Quyết định: nếu lỗi slot quyết định chiếm đa
   số lỗi gây sai hash, grounding là ưu tiên số 1 sau validator; nếu
   không, ưu tiên khác.
2. **E-slot-2 — hiệu chuẩn ngưỡng fuzzy.** Với cùng held-out, chạy
   `ground_slot()` ở nhiều ngưỡng (ví dụ 80/85/88/92) và biên (0/5/8/12),
   vẽ tỉ lệ ground đúng / ground sai / AMBIGUOUS / UNKNOWN theo từng
   loại slot. Khóa ngưỡng nào cho tỉ lệ ground sai thấp nhất trong khi
   tỉ lệ UNKNOWN vẫn chấp nhận được (vì UNKNOWN chỉ mất điểm hỏi lại,
   còn ground sai thì mất cả hash). Không khóa ngưỡng trên cùng dữ liệu
   đã đo rồi báo lại số đó.
3. **E-neg-1 — đo guard phủ định.** Tạo tập kiểm tra từ train held-out
   bằng cách lọc các mẫu có cue phủ định/tương phản (theo transcript
   gold, không phải ASR), chạy guard trên transcript ASR, đếm: chặn đúng /
   chặn oan / lọt (thực hiện hành động bị cấm) / tương phản xử lý đúng.
   Tiêu chí tiếp tục (đề xuất, chưa phải kết luận): tỉ lệ lọt ≈ 0 mới
   chấp nhận guard cho write nhạy cảm; chặn oan cao thì thu hẹp scope
   hoặc bảng động từ, không được nới guard bằng cách bỏ cue.
4. **E-nbest-1 — N-best có đáng thời gian không.** So sánh 1-best +
   grounding với 5-best + fusion + grounding trên cùng held-out, đo cả
   slot-error và thời gian/mẫu trên A30 (hoặc GPU tương đương, ghi rõ
   phần cứng thật khi báo cáo). Nếu fusion chỉ cải thiện slot-error
   không đáng kể mà đẩy thời gian sát 30s, bỏ N-best, giữ 1-best +
   grounding.
5. **E-lat-1 — ngân sách 30s.** Đo end-to-end (ASR + grounding + 1 lần
   gọi LLM + tool calls) trên A30 cho mẫu dài nhất trong held-out.
   Grounding bằng code phải dưới 1s/mẫu mới coi là "miễn phí"; nếu
   candidate list lớn bất thường, thêm bước lọc candidate bằng
   substring/từ khóa trước khi fuzzy (blocking), không tăng ngưỡng để
   "cho nhanh".

## 8. Thư viện, phiên bản, licence (chỉ ghi những gì đã xác minh)

| Thư viện / tài nguyên | Dùng cho | Licence / phiên bản — trạng thái xác minh |
|---|---|---|
| Python stdlib (`unicodedata`, `re`, `difflib`, `dataclasses`) | NFC, tone key, fallback fuzzy, cấu trúc code | Stdlib, không cần licence riêng; luôn có trong Docker Python |
| RapidFuzz | Fuzzy matching chính (WRatio, token_sort) | **MIT** (trang PyPI của dự án, đã xác minh); phiên bản cụ thể **không khẳng định** — pin tại lúc build và ghi vào `requirements.lock` |
| PhoWhisper (small 244M / medium 769M) | ASR tiếng Việt | Paper ICLR 2024 Tiny Papers, arXiv 2406.02555; WER VIVOS small 6,33 / medium 4,97 (bảng 2 của paper); licence của checkpoint trên HF **chưa xác minh trong lượt này** — đọc card HF trước khi đóng Docker |
| RECOVER (arXiv 2603.16411) | Khung Fuse → Propose → Verify | Paper, tháng 3/2026 (trước cutoff 26/10/2026); code/framework (Agno) **không** chuyển nguyên; chỉ mượn khung |
| DeRAGEC (arXiv 2506.07510) | Ý tưởng lọc ứng viên trước khi sửa | Paper; code tại github.com/solee0022/deragec theo abstract (chưa đọc code trong lượt này — **không** gắn CODE_INSPECTED) |
| CoVoGER (EMNLP 2025) | Bằng chứng N-best hỗn hợp tốt cho sửa lỗi | Paper/benchmark; code tại github.com/N-Orien/CoVoGER theo abstract (chưa đọc code — **không** gắn CODE_INSPECTED) |
| FuzzyWuzzy | — (không dùng) | GPL — loại vì rủi ro licence khi RapidFuzz (MIT) làm cùng việc |
| Double Metaphone gốc / Soundex / NYSIIS | — (không dùng cho tiếng Việt) | Thuật toán tiếng Anh; không có biến thể tiếng Việt đã xác minh |

## 9. Nguồn

Ngày truy cập cho mọi nguồn dưới đây: 2026-10-27. Mức xác minh:
`OFFICIAL` = paper/trang chính thức đã đọc qua kết quả tìm kiếm;
`SECONDARY` = nguồn thứ cấp/tóm tắt; `NOT_FOUND` = đã tìm, không thấy
bằng chứng.

| Nguồn | URL | Trạng thái |
|---|---|---|
| PhoWhisper paper (ICLR 2024 Tiny Papers), bảng WER VIVOS | https://arxiv.org/pdf/2406.02555 | OFFICIAL (bảng 2 đã đối chiếu: small 244M / VIVOS 6,33; medium 769M / 4,97) |
| RECOVER: Fuse → Propose → Verify & Apply, N=5, K=200 | https://arxiv.org/pdf/2603.16411 | OFFICIAL (abstract + §2 đã đọc qua kết quả tìm kiếm) |
| DeRAGEC: denoising NE candidates, giảm tương đối WER 28% (tác giả báo cáo) | https://arxiv.org/pdf/2506.07510 | OFFICIAL (abstract; số là tác giả báo cáo trên tập của họ) |
| Generative ASR NE correction (speech-aware retrieval, TTS datastore) | https://arxiv.org/html/2508.20700v2 | OFFICIAL (abstract + phương pháp; không chuyển giao datastore TTS sang LifeMate) |
| CoVoGER: 5-best hỗn hợp beam + temperature cho GER (EMNLP 2025) | https://aclanthology.org/ (EMNLP 2025 main, anthology ID 2025.emnlp-main.320 — xem ghi chú) | SECONDARY (tóm tắt; code github.com/N-Orien/CoVoGER theo abstract, chưa đọc) |
| RapidFuzz (MIT, WRatio, process) | https://pypi.org/project/RapidFuzz/ | OFFICIAL (trang PyPI: MIT, mô tả scorer; phiên bản cụ thể không khẳng định) |
| Unicode NFC/NFD cho tiếng Việt (nhiều dạng mã hóa tương đương) | https://community.software.sil.org/t/problem-typing-vietnamese-tone-markers-and-diacritics/2793?page=2 | SECONDARY (thảo luận kỹ thuật Unicode; quy tắc NFC là chuẩn Unicode, không phải claim riêng) |
| Ví dụ 6 thanh: ma/má/mà/mả/mã/mạ; strip dấu làm mất nghĩa | https://www.fachuebersetzungsdienst.com/en/translate/vietnamese-english.html | SECONDARY (ví dụ minh họa, không phải nghiên cứu ASR) |
| Ngữ pháp phủ định tiếng Việt: `không` trước động từ/tính từ | https://yourvietnamese.com/learn-vietnamese/vietnamese-conjunctions-and-negations/ | SECONDARY (tài liệu học ngữ pháp; các dạng còn lại trong §4.1 là phân tích thiết kế) |
| Double Metaphone gốc áp lên tên tiếng Việt không dấu (ví dụ AN0, TRNK) | https://namediscoveries.com/names/anhthu | SECONDARY — và là bằng chứng *chống lại* việc dùng thuật toán gốc cho tiếng Việt (mã hóa cách đọc tiếng Anh) |
| Vietnamese Double Metaphone library (riêng cho tiếng Việt) | — (không có URL) | NOT_FOUND trong lượt tìm 2026-10-27 — không khẳng định tồn tại |
| Tone-weighted Levenshtein library cho tiếng Việt | — (không có URL) | NOT_FOUND — thay bằng quy tắc trần điểm + ngưỡng/biên trong §2.3 (thiết kế, chưa đo) |
| Speech-text embedding retrieval cho voice search (giảm WER tương đối 6% trên utterance có trong candidate set) | https://arxiv.org/pdf/2401.04235 | OFFICIAL (abstract; không dùng cho LifeMate vì tốn model phụ + datastore ngoài) |

Ghi chú về URL CoVoGER: kết quả tìm kiếm trả về trang tóm tắt của ACL
Anthology cho paper này nhưng không trả về URL đầy đủ dạng verbatim cho
bản PDF; vì vậy bảng trên không bịa URL PDF — tra cứu theo tên paper và
anthology ID khi cần đối chiếu.

## 10. Đã xác minh / giả định / cần đo / câu hỏi evaluator còn mở

- **Đã xác minh (trong phạm vi bản nháp):** không có thư viện Double
  Metaphone tiếng Việt hay Levenshtein có trọng số thanh điệu cho tiếng
  Việt đã xác minh; RapidFuzz là MIT và chạy offline thuần CPU; PhoWhisper
  small/medium và WER VIVOS trong bảng 2 của paper; RECOVER là khung
  Fuse → Propose → Verify với N=5, K=200 (nhưng datastore ngoài của nó
  không chuyển giao sang LifeMate).
- **Giả định:** candidate chỉ từ read trong sample; bước trích slot đã
  xong trước khi ground; bảng động từ hành động trong guard là đủ cho
  các write thường gặp; ngưỡng fuzzy 88 / biên 8 / trần khác thanh 85
  là điểm khởi đầu hợp lý (chưa đo).
- **Cần đo trên dữ liệu/phần cứng ZAIC thật:** slot-error theo loại
  (E-slot-1); đường cong hiệu chuẩn ngưỡng fuzzy (E-slot-2); tỉ lệ lọt
  và chặn oan của guard phủ định (E-neg-1); N-best có đáng thời gian
  không (E-nbest-1); end-to-end dưới 30s/mẫu trên A30 (E-lat-1); tách
  metric theo vùng miền Bắc/Trung/Nam và giọng thật/tổng hợp.
- **Câu hỏi evaluator còn mở:** cách chấm `sys.ask_missing_info`
  (hỏi đúng/thừa/thiếu), failed call có phải nộp trong trace không, F1
  tính trên toàn bộ call đã nộp hay chỉ call thành công, read call có
  tính vào F1 không; xem danh sách đầy đủ Q-L1..Q-L6 trong
  [../gaps.md](../gaps.md). Không gửi câu hỏi cho ban tổ chức trong đợt
  này.
