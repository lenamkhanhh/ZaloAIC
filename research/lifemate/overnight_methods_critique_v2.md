# Luồng C — Phản biện phương pháp v2: sửa kết luận của overnight audit v1

**Phạm vi:** Chỉ phản biện và sửa kết luận phương pháp + định nghĩa
điều kiện cho D1/DPO. Không sửa code, không sửa file của luồng A/B,
không git, không GPU, không đọc held-out, không đọc file mới của
luồng A/B trong khi chúng đang chạy. Mọi số v1 dưới đây lấy từ
`overnight_capability_decision.md` (v1) + `overnight_thread_b_methods.md`
+ `overnight_thread_c_evaluation_protocol.md` + `round10-fix-report-round3.md`.
Manifest v2 đang được Luồng A làm: **mọi counts trong file này dùng
v1 (val 185 / test 185) và điều phối viên phải thay bằng counts v2
trước khi thực thi; công thức thì không đổi.**

**Kết luận sửa quan trọng nhất (đọc trước):**
1. "SFT thuần chỉ học hình thức ask" là **GIẢ THUYẾT**, không phải
   kết luận. Nó có thể đúng, nhưng chưa có thí nghiệm LifeMate nào
   chứng minh nó — và D1-lite tồn tại chính là để falsify nó.
2. D1-lite không phải "bước đệm chắc chắn đi tới DPO". Nó là một
   **pilot có thể falsify**, với điều kiện loại/giải pháp tiếp theo
   ghi rõ ở mục 2.
3. DPO không phải "hướng thắng mặc định". Nó là **bước có điều
   kiện**: chỉ chạy khi SFT pilot còn lỗi quyết định đo được VÀ
   pair yield đạt gate chất lượng ở mục 3. Không đủ điều kiện thì
   không train DPO, dù D1 có "trông hứa hẹn".
4. Không có con số nào từ paper khác được chuyển thành kỳ vọng
   LifeMate. Mục 4 kiểm tra lại từng claim mượn và giữ nguyên nhãn
   đọc (kể cả nhãn "chưa đọc full-text").

## 1. Bảng sửa kết luận: cũ (v1) → mới (v2) + bằng chứng

