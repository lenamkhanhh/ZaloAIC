# Lộ trình kiểm thử thực nghiệm đợt 4 — trên tập train local

> Lộ trình này chỉ dùng **train local** và **dev LifeMate đã có**. Không dùng held-out
> để tune (held-out chỉ đo sau khi khoá, theo đúng giao thức các plans hiện tại).
> Không dùng public_test để học/chỉnh ngưỡng (DataMate) hay để chọn mẫu (LifeMate).
> Không giả định GPU ngoài route Kaggle của Codex (T4x2, FP16 — không phải bằng chứng
> A30). Mỗi thí nghiệm có tiêu chí vào (entry), tiêu chí ra (exit), và thứ nó chặn
> (blocks). Thí nghiệm nào không đạt exit thì dừng ở đó, không chạy tiếp bằng cảm tính.
>
> Tài liệu gốc: `research/lifemate/asr-repair-decision-framework.md` (LifeMate),
> `research/datamate/abstain-calibration-protocol.md` (DataMate),
> `research/comparison.md` (shortlist cập nhật đợt 4).

## 0. Quy tắc chung cho mọi thí nghiệm

1. **Không hardcode đáp án probe.** Mọi script test dùng dữ liệu tổng hợp tự tạo hoặc
   đọc từ train qua loader chính thức; không chép ID/số tiền/câu trả lời thật vào
   code, prompt, hay danh sách.
2. **Không sửa inference, không chạy model, không mở rộng tập mẫu** nếu thí nghiệm
   đó không ghi rõ là cần chạy model — và mọi lần chạy model đều cần phê duyệt riêng
   của user trước (theo đúng luật scope của repo).
3. **Ghi lại mọi số đo kèm điều kiện đo** (commit, seed, split, hardware). Số không
   kèm điều kiện đo không được dùng để quyết định.
4. **Batch push:** tích luỹ mọi file của một vòng rồi push một lần (theo workflow
   GitHub của user), không push từng file lẻ.

## 1. DataMate — xác minh dữ liệu trước mọi thí nghiệm (D-0, bắt buộc, chặn tất cả)

> **Kết quả kiểm kê 2026-10-28 [LOCALLY_VERIFIED] — phần lớn D-0 đã xong:**
> train 3000 câu / 30 business (biz_101–biz_130; phần lớn 118–119 câu, 7 business
> có 40 câu), public_test 1000 câu / 14 business (dev_001–dev_014) và **không có
> `answers.jsonl`** (giao thức "không dùng public_test để tune" đứng vững);
> định dạng file train: 99 xlsx, 20 csv, 1 sqlite (biz_123/pos.sqlite);
> schema `calendar.csv`: `date,weekday,lunar_day,lunar_month,lunar_year,lunar_leap,
> holiday`, phủ 2024-01-01–2027-12-31; gold percent thang 0–100; gold number là số
> thuần; date ISO cả `yyyy-mm-dd` và `yyyy-mm`; phân bố loại đáp án: number 1884,
> percent 578, string 88, list 193, unanswerable 70, date 145, table 19, boolean 23;
> **không có field type tường minh** trong README (LOBO chạy nhánh pseudo-type).
> Phần còn lại của D-0: suy ra pseudo-type cho 30 business train (schema
> fingerprint + từ khoá README) và xác nhận split private dùng cùng schema trước
> khi nộp. **Hệ quả ngân sách:** nếu private cùng quy mô public_test (~1000 câu)
> thì trần 6 giờ cho trung bình **21,6 giây/câu** — thấp hơn ~40,81 giây/sample của
> XiYan trên BIRD dev; mọi kiến trúc tín hiệu phải đo lại với mốc này.

- **Entry:** đã tải `train.zip` và `public_test.zip` từ portal (đường dẫn trong
  `competition/datamate.md`).
