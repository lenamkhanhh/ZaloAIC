# Danh mục nhánh — snapshot 30/10/2026

Snapshot trước lần push nhánh dọn tài liệu: **23 nhánh remote**. Không nhánh nào bị xóa/force-push trong đợt này.

## Chọn nhanh

- **Code đối chứng đã kiểm chứng:** muse/chat3/r7-antecedent @ ddbe0a0.
- **Điểm vào tài liệu mới:** codex/repo-organization; base ddbe0a0, chỉ docs/ignore.
- **main:** 1caa885a, chưa chứa mọi sửa Run 7. Không tự đồng bộ bằng merge trong lần dọn này.
- **codex/lifemate-model-pilot, codex/lifemate-baseline-integration:** nhánh thí nghiệm riêng, cần đọc run artifact; lần dọn không xác nhận chất lượng model của chúng.
- **sft-prototype-v2:** prototype SFT riêng, không nằm trong runtime đối chứng.

## Toàn bộ refs đã đọc

“Lịch sử/tham chiếu” ở đây chỉ là nhãn điều hướng, không cho phép xóa. Nhánh thí nghiệm chưa kiểm tra trong lần dọn được ghi riêng thay vì suy đã merge/xong.

| Nhánh | SHA lúc kiểm tra | Vai trò điều hướng |
|---|---|---|
| `codex/lifemate-baseline-integration` | [`f2727921`](https://github.com/lenamkhanhh/ZaloAIC/commit/f2727921476775d9aecb197c443d994dc61e646a) | Thí nghiệm riêng; trạng thái cần đọc artifact |
| `codex/lifemate-model-pilot` | [`39803de5`](https://github.com/lenamkhanhh/ZaloAIC/commit/39803de5ba614f30308afbefca82cb6f9f676539) | Thí nghiệm riêng; trạng thái cần đọc artifact |
| `codex/muse-chat3-orchestration` | [`309dc51a`](https://github.com/lenamkhanhh/ZaloAIC/commit/309dc51ad13ce69ce00b451643efca968c73bffe) | Tài liệu giao việc Muse, không phải runtime |
| `gg-phone-callback-lifecycle` | [`4bd95a51`](https://github.com/lenamkhanhh/ZaloAIC/commit/4bd95a51f713cd8c6cbfa984baab23bf4a753d89) | Lịch sử/tham chiếu; chưa xét điều kiện xóa |
| `gg-r5-number-lifecycle-shadow` | [`ff7a288e`](https://github.com/lenamkhanhh/ZaloAIC/commit/ff7a288e668f37e96c03bf9318d974e3a8e6d2a4) | Lịch sử/tham chiếu; chưa xét điều kiện xóa |
| `independent-eval-gg-2026-10-30` | [`abecb515`](https://github.com/lenamkhanhh/ZaloAIC/commit/abecb515f05be2436ac2c2d46f05aa6e3b12b248) | Mốc evaluation độc lập trước đây |
| `main` | [`1caa885a`](https://github.com/lenamkhanhh/ZaloAIC/commit/1caa885ac35f2719f85ef553db457b984e6d2131) | Main công bố cũ, không phải source Run 7 |
| `muse/chat3/integration-chat3-20261030-0939` | [`99779d88`](https://github.com/lenamkhanhh/ZaloAIC/commit/99779d88b61e4abe5e12bab51f5a59c724b29b1f) | Thành phần/mốc Run 2–6 trước source Run 7 |
| `muse/chat3/r2-g1-d1-relation` | [`d08c2aed`](https://github.com/lenamkhanhh/ZaloAIC/commit/d08c2aed6edc2f1335f923d2351220d6bd5cb51d) | Thành phần/mốc Run 2–6 trước source Run 7 |
| `muse/chat3/r2-g1-h2s11` | [`0efcce56`](https://github.com/lenamkhanhh/ZaloAIC/commit/0efcce56f2341fce68383fd8a2599e2cad3efd63) | Thành phần/mốc Run 2–6 trước source Run 7 |
| `muse/chat3/r2-grounding-money` | [`087651bc`](https://github.com/lenamkhanhh/ZaloAIC/commit/087651bc28b0d84572d363f851d64f1498734466) | Thành phần/mốc Run 2–6 trước source Run 7 |
| `muse/chat3/r2-lifecycle-p0` | [`de8e3d22`](https://github.com/lenamkhanhh/ZaloAIC/commit/de8e3d22d1490d6a71ffbce6c8cc478ee7b18efd) | Thành phần/mốc Run 2–6 trước source Run 7 |
| `muse/chat3/r2-minh-repin` | [`4bc4ea5e`](https://github.com/lenamkhanhh/ZaloAIC/commit/4bc4ea5ecf8281e239b089778cf8ef2c8ed3ae18) | Thành phần/mốc Run 2–6 trước source Run 7 |
| `muse/chat3/r3-harness-roster` | [`634bd585`](https://github.com/lenamkhanhh/ZaloAIC/commit/634bd5859ad8d6250590674e5bfc351d86618d9b) | Thành phần/mốc Run 2–6 trước source Run 7 |
| `muse/chat3/r3-observer-roster` | [`de01dd16`](https://github.com/lenamkhanhh/ZaloAIC/commit/de01dd1691133443861f16f735e636e344b60f9a) | Thành phần/mốc Run 2–6 trước source Run 7 |
| `muse/chat3/r3-p0-phone` | [`f80d2cf6`](https://github.com/lenamkhanhh/ZaloAIC/commit/f80d2cf64bcac38329054c6b0404d8961822cd6a) | Thành phần/mốc Run 2–6 trước source Run 7 |
| `muse/chat3/r4-phone-guard` | [`618d25af`](https://github.com/lenamkhanhh/ZaloAIC/commit/618d25af5dcdc6c5411a4b4db3972c954fb2b612) | Thành phần/mốc Run 2–6 trước source Run 7 |
| `muse/chat3/r5-identity` | [`1102560c`](https://github.com/lenamkhanhh/ZaloAIC/commit/1102560c41df0aa75eb62827d00a5324d6864a8b) | Thành phần/mốc Run 2–6 trước source Run 7 |
| `muse/chat3/r6-recipient` | [`a85716e7`](https://github.com/lenamkhanhh/ZaloAIC/commit/a85716e79b39341b7011f93714a727ecd983fbaa) | Thành phần/mốc Run 2–6 trước source Run 7 |
| `muse/chat3/r7-antecedent` | [`ddbe0a0b`](https://github.com/lenamkhanhh/ZaloAIC/commit/ddbe0a0b18a6fb9f6e7d261628a51e7a2c6c10c6) | Source đối chứng CPU hiện tại |
| `overnight-capability-audit` | [`d549f583`](https://github.com/lenamkhanhh/ZaloAIC/commit/d549f58318105ee003f9e5139c7299a02d89d43b) | Lịch sử/tham chiếu; chưa xét điều kiện xóa |
| `round10-provenance-gates-fixes` | [`61d84390`](https://github.com/lenamkhanhh/ZaloAIC/commit/61d84390cf652b9490de5f5db8378d5802c11182) | Lịch sử/tham chiếu; chưa xét điều kiện xóa |
| `sft-prototype-v2` | [`26ba11df`](https://github.com/lenamkhanhh/ZaloAIC/commit/26ba11df8a6abd99a13334346c145135d1838306) | Prototype SFT riêng |

## Khi có source mới

Cập nhật STATUS, ghi full SHA và kết quả audit mới. Giữ các mốc cũ để so sánh. Không dùng tên nhánh động thay thế source pin trong báo cáo.
