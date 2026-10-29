# Luồng C — Evaluation protocol v2 (staged, sửa protocol v1)

**Trạng thái:** Bản đăng ký thay thế protocol v1
(`overnight_thread_c_evaluation_protocol.md` — giữ nguyên làm đối
chứng lịch sử, không sửa nó). Mọi stage dưới đây phải được đăng ký
**trước khi chạy stage đó**; thay đổi sau khi thấy kết quả phải
ghi thành amendment có lý do, không sửa lặng lẽ.

**Thay đổi lớn nhất so với v1 (đọc trước):**
1. **Bỏ quy tắc "mỗi family tối đa 2 reads (pilot + final)".**
   Mỗi family chỉ có **ĐÚNG 1 test read (confirmation)**. Test read
   không phải vòng chọn. Candidate fail test → REJECT, không iterate
   trên test. Candidate thứ hai trong cùng family = family mới, cần
   test set mới — mà test set mới không tồn tại → chỉ được báo cáo
   là test-informed exploration, không bao giờ là adoption evidence.
2. **Bỏ tổng "2096 runs mặc định".** Chi phí tính theo công thức
   từng stage và chỉ các stage thực sự chạy mới tốn runs. Không cộng
   dồn mù.
3. **Base là provisional.** Stage 0 tiêu thụ zero-shot benchmark
   đang chạy; nếu benchmark đổi base thì re-baseline, cấm so sánh
   xuyên base.
4. **Power analysis bắt buộc.** Với test n=185, bar +3pp/CI gần như
   không đạt được trừ khi discordance rất thấp — verdict mặc định
   cho gain nhỏ là INCONCLUSIVE, không phải adopt, không phải
   "no effect", và tuyệt đối không nới bar sau khi thấy kết quả.

**Counts dùng trong file này:** v1 (val 185 / test 185; test strata:
normal 144, ask_after 21, empty 13, ask_only 7). Manifest v2 của
luồng A có thể nhích counts nhẹ — điều phối viên thay số trước khi
thực thi và kiểm tra lại bảng power (§5) nếu test n đổi đáng kể.
Công thức không đổi.

## 1. Nguyên tắc khóa (lock rules)

- **Validation (185):** dùng cho pilot, chọn cấu hình, early stopping,
  đo pair yield, đo ASR attribution. Được đọc nhiều lần, nhưng mọi
  lần đọc đều ghi log (cấu hình nào, metric nào, quyết định nào rút
  ra). Validation numbers là development numbers, không bao giờ
  được trích làm performance của direction.
- **Inner-test (185):** chỉ mở sau khi freeze candidate (config +
  checkpoint + prompts + serialization + guard settings đều ghi
  log và bất biến). Mỗi family đúng 1 read. Read là confirmation,
  không phải vòng chọn. Fail → REJECT family đó (không iterate).
  Muốn thử candidate khác → đăng ký family mới TRƯỚC KHI đọc test
  của family đó; family mới này phải có design frozen từ val evidence
  (không được thiết kế lại từ kết quả test của family trước — nếu
  có, nó là test-informed và mất quyền adopt trên cùng test).
- **Held-out 308:** khóa cho mọi selection/tuning/early stopping/
  prompt/threshold choice và mọi error analysis có feedback vào
  design. Chỉ mở đúng 1 lần post-freeze cho candidate đã adopt qua
  test (Stage 5). Ngoại lệ duy nhất: rule sequential pre-registered
  ở §6.4 (phải chọn TRƯỚC KHI đọc test; mặc định là KHÔNG dùng
  ngoại lệ này).
- **Train (863 v1):** mẫu trong train bị burn cho evaluation — không
  bao giờ xuất hiện trong số claim candidate thắng zero-shot. Báo
  cáo số trên train/full-dev (1237) làm evidence cải thiện là vi
  phạm protocol, không phải kết quả yếu.
- **Không pool:** không pool versions/arms/transcript cells/val+test.
  Mỗi cell một row, một n, một CI. Meta-summary pooled chỉ được
  phép khi các row per-cell đã in đầy đủ phía trên.

## 2. Stage 0 — Zero-shot model selection (tiêu thụ benchmark, không chạy lại mù)

**Quyết định stage này trả lời:** base model nào là comparator cho
mọi stage sau? (Không phải "candidate nào thắng" — stage này chưa
có candidate.)

- **Tiêu thụ benchmark đang chạy:** benchmark zero-shot là một run
  độc lập bên ngoài protocol này. Kết quả của nó chỉ được tiêu thụ
  nếu mỗi row ghi rõ: sample set + n, transcript cell, config
  (checkpoint/revision/decoding), scorer version. Nếu benchmark chạy
  trên full dev (1237, chứa train tương lai) hoặc trên held-out thì
  số đó **không được dùng cho selection** — phải chạy lại baseline
  trên val/test theo protocol này (Stage 0b), không import số.