| # | Kết luận v1 (dạng gây hiểu lầm) | Viết lại v2 (đúng mức bằng chứng) | Vì sao phải sửa |
|---|---|---|---|
| C1 | "SFT trajectory thuần túy chỉ dạy hình thức ask chứ không dạy biên quyết định" (decision §0, §3 D1) | **GIẢ THUYẾT H1:** Trên harness LifeMate, SFT trên verified trajectories cải thiện format/prerequisite nhưng không cải thiện biên act/ask/stop (fill-act rate, ask precision/recall). **Trạng thái: CHƯA KIỂM CHỨNG.** Cơ chế ủng hộ H1: next-token objective mặc định fill (AwN, abstract-level), SFT imitate structure (SpeakRL §§1–3), SFT OOD failure (Tool Zero §§1–3). Cơ chế chống lại H1: filter read-first của D1 trực tiếp thay đổi phân phối trajectory mà model thấy (prerequisite có thể học qua imitation thuần túy); chưa có thí nghiệm nào tách "học hình thức" khỏi "học biên" trên LifeMate. | V1 trình bày H1 như kết luận rút ra từ "ba luồng độc lập cùng kết luận", nhưng không luồng nào chạy SFT trên LifeMate. Ba nguồn paper đều là task/harness khác (math, MultiWOZ, BFCL). Suy từ đó thành tính chất của SFT-LifeMate là nhảy logic, dù hướng suy luận có lý. |
| C2 | "D1-lite làm cold start → D2 là hướng chính" (thứ tự cố định) | **Thứ tự có điều kiện, không cố định.** D1-lite là pilot; D2 chỉ là "hướng chính" *nếu* D1 cho kết quả ở ô "cần D2" trong bảng falsify mục 2. Nếu D1 falsify hoàn toàn (mục 2, trường hợp F0), hướng chính trở thành backup (D3 + grammar/guard, model đóng băng) và D2 không chạy. Nếu D1 tự nó đạt adopt (proxy + fill-act + prerequisite cùng cải thiện, qua test confirmation), D2 là bước tùy chọn, không bắt buộc. | V1 khóa thứ tự trước khi có dữ liệu pilot. Thứ tự đúng phải là cây quyết định, không phải pipeline tuyến tính. |
| C3 | "DPO là hướng chính" / DPO-after-SFT như bước tiếp theo hiển nhiên | **DPO là bước có điều kiện** (mục 3). Điều kiện cần (cả hai): (a) SFT pilot còn lỗi quyết định đo được trên validation; (b) pair yield đạt gate chất lượng pre-registered. Thiếu một trong hai → không train DPO. | V1 liệt kê điều kiện loại bỏ của DPO nhưng vẫn gọi nó là "hướng chính", tạo ấn tượng DPO sẽ chạy. Một bước có điều kiện mà điều kiện chưa đo được thì không được gọi là hướng thắng. |
| C4 | "D1 đơn độc adopt chỉ khi fill-act VÀ prerequisite cùng cải thiện" (v1 §5.4) | **Giữ nguyên, nhưng bổ sung:** điều kiện này chỉ có nghĩa khi cả hai đều đo được bằng rule ở protocol v2 (fill-act rule + prerequisite rule, xem file protocol v2). Nếu rule đo fill-act không đáng tin (audit thủ công < 80% agreement, xem protocol v2 §3.1), thì verdict cho D1 là INCONCLUSIVE về decision, không phải ADOPT hay REJECT trên tiêu chí đó. | V1 đặt điều kiện adopt trên hai metric mà chính v1 chưa định nghĩa cách đo vận hành được. Điều kiện không đo được thì không phải điều kiện. |
| C5 | "Thứ tự D1→D2 có thể đảo ngược trong một trường hợp" (v1 §6.5: D2-lite trực tiếp trên base + guard) | **XÓA trường hợp này khỏi plan chính; ghi thành ý tưởng chưa đăng ký.** DPO-from-base mâu thuẫn với chính contract v1 (reference = D1) và không có bằng chứng nào trong thread B ủng hộ nó (Step-DPO cần policy đã ổn định format; base thô chưa qua D1 sẽ làm pair nhiễu bởi lỗi format). Nếu muốn thử, phải đăng ký thành family riêng với hypothesis riêng, sau khi D1/D2 đã có kết quả — không phải branch "có điều kiện" trong cùng một lần chạy. | V1 vừa nói "không DPO-from-base" (§4.1) vừa mở cửa "D2-lite trên base" (§6.5). Hai câu này mâu thuẫn; v2 chọn câu thứ nhất và loại câu thứ hai khỏi plan. |
| C6 | "D1/D2 chết ngay nếu Q-L2 = cấm" (v1 §7) | **Giữ nguyên, nhưng phân biệt hai mức chết.** (a) Chết cho *submission*: đúng, không submit được dù proxy tăng. (b) Chết cho *nghiên cứu*: sai — pilot vẫn có giá trị đo lường (biết biên có học được không) và kết quả đó vẫn dùng được cho backup design (grammar/guard) vì nó cho biết lỗi nào là decision-shaped. Vì vậy Q-L2 gating Stage 3 *training cho submission*, không gating pilot đo lường — nhưng pilot phải được label rõ là "research-only nếu Q-L2 chưa có đáp án", và không được dùng kết quả pilot để claim submission readiness. | V1 gộp hai mức chết làm một, dễ dẫn tới hoặc train mù (nếu hiểu là "cứ train đi") hoặc bỏ luôn cả đo lường (nếu hiểu là "cấm thì dừng hết"). |
| C7 | "ASR không phải bottleneck" đã re-scope thành "chưa chứng minh" (v1 §1) | **Giữ nguyên re-scope, bổ sung thêm một giới hạn:** ngay cả attribution G0-vs-A0 sau này cũng chỉ đo được *current-turn* ASR nếu history vẫn là ASR (cell G1), hoặc đo được cả hai nếu có cell gold-history (G0) — nhưng G0 dùng gold history mà gold history transcript **chưa được xác lập nguồn** (xem mục 5, mâu thuẫn annotation-vs-ASR). Do đó mọi claim ASR-attribution phải kèm cell chính xác và kèm caveat nguồn history transcript. | V1 đã đúng về E0, nhưng chưa chỉ ra rằng chính cell đối chứng G0 cũng mang caveat nguồn history. |
| C8 | "Base Qwen3-4B-Instruct-2507" như base đã chọn (v1 §4.1) | **Base hiện tại là PROVISIONAL.** Zero-shot benchmark đang chạy bên ngoài là input cho chọn base; protocol v2 (Stage 0) tiêu thụ kết quả đó, không chạy lại mù. Nếu benchmark đổi base, SFT pilot phải re-baseline trên base mới; cấm so sánh xuyên base (xem protocol v2 §2). Mọi claim "base tốt nhất" đều chưa được kết luận cho tới khi benchmark xong. | V1 trình bày base như đã chốt trong khi chính task mới nói benchmark zero-shot đang chạy và kết quả của nó là input cho chọn base sau này. Chốt base trước benchmark là đảo thứ tự. |

