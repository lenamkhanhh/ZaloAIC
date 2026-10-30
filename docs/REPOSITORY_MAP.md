# Bản đồ repo

Đọc [trạng thái](STATUS.md) trước. Giữ đường dẫn cũ để tái lập được, phân biệt vai trò bằng bản đồ này.

## Runtime và kiểm tra

| Đường dẫn | Vai trò |
|---|---|
| [lifemate/agent.py](../lifemate/agent.py) | Vòng agent, grounding/observer hooks, pending ask |
| [lifemate/config.py](../lifemate/config.py), [configs](../lifemate/configs/) | Flags và cấu hình; tên recommended không thay thế evidence |
| [lifemate/adapter.py](../lifemate/adapter.py) | Cầu nối simulator chính thức |
| [lifemate/lifemate_grounding.py](../lifemate/lifemate_grounding.py) | Chuẩn hóa/grounding |
| [lifemate/lifemate_gates_adapter.py](../lifemate/lifemate_gates_adapter.py) | Kết hợp gate, evidence, selection |
| [lifemate/lifemate_callback_negation.py](../lifemate/lifemate_callback_negation.py) | Chọn người/hành động, current/history, phủ định, tham chiếu |
| [lifemate/lifemate_observer.py](../lifemate/lifemate_observer.py) | Quan sát, roster và decision log |
| [lifemate/shadow_export.py](../lifemate/shadow_export.py) | CLI export và log schema validator |
| [lifemate/run.py](../lifemate/run.py) | CLI pipeline |
| [tests](../tests/), [lifemate/tests](../lifemate/tests/) | Ghi rõ module/backend/pass/fail/skip khi báo kết quả |
| [analysis/gg_paired_audit.py](../analysis/gg_paired_audit.py) | Paired gold dev, source/harness/split phải khớp |

## Nguồn lịch sử

| Đường dẫn | Cách đọc |
|---|---|
| [analysis/runtime](../analysis/runtime/) | Báo cáo/brief thí nghiệm cũ, kiểm tra ngày và commit |
| [Evaluation độc lập cũ](https://github.com/lenamkhanhh/ZaloAIC/tree/abecb515f05be2436ac2c2d46f05aa6e3b12b248/analysis/gg_independent_eval) | Nằm ở nhánh evaluation riêng, không ở checkout runtime này; cases công bố không còn là suite kín |
| [research/lifemate](../research/lifemate/) | Research và handoff trước đây |
| [deep-dives](../deep-dives/) | Prototype, không mặc định là runtime |
| [plans](../plans/) | Kế hoạch lịch sử, đối chiếu STATUS trước khi áp dụng |
| [competition](../competition/) | Luật/đề bài ghi theo thời điểm đọc; xác nhận nguồn chính thức |
| [research/datamate](../research/datamate/) | Ngoài scope phát triển hiện tại, giữ để tham khảo |

## Quy ước

- Trạng thái/source đối chứng cập nhật ở [STATUS](STATUS.md).
- Tách CPU tests, scripted traces, gold replay, model inference và official score.
- Giữ báo cáo lịch sử; sửa kết luận bằng link/version mới, không viết lại kết quả cũ.
- Không đưa gold/probe answer metadata vào agent input.
- Raw data/audio/weights và nội dung private của repo bạn không được thêm khi dọn repo public.
- Danh mục nhánh không phải lệnh xóa. Kiểm tra owner/phụ thuộc và bản lưu trước khi archive/xóa.
