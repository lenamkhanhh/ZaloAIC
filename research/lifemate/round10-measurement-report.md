# Đợt 10 — Measurement Report: Provenance DAG & Deterministic Gates

Ngày: 2026-10-28. Phạm vi: dev split 1237 mẫu (seed 42), code Python thuần
CPU, 0 tham số thêm, 0 lượt gọi LLM. Chưa tích hợp vào `agent.py`
(hook round 8 vẫn là điểm tích hợp duy nhất; hai module đợt 10 là
standalone). Chưa push (local trong `lifemate/`, `tests/`, `analysis/`).

## 0. Kết luận trước

- **DAG chứng minh được 355/556 đối số (63,8%)**, so với baseline hẹp
  140/556 (25,2%). Chuyển đổi **+215 đối số**, toàn bộ trên đối số giá
  trị (248 so với 33 trên 448 đối số giá trị). Đối số contact không đổi
  (107 so với 107) vì roster đã bao phủ từ baseline.
- So với baseline nới lỏng (cho phép observation khác app, gần với guard
  E7 nhất có thể tái tạo): baseline 89 đối số giá trị → chuyển đổi
  **+159**. Khoảng chuyển đổi trung thực là **159–215**, tùy chính sách
  observation của guard gốc.
- **428 ca UNKNOWN của E7 KHÔNG được báo cáo theo nghĩa đen.** Scope
  459 write / 511 đối số của E7 không tái tạo được từ code trong repo
  (guard của Codex không có ở đây; mọi tổ hợp scope đã thử đều lệch).
  Rerun này dùng scope tái tạo được, định nghĩa rõ ở §1, và đo chuyển
  đổi = DAG − baseline trên cùng scope, cùng evidence. Số 31 ALLOW /
  428 UNKNOWN của E7 chỉ là điểm tham chiếu, không phải mẫu số của
  rerun này.
- **Gate: chỉ Gate 2 (read-before-write) ĐẠT, precision 99,6% → KEEP.**
  Gate 1 (contact ambiguity) 90,5% → **DROP** theo luật <95%.
  Gate 3 literal 84,6% gold fire rate → **DROP**. Gate 3 scoped 50% →
  **DROP**. Chi tiết và nguyên nhân FP ở §3 — cả ba gate bị loại đều
  có nguyên nhân phân tích được, không phải nhiễu đo.

## 1. Scope của shadow audit (tái tạo được, khác scope E7)

- Dev: 1237 mẫu, 2843 gold call (khớp Arm A round 8).
- Monitored write: gold call là write (không phải read-verb, không phải
  `sys.ask_missing_info`) và có ≥ 1 đối số được giám sát
  (time/date/start/end/amount/contact_id/to-id).
- Kết quả: **479 write / 556 đối số** (giá trị 448, contact 108).
- Evidence mỗi write: anchor = `context.current_time`; current text =
  `audio_text`; history user texts; history observations gắn tool
  (zip tool_calls ↔ tool_results theo index); history events; roster từ
  `contacts.search` trước write; prior same-sample gold calls trước
  write; prefix observations từ replay ToolEnv (chỉ read trước write
  đầu tiên — audit không mutate state).
- Baseline = chỉ 3 luật hẹp của guard cũ: verbatim + observation +
  roster. DAG = toàn bộ luật đợt 10 (§2). Cả hai chạy trên cùng scope,
  cùng evidence.
- Truy cập: mọi observation qua `ToolEnv` (runtime chính thức); không
  bao giờ mở `train_environment/` hay `state.json`. Số điện thoại bị
  loại khỏi mọi bản ghi.

## 2. Chuyển đổi UNKNOWN → PROVEN

| | PROVEN | Tỷ lệ |
|---|---|---|
| Baseline hẹp (verbatim + observation cùng app + roster) | 140/556 | 25,2% |
| DAG đợt 10 | 355/556 | 63,8% |
| **Chuyển đổi (strict)** | **+215** | |
| Baseline nới lỏng (observation khác app cũng tính) | ~89 giá trị | |
| **Chuyển đổi (loose)** | **+159 giá trị** | |

Chia theo loại đối số:

| | Baseline | DAG | Chuyển đổi |
|---|---|---|---|
| Đối số giá trị (448) | 33 | 248 | +215 |
| Đối số contact (108) | 107 | 107 | 0 |

Phân bổ PROVEN của DAG theo luật:

| Luật | Số đối số | Ghi chú |
|---|---|---|
| roster | 95 | contact_id trong roster đã quan sát |
| datetime_assembly | 82 | ngày + giờ từ hai span khác nhau, có linkage |
| relative_date | 43 | ngày/giờ tương đối, tuần bằng chữ, ngày bằng chữ, daypart sau giờ |
| observation (cùng app) | 43 | giá trị đã xuất hiện trong observation cùng họ app |
| number_words | 25 | số/tiền bằng chữ, total-or-reject |
| duration | 24 | end = start mới + duration gốc của event |
| offset | 23 | start/end = event gốc ± cue ("muộn hơn nửa tiếng") |
| number_digits | 17 | số + đơn vị ("50 nghìn", "5 trăm nghìn") |
| supersede | 3 | giá trị mới nhất sau marker sửa lời |

