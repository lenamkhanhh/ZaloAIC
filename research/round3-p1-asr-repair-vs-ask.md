# Round 3 — Ưu tiên 1: Khi nào sửa ASR, khi nào hỏi lại? (LifeMate)

> Bản nháp nghiên cứu, không phải code, không sửa repo. Mốc so sánh:
> commit `8d4721e` của https://github.com/lenamkhanhh/ZaloAIC.
> Mọi con số lấy từ paper khác đều là **tác giả báo cáo trên tập của họ**,
> không phải số ZAIC. Mọi claim chưa xác minh đều ghi rõ UNVERIFIED.
> Ràng buộc cứng nhắc lại: audio tiếng Việt, toàn hệ thống < 6B tham số,
> LLM < 5B, ≤ 30 giây/mẫu trên 1× A30, Docker fully offline, model phát
> hành trước 26/10/2026.

## 0. Repo đã biết gì, và khoảng trống chính xác là gì

### 0.1. Baseline ở 8d4721e (deep-dives/02-asr-grounding-lifemate.md + .py)

- Chỉ ground **slot quyết định** (find/replace có kiểm chứng), không sửa
  toàn bộ transcript bằng LLM.
- Tầng bằng chứng: EXACT → FUZZY_GROUNDED (điểm RapidFuzz ≥ 88 và hơn
  ứng viên thứ hai ≥ 8) → AMBIGUOUS → UNKNOWN.
- Khác thanh (chỉ khác tone, ví dụ Bình/Bính) → AMBIGUOUS → hỏi lại.
- Mất dấu hoàn toàn (ví dụ `Nguyen Van An`) → UNKNOWN (điểm 84,6 < 88).
- N-best fusion: chọn giả thuyết chứa nhiều substring candidate exact
  nhất, hòa thì giữ giả thuyết đầu tiên.
- Tiền/ngày/ID: chỉ khớp digit chính xác, cấm fuzzy (lưu ý: một đợt sửa
  code song song đang tách quy tắc "digits only" này thành chuẩn hóa
  theo từng loại slot — bản nháp này không giả định đợt sửa đó đã xong,
  và các đề xuất dưới đây tương thích với cả hai dạng).
- Phủ định: guard code chặn write mâu thuẫn, N-best mâu thuẫn về cue
  phủ định → chặn + hỏi.

### 0.2. Khoảng trống (đây là thứ đợt này phải lấp, không phải viết lại §0.1)

1. **Không có bằng chứng âm thanh nào** trong quyết định: mọi ngưỡng đều
   là text similarity (RapidFuzz). Một span ASR tự tin sai và một span
   ASR không chắc chắn được đối xử giống nhau nếu điểm text bằng nhau.
2. **Không có cơ chế decode-time biasing**: candidate chỉ xuất hiện sau
   ASR, chưa bao giờ ảnh hưởng tới quá trình decode.
3. **Không phân biệt các trường hợp khác thanh**: "chỉ khác thanh, không
   có đối thủ" và "chỉ khác thanh, đối thủ cũng chỉ khác thanh" đang bị
   gộp chung thành AMBIGUOUS → hỏi.
4. **Không phân biệt trùng tên**: ground trả về chuỗi giá trị, không trả
   về id của candidate. Hai contact cùng tên nhưng khác id là trường hợp
   mà tầng hiện tại không có đáp án đúng nào ngoài hỏi.
5. **Không có quy tắc cho số đọc bằng chữ, tiền có đơn vị, ngày tương
   đối, tên viết tắt** — các dạng này không nằm trong bảng §5 của
   chuyên đề 2.
6. **Chưa từng đo**: ngưỡng 88/biên 8/trần 85 là điểm khởi đầu đề xuất;
   chưa có slot-error theo loại trên train held-out.

### 0.3. "Candidate chỉ từ tool read" là luật hay lựa chọn thiết kế?

**Kết luận: lựa chọn thiết kế của repo, KHÔNG phải luật chính thức đã
ghi nhận.** Bằng chứng:

- `deep-dives/02-asr-grounding-lifemate.md` §1 tự ghi rõ: "Đây là ràng
  buộc của thiết kế này, không phải giới hạn của các paper được trích".
- `competition/lifemate.md` (ghi nhận kiểm tra portal sau đăng nhập ngày
  2026-10-26) liệt kê các cấm chính thức: đọc trực tiếp `state.json`
  hoặc file dưới `<split>_environment/`; mọi đọc/ghi phải qua
  `zaic_tools`, đúng 1 ToolEnv mỗi mẫu, mọi call trên ToolEnv đó phải
  xuất hiện trong submission. **Không có dòng nào cấm dùng user context,
  history, installed_apps, hay danh sách ứng viên có trước khi decode
  làm biasing.**
- Hạn chế thật sự, và là hạn chế chính thức, nằm ở chỗ khác: mọi read
  đều là tool call, và việc read có tính vào F1 không, read thừa có bị
  trừ không, failed call có phải nộp không — đều là câu hỏi mở Q-L2/Q-L3
  trong `gaps.md`, UNVERIFIED. Vì vậy, dùng context có sẵn (installed
  apps, history, user context) để biasing thì không vi phạm luật đã ghi
  nhận; nhưng **đọc thêm một lượt read chỉ để lấy candidate cho biasing
  thì có chi phí F1 chưa biết** — đó là lý do biasing nên ưu tiên nguồn
  không tốn read trước (context/history), và chỉ dùng read khi đã có
  transcript vòng 1.
- Lưu ý kiểm chứng dở dang: lần fetch lại trang portal LifeMate trong
  đợt này **thất bại do lỗi mạng (không phải do bị chặn truy cập)** và
  theo chỉ dẫn thì không thử lại URL đó; vì vậy phần này dựa trên ghi
  nhận portal 2026-10-26 trong repo, không phải kiểm tra portal mới
  trong đợt này. Nếu portal/regulations có điều khoản khác, kết luận
  trên phải viết lại.

## 1. Nguồn đã đọc thật (mức đọc ghi rõ từng nguồn)

