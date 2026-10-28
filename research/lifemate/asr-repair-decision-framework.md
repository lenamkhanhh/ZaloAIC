# Khung quyết định: sửa lỗi ASR vs `sys.ask_missing_info` (LifeMate)

> Tài liệu đợt 4 — đi sâu hơn, không lặp lại `research/round3-p1-asr-repair-vs-ask.md`
> (round 3 đã có: grounding text-similarity, đề xuất Epitran+Panphon, teacher-forcing
> rescoring, contextual decoding ở mức ý tưởng). Tài liệu này kiểm chứng các ý tưởng đó
> xuống tới code, license, test chạy thực tế, và bổ sung các module round 3 chưa có:
> mã phonetic tiếng Việt tự định nghĩa, công thức word-confidence của faster-whisper,
> biasing thật ở mức score (pyctcdecode), và chuẩn hoá typed (số/tiền/ngày/tên tắt/trùng tên).
>
> **Hệ thống nhãn bằng chứng (bắt buộc cho mọi kết luận trong tài liệu này):**
> - `[OFFICIAL]`: đối soát trực tiếp từ ban tổ chức hoặc README/`zaic_tools` của bộ dữ liệu.
> - `[CODE_INSPECTED]`: đã đọc trực tiếp tên file, commit, class/function trong repo nguồn.
> - `[LOCALLY_VERIFIED]`: đã chạy thử nghiệm và kiểm chứng log thực tế.
> - `[INFERENCE]`: nhận định kỹ thuật suy ra từ ngữ cảnh thi đấu. Kết luận nào chỉ dựa
>   trên số paper thì nhãn là `[INFERENCE]`, không được đọc thành bảo đảm cho ZAIC.
> - Các fact nguồn (portal, repo, log chạy) được trích dẫn kèm vị trí; nhãn gắn vào
>   *kết luận/quyết định* rút ra từ fact đó, theo mắt xích yếu nhất.
>
> Mọi ví dụ tên/người trong tài liệu này đều là **hư cấu** (vd "Lan"). Không dùng
> ID, số tiền, hay đáp án thật nào từ probe/dev để minh hoạ.

## 0. Quyết định trước (binary first)

1. **Cơ chế chính — tầng grounding đa tín hiệu xác định, 0 param mới** [INFERENCE]:
   text (RapidFuzz sẵn có) + segmental FED (epitran+Panphon) + tone-digit riêng
   + acoustic rescore cho slot tranh chấp + chuẩn hoá typed. Không thêm model,
   không license rủi ro, không training, chạy CPU trong Docker offline.
2. **Cơ chế bổ sung có điều kiện — contextual 2-pass bằng faster-whisper
   `initial_prompt`/`hotwords`** [INFERENCE]: chỉ cho mẫu nghi ngờ, chỉ sau khi đo
   overcorrection. Biasing mềm, không bảo đảm, không thay thế cơ chế chính.
3. **Không chọn:** mã Soundex/Metaphone tiếng Anh cho tên Việt; viphoneme làm mặc định
   (license non-commercial + dependency lỗi); stack pyctcdecode + wav2vec2-vi làm chính
   (cần CTC stack thứ hai); embedding làm kênh chính (kém đúng ở lỗi thanh điệu);
   TCPGen (cần retrain decoder); speech-to-intent drop-in (không tồn tại cho ZAIC).

## 1. Nền tảng đã kiểm chứng — luật chơi của điểm số

### 1.1. Cái gì quyết định điểm, cái gì không

- `state_hash` bỏ qua live apps (`weather`, `gold_price`, `exchange_rate`, `fuel_price`,
  `lottery`) và bỏ qua mọi trường free-text (`address`, `content`, `note`, `name`,
  `title`, …) ở mọi cấp dict; list scalar so sánh dạng tập hợp [CODE_INSPECTED:
  `zaic_tools/utils.py`, `canon()`, `FREE_TEXT_KEYS`, `LIVE_APPS`].
  Hệ quả [INFERENCE]: ngân sách repair dồn vào slot **hash-relevant** (ID, time,
  amount, enum, trạng thái logic). Sửa free-text (tên hiển thị, nội dung) là **hạng hai**:
  nó chỉ ảnh hưởng F1 trên args, không cứu được hash.