## 2. D1-lite: pilot có thể falsify (bảng quyết định, đo trên validation)

Pilot D1-lite chạy trên inner_train (v1: 863; v2: theo manifest mới),
chọn cấu hình trên inner_val (v1: 185), **không mở test**. Các metric
dưới đây đo bằng rule ở protocol v2 (fill-act rule có audit thủ công;
prerequisite rule theo model prefix). "Gain" = candidate − baseline
trên cùng val, cùng cell (G1 và A0; một cell tăng, một cell đứng yên
thì không tính là gain cho quyết định này — cần cả hai cell cùng
hướng, trừ khi có lý do cell-specific đã đăng ký trước).

| Trường hợp (val) | Verdict cho D1 | Bước tiếp theo |
|---|---|---|
| **F0 — Flat toàn diện:** proxy gain < +1pp VÀ prerequisite gain < +2pp VÀ fill-act reduction < 2pp (cả ba đều phẳng, cả hai cell) | **D1 FALSIFIED (standalone).** Verified-trajectory SFT không dạy được gì đo được trên val. | Dừng D1. Không train D2 trên nền D1 này như "cold start" (cold start phẳng không phải cold start tốt). Chuyển sang backup (D3 + grammar/guard, model đóng băng). Pair yield từ trace D1 vẫn được báo cáo, nhưng không dùng để biện minh cho D2. |
| **F1 — Form-only (trường hợp H1 dự đoán):** proxy gain ≥ +3pp NHƯNG fill-act reduction < 1pp VÀ prerequisite gain < 1pp | **H1 ĐƯỢC ỦNG HỘ (không chứng minh tuyệt đối).** D1 dạy hình thức, không dạy biên. | **Không adopt D1 đơn độc.** Đi tiếp D2 (với D1 làm reference/cold start) **chỉ nếu** gate pair ở mục 3 đạt. Nếu gate pair không đạt → backup, không cố train DPO với pair kém. |
| **F2 — Decision-shaped (trường hợp H1 bị thách thức):** fill-act reduction ≥ 2pp VÀ prerequisite gain ≥ 2pp (kèm proxy không regress) | **H1 BỊ FALSIFY một phần.** SFT đã chạm được vào biên quyết định, ít nhất qua imitation + filter. | D1 trở thành ứng viên adopt (cần qua test confirmation, protocol v2 Stage 4). D2 trở thành bước tùy chọn: chỉ chạy nếu sau D1 vẫn còn lỗi quyết định đo được (gate mục 3a) — không chạy D2 theo quán tính. |
| **F3 — Hỗn hợp / mâu thuẫn cell:** các metric mâu thuẫn giữa G1 và A0 (ví dụ G1 tăng, A0 giảm) | **INCONCLUSIVE về D1.** Không adopt, không reject. | Nghi ngờ đầu tiên: gap clean-vs-ASR (M3/M4) đang nuốt gain ở A0, hoặc rule đo fill-act không ổn định giữa cells. Điều tra trước: audit fill-act thủ công theo cell, kiểm tra ASR attribution (Stage 1). Không chọn cell thuận lợi để báo cáo. |
| **F4 — Format phá vỡ:** parse failures / rejected-call rate tăng so với baseline trên val (bất kể proxy) | **D1 REJECTED vì regression an toàn format.** | Dừng. Kiểm tra serialization/loss mask trước khi kết luận gì về decision (lỗi format là lỗi pipeline, không phải bằng chứng về H1). |