| # | Nguồn | Đã đọc tới mức nào | Dùng cho |
|---|---|---|---|
| S1 | RECOVER, Kumar & Sachdeva, arXiv 2603.16411 — https://arxiv.org/pdf/2603.16411 | **Paper toàn văn** §§1–5, Bảng 2–3 (đọc qua bản PDF). | Khung Fuse → Propose → Verify; candidate scoring 3 tín hiệu; 4 chiến lược fusion; bằng chứng chống merge. |
| S2 | DeRAGEC, Im et al., arXiv 2506.07510 — https://arxiv.org/html/2506.07510v1/ | **Paper toàn văn** §§3–4 (đọc qua bản HTML). | Denoise trước khi sửa; phonetic score bằng Epitran + Panphon; MCQ + rationale; ablation PS/Def. |
| S3 | DeRAGEC repo — https://github.com/solee0022/deragec | **Root listing + README, commit fedc1690b7229dec601b8352fb120b7ad998dede, branch main** (19 commits). File `inference_filtering.py`, `inference_gec.py`, `utils/`, `templates/`, `fewshots/` có tồn tại; **thân file chưa đọc từng dòng trong đợt này** — các chi tiết về `inference_filtering.py` 122–139 và `utils/formatting_mcq.py` lấy từ tóm tắt code DeepWiki, ghi là SECONDARY. | Cấu trúc 2 giai đoạn filter → GEC; format MCQ `(score \| def)`; model dùng trong paper (Llama-3.1-70B, GPT-4o-mini) — vượt ngân sách, xem §5. |
| S4 | CoVoGER, Yang et al., EMNLP 2025 — https://preview.aclanthology.org/bulk-verifications-2026-03-01/2025.emnlp-main.320/ (Anthology ID 2025.emnlp-main.320) | **Abstract** (trang preview chỉ trả abstract, không trả full text). Repo https://github.com/N-Orien/CoVoGER: **root listing, commit bb6400c6fac5018067dd203999a531fd653041ee, branch main** — có `generate/`, `finetune/`, `inference/`; **thân code generate chưa đọc từng dòng trong đợt này.** | Mixture decoding (beam + temperature sampling) cho 5-best; kết luận "mixture tốt nhất cho GER trong đa số setting" ở mức abstract, chưa đủ để lấy tham số cụ thể. |
| S5 | faster-whisper API (SYSTRAN) — https://deepwiki.com/SYSTRAN/faster-whisper/9.1-whispermodel-api và /4.1-whispermodel | **Tóm tắt code SECONDARY** (DeepWiki trích `faster_whisper/transcribe.py` 747–1022, 1522–1621). Chưa đọc raw file trong đợt này. | `initial_prompt`, `hotwords` (bị bỏ qua nếu đặt `prefix`), `word_timestamps`, ngưỡng `avg_logprob`/`log_prob_threshold`/`no_speech_threshold`, `condition_on_previous_text`. |
| S6 | Epitran — https://pypi.org/project/epitran/1.20/ và DeepWiki mapping files https://deepwiki.com/dmort27/epitran/5.1-mapping-files | **SECONDARY**: danh sách ngôn ngữ có `vie-Latn`; file `epitran/data/map/vie-Latn.csv` tồn tại; tone được biểu diễn bằng ký hiệu IPA (˧, ˧˥, ˧˩, ˧˩˧). Chất lượng map tiếng Việt cụ thể **chưa đọc từng dòng**. | G2P tiếng Việt có tone — nền tảng cho phonetic similarity thay cho Double Metaphone tiếng Anh. |
| S7 | ROVER / MBR / consensus decoding — https://pypi.org/project/unisson/ (consensus + MBR selection) và bài giảng Cambridge về MBR | **SECONDARY, mức tóm tắt.** | Định nghĩa consensus: alignment + majority vote theo cột; MBR = chọn hypothesis có kỳ vọng loss thấp nhất so với các hypothesis còn lại. |
| S8 | N-best rescoring cho Whisper (INTERSPEECH, GPT-2 rescoring + ILME) — https://arxiv.org/pdf/2306.01942 | **Snippet-level** (chỉ đoạn công thức và phương pháp qua kết quả tìm kiếm, chưa đọc full paper). | Công thức rescore: log P_Whisper(Y\|X) − λ_ilm·log P_ilm(Y) + λ_GPT2·log P_GPT2(Y); internal LM ước lượng bằng cách forward Whisper với encoder output bằng 0. |
| S9 | Text-constrained acoustic rescoring (teacher-forced likelihood) — kết quả tìm kiếm trỏ tới bản mirror arxiv.cnoctave.top của arXiv 2609.30924 | **Snippet-level, UNVERIFIED** (chưa đọc full paper; URL là mirror, không dùng làm trích dẫn chính). | Ý tưởng: điểm acoustic của một candidate = negative log-likelihood khi teacher-forcing transcript chứa candidate đó; dùng margin check để chấp nhận/từ chối. |
| S10 | Repo ZAIC: `competition/lifemate.md`, `deep-dives/02-*.md/.py`, `gaps.md` (Q-L1..Q-L6), `research/lifemate/*` | **Đã đọc trực tiếp từ local clone ở 8d4721e.** | Baseline, luật đã ghi nhận, câu hỏi evaluator còn mở. |

**Không tìm thấy code công khai của RECOVER trong đợt này.** Paper S1
trích framework Agno làm orchestration, nhưng các kết quả tìm kiếm không
trả về repo RECOVER. Vì vậy RECOVER được đối xử như **đặc tả paper có
thể cài lại**, không phải code đã đọc. Không ghi CODE_INSPECTED cho
RECOVER.

## 2. Điều các nguồn thực sự nói (kèm bằng chứng ngược)

### 2.1. RECOVER (S1): chọn, đừng merge; guardrail xác định là bắt buộc

- Pipeline: 5 hypotheses từ Whisper-small ở 5 nhiệt độ T ∈ {0, 0.2, 0.4,
  0.6, 0.8} → retrieval top-K (K = 200) bằng 3 tín hiệu:
  `score = n_exact·1.0 + f_best·1.2 + p_hit·0.6`, trong đó `f_best` là
  Levenshtein chuẩn hóa tốt nhất (chỉ xét token lệch ±3 ký tự) và
  `p_hit` là nhị phân: phonetic key của phrase có chung prefix 5 ký tự
  với phonetic key của token nào đó trong hypothesis hay không. Trọng
  số là "set empirically" trên tập của họ — **không phải hằng số chuyển
  giao được sang tiếng Việt**.
