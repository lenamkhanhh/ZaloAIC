# Cập nhật nghiên cứu đợt 3 — 2026-10-27 (mốc so sánh: commit 8d4721e)

> Tài liệu này chỉ ghi **những quyết định triển khai thay đổi** sau đợt
> nghiên cứu bổ sung và đợt sửa code song song. Nó KHÔNG viết lại 4
> chuyên đề, và không thay thế các bản nháp đầy đủ trong
> `../research/round3-p1..p5.md` — mọi bằng chứng, bằng chứng ngược và
> nhãn mức độ đọc nằm ở đó. Đọc synthesis này mà không đọc bản nháp
> tương ứng thì chưa đủ căn cứ để chốt một quyết định nào.
>
> Quy ước trung thực áp dụng cho toàn bộ file: con số từ benchmark khác
> là **tác giả tự báo cáo trên tập của họ**, không phải số ZAIC; claim
> nào bản nháp ghi SECONDARY / SNIPPET / UNVERIFIED thì ở đây vẫn giữ
> nguyên nhãn đó, không nâng cấp. Chưa có thực nghiệm nào trên dữ liệu
> ZAIC thật trong đợt này.

## 0. Đợt sửa code song song (commit riêng, đã kiểm chứng)

Xem `tests/test_regressions.py` (54 test, chạy thật — xem §6). Tóm tắt
hướng đổi, chi tiết trước/sau ở cuối mỗi chuyên đề:

- **01:** schema ngoài khai báo đủ properties; x-ref thiếu/chưa load thì
  fail-closed; `ToolAgent` nhận `ExecutionResult` (output/error/refs)
  và có đường kết thúc bình thường qua `completion`; cache giá trị bị
  xóa sau write, ID refs giữ lại.
- **02:** bỏ rule "digits only" chung; tiền/ngày/ID chuẩn hóa theo từng
  loại; guard phủ định theo mệnh đề + cụm từ nhiều từ.
- **03:** dấu âm không còn mất; số nguyên thuần ở locale vn/en; tiền
  qua `parse_vn_money` (Decimal); `query()` thực thi chặn SELECT/WITH;
  SQL Tết loại ở mức đơn hàng (diễn giải, chưa đối chiếu nguyên văn).
- **04:** canonical form gắn tag type (`True` ≠ `1`); consensus đổi sang
  đa số tuyệt đối; calibration thêm ngưỡng reject-all; thêm
  `check_schema_coverage` (full schema + alias).

## 1. Ưu tiên 1 — LifeMate: sửa ASR hay hỏi lại?
Bản đầy đủ: `../research/round3-p1-asr-repair-vs-ask.md`

**Đổi hướng 1 — "Không chắc thì hỏi" là sai về điểm số, không chỉ là
thận trọng.** LifeMate tính theo hash từng mẫu: nếu gold có write mà
mình hỏi thay vì write thì cũng 0 điểm, đúng bằng write sai. Với slot
đã có bằng chứng mà ASR làm hỏng, sửa có căn cứ luôn có kỳ vọng ≥ hỏi
(sửa đúng > 0, sửa sai = hỏi = 0). Hỏi chỉ đúng khi thông tin thật sự
không có (ngày tương đối không có mốc, tên trùng không có slot phân
biệt). Ngoại lệ duy nhất: phủ định — write bị chặn vẫn bị chặn, vì
gold của mẫu phủ định có thể là không-write/`[]`.
*Điều kiện:* kết luận này phụ thuộc Q-L1 (cách evaluator tính ask) —
bản nháp trình bày kết quả dưới cả hai giả định ask-scoring trong thí
nghiệm đề xuất. Chưa chốt cho tới khi Q-L1 được xác minh.

**Đổi hướng 2 — Tách khác thanh thành hai trường hợp.** Khác thanh mà
không có đối thủ trong danh sách read → ứng viên sửa có điều kiện
(kiểm tra phonetic + acoustic), không tự động hỏi. Khác thanh mà đối
thủ cũng chỉ khác thanh (cả Bình và Bính đều có trong contacts) → vẫn
hỏi hoặc tìm slot phân biệt. Tương tự, mất dấu hoàn toàn không còn
auto-UNKNOWN: chỉ sửa khi dạng không dấu + dạng phonetic + điểm
acoustic hội tụ về đúng một candidate.

**Đổi hướng 3 — Grounding phải trả về (id, string), không chỉ string.**
Tên trùng với id khác nhau hiện không có đáp án đúng ở tầng text
(`Candidate.key` có sẵn nhưng `ground_slot` không dùng). Tên trùng
chuẩn hóa giống nhau + id khác nhau → AMBIGUOUS vĩnh viễn ở tầng text,
chỉ giải quyết bằng slot phụ, history, hoặc hỏi.

**Đổi hướng 4 — "Candidate chỉ từ tool read" là lựa chọn thiết kế, không
phải luật đã ghi.** Kiểm tra lại portal 2026-10-26 chỉ ghi cấm đọc
state.json/ToolEnv, không cấm dùng user context/history/installed apps
để biasing. Ràng buộc thật là khác: read thêm tốn F1 chưa rõ (Q-L3),
nên biasing nên ưu tiên nguồn không cần read (context/history), read
chỉ dùng sau pass transcript đầu tiên.

**Thứ tự thử:** (1) sửa có kiểm chứng xác định + acoustic rescoring —
teacher-forced Whisper logprob của transcript đã thay candidate (cùng
PhoWhisper, 0 tham số thêm), với biến thể trừ LM nội bộ để phân biệt
"audio rõ nhưng ASR sai" (LM prior lấn át acoustics). Đây là tín hiệu
âm thanh duy nhất không cần model mới. (2) Contextual decoding
(`initial_prompt` / faster-whisper `hotwords`) — chỉ là thí nghiệm số
2, vì nó là soft biasing có chế độ lỗi overcorrection (chèn tên không
được nói khi không có decider/filter), và với LifeMate nó thực chất là
thiết kế 2 pass (pass 1 → reads → pass 2) tốn ~2× ASR + F1 của read
chưa rõ. **Không thử:** LLM-select kiểu RECOVER với model nhỏ (paper
RECOVER đọc đầy đủ §§1–5: ROVER/merge làm WER tệ hơn trên dữ liệu
nhiễu; LLM-Select chỉ thắng với GPT-4o, với GPT-4o-mini thì mức cải
thiện sụp xuống 2,2–15,7% — Qwen3-4B gần phía mini hơn); DeRAGEC chỉ lấy
được "denoise trước khi sửa" và tín hiệu phonetic riêng, còn stack
70B/GPT, DB 3M entity và định nghĩa Wikipedia đều vượt ngân sách.