- `Simulator.validate()` chỉ kiểm tra schema, **không ghi log, không tăng trace**
  [LOCALLY_VERIFIED: good call → `{"ok": True}`, thiếu `time` bắt buộc →
  `"thiếu tham số bắt buộc: time"`, bad type → `"sai tham số: time phải là string"`,
  cả ba đều giữ log = 0]. Ngược lại, **mọi** `call()` — read, ask, call bị reject,
  write — đều append vào log và tính vào submission [LOCALLY_VERIFIED].
  Hệ quả [INFERENCE]: **validate-first là miễn phí, read là đắt.** Mọi kiểm tra
  có thể làm bằng validate thì làm bằng validate, không dùng read để kiểm tra.

### 1.2. Giá của một call thừa (đo bằng đúng hàm scorer của nhánh experiment)

Với gold = 1 write, dùng `tool_f1` trích nguyên văn từ `lifemate/scoring.py`
(nhánh `codex/lifemate-baseline-integration`, chỉ stub import package)
[LOCALLY_VERIFIED]:

| Submission | F1 |
|---|---|
| write chuẩn | 1.0 |
| write + 1 read thừa | 0.6667 |
| write + 2 read thừa | 0.5 |
| ask thay cho write | 0.0 |

Một read-after-write để "xác minh" write vừa xong tốn **0.333 F1** mà không mua
được gì cho hash: kết quả của write đã echo lại item vừa tạo, và kết quả được
deepcopy (không aliasing) [CODE_INSPECTED: `zaic_tools/executor.py`, `Simulator.call`].
Caveat [CODE_INSPECTED: header `lifemate/scoring.py`]: scorer này là proxy của team,
**chưa xác minh** evaluator chính thức có tính read vào F1 hay không. Nếu evaluator
loại read thì chi phí trên = 0 — pipeline tinh gọn vẫn đúng ở cả hai nhánh (không
tốn gì nếu read miễn phí, tiết kiệm 0.333/call nếu read bị tính). Đây là chiến lược
** weakly dominant**, không phải cược vào một giả thuyết về evaluator.

### 1.3. Luật kỳ vọng cho repair-vs-ask (giữ từ round 3, nay có số)

Trên mẫu gold là write: ask → hash không đổi → điểm 0; repair sai → điểm 0;
repair đúng → > 0. Vì vậy **repair có bằng chứng luôn ≥ ask**, dù độ tin cậy < 100%
[INFERENCE từ luật hash-gate]. Ngoại lệ duy nhất: **phủ định / side-effect thật**
(vd user nói "đừng", "huỷ") — ở đó repair sai gây hậu quả ngoài điểm số nên vẫn
block + ask. Ngược lại, ask chỉ đúng khi thông tin **genuinely missing**: không có
trong audio, context, history, và không lấy được bằng read hợp lệ.

### 1.4. Bài học từ E7 phase 0 — đừng xây guard phổ quát

Phase 0 shadow audit của guard provenance time/amount kết luận `CPU_NOT_READY`:
chỉ 31/459 gold write được giám sát được ALLOW chắc chắn (6,75%), 428 UNKNOWN,
0 BLOCK [CODE_INSPECTED: `analysis/runtime/E7_PHASE0_SHADOW_AUDIT_2026-10-28.md`,
`analysis/e7_shadow/`]. Bài học chuyển sang tài liệu này [INFERENCE]: **đừng xây
một bộ máy "hiểu mọi time/amount" rồi mới quyết.** Grounding đợt 4 phải là
**họ hẹp, nhận diện được rõ ràng** (tên + slot typed + tone), mỗi họ có luật
ALLOW/BLOCK/UNKNOWN riêng, và UNKNOWN thì đi về ask/guard — không bao giờ lặng lẽ
coi UNKNOWN là cho phép.

## 2. Thuật toán quyết định: ba giá trị, không phải nhị phân

Mỗi slot tranh chấp đi qua ba giá trị, tương thích với `GroundingResult.status`
(EXACT / FUZZY_GROUNDED / AMBIGUOUS / UNKNOWN) của `lifemate/grounding.py`
[CODE_INSPECTED] và với bài học ALLOW/BLOCK/UNKNOWN của E7 phase 0:

```
REPAIR   — đủ bằng chứng: đúng 1 candidate, không xung đột kênh, slot typed
           chuẩn hoá được duy nhất. Gọi write với giá trị đã ground.
ASK      — genuinely missing: không có mốc thời gian, không có candidate, hoặc
           ≥2 candidate không phân biệt được và không có slot phân biệt.
BLOCK    — bằng chứng mâu thuẫn hoặc giá trị bị cấm (ID bịa, tiền/tiền tệ mơ hồ
           không phân giải được, phủ định). Trả validation error về cho model
           (không tự ask): ambiguity đi về model dưới dạng lỗi validation, theo
           đúng hành vi của grounding.py — KHÔNG auto-ask từ tầng grounding.
```