- **Base hiện tại = PROVISIONAL:** Qwen3-4B-Instruct-2507 rev `cdbee75`
  + PhoWhisper-small (4.244B). Mọi claim "base tốt nhất" đều chưa
  kết luận cho tới khi benchmark xong và Stage 0 ghi nhận base cuối.
- **Stage 0b — frozen comparator (1 lần duy nhất, trước khi có
  candidate):** chạy baseline đã freeze trên inner-test ở G1 và A0
  (2 × 185 = 370 model runs) + gold-replay sanity trên test (CPU;
  state-hash exact rate phải = 1.0, nếu không thì DỪNG — đó là
  scorer/simulator bug, không phải kết quả model). Comparator này
  được ghi log và tái sử dụng cho mọi family — không chạy lại
  baseline trên test sau khi thấy candidate (chạy lại = test read
  mới cho baseline, phá tính frozen của comparator).
- **Nếu benchmark đổi base:** baseline cũ bị burn làm comparator.
  Stage 0b phải chạy lại trên base mới (đây là comparator mới cho
  family mới, không phải "read thứ hai" của family cũ), và mọi
  candidate SFT pilot trước đó (train trên base cũ) không được so
  với comparator mới — **cấm so sánh xuyên base**. SFT pilot phải
  re-baseline (chạy lại baseline mới trên val) trước khi đo gain.
- **Stop/continue:** Stage 0 xong khi base đã freeze + comparator đã
  ghi log. Không có numeric gate so với số full-dev cũ (sample set
  khác nhau nên số cũ không phải target).

## 3. Stage 1 — ASR ablation (tách khỏi SFT pilot, chỉ dùng validation)

**Quyết định:** ASR có nằm trên critical path không? (Không phải
"ASR checkpoint nào thắng" — adoption của ASR checkpoint cần test
confirmation riêng, xem §6.)

- **Arms (val 185):** A1 (ASR medium, 4.769B) vs A0 (ASR small, baseline
  val đã có từ Stage 0b tương đương trên val — nếu Stage 0b chỉ chạy
  test thì chạy thêm baseline val G1/A0: 2 × 185 = 370 runs; ghi rõ
  trong log stage nào chạy cái gì). Chỉ A1 là runs mới bắt buộc:
  **185 model runs** (cộng ASR passes: transcribe val current requests
  bằng medium nếu chưa cache — số passes = 185, wall-clock
  NOT_MEASURED).
- **Metrics:** entity-span error rate (spans mang slot values: tên
  người, dãy số, time/date, negation/conditional markers) + overall
  WER (per-sample mean + pooled, cả hai đều label) + attribution
  G0-vs-A0 nếu có cell G0 trên val (ASR-attributable = G0 đúng + A0
  sai; LLM = cả hai sai; ASR-luck = G0 sai + A0 đúng, đếm riêng,
  không net). Overcorrection rate bắt buộc cho mọi knob
  conditioning (initial_prompt/hotwords): tỉ lệ mẫu mà transcript
  có conditioning tệ hơn không conditioning.
- **Continue/stop:** ASR-attributable failures ≥ 10% val (tức ≥ 19/185
  mẫu val, đếm theo mẫu) **VÀ** tập trung entity/negation → ASR vào
  critical path: candidate ở Stage 2/3 phải có ASR arm (C_ASR vs
  C_gold). Dưới 10% → ASR deprioritize, chain đi tiếp LLM-side;
  kết quả âm vẫn báo cáo (negative result là result). Stage 1 không
  adopt ASR checkpoint nào — adoption cần paired bar ở test (§6).
- **Caveat lineage (từ critique §5):** cell G0 dùng gold history mà
  nguồn history transcript chưa xác lập — mọi attribution phải kèm
  caveat này cho tới khi luồng A xác lập lineage. Nếu recorded
  history text vốn đã là ASR output thì gap M3 nhỏ hơn v1 tưởng và
  attribution phải tính lại.

## 4. Stage 2 — SFT pilot D1-lite (chọn cấu hình trên validation)

**Quyết định:** D1 có dạy được gì đo được không, và nếu có thì thuộc
ô nào trong bảng falsify (critique §2)?

- **Train:** chỉ inner_train (v1: 863). **Iterate:** chỉ inner_val
  (v1: 185), cells G1 và A0 (candidate chỉ thắng trên gold transcripts
  thì chưa giải quyết deployed setting). Pilot slice trước (~100
  trajectories, 1 epoch; LoRA-vs-full đo wall-clock/memory trên đúng
  setup — NOT_MEASURED cho tới khi pilot đo).
- **Val metrics bắt buộc (mỗi checkpoint):** proxy (4-number
  decomposition §3.4) + fill-act rate (§3.1) + prerequisite rate
  (§3.2) + ask confusion (§3.3) + termination (§3.4) + format failures
  / rejected-call rate. Checkpoint choice dựa trên bộ này, không chỉ
  proxy.
