# Overnight capability decision — LifeMate: SFT or not, and what exactly to try first

**Quyết định (đọc trước): ƯU TIÊN = học quyết định qua trajectory đã
simulator-verify (D1-lite làm cold start) rồi preference training
trên biên act/ask/stop (D2 là hướng chính). DỰ PHÒNG = đo ASR theo
slot + grammar/guard với model đóng băng (D3 + safety layer), dùng
khi checkpoint derived bị cấm hoặc D1/D2 chạm falsifier. HOÃN =
RL from scratch, LLM verifier, tool shortlisting pilot riêng,
ASR fine-tune, đổi base model, đổi serialization sang native
tool-calling.** Chi tiết, điều kiện adopt/reject và falsifier ở
mục 5–7. Không có GPU run nào trong task này; mọi con số latency/
chi phí train chưa đo đều ghi BLOCKED hoặc ESTIMATE, không suy từ
T4.

## 0. Vì sao quyết định này, trong một đoạn

Lỗi thật không phải lỗi format: V10 sửa format thì proxy lên
0.125→0.1875 nhưng prerequisite tụt 5/21→4/21; V11 chỉ xác nhận
được channel hẹp; V13 INCONCLUSIVE vì fill-act — model tự điền
time thiếu từ context nên rule "ask khi thiếu" không bao giờ kịp
chạy. Ba luồng độc lập cùng kết luận: dữ liệu dev đủ sạch để dựng
SFT (Thread A), nhưng SFT trajectory thuần túy chỉ dạy hình thức
ask chứ không dạy biên quyết định (Thread B: AwN, SpeakRL, Tool
Zero), và protocol hiện tại không đủ sức phân biệt hai thứ đó nếu
chỉ nhìn proxy (Thread C). Vì vậy D1 chỉ là cold start rẻ để có
policy nói đúng format và đi đúng trajectory; D2 mới là nơi biên
act/ask/stop được học từ chính lỗi của model trên cùng prefix.
Nếu biên đó không học được bằng preference, hoặc BTC cấm derived
checkpoint, thì không cố train tiếp — chuyển sang đo ASR + siết
grammar/guard với model đóng băng.

## 1. Evidence ledger — những gì thực sự đã đọc

| Artifact | Identity | Dùng cho |
|---|---|---|
| `analysis/overnight_capability_audit/thread_a_data_audit.md` + `a_dev_audit.py`/`a_dev_audit.json` + `a_serialization_roundtrip.py` | Thread A, dev 1237 only, held-out dropped first, scan 0 held-out id | Mọi số liệu dev §2, data contract §4 |
| `research/lifemate/overnight_thread_b_methods.md` | Thread B, papers/code đọc 2026-10-29 (ledger trong file) | 3 hướng sâu §3, falsifier §6 |
| `research/lifemate/overnight_thread_c_evaluation_protocol.md` | Thread C, protocol 12 sections | Inner split, counting, GPU chain §5 |
| `analysis/overnight_capability_audit/inner_split_seed1337.json` + `generate_inner_split.py` | Main synthesis, seed 1337, population 1233 (xem §5.1) | Split dùng cho mọi thí nghiệm sau |
| `research/lifemate/round10-fix-report-round3.md` | Branch `round10-provenance-gates-fixes` @ `61d84390` | Guard state, phone residual, 1 positive độc lập |
| Main `219d7fec`; experiment branch worktree `~/workspace/zaic-branch-a2e832b` (agent `a2e832b`) | Baseline configs, runtime serialization | Serialization contract, frozen baseline |
| `lifemate/splits/train_dev_heldout.json` | Seed 42, dev 1237 / held-out 308 | Dev filter; held-out KHÔNG mở nội dung |

**Evidence classes dùng xuyên suốt:** `[REAL-RUN]` = model chạy
thật; `[GOLD-REPLAY]` = CPU replay gold qua ToolEnv;
`[CPU-AUDIT]` = đếm CPU trên dev; `[PRIOR-MEAS]` = đo trước đó,
trích lại không chạy lại; `[PROPOSAL]` = chưa chạy. Không số nào
được nâng class. Scorer hiện tại là engineering proxy
(state_hash-gated tool F1), KHÔNG phải official evaluator — mọi
"điểm" dưới đây đều là proxy cho tới khi có evaluator thật.

**Các kết luận cũ đã re-scope (không còn là sự thật chung):**
"prompt chạm trần" chỉ đúng cho channel hẹp E6-C và không cải
thiện prerequisite; "ASR không phải bottleneck" CHƯA chứng minh
(E0 dùng gold current + ASR history, không isolate ASR, và không
có gold history transcript); "fine-tune kém" CHƯA chứng minh cho
LifeMate (chưa có SFT nào chạy trong harness này; số của bạn anh
khác harness/split, repo 404 không audit được).

## 2. Phát hiện mới so với research trước (tổng hợp 3 luồng)

