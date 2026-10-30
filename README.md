# ZaloAIC — LifeMate

Pipeline trợ lý tiếng Việt: audio → ASR → LLM → gọi tool qua `zaic_tools`.
Phạm vi phát triển hiện tại: **LifeMate**. DataMate chỉ giữ làm tài liệu lịch sử.

## Bắt đầu ở đây

| Cần làm gì? | Đọc ở đâu? |
|---|---|
| Biết bản đang dùng, kết quả và lỗi còn mở | [Trạng thái hiện tại](docs/STATUS.md) |
| Tìm runtime, tests, audit và tài liệu cũ | [Bản đồ repo](docs/REPOSITORY_MAP.md) |
| Chọn đúng nhánh thay vì nhầm main/integration cũ | [Danh mục nhánh](docs/BRANCHES.md) |
| Chạy lại CPU tests và paired dev | [Kiểm chứng CPU](docs/verification/CPU_2026-10-30.md) |
| Tải data, tham khảo CLI baseline | [RUN_LIFEMATE.md](RUN_LIFEMATE.md), đọc cùng trang trạng thái |

## Mốc code đã kiểm chứng

- Nhánh: [`muse/chat3/r7-antecedent`](https://github.com/lenamkhanhh/ZaloAIC/tree/muse/chat3/r7-antecedent).
- Source: [`ddbe0a0`](https://github.com/lenamkhanhh/ZaloAIC/commit/ddbe0a0b18a6fb9f6e7d261628a51e7a2c6c10c6).
- CPU: **849 tests qua**, không fail/error/skip trên máy audit có đủ data/reference.
- Paired dev: **976 tool calls trong phạm vi audit, 2 lượt bị đánh dấu chặn, 0 lỗi**.
- G&G chỉ quan sát/ghi log. `pending_ask_stop` mặc định OFF. Không suy kết quả này thành điểm chính thức hay model score.

`main` chưa chứa toàn bộ các vòng sửa này. Nhánh có tên `integration` cũng chưa chắc là mới nhất.
Nhánh `codex/repo-organization` tổ chức lại tài liệu trên cùng runtime với source pin ở trên; không đổi hành vi pipeline.

## Thư mục chính

```text
lifemate/       runtime, config, split và tests pipeline
tests/          tests grounding, G&G, observer, export
analysis/       audit scripts và artifact phân tích có phiên bản
docs/           trạng thái, bản đồ, nhánh, cách kiểm chứng
research/       nghiên cứu và báo cáo các vòng trước
competition/    ghi chép luật/đề bài theo thời điểm đọc
plans/          kế hoạch lịch sử, cần đối chiếu trạng thái hiện tại
deep-dives/     prototype/nghiên cứu trước đây
```

Đường dẫn code/script cũ giữ nguyên để không phá import, lệnh chạy hoặc link lịch sử.
Raw data/audio/weights không được thêm vào repo.

[README nghiên cứu trước khi tổ chức lại](docs/history/README_before_organization.md) được giữ nguyên nội dung, có nhãn lịch sử.