- **Ask-rate band (pre-register trước khi đánh giá checkpoint đầu
  tiên):** tính gold val ask rate = (ask_only + ask_after)/185 trên
  val gold (v1: (7 + 21)/185 ≈ 15.1% theo test strata? — **không,
  band tính trên VAL gold, không phải test**: điều phối viên tính
  từ val manifest v2 và ghi log trước khi đo candidate). Band =
  [gold_val_ask_rate − 5pp, gold_val_ask_rate + 10pp] (bất đối xứng
  có lý do: over-asking là failure mode chính từ SpeakRL lesson,
  under-asking đã bị bắt bởi fill-act rate). Ngoài band → stop,
  kiểm tra pair/config balance trước khi train tiếp.
- **Stop rules (một cái đủ để dừng pilot):** (a) val proxy degrade
  2 checkpoints liên tiếp; (b) ask-rate ra khỏi band; (c) format
  failures / rejected-call rate tăng so với baseline; (d) constraint
  breach (context, budget) → reject, không trim lặng lẽ;
  (e) divergence / NaN → báo cáo, không re-run với hyperparameter
  đổi lặng lẽ (mỗi lần đổi = variant mới với val read riêng).
- **Output:** một D1 checkpoint đã freeze (hoặc verdict F0/F1/F2/F3/F4
  theo critique §2) + val numbers + pair yield report (số pairs
  first-divergent-step trích được từ baseline/D1 traces, phân theo
  class — đầu vào cho gate DPO §5). Không test read ở stage này.

## 5. Stage 3 — DPO có điều kiện (chỉ khi gate đạt; train/val như Stage 2)

**Gate (đo trước khi train, ghi log — xem critique §3):**
- (a) Decision-error mass trên val: mẫu val có fill-act ≥ 10 mẫu
  HOẶC mẫu val có prerequisite failure ≥ 10 mẫu (đếm theo mẫu).
- (b) Pair yield đạt tất cả: cùng prefix thật; first-divergent-step
  only (nếu implementation không tách được thì đổi tên thành
  "trajectory DPO", mất claim Step-DPO); chosen đã verify (gold
  hoặc state-hash khớp); rejected là lỗi thật của chính model;
  phủ đủ 3 class (fill-act, prerequisite-skip, wrong-entity), không
  class nào = 0, không class nào > 60%; ask-chosen share trong
  [30%, 70%]; tổng pairs ≥ N_min = max(5 × distinct error
  situations, 100) tính từ pilot yield, ghi log trước khi train,
  không hạ sau khi thấy kết quả.
- Gate không đạt → không train DPO. D1 (nếu F2) đi thẳng Stage 4;
  nếu F0/F1 mà gate không đạt → backup.

**Train/iterate:** như Stage 2 (train pairs từ train traces — val
traces KHÔNG dùng làm training pairs, nếu không val bị burn;
iterate trên val). Stop rules như Stage 2, cộng: DPO phá format
(parse failures tăng) → dừng ngay. Reference = D1 checkpoint
(không DPO-from-base — xem critique C5).

## 6. Stage 4 — Frozen test confirmation (ĐÚNG 1 read mỗi family)