Ghi chú quan trọng về ngưỡng: các ngưỡng +1pp/+2pp/+3pp ở trên là
**ngưỡng vận hành pre-registered cho pilot val (n=185)**, không phải
ngưỡng thống kê cuối cùng. Chúng được chọn để phân loại hướng đi,
không phải để claim significance — claim significance chỉ xảy ra ở
test confirmation với CI (protocol v2 §5). Nếu val cho kết quả nằm
sát ngưỡng (±1pp), verdict là INCONCLUSIVE và pilot cần thêm dữ
liệu val (không phải mở test để giải quyết — mở test để giải quyết
val ambiguity là test leakage).

## 3. DPO: bước có điều kiện — định nghĩa "đủ chất lượng" có nguyên tắc

DPO chỉ được train khi **cả hai** điều kiện sau đều đạt, đo trước
khi train và ghi log. Không điều kiện nào được nới sau khi thấy kết
quả DPO.

### 3a. Điều kiện 1 — SFT pilot còn lỗi quyết định đo được (trên val)
Tồn tại decision-error mass: **số mẫu val có lỗi fill-act ≥ 10 mẫu
HOẶC số mẫu val có prerequisite failure ≥ 10 mẫu** (đếm theo mẫu,
không theo tỉ lệ — để tránh game với mẫu số nhỏ; 10 là ngưỡng đếm
tối thiểu để pair construction có vật liệu, được label là quy ước
vận hành, không phải hằng số đã đo). Nếu cả hai đều < 10 mẫu thì
không còn gì để DPO sửa một cách đáng tin — DPO lúc đó chỉ fit
noise; verdict là "không chạy DPO", và D1 (nếu đạt F2) đi thẳng tới
test confirmation.

### 3b. Điều kiện 2 — Pair yield đạt gate chất lượng
Pair được tính là **usable** chỉ khi thỏa tất cả:
1. **Cùng prefix thật:** prompt + observation history tới bước divergent
   phải giống hệt nhau giữa chosen và rejected (không ghép prefix
   khác nhau rồi gọi là pair). Prefix bao gồm cả observation text
   (không chỉ user request).
2. **First-divergent-step only:** chỉ bước đầu tiên khác nhau được
   tối ưu; các bước sau divergent step bị loại khỏi loss (nếu
   implementation không tách được bước này thì DPO suy biến thành
   whole-trajectory DPO — lúc đó phải đổi tên phương pháp thành
   "trajectory DPO" và mất claim credit-assignment của Step-DPO).
3. **Chosen đã verify:** chosen là gold call hoặc trajectory đã
   simulator-verify (state-hash khớp gold). Chosen tự viết tay hoặc
   từ model khác mà không qua verify thì không tính.
4. **Rejected là lỗi thật của chính model:** rejected lấy từ trace
   của baseline/D1 trên train/val (không import từ harness/model
   khác, không lấy từ paper, không lấy từ repo bạn — repo 404, và
   Step-DPO finding nói foreign pairs kém hiệu quả vì OOD).
5. **Phủ 3 class lỗi chính, không class nào = 0, không class nào
   chiếm > 60% tổng pairs:** fill-act, prerequisite-skip,
   wrong-entity. Class nào = 0 thì DPO không được claim cải thiện
   class đó; class nào > 60% thì phải rebalance trước khi train
   (dominance cap là quy ước chống mode collapse vào một class).
