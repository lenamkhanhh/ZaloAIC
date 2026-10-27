# LifeMate — Solutions và papers chuyển giao

> Mọi mục đều trả lời: bài toán gì, giống/khác LifeMate ở đâu, pipeline và điểm
> cải thiện, kết quả so với baseline nào, code/license, tái dùng/sửa gì, phụ thuộc
> và luật, chi phí/rủi ro, thí nghiệm nhỏ nhất. Không mục nào được gọi là "hiệu quả
> trên ZAIC" nếu chưa đo trên dữ liệu ZAIC.

## 1. ReAct — khung vòng lặp chính

- **Bài toán:** kết hợp reasoning và acting xen kẽ (Thought → Action → Observation).
- **Paper:** https://arxiv.org/pdf/2210.03629 (ICLR 2023, PaLM-540B few-shot —
  không phải model LifeMate).
- **Kết quả (author-reported):** ALFWorld 71% vs act-only 45% (một số tóm tắt ghi
  79% khi kết hợp CoT-SC — chênh lệch này cần đối chiếu bảng gốc, không chọn một
  con tùy tiện); WebShop 40% vs 30,1%; HotpotQA ReAct đơn 27,4% vs CoT 29,4%, nhưng
  ReAct + CoT-SC đạt 35,1%. Lỗi reasoning lặp lại chiếm 47% lỗi ReAct.
- **Áp dụng:** dùng ReAct ngắn gọn (1–2 câu thought) — thought chỉ để liệt kê tham
  số còn thiếu, chọn tool read tiếp theo, kiểm tra precondition. Thought dài chỉ
  tốn context (≤ 16K) và thời gian (≤ 30 s/mẫu).
- **Chống lặp:** giới hạn số vòng; cùng tool + cùng argument 2 lần → dừng và chuyển
  sang ask hoặc `[]`; đưa lỗi tool vào observation để model đổi hướng.

## 2. Hammer — kỹ thuật đáng mượn, checkpoint thì không

- **Paper (ICLR 2025):** https://arxiv.org/pdf/2410.04587 ;
  https://proceedings.iclr.cc/paper_files/paper/2025/file/d45e0bfb5a39477d56b55c0824200008-Paper-Conference.pdf
- **Hai kỹ thuật chuyển giao (secondary):**
  1. **Irrelevance augmentation** — thêm 7.500 mẫu dạy model nhận biết khi không có
     function nào phù hợp: trực tiếp liên quan đến ngoài phạm vi → `[]` và thiếu
     thông tin → `sys.ask_missing_info`.
  2. **Function masking** — che tên function/tham số lúc train để model buộc phải đọc
     description, giảm lệ thuộc vào naming convention.
- **Kết quả (secondary, BFCL v2):** Hammer 7B được mô tả cạnh tranh được với
  GPT-4/GPT-4o — nhưng Hammer-7B **vượt trần LLM < 5B của LifeMate nên loại trực
  tiếp**; chỉ mượn kỹ thuật khi fine-tune model ≤ 5B của đội trên dữ liệu train ZAIC.
- **Chưa xác minh:** license checkpoint `MadeAgents/Hammer-*`, HF repo chính thức —
  kiểm tra trước khi dùng bất kỳ checkpoint nào.

## 3. xLAM — mạnh về function-calling, phải kiểm tra kỹ

- **xLAM-2-3b-fc-r (~3B, base Qwen2.5-3B):** nguồn thứ cấp mô tả là model chuyên
  function-calling; survey thứ cấp ghi 65,74% overall BFCL, Qwen3-4B (prompt)
  62,04%. **Nhãn: số liệu thứ cấp, không phải leaderboard chính thức đã kiểm chứng.**
- **Chưa xác minh:** HF repo, licence, ngày phát hành chính thức của xLAM-2 — nguồn
  blog thứ cấp duy nhất ghi được là
  https://aichina.news/blog/a-3b-agent-for-your-laptop-salesforce-s-xlam-2-tool-caller-lands-on-a1zrpd/
  (không phải nguồn Salesforce chính thức). Để ở mục "để sau", không đưa vào
  shortlist chính cho tới khi xác minh eligible trước 26/10/2026.