**Tín hiệu phonetic mới (thay khoảng trống "không có Double Metaphone
tiếng Việt"):** Epitran `vie-Latn` (IPA có dấu thanh, xác nhận tồn tại
ở mức SECONDARY — map file chưa đọc từng dòng) + khoảng cách articulatory
của Panphon. Đây là G2P, không phải Double Metaphone, và độ robust theo
phương ngữ Bắc/Trung/Nam chưa đo.

**Chưa đủ bằng chứng:** portal fetch lại trong đợt này lỗi mạng, không
retry, nên kết luận §1.4 dựa trên ghi nhận portal 2026-10-26; không tìm
thấy repo code công khai của RECOVER (paper được coi là spec để tái
hiện, không phải code đã đọc); DeRAGEC/CoVoGER chỉ đọc root + README
(commit fedc1690 / bb6400c), thân file decode/rerank lấy từ tóm tắt
DeepWiki (SECONDARY); faster-whisper có expose N-best thật hay không
chưa xác minh.

**Thí nghiệm nhỏ nhất:** trên train held-out, đo hash-correct + tool F1
+ ask-rate cho: baseline text-only hiện tại → + acoustic rescoring →
+ phonetic (Epitran/Panphon) → + contextual decoding 2-pass, mỗi bước
chỉ giữ lại nếu thắng mà không tăng ask sai; báo kết quả dưới cả hai
giả định ask-scoring.

## 2. Ưu tiên 2 — LifeMate: model và recipe thay baseline Qwen prompt-only
Bản đầy đủ: `../research/round3-p2-lifemate-models-recipe.md`

**Kết luận chính: KHÔNG checkpoint nào được thăng hạng vào shortlist
chính. Qwen3-4B-Instruct-2507 vẫn là baseline.** Nguồn gốc Qwen3-4B giờ
đã card-confirmed (Apache 2.0, 4,0B tổng / 3,6B non-embedding, 36 lớp,
context 262.144, commit `cdbee75`). Điểm yếu của nó là loại bằng chứng,
không phải nguồn gốc: model instruct tổng quát, không có bằng chứng
stateful dạng ZAIC; các số τ trên card (Retail 48,7 / Airline 32,0…)
không ghi pass version, policy on/off hay số trial nên **không được
xếp hạng** cùng số τ của APIGen-MT (pass@1, ≥ 5 trial).

**xLAM-2-3b-fc-r — vẫn chỉ A/B, nhưng hai điểm đã giải quyết:**
repo chính thức là `Salesforce/xLAM-2-3b-fc-r` (3B; dạng `Llama-` trong
code mẫu của card 8B là mâu thuẫn đặt tên, đừng download khi chưa mở
card). Bằng chứng stateful mạnh nhất trong nhóm challenger (APIGen-MT,
arXiv 2504.03601v4: BFCL v3 65,11; τ retail 44,4 / airline 32,0), nhưng
bằng chứng ngược chặn thăng hạng nằm ngay trong cùng paper:
**irrelevance 57,94** (ToolACE-2-8B 90,11; GPT-4o FC 83,15) dù relevance
94,44 — giỏi gọi tool đúng, kém từ chối tool sai, đúng vào tầng
ask/refuse của LifeMate. Licence vẫn UNVERIFIED trên card gốc; mọi tín
hiệu thứ cấp đều chỉ CC BY-NC 4.0, và NC có thỏa rule "open-source"
của ZAIC cho cuộc thi có tiền thưởng hay không là câu hỏi cho ban tổ
chức, không phải giả định.

**Hammer2.1-3b — vẫn chỉ A/B; bằng chứng mỏng nhất.** Card-confirmed:
base Qwen 2.5 coder, multi-step/multi-turn calling, 3 đường inference
(Hammer client qua vLLM, vLLM built-in với parser `hermes`, chat
template Transformers). Nhưng số BFCL-v3 chỉ ở dạng ảnh (không đọc
được giá trị), không có số τ, không có đo recovery hay tiếng Việt, và
**không có training code 2.1 trong repo Hammer** — claim multi-step
dựa vào card mà thôi. Licence của chính bản 3B UNVERIFIED (mirror ghi
"MadeAgents other" cho 3B, cc-by-nc-4.0 cho bản 0.5b/7b — licence của
bản khác không phải licence của bản 3B). Ngày phát hành chính xác
UNVERIFIED (ghi chú 06/2025 là ghi chú cập nhật, repo ghi thế hệ 2.1
từ 12/2024).

**Hammer-4B — vẫn chỉ A/B, ưu tiên thấp hơn; base đã xác định, kèm một
sửa sai.** Theo paper ICLR 2025 (arXiv 2410.04587v1, Table 5), base là
Qwen1.5-4B-Chat (trước đây ghi "chưa xác minh"). Số BFCL v2 era
(09/2024): overall 76,05; irrelevance 68,66; F1 Func+Args trung bình
71,35. Không có τ, stateful hay recovery; format train là single-turn
(xem dưới) nên khớp kém nhất với dạng multi-step của LifeMate. Chỉ test
nếu card của chính nó xác nhận CC-BY-4.0.

**Sửa sai về licence có hậu quả SFT: Qwen2.5-Coder-3B KHÔNG phải Apache
2.0.** Card metadata ghi "license: other, license_name: qwen-research"
(nguồn thứ cấp trích card; bảng Qwen2.5 liệt kê 3B là Qwen Research
trong khi 0.5B/1.5B/7B/14B/32B là Apache 2.0). Nếu base SFT phải permissive
thì 3B coder không phải base Apache sạch — điều này củng cố Qwen3-4B
(Apache 2.0, card-confirmed) làm base SFT. (Ngân sách nếu vẫn dùng
coder 3B: 3,09B + PhoWhisper-small 0,244B = 3,334B.)