UNPROVEN còn lại: **201/556** (giá trị 200, contact 1). Theo slot:
amount 71, time 72, start 22, date 16, end 19, contact_id 1 — amount
nay là slot tồn đọng lớn nhất (trước đây là time), chủ yếu là tiền
không có nguồn trong evidence (lược đơn vị, số lượng × đơn giá).

| Residual | Số lượng | Nội dung |
|---|---|---|
| cross-app observation candidate | 57 | giá trị có trong observation nhưng khác họ app — bị chặn cố ý (chống va chạm số tròn, vd 500000) |
| no source found | 144 | không nguồn nào trong evidence |

Các lớp residual KHÔNG triển khai (ghi nhận, không đoán):

- Observation + số học không có id link / khác app ("đặt báo thức
  trước giờ khai mạc một tiếng").
- Đơn vị tiền bị lược ("chuyển ví anh Long hai trăm nha" → gold
  200000; parser KHÔNG được đoán nghìn).
- Số lượng × đơn giá ("mỗi người một cà phê trứng" → 90000).
- Đại từ "hôm đó/đấy" trỏ về ngày trong observation (một phần đã
  cover qua assembly phía observation).
- End = start mới + duration gốc khi không có cue offset (một phần
  đã cover qua luật duration khi có event id link).

### Luật mới hoạt động đúng chỗ nào

- Offset/duration giải quyết đúng cụm `calendar.update_event` — lớp
  residual lớn nhất đợt trước (44/58 đối số UNPROVEN). Ví dụ kiểm tra
  tay: "dời lịch cà phê mai muộn hơn nửa tiếng" → start 15:00→15:30,
  end 16:00→16:30, đúng cả hai.
- Daypart sau giờ: "bốn giờ chiều mai" → 16:00 ngày mai (trước đây
  04:00); "9 giờ kém 15 tối mai" → 20:45 ngày mai.
- Ngày bằng chữ: "ngày mười bảy tháng mười", "hôm hai mươi hai tháng
  mười" đều parse đúng. Thứ bằng chữ: "thứ bảy này", "thứ ba tuần
  sau" đều đúng.
- Cùng-app observation: 1 đối số contact bị mất so với chạy đầu
  (108→107) — chính là ca `ewallet.transfer` c_9526 chỉ có ứng viên
  cross-app; việc chặn nó là hành vi thiết kế, không phải hồi quy.

### Giới hạn trung thực của con số

- Đây là shadow audit trên GOLD writes (đo coverage của prover trên
  đáp án đúng), không phải đo trên proposal của model. PROVEN rate
  trên gold ≠ tỷ lệ chặn hallucination trên proposal thật — bước tiếp
  theo phải là chạy prover trên proposal của model (chưa làm đợt này).
- Baseline "hẹp" chặt hơn guard E7 thực tế có thể đã dùng (E7 có thể
  đã cho observation khác app). Vì vậy khoảng 159–215 mới là khoảng
  trung thực, không phải một con số duy nhất.

## 3. Audit precision từng gate (dev 1237)

Phương pháp: gold write = should-pass (fire = FP); counterfactual
tổng hợp từ chính tình huống gold đó = should-fire (fire = TP).
Precision = TP/(TP+FP), kèm khoảng Wilson 95%. Luật của user: <95% →
loại ngay.

| Gate | Gold applicable | FP (fire trên gold) | TP (synthetic) | Precision | Wilson 95% | Verdict |
|---|---|---|---|---|---|---|
| G1 contact ambiguity | 105 | 10 | 95 | 90,5% | 83,4–94,7% | **DROP** |
| G2 read-before-write | 971 | 4 | 971 | 99,6% | 98,9–99,8% | **KEEP** |
| G3 literal (transfer cần confirm) | 91 transfer | 77 fire | — | — | — | **DROP** |
| G3 scoped (confirm khi "nợ") | 87 | 87 | 87 | 50,0% | 42,7–57,4% | **DROP** |

### G1 DROP — vì sao 10 FP (phân tích tay cả 10)

- 7/10: request tự phân biệt bằng quan hệ/vai trò mà gate chỉ-nhìn-tên
  bỏ qua: "anh Quân bên kho", "Lan chị gái tôi", "An bác sĩ gia đình",
  "chị ấy" (ngữ cảnh), "Minh Hà … nhà cung cấp", "bên đang giao dịch".
  Roster từ `contacts.search` CÓ trường relation, nhưng audit này chỉ
  giữ id/name nên gate không dùng được. Hướng v2: gate nhận biết
  relation (đối chiếu relation trong request với roster relation) —
  phải audit lại như một gate MỚI, không được sửa lén rồi đo lại.
- 3/10 còn lại là lõi không cứu được bằng relation: tên trần ("Nhắn
  tin cho Minh", "Nhắn SMS cho Hương") mà gold vẫn viết thẳng dù roster
  trùng tên, và 1 ca xác nhận ("Dạ đúng rồi, chuyển khoản đó") mà
  recipient đã xác lập từ lượt trước. Ngay cả v2 relation-aware hoàn
  hảo cũng chỉ lên tối đa ~97% trên tập này — sát ngưỡng, phải đo lại
  mới kết luận.

### G2 KEEP — 4 FP đều giải thích được

- 3 ca: contact xác lập ngoài lịch sử search quan sát được — quan hệ
  gia đình/profile ("mạ", "gọi lại cho Vy", tên đầy đủ "Emily
  Carter"). Lớp FP hẹp, không phải lỗi logic gate.
- 1 ca (`train_1696`, `chat_ott.send_message` chat_6142): gold write
  tự nó fail khi replay ("không tìm thấy chat_id") — id không tồn tại
  trong state replay được. Gate fire ở đây là đúng; nếu loại ca này,
  precision là 99,7%. Verdict KEEP không phụ thuộc vào ca này.

### G3 literal DROP — đúng như dự báo

77/91 transfer gold (84,6%) không có marker xác nhận trong transcript.
Trên transfer một lượt, chính request LÀ sự ủy quyền; gate literal
veto cả hành vi gold đúng. Không triển khai được dưới dạng hard gate.

### G3 scoped DROP — tiền đề sai, không phải nhiễu

87 transfer applicable (có ask trước đó, hoặc chi tiết không nằm trong
request hiện tại theo proxy amount-span + tên recipient), và cả 87
đều fire vì không có marker xác nhận sau ask. Nguyên nhân: phần lớn
là transfer mà chi tiết lấy từ HISTORY ("chuyển như lần trước") —
đó là evidence hợp lệ, không phải "thiếu xác nhận". Tiền đề "chi
tiết không trong request hiện tại ⇒ nợ xác nhận" là sai với dữ liệu
này. Gate xác nhận cần khái niệm "user đã ủy quyền instruction này
trong session", không phải "chi tiết nằm trong text hiện tại".

## 4. Chống loop & bẫy ASK-other (task 3)

`AskBudget(max_asks=2)` trong `lifemate_gates.py`, đã unit test:

- Tối đa 2 ASK mỗi session; cùng một slot không được hỏi lần 2 (hỏi
  lặp = loop, không phải tiến bộ).
- Khi hết budget, `allow_ask` trả False cho MỌI slot KỂ CẢ "other" —
  ASK-other bị gỡ bỏ vai trò bến an toàn.
- Chính sách khi ask bị chặn: DO_NOTHING — không bao giờ thực thi
  write chưa chứng minh được thay cho việc hỏi.
- Chưa đo trên model (không có lượt chạy model đợt này); đây là cơ
  chế, chưa phải số đo hành vi.

## 5. Test suite

**97/97 PASS trên cả hai backend** (difflib qua `python3`, RapidFuzz
3.14.6 qua `/tmp/rfvenv/bin/python`):

- `tests/test_lifemate_provenance.py`: parser số/tiền (kể cả hồi quy
  double-scaling), span số, ngày tương đối (thứ bằng chữ, ngày bằng
  chữ, daypart sau giờ), supersede, prover (verbatim/words, relative
  date, time-only, observation cùng app vs khác app, roster, history
  unique vs ambiguous, assembly, offset, duration, default chỉ khi
  khai báo).
- `tests/test_lifemate_gates.py`: G1/G2/G3-literal/G3-scoped/AskBudget.
- `tests/test_lifemate_grounding.py` (48 test round 5–7) và
  `tests/test_agent_grounding_hook.py` (4 test round 8) vẫn xanh —
  không hồi quy.

## 6. File bàn giao (local, chưa push)

- `lifemate/lifemate_provenance.py` — parser + DAG prover (stdlib).
- `lifemate/lifemate_gates.py` — 3 gate + AskBudget (stdlib).
- `tests/test_lifemate_provenance.py`, `tests/test_lifemate_gates.py`.
- `analysis/e7_dag_shadow_audit.py` → output `/tmp/e7_dag_audit.json`
  (local, không push).
- `analysis/gates_precision_audit.py` → output `/tmp/gates_audit.json`
  (local, không push).

## 7. Việc còn lại (không thuộc đợt 10)

1. Chạy prover trên proposal thật của model (không chỉ gold) để đo
   precision chặn hallucination — số đo đợt này mới là coverage.
2. Gate v2 nhận biết relation cho G1 (nếu muốn cứu G1): roster giữ
   relation, đối chiếu với request, audit lại như gate mới.
3. Tích hợp DAG + G2 vào pipeline (qua hook round 8 hoặc vị trí mới)
   — cần phê duyệt riêng; đợt 10 không sửa `agent.py`.
4. Push batch khi user duyệt (theo workflow đã thống nhất).
