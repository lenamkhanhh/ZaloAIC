# Round 3 — Ưu tiên 4: Vì sao consensus có thể cùng sai, và nên dùng compute ở đâu?
## DataMate, Zalo AI Challenge 2026 — bản nháp nghiên cứu (không phải code triển khai)

> Phạm vi: chỉ ưu tiên 4. Không sửa repo, không viết lại chuyên đề 1–3.
> Mốc so sánh: commit `8d4721e` của https://github.com/lenamkhanhh/ZaloAIC
> (`deep-dives/04-confidence-abstain-datamate.md` + `.py`).
> Mọi con số ngân sách dưới đây là **ước tính từ giả định ghi rõ**, không phải
> số đo trên dữ liệu ZAIC hay trên 2× RTX 5090. Mọi claim chưa có nguồn đọc
> trực tiếp được ghi **UNVERIFIED**.

---

## 1. Repo đã biết gì, và khoảng trống chính xác là gì?

### 1.1 Repo đã biết (tóm tắt trung thực từ `deep-dives/04` ở mốc 8d4721e)

- Thiết kế hiện tại: **k = 3** candidate, temperature 0,2–0,5, seed khác nhau;
  so sánh **output sau thực thi** (không so văn bản code); 3/3 hoặc 2/3 đồng
  thuận → đáp án tạm thời; sau đó qua hard gate (rule assertion, evidence
  coverage, second path) rồi qua ngưỡng đã khóa.
- Score tổng hợp tự đề xuất: `0,5 × consensus_fraction + 0,3 × second_path_agree
  + 0,2 × evidence_coverage`. Trọng số này **chưa từng được đo** trên dữ liệu
  ZAIC; repo tự ghi là "starting proposal, NOT a tuned result".
- Ngưỡng học trên `train_cal`, đo một lần trên `train_holdout`, ưu tiên tách
  theo business/type; ngưỡng theo type chỉ dùng khi type có ≥ ~30 mẫu, còn
  không thì dùng ngưỡng global.
- Ngân sách theo mô hình tuần tự: `T = N × k × t_gen / G`; với N = 600 (giả
  định của user, **không phải kích thước private test đã xác minh**), k = 3,
  G = 2 → điểm hòa vốn 24 giây/candidate. Repo tự ghi mô hình này là bi quan
  dưới vLLM continuous batching và throughput hệ thống chưa đo.
- Repo đã nêu đúng nguyên tắc cốt lõi: consensus đo **ổn định, không đo đúng**;
  mọi đáp án vẫn phải qua gate; và yêu cầu báo tỉ lệ "agree-but-wrong".

### 1.2 Khoảng trống mà bản nháp này phải khép (5 câu hỏi)

1. **Seed-only có cho thông tin độc lập thật không?** k = 3 chỉ khác seed có
   tách được lỗi hệ thống (cùng đọc sai rule, cùng chọn sai grain, cùng sai
   cửa sổ as-of/Tết) hay chỉ đo lại cùng một phân phối lỗi?
2. **Đa dạng ở đâu mới đáng tiền?** Đa dạng prompt / plan / chiến lược truy
   vấn (SQL vs Python, grain khác, thứ tự join khác) có hơn tăng số sample
   cùng một prompt không, và hơn bao nhiêu trong ngân sách 6 giờ?
3. **Vote output, execution-based selector, learned verifier khác nhau ra sao?**
   Khi nào mỗi cái giúp, khi nào mỗi cái chỉ là vote trá hình?
4. **Tín hiệu nào bắt lỗi ngữ nghĩa khi code chạy ngon?** Code chạy ra số
   không có nghĩa là số đó đúng: sai rule, sai grain/join (fan trap), sai
   cửa sổ, đọc sai schema đều cho ra số "sạch".
5. **Khi nào sinh thêm, khi nào sửa, khi nào abstain ngay?** Và ngưỡng trên
   score tự đề xuất có nên thay bằng xác suất đúng đã calibration từ đặc
   trưng quan sát được không?

### 1.3 Kết luận trước (đọc xong mới được phép tin phần dưới)

- **Thay đổi lớn nhất được đề xuất: bỏ vai trò quyết định của score trọng số
  0,5/0,3/0,2; thay bằng (a) gate xác định đi trước, (b) vote trên pool đa
  dạng chiến lược thay vì seed-only, (c) xác suất đúng đã calibration bằng
  mô hình nhỏ trên đặc trưng quan sát được, học trên `train_cal`.**
- **Thay đổi thứ hai: bỏ k = 3 cố định; thay bằng adaptive 1 → 3 → 3+1 revision,
  trong đó revision chỉ dùng khi lỗi cụ thể (lỗi thực thi, output rỗng, gate
  fail có thông điệp sửa được), còn disagreement không có lỗi cụ thể thì
  không sinh thêm mù mà đi thẳng tới verifier/abstain.**
- **Thay đổi thứ ba: ngân sách phải tính với hệ số song song η < 2 (đề xuất
  lập kế hoạch với η = 1,5 và kiểm tra trần an toàn η = 1), không dùng 24
  giây/candidate của mô hình G = 2 hoàn hảo làm số duy nhất.**

---

## 2. Nguồn đã đọc thực sự (URL + mức đọc + dùng vào đâu)

Mức đọc được ghi đúng, không phóng đại: `PAPER` = đã đọc abstract + các
section chính qua bản HTML; `ABSTRACT+SNIPPET` = chỉ đọc abstract và đoạn
trích tìm kiếm, chưa đọc toàn văn; `README` = chỉ đọc README, chưa đọc code.

