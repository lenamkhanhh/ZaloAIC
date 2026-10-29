# Thread A — Split revision: quarantine review, manifest v2, history-transcript lineage

**Phạm vi:** chỉ split và hợp đồng dữ liệu. Không sửa simulator,
scorer, inference, guard, baseline config. Không git (không
checkout/reset/merge/push/commit). Không mở nội dung held-out 308
(chỉ dùng split map để khẳng định v2 ids đều thuộc dev). Không đọc
file mới của luồng B/C trong khi chạy. Mọi số liệu dưới đây là
dev-only, CPU, replay qua ToolEnv.

**Kết luận trước (chi tiết + bằng chứng ở dưới):**
- train_1005/1033/1319: **trả lại evaluation pool** (v1 loại khỏi
  mọi split là quá rộng) và **giữ trong training với flag**
  `contact_source=message_history` — contact_id truy được tới
  structured history result, replay thành công, intent khớp.
  Guard G2 không hỗ trợ không chứng minh label sai.
- train_1696: **giữ trong evaluation với cờ anomaly, báo cáo
  metric tách riêng**; **loại khỏi training** vì lý do cơ học độc
  lập (trajectory chứa call fail replay nên không qua được D1
  all-succeed filter).
- Manifest v2: full dev 1237, seed 1337, 866/185/186, tách membership
  khỏi training eligibility. Audio dev **content-disjoint** theo
  sha256 (4033 paths, 0 collision). Tool-sequence overlap val
  57.3% / test 61.8% là expected, không giấu.
- Mâu thuẫn history transcript được giải quyết: train history
  **có** field `audio_text` (2796/2796 turns), nhưng provenance của
  field đó là **UNVERIFIED** — không được gọi là "gold sạch".
  Thuật ngữ đúng: **dataset-provided transcript**.
- **Không tuyên bố "ready to train"** — đó là việc của điều phối
  viên sau tích hợp.

## 1. Xem lại quarantine bằng bằng chứng

### 1.1 Phương pháp
- Replay gold calls qua `ToolEnv("train", id)` (diagnostic accessor
  `get_state()` chỉ dùng để kiểm tra, không phải agent input).
  Check đúng theo `cmd_replay_gold` trong a2e832b `run.py`:
  changed-apps sau replay phải bằng `label.final_state` (chú ý:
  `final_state` chỉ chứa apps BỊ ĐỔI, không phải full state — so
  sánh full state với nó sẽ sai).
- Phân loại nguồn contact_id: đi history + gold prefix theo thứ tự,
  nguồn đầu tiên chứa id đó (roster = `contacts.search` result;
  message = `sms.read_recent`/`phone.recent_calls` result;
  other = result khác; prior_arg = arg của call trước; nowhere).
  History `tool_results` dạng repr-string (412 turns) được parse
  bằng `ast.literal_eval` trước khi walk.