**Family là gì:** một family = một hypothesis + một design đã freeze
từ val (ví dụ: F_D1 = "verified-trajectory SFT cải thiện
prerequisite/fill-act"; F_D2 = "Step-DPO trên nền D1 cải thiện biên
act/ask/stop"). F_D2 phải được đăng ký và freeze design từ val
**trước khi đọc test của bất kỳ family nào** — nếu design của F_D2
thay đổi sau khi thấy kết quả test của F_D1 thì F_D2 là test-informed
và mất quyền adopt trên cùng test (xem §1).

**Runs mỗi family (test 185):** candidate G1 + A0 = **370 model runs**.
Baseline comparator tái sử dụng từ Stage 0b (0 runs mới). Guard
shadow trên saved traces (0 model runs, CPU). Tổng test-phase nếu
chạy cả hai families: 370 (baseline comparator) + 370 + 370 = 1110
model runs. Không có "pilot test read" nào nữa — mọi test read đều
là confirmation read và đều đếm vào 1 read của family đó.

**Adopt (TẤT CẢ, pre-registered):**
1. Primary binary (state-hash exact rate): paired difference ≥ +3pp
   **và** paired bootstrap 95% CI loại 0, ở **CẢ G1 và A0** (gold-only
   win không adopt). Xem §5 về power: với n=185, bar này khó đạt trừ
   khi discordance thấp — đó là tính chất của bar, không phải lý do
   nới bar.
2. Không catastrophic stratum failure: không stratum nào (kể cả
   n<30) có 0 correct (0/n). Xem §4 cho strata n<30.
3. Không stratum n≥30 nào regress > 5pp so với baseline (normal
   stratum, n=144 v1).
4. Guard shadow trên test traces: model-proposal false-block rate
   ≤ 2% point estimate, Wilson upper ≤ 5%; correct blocks trên
   **≥ 3 independent situations** (de-duplicated theo §3.5; hiện
   tại trên traces cũ chỉ có 1 — chưa đạt, phải đo lại trên test
   traces, không kế thừa số cũ).
5. Constraints thỏa dưới CẢ total và non-embedding counting
   (cho tới khi Q-L1 có đáp án), context ≤ 16384 (audit lại nếu
   serialization đổi), deterministic decoding như đã cấu hình.
6. D1 standalone adopt thêm điều kiện: fill-act VÀ prerequisite cùng
   cải thiện (theo rule §3) — nếu chỉ proxy tăng thì đó là form
   learning, không adopt D1 đơn độc (chuyển sang D2 nếu gate đạt).

**Verdict khi CI chứa 0:** **INCONCLUSIVE** — không phải "no effect",
không phải adopt, không phải reject vì "không có tác dụng". Điểm
ước lượng dương + CI chứa 0 vẫn là INCONCLUSIVE. **Tuyệt đối không
nới ngưỡng (+3pp → +2pp, CI 95% → 90%, one-sided post hoc) sau khi
thấy kết quả.** Mọi thay đổi bar sau khi thấy test đều là amendment
cho thí nghiệm TƯƠNG LAI với test set mới, không áp ngược cho
candidate này.

**Fail → REJECT family đó.** Không iterate, không "sửa nhỏ rồi đọc
lại test". Candidate thứ hai trong cùng family = family mới, cần
test set mới (không tồn tại) → báo cáo là test-informed exploration.

## 7. Stage 5 — Held-out post-freeze (chỉ khi test confirm)

- Chỉ candidate đã adopt qua Stage 4 mới được chạy held-out:
  **616 runs** (308 × G1/A0), báo cáo as-is, không tuning sau đó.
- Mâu thuẫn với test → báo cáo, không sửa. Mở lại development cần
  split/seed mới + families mới (test cũ bị burn cho direction đó).
- **Ngoại lệ sequential (phải chọn TRƯỚC KHI đọc test, mặc định
  KHÔNG dùng):** nếu điều phối viên pre-register trước test read
  rằng "nếu test INCONCLUSIVE thì held-out run sẽ quyết định adopt
  với cùng bar +3pp/CI", thì đó là thiết kế sequential hợp lệ với
  alpha cost đã công khai — nhưng nó phải được ghi trong log Stage 4
  trước khi test chạy. Nếu không pre-register thì held-out KHÔNG
  được dùng để cứu một test INCONCLUSIVE (nó trở thành thí nghiệm
  mới, cần freeze lại toàn bộ và công khai rằng adoption decision
  đã dùng hai lần đọc).

## 8. Metrics — định nghĩa vận hành được + giới hạn (bắt buộc cho mọi stage report)

### 8.1 Proxy outcome (primary, nhưng không phải duy nhất)
- State-hash exact rate (per-sample, primary binary) + proxy score
  (state_hash-gated tool F1) + raw F1 (bỏ hash gate) + write-only F1
  (loại reads khỏi cả submission và gold trước khi tính F1 — phơi
  read-dilution gaming: write-only 1.0, +1 read 0.6667, +2 reads 0.5).
  Bốn số luôn đi cùng nhau. Scorer là engineering proxy, không phải
  official evaluator — mọi số đều mang label "proxy" cho tới khi có
  evaluator thật (scorer có UNVERIFIED items: ask scoring, reads có
  tính vào F1 không — xem v1 §1.1).

### 8.2 Fill-act rate (rule đo + giới hạn — mới so với v1)
- **Định nghĩa vận hành:** Xét mỗi model write proposal tại một turn
  mà gold trajectory tại turn tương ứng là `sys.ask_missing_info`
  (hoặc, ở mức sample khi turn alignment không tin được: sample mà
  gold kind là ask_only/ask_after và model submit write cho cùng
  tool với slot mà gold đang hỏi). Proposal được đếm là fill-act
  nếu TẤT CẢ: (a) slot đó thiếu trong request (không xuất hiện dưới
  dạng verbatim hoặc derived span trong current request text theo
  prover rule: number/date/amount spans); (b) slot đó KHÔNG xuất
  hiện trong bất kỳ prior observation nào của chính model prefix
  (nếu có trong observation thì đó là grounded copy, không phải
  fill-act); (c) giá trị được điền khớp với một trong các nguồn
  "cám dỗ" đã biết: current_time của context, giờ round tiếp theo,
  hoặc một giá trị từ history turn không liên quan (kiểm tra bằng
  span search trong history text). Fill-act rate = fill-act proposals
  / write proposals tại các turn gold-ask (proposal-level) VÀ
  fill-act samples / ask-gold samples (sample-level) — báo cáo cả hai.
- **Giới hạn (bắt buộc ghi kèm mọi số fill-act):** (i) Turn alignment
  là fragile khi model có số turn khác gold — sample-level rule là
  fallback, không phải thay thế hoàn hảo; (ii) rule không phân biệt
  được "model điền từ default hợp lệ của task" với hallucination
  nếu default đó không nằm trong (a)–(c) — cần audit thủ công;
  (iii) rule dùng prover spans nên kế thừa giới hạn của prover
  (không xử lý paraphrase, không xử lý số đọc thành lời chưa chuẩn
  hóa). **Vì vậy: trước khi dùng fill-act rate cho bất kỳ verdict
  adopt/reject nào, phải audit thủ công 20 flagged cases (random
  trong flagged set) và báo cáo agreement rate; nếu agreement < 80%
  thì fill-act rate chỉ là exploratory, verdict liên quan tới nó là
  INCONCLUSIVE (không adopt/reject trên tiêu chí đó).**

### 8.3 Prerequisite rate (theo model prefix — như v1 §4.3.1, bổ sung)
- Prerequisite relations được tính trước từ gold trajectory: với mỗi
  gold write, tập các gold prefix reads/searches establish arguments
  của nó. `prereq_satisfied_rate` = số gold writes mà model prefix
  (calls model thực sự gọi trước write đó, trong run đó) chứa read/
  search tương đương (cùng tool + cùng identifying argument +
  succeeded) / tổng số gold writes applicable. Write khớp gold nhưng
  thiếu prerequisite = prerequisite-failed (diagnostic), kể cả khi
  proxy tính nó đúng. **Giới hạn:** "tương đương" cần rule matching
  (cùng tool + cùng entity id) — read trả về empty/noop không tính
  (chỉ succeeded); read đúng tool nhưng sai entity không tính.

### 8.4 Intent (proxy, không phải ground truth — nói thẳng)
- **Wrong-action rate:** write proposals mà tool ≠ gold write tool
  tại turn tương ứng (hoặc ở mức sample: model write tool mà gold
  không bao giờ write trong sample đó) / tổng write proposals.
- **Wrong-entity rate:** cùng tool với gold nhưng khác `*_id` /
  contact / phone argument / tổng write proposals cùng tool.
- **Ask confusion:** ask precision (model asks mà gold asks / tổng
  model asks) và ask recall (gold asks mà model asks / tổng gold
  asks) riêng biệt. Ask khi gold act là lỗi ngang hàng với write khi
  gold ask — ask không phải free pass.
- **Giới hạn bắt buộc:** intent không quan sát trực tiếp được. Các
  số trên là gold-consistency proxies: model có thể khớp gold calls
  với intent khác (trùng hợp) và có thể khác gold calls nhưng vẫn
  đúng intent (đường đi khác tới cùng state — state-hash sẽ bắt
  trường hợp này ở mức sample, nhưng per-proposal intent thì không).
  Không bao giờ viết "intent accuracy" không kèm từ "proxy".

### 8.5 Termination
- **Stop correctness:** model stop (empty submission) iff gold empty
  (per-sample). **Extra-call rate:** submitted calls vượt gold count,
  per-sample. **Repeat rate:** cùng call lặp lại trong một run (đụng
  max_repeats = 2 guard thì ghi riêng). **Ask-terminal compliance:**
  ask là action cuối cùng của model trong run (ask rồi lại write
  trong cùng run = vi phạm — gold ask luôn terminal: ask_only 48,
  ask_after 126, ask giữa 0). **Empty-stop:** stop action có mặt cho
  gold empty.

### 8.6 Guard metrics — breakdown theo type và situation (bắt buộc)
- **Categories (mỗi proposal một loại, loại trừ nhau):**
  correct_block, false_block, correct_pass, miss, out_of_scope,
  unadjudicated — định nghĩa như v1 §5.2. Adjudication dựa trên gold
  + checks §8.2–§8.4, không dựa trên verdict của chính guard.
- **Independent situation (ĐỊNH NGHĨA DUY NHẤT, áp dụng nhất quán):**
  một situation = **(sample_id, reference_value, reference_type)**.
  Cùng sample + cùng reference value + cùng type qua nhiều
  arms/versions/generations chỉ tính **1 lần**. Khác sample thì khác
  situation ngay cả khi cùng reference value (context khác nhau).
  Khác reference value trong cùng sample thì khác situation.
  Ví dụ: train_0004 light_set qua mọi arms/versions = 1 situation.
  Promotion bar "≥ 3 independent situations" đếm theo định nghĩa
  này (de-duplicated), không đếm raw proposals.
- **Báo cáo bắt buộc (mọi bảng guard):** tổng thể (tử số/mẫu số +
  Wilson CI) **VÀ** breakdown theo reference type:
  contact_id-roster, `*_id`-registry, phone_number-roster,
  phone_number-log, phone_number-spoken/text (residual).
  **Tổng G2 1.54% không được che phone-only 11/19 (57.9%).**
  Số gold-replay v1 để đối chứng: tổng 15/976 = 1.54%, Wilson
  [0.0093, 0.0252]; phone-only 11/19 = 57.9%, Wilson [0.3628, 0.7686]
  — khoảng tin cậy rộng vì n=19, nhưng point estimate đủ lớn để
  cấm mọi claim "guard an toàn tổng thể" mà không kèm breakdown.
- **False-block rate (deployment number)** = false_blocks /
  (false_blocks + correct_passes) trên adjudicated correct proposals,
  kèm Wilson CI + mẫu số. Block precision/recall chỉ trên adjudicated
  subset, có label. **Cấm** relabel 1 − false-block rate thành
  "precision" (v1 6-PR). Gold-replay rate và model-proposal rate là
  hai lượng khác nhau, không thay thế nhau.
- **KHÔNG hard-enforce; G1/G3 vẫn DROP.** Mọi bảng guard mang
  qualifier "conditional on the call's own ids" (existence ≠
  disambiguation). Phone_number branch vẫn shadow-only cho tới khi
  có text evidence (11 residual gold fires: số nói bằng chữ số,
  history text, message content).

### 8.7 Strata nhỏ — rule có nguyên tắc (thay gate 5pp máy móc)
- **Strata n < 30 (v1 test: ask_only 7, empty 13, ask_after 21):**
  chỉ báo cáo **descriptive** kèm tử số/mẫu số + Wilson CI. Không
  áp gate 5pp (1 mẫu ở ask_only n=7 = 14.3pp — gate 5pp sẽ reject
  vì 1 mẫu, vô nghĩa thống kê). Ví dụ Wilson: 0/7 → [0, 0.3543];
  1/7 → [0.0257, 0.5131]; 6/7 → [0.4869, 0.9743] — khoảng rộng tới
  mức không kết luận được gì chắc chắn từ một stratum đơn lẻ.
- **Ngoại lệ duy nhất — catastrophic floor:** stratum n<30 có
  **0 correct (0/n)** thì block adoption của checkpoint đó (không
  phải reject direction vĩnh viễn, mà là checkpoint đó không adopt
  được trên bằng chứng này). Lý do: 0/n là tín hiệu duy nhất đủ
  mạnh ở n nhỏ để hành động (dù CI vẫn rộng, việc không làm đúng
  một mẫu nào trong stratum đó là bằng chứng chống lại claim
  "không regress"). Mọi trường hợp khác ở n<30: descriptive only.
- **Strata n ≥ 30 (v1 test: normal 144):** gate regression > 5pp
  áp dụng bình thường, kèm CI.
- **Bắt buộc:** mọi stratum breakdown đều in n, tử số, mẫu số, CI —
  không bao giờ in mỗi tỉ lệ %.

## 9. Power analysis cho bar ≥ +3pp / CI loại 0 (n = 185, paired binary)

Công thức planning (xấp xỉ tốt khi diff nhỏ; CI vận hành vẫn là
paired bootstrap 10k resamples, seed 1337): với d = số discordant
pairs (một bên đúng, một bên sai), SE(diff) ≈ √d / n, half-width
95% ≈ 1.96 × SE. Net wins cần để CI loại 0 ≈ half-width × n.

| Discordant d | SE | 95% half-width | Net wins cần (> half-width × n) | +3pp = 5.55 net wins có loại 0 không? |
|---|---|---|---|---|
| 5 | 1.21pp | 2.37pp | > 4.4 | Có (sát nút) |
| 10 | 1.71pp | 3.35pp | > 6.2 | **Không** (5.55 < 6.2) |
| 20 | 2.42pp | 4.74pp | > 8.8 | Không |
| 30 | 2.96pp | 5.80pp | > 10.7 | Không |
| 50 | 3.82pp | 7.49pp | > 13.9 | Không |
| 80 | 4.83pp | 9.48pp | > 17.5 | Không |

**Kết luận (đọc kỹ):** +3pp ≈ 5.55 mẫu net trên n=185. Để một điểm
+3pp loại 0 khỏi CI cần **d < 8.0** (giải 1.96×√d/185 < 0.03).
Nghĩa là hai models phải đồng ý với nhau gần như mọi mẫu (chỉ ≤ 8
mẫu discordant) thì bar +3pp/CI mới đạt được. Trong thực tế, nếu
candidate thay đổi ~15% outcomes thì d ≈ 28 và half-width ≈ 5.6pp —
khi đó ngay cả gain thật +5pp cũng có thể không loại 0. **Hệ quả
đăng ký trước:**
- Bar +3pp/CI được giữ nguyên (không nới), nhưng verdict mặc định
  cho gain nhỏ là **INCONCLUSIVE**, và team phải chấp nhận rằng
  với n=185, nhiều candidate tốt-thật sẽ rơi vào INCONCLUSIVE.
  INCONCLUSIVE không phải thất bại của candidate — nó là thất bại
  của cỡ mẫu trong việc phân biệt.
- **Không được:** nới bar sau khi thấy kết quả; cộng val+test ad-hoc
  để tăng n (phá test lock); dùng proxy liên tục (continuous score)
  làm backdoor khi binary primary không đạt — trừ khi continuous
  metric đã được đăng ký trước làm secondary với hierarchy rõ ràng
  (primary binary quyết định adopt; secondary continuous chỉ hỗ trợ
  diễn giải, không đảo verdict).
- **Lựa chọn hợp lệ khi thiếu lực (phải chọn TRƯỚC KHI đọc test):**
  (a) chấp nhận INCONCLUSIVE + báo cáo đầy đủ (mặc định, khuyến
  nghị); (b) pre-register sequential rule với held-out (§7.4) làm
  confirmatory set với cùng bar (alpha cost công khai); (c) protocol
  tương lai với evaluation set lớn hơn + seed mới + families mới
  (không tái sử dụng test cũ, không tái sử dụng mẫu train cũ làm
  test mới). Lựa chọn (b)/(c) chỉ hợp lệ khi đăng ký trước test read.
- Tham chiếu unpaired: SE của một tỉ lệ tại p≈0.2, n=185 là 2.94pp;
  diff hai mẫu độc lập SE ≈ 4.16pp (half-width ≈ 8.2pp) — paired
  design đã tốt hơn unpaired, nhưng vẫn không đủ cho bar 3pp trừ
  khi discordance thấp. Đây là lý do paired design là bắt buộc,
  không phải tùy chọn.

## 10. Costs — tách riêng, chưa đo thì NOT_MEASURED

| Stage | Model runs (công thức, v1 n) | ASR passes | Training | Wall-clock |
|---|---|---|---|---|
| Stage 0 (benchmark consume + frozen comparator) | Benchmark: theo benchmark log (không cộng vào chain này). Comparator: 370 (test G1+A0) + val baseline nếu cần: 370 (val G1+A0) | 0 mới (dùng cache/transcript có sẵn; nếu cần transcribe lại thì đếm passes = số mẫu) | Không | NOT_MEASURED |
| Stage 1 (ASR ablation, val) | 185 (A1) | 185 (medium transcribe val current) | Không | NOT_MEASURED |
| Stage 2 (SFT pilot) | Val reads: đếm theo checkpoint (mỗi checkpoint = 2 cells × 185 = 370 runs nếu chạy đủ val; pilot slice nhỏ hơn thì đếm đúng số đã chạy) | 0 mới | Pilot slice (~100 traj, 1 epoch) + full pilot: wall-clock/memory NOT_MEASURED cho tới khi pilot đo | NOT_MEASURED |
| Stage 3 (DPO, nếu gate đạt) | Val reads: như Stage 2, đếm theo checkpoint | 0 mới | DPO runs: NOT_MEASURED | NOT_MEASURED |
| Stage 4 (test confirmation, mỗi family) | 370 (candidate G1+A0); baseline comparator tái sử dụng (0 mới); guard shadow 0 model runs | 0 mới | Không | NOT_MEASURED |
| Stage 5 (held-out, chỉ khi adopt) | 616 (308 × G1/A0) | 0 mới (dùng transcript đã có theo cell) | Không | NOT_MEASURED |
| **KHÔNG có tổng mặc định** | Chỉ cộng các stage thực sự chạy, với n v2 sau khi thay số | — | — | **Không suy wall-clock từ T4x2** |

## 11. Điểm luật còn mở + gợi ý wording câu hỏi BTC (CHO ĐIỀU PHỐI VIÊN SOẠN DRAFT CUỐI — KHÔNG GỬI)

Trạng thái: Q-L1/Q-L2/Q-L3/Q-D1/Q-L5 (+ Q-L4) **chưa từng gửi**.
Luồng C chỉ gợi ý wording; điều phối viên soạn draft cuối và user
duyệt trước khi gửi. Không liên hệ BTC trong luồng này.

- **Q-L2 (gating Stage 3 training cho submission; hỏi đầu tiên):**
  "If we fine-tune a model checkpoint that was released before
  26 October 2026, is the resulting derived checkpoint eligible for
  submission, or must the derived checkpoint itself have been
  released before that date? Does the answer differ for LoRA adapters
  versus fully fine-tuned weights, and for the ASR model versus the
  LLM?" (Lý do hỏi cả LoRA/full và ASR/LLM: v1 chỉ hỏi chung chung;
  đáp án có thể khác nhau theo loại weights.)