6. **Cân bằng ask/act:** tỉ lệ ask-chosen pairs nằm trong
   **[30%, 70%]** tổng pairs (và act-chosen ≥ 30%). Ngoài band này
   thì pair set bị lệch về một phía của biên — train sẽ kéo
   ask-rate lệch hướng đó. Band này là quy ước chống ask-collapse /
   act-collapse, không phải hằng số đã tune.
7. **Ngưỡng số lượng tối thiểu — dạng công thức pre-register, không
   phải số tuyệt đối bịa sẵn:** trước khi train, tính từ pilot yield:
   `N_min = max(5 × (số distinct error situations trong val decision
   errors), 100)`. Lý do: ít nhất 5 pairs mỗi distinct situation để
   tránh fit một ví dụ đơn lẻ; floor 100 để optimization DPO có đủ
   vật liệu ổn định. **N_min, một khi tính từ pilot yield và ghi
   log, không được hạ sau khi thấy kết quả DPO.** Nếu yield < N_min
   → không train DPO: hoặc thu thêm rollouts trên train (không
   dùng val để tạo pair train — val pairs chỉ dùng để đo, nếu dùng
   val traces làm training pairs thì val bị burn), hoặc dừng DPO.
   Con số "5" và "100" ở đây là quy ước vận hành được công khai,
   không phải kết quả đo — điều phối viên có quyền thay chúng
   **trước khi pilot chạy**, nhưng không sau khi đã thấy kết quả.

**Distinct error situation** (dùng cho N_min và cho guard §5 của
protocol v2): một situation = (sample_id, reference_value,
reference_type) đối với guard, và (sample_id, divergent_step_tool,
error_class) đối với pair. Cùng sample + cùng reference/step +
cùng class qua nhiều arms/versions/generations chỉ tính 1 lần.
Ví dụ: train_0004 light_set qua mọi arms/versions = 1 situation,
không phải nhiều positives.

### 3c. DPO stop rules (trong lúc train, đo trên val)
- Ask-rate ra khỏi band đã đăng ký (gold val ask rate ± band ở
  protocol v2 §2.3) → dừng, kiểm tra balance trước khi train tiếp.
- Format failures / rejected-call rate tăng so với D1 checkpoint →
  dừng (β quá thấp hoặc reference sai).
- Val proxy degrade 2 checkpoints liên tiếp → dừng (early-stop
  signal, không thử checkpoint thứ ba không ghi log).
- Mọi thay đổi hyperparameter sau khi train bắt đầu đều là variant
  mới với val read riêng, không phải "tiếp tục train".

## 4. Spot-check claims mượn từ paper (kiểm tra lại, giữ nhãn đọc)