- **Việc làm:**
  1. Giải nén và **liệt kê file từng split** (không tính PA, không tune gì ở bước này).
  2. Xác nhận public test có/không có `answers.jsonl`. **Nếu zip thật có đáp án thì
     toàn bộ giao thức "không dùng public_test để tune" phải viết lại theo bằng
     chứng file đó** — dừng lại, báo user, không tự ý tiếp tục với giao thức cũ.
  3. Đếm: số business, số câu hỏi từng business, số type (nếu có field type trong
     metadata/README từng business), phân bố loại câu hỏi (number/percent/string/
     date/boolean/list/table/unanswerable).
  4. Đọc schema `calendar.csv` thật (tên cột, khoảng ngày phủ, có cột âm lịch tường
     minh hay không) và đối chiếu với thiết kế lookup generic trong
     `research/datamate/abstain-calibration-protocol.md` §5.4 — viết lại module nếu
     schema khác giả định.
  5. Đếm dạng gold của câu percent (0–100 hay 0–1) và câu tiền tệ (số thuần hay kèm
     đơn vị/hậu tố) trên `answers.jsonl` của train; xác định mode làm tròn bằng cách
     so output `ROUND_HALF_UP` với gold (nếu có case lệch thì đổi mode và ghi lại).
  6. Xác định nhánh type: có field type tường minh (dùng type thật cho LOBO) hay
     phải dùng pseudo-type từ schema fingerprint (ghi rõ là proxy có nhiễu).
- **Exit:** có một file ghi nhận `datamate-data-inventory.md` (số business, số câu,
  schema calendar.csv, dạng gold percent/tiền, nhánh type) — và mọi tài liệu dùng
  schema/dạng gold đều khớp với inventory này.
- **Blocks:** D-1, D-2, D-3, D-4, D-5 (mọi thí nghiệm DataMate cần dữ liệu thật).

## 2. LifeMate — đếm lỗi trước khi xây (E-asr-1)

- **Entry:** có train local + loader chính thức. Chỉ dùng CPU.
- **Việc làm:** đếm trên train (không dùng held-out): tần suất duplicate names
  (cùng string chuẩn hoá, khác ID), abbreviations (tên viết tắt), numbers-as-words
  (số đọc bằng chữ, tiền có đơn vị), vague-time (chỉ có ngày, thiếu hour), và các
  cặp tonal minimal pairs trong candidate sets.
- **Exit:** bảng tần suất theo loại lỗi. Thứ tự ưu tiên các module §3–§5 của tài
  liệu LifeMate được sắp lại theo bảng này (loại lỗi hiếm thì làm sau, không làm
  trước loại lỗi phổ biến).
- **Blocks:** thứ tự ưu tiên của E-asr-2, E-asr-3.

## 3. LifeMate — sweep ngưỡng grounding trên train_cal (E-asr-2)

- **Entry:** có E-asr-1 (biết loại lỗi nào phổ biến). Chỉ dùng CPU, chỉ dùng
  train_cal (không phải held-out, không phải public_test).
- **Việc làm:** với mỗi loại slot (tên, time, amount): quét FED threshold, margin,
  và acoustic-margin (nếu có word-probability) trên train_cal; báo repair-right /
  repair-wrong / ask theo từng loại slot. Không hand-set ngưỡng, không copy weight
  1.0/1.2/0.6 của RECOVER.
- **Exit:** bộ ngưỡng + margin có số đo trên train_cal (kèm số mẫu từng bin; bin
  < 30 mẫu thì ghi rõ là thiếu mẫu, không kết luận). Ngưỡng này là **ứng viên**, chưa
  phải ngưỡng khoá — ngưỡng khoá chỉ sau khi đo trên holdout theo plans hiện tại.
- **Blocks:** E-asr-3 (prototype grounding dùng ngưỡng này).

## 4. LifeMate — prototype grounding CPU (E-asr-3)

- **Entry:** có ngưỡng ứng viên từ E-asr-2. Chỉ dùng CPU, không chạy model.
- **Việc làm:**
  1. Implement mã âm tiết `onset|nucleus|coda|tone` + tone-digit từ NFD + chế độ
     gộp miền Nam có log; kiểm thử trên tên đa âm tiết và "qu/gi" đặc biệt.
  2. Implement parser số/tiền group-based (§5.1 tài liệu LifeMate) và dateparser-vi
     với `RELATIVE_BASE` của sample + weekday/vague-time tự code; kiểm thử trên
     dữ liệu tổng hợp trước, rồi trên train_cal.
  3. Implement luật ba giá trị REPAIR/ASK/BLOCK (§2 tài liệu LifeMate) dưới dạng
     hàm thuần, test trên các case tổng hợp (đúng 1 candidate, 0 candidate, trùng
     tên khác ID, vague-time, tiền mơ hồ đơn vị).
