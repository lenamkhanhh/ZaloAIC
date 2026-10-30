# 01 — Kiểm toán độc lập phần đánh giá hiện tại (G&G)

Baseline: `4bd95a5` (= `287e68d5` + file handoff; xem `~/workspace/zaic-eval/SNAPSHOT_LOG.md`).
Phạm vi: chỉ đọc implementation; không sửa agent/G&G/simulator/scorer/config/test của tác giả.

## 1. Kho test của tác giả

10 file, tổng **528 test methods** (đếm `def test_`):

- `tests/test_lifemate_gates.py`: 48 — synthetic, không data/simulator/network.
- `tests/test_gates_adapter.py`: 125 — synthetic only, “no gold, no sample ids”.
- `tests/test_phone_callback_evidence.py`: 75 — synthetic.
- `tests/test_callback_negation.py`: 115 — synthetic.
- `tests/test_evidence_lifecycle.py`: 36 — synthetic.
- `tests/test_lifemate_provenance.py`: 46 — synthetic.
- `tests/test_name_binding.py`: 29 — synthetic.
- `tests/test_lifemate_grounding.py`: 48 — có 6 skip marks (cần data).
- `tests/test_agent_grounding_hook.py`: 4 — integration cho **grounding hook round 8** (không phải G&G); cần `LIFEMATE_DATA`, skip khi thiếu data.
- `tests/test_unfire_controls.py`: 2 test methods nhưng bảng 30+ case, chia 5 loại riêng (correct_unfire / false_unfire / refusal / false_block / unknown_ambiguous), zero-tolerance cho false_unfire và false_block.
- `lifemate/tests/test_lifemate.py`: cần data thật, skip khi thiếu (không thuộc 528).

Nhận xét độc lập:

- Điểm mạnh: toàn bộ test G&G là synthetic, tách khỏi gold; `test_unfire_controls.py` đo 5 loại riêng nên không thể “che” false un-fire bằng tổng tốt. Đây là kiểm tra unit tốt.
- Điểm yếu về tính độc lập: test do cùng phía implement viết, mã hoá kỳ vọng của chính implement. Suite của tôi (mục 2) vẫn tìm được 2 lỗi mới mà suite tác giả không bao phủ (SEAL-003: “đừng (có) mà”; SEAL-004: câu hỏi “số nào/nhỉ”), và các lỗ hổng phạm vi mà adapter không thể tạo fire mới khi baseline đã pass.
- Chi tiết nhỏ: `tests/test_gates_adapter.py` có `"contacts.delete": "write"` trong KINDS, trong khi `lifemate_phone_callback_evidence.py` ghi chú “NO contacts.delete tool in the catalog (reviewer correction)”. Kind map synthetic chứa tool ngoài catalog — không gây sai ở đây nhưng cho thấy fixture synthetic có thể lệch catalog.
- `tests/test_agent_grounding_hook.py` không đo G&G; nó đo hook grounding round 8 (dormant byte-identical, active normalize). Không dùng để kết luận gì về G&G.

## 2. Script gold/shadow

### `analysis/gates_precision_audit.py`
- Đo precision từng gate trên gold trajectories (should-pass) + synthetic counterfactuals (should-fire).
- Dùng `ToolEnv` replay full gold trajectory; không mở `train_environment/` hay `state.json` trực tiếp. Tốt.
- Precision = TP/(TP+FP) + Wilson 95%; KEEP iff ≥95%. Gate 3 literal bị drop nếu fire >5% gold transfers (gold transfer đúng mà bị fire là mâu thuẫn gold).
- Hạn chế: gold được giả định đúng; anomaly `train_1696` cần tách riêng (script paired audit có làm, script này không nhắc rõ).

### `analysis/gg_paired_audit.py`
- So baseline Gate 2 vs candidate (adapter) trên cùng input, cùng scope dev1237; không loại gold call vì gate thiếu hỗ trợ; tách `train_1696`.
- Ghi decision changes đầy đủ nhưng **không adjudicate**: “agreement with gold alone does not prove the new evidence was valid”.
- Có synthetic control “empty evidence must fire”, chống pass rỗng.
- Đặt tên gây nhầm: `false_block_rate` thực chất là fire rate trên gold (gold được giả định đúng), không phải false-block đã adjudicate.