- **Q-L1 (param counting):** "Does the 6B system / 5B LLM limit count
  embedding parameters? Is the total counted as ASR + LLM + any
  router/embedder/verifier combined, or per-component? Should we
  report both total and non-embedding counts?" (Candidate phải pass
  cả hai cách tính cho tới khi có đáp án.)
- **Q-L3 (serving/decoding):** "Is vLLM permitted as the serving
  backend inside the offline Docker image? Is structured output /
  XGrammar (or any grammar-constrained decoding backend) permitted
  on the submission path, or must generation be unconstrained?"
- **Q-D1 (licence vs open-source):** "Which licences satisfy the
  open-source rule? In particular, is a research-only or
  non-commercial (e.g. CC BY-NC) licence eligible if the weights are
  publicly downloadable?"
- **Q-L5 (parser contract):** "Is the output parser contract (native
  tool calls plus the registered pseudo-call prefix) part of the
  official evaluation, or may a submission define its own output
  format as long as the tool calls execute correctly? If a submission
  uses a different serialization, how is it scored?"
- **Q-L4 (A30 measurement, chỉ hỏi nếu không có quyền truy cập A30):**
  "Is the 30-second-per-sample limit measured as wall-clock per
  sample (including ASR + LLM + guard) or amortised over the run?
  Is warm-up excluded?"