1. **Data construction KHÔNG phải blocker (A).** Gold replay sạch:
   2842/2843 calls succeed qua ToolEnv, 1236/1237 samples fully
   succeed; serialization round-trip tái tạo gold chính xác trên
   4 mẫu prototype (normal ×2, ask_only, empty). Dựng SFT là phép
   biến đổi xác định, không phải viết tay.
2. **Gold dạy 0 recovery usable (A).** Chỉ đúng 1 gold call dạng
   not_done, và nó chính là train_1696 đã quarantine (write fail
   replay). Mọi claim "dạy model tự sửa lỗi" từ dữ liệu này đều
   sai — recovery phải đến từ rollout tự sinh đã verify, hoặc
   không claim.
3. **Ids gần như 100% observation-derived (A).** entity_id 921:
   678 từ prior gold results, 242 từ history results, **1 từ
   nowhere**. SFT phải dạy read→copy-id, không bao giờ dạy ghi nhớ
   id. Time 330 thì 281 derived (relative/daypart/offset, không
   copy ISO); amount 109 thì 52 derived (số đọc thành lời,
   quantity×price). Nghĩa là SFT phải dạy derivation, không phải
   transcription.
4. **Ask luôn terminal trong gold (A).** ask_only 48, ask_after
   126, ask ở giữa 0. Last gold call: write 866, read 108, meta
   174, empty 89. SFT thiếu stop-after-read / ask-terminal /
   empty-stop sẽ học sai termination.
5. **Contacts vắng mặt 43.2% dev (A) + direct-dial hợp lệ.**
   534/1237 samples không cài contacts; 17 gold samples dial/SMS
   phone_number mà không có contacts.search trong gold. Pattern
   này mâu thuẫn trực tiếp với mọi rule "phone cần search trước"
   — và khớp residual phone của Round 3 (11 fires tồn dư là số
   nói/văn bản, gate hiện không có text evidence).
6. **Text gần unique nhưng behaviour thì không (A + C).**
   Normalized request texts: 1235 distinct/1237 (chỉ 1 nhóm 3 mẫu
   train_0061/0066/0168). Gold tool sequences: chỉ 582 distinct,
   816 samples chia sẻ sequence với mẫu khác. Random split đo
   "request mới, behaviour quen" — không đo behaviour chưa thấy.
   Vì vậy cần thêm slice `test_unseen_seq` báo cáo riêng (C), và
   D1 phải đo distinct-path diversity (B, bài học RFT/Tool Zero).
7. **Clean-vs-ASR gap ở CẢ hai slot (A).** Train gold history là
   text sạch; runtime `cmd_infer` transcribe cả current request
   lẫn history user turns thiếu `audio_text` bằng PhoWhisper-small
   greedy. Không có dev ASR-prediction cache local nào — đóng gap
   này cần một GPU production-ASR pass, chưa có.
8. **Prompt token budget không phải vấn đề (A, PRIOR-MEAS).**
   Base prompt mean 5372, max 9308; final max 9874; 0 mẫu vượt
   16384−512. Catalog chiếm mean 3899 tokens — đó là lý do loss
   mask phải mask catalog (xem §4), không phải lý do cắt context.
9. **Rarity có cấu trúc (A).** 63/147 tools <10 gold examples,
   26 tools <5, 2 tools chưa từng xuất hiện (`contacts.get`,
   `smart_home.scene_run`). SFT dạy skill (read-first, ask,
   derive), không dạy ghi nhớ tool hiếm — và không upweight/
   duplicate tool hiếm (id per-sample random; duplicate dạy
   memorization).
10. **Blocker lớn nhất không phải kỹ thuật mà là luật (B + C).**
    Derived-checkpoint eligibility (Q-L2) chưa có đáp án và quyết
    định D1+D2 có được submit hay không. Hỏi trước khi train —
    không phát hiện sau khi train xong.

## 3. So sánh các hướng đã chọn (tối đa 3 sâu + các hướng hoãn)

### D1 — Simulator-verified trajectory SFT (STaR / RFT, thang APIGen)
- **Lỗi xử lý:** prerequisite skipping (trực tiếp — trajectory
  không read-trước-write bị filter loại), format (trực tiếp),
  intent-wrong (một phần — state-hash là điều kiện cần, không đủ),
  fill-act (yếu — chỉ dạy hình thức ask, không phạt hành vi fill).
- **Nguồn:** STaR arXiv:2203.14465v2 (generate → rationalize khi
  có đáp án → chỉ fine-tune cái đúng → lặp); RFT arXiv:2308.01825v2
  (yếu tố quyết định là số reasoning path đúng KHÁC NHAU, không
  phải số copy); APIGen arXiv:2406.18518 (format → execution thật
  → semantic check); APIGen-MT arXiv:2504.03601v4 (blueprint đã
  verify → multi-turn trajectory, 5k trajectories).
- **Dữ liệu/compute:** chỉ inner_train 863 (§4); generation dùng
  lại đường Kaggle T4×2 đã có; filter CPU. Chi phí SFT 4B CHƯA ĐO
  — pilot slice ~100 trajectories, 1 epoch, báo wall-clock/memory
  trước; không suy latency A30 từ T4.