Quy tắc theo loại slot [INFERENCE]:

| Slot | REPAIR khi | ASK khi |
|---|---|---|
| Tên/địa điểm (ID) | Đúng 1 candidate qua text + FED + tone (§3), hoặc đúng 1 candidate sau rescore phá hoà | 0 candidate; ≥2 candidate cùng string chuẩn hoá khác ID và không có slot phân biệt (số điện thoại, quan hệ, phòng) trong câu/history |
| Time | Giá trị cụ thể trong request, hoặc suy ra duy nhất bằng date arithmetic từ reference của request (vague chỉ cho DATE, hour vẫn thiếu → ASK) | Không có mốc nào; chỉ có vague ("sáng mai") mà slot cần hour |
| Amount/money | Parser typed cho đúng 1 giá trị sau khi nhân đơn vị (nghìn/triệu/tỷ) | Đơn vị mơ hồ không phân giải được (vd separator kiểu Mỹ lẫn kiểu Việt không có context) |
| Enum/trạng thái | Đúng 1 giá trị khớp catalog | Không khớp giá trị nào |

**Trùng tên khác ID** [INFERENCE]: grounding phải trả **(candidate id, canonical
string)**, không chỉ string. Hai candidate cùng string chuẩn hoá (NFC) nhưng khác
id → AMBIGUOUS vĩnh viễn ở tầng text; chỉ cứu được bằng (a) slot phân biệt đi kèm,
(b) recency trong history, (c) ask. Lưu ý: ask có mang được choices ("which An?")
hay chỉ hỏi tên slot là **Q-L1 — UNVERIFIED**; nếu ask không mang choices thì
trùng tên không slot phân biệt là không cứu được bằng ask (vẫn ask vì đó là hành vi
đúng của task, nhưng kỳ vọng điểm mẫu đó = 0).

**Tên viết tắt** [INFERENCE]: chỉ ground khi đúng 1 candidate theo rule显式, kiểm
chứng được: initials các từ trong tên, substring là một từ đầy đủ trong tên, hoặc
tên app trong `installed_apps`. ≥2 candidate → AMBIGUOUS → ask. **Tuyệt đối không
bảng alias do LLM bịa** (alias không có bằng chứng trong sample vẫn là đoán). Tần
suất viết tắt thực tế trong ZAIC chưa đếm — đo ở E-asr-1 (xem `plans/round4-test-roadmap.md`).

## 3. Các kênh tín hiệu — mỗi kênh đo cái gì, và không được quyết một mình

### 3.1. Mã phonetic tiếng Việt: không có thư viện sẵn, đừng dùng mã tiếng Anh

- **"Vietnamese Soundex / Vietnamese Double Metaphone": KHÔNG TỒN TẠI**
  [INFERENCE từ tìm kiếm âm tính nhiều lần]. `jellyfish` 1.3.0 chỉ có `soundex`,
  `metaphone`, `nysiis` tiếng Anh (không có `dmetaphone` ở bản này)
  [LOCALLY_VERIFIED: `dir(jellyfish)`]. Demo va chạm [LOCALLY_VERIFIED]: Hương và
  Hang cho cùng mã ở cả ba thuật toán (Soundex H520, Metaphone HNK, NYSIIS HANG) —
  mã tiếng Anh bỏ nguyên âm sau phụ âm đầu và gom phụ âm theo nhóm tiếng Anh nên
  **mù trước cấu trúc âm tiết tiếng Việt** (onset–nucleus–coda–tone). Dùng mã tiếng
  Anh để match tên Việt gây va chạm hệ thống. **Loại.**