- **Thứ tự gửi gợi ý:** Q-L2 trước (gating training) → Q-L1/Q-L3
  trước khi chốt candidate → Q-D1/Q-L5 cùng đợt → Q-L4 chỉ khi cần.

## 12. Dependency notes cho điều phối viên (phải xử lý trước khi thực thi)

1. **Manifest v2 (luồng A):** thay mọi counts v1 (train/val/test,
   strata, gold val ask rate cho band §4) bằng counts v2; kiểm tra
   lại bảng power §9 nếu test n đổi đáng kể (công thức SE ≈ √d/n
   vẫn đúng, chỉ thay n). Nếu v2 đổi định nghĩa stratum hoặc seed
   thì protocol này cần amendment ghi rõ (không sửa lặng lẽ).
2. **Lineage history `audio_text` (luồng A):** cho tới khi xác lập,
   mọi attribution ASR mang caveat §3 (critique §5). Nếu lineage
   cho thấy recorded history text vốn là ASR output thì gap M3 phải
   diễn giải lại và cell G0 phải được định nghĩa lại.
3. **SFT prototype + contract runtime (luồng B):** protocol này giả
   định serialization/loss mask/masking assertions của luồng B là
   đúng; nếu luồng B chốt contract khác với a2e832b (provisional),
   thì Stage 2/3 phải re-baseline trên contract mới trước khi đo
   gain (cấm so sánh xuyên contract, giống cấm xuyên base).
