# LifeMate — Ghi chú code và implementation

> Không repo/code nào trong file này được gọi là "chạy được" dựa trên đọc
> snippet. Các repo dưới đây chỉ ở mức đã mở/đọc README hoặc đã thấy tên/snippet
> — trước khi dùng code, ghi rõ file/commit đã đọc.

## Repo đã mở/đọc (code-read)

| Repo | Commit lúc mở | License | Dùng được gì | Chưa dùng được gì |
|---|---|---|---|---|
| PhoWhisper — https://github.com/VinAIResearch/PhoWhisper | `b06f1937995cfee75b9e4ad3e2ae0798faf1a562` | BSD-3-Clause | Checkpoint ASR qua model card Hugging Face `vinai/PhoWhisper-*`, chạy bằng `transformers` pipeline; bảng WER/kích thước | Chỉ có README + LICENSE ở root; code sử dụng nằm ở model card — kiểm tra từng checkpoint trước khi nộp |
| τ-bench — https://github.com/sierra-research/tau-bench | `59a200c6d575d595120f1cb70fea53cef0632f6b` | MIT | Khung phân loại lỗi (`auto_error_identification.py`) và khung loop — các file agent cụ thể trong round 2 chỉ ở mức DEEPWIKI_SUMMARY, cần mở bằng git clone trước khi trích code | Task trong repo đã lỗi thời theo README — tham khảo τ²/τ³-bench khi cần số mới; không so số 2.0 với 1.x |
| ToolSandbox — https://github.com/apple/ToolSandbox | `c8571d7854316d2e1c5f288e59fe1e34e53f6dd1` | **NOASSERTION (chưa xác minh)** | Khái niệm execution context snapshot, milestone/minefield, tool đăng ký bằng decorator với type checking | Không copy code trước khi đọc file LICENSE thực tế |

## Repo/model card chỉ ở mức snippet — chưa đọc code/commit

- DeRAGEC: https://github.com/solee0022/deragec — chỉ xuất hiện ở mức snippet,
  chưa đọc code/commit, chưa xác minh licence/checkpoint.
- Qwen3-4B Function-Calling fine-tune (model card thứ cấp):
  https://huggingface.co/sweatSmile/Qwen3-4B-Function-Calling-Pro — LoRA SFT 1.000
  mẫu, loss 0,518; loss không phải accuracy, chưa có BFCL/ZAIC eval.
- xLAM-2-3b-fc-r: series đã xác minh từ Salesforce + APIGen-MT, nhưng checkpoint
  3B chưa xác minh licence/ngày/tên repo chính xác, BFCL 83,7% là first-party
  (không phải leaderboard chính thức), rủi ro CC BY-NC — ngoài shortlist chính.
  Hammer checkpoints `MadeAgents/Hammer-*`: Hammer v1 (ICLR 2025) tách riêng với
  Hammer2.1-3b (licence/ngày/base chưa xác minh trên card gốc, mirror báo
  CC-BY-NC-4.0 cho bản 0.5b) — ngoài shortlist chính.

## Các khối code phải tự viết (không phụ thuộc repo ngoài)

1. **Validator schema:** từ `<split>_tools_catalog.json` sinh JSON Schema cho từng
   tool; kiểm tra tên tool, kiểu dữ liệu, enum, tham số bắt buộc, `x-ref` (ID phải
   tồn tại trong candidate list đã read), `x-one-of`, `installed_apps`.
2. **Selective-read runner (thay read-before-write mặc định):** chỉ đọc khi cần
   xác lập precondition chưa biết hoặc ground thực thể; cache kết quả read theo
   (tool, argument chuẩn hóa); KHÔNG đọc lại sau write theo mặc định (xem
   deep-profiles.md §0.1, ASSUMPTION). Nếu write lỗi thì không đoán state đã
   đổi — đọc lại bằng tool read chỉ khi bước sau cần dữ liệu đó.
3. **Entity correction rule-based:** ASR N-best (ví dụ 5) + fuzzy match vào candidate
   list đóng từ tool read; số tiền/ngày không fuzzy đoán — không khớp chính xác thì
   hỏi lại.
4. **Loop guard (đúng giao thức):** phát hiện lặp (exact/cycle/stall) → dừng lặp
   ngay, replan 1 lần từ dữ liệu đã đọc/cache; nếu không còn hành động có căn cứ
   thì kết thúc trace nguyên trạng (không append ask/[]/write dọn dẹp, không lọc
   failed call). Ask chỉ khi chưa write gì và slot không ground được bằng read;
   `[]` chỉ sau khi kiểm tra catalog thấy không app nào xử lý được. Xem
   deep-profiles.md §0.2.
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
- [ ] Baseline đã đo: điểm chính thức mean(hash ? F1 : 0) trên train held-out,
      slot-error theo role, ask/refuse confusion, giây/sample, determinism.
      (Tỉ lệ hash đúng chỉ là chẩn đoán, không dùng một mình để chọn hệ thống.)
- [ ] Validator + constrained decoding + selective reads đã bật (không
      verification read mặc định, không redundant read).
- [ ] Entity correction chỉ sửa khi khớp candidate list; số tiền/ngày không fuzzy đoán.
- [ ] Không đọc `state.json`; mọi state qua `zaic_tools`.
- [ ] Docker chạy offline hoàn toàn, không gọi API ngoài, đã test end-to-end trên
      public test (chỉ format/latency — không dùng điểm leaderboard public để chọn hệ thống).
- [ ] Rule nộp trace (failed call, toàn bộ ToolEnv call) đã đối chiếu regulations.

## File cần mở tiếp bằng git clone (chưa phải CODE_INSPECTED)

- Forge (commit `3e5a38aed55504a71e5461b9873ca1979709ab50`, MIT):
  `src/forge/guardrails/response_validator.py`, `src/forge/guardrails/step_enforcer.py`,
  `src/forge/guardrails/error_tracker.py`, `src/forge/core/runner.py`.
- τ-bench: `tau_bench/agents/tool_calling_agent.py`,
  `tau_bench/agents/chat_react_agent.py`, `auto_error_identification.py`.
- Hammer: `train/data_processing.py` và các file trong `evaluation/`.
- ToolSandbox: file LICENSE thực tế (trang hiển thị NOASSERTION).
- Xem chi tiết trong [deep-profiles.md](deep-profiles.md).