- **Điều kiện loại bỏ:** derived-checkpoint bị cấm; train/serve
  serialization lệch (byte-identical bắt buộc); pool verified suy
  biến thành copy gold (distinct-path ~1/sample); proxy tăng
  nhưng fill-act không đổi → D1 chỉ dạy hình thức, leo lên D2
  (không dừng ở D1).
- **Phần nào là suy luận:** việc "verified trajectory dạy được
  prerequisite" là suy luận từ cơ chế filter (chỉ trajectory
  read-first mới sống) — chưa có bằng chứng LifeMate cho tới khi
  pilot đo prerequisite rate.

### D2 — Act/ask/stop preference training trên chính lỗi của model (Step-DPO + Hammer-style abstention negatives) — HƯỚNG CHÍNH
- **Lỗi xử lý:** fill-act (**mục tiêu chính** — fill-act là
  rejected side của pair), prerequisite (rejected = write không
  read trước, chosen = read-first từ cùng prefix), intent-wrong
  (rejected = wrong-entity call), slot-gap (một phần, chỉ khi
  gold có).
- **Nguồn:** DPO arXiv:2305.18290 (policy/reference log-ratio,
  không reward model, không PPO); Step-DPO arXiv:2406.18629 (chỉ
  tối ưu **first erroneous step** từ cùng prefix đúng; pair tự
  sinh > pair human/GPT-4 vì OOD); Hammer arXiv:2410.04587v2
  (function masking + 7.5k irrelevance instance nhãn `[]` = không
  gọi gì — lấy ý tưởng, KHÔNG lấy checkpoint 7.61B vì vượt cap
  5B); AwN arXiv:2409.00557v4 (next-token training mặc định là
  fill — **chỉ đọc abstract + fragment, chưa full-text, ghi rõ**);
  SpeakRL arXiv:2512.13159v1 §§1–3 (GRPO + format + LaaJ reward:
  base 25.63 / SFT 28.78 / DPO 45.73 / SpeakRL 46.17 trên MultiWOZ
  2.4 — **không chuyển số này thành kỳ vọng LifeMate**; setup
  của họ dùng Claude simulator + LLM-judge, cả hai đều bị cấm ở
  đây, chỉ lấy cơ chế + bài học đo turn-count/ask-rate); When2Call
  2025 (taxonomy call/answer/ask/abstain — **bản gốc chưa đọc**,
  lấy taxonomy qua secondary).
- **Dữ liệu:** pair từ cùng prefix — chosen = ask turn /
  read-first / gold call đã verify, rejected = chính trace lỗi của
  model (V10/V11/V13 + rollout mới), label theo trace/version/arm.
  Bắt buộc cân bằng ask/act (mỗi ask-chosen pair cần act-chosen
  pair nơi gold act) nếu không policy sụp thành ask-mọi-thứ; giám
  sát ask-rate như metric hạng nhất.
- **Compute:** DPO cần policy + 1 reference copy (2×4B + optimizer;
  LoRA-DPO giảm mạnh) — CHƯA ĐO, pilot vài trăm pair trước.
  Inference cost không đổi. Reference = checkpoint D1 (DPO-after-
  SFT, không DPO-from-base). β và tỉ lệ ask/act là hyperparameter
  cần sweep, không trình bày như đã tune.
- **Điều kiện loại bỏ:** derived-checkpoint bị cấm; không đủ pair
  first-divergent-step (Step-DPO suy biến thành DPO toàn trajectory,
  mất lợi thế credit assignment); ask-rate phình mà proxy không
  tăng (sai balance); DPO phá format (β quá thấp / reference sai
  → dừng).
- **Bằng chứng phản biện ràng buộc D2:** Tool Zero
  arXiv:2511.01934v1 §§1–3 — SFT trên ToolACE: BFCL-Live 61.1→78.6
  nhưng Non-Live/Multi-Turn đứng yên hoặc regress (9.6→7.8);
  xLAM-7B-fc nhất BFCL nhưng tệ nhất trung bình cross-dataset.
  Hệ quả: D1/D2 phải dùng multi-turn trajectory, đo distinct-path
  diversity, và validate trên slice template-chưa-thấy; gain
  inner-dev không sống qua slice đó thì đó là memorization, reject.

### D3 — ASR decoding-side adaptation + đo lỗi theo slot (đo trước, không đổi model)
- **Lỗi xử lý:** entity, số đọc thành lời, phủ định, điều kiện
  (chính); fill-act chỉ gián tiếp (ASR làm mất slot → model fill,
  nhưng E5 chứng minh fill-act xảy ra cả với gold transcript nên
  ASR không fix triệt để E1).