4. **Zero-shot benchmark (đang chạy):** Stage 0 tiêu thụ kết quả
   của nó theo rule §2. Nếu benchmark không ghi sample set/cell/
   config đầy đủ thì kết quả đó không tiêu thụ được — chạy lại
   baseline theo Stage 0b thay vì import số.
5. **Sequential held-out rule (§7.4):** điều phối viên phải chọn
   (dùng / không dùng) TRƯỚC KHI đọc test và ghi vào log Stage 4.
   Mặc định: không dùng.
6. **Test read counting:** log mọi test read (family, ngày, cells,
   config hash, kết quả, verdict). Một read không ghi log vẫn là
   một read — "quên ghi" không reset số lần đọc.

## 13. Evidence ledger (luồng C, v2)

**Đã đọc / kiểm tra trong luồng này:**
- `overnight_capability_decision.md` (v1, toàn văn).
- `overnight_thread_b_methods.md` (v1, toàn văn).
- `overnight_thread_c_evaluation_protocol.md` (v1, toàn văn).
- `round10-fix-report-round3.md` (grep xác nhận guard numbers).
- Spot-check web (2026-10-29): Step-DPO arXiv 2406.18629v1 abstract
  (first-step + in-distribution finding xác nhận); SpeakRL arXiv
  2512.13159v1 Figure 1 (base 25.63 / SpeakRL 46.17 xác nhận; ablation
  SFT/DPO không xuất hiện trong snippet); Tool Zero arXiv 2511.01934
  (Live 61.1 → 78.6, Multi-Turn 9.6 → 7.8, xLAM cross-dataset
  inconsistency xác nhận; delta Tool-Zero-7B mâu thuẫn nhỏ, không
  trích).