- **Exit:** mọi unit test tổng hợp pass; tỉ lệ REPAIR/ASK/BLOCK trên train_cal được
  báo cáo (không phải điểm proxy — vì chưa chạy model, chưa có điểm). Prototype
  này là **tầng grounding**, chưa phải thay đổi inference của agent.
- **Blocks:** mọi thí nghiệm GPU dùng grounding mới (cần phê duyệt riêng của user).

## 5. LifeMate — đo chi phí rescore và overcorrection của 2-pass (E-asr-4, E-asr-5)

- **E-asr-4 (rescore):** verify route code teacher-forcing cho PhoWhisper (HF vs
  CTranslate2) trước khi implement; đo thời gian/forward trên hardware thật cho slot
  tranh chấp. **Exit:** có số giây/slot + kết luận có/không đủ ngân sách 30s/mẫu
  (với số slot tranh chấp trung bình từ E-asr-1). Nếu route code không verify được
  thì dừng — rescore ở trạng thái thiết kế, không implement mù.
- **E-asr-5 (2-pass biasing):** chạy faster-whisper 2-pass (pass 1 → candidate từ
  context/history → pass 2 với `initial_prompt` câu tự nhiên, tên hiếm cuối prompt,
  ≤224 tokens) trên tập mẫu nghi ngờ; **đo overcorrection riêng** (tên bị chèn dù
  audio không có). **Exit:** có tỉ lệ overcorrection. Nếu overcorrection hệ thống
  (> 0 một cách có hệ thống) thì **bỏ 2-pass, giữ tầng grounding xác định** — quyết
  định này ghi lại, không đảo ngược bằng cảm tính.
- **Blocks:** mọi quyết định đưa rescore/2-pass vào agent thật (cần phê duyệt riêng).

## 6. LifeMate — kiểm tra pipeline tinh gọn bằng scorer CPU (E-lean)

- **Entry:** không cần model mới. Chỉ dùng CPU + scorer proxy hiện tại.
- **Việc làm:** trên dev hiện tại, mô phỏng pipeline §4 của tài liệu LifeMate
  (validate-first, read chỉ cho slot thiếu, không read-after-write) bằng cách tính
  lại F1 khi loại các read thừa khỏi submission (giữ nguyên write và hash). Dùng
  đúng hàm `tool_f1` của nhánh experiment.
- **Exit:** có bảng F1 trước/sau khi loại read thừa (kèm caveat: scorer là proxy,
  evaluator chính thức có thể loại read — khi đó lợi ích = 0 nhưng không âm).
- **Blocks:** không chặn gì (đây là đo lường, không phải thay đổi agent).

## 7. LifeMate — serving A30 (S-1, chặn bởi hardware + câu trả lời BTC)

- **Entry:** có quyền truy cập A30 thật (hoặc Docker chính thức của BTC) và câu trả
  lời BTC cho: vLLM/XGrammar có được phép trong Docker nộp bài không (Q-D, vẫn mở);
  licence xLAM-2-3b-fc-r (research-only + tín hiệu NC) có được tính là open-source
  không; licence Hammer2.1-3b trên card gốc.
- **Việc làm (theo thứ tự, dừng khi gặp blocker):**
  1. Dựng vLLM BF16 config trong `research/comparison.md` (đợt 4) trên A30 thật, đo
     latency/mẫu + format-valid rate trên dev của baseline (re-verify so với đường
     HF hiện tại). Chỉ khi vLLM bị chặn mới chuyển sang llama.cpp Q8_0 và đo lại.
  2. Chỉ sau (1) và sau xác nhận của BTC mới thí nghiệm XGrammar — và chỉ khi dev
     cho thấy lỗi format (không phải lỗi giá trị) chiếm đa số.
  3. A/B model theo thứ tự: xLAM-2-3b-fc-r vs baseline (parser `xlam`, sau khi BTC
     xác nhận licence); Hammer2.1-3b vs baseline (parser `hermes`, sau khi đọc
     licence card gốc). Mỗi A/B dùng cùng dev split, cùng prompt, chỉ đổi model/parser.
- **Exit cho mỗi A/B:** có điểm proxy + format-valid rate + latency trên cùng dev
  split, kèm quyết định giữ hay bỏ (không giữ model nào chỉ vì "nghe mạnh hơn").