- **Lỗi scan của chính luồng này, đã sửa và công khai:** bản scan
  đầu bỏ qua việc feed result của gold calls không mang
  `contact_id` (do `if not cid: continue` đặt trước feed), nên
  gold-prefix `contacts.search` bị miss và báo sai 87 nowhere.
  Sau khi sửa (luôn feed mọi result theo thứ tự), kết quả đổi
  hoàn toàn (mục 1.4). Mọi con số dưới đây là từ bản scan đã sửa,
  đã verify lại bằng ví dụ cụ thể (train_0003: search 'Cô giáo
  Mai' -> c_06 rồi mới transfer).

### 1.2 Từng mẫu: bằng chứng và quyết định

| Mẫu | Gold contact call | Nguồn contact_id (tool + field) | Replay | Changed-apps == final_state | Quyết định |
|---|---|---|---|---|---|
| train_1005 | sms.send c_778 ("nhắn lại mạ") | History `sms.read_recent` result, message `contact_id` = c_778 (tin nhắn từ "mạ", nội dung vé Đà Nẵng đuôi 95) | ok True, done None, khớp gold | True (changed: sms) | Eval: INCLUDE. Train: INCLUDE, flag message_history |
| train_1033 | phone.call c_217 ("gọi lại cho Vy") | History `phone.recent_calls` result, call record nested `contact.id` = c_217, name Vy (cuộc gọi nhỡ) | ok True, done None, khớp gold | True (changed: phone, shopping_list) | Eval: INCLUDE. Train: INCLUDE, flag message_history |
| train_1319 | ewallet.transfer c_9526, 200000 ("chuyển ví hoàn lại cho Emily Carter") | History `sms.read_recent` result, message `contact_id` = c_9526 (tin nhắn Emily Carter) | ok True, done None, khớp gold | True (changed: ewallet, smart_home) | Eval: INCLUDE. Train: INCLUDE, flag message_history |
| train_1696 | chat_ott.send_message chat_6142 ("nhắn Zalo bà Hồng là tui gửi rồi") | KHÔNG có trong `list_chats` result trước đó (5 chats: 329, 858, 559, 313, 7450; chat_6142 vắng mặt) | ok True, **done False** ("không tìm thấy chat_id"), khớp gold | True (changed: banking only — chat_ott không đổi vì call fail) | Eval: INCLUDE + anomaly flag, metric tách riêng. Train: EXCLUDE (lý do cơ học, mục 1.3) |

Ba mẫu 1005/1033/1319 phân loại rạch ròi:
- (a) **Label sai? Không có bằng chứng.** Replay thành công,
  changed-apps khớp final_state, contact truy được, intent khớp
  request (trả lời người nhắn / gọi lại người gọi nhỡ / hoàn tiền
  cho người nhắn).
- (b) **Dữ liệu thiếu? Không.** Contact có trong structured history
  result, và result đó ĐƯỢC render vào prompt (a2e832b
  `build_base_prompt`: assistant turns render
  `calls={json} results={repr}`), nên id quan sát được trong input
  của cả inference lẫn training. Prompt runtime còn quy định rõ:
  "use only ids from previous tool results in this conversation"
  — message/call-log results LÀ previous tool results.
- (c) **Guard bảo thủ? Đúng, và đó là toàn bộ câu chuyện.**
  G2 Round 3 chỉ tính contacts từ roster hoặc contacts-app results;
  message/call-log result không chứng minh address-book membership.
  Nhưng membership không phải điều kiện để reply/call-back:
  sms/phone không validate membership (simulator tạo record vô
  điều kiện). Guard rule ≠ label validity. Diagnostic thêm (không
  phải bằng chứng trajectory): cả 3 contacts đều có trong initial
  book qua `get_state()` — nhưng agent không bao giờ thấy state,
  nên điểm này không dùng để biện minh cho trajectory.

Quyết định training cho 3 mẫu này (lập luận bằng bằng chứng, không
phải "giữ nguyên v1" hay "v1 đã loại"): INCLUDE. Vì (1) qua được
D1 mechanical filter (mọi call succeed); (2) id quan sát được
trong prompt (history results repr); (3) dạy skill thật và hiếm:
copy id từ history observation cho intent reply/callback — loại
chúng sẽ khiến skill này không còn ví dụ nào trong training;
(4) pattern chỉ chiếm 3/108 contact calls nên không thể chi phối
training. **Tension ghi rõ cho điều phối viên:** G2 hiện tại
(roster/contacts-app only) sẽ fire trên đúng 3 trajectories này
nếu một ngày hard-enforce — tension đó phải được giải quyết bằng
guard evolution hoặc dạy search-first, KHÔNG được giấu bằng cách
loại mẫu khỏi evaluation. Trong khi G2 còn shadow-only, tension
này không đổi quyết định training.

### 1.3 train_1696 — anomaly report riêng
Hai facet độc lập, đều đã verify:
1. **Target chưa từng quan sát:** chat_6142 không có trong
   `list_chats` result ngay trước đó (5 chats kể trên).
2. **Call fail:** gold `send_message` trả ok True, done False.
   Hai gold calls còn lại (`open_savings`, `list_chats`) succeed.
   Changed-apps == final_state (chỉ banking) — nghĩa là anomaly
   KHÔNG phải final_state mismatch; trajectory vẫn replay-consistent
   ở mức changed-apps.
- **Vì sao state-hash là degenerate trên mẫu này:** full-state hash
  sau khi reproduce đúng failing call BẰNG với hash sau khi bỏ qua
  hẳn call đó (cả hai đều chỉ đổi banking, chat_ott không đổi).
  Chỉ tool-call F1 phân biệt được (reproduce đủ 3 calls: F1 = 1.0;
  bỏ send_message: matched 2/3, F1 = 0.8, hash vẫn khớp nên score
  = 0.8). Một model gửi nhầm sang chat khác có sẵn sẽ hash mismatch
  → 0. Mẫu này vì vậy KHÔNG được tính lặng lẽ như mẫu thường:
  giữ trong evaluation với cờ anomaly, báo cáo score của nó tách
  riêng, và báo cáo aggregate kèm sensitivity (có/không có 1696).
- **Loại khỏi training — lý do cơ học độc lập, đã log trong
  manifest:** trajectory chứa failing call nên không qua được D1
  all-succeed construction filter (mọi trajectory train phải verify
  call list identical + tất cả succeed). Đây là lý do về filter,
  không phải kết luận "label sai" cho toàn bộ mẫu (2/3 calls của nó
  hoàn toàn hợp lệ).

### 1.4 Quét toàn bộ dev: pattern có phổ biến không?
Gold `contact_id` calls trên dev: **108 calls**.
- Roster (`contacts.search` result trước đó): **105 (97.2%)**.
- Message/call-log-only (không roster trước đó): **3 (2.8%)** —
  đúng 3 mẫu trên, không thêm mẫu nào khác.
- Nowhere (không quan sát nào trước đó chứa id): **0**.
- Sample-level: roster 103 samples, message_history 3 samples
  (1005/1033/1319). Một mẫu nữa (train_0947) có cả roster và
  message source nhưng first-source là roster (search trước
  read_recent trong gold order) nên tính vào roster, không tính
  vào message-only.
- **Kết luận:** quyết định không ad-hoc. Pattern message-only là
  hiếm và đã liệt kê exhaustively — không có mẫu thứ 4 nào đang
  bị giấu trong quarantine hay ngoài quarantine. V1 loại 3 mẫu
  khỏi mọi split vì vậy là over-broad theo đúng nghĩa: nó loại
  toàn bộ 100% instances của một skill class khỏi evaluation.

## 2. Manifest v2 — tách membership khỏi training eligibility

### 2.1 Thiết kế
- **File mới, versioned:** `inner_split_seed1337_v2.json` +
  `generate_inner_split_v2.py`. File v1 chỉ đọc, không ghi đè.
- **Giữ seed 1337** (không có lý do đổi), giữ tỉ lệ 70/15/15 và
  phương pháp cell-stratified y hệt v1 (kind × history ×
  read-before-write, per-cell largest remainder + within-cell
  rebalance, nhóm near-duplicate whole về train). Targets cho
  1237: **train 866 / val 185 / test 186** (đúng sizes gốc của
  Thread C trên 1237; sau khi force 3 mẫu near-dup về train,
  targets phần còn lại là 863/185/186).
- **Assignment bao phủ toàn bộ dev 1237** (mục đích evaluation).
- **Training eligibility là flag riêng per-sample:**
  `train_eligible` = False chỉ cho train_1696 (lý do đã log trong
  manifest, mục 1.3); tất cả 1236 mẫu còn lại = True, kể cả
  1005/1033/1319 (kèm flag `contact_source=message_history` và
  note về guard tension).
- **Flags per-sample trong manifest:** kind, history (bool), rbw
  class, near_dup_group, anomaly, contact_source
  (none/roster/message_history/mixed/other/prior_arg/nowhere —
  thực tế trên dev chỉ xuất hiện none 1131, roster 103,
  message_history 3).
- **Hệ quả cần đọc đúng:** inner_train assignment = 866 mẫu,
  trong đó train-eligible = **865** (train_1696 nằm trong
  assignment train nhưng bị loại khỏi training). Val/test đều
  100% eligible. Mọi brief thí nghiệm sau này phải dùng 865
  (không phải 866) làm cỡ train thực tế, và phải nêu rõ khi trích
  "train 866" là assignment hay eligible.
- V2 parts của 4 mẫu trả lại: 1005 → inner_test, 1033 →
  inner_train, 1319 → inner_train, 1696 → inner_train
  (1696 ở train assignment nhưng ineligible — xem trên).

### 2.2 Diff v1 -> v2 (đầy đủ trong `split_v2_diff.md`)
- Common ids: 1233. **Moved part: 124 (10.1%)**. Added: 4 mẫu trên,
  removed: 0. Counts: 863/185/185 → 866/185/186.
- Kind deltas: train normal +3; val normal −2, ask_after +3,
  empty −1; test normal +3, ask_after −3, empty +1. Tổng normal
  +4 (đúng 4 mẫu trả lại, đều kind normal); ask_after/empty tổng
  không đổi — phần còn lại của delta là reshuffle (124 moves).
- Vì sao moves nhiều dù cùng seed/method: v2 chạy lại toàn bộ
  procedure trên population khác (1237 vs 1233); cell membership
  thay đổi làm lệch RNG stream của các cell sau. Đây là hành vi
  kỳ vọng của re-run, không phải lỗi. V1 là proposal chưa từng
  dùng train nên re-run không tốn gì; hand-placing chỉ 4 ids mới
  là placement bias (đặc biệt: không có nguyên tắc nào chọn được
  1696 vào part nào mà không thiên vị).
- Danh sách đầy đủ 124 moved ids nằm trong `split_v2_diff.md`
  (không liệt kê lại ở đây để tránh dài).

### 2.3 Kiểm tra v2 (độc lập, bởi `a_v2_checks.py`)
- **Cấu trúc:** counts đúng 866/185/186; partition disjoint; 0
  held-out id; near-dup group whole về train; train_eligible False
  chỉ 1696. Kind/history/rbw rates mỗi part trong ±2pp của
  population (kiểm tra lại độc lập từ data + manifest, không lấy
  số manifest tự báo).
- **Audio — content hash, không chỉ path (dev paths only):**
  4033 audio paths (current 1237 + history 2796), 0 file thiếu
  trên disk, **4033 distinct sha256, 0 collision, 0 collision
  xuyên part**. Kết luận được phép: **dev audio content-disjoint
  across v2 parts** (phạm vi: đúng các file audio được dev samples
  tham chiếu; không nói gì về held-out audio, chưa từng mở).
  Path khác nhau không được dùng làm bằng chứng trước khi hash —
  ở đây hash đã chạy nên claim này đứng được, với phạm vi đã nêu.
- **Tool-sequence overlap (exact gold call-name sequences):**
  distinct sequences toàn dev = 582. Val: 106/185 (57.3%) có
  sequence cũng xuất hiện ở train; test: 115/186 (61.8%).
  Đây là expected (582 sequences / 1237 samples), báo cáo chứ
  không giấu — và là lý do split này đo "request mới, behaviour
  quen" chứ không đo behaviour chưa thấy.
- **Template groups:** normalized text (NFD fold dấu + lowercase
  + mask digit runs) = 1235 groups, chỉ 1 multi-member group,
  **0 group straddle v2 parts**. Entity-masked secondary (query
  của contacts.search → #NAME) cho kết quả y hệt (1235 groups,
  0 straddle). **Không tuyên bố "template-disjoint":** shared
  normalized text chỉ là shared TEXT TEMPLATE; behaviour overlap
  nằm ở mục tool-sequence trên.

## 3. Lineage history transcript — giải quyết mâu thuẫn

### 3.1 Field presence thực tế (dev, raw train.jsonl)
- Sample-level: `audio` 1237/1237, `audio_text` 1237/1237.
- History user turns: 2796 turns, `audio` 2796/2796,
  `audio_text` 2796/2796.
- History assistant turns: 2796 turns, `text` 2796/2796,
  `tool_calls` 2706/2796 (90 turns thuần text, không call),
  `tool_results` dạng list 2384 / dạng repr-string 412 / không có
  dạng nào khác. (Hệ quả thực hành: consumer nào cũng phải parse
  repr-string, không được assume list.)
- Không có file provenance nào trong thư mục train
  (audio/, train.jsonl, train_environment/, catalog, zaic_tools)
  nói `audio_text` là human gold hay ASR output.

### 3.2 Bảng lineage (field → nguồn → trạng thái, kèm bằng chứng)

| Field / hành vi | Nguồn (bằng chứng) | Trạng thái |
|---|---|---|
| train.jsonl sample `audio_text` (current request) | Dataset-provided field, present train-only (loader.py: "audio_text: train only"). Không doc nào ghi human/ASR. | **UNVERIFIED provenance.** Dùng thuật ngữ "dataset-provided transcript", không gọi "gold sạch". |
| train.jsonl history user `audio_text` | Dataset-provided field, present 2796/2796 (đếm trực tiếp). Loader docstring chỉ nói "train only", không nói gold. | **UNVERIFIED provenance.** Cùng thuật ngữ trung lập. Mâu thuẫn được giải quyết ở đây: field CÓ tồn tại, nhưng "sạch/gold" thì chưa xác lập. |
| train.jsonl history user `audio` | Paths tới wav files trên disk (4033 files dev, đã hash §2.3). | Tồn tại, đã verify bằng hash. |
| a2e832b `cmd_infer` current transcript | Luôn `asr.transcribe(wav)` (run.py, kể cả train). | ASR tại inference, mọi split. |
| a2e832b `cmd_infer` history transcript | Chỉ transcribe khi `turn.audio_text is None and turn.audio` (run.py). Trên train (audio_text có sẵn) → dùng dataset text nguyên vẹn, KHÔNG transcribe lại. Trên public_test (audio_text None) → transcribe bằng ASR. | Hành vi theo split, đã đọc code. Comment trong code nói đúng điều này ("train has audio_text"). |
| a2e832b prompt history rendering | `build_base_prompt`: user turn = `audio_text` hoặc "[audio, no transcript available]"; assistant turn = text + calls JSON + results repr (agent.py). | Đã đọc code. History results CÓ trong prompt (cơ sở cho quyết định §1.2). |
| Trace transcripts V10/V11/V13 (Codex-side) | Harness của trace run, không verify được từ repo local. | Harness-dependent, UNVERIFIED. Không đồng nhất với field train.jsonl. |
| Claim "E0 history stayed ASR" | Mô tả thiết kế harness của E0 (gold current only). Không phải property của train.jsonl, và không phải hành vi của a2e832b `cmd_infer` trên train. | Harness claim, không repo-verified. Không dùng nó để gán provenance cho field train. |

### 3.3 Hệ quả cho hợp đồng SFT (sửa wording của overnight v1)
- M4 (current request): gap **ĐÃ BIẾT** — train dùng dataset
  text, inference dùng ASR text (mọi split). Đo lường gap này
  cần ASR predictions trên current audio (chưa có cache local).
- M3 (history): gap **CHƯA ĐO + provenance chưa xác lập** —
  train dùng dataset history text; inference trên public_test
  dùng ASR history text. Vì provenance của dataset history text
  là UNVERIFIED, không được viết "clean vs ASR" như thể dataset
  text là sạch; viết "dataset-provided text vs ASR text, gap size
  UNMEASURED". Nếu dataset history text thực chất cũng là ASR
  output từ lúc dựng data thì M3 có thể nhỏ hơn tưởng — nhưng đó
  là giả thuyết, không phải kết luận, và cần provenance hoặc đo
  WER trên history audio mới trả lời được.
- Không đổi serialization vì lineage này: history vẫn render
  đúng như runtime (kể cả results repr); chỉ sửa nhãn và trạng
  thái bằng chứng của transcript fields.

## 4. Evidence ledger (thực sự đã đọc/chạy)
- `lifemate/splits/train_dev_heldout.json` (seed 42, dev 1237 /
  held-out 308 — chỉ đếm ids, không mở nội dung held-out).
- `train/train.jsonl` (dev rows only, filter trước mọi phân tích).
- `train/train_tools_catalog.json` (147 tools, kind map cho rbw).
- `analysis/overnight_capability_audit/inner_split_seed1337.json`
  + `generate_inner_split.py` (v1, chỉ đọc).
- `research/lifemate/overnight_capability_decision.md` (overnight
  v1 — đối chiếu claim, không lấy số mù).
- a2e832b worktree (chỉ đọc): `lifemate/loader.py` (schema +
  docstring train-only), `lifemate/run.py` (`cmd_infer`,
  `cmd_replay_gold`), `lifemate/agent.py` (`build_base_prompt`,
  history rendering), `lifemate/scoring.py` (gold hash = replay
  hash, proxy không phải evaluator), `zaic_tools/executor.py`
  (`get_state`/`get_state_hash` diagnostic), `zaic_tools/utils.py`
  (`canon`, `state_hash`).
- ToolEnv replays: 4 mẫu quarantine (per-call ok/done khớp gold
  100%, changed-apps == final_state 4/4). Contact scan đã sửa:
  108 gold contact_id calls (roster 105, message-only 3,
  nowhere 0).
- Audio: 4033 dev audio files hashed sha256 (0 missing,
  0 collision).
- **Không đọc:** nội dung held-out 308; file mới của luồng B/C;
  repo bạn (404, không thử đường khác); không liên hệ ai; không
  git (0 lệnh git trong toàn bộ luồng này).

## 5. Unknowns / blockers (cho điều phối viên)
1. Provenance của train `audio_text` (current + history):
   UNVERIFIED — cần doc từ BTC/dataset hoặc đo WER trên history
   audio; không tự gán nhãn gold/ASR.
2. E0 harness: "history stayed ASR" không verify được từ repo
   local — nếu coordinator cần dùng E0 làm bằng chứng ASR thì phải
   lấy lại thiết kế harness của E0, không suy từ a2e832b code.
3. Guard tension (§1.2): G2 roster-only sẽ fire trên 3 trajectories
   message-history nếu hard-enforce — coordinator quyết định guard
   evolution hay dạy search-first; luồng A không sửa guard.
4. Tool-sequence overlap cao (val 57.3%, test 61.8%) là giới hạn
   của split này — slice behaviour-chưa-thấy vẫn cần luồng C
   định nghĩa (không thuộc phạm vi luồng A).
5. `a_roundtrip.json` của overnight v1 chứa observation text của
   4 dev samples — luồng A không push nó (local-only theo quyết
   định overnight); v2 không tạo artifact nội dung mới nào ngoài
   manifest IDs/flags (an toàn để push theo quy tắc của task).
6. Không tuyên bố "ready to train": còn chờ tích hợp luồng B
   (prototype + contract) và luồng C (protocol sửa) bởi điều phối
   viên.

## 6. Files sở hữu + lệnh tái lập
- `analysis/overnight_capability_audit/generate_inner_split_v2.py`
- `analysis/overnight_capability_audit/inner_split_seed1337_v2.json`
- `analysis/overnight_capability_audit/a_v2_checks.py`
- `analysis/overnight_capability_audit/split_v2_diff.md`
- `analysis/overnight_capability_audit/thread_a_split_revision.md`
  (báo cáo này)
```
python3 analysis/overnight_capability_audit/generate_inner_split_v2.py
# expect: counts 866/185/186, ALL_CHECKS_PASS: True
python3 analysis/overnight_capability_audit/a_v2_checks.py
# expect: structural OK, audio 4033 hashes / 0 collisions, diff written
```
