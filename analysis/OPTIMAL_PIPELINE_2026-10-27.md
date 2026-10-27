# Tối ưu pipeline LifeMate — tổng hợp từ đề xuất ZAIC2 + đo trên data thật

> Chỉ phân tích, không sửa code (Codex đang chạy). Số liệu data đo ngày
> 2026-10-27 trên train dev (1.237 mẫu) và public_test (634 mẫu).
> Số liệu model từ web cần đối chiếu lại card HF trước khi nộp — xem cột
> "mức xác minh" ở bảng 1.

## 0. Kết luận trước (đọc 1 phút)

1. **Triển khai đầu tiên: PhoWhisper-medium + Qwen3-4B-Instruct-2507**
   (đề xuất 1 của ZAIC2). Tổng 4,769B < 6B. Đây là nâng cấp rẻ nhất
   mà trúng đúng chỗ đau của data: slot nghe (tiền/giờ/tên) VÀ hiểu
   đúng ý định/phủ định/điều kiện ở turn đầu (xem đính chính §2.2)
   — trong khi LLM giữ nguyên nên không có rủi ro format mới.
2. **A/B thứ hai: Qwen3.5-4B non-thinking** (đề xuất challenger của
   ZAIC2). **Đủ điều kiện về ngày** (ra tháng 3/2026, trước hạn
   26/10/2026) và Apache 2.0 — nhưng có 2 điểm phải kiểm trước khi
   chạy: đúng HF id + chat template, và vLLM có hỗ trợ kiến trúc
   Gated DeltaNet hybrid attention của nó không. Không kiểm 2 điểm
   này thì đừng A/B.
3. **Voxtral: chỉ làm thí nghiệm có điều kiện, và chỉ ở vai trò
   transcriber tiếng Việt** — không làm agent. Lý do: tiếng Việt
   KHÔNG nằm trong danh sách ngôn ngữ hỗ trợ mà hãng công bố, khả
   năng tool-calling trên catalog 147 tool chưa được chứng minh, và
   ghép Voxtral Mini (3B) + Qwen3-4B (4B) = 7B sẽ VƯỢT trần 6B.
4. **Context và latency đều CHƯA ĐO — không kết luận chúng "luôn
   đủ".** Ước lượng từ kích thước prompt cho thấy dư địa context
   lớn, và lập luận cho thấy LLM steps là rủi ro latency chính,
   nhưng cả hai đều chưa đo trên A30 với backend thật (xem đính
   chính §2.3–§2.4). Đừng chọn model vì context dài, và đừng coi
   max_steps=12 là bảo đảm dưới 30 giây.

## 1. Bảng ứng viên — ngân sách, điều kiện, mức xác minh

| Tổ hợp | Tổng tham số | Ngày phát hành | Licence | Mức xác minh |
|---|---|---|---|---|
| Baseline: PhoWhisper-small 0,244B + Qwen3-4B 4,0B | 4,244B | small: 2024 (paper ICLR 2024); Qwen3-4B-2507: 07/2025 | Apache 2.0 (Qwen3 card-confirmed trong repo) | Đã có trong repo |
| ZAIC2-1: PhoWhisper-medium + Qwen3-4B | **4,769B** | medium: cùng họ Whisper, paper 2024 | Chưa xác minh trên card vinai — PHẢI kiểm trước nộp | 769M là kích thước kiến trúc Whisper medium (bảng size chuẩn); card vinai chưa đọc |
| ZAIC2-2: Qwen3.5-4B non-thinking + PhoWhisper-small | 4,244B | **02–03/2026** (small series 02/03/2026), trước hạn 26/10/2026 | Apache 2.0 | Web: nhiều nguồn khớp nhau (xem §6 nguồn) |
| Voxtral Mini làm agent thay LLM | 3B (một mình) | 15–16/07/2025 | Apache 2.0 | Web: hãng công bố |
| Voxtral Mini + Qwen3-4B | **7B — VƯỢT TRẦN, LOẠI** | — | — | Tính trực tiếp từ 3B + 4B |