- **Nguồn:** PhoWhisper ICLR 2024 Tiny Paper Table 2 (small 244M
  VIVOS 6.33 / VLSP-1 15.93; medium 769M 4.97 / 14.12; large 1.55B
  4.67 / 13.75; train 843.79h tiếng Việt) — benchmark chung,
  **không phải WER trên audio LifeMate**; N-best rescoring
  (Futami et al. arXiv:2110.01857; Zhang et al. 2024 — sub-word
  NNLM rescoring tốt nhất cho entity theo báo cáo). Dạng rẻ nhất
  có thể chuyển giao là **lexicon-constrained rescoring** (acoustic
  score + bonus từ lexicon của state hợp lệ lúc runtime + chuẩn
  hóa số đọc thành lời), không phải neural rescorer mới (tốn
  param/latency chưa đo).
- **Dữ liệu:** audio dev + gold transcript của current turn
  (1237); gold transcript của history turn CHƯA được xác lập
  (history `audio_text` là ASR output theo thiết kế E0) nên ASR
  fine-tune cho history hiện không có data verify.
- **Điều kiện loại bỏ:** attribution cho thấy lỗi ASR hiếm khi
  đổi quyết định của LLM (decision-stable) → dừng toàn bộ việc
  ASR; `initial_prompt`/hotwords overcorrect → thu hẹp vocab hoặc
  bỏ knob (`hotwords` có trong đúng version faster-whisper đang
  pin hay không là CHƯA VERIFY); biến thể "address book tại thời
  điểm ASR" đòi sửa pipeline (ASR chạy trước khi load state) →
  hoãn.
- **Falsifier:** pilot ASR giảm slot-error nhưng proxy (với gold
  history để cô lập current-turn ASR) không nhúc nhích →
  current-turn ASR không phải bottleneck, dồn nguồn sang D1/D2.

### Hoãn (lý do 1 dòng mỗi cái)
- **Pure RL from scratch (Tool Zero GG-GRPO):** bằng chứng phản
  biện SFT mạnh nhất, nhưng cần infra rollout+reward chưa có, và
  kết quả 7B/32B không chuyển sang budget 4B — hoãn tới khi có
  D1+D2 làm cold start.
- **LLM verifier / Reflexion:** Round 9 đã loại verifier dưới
  6B/30s nếu không đếm param/latency; thêm turn tốn latency chưa
  đo.
- **Tool shortlisting/retrieval:** adjunct hợp lý cho intent-wrong
  và áp lực context, nhưng chưa verify primary source trong thread
  này và đổi prompt contract sẽ làm nhiễu so sánh D1/D2 — pilot
  riêng sau.
- **ASR fine-tune:** hoãn hẳn — cần pair audio–gold đã verify
  (chỉ current turn, hẹp) + cùng câu hỏi derived-checkpoint.
- **ASR model swap small→medium:** KHÔNG litigate lại — đã là combo
  "try now" từ research chọn LLM/ASR trước (4.769B, verified
  budget); D3 đo nó như một cell (A1), không phải hướng mới.
- **Đổi base model (Qwen3.5-4B) / đổi serialization sang native
  tool-calling:** làm nhiễu attribution (không biết gain từ SFT
  hay từ base/format) + budget chặt hơn (5.469B) + re-check
  licence/date — hoãn tới sau khi D1/D2 có kết quả trên base hiện
  tại.
- **Dynamic grammar / constrained decoding:** adjunct tốt cho
  format/slot-gap (Round 9 đã nghiên cứu) nhưng không dạy quyết
  định, và quyền dùng XGrammar trên submission path vẫn UNVERIFIED
  — giữ làm safety layer, không phải hướng học.

## 4. Data / training contract (D1 + D2)

### 4.1 Base model / revision được cân nhắc
- **SFT base: Qwen3-4B-Instruct-2507 rev `cdbee75`** (đúng LLM của
  baseline hiện tại) + PhoWhisper-small cho các cell G1/A0; ASR
  medium (0.769B) chỉ xuất hiện như cell A1, không phải base mới.
  Tổng 4.244B (small) / 4.769B (medium) — đều dưới cap 6B/5B.
  **Không chọn Qwen3.5-4B** (lý do §3, hoãn).
- **DPO reference = checkpoint D1** (DPO-after-SFT). Không DPO
  trực tiếp từ base (mất format/trajectory prior).
- **LoRA vs full FT: CHƯA QUYẾT.** Pilot slice đo cả hai trên
  đúng setup Kaggle (wall-clock, memory, proxy delta) rồi chọn;
  không trình bày con số nào như đã tune.

### 4.2 Dataset construction + split (đã chốt, file kèm theo)
- **Split (Thread C + amendment của main):** quarantine 4 mẫu của
  Thread A (train_1696, train_1005, train_1033, train_1319 — cả 4
  đều kind normal) bị loại TRƯỚC KHI split → population 1233.
  Seed 1337 (khác seed 42 gốc), cell-stratified theo
  kind × history-presence × read-before-write class, nhóm
  near-duplicate (train_0061/0066/0168) whole về train:
  **inner_train 863 / inner_val 185 / inner_test 185**.
  Inner_train: normal 679, ask_after 88, empty 62, ask_only 34;
  history 567; multi-call 588. Inner_test: normal 144, ask_after
  21, empty 13, ask_only 7 (ask_only n=7 → 1 swing = 14.3pp, đọc
  stratum gate kèm n).
  File: `analysis/overnight_capability_audit/inner_split_seed1337.json`
  (manifest gồm counts, rates, overlap checks — tất cả pass:
  partition disjoint, audio-path disjoint, 0 held-out id,
  0 quarantine id; history/rbw rates mỗi part trong ±2pp của
  population). Generator:
  `analysis/overnight_capability_audit/generate_inner_split.py`.
