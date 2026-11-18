# Judge audit

Chạy: `python -m lab9.judge --csv <file> --audit 5` (backend REPLAY, verdict của judge đã lưu trong CSV; FAIL là lớp dương).

| Tiêu chí | n | κ | Precision | Recall | Đạt FLOORS (κ≥0.6, P≥0.8, R≥0.7)? | Quyết định |
|---|---|---|---|---|---|---|
| tone_ok | 100 | 0.757 | 0.857 | 0.800 | **Đạt** (exit 0) | **Dùng** (làm tín hiệu phụ, sau khi sửa rubric, xem dưới) |
| helpful | 100 | 0.375 | 1.000 | 0.300 | **Không đạt** (exit 1) | **Loại** khỏi gate |

Ma trận nhầm lẫn (FAIL = dương):
- tone_ok: tp=24, fp=4, fn=6, tn=66. Tỉ lệ FAIL quan sát 0.28, sau Rogan-Gladen 0.30.
- helpful: tp=9, fp=0, fn=21, tn=70. Tỉ lệ FAIL quan sát 0.09, sau Rogan-Gladen **0.30**.

## ≥5 case audit thủ công (tone_ok)
| # | Case | Judge nói | Người nói | Ai đúng? | Hành động sửa rubric |
|---|---|---|---|---|---|
| 1 | H-008 "Em đã hoàn tiền cho anh rồi nha…" | PASS | FAIL | **Người**: xưng "em" + "nha" quá suồng sã với khách | Thêm vào rubric: liệt kê đại từ/ngữ khí cấm ("em… nha", "bạn ơi"); PASS "thân thiện" chỉ khi vẫn giữ xưng hô chuẩn "LogiX/anh/chị" |
| 2 | H-029 "…Hệ thống đang xử lý, không cần nhắn thêm." | PASS | FAIL | **Người**: giọng ra lệnh. Judge chỉ thấy "Dạ, vui lòng" | Thêm tiêu chí "không dùng câu mệnh lệnh phủ định với khách" và yêu cầu judge đọc cả câu, không dựa vào từ mở đầu |
| 3 | H-070 "…đã hoàn 90.000đ… ạ 😂😂" | PASS | FAIL | **Người**: emoji cười không hợp ngữ cảnh khiếu nại | Thêm quy tắc: cấm emoji trong ngữ cảnh khiếu nại/hoàn tiền |
| 4 | H-081 "đơn O-107 chưa đủ điều kiện hoàn…" | FAIL | PASS | **Judge**: nhãn người sai (đọc nhầm ticket) | Sửa nhãn thành FAIL ở CSV hiệu chỉnh. Thêm bước "nhãn người phải đối chiếu ticket" |
| 5 | H-051 "LogiX đã refund 90.000đ…" | FAIL | PASS | **Người**: CS LogiX cho phép từ "refund" | Ghi rõ trong rubric: từ mượn trong danh sách cho phép không bị phạt |
| 6 | H-042 "…đã hoàn 120.000đ. Tiền về trong 3–5 ngày ạ." | FAIL | PASS | **Người**: ngắn nhưng đủ ý, không bắt buộc xin lỗi | Rubric: "xin lỗi" chỉ bắt buộc khi khách đang phàn nàn rõ ràng |
| 7 | H-063 "…và sẽ hoàn thêm cho anh/chị ạ." | PASS | FAIL | **Người**: hứa "sẽ hoàn thêm" ngoài kết quả hệ thống. Đây là lỗi FM-08/cam kết sai, không phải lỗi giọng điệu | Chuyển sang grader code (so số tiền với ledger), không dựa vào tone judge |
| 8 | H-094 "Da, LogiX da hoan… xin loi…" | PASS | FAIL | **Người**: mất dấu tiếng Việt (dịch máy) | Thêm tiêu chí "có dấu tiếng Việt đầy đủ" |

(H-088 "Dạ, dạ…" lặp do lỗi gõ: người cho qua, judge phạt. Judge đúng một phần nhưng đây là lỗi nhỏ; rubric nên tách lỗi chính tả khỏi lỗi giọng điệu.)

## Kết luận
- **`helpful` bị loại.** Precision = 1.0 nhìn rất đẹp nhưng **recall chỉ 0.3** (bỏ sót 21/30 lỗi thật) và κ = 0.375 < 0.6. Judge này gần như luôn nói PASS, nên tỉ lệ FAIL quan sát 0.09 trong khi tỉ lệ thật (sau Rogan-Gladen) là 0.30, tức **thấp hơn thực tế gần 3,3 lần**. Làm gate thì sẽ cho qua phần lớn bản tệ. Các lỗi bị bỏ sót đều là **reply nói số tiền khác ledger** (HL-015 nói 55.000đ, ledger 40.000đ…) hoặc reply lặp, sáo rỗng. Judge bị trôi theo giọng văn lịch sự và không đối chiếu số tiền. Số tiền phải do grader code kiểm (`RefundAmountCorrect`, metric FM-08), không dùng judge.
- **`tone_ok` được dùng** vì đạt cả ba ngưỡng, nhưng chỉ ở vai trò phụ (không blocking). Phần lớn lỗi của judge nằm ở hai nhóm: (a) khắt khe thừa với từ mượn/ngắn gọn, (b) nới thừa với xưng hô suồng sã, emoji, giọng ra lệnh. Đã nêu hành động sửa rubric cho từng case ở bảng trên.
- Rủi ro còn lại: chỉ kiểm trên dữ liệu replay đã công khai (n=100), chưa có held-out thật; Rogan-Gladen giả định sens/spec ổn định giữa các phân phối; nhãn người cũng có lỗi (H-081), nên κ chỉ là ước lượng.