- Tool 2 (Propose): LLM chỉ được đề xuất find/replace cho entity, output
  JSON gồm offsets, span gốc, span thay thế, entity type, confidence,
  reason; thay thế phải là một phrase trong entity list; cấm sửa ngữ
  pháp/chính tả/casing chung.
- Tool 3 (Verify & Apply), 5 check xác định: (1) replacement phải có
  trong entity list; (2) bỏ thay đổi chỉ khác casing; (3) nếu offsets
  LLM đưa sai thì relocate span và tính lại offsets; (4) normalised
  Levenshtein similarity giữa span gốc và replacement phải đủ cao
  (ví dụ citeva → cytiva qua, star → cytiva trượt); (5) áp dụng từ
  trái sang phải, bỏ edit chồng lấn với edit trước.
- Kết quả (tác giả báo cáo, GPT-4o làm LLM): LLM-Select nhất quán nhất;
  1-Best + constrained LLM editing đã đạt RWERR 33,2% (Earnings-21),
  41,2% (Common Voice), 20,4% (Medical), 12,7% (ContextASR-Bench). Với
  GPT-4o-mini, RWERR chỉ còn 2,2–15,7% — **bằng chứng ngược quan trọng:
  cùng pipeline, LLM yếu hơn thì lợi ích sụt mạnh**. Qwen3-4B của
  LifeMate gần GPT-4o-mini hơn GPT-4o, nên không được kỳ vọng mức
  RWERR của GPT-4o.
- **Bằng chứng chống merge (quan trọng nhất cho LifeMate):** trên ATCO2
  nhiễu, ROVER Ensemble giảm E-WER (51,50% → 47,39%) nhưng **tăng WER
  tổng 48,63% → 64–66%** do insertion; Entity-Aware Select cũng tăng WER
  trên ATCO2 và ContextASR-Bench. LLM-Select tránh được vì nó **chọn một
  variant nguyên vẹn thay vì merge token**. Với LifeMate, một token
  chèn sai trong write là hash về 0, nên merge là chiến lược rủi ro cao
  nhất, không phải mặc định.
- Cơ chế lỗi chính được sửa là substitution (chiếm 63–93% tổng giảm
  lỗi), không phải deletion/insertion — khớp với bài toán slot của
  LifeMate (tên/số bị đọc sai, không phải bị mất hoàn toàn).

### 2.2. DeRAGEC (S2, S3): denoise trước khi sửa; phonetic score thật

- Khác RECOVER ở chỗ: retrieval từ NE database ngoài (3.003.462 NE từ
  Common Voice train + media entities + Wikipedia), top-10 candidate,
  mỗi candidate gắn `PS` (phonetic similarity, tính bằng Epitran chuyển
  thành IPA rồi Panphon đo khoảng cách theo articulatory features) và
  `Def` (một câu định nghĩa Wikipedia), serialise dạng
  `<n_i | phonetic-score: PS_i | def: Def_i>`.
- Denoising gate là MCQ + rationale tổng hợp: model phải giải thích vì
  sao chọn candidate trước khi chốt; few-shot gồm rationale mẫu. Điểm
  mấu chốt từ ví dụ của họ: **phonetic score cao nhất không luôn là đáp
  án đúng** (ví dụ beecke 0,67 thắng bk 1,00 nhờ ngữ cảnh) — tức là
  "chọn điểm cao nhất" là chính sách sai, cần thêm tín hiệu ngữ nghĩa.
- Ablation (Bảng 1 của paper, Whisper-large-v3-turbo beam 5 làm ASR):
  ASR-only WER 7,7% (CV) / 8,9% (STOP); DeRAGEC đầy đủ 6,0% / 5,9% với
  Llama-3.1-70B; ORACLE (cho ground-truth NE) 5,8% / 5,7% — tức denoise
  của họ gần chạm oracle **trên tập của họ, với model 70B**.
- **Bằng chứng ngược cho LifeMate:** toàn bộ stack đó (70B, GPT-4o-mini,
  o1 làm rationale generator, NE DB 3M, Wikipedia Def, tagger
  GliNER-large) đều vượt ngân sách < 6B/offline/sample-only. Phần chuyển
  giao được chỉ là: (a) **denoise trước khi sửa** (lọc candidate bằng
  tín hiệu độc lập trước khi đưa vào LLM/corrector), (b) **PS là một
  tín hiệu riêng, không thay thế text similarity**, (c) **Def thay bằng
  thuộc tính từ read** (ví dụ phòng của thiết bị, quan hệ của contact —
  *nếu* read trả về các trường đó; UNVERIFIED read trả về trường nào).
  Rationale bằng LLM 4B cho mọi slot là tốn kém và chưa chứng minh tốt
  hơn rule xác định trên tập nhỏ candidate trong sample.

### 2.3. CoVoGER (S4): 5-best hỗn hợp tốt cho GER — nhưng là benchmark, không phải policy

- 5-best list được tạo bằng **mixture của beam search và temperature
  sampling**; kết luận ở mức abstract: mixture cho GER tốt nhất trong
  đa số setting, trên 15 ngôn ngữ (có cả tiếng Việt? — abstract không
  liệt kê ngôn ngữ, UNVERIFIED có tiếng Việt trong 15 ngôn ngữ đó hay
  không, và không có số riêng cho tiếng Việt).
- CoVoGER đánh giá GER bằng LLM rewrite toàn bộ transcript (cả
  commercial zero-shot lẫn open-source LoRA fine-tune) — mục tiêu là
  WER, không phải slot-correctness hay state_hash. Vì vậy nó chứng minh
  **N-best đa dạng có giá trị**, không chứng minh "rewrite toàn câu bằng
  LLM" là đúng cho LifeMate (chuyên đề 2 đã loại rewrite toàn câu vì lý
  do hash, và CoVoGER không bác bỏ lý do đó).

### 2.4. Contextual biasing lúc decode (S5 + RECOVER §1)

- Whisper có sẵn 2 kênh biasing không tốn tham số mới: `initial_prompt`
  (text điều kiện decoder; chỉ ~224 token cuối của prompt có tác dụng
  mạnh nhất, nên prompt phải ngắn và đặt từ quý hiếm ở cuối) và
  `hotwords` trong faster-whisper (boost các phrase; bị bỏ qua nếu đặt
  `prefix`). Đây là biasing **mềm** (soft): nó tăng xác suất token của
  từ trong list, không ép buộc — khác với deep biasing / trie-based
  decoding cho transducer (RECOVER §1 trích dẫn, cần can thiệp decoder
  internals, không áp dụng trực tiếp cho Whisper black-box).
