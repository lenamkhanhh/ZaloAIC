# Kế hoạch thi đấu — DataMate

> Mọi thử nghiệm đều phải đo **PA** (không chỉ accuracy), thời gian/câu hỏi, và
> tỷ lệ chuyển đổi giữa đúng/sai/abstain/unanswerable. Tách held-out: không đo trên
> dữ liệu đã dùng để viết helper hoặc fine-tune.

## Baseline thực dụng

```
Profiler (không LLM) → Planner (đủ/thiếu dữ liệu) → Coder (SQL/pandas, 1 chương trình)
  → Executor → Checker (tối đa 1–2 vòng sửa) → Formatter tách riêng
  → Quyết định cuối: trả lời / unanswerable / abstain theo ngưỡng đã calibration
```

- Model khởi đầu: Qwen2.5-Coder-7B hoặc Qwen3-8B — **xác minh checkpoint trước**
  (ngày phát hành, tổng tham số thực từ `config.json`, license) vì shortlist hiện
  tại chỉ dựa trên nguồn thứ cấp.
- Tuần 1: đọc evaluator + README + rulebook từng split; viết profiler + helper +
  formatter + unit test; chạy profiler trên train và ghi snapshot schema.
- **Formatter phải pass gần 100% test riêng từng type trước khi đo PA** — nếu
  formatter sai, mọi công sức tính toán đều mất.

## Phân tích quyết định trả lời / bỏ qua dưới Penalized Accuracy

**Toán học (suy luận từ công thức PA, không phải tuyên bố của evaluator):**
với xác suất đúng đã calibration là p, kỳ vọng trả lời = p×(+1) + (1−p)×(−1) =
2p − 1; kỳ vọng abstain = 0. Trả lời có lợi khi **p > 0,5**.

**Vì sao ngưỡng 0,5 trên lý thuyết vẫn nguy hiểm trong thực tế:**

1. **LLM thường overconfident.** Confidence miệng không phải xác suất đúng thực.
   Phải calibration trên held-out của train: chia train thành train/calibration,
   đo accuracy thực theo từng khoảng confidence, rồi mới đặt ngưỡng.
2. **Không dùng một ngưỡng cho mọi câu.** Tách ngưỡng theo type (number/percent dễ
   sai làm tròn hơn boolean), theo độ khó (join nhiều bảng, cửa sổ thời gian phức
   tạp), và theo mức độ bằng chứng (có/không có cột cần thiết).
3. **Unanswerable và abstain là hai quyết định khác nhau, không được gộp:**
   - `unanswerable` đúng được +1, nhưng trả lời một câu unanswerable bằng giá trị
     thì bị −1 theo khung.
   - `abstain` luôn 0 bất kể reference là gì (theo khung).
   - Nếu bằng chứng cho thấy **dữ liệu thiếu trường/bảng/khoảng thời gian cần
     thiết**, ưu tiên phân loại `unanswerable` thay vì abstain mù. Ngược lại, nếu
     dữ liệu có đủ nhưng phép tính không chắc chắn, abstain an toàn hơn đoán.
4. **Sai type = sai hoàn toàn.** Tính đúng nhưng format sai vẫn mất điểm và còn
   bị −1 — formatter phải tách khỏi bước tính toán và có test riêng.

**Tín hiệu calibration thực dụng (kết hợp, rồi học ngưỡng trên held-out):**

| Tín hiệu | Cách đo | Ý nghĩa khi yếu |
|---|---|---|
| Self-consistency giữa nhiều lần sinh code | Sinh 3–5 code độc lập, xem tỷ lệ đồng thuận về giá trị cuối | Đồng thuận thấp → cân nhắc abstain |
| Đồng thuận SQL vs Python/pandas | Cùng câu hỏi, tính bằng cả SQL và pandas, so sánh kết quả | Hai đường khác nhau → có lỗi logic ở một bên |
| Thực thi rỗng / lỗi | Code chạy ra 0 dòng, NULL, hoặc lỗi | Có thể là sai schema linking, sai join, hoặc dữ liệu thực sự trống — phải phân biệt |
| Độ phủ schema | Các cột/bảng cần thiết có tồn tại và có giá trị trong cửa sổ thời gian không | Thiếu cột/bảng/khoảng thời gian → ứng viên `unanswerable` |
| Kiểm tra đơn vị / tiền tệ / khoảng ngày as-of | Kết quả có nằm trong khoảng hợp lý không, có vượt as-of không, đơn vị có khớp câu hỏi không | Vượt as-of hoặc sai đơn vị là dấu hiệu sai logic |

