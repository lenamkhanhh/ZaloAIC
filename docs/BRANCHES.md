# Danh mục nhánh LifeMate — 30/10/2026

## Bản chính

- **`main` đã nhận source Run 7** qua merge `6ce0af9dde433036b0501da7e572c5da8921f2e2`.
- Source runtime được chốt là `ddbe0a0b18a6fb9f6e7d261628a51e7a2c6c10c6`; commit này và toàn bộ lịch sử sửa trước đó vẫn nằm trong lịch sử `main`.
- Tài liệu điều hướng và báo cáo CPU cũng nằm trong `main`. Các kết quả CPU ở đây không phải kết quả model hay điểm chính thức.
- Nhánh nghiên cứu bên dưới được giữ vì còn commit riêng chưa nhập vào `main`.

## Các nhánh còn giữ

| Nhánh | SHA đã kiểm tra | Vì sao giữ |
|---|---|---|
| `codex/lifemate-baseline-integration` | [`f2727921`](https://github.com/lenamkhanhh/ZaloAIC/commit/f2727921476775d9aecb197c443d994dc61e646a) | Nhánh tích hợp và kiểm tra baseline riêng; chưa nhập vào source Run 7. |
| `codex/lifemate-model-pilot` | [`39803de5`](https://github.com/lenamkhanhh/ZaloAIC/commit/39803de5ba614f30308afbefca82cb6f9f676539) | Nhánh thử model riêng; cần xem run artifacts trước khi dùng kết quả. |
| `codex/muse-chat3-orchestration` | [`309dc51a`](https://github.com/lenamkhanhh/ZaloAIC/commit/309dc51ad13ce69ce00b451643efca968c73bffe) | Tài liệu điều phối Muse còn tách biệt với runtime. |
| `independent-eval-gg-2026-10-30` | [`abecb515`](https://github.com/lenamkhanhh/ZaloAIC/commit/abecb515f05be2436ac2c2d46f05aa6e3b12b248) | Bộ đánh giá độc lập; là mốc cũ, không thay thế đánh giá source hiện tại. |
| `overnight-capability-audit` | [`d549f583`](https://github.com/lenamkhanhh/ZaloAIC/commit/d549f58318105ee003f9e5139c7299a02d89d43b) | Nghiên cứu capability và protocol huấn luyện, chưa được chấp nhận để train. |
| `sft-prototype-v2` | [`26ba11df`](https://github.com/lenamkhanhh/ZaloAIC/commit/26ba11df8a6abd99a13334346c145135d1838306) | Prototype và validator SFT; chưa phải checkpoint đã train hoặc được chọn. |

Các SHA trên là mốc remote đã kiểm tra khi dọn nhánh. Trước khi tiếp tục một hướng, fetch nhánh và đọc report/artifact của đúng commit.

## Nhánh đã nhập vào `main` rồi xóa ref remote

Trước khi xóa, từng tip dưới đây được kiểm tra là tổ tiên của commit merge `6ce0af9`. Xóa tên nhánh không xóa code hay lịch sử đã nhập vào `main`.

| Ref đã xóa | Tip đã nhập |
|---|---|
| `codex/repo-organization` | `234c4d34` |
| `gg-phone-callback-lifecycle` | `4bd95a51` |
| `gg-r5-number-lifecycle-shadow` | `ff7a288e` |
| `muse/chat3/integration-chat3-20261030-0939` | `99779d88` |
| `muse/chat3/r2-g1-d1-relation` | `d08c2aed` |
| `muse/chat3/r2-g1-h2s11` | `0efcce56` |
| `muse/chat3/r2-grounding-money` | `087651bc` |
| `muse/chat3/r2-lifecycle-p0` | `de8e3d22` |
| `muse/chat3/r2-minh-repin` | `4bc4ea5e` |
| `muse/chat3/r3-harness-roster` | `634bd585` |
| `muse/chat3/r3-observer-roster` | `de01dd16` |
| `muse/chat3/r3-p0-phone` | `f80d2cf6` |
| `muse/chat3/r4-phone-guard` | `618d25af` |
| `muse/chat3/r5-identity` | `1102560c` |
| `muse/chat3/r6-recipient` | `a85716e7` |
| `muse/chat3/r7-antecedent` | `ddbe0a0b` |
| `round10-provenance-gates-fixes` | `61d84390` |

## Quy tắc cập nhật

- Khi source mới được kiểm tra, cập nhật `STATUS.md` và ghi commit đầy đủ.
- Giữ các nhánh nghiên cứu tách riêng cho tới khi kết quả được kiểm chứng và nhập có chủ đích.
- Không xóa nhánh chỉ vì nhánh cũ hoặc tên khó hiểu; chỉ xóa sau khi đã xác minh nội dung nằm trong `main` hoặc đã được thay thế rõ ràng.