- Bằng chứng ngược từ một pipeline tương tự (Whisper Courtside, tìm
  thấy qua search — ghi là SECONDARY, chưa đọc full): prompt chỉ có
  topic thì thường không sửa được proper noun; prompt có tên thì cải
  thiện rõ nhưng **không có safeguard sẽ overcorrect — chèn tên không
  được nói**. Decider/filter (ngưỡng similarity, giới hạn token) là
  phần bắt buộc, không phải tùy chọn.
- **Bài toán gà-trứng cho LifeMate:** biasing list muốn có candidate từ
  read, nhưng read muốn có transcript vòng 1 để biết cần đọc gì. Nên
  contextual decoding cho LifeMate thực chất là **2-pass**: pass 1
  transcribe thô → đọc candidate → pass 2 decode lại với prompt/hotwords
  từ candidate. Chi phí: ~2× thời gian ASR + chi phí read (F1 chưa biết,
  Q-L3). Nếu pass 1 đã đúng slot thì pass 2 là lãng phí; nên chỉ chạy
  pass 2 khi pass 1 có slot nghi ngờ (điểm thấp, N-best mâu thuẫn, hoặc
  slot không ground được).

### 2.5. Acoustic rescoring: tín hiệu duy nhất tách được "audio nói gì" khỏi "LM thích gì"

- Whisper là conditional LM: điểm decode gộp cả acoustic và LM prior
  nội tại. Hai cách tách đã thấy trong literature:
  - **Teacher-forced acoustic score:** với mỗi transcript biến thể
    (thay span nghi ngờ bằng một candidate), chạy forward Whisper với
    transcript đó làm target và lấy tổng logprob — biến thể nào audio
    ủng hộ hơn sẽ có điểm cao hơn. Đây là cách duy nhất trong danh sách
    này đo trực tiếp "audio có giống candidate này không" mà không cần
    model mới (dùng chính PhoWhisper, 0 tham số thêm; chi phí: 1 forward
    ngắn cho mỗi candidate, rẻ hơn decode lại toàn bộ).
  - **ILME subtraction (S8, snippet-level):** trừ internal LM score
    (ước lượng bằng forward với encoder output bằng 0) khỏi điểm
    Whisper, rồi cộng điểm LM ngoài. Phiên bản tối giản cho LifeMate:
    so sánh **acoustic-only score** (Whisper score − internal LM) giữa
    1-best và candidate variant; nếu candidate thắng về acoustic-only
    dù thua về điểm decode đầy đủ, đó là bằng chứng audio ủng hộ
    candidate mà LM đã lấn át — đúng trường hợp "audio rõ nhưng ASR
    sai" (thường là tên hiếm: LM prior thấp nên decoder chọn từ quen
    thuộc hơn).
- **Giới hạn:** cả hai cách đều dùng cùng một model đã sai, nên chúng
  không độc lập hoàn toàn với lỗi gốc. Chúng chỉ có giá trị khi **kết
  hợp** với text/phonetic: một candidate chỉ được sửa khi ít nhất 2
  trong 3 tín hiệu (acoustic, phonetic, textual) đồng thuận. Một tín
  hiệu đơn độc — kể cả acoustic — không đủ cho write.
- **Confidence của ASR (S5):** faster-whisper cho `avg_logprob` theo
  segment và `probability` theo word (khi bật word_timestamps). Đây là
  tín hiệu rẻ nhất để phát hiện span nghi ngờ, nhưng **không phải xác
  suất đúng**: Whisper có thể tự tin sai với tên hiếm (LM prior cao cho
  từ quen). Vì vậy confidence chỉ dùng để **chọn span cần kiểm chứng**,
  không dùng để **chốt sửa hay hỏi**.

## 3. Xử lý từng loại slot khó (quy tắc đề xuất, chưa đo)

### 3.1. Tên chỉ khác thanh — tách thành 3 trường hợp, đừng gộp

| Trường hợp | Ví dụ | Quyết định đề xuất |
|---|---|---|
| Khác thanh, **không có đối thủ** trong candidate list (chỉ một Bình, không có Bính) | ASR "Bính", contacts chỉ có "Bình" | **Ứng viên sửa, không hỏi ngay**: kiểm tra acoustic rescore của "Bình" vs "Bính" + phonetic distance (Epitran: chỉ khác tone marker). Nếu acoustic ủng hộ "Bình" (hoặc ít nhất không thua rõ) → sửa thành "Bình". Chỉ hỏi khi acoustic cũng mâu thuẫn. Lý do: hỏi ở đây gần như chắc chắn mất mẫu (xem §6 về hash), trong khi sửa có bằng chứng 2 tín hiệu. |
| Khác thanh, **có đối thủ cũng chỉ khác thanh** (cả Bình và Bính đều có trong contacts) | ASR "Bính", contacts có cả hai | **BẮT BUỘC hỏi** (hoặc dùng slot phân biệt khác nếu có, ví dụ số điện thoại đi kèm, phòng, quan hệ). Không có cách text/acoustic nào phân biệt hai người này nếu audio thật sự mơ hồ về thanh; nếu acoustic rescore phân biệt rõ (một variant thắng với margin lớn) thì có thể sửa, nhưng margin này phải hiệu chuẩn trên train, không đặt tay. |
| Khác thanh nhưng **ASR đã đúng thanh, candidate sai thanh** | Không xảy ra theo định nghĩa: candidate là ground truth từ read, ASR mới là phía có thể sai. Nếu read trả về tên không dấu hoặc sai dấu (UNVERIFIED read có chuẩn dấu hay không) thì toàn bộ giả định "candidate là canonical" sụp — phải kiểm tra chất lượng dấu của read trên train trước khi khóa chính sách này. |

Hệ quả: **quy tắc "khác thanh → AMBIGUOUS" hiện tại là quá thô**. Nó
đúng cho trường hợp có đối thủ, sai (quá bảo thủ) cho trường hợp không
đối thủ.