### `analysis/gg_shadow.py`
- Shadow trên trace đã lưu: prefix nhân quả (model transcript, history ASR, tool events trước proposal), không dùng proposal hiện tại / future / gold làm evidence; gold chỉ để adjudicate ngoài.
- Adjudication 6 loại; precision/recall chỉ trên subset đã adjudicate; out-of-scope và insufficient_evidence đếm riêng. Tốt.
- `safety_conclusion`: “insufficient evidence” khi <2 independent positives — ngưỡng tùy ý, cần nêu rõ.
- Nit: usage string ghi `analysis/model_trace_shadow.py` trong khi file là `gg_shadow.py`; docstring “never touches the repo” nhưng script load module lifemate qua `lifemate_dir` (đúng là cần code để chạy, chỉ là câu chữ gây nhầm).

## 3. Những gì phần đánh giá hiện tại chưa đo

1. **Tích hợp agent**: không agent nào gọi G&G (audit-script-only + tests). Không có đo “G&G làm đổi hành vi agent khi chỉ quan sát”.
2. **Fire mới**: adapter chỉ un-fire hoặc suppress qua ledger khi baseline đã fire/pass theo cách cụ thể; khi baseline pass, adapter không có đường fire mới. Các case wrong-person tới số trong roster, action mismatch, delegate, money-as-target nằm ngoài phạm vi — suite mục 2 đã ghi nhận.
3. **Adjudication của decision changes**: paired audit liệt kê 13 un-fires nhưng không kết luận đúng/sai; cần adjudicate độc lập (mục 3 đã làm một phần trên trace).
4. **Held-out**: mọi script chỉ dùng dev1237; held-out 308 vẫn khóa. Tốt — giữ nguyên.

## 4. Vấn đề phương pháp luận (bổ sung từ audit độc lập)

- **Gold tự định nghĩa đúng**: gold labels được coi là hành vi đúng mặc định (vd gate3: fire trên gold transfer = “gold contradiction”). Đây là kiểm tra tính nhất quán với gold, không phải kiểm tra tính đúng tuyệt đối.
- **Audit dùng chung helper với implementation**: gates audit import `lifemate_gates`, `find_number_spans`, `nfc_lower` từ chính code được kiểm tra — hai bên có thể cùng sai theo cùng một parser (G5 review từng tìm 4 bug kiểu này).
- **E7 thay gold text khi thiếu ASR**: 1,389 dev gold writes dùng gold text thay ASR cache, đánh dấu UNAVAILABLE (trung thực), nhưng paired check ASR-vs-gold thật chỉ có 19 occurrences trên V13.
- **Re-audit cùng corpus**: v1/v2/v3 đo lại cùng tập mẫu — bảng version là audit lại, không phải bằng chứng mới.
- **Synthetic tự sinh tự chấm**: grounding Arm B dùng `int_to_words` cùng code base để render rồi kiểm tra recover — cùng convention số học ở cả hai phía.
- **Known-fill manifest (6 IDs)** chính là corpus dùng lúc phát triển; SPEC tự thừa nhận “not independent validation”.
- **Counterfactual cực đoan**: Gate2 “evidence removed” (empty PriorCall + empty rosters) là tình huống suy biến, có thể không bao giờ xuất hiện ở runtime dưới dạng đó.
- **E7 guard ba trạng thái** (ALLOW/BLOCK/UNKNOWN), verdict **CPU_NOT_READY**: 0 gold BLOCK đạt, nhưng 428/459 gold UNKNOWN (positive coverage chỉ 6.75%) và known-fill 0780 UNKNOWN — UNKNOWN không phải allow thành công, cũng không phải bằng chứng “zero over-rejection”. E7 deployment brief tồn tại nhưng **chưa chạy**.

## Kết luận mục 1

