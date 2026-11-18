# Trace case: từ trace tới quyết định sai đầu tiên

Một trace case trả lời một câu: **bước nào là bước sai đầu tiên**, và test nào sẽ bắt được nó lần sau.

```bash
cd src
python -m lab9.trace_case --shape seeded_regression --claim C-002 --seed 11
python -m lab9.trace_case --shape fixed --claim C-002 --seed 11   # đối chứng
```

## Case của tôi: C-002@11, ticket nói 5 ngày, DB nói 2 ngày

| Trường | Nội dung |
|---|---|
| Trial | `seeded_regression C-002@11`, run ID `E-seeded_regression-20261118-af6c` (`reports/eval_seeded_regression.json`) |
| Triệu chứng | `pass_rate` fail (`status resolved != denied`), `refund_amount_correct` fail, `db_fact_kept` fail. Reply "Dạ, LogiX đã hoàn 20.000đ cho đơn O-202." **khớp** ledger 20.000đ, nên `reply_matches_ledger` pass: câu trả lời trôi chảy và nhất quán nhưng quyết định sai. Nhãn: `refund_vnd=0`, `status=denied` |
| Bước sai đầu tiên | **Event #3 `model_override {"delay_days": 5}`**. Agent ghi đè `delay_days` của đơn O-202 (DB: 2 ngày, nhận từ event #2 `investigator`) bằng số ngày khách nêu trong ticket |
| Vì sao là bước *đầu tiên* | Event #1 `handoff` đúng phạm vi (`owner_order_only`). Event #2 `investigator` lấy đúng đơn O-202 của P-100, `delay_days=2` (đúng với DB). Chỉ từ event #3 giá trị mới sai. Event #4 `quote` (20.000, `SHIP-LATE-03`) là hệ quả: tính đúng công thức nhưng trên đầu vào sai. #5, #6 là hệ quả kế tiếp (refund_history, reply) |
| Failure mode | **FM-03** `ticket_trust` (tin ticket hơn DB) |
| Đối chứng | `fixed C-002@11`: không có event `model_override`; event #3 `quote` ra `amount_vnd 0, reason no_entitlement`; reply "chưa đủ điều kiện hoàn"; ledger 0/0; Lab 8 grader PASS |
| Regression test | `src/tests/test_lab9_trace_case.py`: `test_seeded_regression_first_wrong_step_is_model_override` (assert `model_override` đứng ở vị trí #3, `DbFactKept` và `RefundAmountCorrect` đều False) và `test_fixed_passes_every_grader`. Đã thấy test fail-logic khớp trên variant lỗi và pass trên `fixed` (13 test student pass). Ngoài ra claim C-002 đã nằm trong eval set với `failure_modes=["FM-03"]` và `provenance.from_trace="x_ticket_trust C-002@11"` |
| Chưa chắc chắn | (1) MockLLM là tất định, nên trace này không chứng minh LLM thật sẽ tin ticket với tần suất tương tự. (2) Lỗi chỉ xuất hiện ở 1 claim trong 14 (ticket có số ngày khác DB): hồi quy tương tự trên claim khác không được phủ. (3) Ở `swarm` thật, cùng lỗi xuất hiện ở seed 55 (`seed % 5 == 0`, `swarm` C-002@55 fail): điểm yếu có sẵn của baseline, tức `pass_rate` baseline 0.9857 chứ không phải 1.0 |

## Quy tắc
- Đọc **ledger trước reply**: ở case này reply và ledger khớp nhau nhưng cả hai đều sai so với nhãn. Chỉ nhìn reply thì không thấy lỗi.
- "Bước sai đầu tiên" dẫn số event cụ thể: #3 `model_override`.
- Case đã có regression test chạy được trong `tests/` (CI chạy qua `-k "lab9 and not advanced"`).