**Code Hammer đọc từng dòng lần đầu (repo `MadeAgents/Hammer`, licence
code Apache-2.0 — không phải licence checkpoint, commit `ff415d9`):**
`train/data_processing.py` (293 dòng): 60k + 7,5k irrelevance data,
trộn, lặp 3×; với xác suất 2/3 (comment code "Masking ratio p=1-1/3")
áp toàn bộ chuỗi masking — tên tool → chuỗi ngẫu nhiên 5–15 ký tự,
tên tham số → 4–10 ký tự, default trùng đáp án được viết lại (bẫy
default-value), đáp án rename nhất quán, tools dedup/pad/shuffle.
**Mâu thuẫn phải ghi:** paper ablation (ví dụ "mask 0,33") và script
2/3 là hai con số khác nhau; đừng trích 0,67 như khuyến nghị của paper.
Bài học của paper: mask cao làm chậm học cùng task nhưng giúp khái
quát cross-task; irrelevance mix có trade-off ngược với khả năng gọi,
tối ưu ~10% trên ablation của họ. **Giới hạn format quyết định:**
format SFT của v1 là single-turn only (instruction → JSON list, `[]`
nếu không gọi; "không dùng được thì từ chối; thiếu tham số thì chỉ
ra") — không có history multi-turn, không có role observation. Hammer
v1 dạy sinh call một lần, không dạy chaining theo observation.
`evaluation/evaluate.py` (118 dòng): P/R/F1 theo call, exact string
match; lỗi format và prediction rỗng bị bỏ qua trước khi đếm nên không
đo irrelevance — đừng tái dùng làm scorer LifeMate (cần cổng
state_hash + tool F1 + xử lý ask/empty).

**Đổi hướng recipe: từ "SFT trên rollout của agent" sang blueprint-first,
gold cố định trước, trajectory rejection-sampled (mẫu APIGen-MT), với
masking + irrelevance mixing của Hammer làm tầng augmentation.**
Gold (instruction `q`, ground-truth actions `a_gt`, expected outputs
`o_gt`) được tác giả hoá và kiểm chứng TRƯỚC khi có trajectory học
sinh nào: cổng format → cổng thực thi (mô phỏng `a_gt` trong
`zaic_tools` trên state mới, lấy diff) → cổng policy/intent (policy
thành check trên trace mô phỏng; thực thi thành công ≠ đúng intent) →
cổng committee (nhiều judge khác nhau, vote đa số). Trajectory chỉ giữ
khi đạt goal (`r = 1`) so với gold cố định đó, ≤ 3 attempt/task, human
mô phỏng tiết lộ chi tiết từng turn (APIGen-MT: task-config success
70% có feedback vs 28% không; trajectory success 67%; trung bình 7
call, 6 turn user). **Quy tắc chống circularity, dạng vận hành:** không
bao giờ tính `state_hash` từ chính call của học sinh rồi coi là nhãn.
Tái dùng gold train của ZAIC làm nhãn SFT thì không circular (gold của
ban tổ chức), nhưng rollout của học sinh làm gold thì cấm. Rollout thất
bại chỉ dùng làm dữ liệu recovery khi fix được kiểm chứng với gold cố
định, còn không thì bỏ. Chi tiết train APIGen-MT: chỉ predict token
assistant, mask prompt, LLaMA-Factory, full FT, ZeRO-3, FlashAttention
2, bf16, AdamW, ≤ 3 epoch — **learning rate và batch size không tìm
thấy trong bản arXiv HTML v4 (đã search, không có hit); không bịa.**
Format mapping: Qwen chat template cho Qwen3-4B; Hermes-style
JSON-in-fence cho Hammer2.1; template + parser của xLAM cho xLAM — kèm
cảnh báo `sys.ask_missing_info` của ZAIC (hỏi trước khi hành động)
**không phải** tool `respond` của Hammer (trả lời cuối) và không được
đồng nhất. Augmentation: masking bắt đầu thấp và A/B (không lấy mặc
định 2/3 của script), irrelevance mix bắt đầu ~10% gắn nhãn theo dạng
ask của ZAIC (không chỉ `[]` của Hammer), ví dụ clarification chỉ ở vị
trí pre-write (rule ask-sau-write chưa xác minh), biến thể nhiễu ASR
chỉ từ transcript train thật, mọi text tổng hợp bằng tiếng Việt.
Recovery là phần thêm của recipe, không phải thuộc tính của checkpoint:
**không ứng viên nào có đo recovery sau call thất bại đã công bố**;
RECOVER (đợt trước) là phần bù phía inference.

**Thí nghiệm nhỏ nhất (định nghĩa, chưa chạy — không có A30 hay chạy
trên dữ liệu ZAIC):** một split train_holdout cố định (tách
business/type), cùng harness validator/loop-guard/selective-read, greedy
decoding, seed cố định. Các arm theo thứ tự: (1) Qwen3-4B prompt-only,
(2) + few-shot với exemplar đã mask tên, (3) + retrieval theo dạng
tool/dependency, (4) Qwen3-4B small-SFT theo recipe trên, (5) xLAM-2-3b
prompt-only và (6) Hammer2.1-3b prompt-only — chỉ khi licence của chúng
giải quyết thuận lợi. 5 metric, không quyết bằng một metric:
hash-correct rate, tool F1 (metric chọn: trung bình của hash-correct ?
tool F1 : 0), irrelevance/ask accuracy, recovery rate, latency ≤ 30s
làm ràng buộc — cộng thêm slice slot tiếng Việt riêng. Quy tắc chọn
(đề xuất): chỉ thăng hạng khi thắng ở metric chọn mà không thụt lùi
irrelevance/ask hay recovery. Thắng call-accuracy nhưng thụt
irrelevance là thua đối với LifeMate — đúng cái bẫy của xLAM-2-3b.

**Chưa đủ bằng chứng:** licence card gốc của xLAM-2-3b / Hammer2.1-3b /
Hammer-4b / Hammer2.0-3b; NC hay Qwen Research có thỏa rule
"open-source" của ZAIC không; ngày phát hành chính xác từng ngày
(cutoff hiện không gặp rủi ro theo bằng chứng hiện có); `config.json`
của mọi ứng viên; hiệu năng tool-use tiếng Việt của mọi ứng viên; bằng
chứng stateful dạng ZAIC của mọi ứng viên; gold train có được tái dùng
làm nhãn SFT không (lập luận là không circular, chưa có ruling của ban
tổ chức); rule ask-sau-write; diễn giải cutoff cho checkpoint
fine-tune; latency A30 và rule đếm total-vs-non-embedding; hyperparameter
APIGen-MT; dữ liệu/code train Hammer2.1; và bản thân dataset ZAIC
(giải nén zip vẫn là bước xác minh quan trọng nhất tiếp theo).

## 3. Ưu tiên 3 — DataMate: solution hoàn chỉnh để đối chiếu kiến trúc
Bản đầy đủ: `../research/round3-p3-datamate-complete-solutions.md`

**Đổi hướng 1 — BASE-SQL không có code: ngừng chờ nó.** Repo chính
thức (https://github.com/CycloneBoy/base_sql, HEAD `065bfe1`) chỉ có
README + LICENSE + ảnh; todo "Organize the code and publish it to
github" trong README chưa tick. Successor cùng nhóm, CSC-SQL
(https://github.com/CycloneBoy/csc_sql, HEAD `0fafdf3`, Apache 2.0),
mới là nơi revision/merge-revision thật sự nằm trong code — nhưng có
bẫy: dữ liệu train merge của nó chèn gold SQL vào cặp top-2
(`execute_batch_vote_sql_to_result`, `is_train=True`), nên merge prompt
zero-shot với model 7B base là cơ chế **khác và yếu hơn** số báo cáo
của CSC-SQL, và ngày công bố HF của checkpoint merge CSC 7B (cutoff
01/10/2026) vẫn UNVERIFIED. **Quyết định:** xóa BASE-SQL khỏi danh sách
"code cần đọc"; giữ CSC-SQL chỉ làm tham chiếu merge kèm cảnh báo đó,
không bao giờ trích số CSC cho merge zero-shot.

**Đổi hướng 2 — DABstep baseline giờ đã đọc thật, và không nên copy làm
khung DataMate.** HF Space https://huggingface.co/spaces/adyen/DABstep,
revision `d4431c2e` (lỗi fetch đợt 2 đã sửa qua HF API):
`baseline/run.py` + `baseline/utils.py` + `baseline/prompts.py` cho thấy
smolagents `CodeAgent` với `tools=[]`, tối đa 10 bước, model mặc định
`openai/o3-mini`, rule nghiệp vụ dán vào prompt dưới dạng `guidelines`
(không bao giờ tách thành assertion kiểm chứng được), `open` bị ghi đè
thành chỉ-đọc, và không có typed formatter, cross-check hay abstain
theo PA. **Quyết định:** chỉ lấy hai chi tiết — `open` chỉ-đọc làm mẫu
cho enforcement chỉ-đọc, và bài học rule phải **vừa** nằm trong prompt
**vừa** tách thành assertion code (baseline chỉ làm nửa đầu, đúng chỗ
nó yếu).

**Đổi hướng 3 — ReFoRCE branch `o3` đã chốt, kèm ba sửa chữa cho mô tả
đợt 2.** Clone `--branch o3`, HEAD `d2658991`, Apache 2.0.
`methods/ReFoRCE/agent.py`: tên class xác nhận là `REFORCE`;
exploration là rule cứng (một lần gọi LLM phải cho ≥ 3 exploration SQL,
không thì retry tối đa 3 lần; 0 exploration thành công thì dừng
exploration); `execute_sqls` sửa lỗi tối đa 3 lần, đơn giản hóa khi
rỗng, dừng sau 3 lỗi liên tiếp. "Self-consistency" của nó **không phải**
majority vote — self-refine dừng khi kết quả lặp lại; majority vote chỉ
nằm trong `vote_result` (opt-in `--do_vote`, 3 vote), so sánh CSV kết
quả không phân biệt thứ tự, và quan trọng nhất: **khi hòa mà không có
`--model_vote` hay `--random_vote_for_tie`, nó trả về mà không copy kết
quả nào** — bằng chứng mức code cho "hòa → abstain" dưới Penalized
Accuracy. `methods/ReFoRCE/sql.py` (`SqlEnv`) xác nhận SQLite `mode=ro`,
timeout 300s, và ba trạng thái phân biệt (success / chuỗi rỗng / dict
lỗi). **Quyết định:** không đảo ngược gì, nhưng hành vi vote-hòa và
rule cứng exploration giờ là code-verified, không còn là mô tả paper.

**Đổi hướng 4 — Unit Tester của CHESS là pass-through đúng ở các ca
DataMate gặp nhiều nhất: bỏ chọn bằng LLM.** Repo
https://github.com/ShayanTalaei/CHESS, HEAD `3d6e835`, Apache 2.0.
`src/workflow/agents/unit_tester/tool_kit/evaluate.py`: chọn = clustering
theo thực thi + LLM chấm theo unit test do LLM sinh, hòa thì lấy cluster
lớn nhất — nhưng với 1 candidate thì điểm auto-1, với 0 unit test thì
candidate đầu auto-1, và với 0 candidate thì nó chèn placeholder
`"SELECT * FROM table_name"` (điểm 0). Tool `Revise` của nó còn gắn cờ
mọi trạng thái khác `SYNTACTICALLY_CORRECT` để sửa, kể cả
`ZERO_COUNT_RESULT` — tức đáp án COUNT=0 đúng bị "sửa" mất. **Quyết
định:** thay selector LLM bằng vote theo output thực thi, hòa →
abstain, cộng assertion rule bằng code + tính toán thứ hai độc lập; chỉ
giữ phần tách được của CHESS — chọn schema trước khi sinh (tác giả báo
cáo +~2% accuracy, ~5× ít token, chưa xác minh độc lập).

**Đổi hướng 5 — RSL-SQL chứng minh trigger sửa phải xét trường error,
không chỉ row_count. [SỬA SAI 2026-10-27, đọc lại code gốc]** Repo
https://github.com/Laqcce-cao/RSL-SQL, HEAD `fb1dcf0`, Apache 2.0.
4 bước nối file (SQL sơ bộ → SQL tăng cường → chọn nhị phân bằng LLM
với cả hai kết quả thực thi trong prompt → tự sửa tối đa 5 vòng) thật
sự rẻ. Bản tổng hợp trước đây ghi sai rằng `execute_sql` trả
`(0, 0, error)` cho cả lỗi và rỗng. Thực tế `src/utils/util.py::execute_sql`
trả `(row_count, column_count, result)` và trường thứ ba PHÂN BIỆT
được: rỗng hợp lệ → `(0, 0, "")`, lỗi → `(0, 0, <error_text>)`,
timeout → `(0, 0, "TimeoutError: ...")`. Lỗi thật ở
`src/step_4_self_correction.py`: trigger sửa là
`row_count == 0 and column_count == 0` và bỏ qua hoàn toàn trường thứ
ba, nên SQL đúng nhưng ra 0 dòng vẫn bị sửa tối đa 5 lần. COUNT=0
không bị ảnh hưởng (COUNT(*) trả về 1 dòng nên bước 4 dừng).
**Quyết định (giữ nguyên, với lý do đã sửa):** trigger sửa có điều kiện
của repo phải xét error-string và loại trừ đáp án rỗng đã kiểm chứng
(COUNT=0, list rỗng đã check) — giờ là yêu cầu cứng, không phải sở
thích, và nối trực tiếp với taxonomy của Ưu tiên 5.

**Kiến trúc chốt đầu tiên là B-trimmed, không phải C, không phải
pipeline 7 bước đầy đủ ngay ngày đầu.** So sánh (greedy, 7B local):
A = 1 lần gọi model; B = 2–6 lần (exploration 1 + chính 1 + sửa có điều
kiện chỉ khi trigger); C = 10–24 lần (CHESS ~20 lần gọi cấu trúc; CSC
major-voting 24 sample; DABstep ≤ 10 bước agent) — kiến trúc duy nhất
có nguy cơ vỡ ngân sách 6 giờ ngay cả trước khi tính latency từng lần
gọi, và selector LLM của nó chia sẻ blind spot với generator. **Thứ tự
mới:** (1) A + formatter xác định + profiler, đo trước; (2) + shortlist
schema xác định với một fallback full-schema (đo recall trước PA);
(3) + sửa có điều kiện kiểu ReFoRCE (tối đa 3, đơn giản hóa khi rỗng,
dừng sau 3 lỗi liên tiếp, loại trừ rỗng đã kiểm chứng); (4) chỉ sau đó
mới tới C rút gọn — vote output với k=2–3, chỉ dùng khi candidate bất
đồng, không bao giờ gọi selector khi đã đồng thuận.

**Một con số trong repo cần sửa khi cập nhật tài liệu:** con số 14,55%
DABstep-hard hiện mô tả là "best agent tại thời điểm paper" khớp với
dòng baseline o4-mini reasoning trong bảng leaderboard của I2I-STRADA
(arXiv 2507.17874), trong khi chính I2I-STRADA sau đó báo 28,04% hard
(Claude 3.5 Sonnet) — nên không trích nó như mốc "best" cố định nữa.
I2I-STRADA bản thân chỉ có paper (không tìm thấy code công khai);
code CHASE-SQL cũng không tìm thấy (chỉ paper, arXiv 2410.01943), nên
cả hai không được trích làm bằng chứng code.

**Thí nghiệm nhỏ nhất (train_holdout tách business, cùng checkpoint
7B):** 5 đối đầu, đo bằng PA (không phải accuracy), abstain rate và
giây/câu: (1) A vs B2 sửa có điều kiện — B2 chỉ thắng nếu số ca
lỗi→đúng vượt số ca đúng→hỏng do sửa; (2) shortlist có/không fallback
— đo recall bảng/cột cần thiết TRƯỚC PA; (3) vote output k=2–3 vs chọn
nhị phân bằng LLM, chỉ chấm trên câu candidate thật sự bất đồng;
(4) merge zero-shot vs vote thuần trên cùng cặp top-2 — merge chỉ sống
nếu nó sửa "cả hai bản nháp đều đúng một nửa" nhiều hơn trộn hai lỗi
thành lỗi mới; (5) tập câu gold-0/gold-empty riêng — pipeline nào
"sửa" đáp án 0/rỗng đúng thì loại ngay. Không cần training dài, không
cần A30 cho các thí nghiệm này (một GPU chạy vLLM cho model 7B là đủ;
wall-clock suy ra với giả định ghi rõ).

**Chưa đủ bằng chứng:** không có số PA nào của B hay C trên model 7B
cho DataMate ở bất cứ đâu trong nghiên cứu này (mọi số đều là benchmark
khác/backbone khác); ngày cutoff của checkpoint CSC-SQL 7B và text
licence của DABstep Space UNVERIFIED; throughput 2× RTX 5090 chưa đo
(số lần gọi trên là lần gọi logic, không phải wall-clock — không được
giả định 2 GPU gấp đôi throughput); cách evaluator ZAIC thật xử lý
unanswerable/percent/tie-break, cộng nội dung zip train thật, vẫn chưa
xác minh cho tới bước giải nén.

## 4. Ưu tiên 4 — DataMate: vì sao consensus cùng sai, và compute đặt ở đâu?
Bản đầy đủ: `../research/round3-p4-consensus-compute.md`

**Đổi hướng 1 — Bỏ score trọng số 0,5/0,3/0,2 làm cổng quyết định.**
Nó là heuristic trong [0,1], không phải xác suất — score 0,83 không có
nghĩa "83% đúng", và ngưỡng 0,5 của nó không có ý nghĩa xác suất.
Thay bằng: cổng xác định trước, rồi một verifier nhỏ KHÔNG phải LLM
(hồi quy logistic trên đặc trưng quan sát được duy nhất — consensus
fraction sau khi lọc cổng, số output khác nhau, second-path agreement,
pass/fail từng cổng, question type với fallback ≥ 30 mẫu như hiện có,
độ khó quan sát được) train trên train_cal, đo ECE và reliability
diagram trên holdout tách business. Chỉ khi đó ngưỡng break-even PA
P(đúng) > 0,5 (từ E[PA] = 2p − 1) mới có nghĩa; nếu calibration trên
holdout lệch thì ngưỡng phải dịch theo reliability curve đã đo, không
giữ 0,5.

**Đổi hướng 2 — Bỏ k=3 chỉ-khác-seed làm pool mặc định.** Seed-only
thất bại đúng ở chỗ DataMate thất bại: cùng đọc sai rule, cùng sai
grain/join (fan trap), cùng sai cửa sổ as-of/Tết, cùng mislink schema
→ cùng một đáp án sai, vote khóa nó lại ("Tyranny of the Majority",
Estornell & Liu qua Minority Sentinel; cùng kết luận từ work về
positional bias và Context Bagging, nơi bias nằm ở context chung chứ
không phải decoding). Pool mặc định phải đa dạng chiến lược: SQL + Python/
pandas viết độc lập + một plan SQL/grain khác. Bằng chứng đa dạng chất
lượng thắng số lượng: work về test-time augmentation thấy paraphrase
giữ nghĩa cho gain lớn nhất (+1,80pp, tác giả báo cáo) trong khi nhiễu
ký tự tạo bất đồng nhiều hơn (37,8% vs 27,4%) nhưng gain ít hơn.
Nguyên tắc của DiVeRSe (prompt đa dạng + vote có trọng số verifier)
chuyển được; quy mô 100-path của nó thì không.

**Đổi hướng 3 — Đưa cổng xác định lên TRƯỚC vote, và để thiểu số qua
cổng thắng đa số trượt cổng.** Bộ cổng mới E1–E6: fan-out/chasm
(kiểu sqlsure — chỉ README, claim "2.568 gold query, 45 flag, 0 false
alarm" là tự báo cáo, chưa xác minh độc lập ở đây), grain vs grouping
của câu hỏi, cửa sổ thời gian/as-of vs calendar.csv, checklist định
nghĩa doanh thu (VAT/delivery/cancelled/returned), schema linking vs
profiler, và kiểm tra khoảng từ profiler. Consensus 3/3 mà trượt hard
gate thì phải abstain hoặc sửa có mục tiêu, không được trả lời chỉ vì
nó là 3/3.

**Đổi hướng 4 — Thay k=3 cố định bằng adaptive 1 → 3 → 3+1, và thay
resample mù bằng sửa có mục tiêu.** Tier 1: một candidate greedy; trả
lời ngay chỉ khi mọi cổng qua và câu hỏi rủi ro thấp (không JOIN+SUM,
không cửa sổ phức tạp). Tier 2: pool đa dạng chiến lược 3. Tier 3: tối
đa một lần sửa, chỉ khi có thông điệp lỗi cụ thể (lỗi thực thi, output
rỗng bất thường, cổng named failure) — không bao giờ resample chỉ vì
bất đồng. Abstain ngay khi: mọi candidate trượt cùng một hard gate,
P(đúng) đã calibration của verifier dưới ngưỡng đã khóa, hoặc không
candidate nào qua cổng. Bằng chứng ngược được giữ trong bản nháp: work
về uncertainty-aware budget allocation thấy early-exit theo ngưỡng
**không** tăng accuracy (hard-exit tốt nhất −1,0%; easy-exit tiết kiệm
~20% budget với −1,2%) — nên adaptive được bán như tiết kiệm compute,
không phải tăng accuracy; accuracy phải đến từ đa dạng + cổng +
verifier.

**Ngân sách: không dùng số break-even 24s/candidate của repo làm số duy
nhất.** Nó giả định song song 2 GPU hoàn hảo (η=2). Với speedup hiệu
dụng η, break-even cho k=3, N=600 (N là giả định của user, không phải
kích thước private đã xác minh) là 12s ở η=1, 18s ở η=1,5, 24s ở η=2.
Lập kế hoạch với η=1,5 và kiểm tra trần an toàn ở η=1 (phụ thuộc tuần
tự của adaptive đẩy η thực xuống dưới 2; load model, tiền xử lý CPU/
DuckDB và giới hạn batching đều tính). Với tỷ lệ tier minh họa, chưa đo
(50% Tier 1, 30% Tier 2, 15% Tier 3, 5% abstain sau Tier 2), số candidate
trung bình giảm từ 3,00 xuống 2,15 (~28% tiết kiệm); ở t_gen=10s,
N=600, đó là 3,58h ở η=1 so với 5,00h của k=3 cố định — biến thể duy nhất
trên vừa ngân sách ở η=1. Nếu N là 1.000 thì k=3 cố định ở η=1 là 8,33h
(vượt ngân sách).

**Vote vs execution-selector vs learned verifier, mỗi cái một dòng:**
vote output rẻ nhất nhưng mù trước lỗi tương quan; selector kiểu CodeT
chỉ thắng vote nếu "test" của nó là assertion xác định từ rulebook/
profiler (test do LLM sinh chia sẻ bias của generator); verifier kiểu
LEVER chỉ thắng vote nếu nó không phải cùng LLM tự chấm mình (tự đánh
giá kiểu Kadavasth có calibration trung bình nhưng không độc lập) —
do đó mới đề xuất verifier nhỏ không phải LLM.

**Thí nghiệm nhỏ nhất (cùng train holdout tách business, cùng
generator):** các arm A0 (1 greedy + cổng) → A1 (k=3 seed-only + vote) →
A2 (k=3 đa dạng chiến lược + vote) → A3 (A2 + selector dựa assertion) →
A4 (A2 + verifier logistic) → A5 (adaptive với A4). Báo PA, coverage,
selective accuracy, agree-but-wrong rate, oracle rate (lỗi sinh vs lỗi
chọn), PA theo business, ECE, giây/câu. Quy tắc chọn định trước trong
bản nháp: giữ arm đơn giản hơn trừ khi verifier thắng > 0,02 PA trên
holdout; chỉ nhận adaptive nếu giữ PA trong 0,01 của A4 với k trung
bình ≤ 2,5.

**Chưa đủ bằng chứng (ghi UNVERIFIED trong bản nháp):** mọi số PA/gain/
ECE (không chạy thực nghiệm ZAIC nào ở đây); agree-but-wrong rate thật,
tỷ lệ tier, t_gen, thời gian load model, η thật và N của private; verifier
logistic có chuyển qua business khác không; second path Python có thật
sự độc lập với path SQL không; diễn giải rulebook "any-returned orders"
(mức đơn hay mức dòng, để cho P3/P5); sqlsure có được phép trong Docker
DataMate không; và jury cross-model không khả thi dưới cap 15B (chỉ
dùng làm nguyên tắc decorrelation).

## 5. Ưu tiên 5 — DataMate: chứng minh thiếu dữ liệu khác pipeline chưa tìm ra
Bản đầy đủ: `../research/round3-p5-evidence-of-absence.md`

**Đổi hướng 1 — Đảo ngược thứ tự quyết định: `unanswerable` không còn
là lá đầu tiên của cây §5.2.** Cây hiện tại kết luận `unanswerable`
trước khi sinh code từ "bảng/cột/rule yêu cầu bị thiếu". Về hình thức
(ABISS, §3, Definitions 2–3), unanswerable nghĩa là `f(q,D,K) = ∅` —
không tồn tại chương trình hợp lệ — và một lần planner thất bại chỉ
chứng minh "planner này chưa tìm ra", không phải tập đó rỗng. Kết luận
đắt như vậy chỉ được đưa ra sau checklist E0–E8 (§4 bản nháp), bao gồm
ít nhất một probe query đã thực thi. Kiểm tra schema trước code trở
thành màn lọc, không phải phán quyết.

**Đổi hướng 2 — Abstain thành mặc định khi không chắc chắn.** Dưới PA
(+1/0/−1) và giả định vẫn UNVERIFIED đằng sau gaps.md Q-D2 (một
`unanswerable` sai tốn −1, như đáp án sai), abstain không bao giờ mất
điểm trong khi `unanswerable` sai thì mất. Nên checklist chưa hoàn tất
(timeout giữa chừng, pass linking thứ hai chưa chạy, profiler chưa đầy
đủ) phải rơi về abstain, không bao giờ về `unanswerable`. Bản nháp thêm
một cổng đo được cho việc này: chỉ đưa `unanswerable` khi false-absence
rate trên train_cal kéo theo P(thật sự unanswerable | checklist âm) >
0,5, đúng break-even của PA.

**Đổi hướng 3 — Cứu đáp án 0/rỗng: rule "output rỗng → abstain" hiện tại
đang mất điểm.** COUNT(*) trên tập rỗng luôn trả một dòng = 0, nên
COUNT = 0 phải trả lời trực tiếp. SUM/AVG trên tập rỗng trả NULL, không
được tự đổi thành 0 cũng không được tự thành `unanswerable` (abstain
trừ khi rulebook của split định nghĩa 0). Đáp án list `[]` chỉ hợp lệ
khi probe coverage chứng minh entity tồn tại và khoảng thời gian nằm
trong phạm vi dữ liệu; còn không thì list rỗng có thể chỉ là filter sai
→ abstain. Bằng chứng ngược đã gắn cờ: chính ABISS yêu cầu ground-truth
không rỗng khi validate — đó là rule xây benchmark, **không được**
nhập vào DataMate, nơi 0/`[]` là đáp án hợp lệ.

**Đổi hướng 4 — Cấm yêu cầu do planner tự bịa.** Mọi item "yêu cầu"
trong kiểm tra schema phải truy vết được tới token của câu hỏi hoặc
điều khoản rulebook, và trace phải được log. Nếu lý do duy nhất của nó
là "plan của tôi cần cột này" thì xóa khỏi danh sách yêu cầu. Trước bất
kỳ phán quyết "thiếu cột" nào, search suy ra là bắt buộc, theo thứ tự:
alias trong README → công thức trong rulebook → đường join (FK, rồi
value join) → aggregation trên bảng chi tiết → join date-part/calendar.
Ca false-absence phổ biến nhất ở DataMate chính là đây: không có cột
"revenue", nhưng revenue suy ra được bằng tổng tiền dòng sau chiết khấu
dòng, loại đơn hủy/đơn có hàng trả (theo rulebook mặc định của repo).

**Đổi hướng 5 — Mơ hồ ≠ thiếu.** Nếu ≥ 2 chương trình không tương đương
cùng khớp câu hỏi mà rulebook không phân giải được (ABISS `|f| ≥ 2`:
hai cột cùng tên, "recent" mơ hồ, định nghĩa rulebook mâu thuẫn) thì
quyết định là abstain kèm cả hai cách đọc đã log — không phải
`unanswerable`, và không đoán cách đọc phổ biến nhất. Consensus k=3
không bác bỏ được mơ hồ, vì cả ba candidate có thể chia sẻ cùng cách
đọc mặc định.

**Đổi hướng 6 — Schema linking cần hai pass độc lập, không phải một
fallback.** Một lần shortlist trượt + một lần fallback full-schema vẫn
chỉ là ý kiến của một pipeline. Checklist yêu cầu hai route linking độc
lập (ví dụ shortlist vs quét lexical full-schema, cộng check README/
alias) đều âm trước khi claim thiếu; route thứ hai tìm ra cột thì ca đó
được phân loại lại thành lỗi linking (b), không phải thiếu (a).

**Taxonomy (kèm test phân biệt cho mỗi loại):**
- **(a) Thật sự thiếu** — khái niệm không có trong dữ liệu và rulebook,
  không suy ra được; gồm hai sub-case của ABISS, thiếu entity/attribute
  và thiếu relationship (cả hai bảng đều có nhưng không có join). Loại
  duy nhất được kết luận `unanswerable`, và chỉ sau E0–E8.
- **(b) Lỗi linking** — cột tồn tại dưới tên/alias/sheet khác; route
  linking thứ hai tìm ra.
- **(c) Suy ra được** — không có cột trực tiếp, nhưng tính được qua
  công thức/join/aggregation/calendar (như trên).
- **(d) Không có giao dịch** — phạm vi tồn tại, 0 dòng; xử lý theo §3
  trên (COUNT→0, SUM-NULL→abstain trừ khi rulebook định 0, list→`[]`
  chỉ với probe coverage dương).
- **(e) Query lỗi/timeout** — luôn abstain; probe query tối thiểu
  (ví dụ `COUNT(*)` trên bảng, hoặc bóc từng lớp filter) tách "query
  sai" khỏi "dữ liệu thiếu".
- **(f) Mơ hồ nghiệp vụ** — abstain kèm các cách đọc đã log (như trên).

**Thí nghiệm nhỏ nhất (chỉ train, không GPU/model):**
1. **Test zero (tiên quyết):** giải nén zip train thật và xác nhận
   `answers.jsonl` null thật sự nghĩa là gold-unanswerable — nếu không
   thì mọi thí nghiệm dưới đây phải thiết kế lại.
2. Ma trận nhầm lẫn của policy §5.2 hiện tại trên train_holdout, báo
   trên hết **false-absence rate** và **abstain-on-COUNT=0/list-empty
   rate**.
3. Ablation: chuyển mọi phán quyết `unanswerable` ở bước 1 thành
   abstain, đo thay đổi PA — nếu PA tăng thì cây hiện tại đang chủ động
   mất điểm vì false absence.
4. Gán nhãn tay 30–50 câu gold-unanswerable vào taxonomy (a)–(f) để học
   phân phối thật (nếu đa số là (b)/(c) thì linking + derivation search
   là ưu tiên hàng đầu, không phải tuning ngưỡng).
5. Test probe rỗng có kiểm soát trên câu gold-0/`[]` (bóc filter từng lớp).

**Chưa đủ bằng chứng (không coi là luật):**
- **Q-D2 — unknown có impact lớn nhất:** `unanswerable` sai tính bao
  nhiêu điểm. Nếu tốn 0 như abstain thì cổng E8 nghiêm ngặt có thể nới;
  nếu −1 thì bắt buộc.
- Gold ZAIC có coi câu mơ hồ là `unanswerable` không (nếu có thì
  "mơ hồ → abstain" mất +1 trên private và cần xem lại khi đọc được
  evaluator).
- Rulebook của split có định nghĩa 0 cho SUM rỗng không, và field
  `alias` của train có tồn tại trên private không.
- False-absence rate kiểu leave-one-business-type-out (private gồm
  business type chưa thấy; chất lượng README dao động từ dictionary đầy
  đủ tới gần rỗng theo repo), có thể tệ hơn holdout ngẫu nhiên.

## 6. Kiểm chứng đợt này (lệnh, kết quả, phần chưa kiểm chứng)

Môi trường chạy test: Python 3.12.3, jsonschema 4.10.3, duckdb 2.0.0,
pandas 3.1.0, openpyxl 3.1.5, rapidfuzz 3.14.6 (cài trong venv riêng,
không commit vào repo).

```
python3 -m py_compile deep-dives/*.py deep-dives/tests/test_regressions.py
# -> OK
python3 -m unittest discover -s deep-dives/tests
# -> Ran 54 tests in 0.25s, OK
python3 deep-dives/01-constrained-decoding-lifemate.py  # demo: schema + guard
python3 deep-dives/02-asr-grounding-lifemate.py          # demo: grounding + guard
python3 deep-dives/03-duckdb-excel-datamate.py            # demo: VN number + Tet
python3 deep-dives/04-confidence-abstain-datamate.py      # demo: 3 decision paths
# -> tất cả chạy, output khớp kỳ vọng đã sửa (xem cuối mỗi chuyên đề)
```

**Chưa kiểm chứng, ghi rõ không gọi là đã xác minh:**
- vLLM/XGrammar/Outlines trên A30 với schema thật (không có A30, các
  thư viện đó không cài được trong môi trường này — hàm
  `backend_schema_report` trong 01 chỉ liệt kê, không chứng minh).
- Mọi số PA, gain, ECE, latency trong §1–§5 (không chạy trên dữ liệu
  ZAIC; dataset chưa được giải nén trong đợt này).
- Q-L1 (ask scoring), Q-L3 (read có tính F1 không), Q-D2 (unanswerable
  sai tính điểm), rule đếm total-vs-non-embedding, diễn giải cutoff
  cho checkpoint fine-tune, và nội dung zip train thật.
- Các claim SECONDARY/SNIPPET trong 5 bản nháp (xem nhãn trong từng
  bản nháp; synthesis này không nâng cấp chúng).

## 7. Những gì thay đổi so với 8d4721e, tóm tắt một đoạn

LifeMate: bỏ chính sách "không chắc thì hỏi" cho slot có bằng chứng
(thay bằng sửa có kiểm chứng + acoustic rescoring thử trước, contextual
decoding thử sau); tách khác thanh theo có/không đối thủ; grounding
trả (id, string); Qwen3-4B giữ baseline, xLAM/Hammer vẫn A/B với lý do
đã ghi rõ (irrelevance của xLAM-2-3b, licence/date của Hammer), recipe
SFT đổi sang blueprint-first + gold cố định trước + rejection sampling
thay vì SFT trên rollout. DataMate: kiến trúc chốt đầu tiên là
B-trimmed (A đo trước, rồi shortlist + fallback, rồi sửa có điều kiện
kiểu ReFoRCE), không phải C; bỏ selector LLM (CHESS có pass-through;
RSL bước 4 sửa cả kết quả rỗng đúng vì trigger bỏ qua trường error);
bỏ score trọng số 0,5/0,3/0,2
(thay bằng cổng xác định + verifier logistic nhỏ trên đặc trưng quan
sát được); pool candidate đổi từ seed-only sang đa dạng chiến lược;
`unanswerable` bị giáng từ phán quyết trước code xuống kết luận sau
checklist E0–E8, abstain thành mặc định khi không chắc; COUNT=0 được
cứu thành đáp án, SUM-NULL và list rỗng xử lý theo probe. BASE-SQL bị
xóa khỏi danh sách code cần đọc (repo trống); DABstep baseline đã đọc
thật nhưng chỉ lấy được bài học enforcement chỉ-đọc và rule-thành-
assertion.