- **Epitran `vie-Latn` + Panphon: dùng cho segmental, KHÔNG đo được tone**
  [CODE_INSPECTED: epitran 1.35.3, `data/map/vie-Latn.csv`, `data/post/vie-Latn.txt`;
  license MIT-Modern-Variant / MIT]. Post-processor "Move tones to end of word"
  làm mất tone trong output thực tế [LOCALLY_VERIFIED: Bình/Bính → cùng `biɲ`,
  FED Panphon = 0.0; Minh/Mình → cùng `miɲ`, FED = 0.0]. Các cặp gộp phương ngữ
  cũng không phân biệt được: Trâm/Châm → cùng `cɤ̆m`, Sang/Xang → cùng `saŋ`,
  Dũng/Rũng → cùng `zuŋ` (FED 0.0). Ngược lại, khác nucleus cho FED lớn
  (Dương/Giang = 1.0, Hương/Hang = 1.0); cặp onset gần Nam/Lam = 0.125.
  Hệ quả [INFERENCE]: **tone phải là kênh riêng lấy từ dấu chính tả** (NFD →
  diacritic → tone digit 1–6), vì chính tả tiếng Việt mã hoá tone đầy đủ. Một cặp
  "cùng segmental + khác tone" phải xử lý bằng luật tone riêng, không bằng ngưỡng
  FED. Thang FED bị nén ở đầu dưới (0.0 / 0.0625 / 0.125 / 1.0) nên **một ngưỡng FED
  duy nhất không tách sạch** "cùng người sai tone" khỏi "khác người onset gần" —
  các cặp onset gần cần kênh acoustic (§3.3). Mọi ngưỡng FED/margin phải quét trên
  train_cal, không hand-set.
- **viphoneme 3.0.0: mạnh nhất về phương ngữ, nhưng license + dependency rủi ro**
  [CODE_INSPECTED: API `T2IPA`/`vi2IPA`, công thức âm tiết `(C1)(w)V(G|C2)+T`,
  ba phương ngữ Bắc/Trung/Nam, hai hệ tone Pham/Cao]. License wheel ghi
  "AILAB / Free for non-commercial use", toàn văn **chưa đọc** — bài thi có giải
  thưởng có phải "non-commercial" hay không là **UNVERIFIED**. Import thực tế lỗi
  `ModuleNotFoundError: No module named 'vinorm'` [LOCALLY_VERIFIED] — wheel không
  kéo đủ dependency (vinorm, underthesea, eng_to_ipa + model downloads), ma sát lớn
  cho Docker offline. **Chỉ xem xét khi cần phương ngữ, sau khi đọc toàn văn license
  và fix dependency. Không làm mặc định.**
- **underthesea / VnCoreNLP: KHÔNG có hàm phonetic** [SECONDARY]. underthesea chỉ
  có `word_tokenize` (đầu vào cho segmenter) và NER phía text; VnCoreNLP chỉ có 4
  annotator `wseg/pos/ner/parse`, chạy Java `-Xmx2g` — lựa chọn tồi cho Docker
  offline + 30s/mẫu.

### 3.2. Mã âm tiết tự định nghĩa (kênh bổ sung, đã chạy prototype)

Vì không có thư viện mã phonetic tiếng Việt, đề xuất mã 4 thành phần
`onset|nucleus|coda|tone`, parse bằng longest-match (onset: ngh, gh, kh, nh, ph,
th, tr, ch, gi, qu, …; nucleus: iê, yê, uô, ươ, ia, ua, ưa, …; coda: ng, nh, ch, c,
m, n, p, t) và tone từ diacritic sau chuẩn hoá NFD (ngang=1, sắc=2, huyền=3,
hỏi=4, ngã=5, nặng=6), kèm chế độ gộp miền Nam có chủ đích (d/gi/r→Z, tr/ch→C,
s/x→S) [LOCALLY_VERIFIED prototype: Bình `b|i|nh|3` vs Bính `b|i|nh|2`; Trâm/Châm
gộp thành `C|a|m|1` ở chế độ Nam]. Ưu điểm so với epitran: **tone là thành phần
显式, và gộp phương ngữ là lựa chọn có log**, không gộp ngầm. Nhược điểm: đây là
thiết kế đề xuất [INFERENCE], chưa validate trên lỗi ASR thật; cần kiểm thử trên
tên đa âm tiết và "qu/gi" đặc biệt. Vai trò: **kênh bổ sung cho FED, không thay
thế epitran.**