### 3.2. Trùng tên — ground phải trả về id, không phải chuỗi

- Hiện tại `ground_slot()` trả về `value` là chuỗi; `Candidate` có field
  `key` nhưng ground không dùng nó để phân biệt. Với hai contact cùng
  tên "Nguyễn Văn An" khác id, mọi chính sách text đều bó tay.
- Quy tắc mới: **grounding là ánh xạ span → (candidate id, chuỗi
  canonical)**. Nếu hai candidate có cùng chuỗi chuẩn hóa NFC nhưng khác
  id → AMBIGUOUS vĩnh viễn ở tầng text, chỉ giải quyết bằng: (a) slot
  phụ đi kèm trong câu (số điện thoại, ngân hàng, phòng, quan hệ); (b)
  history (người vừa nhắc tới); (c) hỏi. Nếu không có (a)/(b) thì hỏi —
  và ghi rõ: đây là trường hợp hỏi **đúng nghĩa** (thông tin phân biệt
  không có trong audio), khác với hỏi vì ASR nhiễu.
- UNVERIFIED: `sys.ask_missing_info` có cho phép hỏi "An nào?" với lựa
  chọn kèm theo hay chỉ hỏi tên slot (Q-L1). Nếu format ask không mang
  được lựa chọn, trùng tên không có slot phụ đồng nghĩa với mẫu đó
  không cứu được bằng ask — vẫn hỏi (vì đó là hành động đúng về mặt
  task), nhưng kỳ vọng điểm của mẫu đó là 0.

### 3.3. Tên viết tắt, biệt danh, tên rút gọn

- Dạng: "anh An" cho "Nguyễn Văn An"; "VCB" cho "Vietcombank"; "đèn
  phòng khách" nói thành "đèn khách" (UNVERIFIED các dạng này có trong
  dữ liệu ZAIC hay không — cần đếm trên train).
- Quy tắc: viết tắt chỉ được ground khi **duy nhất một candidate** khớp
  với dạng rút gọn đó theo một quy tắc tường minh, có thể kiểm chứng
  (ví dụ: initials của các từ trong tên; substring là một từ đầy đủ
  trong tên; tên app trong `installed_apps`). Nếu quy tắc rút gọn cho ra
  ≥ 2 candidate → AMBIGUOUS → hỏi. **Tuyệt đối không để LLM tự bịa bảng
  alias** (ví dụ đoán "VCB = Vietcombank" khi không có bằng chứng trong
  sample là đoán, dù đoán đó có vẻ hiển nhiên với người Việt — vì
  "VCB" cũng có thể là một tên khác trong sample).
- Nguồn alias hợp lệ duy nhất (theo thứ tự): (1) trường alias nếu read
  trả về (UNVERIFIED); (2) `installed_apps`/history trong context; (3)
  quy tắc initials/substring duy nhất; (4) hỏi.

### 3.4. Số đọc bằng chữ, tiền có đơn vị, ngày tương đối

- **Số đọc bằng chữ:** ASR có thể trả "một trăm năm mươi nghìn" hoặc
  "150000" hoặc "150 nghìn" cho cùng một giá trị. Cả hai phía (raw span
  và candidate) phải chuẩn hóa về **cùng một Decimal** trước khi so
  sánh, với bảng đơn vị tường minh: nghìn/ngàn = 10³, triệu = 10⁶, "k"
  = 10³, "rưỡi" = +0,5 đơn vị đứng trước nó (ví dụ "hai triệu rưỡi" =
  2.500.000). Cặp nhầm kinh điển "mười lăm" (15) vs "năm mươi" (50) phải
  được test riêng: chúng khác nhau cả về phonetic lẫn text, nên acoustic
  rescore là tín hiệu phân biệt chính, không phải fuzzy text.
- **Tiền có đơn vị:** đơn vị là một phần của giá trị, không phải hậu tố
  trang trí. "150 nghìn" ≠ "150" ≠ "150 triệu". Chuẩn hóa phải giữ đơn
  vị (nhân hệ số) rồi mới so sánh — đúng hướng với đợt sửa code song
  song (typed money), và là lý do quy tắc digits-only cũ sai.
- **Ngày tương đối:** "ngày mai", "tuần sau", "hôm qua", "cuối tuần
  này", "thứ hai tới" chỉ có nghĩa khi biết **ngày tham chiếu**. Ngày
  tham chiếu lấy từ đâu là UNVERIFIED: sample context có trường ngày
  hiện tại hay không chưa được ghi nhận trong `competition/lifemate.md`.
  Quy tắc: nếu có ngày tham chiếu từ context (không phải đoán) → tính
  toán xác định rồi ground như ngày tuyệt đối; nếu không có → đây là
  **thông tin thiếu thật sự → hỏi**, không được lấy ngày hệ thống lúc
  chạy Docker làm ngày tham chiếu (ngày chạy private test khác ngày
  ghi sample, và reproducibility 5 lần chạy sẽ vỡ nếu dùng wall-clock).
- **Số tài khoản/số điện thoại đọc bằng chữ:** chuyển về chuỗi chữ số
  rồi so exact như ID; một chữ số sai → UNKNOWN (không fuzzy), kể cả
  khi acoustic ủng hộ — vì với ID, "gần đúng" vẫn là tài khoản khác.

### 3.5. Kết hợp ASR confidence, N-best và tool-read context — bảng quyết định

Không dùng một score tổng hợp tự bịa. Dùng **bảng 3 tín hiệu độc lập**:

| Tín hiệu | Lấy từ đâu | Vai trò |
|---|---|---|
| Text similarity | RapidFuzz trên NFC giữ dấu (hiện có) | Ứng viên ban đầu; không bao giờ đủ một mình cho sensitive slot |
| Phonetic distance | Epitran vie-Latn → IPA (có tone) + Panphon articulatory distance (mới, 0 tham số model) | Phân biệt khác thanh vs khác phụ âm/vần; phân biệt "Bình/Bính" (chỉ khác tone marker) với "Nam/Lam" (khác phụ âm đầu) |
| Acoustic score | Teacher-forced Whisper logprob của transcript biến thể (cùng PhoWhisper, 0 tham số thêm) | Bằng chứng duy nhất gắn với audio; dùng để phá vỡ hòa giữa các candidate text-gần-nhau |
| N-best agreement | Tỉ lệ hypothesis chứa span/candidate (RECOVER entity-hit counts) | Đo độ ổn định của ASR; agreement 5/5 + confidence cao + vẫn sai = trường hợp LM-bias, cần acoustic-only check |
| ASR confidence | `avg_logprob` segment + word `probability` (faster-whisper) | Chỉ để **chọn span nghi ngờ** (đi kiểm chứng), không để chốt |