| # | Nguồn | URL | Mức đọc | Dùng vào |
|---|-------|-----|---------|----------|
| S1 | Wang et al., "Self-Consistency Improves Chain of Thought Reasoning in Language Models", ICLR 2023 | https://arxiv.org/abs/2203.11171 | ABSTRACT+SNIPPET (abstract + tóm tắt; chưa đọc toàn văn) | Gốc của vote trên nhiều reasoning path; giả định "lỗi phân tán, đáp án đúng hội tụ" |
| S2 | Li et al., "Making Large Language Models Better Reasoners with Step-Aware Verifier" (DiVeRSe), arXiv:2206.02336 | https://arxiv.org/pdf/2206.02336 | ABSTRACT+SNIPPET | Đa dạng prompt + verifier có trọng số thay cho vote đếm đầu người; quy mô 5 prompt × 20 path = 100 path là bằng chứng về chi phí, không phải mục tiêu copy |
| S3 | Ni et al., "LEVER: Learning to Verify Language-to-Code Generation with Execution", ICML 2023 | https://ar5iv.labs.arxiv.org/html/2302.08468 | PAPER (§1–§2 + abstract đã đọc; §3 trở đi chỉ lướt) | Verifier học được trên (NL, program, execution result); rerank = P_LM × P_verifier, rồi marginalize theo execution result |
| S4 | Chen et al., "CodeT: Code Generation with Generated Tests", arXiv:2207.10397 | https://arxiv.org/pdf/2207.10397 | ABSTRACT+SNIPPET | Dual execution agreement: nhóm solution theo tập test cùng pass; score \|Sx\| × √\|Sy\|; giả định "incorrect solutions are diverse" |
| S5 | Shi et al., "Natural Language to Code Translation with Execution" (MBR-EXEC), EMNLP 2022 | https://arxiv.org/pdf/2204.11454 | ABSTRACT+SNIPPET | MBR trên execution result: chọn program có agreement cao nhất với các program khác sau khi thực thi, không so văn bản |
| S6 | Estornell & Liu qua "Minority Sentinel" (arXiv:2606.29270) — phân tích "Tyranny of the Majority" | https://arxiv.org/html/2606.29270 | ABSTRACT+SNIPPET (chỉ phần §2.2 trích dẫn Estornell & Liu; chưa đọc bản gốc Estornell & Liu) | Bằng chứng ngược: khi lỗi tương quan, majority vote khóa chặt đáp án sai; Condorcet chỉ đúng khi voter độc lập |
| S7 | "Self-Consistency Falls Short! … Positional Bias on Long-Context Problems" (arXiv:2411.01101) | https://arxiv.org/html/2411.01101v3 | ABSTRACT+SNIPPET | Bằng chứng ngược: bias vị trí làm lỗi tương quan qua mọi sample; SC giảm 20–25% trong thí nghiệm retrieval của họ (số tác giả báo cáo, chưa tự kiểm chứng) |
| S8 | "Context Bagging" (CoBag) — diversity ở tầng context thay vì decoding | https://lemma-public-asset.analemma.ai/online/fars/live/live_live_20260213/idea_f79ac17b-216a-441f-96fb-af5bdae0ed99/main.pdf | ABSTRACT+SNIPPET | Khi context chứa distractor gây bias, đổi context (subset + thứ tự) mới decorrelate được lỗi; SC trên cùng context thất bại |
| S9 | "LLMs as a Jury: Cross-Model Consensus…" (arXiv:2607.10139) | https://arxiv.org/html/2607.10139 | ABSTRACT+SNIPPET | Cross-model panel decorrelate lỗi tốt hơn resample một model; nhưng DataMate chỉ có một model chính trong ngân sách 15B — ý này chỉ dùng để hiểu nguyên lý, không phải đề xuất dùng nhiều model lớn |
| S10 | "Test-Time Augmentation for LLMs: Where to Inject Diversity" (arXiv:2608.09351) | https://arxiv.org/html/2608.09351v2 | ABSTRACT+SNIPPET | Paraphrase giữ nghĩa cho gain lớn nhất (+1,80 pp so với 1 call, tác giả báo cáo); nhiễu ký tự làm disagreement cao hơn (37,8% vs 27,4%) nhưng gain thấp hơn → **chất lượng disagreement quan trọng hơn lượng disagreement** |
| S11 | "Uncertainty-Aware Budget Allocation for Adaptive Test-Time Reasoning" (UAB, arXiv:2605.26849) | https://arxiv.org/pdf/2605.26849 | ABSTRACT+SNIPPET (§ Threshold Exits) | Bằng chứng ngược quan trọng cho adaptive: threshold-exit tốt nhất **không tăng accuracy** (hard-exit −1,0%; easy-exit tiết kiệm ~20% budget với giá −1,2%) — adaptive là công cụ tiết kiệm compute, không phải công cụ tăng accuracy |
| S12 | Kadavath et al., "Language Models (Mostly) Know What They Know" (arXiv:2207.05221) | https://explore.openaire.eu/search/publication?articleId=doi_dedup___::4f950b49e90b16ecddc6b98bc8c20f6c | ABSTRACT+SNIPPET | P(True) self-evaluation có calibration khá trên model lớn, nhưng kém trên task mới; self-judge của cùng model không phải verifier độc lập |
| S13 | sqlsure — semantic inspector cho SQL (FANOUT/CHASM/ADDITIVITY/JOIN_KEY) | https://github.com/sqlsure/sqlsure | README (chưa đọc code, chưa chạy rule test) | Mẫu cho gate xác định bắt fan trap trước khi thực thi; các claim "2.568 gold query, 45 flag, 0 false alarm" là **tự báo cáo của repo, chưa được kiểm chứng độc lập ở đây**; licence Apache-2.0 theo README |

**Không đọc code** của CodeT, LEVER, DiVeRSe, MBR-EXEC trong đợt này (chỉ đọc
paper/abstract). Nếu parent cần, bước tiếp theo là clone và đọc file cụ thể
của các repo đó — không được ghi "đã đọc code" từ bản nháp này.

**Lưu ý thời gian:** một số nguồn trên (S6–S11) có arXiv ID thuộc 2025–2026,
sau mốc model DataMate (model public trước 01/10/2026). Chúng là **tài liệu
tham khảo về phương pháp**, không phải model/checkpoint triển khai, nên mốc
cutoff của model không áp dụng cho chúng; nhưng mọi ý tưởng lấy từ đó vẫn
phải được đo lại trên train ZAIC trước khi chốt.

---

## 3. Vì sao consensus có thể cùng sai — mô hình lỗi

### 3.1 Điều kiện để vote đúng, và điều kiện đó vỡ ở đâu

Vote đúng cần hai điều kiện (S1 + Condorcet, xem S6):

1. Mỗi candidate đúng với xác suất p đủ lớn, và
2. **Lỗi của các candidate độc lập** (hoặc ít nhất không tương quan mạnh).

Trong DataMate, điều kiện 2 vỡ theo đúng 4 cách sau — và cả 4 đều cho ra
cùng một đáp án sai, tức là vote 3/3 vẫn sai:

| Cơ chế tương quan | Ví dụ DataMate cụ thể | Vì sao seed không cứu được |
|---|---|---|
| Cùng đọc sai rule | Cả 3 candidate đều tính doanh thu sau chiết khấu nhưng quên loại đơn có dòng trả (hoặc ngược lại: loại cả đơn trong khi rule chỉ loại dòng) | Rule nằm trong prompt chung; seed chỉ đổi cách diễn đạt, không đổi cách hiểu rule |
| Cùng chọn sai grain / join | Cả 3 đều `SUM` sau JOIN 1–N (fan trap) vì cùng thấy schema đó, cùng viết join đó | Grain không nằm trong prompt một cách tường minh; model mặc định join rồi sum |
| Cùng sai cửa sổ thời gian | Cả 3 đều dùng tháng dương thay vì cửa sổ Tết (23 Chạp → 10 Giêng), hoặc dùng `lunar_year = Y` duy nhất làm mất nửa tháng Giêng | Cửa sổ nằm trong rulebook/calendar; seed không đổi phép join calendar |
| Cùng đọc sai schema | Cả 3 đều map "doanh thu" vào cùng một cột sai (cột trước chiết khấu thay vì sau chiết khấu) vì cột đó có tên gần nghĩa nhất | Schema linking sai là lỗi ở tầng hiểu schema, không phải tầng sampling |