```python
# Mã âm tiết — bản phác, chưa phải code triển khai cuối (cần kiểm thử trên train).
# Input: một từ tiếng Việt đã chuẩn hoá NFC. Output: "onset|nucleus|coda|tone".
# Quy tắc gộp miền Nam chỉ bật khi có flag southern_merge=True, và phải log lại.
TONE_DIGIT = {"": 1, "\u0301": 2, "\u0300": 3, "\u0309": 4, "\u0303": 5, "\u0323": 6}

def tone_digit(word: str) -> int:
    import unicodedata
    for ch in unicodedata.normalize("NFD", word):
        if ch in TONE_DIGIT:
            return TONE_DIGIT[ch]
    return 1  # không dấu thanh = ngang (chỉ đúng khi từ đã có dấu đầy đủ)

def syllable_code(word: str, southern_merge: bool = False) -> str:
    # Phác: tách tone trước, rồi longest-match onset/nucleus/coda trên phần còn lại.
    # Danh sách onset/nucleus/coda đầy đủ phải lấy từ đếm trên train, không hardcode
    # mù — đoạn code này chỉ cố định *dạng* mã, không cố định *bảng* âm tiết.
    raise NotImplementedError("fill onset/nucleus/coda tables from train counts first")
```

### 3.3. Bằng chứng âm thanh: word-confidence có sẵn, rescore là tie-breaker

- **faster-whisper word-probability** [CODE_INSPECTED: faster-whisper 1.2.1,
  `transcribe.py`, MIT]: khi `word_timestamps=True`, `find_alignment()` dùng
  cross-attention của chính Whisper (`median_filter_width=7`); công thức chính xác
  là **trung bình xác suất token của decoder trên các token thuộc về từ đó**.
  Cách dùng đúng [INFERENCE]: word-probability và segment `avg_logprob` /
  `no_speech_prob` là tín hiệu **chọn span nghi ngờ để verify**, không bao giờ quyết
  repair-vs-ask một mình — vì đó là decoder confidence, không phải bằng chứng
  acoustic độc lập; lỗi LM-confident vẫn có probability cao.
- **Teacher-forcing rescoring** [INFERENCE từ semantics API HF — chưa đọc code,
  cần verify trước khi implement]: cho Whisper chạy forward với `labels` = biến thể
  transcript chứa candidate A vs B; tổng logprob cao hơn thì audio ủng hộ biến thể
  đó. Đây là tín hiệu duy nhất gắn trực tiếp với audio mà không cần model mới
  (cùng PhoWhisper, vài forward cho slot tranh chấp). Caveat: rescoring dùng **cùng
  model đã decode sai** nên không độc lập hoàn toàn — chỉ đảo được lỗi do
  LM-decoding gây ra, không cứu được lỗi cả acoustic lẫn LM đều ủng hộ sai. Vai trò:
  **tie-breaker, không phải oracle.** Chi phí: đo trên hardware thật trước khi chốt.
- **whisper-timestamped / CTC segmentation / WhisperX** [SECONDARY, UNVERIFIED
  phần lớn]: whisper-timestamped cần openai-whisper PyTorch (không phải add-on cho
  faster-whisper); CTC segmentation cần model CTC — Whisper là encoder-decoder,
  không có CTC head, nên không dùng trực tiếp; WhisperX cần model alignment riêng
  cho tiếng Việt (chưa tìm thấy). **Không chọn.**

### 3.4. Decode-time biasing: `hotwords` của faster-whisper chỉ là prompt conditioning

[CODE_INSPECTED: faster-whisper 1.2.1, `transcribe.py` dòng 1542–1548]: `hotwords`
**không phải logit bias, không có pass boosting riêng** — token của hotword chỉ
được nối vào decoder prompt (cùng kênh với `initial_prompt`); bị **ignore hoàn toàn
khi `prefix` được set**; bị truncate ở `max_length // 2 - 1` (~223 tokens).
Hệ quả [INFERENCE]: biasing mềm, không bảo đảm; model vẫn có thể không sinh ra
hotword. Khuyến nghị thực hành: 2-pass cho mẫu nghi ngờ — pass 1 lấy candidate từ
**nguồn read-free trước** (context/history, vì mọi read đều là tool call), pass 2
với `initial_prompt` dạng câu tự nhiên (không phải list tên trần), tên hiếm để
cuối prompt, tổng ≤224 tokens. **Bắt buộc đo overcorrection riêng** (tên bị chèn
dù audio không có) — nếu hệ thống thì bỏ 2-pass và giữ tầng grounding xác định.
- **pyctcdecode hotwords là biasing thật ở mức score** [CODE_INSPECTED: pyctcdecode
  0.5.0, Apache-2.0; KenLM LGPL] — nhưng decode **CTC logits**, không cắm được vào
  PhoWhisper. Muốn dùng phải thêm wav2vec2-vi (95M, license mirror CC-BY-NC-4.0
  **SECONDARY, phải đối soát HF card**) + beam search KenLM trên CPU + train/tune
  LM: 2× ASR, đắt và phức tạp so với lợi ích chưa đo. **Không ưu tiên.**