- **Blocks:** mọi quyết định đưa model mới vào submission (cần phê duyệt riêng +
  licence đã xác nhận).

## 8. DataMate — formatter unit tests trên gold train (D-1)

- **Entry:** có D-0 (inventory + dạng gold percent/tiền + schema calendar.csv).
  Chỉ dùng CPU, chỉ dùng train.
- **Việc làm:** implement formatter §5 của tài liệu DataMate (số âm ngoặc kế toán,
  VNĐ separator + đơn vị, percent theo convention đã đo, date ISO + dd/mm có flag,
  lunar lookup theo schema thật, Excel sheet scoring + merge phân biệt nhãn/số +
  header detection rule) dưới dạng hàm thuần; test trên gold train (so output với
  gold, đếm khớp/lệch theo loại câu).
- **Exit:** tỉ lệ formatter khớp gold theo loại câu (number/percent/date/string/
  table/list) + danh sách case lệch có phân tích nguyên nhân (mode làm tròn?
  separator mơ hồ? header đoán?). Formatter chưa khớp gold thì chưa được dùng để
  đo PA — vì lỗi formatter sẽ bị tính là lỗi hệ thống.
- **Blocks:** D-3 (LOBO đo PA — PA chỉ có nghĩa khi formatter đã khớp gold).

## 9. DataMate — LOBO harness (D-2)

- **Entry:** có D-0 (nhánh type đã xác định) + D-1 (formatter khớp gold). Chỉ dùng
  CPU cho harness (phần sinh code cần model thì theo route Kaggle, cần phê duyệt riêng).
- **Việc làm:** implement harness LOBO Variant B trước (tune pooled trên các type
  còn lại, verify trên type bị giấu, đo một lần); Variant A sau, chỉ khi m ≥ 4
  (tune trên 1 type, verify trên 1 type khác). Báo cáo đúng mẫu bảng §3.5 của tài
  liệu DataMate (per-type + PA min + độ phân tán ngưỡng + LOBO_gap so với
  random-split baseline).
- **Exit:** có bảng LOBO đầy đủ cho hệ thống baseline hiện tại (chưa có calibrator
  mới) — đây là đường baseline để mọi cải tiến sau so sánh. **Không chọn ngưỡng từ
  kết quả LOBO rồi báo lại PA LOBO đó như kết quả độc lập.**
- **Blocks:** D-3 (calibrator — calibrator học trên train_cal của LOBO, không học
  trên holdout).

## 10. DataMate — calibrator vs weighted-sum (D-3)

- **Entry:** có D-2 (harness LOBO chạy được) + features từ pipeline (consensus
  fraction, execution rate, cross-path agreement, evidence coverage, fluency tuỳ
  chọn). Chỉ dùng CPU cho phần fit/đo (phần sinh candidate cần model thì theo route
  Kaggle, cần phê duyệt riêng).
- **Việc làm:** fit Platt và isotonic trên train_cal (của LOBO, không phải holdout);
  chọn bằng NLL/Brier trên LOBO-held-out (không phải trên chính train_cal); so sánh
  calibrator vs weighted-sum cố định của 04 trên cùng holdout, chọn bằng PA (không
  chọn bằng cảm tính). Đo thêm: tỉ lệ "SQL-vs-Python đồng thuận mà vẫn sai" trên dev
  có nhãn (thước đo trực tiếp của "đồng loã" — nếu tỉ lệ này cao thì cross-path
  không được coi là tín hiệu mạnh).
- **Exit:** có calibrator đã khoá (map + τ_khoá = τ_cal + δ LOBO) + bảng so sánh
  calibrator vs weighted-sum + abstain rate trên holdout (để tránh abstain quá tay).
- **Blocks:** mọi quyết định dùng calibrator trong submission (cần phê duyệt riêng).

## 11. DataMate — gate abstain bằng toy tests, không cần model (D-4)

- **Entry:** không cần model, không cần dữ liệu thật. Chỉ dùng CPU.
- **Việc làm:** implement submission-writer gate 5 điều kiện (§4.7 tài liệu
  DataMate) dưới dạng hàm thuần; test trên các input giả: tất cả candidate lỗi;
  top share < τ; hoà top (margin = 0); cluster thắng là rỗng/0/NULL không có bằng
  chứng độc lập; output là sentinel (`"Error SQL"`, `"--error--"`,
  `"SELECT * FROM table_name"`, chuỗi lỗi, chuỗi rỗng không giải thích được).
  Mỗi nhánh phải cho ra abstain (không phải vắng file, không phải chuỗi factoid).