Phần đánh giá hiện tại chắc ở tầng unit (528 tests synthetic, zero-tolerance cho false un-fire/false block) và paired gold audit có kỷ luật scope, nhưng **không độc lập** (cùng phía viết test và code) và **không đo tích hợp agent**. Các lỗi mới và lỗ hổng phạm vi ở mục 2 là bằng chứng rằng suite tác giả chưa đủ. Khuyến nghị: giữ nguyên test tác giả (không sửa), dùng suite độc lập mục 2 + adjudication mục 3 làm lớp kiểm tra thứ hai, và chỉ đo agent khi có hook runtime thật (mục 4).

## 5. Điểm mù từ đọc code (bổ sung)

- **Phân biệt hai hook**: grounding hook (chuẩn hoá đề xuất, `ground_tool_call`) ĐÃ tích hợp trong `AgentLoop` (chạy trước `env.validate`; NEEDS_ASK → `sys.ask_missing_info`; `baseline.json`: off, `recommended.json`: on). Cái audit-script-only là các **gates veto** (G1/G2/G3) — agent loop không import chúng.
- **Không có chế độ observer/OFF-ON** ở baseline: công tắc duy nhất `config.grounding` khi ON thì đổi hành vi, không phải observe-only. Protocol mục 4 phải viết mới hoàn toàn — đã ghi PENDING.
- **Residuals đã tự khai trong code**: patch-verified write bị coi là echo khi id == argument (có thể veto lệnh đúng); legacy 2-tuple của 4 tool đa-registry (smart_home.get_status, music.list_tracks, podcast_radio.search, loyalty.get_points) không path → establish NOTHING; FK field trong record không chứng minh registry được tham chiếu.
- **Rủi ro ContactFilter**: viết tắt đúng 1 từ ("Minh") → FUZZY_GROUNDED âm thầm; roster thiếu người → ground nhầm người; ngưỡng fuzzy (88/8) tự thừa nhận chưa hiệu chuẩn trên ASR.
- **AskBudget**: hết 2 lượt → DO_NOTHING âm thầm (task dở dang thay vì hỏi tiếp); không bao giờ hỏi lại cùng slot.
- **Chưa chốt**: 2 biến thể confirmation gate cho hành vi ngược nhau trên transfer một lượt (request = ủy quyền vs cần marker).

## 6. Audit 6 test files — 3 lỗ hổng phương pháp luận đáng ghi nhất

- **Attribution sai tầng** (`tests/test_agent_grounding_hook.py`): test `leftover_name_without_roster_becomes_ask` đặt tên theo hook, nhưng `grounding_log[0].status == UNCHANGED` trong khi output là ask — ask thực ra từ `AgentLoop`, test không cô lập được hook. Test 1 (OFF) chỉ chứng minh pass-through, không chứng minh ON không làm lệch output của generator thật (generator là scripted cố định).
- **Test và spec cùng tiến hóa** (`tests/test_lifemate_gates.py`): các “fix round” đổi cả implementation lẫn test; test pin hành vi mới chứ không xác thực quy tắc mới đúng với simulator (registry mapping là sản phẩm của tác giả; nhiều assert trên cùng fixture = biến thể của 1 rule, không phải N bằng chứng độc lập; có case dùng schema synthetic “no real tool combines both” — không tồn tại trong catalog thật).
- **Phạm vi nhầm lẫn** (`deep-dives/tests/test_regressions.py`): test xanh cho module demo trong `deep-dives/`, KHÔNG bao phủ `lifemate/agent.py`, `lifemate_gates.py`, `lifemate_grounding.py` — không được trích dẫn như bằng chứng an toàn pipeline.
- Phụ: `test_lifemate.py::test_gold_replay_changed_apps_match_final_state` là kiểm tra nhất quán label↔simulator gần mức 2 (trung thực, nhãn DIAGNOSTIC ONLY), nhưng chỉ 5 mẫu đầu; các subTest loop trên 1 parser (17 subTest số-từ…) là 1 bằng chứng, không phải 17.