Đây chính là "Tyranny of the Majority" mà S6 trích dẫn từ Estornell & Liu:
khi lỗi tương quan cao, tăng k không những không giúp mà còn **khóa chặt**
đáp án sai với độ tin cậy cao hơn. S7 cho cùng kết luận ở long-context:
bias vị trí làm mọi sample lệch cùng hướng, SC khuếch đại thay vì triệt
tiêu lỗi. S8 chỉ ra nguyên nhân nằm ở **context chung**, không phải ở
decoding: đổi seed mà giữ nguyên context bị bias thì lỗi vẫn tương quan.

### 3.2 Hệ quả cho DataMate: agree-but-wrong là metric bắt buộc, không phải metric phụ

Repo đã yêu cầu báo agree-but-wrong, nhưng thiết kế hiện tại vẫn dùng
consensus làm cổng chính. Thứ tự đúng phải đảo lại:

1. **Gate xác định trước** (rule, grain, join, cửa sổ, range) — vì gate này
   không chia sẻ lỗi với generator: nó đọc SQL và dữ liệu, không đọc prompt
   của generator theo cùng một cách.
2. **Đa dạng chiến lược** (mục 4) — vì chỉ đa dạng mới phá tương quan.
3. **Vote / verifier sau cùng** — và vote chỉ được tin khi pool đã đa dạng.

Một pool 3 candidate seed-only mà đồng thuận 3/3 nhưng trượt gate thì phải
abstain (hoặc revision có mục tiêu), không được "3/3 nên chắc đúng".
Ngược lại, một pool 2/3 nhưng candidate thiểu số là candidate duy nhất qua
được gate xác định (ví dụ: chỉ nó aggregate trước khi join) thì thiểu số đó
đáng được xem xét nghiêm túc, không tự động thua vote — đây là trường hợp
"minority truth" mà S6 đo được ở 25,5% các case divergent trong debate
(số của S6, chưa kiểm chứng trên DataMate; dùng để đặt giả thuyết, không
dùng làm số ZAIC).

### 3.3 Seed-only vs strategy-diverse: bằng chứng hai chiều

**Ủng hộ seed-only (khi nào nó đủ):**
- S1: khi lỗi thực sự phân tán (lỗi số học lẻ tẻ, lỗi cú pháp, lỗi chọn cột
  ngẫu nhiên), vote trên nhiều path đúng là hội tụ về đáp án đúng. Với câu
  DataMate đơn giản (một bảng, một filter, không join, không cửa sổ phức
  tạp), lỗi thuộc loại này là chính, và seed-only đủ.
- S1 dùng k lớn (40 path trong paper gốc cho toán) — nhưng DataMate không
  có ngân sách đó; k = 3 là bản rút gọn, và ở k = 3, luật số lớn chưa kịp
  phát huy. **UNVERIFIED:** chưa có số nào trong đợt này đo gain của k = 3
  so với k = 1 trên dữ liệu ZAIC.

**Chống seed-only (khi nào nó thất bại có hệ thống):**
- S6/S7/S8 (mục 3.1): lỗi tương quan → vote khóa sai.
- S2 (DiVeRSe): tăng đa dạng bằng cách **đổi prompt** (khác exemplar, khác
  cách diễn đạt), không chỉ đổi seed, rồi mới vote có trọng số bằng verifier.
  Nguyên lý chuyển giao được, quy mô 100 path thì không.
- S10 (TTA): ở cùng số lượng call, **nơi inject diversity quan trọng hơn
  lượng diversity**. Paraphrase giữ nghĩa > nhiễu ký tự dù nhiễu tạo
  disagreement nhiều hơn. Chuyển sang DataMate: đổi plan (SQL vs Python,
  aggregate-trước-join vs join-trước-aggregate, cửa sổ tính bằng calendar
  join vs tính bằng Python) là "paraphrase giữ nghĩa" ở tầng chiến lược;
  đổi seed/temperature là "nhiễu" ở tầng decoding.
- S9: panel cross-model decorrelate tốt hơn resample một model — nhưng
  DataMate không có ngân sách cho panel model lớn; bài học rút ra là:
  **decorrelation phải đến từ thứ gì đó ngoài generator chính**, ví dụ
  deterministic gate, second path bằng engine khác, hoặc verifier không
  phải LLM judge của cùng model.

**Kết luận trung gian:** seed-only là baseline rẻ, không phải thiết kế cuối.
Pool nên có tối thiểu 2 chiến lược thực sự khác nhau trước khi nói tới vote.

---

## 4. Ba cơ chế chọn đáp án — khác nhau ở đâu, khi nào dùng cái nào

### 4.1 Vote trên output (hiện tại của repo; MBR-EXEC là dạng tổng quát của nó)

- **Cơ chế:** thực thi mọi candidate, nhóm theo output đã chuẩn hóa, chọn
  nhóm đông nhất (S1, S5). MBR-EXEC (S5) là cùng ý tưởng nhưng chặt hơn:
  chọn program có agreement cao nhất với các program khác **sau khi thực
  thi**, vì hai program khác văn bản có thể cùng ngữ nghĩa.
- **Khi giúp:** lỗi phân tán, và output đúng là "điểm hội tụ" duy nhất.
- **Khi hại:** lỗi tương quan (mục 3.1); và khi output đúng không phải là
  output phổ biến nhất vì generator bị bias (ví dụ: model luôn thích dùng
  cột A, cột A sai, nên output từ cột A chiếm đa số).
- **Chi phí:** rẻ nhất (chỉ cần thực thi, không cần model phụ). Đây là lý
  do nó vẫn giữ vai trò **tầng 1**, không phải tầng cuối.

### 4.2 Execution-based selector (CodeT-style; mạnh hơn vote ở một điểm duy nhất)