| Claim (v1 / Thread B) | Kết quả spot-check của luồng C (2026-10-29) | Nhãn cuối cùng |
|---|---|---|
| Step-DPO: "chỉ tối ưu first erroneous step từ cùng prefix" + "pair tự sinh > pair human/GPT-4" | **XÁC NHẬN từ abstract arXiv:2406.18629 (v1).** Abstract ghi rõ: dataset ~10K pairs (problem + prior steps + chosen + rejected step); pipeline 3 bước (error collection, step localization, rectification); "chosen reasoning step is generated by the model itself, as we find that in-distribution data (i.e., self-generated data) is more effective than out-of-distribution data (e.g., data written by humans or GPT-4) for Step-DPO, as shown in Table 4"; <500 steps, ~+3% MATH ở model >70B; Qwen2-72B-Instruct 70.8% MATH / 94.0% GSM8K. **Phạm vi bắt buộc:** math long-chain reasoning, model >70B, Table 4 của paper — không phải tool use, không phải 4B, không phải LifeMate. Việc "chosen step tự sinh" trong paper là bước rectification của chính policy, không phải "lấy gold làm chosen" — khi áp sang LifeMate, chosen = gold/verified call là một *adaptation*, phải ghi là adaptation, không phải "đúng như Step-DPO". | **ĐÃ XÁC NHẬN (abstract-level, arXiv v1).** Dùng được cho cơ chế (first-step + in-distribution), không dùng cho kỳ vọng số. |
| SpeakRL: base 25.63 / SFT 28.78 / DPO 45.73 / SpeakRL 46.17, turns 8.12 → 5.82 (MultiWOZ 2.4) | **XÁC NHẬN MỘT PHẦN.** ArXiv HTML 2512.13159v1 Figure 1 xác nhận: Base 25.63%, Claude-Sonnet-4.0 44.08%, SpeakRL 46.17% trên MultiWOZ 2.4; review độc lập ghi "20.14% absolute improvement (25.63% → 46.17%)" và "turns reduced by 28%" (≈ 8.12 → 5.85, khớp 5.82 trong sai số làm tròn). **Các số ablation SFT 28.78 / DPO 45.73 và turns 8.12 → 5.82 chính xác KHÔNG xuất hiện trong snippet spot-check của luồng C** — chúng vẫn mang nhãn "Thread B đọc §§1–3", không được nâng lên "luồng C xác nhận". Setup caveat giữ nguyên và bổ sung: GRPO của SpeakRL được review ghi là *bỏ KL penalty* với reference để thích ứng format custom — chi tiết này quan trọng khi áp sang DPO (DPO giữ reference; GRPO-bỏ-KL không phải DPO). Simulator là Claude Sonnet 4 + LLM-judge (theo Thread B) — cả hai đều bị cấm ở đây, nên không chuyển số nào sang LifeMate. | **Headline (25.63 → 46.17) XÁC NHẬN; ablation SFT/DPO/turns: GIỮ NHÃN Thread-B-read, chưa re-verify.** Không dùng làm kỳ vọng LifeMate. |
| Tool Zero: SFT BFCL-Live 61.1 → 78.6 nhưng Non-Live/Multi-Turn đứng yên/regress (9.6 → 7.8); xLAM-7B-fc nhất BFCL nhưng tệ nhất trung bình | **XÁC NHẬN pattern cốt lõi từ arXiv HTML 2511.01934 (v1/v2).** Văn bản paper: "significant improvements on the Live metric… from 61.1 to 78.6. Conversely, exhibiting negligible gains or regressions on Non-Live and Multi-Turn subsets (e.g., 9.6 → 7.8)"; "xLAM-7B-fc achieved top performance on BFCL, it suffered significant degradation on two others, leading to the lowest overall average score"; "foundation models demonstrated more consistent cross-dataset performance". **Phát hiện lệch số nhỏ:** Thread B ghi Tool-Zero-7B "beats ToolACE-8B by 7.14% and ToolRL-7B by 7.18%"; snippet spot-check ghi "surpasses DS-R1 by +8.33 and ToolRL-7B by +6.84" (metric/version khác nhau giữa v1/v2 hoặc bảng khác nhau). **Vì vậy: KHÔNG trích +7.14/+7.18/+6.84/+8.33 làm số đã verify.** Chỉ trích pattern Live-tăng/Multi-Turn-regress + cross-dataset inconsistency, là phần đã xác nhận khớp nhau ở cả hai nguồn. | **Pattern XÁC NHẬN; delta số Tool-Zero-7B: CHƯA VERIFY (mâu thuẫn nhỏ giữa các nguồn) — không trích.** |
| STaR / RFT / APIGen / APIGen-MT (cơ chế + số) | **Không re-verify độc lập trong luồng C; giữ nhãn Thread B.** Các số (STaR loop, RFT 35.9% → 49.3% GSM8K LLaMA-7B, APIGen 3,673 APIs / 60k, APIGen-MT 5k trajectories) đều là task khác (QA/math/function-calling tổng quát), không phải LifeMate. Chỉ dùng cho cơ chế (verified trajectory, distinct-path diversity, multi-turn unit). Đặc biệt: RFT "distinct correct paths" là finding trên GSM8K — áp sang LifeMate thành metric distinct-path diversity là *suy luận*, phải ghi là suy luận. | **GIỮ NHÃN Thread-B-read. Cơ chế dùng được; số không chuyển.** |
| Hammer (function masking + 7.5k irrelevance, BFCL 83.92% 7B) | **Không re-verify trong luồng C; giữ nhãn Thread B.** Điểm duy nhất luồng C bổ sung: checkpoint 7.61B vượt cap là lý do đủ để loại checkpoint, nhưng *ý tưởng* irrelevance (`[]` = không gọi) vẫn dùng được — với điều kiện irrelevance pairs của LifeMate phải là "missing argument → ask" và "no suitable tool → stop", không phải copy nhãn `[]` của Hammer (LifeMate không có output `[]`; output là ask/stop theo contract). | **GIỮ NHÃN Thread-B-read. Ý tưởng dùng được sau adaptation; checkpoint loại.** |
| AwN: "next-token training mặc định fill" | **GIỮ NGUYÊN NHÃN: abstract + fragment v2, CHƯA ĐỌC FULL-TEXT.** Luồng C không fetch thêm AwN full-text thành công trong phạm vi này và không nâng cấp nhãn. Mọi câu dùng AwN phải kèm "(abstract-level)". Đặc biệt: AwN-as-prompting đã bị E5 bác bỏ trên LifeMate (0/7 → 1/7) — AwN chỉ dùng được cho *cơ chế* (vì sao fill là default), không dùng để biện minh cho prompting thêm. | **CHƯA ĐỌC FULL-TEXT — không nâng cấp.** |
| When2Call: taxonomy 4 quyết định + 3,109 instances | **GIỮ NGUYÊN NHÃN: bản gốc CHƯA ĐỌC, taxonomy qua secondary.** Chỉ dùng taxonomy (call/answer/ask/abstain) cho eval labeling; không dùng dataset làm training data (khác tools, tiếng Anh, không có simulator state). | **BẢN GỐC CHƯA ĐỌC — không nâng cấp.** |

