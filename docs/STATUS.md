# Trạng thái LifeMate — 30/10/2026

Đầu mối trạng thái của lần tổ chức repo này. Đây là snapshot có ngày, không phải bảng tự cập nhật.

## Source

| Mục | Giá trị |
|---|---|
| Source CPU đã kiểm chứng | `ddbe0a0b18a6fb9f6e7d261628a51e7a2c6c10c6` |
| Commit nhập source và tài liệu vào main | `6ce0af9dde433036b0501da7e572c5da8921f2e2` |
| Main trước khi nhập | `1caa885ac35f2719f85ef553db457b984e6d2131` |
| G&G | Shadow-only: tính quyết định và ghi log, không chặn env.call |
| pending_ask_stop | Mặc định False; khi True, ask thành công kết thúc lượt |

`main` hiện chứa source Run 7 và bộ tài liệu điều hướng. Bản ghi này là snapshot ngày 30/10/2026; fetch `main` để lấy tip mới nhất.

## Đã kiểm chứng độc lập

| Kiểm tra | Kết quả | Phạm vi |
|---|---|---|
| 21 module unittest | 849 pass, 0 fail/error/skip | CPU, difflib, đủ data/frozen reference |
| Paired dev | 976 applicable, fired 2, errors 0 | Gold-relative shadow audit |
| train_0509 | Đúng c_01 qua, sai c_04 bị đánh dấu chặn | Tool result thật, adapter, AgentLoop/simulator |
| Repro ID thiếu phone, current/history | Các repro audit trước vẫn đúng | Scripted/synthetic |
| pending_ask_stop ON | Một ask, không tiêu thụ proposal sau | Scripted generator, simulator thật |
| Observer export OFF/ON | Cùng calls/state; OFF 3 envelope/0 record, ON 3/4 | Scripted-test |

Hai paired fires: train_1005 (trường hợp quan hệ bị chặn bảo thủ), train_1696 (gold anomaly). Bỏ anomaly: 1/975.
**976 là tool calls, không phải mẫu độc lập; 849 là code tests, không phải train examples.**
[Xem lệnh và điều kiện tái lập](verification/CPU_2026-10-30.md).

## Còn mở

- “Lộc bên điện”, relation “tổ điện nước”, vẫn có thể chặn đúng người; “bên nước” đã qua trong probe.
- Hai batch Muse báo: 26/26 đúng và 25/26 đúng; batch sau một false block, không false pass. Không gọi cả hai batch là không lỗi. Hai batch scripts gốc vẫn local bên Muse trong handoff, chưa được audit độc lập này tái chạy.
- Các giới hạn pre-name/cancellation khác đã báo trong Run 7 không được lần dọn repo này tuyên bố đã đóng.
- First-proposal well-formed fabrication vẫn OPEN. pending_ask_stop chỉ xử lý sau ask khi flag bật.
- Vắng trong search không tự chứng minh đã xóa entity.
- Chưa adopt G&G để chặn thật; gold replay không chứng minh precision trên proposal model.

## Model và training

Audit source pin này không chạy ASR/LLM weights hoặc training. Không chuyển kết quả từ notebook/nhánh model khác sang Run 7. Đọc artifact và manifest của đúng nhánh trong [danh mục nhánh](BRANCHES.md).
SFT prototype ở `sft-prototype-v2`, không thuộc runtime Run 7 và không được tài liệu này coi là đã train.
Các câu hỏi BTC về checkpoint/param/evaluator cần câu trả lời riêng; [gaps.md](../gaps.md) là ghi chép lịch sử, không phải evaluator.

## Tiếp theo

Đóng băng source, thu trace model trên dev cố định và so sánh variant có đối chứng; G&G tiếp tục shadow-only trong bước đo. Giữ source/config/input identity để phân biệt lỗi model với lỗi guard. Không đổi split/seed/config mặc định trong lúc dọn tài liệu.