**Luật kết hợp đề xuất (chưa đo, cần hiệu chuẩn):**

- Slot tên/thiết bị: sửa khi **≥ 2/3 tín hiệu** (text, phonetic,
  acoustic) đồng thuận về cùng một candidate VÀ candidate đó duy nhất
  (không có đối thủ cùng thỏa). 1/3 → hỏi (hoặc giữ 1-best nếu span đó
  không phải slot quyết định — nhưng với LifeMate, slot nào trong write
  cũng là quyết định).
- Slot nhạy cảm (tiền/ngày/ID): sửa khi **typed-exact + acoustic đồng
  thuận**; text/phonetic không bao giờ đủ một mình, và fuzzy text không
  bao giờ được dùng.
- Phủ định: giữ nguyên guard hiện tại (code, không fuzzy). Thêm một
  ngoại lệ: N-best agreement 5/5 **không** ghi đè guard phủ định — vì
  rớt "không" có thể là lỗi hệ thống (từ ngắn, không trọng âm), agreement
  cao không chứng minh "không" thật sự không có trong audio; chỉ
  acoustic check trên đoạn audio chứa cue (nếu có word timestamps) mới
  có thể bác bỏ cue, và việc này UNVERIFIED về mặt triển khai.

## 4. So sánh 4 kiến trúc

| | (A) 1-best + text matching (baseline hiện tại) | (B) Contextual decoding (biasing lúc decode) | (C) N-best / acoustic rescoring | (D) Verified correction (RECOVER-adapted, deterministic selector) |
|---|---|---|---|---|
| Luồng | ASR greedy → ground text → tool | Pass 1 → read/context → pass 2 với initial_prompt/hotwords → ground | N-best (beam/temp) → rescore bằng Whisper logprob / acoustic-only → chọn variant | N-best → retrieval 3 tín hiệu → propose (rule, không LLM) → Verify&Apply xác định |
| Bằng chứng dùng | Text duy nhất | Audio + context (nhưng soft, không đảm bảo) | Audio (logprob) + text | Audio + text + phonetic + read candidate |
| Sửa được gì | Tên gần giống text; số exact | Tên hiếm mà LM hay đọc sai, **nếu** tên có trong prompt | Tên mà LM chọn sai dù audio ủng hộ candidate khác | Mọi loại trên, nhưng chỉ trong candidate list |
| Không sửa được | Tên bị LM đọc sai tự tin; tên hoàn toàn vắng mặt khỏi 1-best mà text không gợi ra | Tên không có trong context/read; tên ngoài prompt cap (~224 token) | Tên không xuất hiện trong bất kỳ hypothesis nào và không có trong candidate list | Entity không có trong read (đúng theo thiết kế, nhưng là giới hạn) |
| Rủi ro chính | Sửa sai do text gần giống; bỏ lỡ do ngưỡng cứng | **Overcorrection**: chèn tên không được nói; 2-pass tốn thời gian + read cost (Q-L3) | Rescore dùng cùng model đã sai → không độc lập hoàn toàn; N-best từ faster-whisper không expose trực tiếp (xem §7) | Phức tạp nhất; nếu selector là LLM 4B thì lợi ích sụt (bằng chứng RECOVER mini); nếu selector là rule thì mất khả năng sửa ngoài list |
| Chi phí tính toán | ~0 (CPU fuzzy) | ~2× ASR + 1 LLM call (nếu có) | N× decode (temp sampling) hoặc N forward teacher-forcing (rẻ hơn) | N× decode + retrieval CPU + 0–1 LLM call (nếu dùng LLM propose; bản deterministic thì 0) |
| Phù hợp ngân sách <6B/30s? | Có, rẻ nhất | Có, nếu chỉ pass 2 cho mẫu nghi ngờ | Có, nếu N ≤ 5 và teacher-forcing thay cho decode lại | Có, nếu propose bằng rule (không LLM) |
| Điểm yếu chí tử với hash | Ground sai = hash 0, không cứu được | Prompt chèn sai tên = write sai = hash 0 | Chọn variant sai = toàn bộ transcript sai theo | Sửa ngoài list = đoán; sửa sai = hash 0 |

**Đọc bảng này theo cách đúng:** (A) là sàn, không phải đích. (D) là
khung tổ chức đúng (nó chứa (C) như một bước), (B) là bổ sung có điều
kiện, không phải thay thế. Đừng đọc "RECOVER tốt nhất" thành "cần
LLM-Select": trong RECOVER, LLM-Select tốt nhất **với GPT-4o**; với
Qwen3-4B, phần LLM của pipeline là phần yếu nhất, nên (D) cho LifeMate
phải là **deterministic selector + rule proposer**, không phải LLM
proposer.

## 5. Đáng thử trước: thứ tự và lý do

**Thử trước: (D) với deterministic selector, tích hợp (C) làm bước
rescore, trên nền (A).** Cụ thể, theo thứ tự triển khai:

1. **Sửa 3 lỗi chính sách của baseline trước khi thêm model mới** (rẻ,
   không tốn tham số, thay đổi kỳ vọng điểm ngay):
   - (a) Ground trả về **(id, chuỗi)** và trùng tên cùng chuỗi → AMBIGUOUS.
   - (b) Khác thanh không đối thủ → ứng viên sửa có điều kiện (acoustic
     + phonetic), không auto-hỏi; khác thanh có đối thủ → bắt buộc hỏi.
   - (c) Mất dấu: không auto-UNKNOWN; nếu dạng không dấu của raw khớp
     duy nhất một candidate sau khi so sánh cả dạng không dấu **và**
     phonetic (Epitran) **và** acoustic không phản đối → sửa; ngược lại
     hỏi.