- **Train chỉ trên inner_train 863.** Inner_val 185 chỉ để iterate.
  Inner_test 185: mỗi direction family tối đa 2 reads (1 pilot +
  1 final, đều ghi log); read thêm làm burn decision-test.
  Held-out 308: khóa hoàn toàn cho tới post-freeze run duy nhất
  (§5.4).
- **Construction (per sample, deterministic transform):** render
  base prompt bằng đúng worktree `build_base_prompt` (byte-identical
  với runtime: single user message qua Qwen chat template, catalog
  đã filter theo installed apps + `sys.ask_missing_info`, history
  render đúng kể cả `results={repr}`); đi gold calls làm targets;
  observations = real `ToolEnv` results (full result JSON); KHÔNG
  hand-fix trajectory nào — simulator-verify mọi trajectory (call
  list identical, tất cả succeed theo predicate ok True AND done
  ≠ False) hoặc drop, có log.
- **Floors (giữ tất cả minority, không downsample):** ask_only 34,
  empty 62, ask_after 88, multi-call 588, history 567; duplicate→ask:
  giữ mọi case đã verify qua search results (adjacent count 40 là
  lower bound, builder phải verify bằng results chứ không đếm
  adjacency); direct-dial: giữ mọi case (pattern hợp lệ, §2.5).
  Không upweight/duplicate tool hiếm.
- **Quarantine (loại khỏi train/val/test):** train_1696 (sole
  replay-failing write), train_1005/1033/1319 (contact_ids chỉ từ
  message history — dạy đúng pattern mà Round 2/3 đã đóng).
  Near-duplicate group không loại vì sai, chỉ bắt buộc cùng phía
  split (đã về train).

### 4.3 Serialization / loss mask
- **Serialization pinned:** đúng runtime a2e832b — một user message
  plain-text prompt; một JSON object mỗi turn (`{"name", "arguments"}`
  hoặc `{"stop": true}`); observation sau mỗi call (kể cả validation
  failure); loop guard (repeat ≥2 → replan once → stop) là hành vi
  inference, không phải target. Grounding adapter giữ ON ở inference
  như safety net; targets = gold calls đã grounded (id thật, int
  amount, ISO time) — KHÔNG train model emit dạng chưa grounded
  (`contact_name`, số đọc thành lời) rồi trông chờ adapter sửa.
- **Loss mask [PROPOSAL, chưa chạy]:** chỉ train trên assistant-turn
  tokens (call JSONs + final stop); mask prompt/catalog/history/
  observations (catalog mean ~3.9k tokens — mask nó là bắt buộc
  nếu không loss bị catalog nhấn chìm). Fuzzy args train bình
  thường nhưng evaluate ở token-F1 > 0.6, không exact-match.
- **Truncation:** sequences vừa budget (final max 9874 < 16384);
  nếu sequence nào vượt, DROP + log, không bao giờ truncate lặng
  lẽ giữa trajectory. Không packing (phá cấu trúc trajectory).

### 4.4 Positive / negative coverage
- **Positives (D1):** mọi gold class trong inner_train (§4.2),
  cộng self-generated rollouts (temperature > 0) qua cùng filter
  (format valid + mọi call succeed + final state_hash == gold).
  Distinct-path diversity là metric bắt buộc của pool (RFT/Tool
  Zero): nếu pool suy biến thành copy gold thì D1 không có gì để
  học ngoài memorization.
- **Negatives (D2):** chỉ từ nguồn đã verify — (a) chính trace lỗi
  của model (V10/V11/V13 proposals + rollout mới), label theo
  trace/version/arm; (b) synthetic negatives chỉ khi simulator
  verify (final state khác gold hoặc validation reject), luôn
  label synthetic. Pair construction: cùng prefix, first divergent
  step (Step-DPO); chosen = ask turn / read-first / gold call đã
  verify; rejected = fill-act / write-không-read-trước /
  wrong-entity call từ cùng prefix. Cân bằng ask/act bắt buộc;
  ask-rate là metric hạng nhất.
- **Không có:** recovery positives/negatives từ gold (0 usable,
  §2.2) — capability recovery KHÔNG được claim từ D1/D2; nếu cần,
  nó là rollout-verified work riêng sau này, không phải extension
  lặng lẽ của D1.

### 4.5 Hyperparameter — cần thí nghiệm, KHÔNG trình bày như đã tune
LoRA r/alpha vs full FT; LR; epochs (bắt đầu 1 ở pilot slice);
batch/grad-accum (phụ thuộc hardware, pilot đo); DPO β; tỉ lệ
ask/act balance; max_len (16384, drop-and-log khi vượt); rollout
temperature + số rollout/sample cho D1 pool; Step-DPO pair budget
(vài trăm pair pilot trước). Mọi lựa chọn cuối đều phải ghi kèm
inner_val delta đã đo, không ghi kèm lý thuyết.