- Tính toán CPU của luồng C: Wilson CI (15/976, 11/19, 0/7, 1/7,
  0/13, 6/7) và bảng power paired (§9). Không ghi file ngoài 2 file
  sở hữu.

**Không làm trong luồng này (giới hạn):**
- Không git; không sửa file của luồng A/B; không đọc file mới của
  luồng A/B trong khi chúng đang chạy; không đọc held-out rows (chỉ
  counts/lock rule từ v1); không mở lại repo bạn (404); không liên
  hệ BTC (chỉ gợi ý wording §11); không paid API; không Kaggle;
  không GPU/training/inference; không sửa simulator/scorer/inference/
  guard/baseline config; không thay benchmark zero-shot đang chạy.
- Không tuyên bố "ready to train" — đó là việc của điều phối viên.

**Unknowns / blockers (chuyển cho điều phối viên):**
- Manifest v2 counts (luồng A) + lineage history `audio_text`.
- Kết quả zero-shot benchmark (Stage 0 input).
- Organizer answers (Q-L1/Q-L2/Q-L3/Q-D1/Q-L5/Q-L4) — chưa gửi.
- Fill-act rule agreement rate (cần audit 20 cases trước khi dùng
  cho verdict — xem §8.2).
- A30 latency, train cost/memory: NOT_MEASURED.
- Official evaluator: ABSENT (mọi số đều là proxy).
