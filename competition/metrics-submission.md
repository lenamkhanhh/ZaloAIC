# Metric và submission — cả hai track

*Mức bằng chứng: official portal, kiểm tra 2026-10-26.*

## LifeMate

- Điểm mẫu = 0 nếu `state_hash` sai; nếu hash đúng thì tính tool-call F1
  (non-fuzzy khớp hệt, fuzzy token-F1 > 0,6 sau lowercase + NFC, thứ tự không xét).
- Mẫu gold rỗng: 1 điểm chỉ khi nộp rỗng.
- Timeout/lỗi thực thi = 0. Nộp Docker + `submission.jsonl`.
- Public submission: tối đa 5 file/ngày (reset cuối ngày).
- Final solution: tối đa 2 lần nộp Docker, chỉ lần cuối được chấm; nộp qua form
  "Solution Submission" kèm checksum và link Google Drive công khai, hạn 16/11/2026
  23:59 GMT+7. Private phase 20–23/11, JSONL cuối hạn 23/11/2026 23:59 GMT+7.
- Top 2 mỗi track công bố 02/12/2026.
- **Chưa xác minh:** cách chấm `sys.ask_missing_info`, failed call trong trace,
  Docker base image và inference script chính thức, cách tính tham số total/active.

## DataMate

- Penalized Accuracy: đúng +1, abstain 0, sai −1, không điểm từng phần.
- Public submission: tối đa 5 file/ngày.
- Final solution: tối đa 2 lần nộp Docker, chỉ lần cuối được chấm; hạn 16/11/2026
  23:59 GMT+7. Private phase 20–23/11, JSONL cuối hạn 23/11/2026 23:59 GMT+7.
- Log bắt buộc trong Docker: mỗi câu hỏi ghi tối thiểu question id, đáp án cuối,
  thời gian xử lý, và cách đáp án được suy ra (code đã sinh và kết quả thực thi) —
  dùng để đối chiếu kết quả nộp với kết quả chạy lại.
- Tính tái lập: |PA(uploaded) − PA(rerun)| ≤ 0,03, nếu không giải thích được thì
  bị loại.
- Tie-break theo tổng thời gian inference trong lần chạy lại, rồi theo thời gian
  nộp sớm hơn (ghi nhận từ portal; cần đối chiếu lại evaluator trước khi dùng
  làm chiến thuật).
- **Chưa xác minh:** cách evaluator xử lý missing/unanswerable/sai type/hòa/
  thứ tự list/làm tròn/percent format — xem [datamate.md](datamate.md) và
  [../gaps.md](../gaps.md). Không chốt pipeline dựa trên suy đoán ở các điểm này.