## 5. Evaluation contract + chuỗi thí nghiệm GPU tối thiểu (cho Codex)

### 5.1 Counting units và báo cáo bắt buộc
- Unit chính: **sample** (state-hash exact rate, proxy, ask
  correctness). Proposal/argument báo cáo cả per-proposal VÀ
  per-sample với cluster bootstrap; không pool versions/arms/
  transcript cells/val+test. So sánh paired trên cùng inner_test
  185 (paired bootstrap 95% CI, 10k resamples, seed 1337 +
  bảng McNemar discordant); CI chứa 0 thì không phải improvement.
- Gold-call match KHÔNG đủ: mỗi decision report phải kèm
  (1) prerequisite satisfaction tại model prefix (gold-prefix reads
  vs prefix thật của model — check mà V10 đã fail trong khi proxy
  tăng); (2) ask confusion table + ask precision/recall (ask khi
  gold act là lỗi, không phải free pass); (3) 4-number decomposition
  — state-hash exact rate, gated proxy, raw F1, write-only F1
  (phơi read-dilution gaming: write-only 1.0, +1 read 0.6667,
  +2 reads 0.5); (4) termination/repeat rates; (5) rejected-call
  rate và ok-True/done-False vacuous-success rate (rejected calls
  đứng trong trace và dilute F1).
- Guard: paired guard on/off trên cùng saved traces (shadow log
  decisions, veto re-score — không so model A + guard vs model B
  không guard). Categories: correct_block, false_block,
  correct_pass, miss, out_of_scope, unadjudicated (mỗi loại
  per-proposal và per-sample; tình huống lặp de-duplicate —
  train_0004 tính 1 lần). Deployment number = **false-block rate**
  = false_blocks / (false_blocks + correct_passes) kèm Wilson CI;
  cấm relabel 1 − false-block rate thành "precision" (Round 3,
  6-PR). Gold-replay rate (1.54%) và model-proposal rate là hai
  lượng khác nhau, không thay thế nhau. Mọi bảng guard mang
  qualifier "conditional on the call's own ids" (existence ≠
  disambiguation). Phone_number branch vẫn shadow-only (11 residual
  gold fires).

### 5.2 Transcript cells (mọi label phải kèm cell)
- G0: gold/gold (gold current + gold history — cell tham chiếu,
  không phải thiết kế E0). G1: gold current + ASR history (= thiết
  kế E0). A0: ASR small (baseline). A1: ASR medium (4.769B).
  Candidate cells C-* luôn match với G1/A0. Candidate ASR benefit
  = (C_ASR − C_gold) − (A0 − G0). Attribution: ASR-attributable =
  G0 đúng + A0 sai; LLM = cả hai sai; ASR-luck = G0 sai + A0 đúng
  (đếm riêng, không net). ASR adoption cần entity-span improvement
  + không tăng ASR-attributable failures; hotwords/initial_prompt
  phải báo overcorrection rate.

### 5.3 Constraints checklist (UNVERIFIED = hỏi BTC, xem §7)
C1 param counting — pass dưới cấu hình nhưng rule UNVERIFIED
(Q-L1: embeddings có tính? ASR+LLM+verifier tính chung? — candidate
phải pass dưới CẢ total và non-embedding counting). C2 checkpoint
date — baseline OK, nhưng Q-L2 (fine-tune của base pre-cutoff có
đủ điều kiện, hay derived checkpoint tự nó phải predate
2026-10-26?) quyết định SFT có submit được không — hỏi trước
Stage 3. C3 context ≤ 16384 — audit được qua token-count (max/p99).
C4 deterministic decoding — temp 0.0/seed 42 đã cấu hình, Q-L3 hỏi
vLLM/XGrammar permission (chưa từng gửi). C5 offline Docker —
test được với network disabled. C6 ≤ 30s/sample trên 1× A30 —
**BLOCKED, chưa có measurement nào** — chỉ đo p50/p95/max trên
A30. C7 licence vs "open-source" — UNVERIFIED (Q-D1, xLAM
research-only/CC BY-NC signal). C8 parser contract — Q-L5.
Budget chain tính bằng runs × samples, không tính bằng giờ
(wall-clock BLOCKED).

### 5.4 GPU chain tối thiểu (Codex triển khai sau; main không chạy GPU)
- **Stage 0 — freeze + baselines.** Freeze config/code/data/split
  (inner_split_seed1337). Chạy baseline trên inner_test 185 ở
  G0/G1/A0 (555 runs) + gold-replay sanity: hash exact rate phải
  là 1.0, nếu không thì DỪNG — đó là scorer bug, không phải kết
  quả model.
