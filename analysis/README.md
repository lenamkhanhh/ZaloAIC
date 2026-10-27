# analysis/ — Tài liệu chẩn đoán LifeMate (chỉ đọc, không phải code)

Mục riêng cho việc đối chiếu giữa bên phân tích và bên code (Codex).
Không chứa raw dataset, audio hay weights.

## Nội dung

- `dev_probe_ids.json` — Danh sách 26 probe, tất cả thuộc 1.237 mẫu
  dev (split `lifemate/splits/train_dev_heldout.json`), kèm lý do
  chọn, kỹ năng cần kiểm tra và lỗi cần phân biệt.
- `WAIT_ANALYSIS_2026-10-27.md` — Kiểm chứng probe bằng label thật,
  gold trace smoke-5, và 2 mẫu cần đọc kỹ (train_1696, train_0082).
- `OPTIMAL_PIPELINE_2026-10-27.md` — Tổng hợp pipeline tối ưu từ
  đề xuất ZAIC2 + số liệu đo trên data (ngân sách, latency,
  context, thí nghiệm phân biệt theo thứ tự rẻ → đắt). Đã sửa các
  kết luận quá mạnh ngày 2026-10-27 (xem §0/§2.2/§2.3/§2.4/§3):
  ASR sai cả intent/phủ định/điều kiện chứ không chỉ slot;
  latency A30 và context đủ đều là chưa đo; scorer là proxy, không
  phải evaluator chính thức; chọn trên dev, held-out chỉ kiểm sau
  khi chốt.
- `OBSERVATION_TRUNCATION_2026-10-27.md` — Replay gold 26 probe đo
  mất thông tin do `repr(result)[:300]`: 14/29 read dài quá 300 ký
  tự, 3 giá trị mất thật (845.000 của train_0003; light_bedroom2
  của train_0004 và train_0069), và đề xuất giữ thông tin theo
  schema.
- `EMPTY_VS_ASK_2026-10-27.md` — Phân tích empty-vs-ask bằng cặp
  đối chiếu dev (thiếu giờ → hỏi; trùng contact → hỏi trừ khi có
  yếu tố phân biệt; bị hủy / app không cài / history giải quyết →
  empty) kèm ngoại lệ và mâu thuẫn label.
- `CONTEXT_BUDGET_2026-10-28.md` + `measure_context_budget.py` —
  Nhánh độc lập 2026-10-28: đo prompt bằng tokenizer thật
  (Qwen3-4B-Instruct-2507 rev cdbee75) theo đúng code nhánh
  `codex/lifemate-baseline-integration` commit e79f9722, trên toàn
  bộ 1.237 mẫu dev. Kết luận: JSON compact đầy đủ vừa ngân sách
  (0/4.080 bước vượt, max 9.415 token), trong khi `repr[:300]` làm
  mất 312/1.168 giá trị bước sau cần dùng và 27,9% leaf phi-boolean.
  Đề xuất tối thiểu: thay `repr[:300]` bằng JSON compact đầy đủ,
  giữ nguyên guard raise khi vượt ngân sách. Script tái lập đã kiểm
  chứng khớp byte-identical với code nhánh trên 30 mẫu. Ràng buộc
  renderer vẫn giữ nguyên: không rút gọn list còn ID/tên, không xoá
  field vì thuộc FREE_TEXT_KEYS, không đổi pipeline đang chạy.

## Hai bộ smoke — đừng nhầm lẫn

- **Bộ smoke của Muse:** train_0025, train_0016, train_0049,
  train_0004, train_0019 (trường `smoke_ids` trong
  `dev_probe_ids.json`).
- **Bộ smoke của Codex:** train_0019, train_0116, train_0025,
  train_0003, train_0008.
- Giao nhau: train_0019, train_0025. Hợp của hai bộ (8 mẫu):
  train_0003, train_0004, train_0008, train_0016, train_0019,
  train_0025, train_0049, train_0116. Cả hai bộ đều là tập con của
  26 probe; không bộ nào chứa mẫu held-out.

## Cách chọn đủ 26 ID (chú ý hành vi của --ids-file)

`lifemate/run.py --ids-file` đọc `smoke_ids` TRƯỚC `probes`, nên
`--ids-file analysis/dev_probe_ids.json` chỉ chạy 5 mẫu smoke của
Muse, không phải 26 mẫu. Để chạy đủ 26 mẫu, dùng một trong hai
cách (không sửa code):

```bash
# Cách 1: liệt kê ID từ trường probes rồi đưa vào --ids
IDS=$(python3 -c "import json; print(','.join(p['id'] for p in json.load(open('analysis/dev_probe_ids.json'))['probes']))")
python3 -m lifemate.run infer --data <data> --split train \
  --config lifemate/configs/recommended.json --ids "$IDS" --out out.jsonl
# Cách 2: file JSON chỉ chứa danh sách trần 26 ID (định dạng bare list
# mà --ids-file cũng chấp nhận), rồi dùng --ids-file với file đó.
```

Chạy bộ smoke của Codex hoặc hợp hai bộ thì dùng `--ids` với danh
sách tương ứng ở trên.

## Metadata probe chỉ dành cho chẩn đoán — tuyệt đối không đưa vào input agent

File probe tuy KHÔNG có mảng gold calls, nhưng các trường `reason`
đã chứa ID/amount/chuỗi đáp án (ví dụ reason của train_0003 nêu
845.000 và c_06; reason của train_0004 nêu light_bedroom2 và 50).
Vì vậy TOÀN BỘ metadata probe — `reason`, `transcript_gold`,
`skill_to_test`, `error_to_distinguish` — và toàn bộ các file
phân tích trong mục này (vốn trích gold để đối chiếu) chỉ dùng để
chẩn đoán SAU khi chạy. Input của agent chỉ gồm audio + context +
history của mẫu, không bao giờ gồm metadata probe hay đáp án gold.

## Quy ước bắt buộc khi dùng các file này

- **Định nghĩa read:** tool có `kind: "read"` trong catalog
  (read = không đổi state; write = đổi state/tạo hành động;
  meta = `sys.ask_missing_info`). Trên gold dev: read 1.280 /
  2.843 (45,0%), write 1.389, meta 174. Không dùng heuristic đoán
  theo tên tool (con số 1.138 cũ theo tên là sai, đã sửa).
- **train_1696 là gold anomaly:** gold chứa luôn call
  `chat_ott.send_message` tới `chat_6142` không tồn tại
  (`ok: true, done: false`). KHÔNG hardcode id sai này vào agent
  hay prompt, không dạy model phát ra id không tồn tại. Khi đo,
  báo cáo mẫu này riêng (ghi chú anomaly).
- **Không hard-code đáp án probe:** file probe cố tình KHÔNG chứa
  gold tool calls. Chấm điểm từ label train bằng
  `lifemate/run.py score`. File trace gold chi tiết KHÔNG nằm
  trong repo (giữ ở máy phân tích) đúng theo thiết kế này.
- **Hỏi chưa có đáp án (Q-L1/Q-L3/Q-L5):** cách chấm ask, read có
  tính F1 không, và hết vòng lặp nộp gì — vẫn mở, xem `gaps.md`.