Lưu ý về Qwen3.5: context native 262K là vô nghĩa ở đây vì trần cuộc
thi là 16K; vocab 248K và kiến trúc hybrid (Gated DeltaNet : full
attention = 3:1) mới là thứ ảnh hưởng tới backend inference. Thinking
mode là mặc định của Qwen3.5 — phải tắt (non-thinking), nếu không
chuỗi reasoning sẽ ăn cả context lẫn 30s/mẫu.

## 2. Data nói gì — cái gì quyết định điểm, cái gì không

### 2.1 Điểm = hash-gated F1, nên LLM quyết định nhiều hơn ASR
Hash sai → mẫu 0 điểm bất kể F1. Hash chỉ phụ thuộc: đúng write
tool, đúng tham số hash-relevant (id, amount, thời gian, enum) và
đúng chuỗi đổi state. ASR chỉ ảnh hưởng điểm khi nó làm hỏng một
slot chảy vào tham số hash-relevant hoặc vào tham số của ask. ASR
hỏng free-text (nội dung SMS, tên địa điểm) chỉ mất F1 (fuzzy), không
mất hash.

### 2.2 Bán kính ảnh hưởng của slot trong dev (đo từ gold args)
- Tham số amount: 86/1.237 mẫu (7%).
- Tham số thời gian/ngày: 301/1.237 (24%).
- Phụ thuộc `contacts.search` (tên → id): 176/1.237 (14%).
- ≥ 3 call: 517/1.237 (42%) — nhóm này là sân của LLM, không phải ASR.
- Ask: 174/1.237 (14%), trong đó ask_only 48, ask_after 126; ask tập
  trung vào call phụ thuộc contact (phone.call 34, sms.send 24,
  ewallet.transfer 15).