2. **Thêm phonetic signal (Epitran vie-Latn + Panphon)** cho retrieval
   và cho bước Verify. 0 tham số model, CPU thuần, offline. Đây là phần
   mới có giá trị cao nhất trên chi phí: nó là thứ duy nhất phân biệt
   được "khác thanh" với "khác phụ âm" một cách có cơ sở ngôn ngữ, thay
   vì heuristic tách thanh hiện tại.
3. **Thêm acoustic rescore bằng teacher-forcing** cho các slot còn
   tranh chấp (không phải cho mọi mẫu). 0 tham số thêm, dùng chính
   PhoWhisper. Đây là bước duy nhất có thể cứu trường hợp "audio rõ
   nhưng ASR sai".
4. **Contextual decoding (B) chỉ làm thí nghiệm thứ hai**, và chỉ cho
   mẫu nghi ngờ: pass 1 → candidate → pass 2 với `initial_prompt` dạng
   câu tự nhiên, tên quý hiếm đặt cuối prompt, tổng ≤ 224 token; đo
   riêng tỉ lệ overcorrection (tên chèn thêm mà audio không có) — nếu
   overcorrection > 0 một cách có hệ thống thì bỏ (B), giữ (D).
5. **Không thử trước:** DeRAGEC-style LLM rationale (70B/GPT, DB ngoài,
   Wikipedia Def) và ROVER token-merge. Lý do đã nêu ở §2.2 và §2.1:
   vượt ngân sách, và merge đã được chứng minh làm tăng WER tổng trên
   dữ liệu nhiễu.

**Vì sao không phải (B) trước:** (B) cần 2 pass và read trước decode,
trong khi (D)+(C) sửa được cùng lớp lỗi mà không cần decode lại, không
tốn read thêm, và có guardrail xác định. (B) chỉ thắng (D) ở trường hợp
tên hiếm mà pass 1 đọc sai tới mức retrieval cũng không tìm ra
candidate — trường hợp này hiếm hơn và phải đo mới biết có đáng 2× ASR
không.

## 6. Phát hiện làm thay đổi hướng: "hỏi khi không chắc" đang sai về mặt kỳ vọng điểm

Đây là điểm quan trọng nhất của đợt này, và nó đến từ luật chấm của
chính LifeMate, không phải từ paper nào:

- Luật đã ghi nhận (`competition/lifemate.md`): `state_hash` nộp phải
  bằng gold, nếu không mẫu đó **0 điểm bất kể tool calls trông đúng đến
  đâu**; F1 chỉ tính khi hash đúng.
- Hệ quả: với một mẫu mà gold **có chứa write đó**, hỏi thay cho write
  cũng cho 0 điểm — **bằng với viết sai**. Hỏi không "bảo toàn điểm",
  hỏi chỉ đúng khi gold của mẫu đó **chính là ask** (thông tin thật sự
  thiếu).
- Với một mẫu mà gold có write nhưng ASR làm hỏng slot: sửa đúng →
  có cơ hội điểm > 0; sửa sai → 0; hỏi → 0. **Sửa (có bằng chứng, dù
  không chắc chắn tuyệt đối) luôn có kỳ vọng ≥ hỏi**, miễn là sửa không
  tạo ra tác dụng phụ ngoài mẫu đó — mà mỗi mẫu chạy 1 ToolEnv riêng,
  nên không có tác dụng phụ liên mẫu nào được ghi nhận.
- Vì vậy chính sách đúng không phải "không chắc → hỏi", mà là:
  - **Thông tin thật sự vắng mặt** (không có trong audio, context,
    history, read — ví dụ ngày tương đối không có ngày tham chiếu, trùng
    tên không có slot phụ) → **hỏi** (đây là trường hợp ask có thể là
    gold).
  - **Thông tin có mặt nhưng ASR nhiễu** (slot có candidate, có bằng
    chứng text/phonetic/acoustic dù chưa đủ mạnh theo ngưỡng cũ) →
    **sửa theo bằng chứng tốt nhất**, kể cả khi độ tin cậy < 100%.
    Ngưỡng sửa cho nhóm này nên hiệu chuẩn theo **kỳ vọng hash**, không
    theo "tỉ lệ sửa sai phải ≈ 0" — vì sửa sai và hỏi đều bằng 0 trên
    mẫu đó, nên một chính sách sửa với tỉ lệ đúng 30% vẫn tốt hơn hỏi
    100% (30% mẫu có điểm so với 0%).
  - **Ngoại lệ duy nhất:** phủ định. Viết một write bị cấm (ví dụ chuyển
    tiền khi user nói "không chuyển") không chỉ mất điểm mẫu đó — theo
    mô tả đề bài, nó là tác dụng phụ thật trong môi trường mô phỏng, và
    nếu gold của mẫu đó là **không viết gì** (hoặc `[]`) thì hỏi thay
    cho viết cũng sai hash. Nhưng guard phủ định vẫn giữ ở mức bảo thủ
    (chặn + hỏi) vì: (a) gold cho mẫu phủ định có thể là ask hoặc `[]`,
    chưa phân biệt được (Q-L1/Q-L5 UNVERIFIED); (b) chặn là hành vi an
    toàn duy nhất không tạo tác dụng phụ sai. Phủ định là trường hợp
    duy nhất mà "hỏi khi không chắc" vẫn đúng.
- **Caveat:** lập luận trên giả định ask không được điểm từng phần khi
  hash sai — đúng theo luật hash-gate đã ghi nhận, nhưng cách chấm
  `ask_missing_info` chi tiết (hỏi đúng/thừa/thiếu) vẫn là Q-L1
  UNVERIFIED. Nếu evaluator cho điểm từng phần cho ask dù hash sai (trái
  với mô tả hash-gate), thì chính sách phải tính lại. Thí nghiệm §7
  phải báo kết quả dưới cả hai giả định ask-scoring để không khóa sai.

## 7. Phép thử nhỏ nhất phân biệt các phương án (trên train ZAIC)

Chạy trên **train held-out** (train là nguồn gold duy nhất được ghi
nhận; public test chỉ có `sample_submission.jsonl` làm mẫu format theo
ghi nhận trước — phải xác minh lại bằng cách giải nén zip thật trước
khi chạy). Không đo trên dữ liệu đã dùng để viết rule/chọn ngưỡng rồi
báo lại số đó.