**Không dùng một tín hiệu duy nhất.** Evidence calibration bằng retrieval coverage
trong nghiên cứu SQuAD 2.0 chỉ đạt AUROC 0,5475 (author-reported) — gần như đoán mò
trong nghiên cứu đó; đừng dùng coverage làm tín hiệu abstain duy nhất.

**Ví dụ minh họa (tính toán từ công thức, không phải kết quả ZAIC):** trả lời 100%
với độ chính xác 55% cho PA ≈ 0,10; trả lời 60% với độ chính xác 80% (abstain 40%)
cho PA = 0,36. **Abstain có kỷ luật thắng trả lời bừa, ngay cả khi tỉ lệ trả lời
thấp hơn.** Ngược lại, abstain quá mức cũng mất điểm — tìm điểm cân bằng, không
chỉ "abstain cho an toàn".

## Phân tích lỗi — đo theo nhóm

| Nhóm lỗi | Cách phát hiện | Hướng sửa ưu tiên |
|---|---|---|
| Hiểu nghiệp vụ / rulebook sai | Đối chiếu code với rule đã trích; đếm câu sai do lọc sai (đơn hủy, trả hàng, voucher, VAT) | Trích rule thành assertion; kiểm tra lọc bằng đếm đối chiếu |
| Truy xuất / tính toán sai | Chạy lại code, so kết quả trung gian với tính tay trên mẫu nhỏ | Exploration query + profiling (ReFoRCE/ProSPy); 2 cách tính độc lập |
| Output sai type / thứ tự / độ chính xác | So với evaluator: type, làm tròn 2 chữ số, thứ tự list, tên cột table | Tầng chuẩn hóa output xác định; test riêng từng type |
| Unanswerable nhận nhầm thành trả lời | Đếm câu gold unanswerable mà model trả lời | Grounding check: đáp án phải truy vết được tới dòng/file cụ thể; không truy vết được → abstain/unanswerable |
| Abstention sai (bỏ câu làm được) | Tỉ lệ abstain trên câu gold trả lời được, theo bin confidence | Hiệu chuẩn ngưỡng theo loại câu; giảm ngưỡng khi evidence mạnh |
| Generalization sang doanh nghiệp mới | Đánh giá leave-one-business-type-out trên train | Schema linking dựa trên mẫu giá trị + README, không dựa trên tên bảng đã thuộc; synthetic business mới |

## Nâng cấp ưu tiên (theo thứ tự)

1. **Tầng chuẩn hóa output + hiệu chuẩn abstain theo loại câu** — lever rẻ nhất
   dưới PA.
2. **Sinh 3 candidate + kiểm tra chéo bằng thực thi** (CHESS/BASE-SQL gọn) — giới
   hạn số candidate để vừa 6 giờ.
3. **Exploration/profiling tự động khi README nghèo** (ReFoRCE/ProSPy) + retrieval
   ví dụ kiểu ViR² (rẻ, không cần train lại).
4. **Fine-tune nhỏ trên train ZAIC** (schema linking + sinh code) nếu có GPU và
   thời gian — mỗi bước đều phải đo PA trên business mới
   (leave-one-business-out), không chỉ trên business đã train.
5. **Penalty-based abstention trong training** — chỉ khi đã có pipeline ổn định.

## Hướng ít được biết nhưng đáng thử

- **Planner tách riêng với kiểm tra không dùng LLM:** Planner phải liệt kê tên
  cột/bảng thực sự tồn tại trong profiler (không phải tên do LLM bịa), và Checker
  phải chạy code thật — giảm rủi ro Critic/Planner cùng model với Coder mù cùng
  một lỗi.
- **Synthetic business mới:** đổi tên cột, đổi loại hình từ business train để tập
  generalization, thay vì chỉ sinh thêm câu hỏi trên cùng schema.
- **PhoBERT/encoder nhỏ cho schema/value linking** (135M/370M, cộng vào tổng 15B)
  trong khi LLM chính làm planning/code — tiết kiệm ngân sách so với việc dùng LLM
  lớn cho mọi bước.

## Để sau hoặc loại bỏ