- **Đính chính (2026-10-27): kết luận "ASR chỉ ảnh hưởng slot" là
  QUÁ MẠNH và đã sửa.** ASR có thể làm sai cả intent, phủ định,
  điều kiện và tham chiếu — tức làm sai cả bài đa bước, không chỉ
  slot:
  - Điều kiện rẽ nhánh: "nếu mai mưa thì… không mưa thì thôi"
    (họ train_0025/0016/0082) — nghe sai "không" là lật cả nhánh
    hủy/dời/không làm gì, dù mọi tham số bước sau đều lấy từ read.
  - Tự sửa: train_0007 "đặt báo thức 5 giờ nhé, à không, 5 rưỡi
    sáng mai" — chỉ nghe được mệnh đề đầu là tạo sai alarm.
  - Phủ định/hủy: "à thôi khỏi", "đừng thêm" — nghe sai phủ định
    biến empty thành write (hoặc ngược lại), sai cả hash lẫn F1.
  - Tham chiếu: tên người (Minh/Mẹ/Hương), từ hạn định ("bên
    kho", "bên hậu cần") — nghe sai tên là chọn sai candidate
    ngay từ bước search, rồi sai cả chuỗi sau.
  - Vì vậy ASR-medium hoàn toàn có thể cải thiện cả nhóm đa bước
    (thông qua turn đầu đúng), và thí nghiệm ASR ở §3 phải đo cả
    độ chính xác nhánh/hủy/sửa, không chỉ slot-error. Thứ tự vẫn
    là ASR-medium trước (rẻ, ít rủi ro), LLM-challenger sau — nhưng
    lý do không còn là "ASR có trần ở nhóm slot" nữa.

### 2.3 Audio và latency — ASR không phải nút thắt
Đo bằng stdlib wave trên file thật:
- Final audio: dev trung bình 7,0s (p90 10,8s, max 15,7s); public
  trung bình 7,6s (p90 11,8s, max 17,1s).
- Final + history user audio (public phải transcribe cả history vì
  không có transcript): trung bình 14,4s (p90 24,6s, max 43,2s).
- **Đính chính (2026-10-27): latency medium-ASR trên A30 là CHƯA
  ĐO, không phải "chỉ vài giây".** Lập luận "audio ngắn nên ASR
  rẻ" là suy luận, không phải số đo: chưa có lần chạy nào trên A30
  (máy phân tích không có GPU), chưa rõ backend (faster-whisper
  CTranslate2 vs transformers) và chưa đo mẫu max-audio (43,2s).
  Phải đo end-to-end trên A30 theo đúng backend sẽ nộp, báo
  p50/p90/max trên mỗi mẫu, trước khi chốt medium.
- **Đính chính: max_steps=12 KHÔNG bảo đảm dưới 30 giây.** Trường
  hợp xấu nhất là 12 × (xử lý prompt ngày càng dài theo history
  tới 24 turn + observation tích lũy + sinh JSON) cộng ASR trên
  tối đa 43s audio, và tốc độ phụ thuộc backend (vLLM nhanh hơn
  transformers đáng kể). max_steps và non-thinking chỉ là guard
  giảm rủi ro, không phải chứng minh latency. Thinking mode của
  Qwen3.5 (nếu quên tắt) vẫn là thứ dễ làm vỡ 30s nhất.

### 2.4 Context — không phải nút thắt
- Installed apps/mẫu: trung bình 9,2 (p90 13, max 18) → catalog lọc
  theo mẫu đã nhỏ.
- Transcript: trung bình 97 ký tự (p90 144, max 296).
- History: trung bình 4,5 turn (p90 12, max 24).
- **Đính chính (2026-10-27): "context luôn đủ" là CHƯA ĐO.** Các
  con số trên là ký tự và số turn, không phải token thực tế của
  prompt (catalog đã lọc + history đầy đủ + observation tích lũy
  qua các bước, kể cả observation dài). Ước lượng cho thấy dư địa
  lớn, nhưng phải đo token prompt thật (p90/max trên dev, với
  observation đầy đủ) trước khi kết luận. Lợi thế context 262K
  của Qwen3.5 vẫn là vô nghĩa ở đây vì trần cuộc thi là 16K —
  điểm này giữ nguyên — nhưng không được trình bày "vài nghìn
  token" như số đo.

### 2.5 Empty — 5 nguyên nhân khác nhau, đừng dạy model "thiếu gì cũng hỏi"
89 mẫu empty trong dev, xem phân tích đầy đủ (kèm cặp đối chiếu)
trong `EMPTY_VS_ASK_2026-10-27.md`: yêu cầu bị hủy, tán gẫu/báo cáo
việc đã xong, app cần thiết không được cài (đặt khách sạn Đà Lạt;
"chuyển 350k cho Mai" gold rỗng vì mẫu đó không cài
contacts/ewallet/banking — không phải "không giải quyết được" chung
chung), và điều kiện đã được history giải quyết.
Hệ quả: chính sách empty-vs-ask phải học từ data, không được mặc
định "thiếu thông tin → ask". Đây là nhóm mà prompt baseline dễ mất
điểm nhất nếu chỉ dạy "hỏi khi thiếu".

## 3. Thí nghiệm phân biệt — làm theo thứ tự rẻ → đắt

**Phân biệt scorer proxy với evaluator chính thức (đính chính
2026-10-27).** `lifemate/scoring.py` là scorer proxy dựng từ mô tả
portal (hash đúng mới tính F1, empty đúng mới 1 điểm, fuzzy
token-F1 > 0,6) — gói dữ liệu KHÔNG kèm evaluator chính thức, và
các câu hỏi Q-L1 (cách chấm ask), Q-L3 (read có tính F1 không),
Q-L5 (hết vòng lặp nộp gì) vẫn mở. Mọi "điểm" trong tài liệu này
đều là điểm proxy, không phải điểm chính thức, và không được
trình bày như điểm chính thức.

**Quy tắc chọn/kiểm (đính chính 2026-10-27): chọn cấu hình trên
dev, giữ held-out cho kiểm tra sau khi chốt.** Toàn bộ lựa chọn
dưới đây chạy trên dev (toàn bộ 1.237 mẫu dev, tách nhóm — không
chỉ 26 probe). Sau khi chốt cấu hình thì đóng băng, chạy held-out
(308 mẫu) MỘT lần để kiểm tra khái quát, rồi báo cáo kết quả đó
nguyên trạng. Held-out KHÔNG được dùng để chọn lại, đổi prompt
hay đổi model — nếu held-out lệch dev thì đó là phát hiện về độ
khái quát, không phải vòng chọn mới.

1. **ASR slot-error + branch-accuracy, không cần LLM (rẻ nhất, làm
   trước):** transcribe audio của nhóm probe + mẫu có
   amount/time/contact bằng small và medium, so với transcript
   gold của train trên: (a) slot-error (số tiền, giờ, tên) và
   (b) độ chính xác nhánh/hủy/sửa (điều kiện mưa/không mưa, phủ
   định "thôi/khỏi", tự sửa "à không") — vì đính chính §2.2 cho
   thấy ASR sai ở (b) cũng làm mất hash. Không so WER chung
   chung. Medium chỉ được giữ nếu thắng ở (a) hoặc (b).
2. **Hai bộ smoke + dev theo nhóm với ZAIC2-1 vs baseline:** đo
   proxy score tách theo nhóm: slot-nghe (amount/time/contact)
   vs đa bước (≥3 call) vs ask vs empty vs history-conditional.
   Kỳ vọng sửa đổi: ZAIC2-1 có thể thắng cả nhóm slot-nghe VÀ
   nhóm đa bước (qua turn đầu đúng) — thắng ở nhóm đa bước không
   còn là dấu hiệu nghi ngờ nữa, miễn là thắng đó tập trung ở
   các mẫu có điều kiện/phủ định/tự sửa ở turn đầu.
3. **Qwen3.5 A/B (chỉ sau khi qua 2 pre-check ở §1):** cùng dev,
   tách nhóm đa bước + ask + history-conditional (kiểu
   train_0082). Chỉ promote khi thắng proxy hash-gated trên dev,
   không phải khi thắng benchmark chung hay khi "trả lời hay hơn".
4. **Voxtral (chỉ nếu còn thời gian):** so transcription tiếng Việt
   với PhoWhisper trên cùng audio probe, đo slot-error. Chỉ xét
   tiếp vai trò agent nếu transcription thắng rõ VÀ tìm được bằng
   chứng tool-calling có cấu trúc — hiện chưa có.
5. **Đóng băng → kiểm held-out một lần → rồi mới xét SFT:** SFT chỉ
   khi prompt-only đi ngang trên dev VÀ held-out kiểm tra không
   phản đối. Recipe đã có (blueprint-first + gold cố định trước +
   rejection sampling, P2). SFT trước 16/11 là rủi ro thời gian +
   overfit template, không phải nước đi đầu tiên.

## 4. Đính chính số liệu read (2026-10-27, theo Codex)

Định nghĩa read duy nhất được dùng: tool có `kind: "read"` trong
catalog (read = không đổi state; write = đổi state/tạo hành động;
meta = `sys.ask_missing_info`). Trên gold dev: **read 1.280 /
2.843 (45,0%)**, write 1.389, meta 174. Con số 1.138 theo heuristic
tên tool trong bản phân tích trước là sai (bỏ sót 155, tính thừa
13) và đã được sửa trong `WAIT_ANALYSIS_2026-10-27.md` §3 — không
dùng heuristic tên nữa.

## 5. Những gì KHÔNG đổi dù chọn tổ hợp nào (stack 0 tham số, đã có trong recommended config)

Typed grounding theo loại slot, selective reads (read thừa có thể
tính F1 — Q-L3 vẫn mở nên đọc thừa là rủi ro), validator trước call
(validate không ghi log, đã xác minh bằng code), observation vào
prompt sau mọi call, loop guard + max_steps 12. Các thứ này quyết
định phần lớn điểm số ở nhóm read/ask/đa bước và không tốn tham số
— đổi model mà bỏ stack này là đổi sai chỗ.

## 6. Nguồn web cho §1 (đối chiếu lại card HF trước nộp)

- Qwen3.5 small series (0,8B/2B/4B/9B) phát hành 02/03/2026, Apache
  2.0, 4B, context native 262K; dòng Qwen3.5 bắt đầu 16/02/2026.
- Whisper medium = 769M tham số theo bảng kích thước chuẩn của họ
  Whisper (PhoWhisper kế thừa kiến trúc này; card vinai vẫn cần đọc
  để xác nhận licence/ngày).
- Voxtral Mini 3B và Small 24B phát hành 15–16/07/2025, Apache 2.0;
  ngôn ngữ công bố: Anh, Tây Ban Nha, Pháp, Bồ Đào Nha, Hindi, Đức,
  Hà Lan, Ý — không có tiếng Việt; bản Mini Transcribe chỉ qua API.