- **TCPGen** [SECONDARY, paper arXiv 2210.16554]: pointer generator + prefix tree,
  phải train chung với ASR — không retrofit được PhoWhisper frozen. Hướng dài hạn,
  không phải cơ chế cho deadline 16/11.

### 3.5. Embedding: kênh yếu nhất cho bài toán này

- BKAI bi-encoder (PhoBERT-base-v2, 768-dim, **bắt buộc input đã tách từ**,
  license UNVERIFIED) và BGE-M3 (đa ngữ 100+ ngôn ngữ gồm tiếng Việt, ~568M,
  license MIT theo nguồn thứ cấp) [SECONDARY]. Lý do cấu trúc [INFERENCE]: tonal
  minimal pairs là từ khác nghĩa — embedding ngữ nghĩa được train để tách các từ
  khác nghĩa ra xa, trong khi lỗi ASR cần điều ngược lại (hai dạng khác tone nhưng
  cùng một người phải gần nhau). Với tên ngắn 1–2 âm tiết, embedding không mã hoá
  thanh điệu hệ thống. **Không có ngưỡng cosine/margin nào được verify cho name
  matching** — nếu dùng, phải sweep trên train_cal và báo repair-right/wrong/ask
  theo loại slot. Chi phí: BGE-M3 +568M (tổng 4,812B, vẫn < 6B) nhưng +load/inference
  và vendoring weights. **Chỉ xem xét khi cần match tên dài/địa điểm biến thể phức
  tạp mà phonetic không phủ được, và chỉ là kênh phụ sau phonetic.**

### 3.6. Speech-to-intent trực tiếp: không có drop-in

- "VSLUE": **không tồn tại dưới tên đó** (tìm chính xác chỉ ra VLUE và tài liệu
  không liên quan) — không được trích dẫn.
- VN-SLU (Interspeech 2024): dataset SLU tiếng Việt thật đầu tiên (17.321
  utterances, 240 speakers, 20,1 giờ, smart-home/assistant). Baselines trên data
  của họ: intent acc 86–92%, nhưng **utterance acc chỉ 30–38%** — cách rất xa mức
  hash-grade (một slot sai là cả mẫu 0 điểm). Intent inventory không khớp catalog
  tool ZAIC → adapt = training lại, không kịp trước 16/11 với độ tin cậy chưa biết.
- **Kết luận:** không có speech-to-intent mã nguồn mở nào dùng trực tiếp được cho
  ZAIC. Pipeline thay thế chính là §2 + §3.1–§3.4 + §4 của tài liệu này.

## 4. Pipeline tinh gọn — đọc chỉ khi thực sự cần

```
1. Model đề xuất call → validate() TRƯỚC (miễn phí, không tăng trace).
   - Lỗi schema → trả validation error về cho model, model tự sửa trong cùng lượt.
   - Đừng dùng read để kiểm tra schema hay "xác minh" giá trị.
2. Chỉ read khi tham số thực sự thiếu và read đó có thể cung cấp nó:
   - read cho candidate ID (contacts.search), cho giá trị quan sát (list_bills),
     cho điều kiện (forecast/weather) khi task yêu cầu kiểm tra điều kiện.
   - Mỗi read phải gắn với đúng một slot thiếu đã nêu tên; read "cho chắc" là cấm.
3. KHÔNG read-after-write. Kết quả write đã echo item vừa tạo.
4. Ambiguity → validation error về cho model, KHÔNG auto-ask từ tầng grounding.
5. Chỉ gọi sys.ask_missing_info khi §2 kết luận genuinely missing, với đúng
   (tool_name, params) của gold ask — và chỉ khi đó ask mới là hành vi đúng
   (dù điểm mẫu đó vẫn 0 nếu gold là write: ask đúng ≠ ask có điểm).
```

Lưu ý về ask [UNVERIFIED, Q-L1]: ask có mang được choices hay chỉ hỏi tên slot
chưa được xác nhận — pipeline không được thiết kế dựa trên giả định ask mang choices.

## 5. Chuẩn hoá typed — số đọc bằng chữ, tiền có đơn vị, ngày tương đối