## 5. Mâu thuẫn annotation-vs-ASR trong v1 (ghi rõ cho luồng A + điều phối viên)

V1 chứa hai câu khó đứng chung nếu không tách lineage:
- (a) "Train gold history là text sạch" (§2.7, §4.3 M3: history user
  turns trong train mang clean `audio_text`).
- (b) "Gold transcript của history turn CHƯA được xác lập / history
  `audio_text` là ASR output theo thiết kế E0" (§3 D3, §8.8).

Cả hai có thể cùng đúng nếu tách hai tầng:
- **Tầng annotation trong train file:** field `audio_text` của history
  user turns trong `train.jsonl` — cần luồng A xác lập lineage: nó
  là transcript do annotator viết (gold) hay là output của một ASR
  pass nào đó đã chạy trước khi đóng gói data? Tên field không chứng
  minh nguồn. **Không gọi một field là "gold sạch" chỉ vì tên nó là
  `audio_text` nếu chưa xác lập nguồn.**
- **Tầng transcript của trace runtime:** khi chạy `cmd_infer`, history
  user turns thiếu `audio_text` được transcribe bằng ASR — đó là
  hành vi runtime, không phải thuộc tính của train file.

**Quy tắc đặt tên v2 (áp dụng cho mọi báo cáo sau):**
- "Gold transcript" chỉ dùng khi nguồn đã xác lập là annotation
  con người hoặc transcript đã verify thủ công.
- "Recorded history text" cho field `audio_text` của history turns
  khi nguồn chưa xác lập.
- "ASR transcript" cho output của ASR pass tại runtime.
Cho tới khi luồng A xác lập lineage, mọi claim về gap M3 phải viết
là "gap giữa recorded history text (nguồn chưa xác lập) và runtime
ASR history text", không viết "gap giữa gold sạch và ASR". Điều này
không làm đổi quyết định D1/D2 (D1/D2 train trên recorded text dù
nguồn là gì), nhưng nó làm đổi *diễn giải* của cell G1/A0: nếu
recorded history text vốn đã là ASR output thì gap M3 nhỏ hơn v1
tưởng, và ASR attribution phải tính lại.

