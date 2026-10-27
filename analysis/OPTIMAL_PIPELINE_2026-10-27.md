# Tối ưu pipeline LifeMate — tổng hợp từ đề xuất ZAIC2 + đo trên data thật

> Chỉ phân tích, không sửa code (Codex đang chạy). Số liệu data đo ngày
> 2026-10-27 trên train dev (1.237 mẫu) và public_test (634 mẫu).
> Số liệu model từ web cần đối chiếu lại card HF trước khi nộp — xem cột
> "mức xác minh" ở bảng 1.

## 0. Kết luận trước (đọc 1 phút)

1. **Triển khai đầu tiên: PhoWhisper-medium + Qwen3-4B-Instruct-2507**
   (đề xuất 1 của ZAIC2). Tổng 4,769B < 6B. Đây là nâng cấp rẻ nhất
   mà trúng đúng chỗ đau của data: slot nghe (tiền/giờ/tên) — trong
   khi LLM giữ nguyên nên không có rủi ro format mới.
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
4. **Context 16K không phải nút thắt; latency 30s thì LLM mới là nút
   thắt, không phải ASR.** Đừng chọn model vì context dài.

## 1. Bảng ứng viên — ngân sách, điều kiện, mức xác minh

| Tổ hợp | Tổng tham số | Ngày phát hành | Licence | Mức xác minh |
|---|---|---|---|---|
| Baseline: PhoWhisper-small 0,244B + Qwen3-4B 4,0B | 4,244B | small: 2024 (paper ICLR 2024); Qwen3-4B-2507: 07/2025 | Apache 2.0 (Qwen3 card-confirmed trong repo) | Đã có trong repo |
| ZAIC2-1: PhoWhisper-medium + Qwen3-4B | **4,769B** | medium: cùng họ Whisper, paper 2024 | Chưa xác minh trên card vinai — PHẢI kiểm trước nộp | 769M là kích thước kiến trúc Whisper medium (bảng size chuẩn); card vinai chưa đọc |
| ZAIC2-2: Qwen3.5-4B non-thinking + PhoWhisper-small | 4,244B | **02–03/2026** (small series 02/03/2026), trước hạn 26/10/2026 | Apache 2.0 | Web: nhiều nguồn khớp nhau (xem §5 nguồn) |
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
- Kết luận: nâng cấp ASR có trần lợi ích rõ ràng (nhóm slot nghe),
  còn nâng cấp LLM ảnh hưởng tới nhóm lớn hơn (đa bước + ask +
  history). Vì vậy thứ tự đúng là: ASR-medium trước (rẻ, ít rủi ro),
  LLM-challenger sau (đắt, cần A/B theo nhóm).

### 2.3 Audio và latency — ASR không phải nút thắt
Đo bằng stdlib wave trên file thật:
- Final audio: dev trung bình 7,0s (p90 10,8s, max 15,7s); public
  trung bình 7,6s (p90 11,8s, max 17,1s).
- Final + history user audio (public phải transcribe cả history vì
  không có transcript): trung bình 14,4s (p90 24,6s, max 43,2s).
- Với faster-whisper trên A30, cả small lẫn medium đều xử lý xong
  lượng audio này trong vài giây — phần lớn ngân sách 30s/mẫu thuộc
  về LLM (tối đa 12 bước × sinh JSON). Nâng small → medium gần như
  không tốn thêm ngân sách thời gian đáng kể, nhưng phải đo thật
  trên mẫu max-audio (43s) trước khi chốt.
- Bù lại: thinking mode của Qwen3.5 (nếu quên tắt) hoặc tăng max_steps
  mới là thứ làm vỡ 30s. Giữ max_steps 12 và non-thinking là guard
  latency, không chỉ là guard chất lượng.

### 2.4 Context — không phải nút thắt
- Installed apps/mẫu: trung bình 9,2 (p90 13, max 18) → catalog lọc
  theo mẫu đã nhỏ.
- Transcript: trung bình 97 ký tự (p90 144, max 296).
- History: trung bình 4,5 turn (p90 12, max 24).
- Prompt thực tế chỉ vài nghìn token, xa trần 16K. Lợi thế context
  262K của Qwen3.5 là vô nghĩa ở đây; đừng trả giá (backend rủi ro,
  format mới) để đổi lấy context không dùng tới.

### 2.5 Empty — 5 nguyên nhân khác nhau, đừng dạy model "thiếu gì cũng hỏi"
89 mẫu empty trong dev, ví dụ thật cho thấy ít nhất 5 loại: yêu cầu
bị hủy giữa chừng ("à thôi khỏi"), tán gẫu, báo cáo việc đã xong,
ngoài phạm vi app (đặt khách sạn Đà Lạt), và không giải quyết được
("chuyển 350k cho Mai" nhưng gold rỗng — không hỏi, không gọi).
Hệ quả: chính sách empty-vs-ask phải học từ data, không được mặc
định "thiếu thông tin → ask". Đây là nhóm mà prompt baseline dễ mất
điểm nhất nếu chỉ dạy "hỏi khi thiếu".

## 3. Thí nghiệm phân biệt — làm theo thứ tự rẻ → đắt

1. **ASR slot-error, không cần LLM (rẻ nhất, làm trước):** transcribe
   audio của nhóm probe + mẫu có amount/time/contact bằng small và
   medium, so slot-error (số tiền, giờ, tên) với transcript gold
   của train — không so WER chung chung, vì WER không phân biệt slot
   hash-relevant với free-text. Medium chỉ được giữ nếu thắng ở slot.
2. **Smoke-5 + held-out theo nhóm với ZAIC2-1 vs baseline:** đo
   hash-gated score tách theo nhóm: slot-nghe (amount/time/contact)
   vs đa bước (≥3 call) vs ask vs empty. Kỳ vọng: ZAIC2-1 thắng ở
   nhóm 1, hòa ở các nhóm còn lại. Nếu thắng cả nhóm đa bước thì
   nghi ngờ (ASR không giải thích được) — kiểm tra lại.
3. **Qwen3.5 A/B (chỉ sau khi qua 2 pre-check ở §1):** cùng held-out,
   tách nhóm đa bước + ask + history-conditional (kiểu train_0082).
   Chỉ promote khi thắng hash-gated, không phải khi thắng benchmark
   chung hay khi "trả lời hay hơn".
4. **Voxtral (chỉ nếu còn thời gian):** so transcription tiếng Việt
   với PhoWhisper trên cùng audio probe, đo slot-error. Chỉ xét
   tiếp vai trò agent nếu transcription thắng rõ VÀ tìm được bằng
   chứng tool-calling có cấu trúc — hiện chưa có.
5. **SFT để cuối cùng:** chỉ khi prompt-only đi ngang trên held-out.
   Recipe đã có (blueprint-first + gold cố định trước + rejection
   sampling, P2). SFT trước 16/11 là rủi ro thời gian + overfit
   template, không phải nước đi đầu tiên.

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
