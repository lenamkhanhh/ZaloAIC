# LifeMate — Ghi chú code và implementation

> Không repo/code nào trong file này được gọi là "chạy được" dựa trên đọc
> snippet. Các repo dưới đây chỉ ở mức đã mở/đọc README hoặc đã thấy tên/snippet
> — trước khi dùng code, ghi rõ file/commit đã đọc.

## Repo đã mở/đọc (code-read)

| Repo | Commit lúc mở | License | Dùng được gì | Chưa dùng được gì |
|---|---|---|---|---|
| PhoWhisper — https://github.com/VinAIResearch/PhoWhisper | `b06f1937995cfee75b9e4ad3e2ae0798faf1a562` | BSD-3-Clause | Checkpoint ASR qua model card Hugging Face `vinai/PhoWhisper-*`, chạy bằng `transformers` pipeline; bảng WER/kích thước | Chỉ có README + LICENSE ở root; code sử dụng nằm ở model card — kiểm tra từng checkpoint trước khi nộp |
| τ-bench — https://github.com/sierra-research/tau-bench | `59a200c6d575d595120f1cb70fea53cef0632f6b` | MIT | `run.py`, `tau_bench/`, `few_shot_data/`, `historical_trajectories/`, `auto_error_identification.py` (khung phân loại lỗi) | Task trong repo đã lỗi thời theo README — tham khảo τ²/τ³-bench khi cần số mới |
| ToolSandbox — https://github.com/apple/ToolSandbox | `c8571d7854316d2e1c5f288e59fe1e34e53f6dd1` | **NOASSERTION (chưa xác minh)** | Khái niệm execution context snapshot, milestone/minefield, tool đăng ký bằng decorator với type checking | Không copy code trước khi đọc file LICENSE thực tế |

## Repo/model card chỉ ở mức snippet — chưa đọc code/commit

- DeRAGEC: https://github.com/solee0022/deragec — chỉ xuất hiện ở mức snippet,
  chưa đọc code/commit, chưa xác minh licence/checkpoint.
- Qwen3-4B Function-Calling fine-tune (model card thứ cấp):
  https://huggingface.co/sweatSmile/Qwen3-4B-Function-Calling-Pro — LoRA SFT 1.000
  mẫu, loss 0,518; loss không phải accuracy, chưa có BFCL/ZAIC eval.
- xLAM-2-3b-fc-r, Hammer checkpoints `MadeAgents/Hammer-*`: chưa xác minh HF repo
  chính thức, licence, ngày phát hành.

## Các khối code phải tự viết (không phụ thuộc repo ngoài)

1. **Validator schema:** từ `<split>_tools_catalog.json` sinh JSON Schema cho từng
   tool; kiểm tra tên tool, kiểu dữ liệu, enum, tham số bắt buộc, `x-ref` (ID phải
   tồn tại trong candidate list đã read), `x-one-of`, `installed_apps`.
2. **Read-before-write wrapper:** mọi write đều qua tool read trước (lấy state hiện
   tại, kiểm tra precondition); sau write đọc lại để xác nhận; nếu write lỗi thì
   không đoán state đã đổi — đọc lại bằng tool read.
3. **Entity correction rule-based:** ASR N-best (ví dụ 5) + fuzzy match vào candidate
   list đóng từ tool read; số tiền/ngày không fuzzy đoán — không khớp chính xác thì
   hỏi lại.
4. **Loop guard:** giới hạn số vòng ReAct; phát hiện lặp (cùng tool + cùng argument
   2 lần) → dừng và chuyển sang ask hoặc `[]`.
5. **Deterministic runner:** greedy decoding, temperature 0, seed cố định; log toàn
   bộ tool calls qua ToolEnv để đối chiếu với submission (luật log call phải đối
   chiếu thể lệ trước khi lọc bất kỳ call nào).
6. **Harness đo theo nhóm lỗi:** ASR slot-error, chọn sai tool, sai argument, sai
   thứ tự/dependency, write thừa, ask/refuse sai, parse/format lỗi, timeout > 30 s —
   theo taxonomy của τ-bench, không đo chung một con số accuracy.

## Checklist trước khi đóng Docker

- [ ] Catalog tool ZAIC đã đọc từ dữ liệu/portal chính thức, không suy đoán.
- [ ] HF repo + licence + ngày phát hành của ASR và LLM đã xác minh trước 26/10/2026.
- [ ] Tổng tham số hệ thống (kể cả model phụ) < 6B, LLM < 5B, context ≤ 16K.
- [ ] Baseline đã đo: state đúng, tool F1, slot-error, ask/refuse confusion,
      giây/sample, determinism.
- [ ] Validator + constrained decoding + read-before-write đã bật.
- [ ] Entity correction chỉ sửa khi khớp candidate list; số tiền/ngày không fuzzy đoán.
- [ ] Không đọc `state.json`; mọi state qua `zaic_tools`.
- [ ] Docker chạy offline hoàn toàn, không gọi API ngoài, đã test end-to-end trên
      public test.
- [ ] Rule nộp trace (failed call, toàn bộ ToolEnv call) đã đối chiếu regulations.