## 6. Những gì file này KHÔNG làm (để điều phối viên không hiểu lầm)

- Không chọn base (Stage 0 của benchmark quyết định; base hiện tại
  là provisional).
- Không tuyên bố "ready to train" — đó là việc của điều phối viên
  sau khi tích hợp 3 luồng + kiểm tra snapshot cuối.
- Không sửa protocol v1 bằng cách xóa nó: protocol v2 (file companion)
  là bản thay thế có đăng ký, v1 giữ nguyên làm đối chứng lịch sử.
- Không mở held-out, không liên hệ BTC (chỉ gợi ý wording ở protocol
  v2 §7 cho điều phối viên soạn draft cuối, không gửi).
- Không đọc file mới của luồng A/B trong khi chúng đang chạy; mọi
  số v2-manifest đều là dependency note cho điều phối viên cập nhật
  sau (protocol v2 §8).

## 7. Evidence ledger (luồng C, v2)

**Đã đọc / kiểm tra trong luồng này:**
- `research/lifemate/overnight_capability_decision.md` (v1, toàn văn).
- `research/lifemate/overnight_thread_b_methods.md` (v1, toàn văn).
- `research/lifemate/overnight_thread_c_evaluation_protocol.md` (v1,
  toàn văn).
- `research/lifemate/round10-fix-report-round3.md` (grep xác nhận:
  G2 15/976 = 1.54%, phone residual 11/19, train_0004 independent
  positive duy nhất, fires 21 → 15 sau call-log source).
- Spot-check web (2026-10-29): arXiv abstract/HTML Step-DPO
  2406.18629v1 (first-step + in-distribution finding xác nhận);
  arXiv HTML SpeakRL 2512.13159v1 Figure 1 (base 25.63 / SpeakRL
  46.17 xác nhận; ablation SFT/DPO không xuất hiện trong snippet);
  arXiv HTML Tool Zero 2511.01934 (Live 61.1 → 78.6,
  Multi-Turn 9.6 → 7.8, xLAM cross-dataset inconsistency xác nhận;
  delta Tool-Zero-7B mâu thuẫn nhỏ giữa nguồn, không trích).
- Tính toán CPU của luồng C (không ghi file ngoài 2 file sở hữu):
  Wilson CI cho 15/976 = [0.0093, 0.0252], 11/19 = [0.3628, 0.7686],
  0/7 = [0, 0.3543], 1/7 = [0.0257, 0.5131]; bảng power paired
  (protocol v2 §5).

**Giữ nguyên nhãn chưa đọc / chưa verify (không nâng cấp):**
- AwN full-text (abstract + fragment v2 only).
- When2Call bản gốc (taxonomy qua secondary only).
- STaR/RFT/APIGen/APIGen-MT/Hammer: Thread-B-read, không re-verify
  độc lập trong luồng C.
- Tool-Zero-7B delta số (+7.14/+7.18/+6.84/+8.33): mâu thuẫn nhỏ,
  không trích.
- SpeakRL ablation SFT 28.78 / DPO 45.73 / turns 8.12 → 5.82:
  Thread-B-read (§§1–3), không xuất hiện trong spot-check snippet
  của luồng C.
- Mọi số latency/train cost/A30: NOT_MEASURED (không suy từ T4).
- Held-out 308: chỉ counts + lock rule từ v1, không mở rows.

**Unknowns / blockers (chuyển cho điều phối viên):**
- Lineage của history `audio_text` trong train file (gold annotation
  hay ASR output cũ) — luồng A xác lập (§5).
- Counts manifest v2 (luồng A) — protocol v2 dùng công thức v1,
  điều phối viên thay số trước khi thực thi.
- Kết quả zero-shot benchmark (đang chạy) — Stage 0 tiêu thụ, base
  provisional cho tới khi có nó.
- Organizer answers Q-L1/Q-L2/Q-L3/Q-D1/Q-L5 (+ Q-L4 về cách đo A30)
  — chưa gửi; wording gợi ý ở protocol v2 §7.