- **Cơ chế (S4):** ngoài solution, sinh thêm **test case** (ở DataMate:
  test case = một truy vấn kiểm chứng nhỏ, hoặc một bộ khẳng định từ
  rulebook/profiler, ví dụ "tổng doanh thu tháng này không vượt tổng doanh
  thu toàn dữ liệu", "số dòng sau filter ≤ số dòng gốc"). Nhóm solution theo
  **tập test cùng pass**, score `|Sx| × √|Sy|` (số solution trong nhóm × căn
  số test cùng pass). Một solution đúng phải pass nhiều test **và** có nhiều
  solution khác cùng pass đúng tập đó.
- **Khi giúp hơn vote thuần:** khi có test đủ khó để phân biệt hai output
  đều "chạy được". Vote thuần chỉ biết hai output khác nhau; CodeT-style
  biết output nào pass được nhiều kiểm chứng độc lập hơn.
- **Khi hại / giới hạn:**
  - Test do cùng model sinh ra thì test cũng chia sẻ bias với solution
    (S4 tự thừa nhận giả định "incorrect solutions are diverse" — giả định
    này **vỡ đúng ở các lỗi tương quan mục 3.1**).
  - Ở DataMate, test "đúng" nhất là các assertion từ rulebook và profiler —
    tức là deterministic gate, không phải test do LLM sinh. Vì vậy bản
    chuyển giao thực tế của CodeT sang DataMate là: **dùng rule assertion +
    profiler check làm "test set", không dùng LLM-generated test làm chính**.
  - Chi phí: mỗi test là một lần thực thi DuckDB (rẻ), không phải một lần
    sinh LLM — nên CodeT-style ở DataMate rẻ hơn nhiều so với CodeT gốc.

### 4.3 Learned verifier (LEVER-style; DiVeRSe voting verifier)

- **Cơ chế (S3):** huấn luyện một verifier `P(v | NL, program, execution
  result)` trên các program đã sample từ chính generator, nhãn đúng/sai =
  execution result có khớp gold không. Rerank score =
  `P_LM(program) × P_verifier(đúng)`, rồi **marginalize** (cộng dồn) theo
  execution result giống nhau. DiVeRSe (S2) làm tương tự nhưng verifier
  chấm từng step, rồi vote có trọng số.
- **Khi giúp hơn vote:** verifier học được **đặc trưng ngữ nghĩa của
  execution result** (kiểu dữ liệu, khoảng giá trị, thuộc tính biến — S3
  nhấn mạnh điểm này) mà vote đếm đầu người không thấy. Ví dụ: một output
  là số âm cho "doanh thu" hoặc một bảng có số dòng vượt tổng số dòng gốc
  sẽ bị verifier đánh thấp dù nó chiếm đa số.
- **Khi hại / giới hạn:**
  - Verifier cần dữ liệu huấn luyện có nhãn — ở DataMate, nhãn chỉ có trên
    train (train_cal/train_holdout), không có trên private test. Verifier
    huấn luyện trên train_cal có nguy cơ **không transfer qua business khác**
    (leave-one-business-type-out là phép thử bắt buộc, xem mục 7).
  - Verifier là một model khác (S3 dùng T5/RoBERTa) — nếu dùng chính LLM
    7B làm judge thì đó **không phải verifier độc lập** (S12: self-evaluation
    của cùng model có calibration khá nhưng không độc lập; và judge cùng
    model chia sẻ blind spot với generator).
  - **Đề xuất thực tế cho DataMate (rẻ và độc lập nhất):** verifier = mô
    hình nhỏ **không phải LLM** (logistic regression / gradient boosting
    nhỏ) trên đặc trưng quan sát được (mục 6). Nó không sinh text, không
    chia sẻ prompt với generator, và tham số của nó không đáng kể so với
    trần 15B. Nếu dùng LLM judge, phải đo riêng contribution của nó và coi
    nó là một candidate nữa, không phải trọng tài.

### 4.4 Bảng đối chiếu nhanh

| Cơ chế | Tín hiệu dùng | Độc lập với generator? | Bắt được lỗi ngữ nghĩa? | Chi phí chính | Vai trò đề xuất |
|---|---|---|---|---|---|
| Vote output (S1/S5) | Tần suất output | Không (cùng model, cùng prompt) | Không | Thực thi (rẻ) | Tầng 1, khi pool đã đa dạng |
| CodeT-style selector (S4) | Tập test cùng pass | Một phần (test xác định thì độc lập; test do LLM sinh thì không) | Có, nếu test đủ khó | Thực thi (rẻ) | Tầng 2, với test = rule assertion + profiler |
| Learned verifier (S3/S2) | (NL, program, execution result) → P(đúng) | Có, nếu verifier không phải cùng LLM judge | Có, nếu feature đủ tốt | Huấn luyện trên train_cal (một lần) + inference rẻ (nếu là mô hình nhỏ) | Tầng cuối cho câu khó; thay score trọng số |
| Deterministic gate (sqlsure-style, S13) | SQL text + FK/grain/rulebook | Có hoàn toàn | Có, đúng loại lỗi fan trap/join | Parse SQL (rất rẻ) | **Đi trước mọi vote**; fail = abstain/revision, không vote |

---

## 5. Tín hiệu bắt lỗi ngữ nghĩa khi code chạy ngon

Mỗi tín hiệu dưới đây phải là **một check có thể chạy được**, không phải
một lời khuyên "hãy cẩn thận". Cột "chi phí" chỉ tính trong Docker offline.

| # | Lỗi ngữ nghĩa | Tín hiệu phát hiện | Cách triển khai rẻ nhất | Nếu tín hiệu này fail thì làm gì |
|---|---|---|---|---|
| E1 | Fan trap: SUM sau JOIN 1–N | Parse SQL: có JOIN 1–N (theo FK) rồi SUM/COUNT ở SELECT mà không aggregate trước join | Gate xác định kiểu sqlsure (S13): FANOUT/CHASM; hoặc tự viết parser bằng sqlglot trên join graph + FK từ schema | Revision bắt buộc: viết lại dạng aggregate-trước-join; nếu revision vẫn fan trap → abstain, không vote |
| E2 | Sai grain | GROUP BY keys ≠ grouping mà câu hỏi yêu cầu (ví dụ: hỏi theo tháng mà group theo ngày, hoặc không group mà hỏi "mỗi") | So sánh GROUP BY với danh sách grouping trích từ câu hỏi (rule-based, không LLM); kiểm tra số dòng output có khớp số nhóm kỳ vọng không | Revision với grain đã sửa; nếu không xác định được grain → abstain |
| E3 | Sai cửa sổ thời gian / as-of | WHERE date không khớp cửa sổ rulebook (as-of, tháng hiện tại tính tới as-of, cửa sổ Tết = OR hai nửa) | Assertion từ rulebook: cửa sổ kỳ vọng tính từ calendar.csv, so sánh với khoảng date thực tế mà query quét (min/max date trong filter hoặc trong dữ liệu sau filter) | Revision với cửa sổ đã sửa; nếu cửa sổ mơ hồ (ví dụ: ngữ nghĩa lunar_year chưa xác minh — xem P5) → abstain |
| E4 | Sai định nghĩa doanh thu | SQL thiếu một trong các điều kiện loại trừ: VAT, phí vận chuyển, đơn hủy, đơn/dòng trả — theo đúng rulebook của split | Checklist từ rulebook: mỗi điều kiện là một predicate phải xuất hiện (hoặc được chứng minh là không cần vì dữ liệu không có trường đó); **UNVERIFIED:** cách hiểu "loại đơn có hàng trả" ở mức đơn hay mức dòng vẫn là câu hỏi mở cho P3/P5, phải đối chiếu rulebook thật trước khi hard-code | Revision bổ sung điều kiện; nếu rulebook không nói rõ → abstain thay vì đoán |
| E5 | Sai schema linking | Cột được dùng không phải cột mà profiler/rulebook gợi ý cho khái niệm đó; hoặc cột có tên gần nghĩa nhưng kiểu/đơn vị khác | So sánh cột dùng với cột gợi ý từ profiler (kiểu, đơn vị, phân phối); kiểm tra foreign key có tồn tại không | Exploration lại schema (không sinh thêm candidate mù); nếu vẫn không khớp → abstain |
| E6 | Output ngoài khoảng hợp lý | Output vượt giới hạn vật lý từ profiler: SUM > tổng toàn dữ liệu, COUNT > số dòng gốc, percent ngoài [−100, 100] (hoặc ngoài khoảng rulebook cho phép), date ngoài khoảng dữ liệu | Range check từ profiler (tính một lần trên dữ liệu, không cần LLM) | Abstain ngay nếu vi phạm cứng (ví dụ: SUM > tổng); revision nếu vi phạm mềm có thể do filter sai |
| E7 | Second path bất đồng | Cùng một câu, tính bằng SQL và bằng Python/pandas với logic viết độc lập, cho hai output khác nhau | Second path thật sự độc lập: khác engine, khác người viết logic (prompt khác, hoặc code template khác), không phải chạy lại cùng SQL | Không vote mù: đi tới Tier 3 (mục 6.3) — xem xét từng path bằng gate E1–E6, path nào qua nhiều gate hơn thì thắng; nếu cả hai đều trượt gate → abstain |
| E8 | Output rỗng nhưng dữ liệu không rỗng | Query trả về 0 dòng trong khi profiler cho thấy có dữ liệu trong khoảng đó | Đếm dòng sau filter vs đếm dòng trong khoảng tương đương không filter | Revision filter (thường là sai điều kiện join hoặc sai format ngày); nếu filter đã đúng mà dữ liệu thật sự rỗng → xem P5 (0/danh sách rỗng có thể là đáp án đúng) |
| E9 | Output nhạy với thứ tự / paraphrase | Paraphrase câu hỏi (giữ nghĩa) hoặc đổi thứ tự bảng trong prompt làm output đổi | Chỉ dùng làm tín hiệu yếu, vì tốn thêm call LLM; theo S10, paraphrase giữ nghĩa là diversity tốt, nhưng ở DataMate nó đắt — chỉ dùng ở Tier 3 cho câu đã disagreement | Nếu paraphrase đổi output → abstain (không tin output gốc); nếu giữ nguyên → tăng tin cậy một bậc, không tăng thành "chắc chắn" |

**Nguyên tắc chung:** E1–E6 là deterministic, rẻ, và độc lập với generator —
chúng phải chạy **trước** vote. E7 là cầu nối sang verifier. E9 là đắt nhất
và yếu nhất, chỉ dùng cuối cùng.

---

## 6. Thiết kế adaptive compute đề xuất (thay k = 3 cố định)

### 6.1 Nguyên tắc: compute chỉ được thêm khi nó có thể thay đổi quyết định

S11 là bằng chứng ngược quan trọng: early exit theo ngưỡng **không tăng
accuracy** (tiết kiệm ~20% budget với giá −1,2% accuracy ở cấu hình tốt
nhất). Vì vậy adaptive ở đây được bán đúng giá trị của nó: **tiết kiệm
compute để dồn cho câu khó, không phải tăng accuracy trên câu dễ**.
Accuracy tăng (nếu có) phải đến từ diversity + gate + verifier, không đến
từ việc "exit sớm".

### 6.2 Các tier

```
Tier 0 — Deterministic pre-check (0 LLM call, mọi câu):
  schema linking + rulebook checklist + profiler range.
  Nếu thiếu dữ liệu/rule sau fallback đầy đủ → unanswerable (thuộc P5,
  không quyết ở đây). Nếu không → Tier 1.

Tier 1 — Một lượt duy nhất (1 candidate, greedy, temp 0):
  Sinh 1 SQL (hoặc 1 Python nếu câu đó hợp Python hơn), thực thi, chạy
  gate E1–E6.
  → ĐIỀU KIỆN ANSWER NGAY (tất cả phải đúng):
     * gate E1–E6 pass,
     * output không rỗng một cách bất thường (hoặc rỗng nhưng đã qua E8),
     * câu thuộc loại "thấp rủi ro": không JOIN + SUM, không cửa sổ phức
       tạp, không percent, không nhiều bảng.
  → Nếu bất kỳ điều kiện nào fail → Tier 2. Không abstain ở Tier 1 trừ
     khi gate fail cứng và không có hướng sửa (ví dụ: fan trap không thể
     viết lại vì thiếu FK — khi đó abstain ngay, đừng sinh thêm).

Tier 2 — Pool đa dạng chiến lược (tổng cộng 3 candidate, KHÔNG phải 3 seed):
  Candidate 2: chiến lược khác Tier 1 (ví dụ: Tier 1 là SQL thì candidate 2
    là Python/pandas với logic viết độc lập; hoặc SQL với grain/plan khác).
  Candidate 3: chiến lược thứ ba (ví dụ: SQL nhưng bắt đầu từ bảng khác,
    hoặc đổi thứ tự: filter trước, aggregate sau, theo plan đã nêu rõ).
  Thực thi cả 3, chạy gate E1–E6 cho từng candidate, rồi chọn bằng:
     (a) loại bỏ mọi candidate trượt gate cứng,
     (b) trong số còn lại, vote trên output (MBR-EXEC-style),
     (c) nếu còn disagreement → verifier nhỏ (mục 6.4) chấm từng output,
         chọn output có P(đúng) đã calibration cao nhất, chỉ answer khi
         P(đúng) > ngưỡng đã khóa (mục 6.4).
  → Nếu sau Tier 2 vẫn: không candidate nào qua gate, hoặc verifier
     P(đúng) cao nhất vẫn < ngưỡng → Tier 3.

Tier 3 — Revision có mục tiêu (tối đa 1 revision, KHÔNG resample mù):
  Chỉ revision khi có **thông điệp lỗi cụ thể**: lỗi thực thi, output rỗng
  bất thường, gate fail có tên (ví dụ: FANOUT, cửa sổ sai, cột sai).
  Revision prompt = candidate tốt nhất + thông điệp lỗi + bằng chứng
  (profiler/rule) — không phải "hãy thử lại".
  Revision xong: chạy lại gate E1–E6 + verifier. Nếu pass và P(đúng) >
  ngưỡng → answer. Nếu không → abstain.
  → KHÔNG revision khi: disagreement thuần túy không có lỗi cụ thể
     (sinh thêm candidate giống nhau chỉ tốn compute mà không phá tương
     quan), hoặc khi đã có 2 candidate trượt cùng một gate cứng (lỗi hệ
     thống, không phải lỗi lẻ).
```

### 6.3 Bảng quyết định: sinh thêm / sửa / abstain ngay

| Tình huống sau Tier 1/2 | Hành động | Vì sao (không phải "cứ thử thêm") |
|---|---|---|
| Lỗi thực thi (cú pháp, cột không tồn tại, kiểu không khớp) | **Sửa** 1 lần với thông điệp lỗi | Lỗi có địa chỉ sửa rõ ràng; resample mù có thể lặp lại lỗi |
| Output rỗng bất thường (E8) | **Sửa** filter/join | Lỗi có thể định vị (filter nào làm rỗng) |
| Gate fail có tên (fan trap, cửa sổ, grain) | **Sửa** theo đúng gate đó | Gate cho biết phải sửa cái gì; sinh thêm không sửa gate |
| Disagreement giữa các chiến lược, không gate fail | **Verifier** chấm, không sinh thêm | Thêm candidate cùng chiến lược không phá tương quan; cần tín hiệu ngoài vote |
| Tất cả candidate trượt cùng gate cứng | **Abstain ngay** | Lỗi hệ thống (thiếu FK, thiếu rule, schema không đủ); thêm compute không tạo dữ liệu mới |
| Verifier P(đúng) cao nhất < ngưỡng khóa | **Abstain ngay** | Kỳ vọng PA của việc answer là âm (p < 0,5 → 2p−1 < 0); sinh thêm chỉ đổi p một cách nhiễu |
| Candidate thiểu số là duy nhất qua gate | **Xem xét thiểu số trước**, không vote mù | Minority truth (S6): gate độc lập đáng tin hơn đa số tương quan |
| Câu thấp rủi ro + Tier 1 pass toàn bộ | **Answer ngay, không Tier 2** | Thêm compute không đổi quyết định; dồn budget cho câu khó |

### 6.4 Thay score trọng số bằng xác suất đúng đã calibration

**Vấn đề của score hiện tại:** `0,5/0,3/0,2` là một số trong [0, 1], nhưng
không phải xác suất. Score 0,83 (ví dụ: consensus 2/3 → 0,333 + second path
đồng ý → 0,3 + evidence 1,0 → 0,2) **không có nghĩa** "83% đúng". Không có
cách nào từ score đó suy ra kỳ vọng PA, và ngưỡng trên score đó không có
ngữ nghĩa xác suất — nó chỉ là một thứ tự sắp xếp tùy ý.

**Đề xuất thay thế (học trên train_cal, khóa, đo trên train_holdout):**

1. **Đặc trưng quan sát được (không dùng gold, không dùng output của
   chính verifier):**
   - consensus_fraction (trong pool sau khi loại candidate trượt gate cứng),
   - số output phân biệt / tổng số candidate thành công,
   - second_path_agrees (0/1, với second path độc lập thật sự),
   - evidence_coverage (từ profiler),
   - số gate E1–E6 pass / fail (mỗi gate là một feature riêng, không gộp),
   - loại câu (one-hot, nhưng chỉ dùng khi type có ≥ 30 mẫu trên train_cal,
     còn không thì fallback global — giữ quy tắc min_support của repo),
   - độ khó quan sát được: số bảng, có JOIN + SUM không, có cửa sổ thời
     gian không, độ dài SQL.
2. **Mô hình:** logistic regression (hoặc gradient boosting nhỏ nếu đủ
   mẫu) dự đoán P(đúng | features). Đây là mô hình nhỏ, không phải LLM,
   không chia sẻ prompt với generator, tham số không đáng kể so với trần
   15B. **UNVERIFIED:** chưa đo xem logistic có đủ capacity cho task này
   không; nếu train_cal quá nhỏ, fallback về "consensus_fraction theo type"
   như repo đã đề xuất.
3. **Calibration:** sau khi fit, kiểm tra reliability diagram và ECE trên
   train_cal (cross-validation theo business, không phải random split —
   vì private test có thể chứa business khác). Nếu ECE cao, áp Platt
   scaling hoặc isotonic (chỉ khi đủ mẫu; isotonic với mẫu nhỏ sẽ overfit).
4. **Ngưỡng quyết định từ PA, không từ cảm giác:** với PA (+1 đúng, 0
   abstain, −1 sai), answer có kỳ vọng dương khi và chỉ khi
   `P(đúng) > 0,5` (vì E[PA] = p×(+1) + (1−p)×(−1) = 2p − 1). Ngưỡng vận
   hành = 0,5 **chỉ khi** P(đúng) đã calibration đúng. Nếu calibration trên
   holdout cho thấy P(đúng) bị lệch (ví dụ: nhóm P≈0,6 chỉ đúng 45% thật),
   ngưỡng phải dịch theo đường reliability đã đo, và phải báo rõ độ lệch
   đó — không được giữ ngưỡng 0,5 một cách mù.
5. **Báo cáo bắt buộc trên holdout:** PA, coverage, selective accuracy,
   ECE, agree-but-wrong rate, và PA theo từng business (leave-one-out).
   Nếu verifier không cải thiện PA so với "consensus_fraction theo type"
   thì **giữ bản đơn giản** — repo đã nêu nguyên tắc này và bản nháp này
   giữ nguyên nó.

**Phân biệt heuristic score vs xác suất đã calibration (ghi rõ trong
tài liệu triển khai):**

| | Heuristic score (hiện tại) | P(đúng) đã calibration (đề xuất) |
|---|---|---|
| Score 0,8 có nghĩa là gì? | Không có nghĩa xác suất; chỉ là thứ tự | Trong nhóm các câu có P≈0,8, khoảng 80% đúng (nếu calibration tốt) |
| Ngưỡng 0,5 có nghĩa là gì? | Tùy ý | Điểm hòa vốn kỳ vọng PA (khi calibration đúng) |
| Khi nào tin được? | Không kiểm chứng được | Khi ECE thấp trên holdout tách theo business |
| Khi nào không tin được? | Luôn luôn, vì chưa từng đo | Khi ECE cao, hoặc khi holdout là business mới mà verifier chưa thấy |

---

## 7. Ngân sách: không giả định 2 GPU = throughput gấp đôi

### 7.1 Vì sao không được dùng G = 2 như số nhân hoàn hảo

- **Model load:** 2 replica phải load 2 lần (song song trên 2 GPU thì wall
  time ≈ 1 lần load, nhưng vẫn là thời gian chết không sinh candidate nào;
  load tuần tự thì gấp đôi). Thời gian load là **UNVERIFIED** ở đây — phải
  đo một lần trên máy thật, không điền số mù.
- **Continuous batching:** vLLM batch nhiều request cùng lúc làm throughput
  mỗi candidate tốt hơn mô hình tuần tự, nhưng batching chỉ hiệu quả khi
  các request **độc lập và cùng sẵn sàng**. Adaptive (Tier 2 chỉ chạy khi
  Tier 1 fail, Tier 3 chỉ chạy khi Tier 2 disagreement) tạo **phụ thuộc
  tuần tự**: candidate sau không thể batch cùng candidate trước. Vì vậy
  throughput thực tế nằm giữa mô hình tuần tự và mô hình song song hoàn
  hảo — và adaptive càng mạnh thì càng gần mô hình tuần tự.
- **Bottleneck không phải GPU:** tiền xử lý Excel, DuckDB execution,
  profiler, parse SQL đều chạy trên CPU và có thể thành bottleneck chung
  cho cả 2 replica.
- **Tensor parallel vs 2 replica:** nếu dùng cả 2 GPU cho 1 replica (tensor
  parallel), mỗi token nhanh hơn nhưng không có 2 luồng độc lập; nếu dùng
  2 replica độc lập, throughput tối đa gấp đôi **chỉ khi cả hai đều bão
  hòa**. Hai cấu hình này không tương đương và phải chọn một, đo một.

### 7.2 Công thức với hệ số song song hiệu dụng η

Định nghĩa η = hệ số tăng throughput thực tế của 2 GPU so với 1 GPU,
với 1 < η ≤ 2. **Đề xuất lập kế hoạch với η = 1,5 và kiểm tra trần an
toàn với η = 1.** Mọi số dưới đây dùng N = 600 (giả định của user, chưa
xác minh kích thước private test) và chưa cộng thời gian load model.

```
T_wall = (N × k_avg × t_gen) / η  +  N × t_exec  +  T_load
t_break-even = (T_budget − T_load − N × t_exec) × η / (N × k_avg)
```

Với T_budget = 21.600 giây (6 giờ), bỏ qua T_load và t_exec để thấy trần
thuần cho sinh candidate (hai số này phải đo rồi trừ ra sau):

| η (hệ số song song hiệu dụng) | t_gen = 5s | t_gen = 10s | t_gen = 20s |
|---|---|---|---|
| η = 1 (tuần tự hoàn toàn, trần an toàn) | 600×3×5 = 9.000s = 2,50h | 18.000s = 5,00h | 36.000s = 10,00h ✗ |
| η = 1,5 (lập kế hoạch) | 6.000s = 1,67h | 12.000s = 3,33h | 24.000s = 6,67h ✗ |
| η = 2 (song song hoàn hảo — số của repo cũ) | 4.500s = 1,25h | 9.000s = 2,50h | 18.000s = 5,00h |

Điểm hòa vốn cho k = 3 cố định: η = 1 → 12s/candidate; η = 1,5 → 18s;
η = 2 → 24s (số 24s của repo chỉ đúng ở η = 2).

### 7.3 Ngân sách của thiết kế adaptive (giả định phân bố, phải đo lại)

Giả định phân bố tier **chưa đo, chỉ để tính minh họa** (thay bằng số
holdout thật trước khi chốt):

| Tier | Tỉ lệ câu (giả định) | Candidate / câu | Đóng góp vào k_avg |
|---|---|---|---|
| Tier 1 answer ngay | 50% | 1 | 0,50 |
| Tier 2 (pool 3) | 30% | 3 | 0,90 |
| Tier 3 (pool 3 + 1 revision) | 15% | 4 | 0,60 |
| Abstain sau Tier 2 (không revision) | 5% | 3 | 0,15 |
| **Tổng** | 100% | — | **k_avg = 2,15** (so với 3,00 cố định, tiết kiệm ~28%) |

Với t_gen = 10s, N = 600:
- k = 3 cố định, η = 1,5: 600 × 3 × 10 / 1,5 = 12.000s = 3,33h.
- Adaptive k_avg = 2,15, η = 1,5: 600 × 2,15 × 10 / 1,5 = 8.600s = 2,39h.
- Adaptive k_avg = 2,15, η = 1 (trần an toàn): 12.900s = 3,58h — vẫn trong
  6 giờ, còn dư cho execution + load. Đây là kiểm tra quan trọng nhất:
  **thiết kế adaptive phải vừa ngân sách ngay cả ở η = 1**, vì adaptive
  tạo phụ thuộc tuần tự làm η thực tế thấp hơn 2.

Nhạy cảm với N: nếu N = 1.000 thay vì 600 (UNVERIFIED — private test có
thể lớn hơn giả định), mọi số trên nhân với 1,67: adaptive ở η = 1,5,
t_gen = 10s → 14.333s = 3,98h (vẫn vừa); k = 3 cố định ở η = 1 → 30.000s =
8,33h (vượt). **Vì vậy không được chốt k cố định trước khi biết N thật
hoặc ít nhất có trần N từ BTC.**

### 7.4 Những gì phải đo trước khi chốt ngân sách (không đo thì không chốt)

1. t_gen thực tế của Qwen2.5-Coder-7B trên 1× RTX 5090 (hoặc máy tương
   đương) với prompt DataMate thật, ở độ dài output thật — không dùng số
   từ paper khác.
2. T_load của 1 replica và 2 replica (song song vs tuần tự).
3. η thực tế: chạy cùng một batch câu ở 1 replica và 2 replica, đo tỉ lệ
   throughput — không giả định.
4. t_exec thực tế của DuckDB trên business lớn nhất (không phải business
   trung bình).
5. Phân bố tier thật trên train_holdout (bao nhiêu % câu dừng ở Tier 1).

---

## 8. Phép thử nhỏ nhất phân biệt các phương án (trên cùng train_holdout)

**Nguyên tắc:** cùng generator, cùng holdout tách theo business, cùng
ngân sách đo bằng giây/câu — chỉ đổi một thành phần mỗi lần. Không so
sánh hai phương án chạy trên hai holdout khác nhau.

### 8.1 Các arm (chạy theo thứ tự, dừng khi một arm đã thắng rõ)

| Arm | Mô tả | Câu hỏi nó trả lời |
|---|---|---|
| A0 | 1 candidate greedy + gate E1–E6 + ngưỡng p > 0,5 (không consensus) | Baseline thật sự là bao nhiêu? (Mọi arm khác phải hơn A0 về PA, không chỉ hơn nhau) |
| A1 | k = 3 seed-only + vote (thiết kế repo hiện tại, nhưng gate đi trước) | Seed-only cho bao nhiêu so với A0? |
| A2 | k = 3 strategy-diverse (SQL + Python + SQL-plan-khác) + vote | Diversity chiến lược có hơn seed-only không, và hơn bao nhiêu PA? |
| A3 | A2 + CodeT-style selector (test = rule assertion + profiler check) | Test xác định có chọn tốt hơn vote thuần không? |
| A4 | A2 + verifier logistic trên features mục 6.4 (học trên train_cal) | Verifier học được có hơn vote không, hay chỉ hơn trên train_cal mà fail trên business mới? |
| A5 | Adaptive Tier 1→2→3 (mục 6.2) với verifier A4 | Adaptive có giữ được PA của A4 với k_avg thấp hơn không? |

### 8.2 Metric bắt buộc (không chỉ PA tổng)

- **PA** (chính), **coverage**, **selective accuracy** (accuracy trên câu
  đã trả lời), **wrong-answer rate**.
- **Agree-but-wrong rate:** trong số câu đã trả lời, tỉ lệ câu mà mọi
  candidate đồng thuận nhưng đáp án sai. Đây là metric trực tiếp đo lỗi
  tương quan; arm nào giảm được nó mới thực sự phá tương quan.
- **Oracle rate:** tỉ lệ câu mà ít nhất một candidate đúng (đo generation)
  so với PA của arm (đo selection). Nếu oracle cao mà PA thấp → lỗi ở
  selection, không phải generation; đừng tăng k, hãy sửa selector.
- **PA theo business** (leave-one-business-type-out) và **PA theo loại câu**
  — để phát hiện verifier chỉ học được business đã thấy.
- **Giây/câu** (sinh + thực thi + gate + verifier) và **k_avg thực tế** —
  để kiểm tra ngân sách mục 7, không chỉ accuracy.
- **ECE + reliability diagram** của verifier A4 trên holdout (không chỉ
  trên train_cal).

### 8.3 Tiêu chí dừng / chọn (viết trước khi chạy, không chọn sau khi thấy số)

- Chọn arm có **PA cao nhất trên holdout**, với điều kiện giây/câu vừa
  ngân sách ở η = 1 (trần an toàn).
- Nếu A4 không hơn A2 quá 0,02 PA trên holdout (ngưỡng thực dụng, không
  phải ngưỡng thống kê), **giữ A2** — verifier phức tạp không đáng.
- Nếu A5 giữ PA của A4 (chênh ≤ 0,01) với k_avg ≤ 2,5 thì **chọn A5** làm
  thiết kế cuối; nếu không, giữ A4 với k cố định nhưng phải chứng minh
  ngân sách ở η = 1.
- Nếu agree-but-wrong rate của A1 > 30% số câu đã trả lời (ngưỡng cảnh
  báo, không phải kết luận), coi seed-only là **không đủ** và bắt buộc
  A2 trở lên — không được chốt A1 chỉ vì nó rẻ.

---

## 9. Những gì thay đổi so với thiết kế 8d4721e (tóm tắt cho parent)

1. **Score 0,5/0,3/0,2 không còn là cổng quyết định.** Nó là heuristic
   chưa calibration; thay bằng gate xác định + P(đúng) đã calibration
   (logistic trên features quan sát được, học trên train_cal, ECE đo trên
   holdout tách theo business). Ngưỡng 0,5 chỉ có nghĩa khi P đã calibration.
2. **k = 3 seed-only không còn là pool mặc định.** Pool mặc định mới là
   strategy-diverse (SQL + Python + plan khác); seed-only chỉ là baseline
   A1 để đo, không phải thiết kế chốt.
3. **Vote không còn đứng trước gate.** Gate E1–E6 (fan trap, grain, cửa
   sổ, định nghĩa doanh thu, schema linking, range) chạy trước vote; candidate
   trượt gate cứng bị loại khỏi pool, và thiểu số qua gate được xem xét
   trước đa số trượt gate.
4. **Revision thay resample mù.** Chỉ revision khi có thông điệp lỗi cụ
   thể; disagreement không lỗi cụ thể → verifier/abstain, không sinh thêm.
5. **Ngân sách tính với η = 1,5 (lập kế hoạch) và η = 1 (trần an toàn).**
   Điểm hòa vốn 24s/candidate của repo chỉ đúng ở η = 2; ở η = 1 là 12s,
   ở η = 1,5 là 18s (với k = 3, N = 600). Adaptive đưa k_avg về ~2,15
   (giả định, phải đo lại) và là cách duy nhất trong các phương án trên
   vừa ngân sách ở η = 1 với t_gen = 10s.
6. **Abstain ngay có thêm 3 trường hợp rõ ràng:** tất cả candidate trượt
   cùng gate cứng; verifier P(đúng) < ngưỡng khóa; thiểu số qua gate nhưng
   không đủ bằng chứng để thắng đa số (khi đó abstain thay vì chọn đa số
   trượt gate).

## 10. Những gì vẫn chưa đủ bằng chứng để chốt (UNVERIFIED — không được ghi thành kết luận)

- Mọi con số PA/gain/ECE: chưa có thí nghiệm nào trên dữ liệu ZAIC trong
  đợt này; các số từ S1–S13 là số của tác giả trên benchmark của họ, không
  transfer tự động sang DataMate, model 7B, hay tiếng Việt.
- Tỉ lệ agree-but-wrong thật của DataMate, phân bố tier thật, t_gen thật,
  T_load thật, η thật, kích thước N thật của private test.
- Verifier logistic có đủ capacity không; verifier có transfer qua business
  mới không; second path Python có thực sự độc lập với SQL không (hay cùng
  một lỗi logic được viết lại bằng hai ngôn ngữ).
- Cách hiểu rulebook thật cho "loại đơn có hàng trả" (mức đơn hay mức dòng)
  — ảnh hưởng trực tiếp gate E4; thuộc P3/P5, không chốt ở đây.
- sqlsure có được phép dùng trong Docker DataMate không (nó không phải
  model inference, nhưng quy định về thư viện bên thứ ba trong Docker chưa
  được đối chiếu với BTC trong đợt này) — và các claim benchmark của nó
  chưa được kiểm chứng độc lập.
- Cross-model jury (S9) không khả thi trong trần 15B với model lớn; chỉ
  dùng làm nguyên lý decorrelation, không phải đề xuất triển khai.
- DiVeRSe/LEVER/CodeT đều dùng model và quy mô lớn hơn nhiều so với
  Qwen2.5-Coder-7B + 6 giờ; nguyên lý chuyển giao được, con số thì không.