- **Exit:** mọi toy test pass, kèm ghi nhận: **định dạng abstain của DataMate vẫn
  UNVERIFIED** — gate này chỉ khoá được sau khi đọc evaluator/README thật và biết
  mã hoá abstain (bỏ trống? chuỗi đặc biệt? field riêng?). Cho tới lúc đó, gate
  chạy ở chế độ "đo trên train_holdout với giả định abstain = 0".
- **Blocks:** không chặn gì khác (gate là code thuần, gắn được vào pipeline bất kỳ
  lúc nào sau khi encoder được xác nhận).

## 12. DataMate — ngân sách 6 giờ và latency (D-5)

- **Entry:** có checkpoint thật + số câu private ước lượng (nếu có) hoặc số câu
  train (để ngoại suy). Đo trên hardware tương đương máy chấm càng gần càng tốt;
  nếu chỉ có T4x2 thì ghi rõ là ngoại suy, không phải số A30/5090.
- **Việc làm:** đo thời gian/câu cho từng chặng (sinh k candidate, thực thi, cross-
  path, calibrator, formatter); tính tổng thời gian cho toàn bộ private test theo
  công thức tuyến tính theo N (như 04 §4.1); quyết định k, có/không second path,
  có/không logprobs bằng AURC/PA tăng thêm trên holdout so với chi phí (không bật
  mọi tín hiệu mặc định).
- **Exit:** có bảng ngân sách thời gian + quyết định k/second-path/logprobs đã
  khoá. Nếu ngân sách vượt 6 giờ thì cắt theo thứ tự: giảm generator (XiYan-style:
  5 → 3) trước, giảm `ps` (2 → 1) sau, giảm k cuối cùng (vì k nhỏ làm vote share
  nhiễu hơn).
- **Blocks:** mọi quyết định kiến trúc tín hiệu cuối cùng.

## 13. Thứ tự thực hiện tổng thể (đề xuất)

```
Tuần này (CPU-only, không cần phê duyệt chạy model):
  D-0 → E-asr-1 → E-asr-2 → E-asr-3 → E-lean → D-1 → D-4
  (D-0 chặn mọi thí nghiệm DataMate cần dữ liệu thật; E-asr-1 chặn thứ tự ưu tiên
  LifeMate; D-4 làm được ngay, không phụ thuộc dữ liệu)
Sau khi có dữ liệu + phê duyệt chạy model (route Kaggle, cần phê duyệt riêng từng lần):
  E-asr-4 → E-asr-5 → D-2 → D-3
Khi có A30 + câu trả lời BTC:
  S-1 (vLLM đo → A/B xLAM → A/B Hammer, theo thứ tự, dừng khi gặp blocker)
Cuối cùng:
  D-5 (ngân sách 6 giờ, sau khi kiến trúc tín hiệu đã khoá)
```

## 14. Những gì KHÔNG làm trong đợt 4 (ghi rõ để không bị mở rộng scope)

- Không fine-tune model nào (LifeMate hay DataMate) — đợt 4 chỉ có grounding,
  calibration, gate, formatter (code + đo lường).
- Không chạy E7 GPU — E7 guard vẫn CPU_NOT_READY (phase 0); GPU chỉ sau khi phase
  0 đạt READY và có phê duyệt riêng.
- Không mở rộng E5 thêm 28 mẫu — đã hoãn (cơ chế đã biết, rule có trần cấu trúc).
- Không sửa parser E6-C trong đợt 4 — key=value pseudo-call giữ nguyên là hạng mục
  báo cáo (reporting-only), không thay đổi parser trong E7.
- Không tune bất kỳ ngưỡng nào trên public_test (DataMate) hay held-out (cả hai
  track). Held-out chỉ đo sau khi khoá.
- Không trích số BIRD/Spider/DABstep/BFCL thành bảo đảm cho ZAIC — mọi số benchmark
  chỉ dùng để chọn cơ chế, và phải ghi rõ nguồn + phiên bản + split.