| Quyết định | Lý do |
|---|---|
| Pipeline 4 agent nặng ~20 LLM call/câu làm mặc định | Đe dọa giới hạn 6 giờ |
| MCTS 24 rollout nguyên bản (Alpha-SQL) | Quá đắt nếu không đo và cắt |
| Unit test tự nhiên do LLM sinh (CHESS nguyên bản) | Có thể "đồng lõa" với SQL sai — đổi thành kiểm tra thực thi + kiểm tra chéo |
| Model > 15B, MoE tính tổng > 15B, checkpoint sau 01/10/2026, API thương mại | Vi phạm luật |
| Tối đa hóa coverage mà không calibration | Dưới PA, một câu sai −1 xóa một câu đúng +1 |
| Chuẩn hóa bỏ dấu tiếng Việt | Evaluator giữ dấu thanh sau chuẩn hóa NFC + lowercase |
| Lịch Trung Quốc thay lịch Việt Nam | Lệch 1 ngày trong một số trường hợp do khác múi giờ tính new moon |
| Dùng public/private test để train hoặc sinh synthetic | Cấm tuyệt đối |
| TabPFN và model tabular prediction | Hữu ích cho dự đoán bảng, không trực tiếp giải QA có type exact và rulebook nghiệp vụ |

## Kế hoạch thử nghiệm

| ID | Giả thuyết | Dữ liệu kiểm tra | Metric | Tiêu chí tiếp tục / dừng |
|---|---|---|---|---|
| D1 — Chuẩn hóa output | Formatter tách riêng loại bỏ lỗi format | 50 kết quả tính đúng, chạy qua formatter | Tỉ lệ format đúng theo từng type | Baseline phải pass gần 100% test này trước khi đo PA |
| D2 — Baseline | LLM ≤ 14B + 1 chương trình + ngưỡng abstain 0,5 cho đường cơ sở | Toàn bộ public test | PA + tỉ lệ đúng/sai/abstain theo loại câu | Đây là đường cơ sở cho mọi nâng cấp sau |
| D3 — Hiệu chuẩn abstain | Ngưỡng theo loại câu, học trên held-out, thắng ngưỡng lý thuyết 0,5 | Public test chia 2 nửa (chọn ngưỡng nửa 1, đo nửa 2) | PA | Giữ nếu PA tăng ≥ 0,03 so với D2 và ngưỡng ổn định khi chia public test làm 2 nửa |
| D4 — Kiểm tra chéo | 2 cách tính độc lập, chỉ trả lời khi đồng thuận | 50 câu held-out | PA, tỉ lệ abstain | Giữ nếu PA tăng mà tỉ lệ abstain không tăng quá 10 điểm phần trăm |
| D5 — Generalization | Leave-one-business-type-out phát hiện overfit loại hình | Train, giấu 1 loại hình, test trên đó | PA trên business bị giấu | Nếu PA giảm > 0,15 khi giấu 1 loại hình, ưu tiên exploration/profiling + synthetic business mới trước khi fine-tune |
| D6 — Ngân sách thời gian | Cấu hình đầy đủ vừa 6 giờ private test | Toàn bộ public test, ngoại suy | Tổng thời gian, giây/câu hỏi | Nếu vượt 6 giờ: cắt candidate trước, giảm vòng revision sau, giữ profiler + formatter + abstain |
| D7 — Planner | Planner tách riêng cải thiện unanswerable mà không làm mất câu đúng | 50 câu held-out gồm cả câu unanswerable đã biết | Unanswerable đúng, câu đúng bị chuyển nhầm thành unanswerable, PA tổng | Giữ nếu unanswerable đúng tăng mà câu đúng bị chuyển nhầm không tăng đáng kể |
| D8 — Multi-candidate | 5 candidate + lọc thực thi + đồng thuận thắng 1 candidate | 50 câu held-out | PA, giây/câu hỏi | Giữ nếu PA tăng đủ bù thời gian |
| D9 — Fan trap / join ngầm | Aggregate trước khi join và liệt kê khóa join từ profiler tránh lỗi nhân đôi | 10 câu hỏi cố tình có fan trap và join ngầm | Tỉ lệ tránh được lỗi | Sửa helper/join rule cho tới khi pass toàn bộ 10 câu |

**Thứ tự làm việc đề xuất (trước deadline 16/11/2026):** tuần 1 nền tảng không cần
LLM + baseline; tuần 1–2 baseline LLM + 1 candidate; tuần 2 nâng cấp rẻ (Planner,
multi-candidate, cross-check, calibration); tuần 2–3 nâng cấp đắt (revision, synthetic
có kiểm chứng, LoRA) chỉ khi còn thời gian và pass D5; trước khi đóng Docker: chạy
toàn bộ pipeline trong Docker offline, đo thời gian tổng, kiểm tra log code + kết
quả mỗi câu hỏi, kiểm tra tổng tham số ≤ 15B bằng config thực tế, kiểm tra không
có gọi mạng lúc inference. **Luôn có phương án dự phòng:** nếu fine-tune hoặc MCTS
làm vỡ ngân sách thời gian hoặc giảm PA trên business mới, quay về baseline — baseline
chạy được và đã calibration vẫn tốt hơn pipeline phức tạp nhưng chậm hoặc overfit.