- **Stage 1 — ASR ablation (D3 đo lường).** A1 vs A0 trên inner_test
  (185 runs). Branch: chỉ đi sâu ASR nếu ASR-attributable failures
  ≥ 10% inner_test VÀ tập trung entity/negation — nếu không, D3
  dừng ở đo lường.
- **Stage 2 — guard shadow.** Shadow guard trên traces đã lưu của
  Stage 0 (0 model runs). Veto bị reject cho một reference type
  nếu model-proposal false-block > 5%; nếu unadjudicated > 10%
  thì sửa adjudication trước.
- **Stage 3 — candidate pilot (D1-lite → D2).** Train CHỈ trên
  inner_train; iterate CHỈ trên inner_val. Pilot slice trước
  (~100 trajectories, 1 epoch; vài trăm DPO pairs) để đo
  wall-clock/memory và chọn LoRA-vs-full. Stop rules (ghi log,
  không sửa hyperparameter lặng lẽ): 2 lần validation degrade liên
  tiếp; stratum regression > 5pp (đọc kèm n — ask_only test n=7);
  constraint breach; divergence.
- **Stage 4 — decision read (inner_test, tối đa 2 reads cho mỗi
  direction family: 1 pilot + 1 final).** Chạy candidate ở G1 và
  A0 (740 runs cho 2 candidates × 2 cells × 185). **Adopt khi và
  chỉ khi TẤT CẢ:** ≥ +3pp với paired CI loại 0 ở CẢ G1 và A0;
  không stratum regression > 5pp (kèm n); guard shadow conditions
  đạt (model-proposal false-block ≤ 2%, Wilson upper ≤ 5%,
  correct blocks trên ≥ 3 independent situations — hiện tại là 1,
  CHƯA ĐẠT); constraints thỏa dưới cả hai cách tính param.
  Một điều kiện fail → reject, kèm paired table. Ghi rõ: D1 đơn
  độc adopt chỉ khi fill-act VÀ prerequisite cùng cải thiện (nếu
  chỉ proxy tăng thì đó là form learning, chuyển sang D2 chứ
  không adopt D1).
- **Stage 5 — post-freeze held-out run duy nhất.** 308 × 2 cells
  (G1/A0) = 616 runs, báo cáo as-is, không tuning sau đó. Mâu
  thuẫn thì báo cáo, không sửa — mở lại development cần split/seed
  mới và burn decision-test cũ.
- **Tổng model runs (không tính training):** 555 + 185 + 740 + 616
  = 2096 runs. Wall-clock BLOCKED cho tới khi có đo A30.
  (Số của Thread C là 558/744 trên test 186 cũ; đã rescale về
  test 185 sau amendment quarantine-before-split.)

## 6. Tự phản biện — những gì có thể khiến quyết định này sai

1. **863 mẫu train là nhỏ.** Rủi ro memorization (Tool Zero) là
   thật: gain inner-dev có thể không sống qua slice
   `test_unseen_seq`. Mitigation: distinct-path diversity, slice
   unseen-sequence báo cáo riêng, decision metrics (fill-act,
   prerequisite, ask-rate) chứ không chỉ proxy. Nếu gain biến mất
   trên slice đó → reject claim generalization của SFT.
2. **DPO trên 4B có thể không ổn định.** β thấp phá format, balance
   sai phình ask-rate. Mitigation: pilot vài trăm pair, stop rules
   §5.4, reference = D1 (không DPO-from-base).
3. **Gap clean-vs-ASR có thể nuốt gain.** D1/D2 train trên gold text
   nhưng test ở A0 là ASR text (cả current lẫn history). Mitigation:
   adopt đòi gain ở CẢ G1 và A0; nếu chỉ G1 tăng mà A0 đứng yên thì
   đó là bằng chứng gap đang nuốt gain — lúc đó ưu tiên chuyển sang
   ASR-text training data (GPU prerequisite: production-ASR pass
   trên train audio) trước khi train tiếp.
4. **Proxy không phải evaluator thật.** Mọi adopt criteria đều
   proxy-gated. Nếu evaluator thật xuất hiện và mâu thuẫn proxy
   (ví dụ read policy, ask policy khác), adopt criteria phải đánh
   giá lại — không tự động chuyển kết quả proxy thành kết quả
   submission.
5. **Thứ tự D1→D2 có thể đảo ngược trong một trường hợp:** nếu pilot
   D1 cho thấy format/prerequisite đã tốt nhưng fill-act đứng yên
   VÀ pair first-divergent-step đã đủ từ trace cũ (V10/V11/V13) thì
   có thể thử D2-lite trực tiếp trên base + guard mà không cần D1
   full — nhưng vẫn cần D1 checkpoint làm reference cho DPO đầy đủ;
   trường hợp này ghi thành branch có điều kiện, không phải plan B
   mặc định.

## 7. Bằng chứng nào sẽ đổi quyết định (decision-flip triggers)

- **Q-L2 = derived checkpoint bị cấm** → priority chết ngay dù
  proxy tăng → chuyển sang backup (D3 + grammar/guard, model đóng
  băng). Đây là trigger mạnh nhất, và là lý do câu hỏi phải gửi
  trước Stage 3.