- **xLAM-7b-r (~6,9–7,2B):** loại trực tiếp vì vượt trần LLM < 5B và hệ thống < 6B.
- **Rủi ro riêng:** BFCL đo trên API tổng quát, không đo state cuối, tiếng Việt,
  hay ask/refuse của LifeMate.

## 4. Qwen3-4B — LLM baseline hợp lý nhất hiện tại

- **Thông tin thứ cấp cần xác minh trên HF/official:** Qwen3-4B-Instruct-2507 được
  nguồn thứ cấp ghi phát hành 06/08/2025, 4,0B tham số, Apache 2.0, native context
  262K, có native tool calling; đa ngôn ngữ nên xử lý tiếng Việt tốt hơn model
  chuyên function-calling chỉ huấn luyện tiếng Anh.
- **Giới hạn LifeMate:** context của task ≤ 16K, nên phải cắt prompt/history/tool
  schemas xuống ≤ 16K — đừng nhồi toàn bộ history + toàn bộ catalog vào mọi vòng gọi.
- **Thí nghiệm nhỏ nhất:** prompt Qwen3-4B với đúng schema ZAIC + 2–3 few-shot theo
  format ReAct ngắn gọn, đo parse-error, tool-selection accuracy, state đúng trên
  200 sample.

## 5. Small specialist fine-tune (APIGen, ToolACE) — chỉ khi baseline yếu ở format

- **APIGen (paper Salesforce, đã đọc abstract):** https://arxiv.org/pdf/2406.18518 —
  sinh dữ liệu → verify 3 tầng: (1) format checking, (2) thực thi thật qua tool,
  (3) semantic verification. Áp dụng cho ZAIC: thay "thực thi API" bằng "chạy qua
  `zaic_tools` trên state mô phỏng và kiểm tra state cuối có khớp intent không";
  dữ liệu không qua được tầng 2 thì loại.
- **ToolACE (secondary):** pipeline sinh dữ liệu function calling (pool 26.507 API,
  verification 2 lớp); fine-tune Llama-3.1-8B đạt top BFCL theo tổng hợp thứ cấp —
  checkpoint 8B vượt trần LifeMate, chỉ mượn quy trình sinh dữ liệu: dùng dữ liệu
  train ZAIC + catalog tool để sinh thêm trajectory đa lượt, chỉ giữ trajectory
  cho đúng state_hash.
- **Bằng chứng gián tiếp (blog thứ cấp, không peer-review, không phải ZAIC):**
  Qwen3-0.6B fine-tune được báo cáo đạt 79,5% tool-call equivalence so với teacher
  GPT-OSS-120B 50,0% và base 10,3% trên lệnh smart-home IoT — chỉ là giả thuyết
  "specialist nhỏ thắng generalist lớn ở format", không lấy 79,5% làm kỳ vọng.
- **Rủi ro:** overfit format; mất khả năng hỏi lại/từ chối nếu dữ liệu execute áp
  đảo; teacher dùng để sinh dữ liệu phải ghi rõ để tránh tranh cãi về nguồn gốc.
- **Thí nghiệm nhỏ nhất:** LoRA nhỏ trên 1.000–2.000 ví dụ tổng hợp đã verify qua
  `zaic_tools`, đo trên public test thật; nếu không cải thiện state đúng thì dừng.

## 6. Constrained decoding + validator — bắt buộc, nhưng hiểu đúng giới hạn

- **Công cụ (hướng dẫn thứ cấp, chưa test trên A30):** vLLM `guided_json` /
  `GuidedDecodingParams`, Outlines, XGrammar, llama.cpp GBNF.
- **Làm được:** ép output đúng JSON schema → loại gần như hoàn toàn lỗi parse, tên
  tool không tồn tại, thiếu trường bắt buộc (nếu schema viết đủ chặt).
- **Không làm được:** chọn đúng tool, điền đúng argument, gọi đúng thứ tự, đạt đúng
  state. Constrained decoding chỉ đảm bảo "viết đúng form", không đảm bảo "làm đúng
  việc" — phải kèm validator code.
- **Pipeline:** constrained decoding → validator code (tên tool trong catalog, kiểu
  dữ liệu, enum, ID tồn tại trong candidate list, tham số bắt buộc) → nếu fail thì
  cho LLM sửa 1 lần với thông báo lỗi cụ thể, nếu vẫn fail thì dừng an toàn (ask
  hoặc `[]`) thay vì nộp trace lỗi.
