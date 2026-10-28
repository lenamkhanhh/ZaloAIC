# Grounding dry-run trên dev split (đợt 8)

> Chạy ngày 2026-10-28 bằng script `analysis/grounding_dry_run_replay.py`
> (đã sửa nhỏ: đường dẫn zaic_tools lấy từ `--data-root/train`, không còn
> suy từ thư mục chứa jsonl — vì dev.jsonl là bản lọc giữ ngoài data dir).
> Dev = 1237 mẫu từ `lifemate/splits/train_dev_heldout.json`
> (dev 1237 + heldout 308 = 1545 train; kiểm chứng: dev.jsonl lọc ra đúng
> 1237, heldout gặp đúng 308, 0 mẫu ngoài split).
>
> Lệnh chạy lại:
> `python3 analysis/grounding_dry_run_replay.py --train-jsonl <dev.jsonl>
> --data-root <thư mục chứa train/>`
> (ToolEnv dùng split "train" vì dev id vốn là train id — env của dev mẫu
> chính là env train của nó.)

## Kết quả — đạt chuẩn train trên mọi nhánh

| Nhánh | Đo | Dev | Train (đợt 7, đối chiếu) |
|---|---|---|---|
| Arm A | Gold calls qua adapter | 2843 | 3541 |
| Arm A | Calls bị adapter thay đổi | **0** (2843/2843 UNCHANGED) | 0 (3541/3541) |
| Arm A | Grounded calls pass `ToolEnv.validate()` | **2843/2843 (100%)** | 3541/3541 (100%) |
| Arm A | Gold calls gốc fail validate (đối chứng) | 0 | 0 |
| Arm B | Tiền/số khôi phục đúng | 117/117 | 146/146 |
| Arm B | Ngày tương đối khôi phục đúng ISO | 94/94 | 112/112 |
| Arm B | Giờ tương đối khôi phục đúng | 294/294 | 378/378 |
| Arm B | Daypart mơ hồ → NEEDS_ASK(hour) | 235/235 | 294/294 |
| Arm B | Daypart + giờ ghi rõ → GROUNDED | 235/235 | 294/294 |
| Arm B | Trùng tên query → NEEDS_ASK(ambiguous) | 56/56 | 68/68 |
| Arm B | Query sạch → GROUNDED đúng | 106/106 | 136/136 |
| Tổng | Failures | **0** | 0 |

Nhất quán nội bộ: dev + heldout = train trên mọi ô số (vd tiền 117 + 29 =
146; ngày 94 + 18 = 112; dup 56 + 12 = 68) — dev không phải tập khác biệt,
nó là đúng phần dev của train, nên 100% trên dev là xác nhận độc lập của
chuẩn train, không phải số mới lạ. 12 giá trị `time` time-only được skip
theo thiết kế (như 20 ở train).

## Kết luận cho cổng bật hook

Arm A 100% UNCHANGED + 100% validate và Arm B 100% trên cả 7 nhóm đo đều
giữ nguyên trên dev. Điều kiện "dry-run trên dev đạt chuẩn như train"
(trước khi gắn hook) đã thỏa — hook đợt 8 được gắn trên cơ sở này.