- **D1: proxy tăng nhưng fill-act + prerequisite đứng yên** →
  D1 chỉ dạy hình thức → không adopt D1, dồn sang D2 + inference-side.
- **D2: fill-act không giảm trong khi ask-rate trong band và proxy
  không regress** → biên quyết định không phải territory của
  learned-policy → chuyển sang prompt/guard/grammar.
- **D2: ask-rate phình mà proxy không tăng** → balance sai, dừng
  và re-balance, không tăng data mù.
- **D3: ASR-attributable ≥ 10% + entity/negation-concentrated +
  pilot ASR moves proxy trong cell cô lập** → promote ASR work lên
  trước D2.
- **Unseen-sequence slice: gain biến mất** → reject SFT
  generalization claim, dù inner_test tăng.
- **Official evaluator xuất hiện và mâu thuẫn proxy** → re-evaluate
  toàn bộ adopt criteria trước khi claim submission.

## 8. Blocker và phần chưa biết (không lấp bằng khẳng định)

1. **Organizer questions — CHƯA TỪNG GỬI, cần user duyệt trước khi
   gửi (không tự liên hệ BTC):** Q-L1 param counting (embeddings?
   ASR+LLM+verifier chung?); Q-L2 derived-checkpoint eligibility
   (gating Stage 3); Q-L3 vLLM/XGrammar permission; Q-D1 licence vs
   "open-source"; Q-L5 parser contract. Gửi sớm — Q-L2 trước Stage 3,
   Q-L1/Q-L3 trước khi chốt candidate.
2. **Friend SFT: NOT AUDITED.** Repo 404, audit dừng theo lệnh user;
   không có local SFT script/config/manifest/checkpoint nào trong
   workspace. Không số nào của bạn anh (WER 29.4%→9.6%, public
   46.68) được dùng hay phán xét ở đây.
3. **Chi phí/memory/wall-clock train 4B: CHƯA ĐO** (pilot đo trước).
4. **Latency A30 mọi cấu hình: BLOCKED** (không suy từ T4x2).
5. **WER trên audio LifeMate + attribution lỗi ASR theo slot:
   CHƯA ĐO** (D3 Stage 1 đo).
6. **Official evaluator: ABSENT** — mọi adopt criteria đều proxy-gated.
7. **`hotwords` trong đúng faster-whisper version đang pin:
   CHƯA VERIFY.** Licence APIGen-MT-5k; licence file của đúng
   revision Qwen3-4B-Instruct-2507 cho derived submission; full-text
   AwN; bản gốc When2Call; primary source tool retrieval — tất cả
   ghi rõ trong ledger của Thread B, không lấp.
8. **History transcripts là ASR output với error chưa đo** (không
   có gold history) — giới hạn đứng trên mọi kết quả G1/A0.
9. **Decision-test strata nhỏ:** ask_only n=7, empty n=13 trong
   inner_test — stratum gate > 5pp phải đọc kèm n.

## 9. Commits, files và lệnh tái lập

- Base nội dung audit: main `219d7fec`; Round 3 branch
  `round10-provenance-gates-fixes` @ `61d84390`; experiment branch
  worktree `~/workspace/zaic-branch-a2e832b` (agent `a2e832b`).
  Lưu ý: main remote hiện tại đã nhích lên `1caa885a`
  (219d7fec + một commit test-push TEST_PUSH.md không liên quan
  tới audit) — nhánh mới dưới đây tạo từ main @ `1caa885a`.
- Nhánh push của task này: `overnight-capability-audit` (từ main @
  `1caa885a`, KHÔNG merge main). Push set: 3 thread reports + A scripts/jsons
  (trừ `a_roundtrip.json` — local-only vì chứa observation text
  của 4 dev samples, tái tạo được bằng script) + generator +
  inner split manifest + báo cáo này. Verify sau push bằng
  list_commits + blob-SHA byte-compare như các round trước.
- Files:
  - `analysis/overnight_capability_audit/thread_a_data_audit.md`
  - `analysis/overnight_capability_audit/a_dev_audit.py`
  - `analysis/overnight_capability_audit/a_dev_audit.json`
  - `analysis/overnight_capability_audit/a_serialization_roundtrip.py`
  - `analysis/overnight_capability_audit/generate_inner_split.py`
  - `analysis/overnight_capability_audit/inner_split_seed1337.json`
  - `research/lifemate/overnight_thread_b_methods.md`
  - `research/lifemate/overnight_thread_c_evaluation_protocol.md`
  - `research/lifemate/overnight_capability_decision.md` (báo cáo này)
- Tái lập split (CPU, không held-out, không GPU):
  ```
  python3 analysis/overnight_capability_audit/generate_inner_split.py
  # expect: counts 863/185/185, ALL_CHECKS_PASS: True
  ```
- Tái lập audit A (CPU):
  ```
  python3 analysis/overnight_capability_audit/a_dev_audit.py
  python3 analysis/overnight_capability_audit/a_serialization_roundtrip.py
  ```