**E-asr-1 — Slot-error taxonomy (nền tảng, làm trước mọi so sánh):**
- Chạy PhoWhisper-small greedy trên held-out; lấy `audio_text` làm
  transcript tham chiếu (UNVERIFIED `audio_text` có phải transcript
  gold hay transcript ASR mẫu — phải kiểm tra 1–2 mẫu trước khi dùng
  làm ground truth; nếu nó là ASR mẫu thì taxonomy phải đối chiếu với
  gold `tool_calls` thay vì `audio_text`).
- Đối chiếu slot trong gold `tool_calls` với transcript: phân loại lỗi
  theo bảng: sai thanh / mất dấu / sai phụ âm-vần / số đọc bằng chữ /
  tiền sai đơn vị / ngày tương đối / rớt phủ định / tương phản / trùng
  tên / viết tắt. Đầu ra là **bảng tần suất theo loại slot**, không phải
  WER tổng. Quyết định: loại lỗi nào chiếm đa số slot-sai-gây-mất-hash
  thì ưu tiên đó.

**E-asr-2 — So sánh 4 chính sách trên cùng held-out (phép thử quyết định):**
- P0: baseline hiện tại (1-best + text, khác thanh → hỏi, mất dấu →
  UNKNOWN).
- P1: P0 + phonetic (Epitran + Panphon) + quy tắc khác thanh/mất dấu
  mới (§3.1, §5 bước 1–2).
- P2: P1 + acoustic rescore teacher-forcing cho slot tranh chấp.
- P3: P2 + contextual 2-pass cho mẫu nghi ngờ.
- Mỗi chính sách báo: số mẫu slot-đúng / slot-sai / hỏi, **tỉ lệ
  hash-proxy** = tỉ lệ mẫu mà mọi slot quyết định đều đúng và không có
  write bị cấm (proxy cho hash, vì hash thật cần chạy ToolEnv — nếu
  chạy được ToolEnv của split thì báo hash thật thay cho proxy, ghi rõ
  đã chạy ToolEnv hay chưa). Báo hash-proxy dưới 2 giả định ask-scoring
  (ask = gold khi thiếu thật; ask = 0 khi gold có write).
- Tiêu chí chọn: chính sách nào tăng hash-proxy nhiều nhất với chi phí
  thời gian/mẫu thấp nhất; một chính sách tăng slot-đúng nhưng tăng
  cả slot-sai (overcorrection) phải bị trừ điểm rõ ràng, không chỉ báo
  số đúng.

**E-asr-3 — Hiệu chuẩn ngưỡng, không đặt tay:**
- Với P1/P2, quét ngưỡng phonetic distance, acoustic margin, và text
  threshold trên **train_cal** (tách riêng khỏi held-out), vẽ đường cong
  sửa-đúng / sửa-sai / hỏi theo từng loại slot; khóa ngưỡng trên cal,
  đo một lần trên held-out. Trọng số kiểu RECOVER (1,0/1,2/0,6) **không
  được copy** — phải fit lại hoặc chứng minh không nhạy với trọng số
  trên cal.

**E-asr-4 — Ngân sách 30s và N-best API:**
- Đo end-to-end trên phần cứng thật (ghi rõ GPU, không ghi "A30" nếu
  không phải A30): greedy 1×, 5-temp 5×, teacher-forcing mỗi candidate,
  pass 2 contextual. Kiểm tra luôn: faster-whisper/transformers có
  expose N-best thật hay không (UNVERIFIED trong đợt này — nếu API chỉ
  trả 1-best thì N-best phải lấy bằng temperature sampling loop, và chi
  phí đó phải tính vào ngân sách).
- Kiểm tra Epitran vie-Latn trên 3 miền: lấy mẫu tên 3 miền từ train
  (nếu có nhãn miền — UNVERIFIED) hoặc ít nhất test các cặp merger miền
  Nam (d/gi/r, tr/ch, s/x) xem phonetic distance có sụp đổ hay không.
  Nếu sụp đổ, cần bảng merger dung sai theo miền, không dùng một
  distance duy nhất.

## 8. Những gì vẫn chưa đủ bằng chứng để chốt

1. **Cách chấm ask (Q-L1), read trong F1 (Q-L3), trace nộp (Q-L2),
   hành vi khi hết vòng (Q-L5)** — tất cả UNVERIFIED; §6 phụ thuộc vào
   Q-L1, phải đo lại nếu evaluator khác mô tả hash-gate.
2. **Portal LifeMate chưa kiểm tra lại trong đợt này** (fetch thất bại
   do lỗi mạng, không thử lại theo chỉ dẫn) — kết luận §0.3 dựa trên
   ghi nhận 2026-10-26 trong repo.
3. **N-best API của PhoWhisper/faster-whisper**: chưa xác minh faster-
   whisper có trả N-best hay chỉ 1-best; temperature sampling loop là
   phương án dự phòng, chưa đo chi phí.
4. **Epitran vie-Latn chất lượng thực tế**: file map tồn tại, nhưng độ
   chính xác G2P cho tên người Việt 3 miền, và Panphon distance cho
   tiếng Việt, chưa đo.
5. **Read trả về trường nào**: candidate có kèm alias, phòng, quan hệ,
   mô tả hay chỉ có tên + id — UNVERIFIED; quyết định §2.2 (Def thay
   bằng thuộc tính read) và §3.2 (slot phụ) phụ thuộc vào đây.
6. **Ngày tham chiếu cho ngày tương đối**: context có trường ngày hay
   không — UNVERIFIED.
7. **Tần suất thực tế** của trùng tên, viết tắt, số đọc bằng chữ trong
   dữ liệu ZAIC — chưa đếm; mọi quy tắc §3 đều là giả thuyết cho tới
   E-asr-1.
8. **CoVoGER mixture decoding chi tiết** (tỉ lệ beam vs sample, tham số
   nhiệt độ) và **thân code DeRAGEC/CoVoGER** — chưa đọc từng dòng;
   không dùng chúng làm bằng chứng cho tham số cụ thể.
9. **RECOVER code** — không tìm thấy repo công khai trong đợt này;
   RECOVER chỉ là đặc tả để cài lại, không phải code đã kiểm chứng.
10. **ILME / teacher-forced rescoring cho PhoWhisper** — ý tưởng từ
    snippet-level source (S8, S9), chưa cài thử; hiệu quả trên tiếng
    Việt và chi phí forward mỗi candidate chưa đo.