- **Thí nghiệm nhỏ nhất:** A/B bật/tắt constrained decoding trên cùng model/prompt,
  đo parse-error, số vòng sửa, giây/sample, state đúng.

## 7. Symbolic Constraint Agents (SCA) — hướng ít người làm nhưng rất hợp

- **Paper (secondary):** https://arxiv.org/html/2610.25552 — đánh giá trên AppWorld
  test-challenge và τ²-bench.
- **Cơ chế:** khai thác ràng buộc hình thức trên tool call để **chặn lỗi trước khi
  gọi**, thay vì sửa sau khi lỗi. LifeMate có sẵn catalog với JSON Schema, `x-ref`,
  `x-one-of` nên có thể sinh ràng buộc tự động: tham số bắt buộc, `x-ref` phải là
  ID hợp lệ, `x-one-of` (ít nhất 1 trong nhóm, ví dụ `contact_id` hoặc
  `phone_number`), tool chỉ được gọi khi thuộc `context.installed_apps`.
- **Lưu ý luật:** validator chỉ nên chạy ở tầng lập kế hoạch trước khi gọi. Nếu lọc
  sau thực thi thì phải đối chiếu thể lệ về luật log call — mọi call đã chạy qua
  ToolEnv đều phải xuất hiện trong submission theo luật ghi nhận, nên không tự ý
  lọc trace sau thực thi.
- **Thí nghiệm nhỏ nhất:** viết validator từ catalog, chạy trên trajectory của
  baseline trên public test, đếm số call vi phạm bị chặn và số mẫu đổi từ sai
  thành đúng (qua state_hash mô phỏng lại bằng ToolEnv trên train).

## 8. Missing info vs out-of-scope — khung phân biệt

- **DelegationBench (secondary):** phân biệt Act (làm được) vs Ask (cần phê duyệt)
  vs Request (cần thêm fact) vs Refuse (không nên làm).
  Paper: https://arxiv.org/html/2610.05532 — ngày chính xác so với cutoff chưa xác
  minh, chỉ dùng khung, không dùng checkpoint từ đây.
- **Áp dụng cho LifeMate:**
  - **Ask** = yêu cầu có app xử lý được, nhưng thiếu tham số bắt buộc và không ground
    được bằng tool read → hỏi đúng thông tin còn thiếu, hỏi ít nhất có thể, dừng lại.
  - **Refuse/out-of-scope** = không có app nào xử lý được → `[]`, không bịa tool,
    không gọi write.
  - Trước khi ask, luôn thử ground bằng tool read. Trước khi refuse, kiểm tra lại
    catalog: có app nào tên/chức năng gần giống không; nếu có thì đó là ask/execute,
    không phải refuse.
- **Cách đo:** confusion matrix riêng cho 3 lớp execute / ask / refuse trên public
  test (hoặc tập gắn nhãn thủ công); báo cáo ask đúng, ask thừa, ask thiếu, refuse
  đúng, refuse sai — không gộp thành một con số accuracy chung.

## 9. Không khuyến nghị / loại trừ

| Loại trừ | Lý do |
|---|---|
| Model > 5B làm LLM, hệ thống > 6B | Vi phạm trần LifeMate |
| MoE mà tổng tham số > 6B (dù active nhỏ) | Chưa xác minh cách tính; rủi ro bị loại — chỉ dùng dense nếu chưa xác minh được |
| API ngoài lúc inference | Vi phạm offline |
| Checkpoint phát hành sau 26/10/2026 | Vi phạm cutoff |
| Đọc `state.json` trực tiếp | Vi phạm rule; mọi state phải qua `zaic_tools` |
| DuplexSLA / speech–language–action native end-to-end | LifeMate là audio file + ToolEnv offline, không phải hội thoại full-duplex; size/licence/checkpoint/A30 chưa xác minh — chỉ lấy ý "tách kênh action khỏi text tự do". Paper: https://arxiv.org/pdf/2605.20755 |
| Fine-tune ASR quy mô lớn ngay từ đầu | Tốn thời gian tới 16/11; chỉ làm nếu phân tích lỗi chứng minh lỗi ASR hệ thống |
| Dùng điểm BFCL/VIVOS/WER để chốt model | Benchmark khác miền, khác cách chấm (không có state_hash gate) |