### 5.1. Số/tiền: parse theo nhóm big-unit, đơn vị là một phần của giá trị

Bản naive parse tuyến tính **fail 5/8** (vd "một trăm năm mươi nghìn" → 1.050.000 do
lỗi nhân "mươi" vào giá trị trăm). Bản group-based (tách tại tỷ/triệu/nghìn, mỗi
nhóm parse trăm–mươi–đơn vị, xử lý `rưỡi` = +0.5 unit trước đó) **đạt 13/13** trên
test tổng hợp [LOCALLY_VERIFIED]: "một trăm năm mươi nghìn" → 150.000; "hai triệu
rưỡi" → 2.500.000; "mười lăm" → 15 vs "năm mươi" → 50 (cặp nhầm lẫn kinh điển —
khác nhau ở text nên parser text xử lý được, chỉ còn lớp nhầm lẫn acoustic cần
rescore); "một tỷ hai trăm triệu" → 1.200.000.000. Bảng đơn vị bắt buộc:
nghìn/ngàn = 10³, triệu = 10⁶, tỷ = 10⁹, k = 10³, "rưỡi" = +0.5 unit; biến thể
"mốt/tư/lăm" sau "mươi". **"150 nghìn" ≠ "150" ≠ "150 triệu"** — chuẩn hoá phải
nhân đơn vị trước khi so sánh. Prototype này [INFERENCE + LOCALLY_VERIFIED trên
tổng hợp] chưa validate trên transcript ASR thật (ASR có thể đọc sai "mươi/lăm",
cần acoustic rescore cho các cặp này).

### 5.2. Ngày: dateparser-vi chỉ làm được một nửa

Test với `RELATIVE_BASE` = tối thứ Bảy 2026-10-17 20:00 [LOCALLY_VERIFIED,
dateparser 1.4.3, BSD-3-Clause]: "ngày mai / hôm qua / tuần sau" và "ngày 15 tháng
11 / 15/11" pass; **"thứ hai tới / thứ hai tuần sau / cuối tuần này", "sáng mai /
chiều mai", "2 ngày nữa" đều None — fail.** Điểm mấu chốt [INFERENCE]:
**truyền reference date của sample, không bao giờ dùng wall-clock của Docker**
(ngày chạy private khác ngày ghi sample; 5 lần chạy lặp phải tái lập được).
dateparser giữ nguyên clock của base cho biểu thức chỉ có ngày ("ngày mai" →
20:00) — caller phải tự strip time khi chỉ cần date, đúng ranh giới date-vs-hour
của E7 (date suy ra được, hour thì không). Weekday và vague-time phải tự code trên
nóc dateparser. "sáng mai" fail là **đúng theo thiết kế**: vague time chỉ cho DATE,
hour còn thiếu → ask.

## 6. Rủi ro còn lại

1. Mọi ngưỡng (FED, margin, acoustic margin, cosine) đều chưa có số trên ZAIC —
   tất cả phải sweep trên train_cal, không copy từ paper hay test nhỏ trong báo cáo này.
2. Teacher-forcing route code cho PhoWhisper (HF vs CTranslate2) và chi phí/slot
   chưa verify; N-best API của faster-whisper (sampling loop) chưa đo.
3. Read trả về những field nào (alias/room/relation), context có field reference
   date hay không — chưa verify, ảnh hưởng §2 và §5.2.
4. Ask scoring (Q-L1), reads trong F1 (Q-L3), submitted trace (Q-L2), loop-exhaustion
   (Q-L5) — chưa có câu trả lời từ BTC; pipeline §4 được thiết kế để đúng ở cả hai
   nhánh của Q-L3, nhưng Q-L1/Q-L2/Q-L5 vẫn có thể đổi luật ask.
5. Tần suất thực tế của duplicate names, abbreviations, numbers-as-words trong ZAIC
   train chưa đếm (E-asr-1) — thứ tự ưu tiên các module phụ thuộc vào số này.
6. Toàn văn license viphoneme; license HF card của wav2vec2-vi và BKAI bi-encoder;
   license whisper-timestamped, ctc-segmentation, LaBSE — chưa verify, không dùng
   làm tiền đề cho quyết định.
7. E7 guard vẫn CPU_NOT_READY — tầng grounding này không thay thế guard provenance;
   hai tầng bổ sung nhau (grounding sửa slot, guard chặn write không truy vết được),
   và guard chỉ vào GPU khi phase 0 đạt READY.
