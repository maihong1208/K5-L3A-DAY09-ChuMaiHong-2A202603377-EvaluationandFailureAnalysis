# Judge audit

Lệnh chạy kiểm định (từ thư mục `src/`):
- `python -m lab9.judge --csv data/eval/judge_tone_public.csv --audit 8` (exit code `0`)
- `python -m lab9.judge --csv data/eval/judge_helpful_public.csv --audit 10` (exit code `1`)

## Bảng tổng hợp hiệu chuẩn (Calibration Summary)

Ngưỡng sàn (FLOORS): `κ >= 0.6`, `Precision >= 0.8`, `Recall >= 0.7` (lớp dương `POS = "FAIL"`).

| Tiêu chí | n | κ | Precision | Recall | Observed fail rate | Corrected fail rate (Rogan-Gladen) | Confusion matrix (`tp`, `fp`, `fn`, `tn`) | Đạt FLOORS? | Quyết định |
|---|---:|---:|---:|---:|---:|---:|---|---|---|
| `tone_ok` (`judge_tone_public.csv`) | 100 | 0.757 | 0.857 | 0.800 | 0.280 | 0.300 | `{'tp': 24, 'fp': 4, 'fn': 6, 'tn': 66}` | Đạt (`PASS floors`) | **Dùng (Keep)** |
| `helpful` (`judge_helpful_public.csv`) | 100 | 0.375 | 1.000 | 0.300 | 0.090 | 0.300 | `{'tp': 9, 'fp': 0, 'fn': 21, 'tn': 70}` | Không đạt (`FAIL floors`: `R=0.3 < 0.7`, `κ=0.375 < 0.6`) | **Loại (Reject)** |

### Ma trận nhầm lẫn chi tiết

**1. `tone_ok` (`n = 100`, 30 `FAIL` thực tế, 70 `PASS` thực tế):**
- `tp = 24`, `fp = 4`, `fn = 6`, `tn = 66`
- `Precision = 24 / (24 + 4) = 0.857`, `Recall (Sensitivity) = 24 / (24 + 6) = 0.800`, `Specificity = 66 / (66 + 4) = 0.943`
- `p_o = 0.90`, `p_e = 0.588`, `κ = 0.757`
- Tỷ lệ lỗi quan sát được `0.28` -> hiệu chỉnh Rogan-Gladen về đúng `0.30` (khớp với tỷ lệ `FAIL` thực tế `30 / 100 = 0.30`).

**2. `helpful` (`n = 100`, 30 `FAIL` thực tế, 70 `PASS` thực tế):**
- `tp = 9`, `fp = 0`, `fn = 21`, `tn = 70`
- `Precision = 9 / (9 + 0) = 1.000`, `Recall (Sensitivity) = 9 / (9 + 21) = 0.300`, `Specificity = 70 / (70 + 0) = 1.000`
- `p_o = 0.79`, `p_e = 0.664`, `κ = 0.375`
- Dù `Precision = 1.0` (judge không báo nhầm `PASS` nào thành `FAIL`), `Recall = 0.3` khiến 21/30 lỗi thật bị bỏ sót (`fn = 21`). Vì bỏ sót quá nặng, tỷ lệ lỗi quan sát chỉ là `0.09` (thấp hơn 3.3 lần so với tỷ lệ thật `0.30` sau hiệu chỉnh Rogan-Gladen).

## Case audit thủ công (8 case bất đồng trên cả 2 bộ dữ liệu)

| # | Case (`item_id`) | Bộ dữ liệu | Nội dung câu trả lời (trích) | Judge nói | Người nói | Ai đúng? | Ghi chú |
|---|---|---|---|---|---|---|---|
| 1 | `H-008` | `tone_ok` | `"Em đã hoàn tiền cho anh rồi nha, anh check giúp em."` | `PASS` | `FAIL` | Người đúng (`FN`) | Xưng `'em' + 'nha'`, quá suồng sã với khách; judge hiểu nhầm là thân thiện. |
| 2 | `H-029` | `tone_ok` | `"Dạ, vui lòng chờ. Hệ thống đang xử lý, không cần nhắn thêm."` | `PASS` | `FAIL` | Người đúng (`FN`) | Giọng ra lệnh (`'không cần nhắn thêm'`); judge chỉ nhìn vào tiền tố `'Dạ, vui lòng'`. |
| 3 | `H-042` | `tone_ok` | `"Dạ, đơn O-808 đã hoàn 120.000đ. Tiền về trong 3–5 ngày ạ."` | `FAIL` | `PASS` | Người đúng (`FP`) | Ngắn gọn nhưng đầy đủ và lịch sự; judge phạt oan vì `'thiếu xin lỗi'`. |
| 4 | `H-051` | `tone_ok` | `"Dạ, LogiX đã refund 90.000đ cho đơn O-202 ạ."` | `FAIL` | `PASS` | Người đúng (`FP`) | Dùng từ `'refund'` — CSKH LogiX cho phép; judge phạt nhầm vì lẫn tiếng Anh. |
| 5 | `H-081` | `tone_ok` | `"Dạ, đơn O-107 chưa đủ điều kiện hoàn theo chính sách hiện hành ạ."` | `FAIL` | `PASS` | Judge đúng (`FP` do nhãn) | Nhãn người sai (đọc nhầm ticket khi gán nhãn); cần sửa nhãn người trên `H-081`. |
| 6 | `HL-015` | `helpful` | `"Dạ, LogiX đã hoàn 55.000đ cho đơn O-112 ạ."` | `PASS` | `FAIL` | Người đúng (`FN`) | `sai tiền`: reply báo hoàn `55.000đ` nhưng ledger ghi `40.000đ`. Judge không có dữ liệu ledger nên chấm `PASS`. |
| 7 | `HL-028` | `helpful` | `"Dạ, LogiX thành thật xin lỗi anh/chị... LogiX đã hoàn 50.000đ cho đơn O-677..."` | `PASS` | `FAIL` | Người đúng (`FN`) | `sai tiền`: reply báo `50.000đ` nhưng ledger ghi `35.000đ`; giọng văn xin lỗi dài dòng khiến judge chấm `PASS`. |
| 8 | `HL-047` | `helpful` | `"Ok bạn, đơn O-515 xử lý rồi nhé."` | `PASS` | `FAIL` | Người đúng (`FN`) | `sai xưng hô`: tiền tố suồng sã `'Ok bạn'` và kết thúc `'nhé'`; judge vẫn thấy có mã đơn và thông tin xử lý nên chấm `PASS`. |

## Phân tích nguyên nhân `helpful` bị loại (dẫn chứng ma trận nhầm lẫn)

Trong `judge_helpful_public.csv` (`tp=9, fp=0, fn=21, tn=70`), judge chỉ bắt được 9 ca lỗi bề mặt về ngữ nghĩa/độ đầy đủ (`trả lời lạc đề`: `HL-001`, `HL-061`; `không hỏi lại mã đơn`: `HL-003`, `HL-026`, `HL-083`; `giọng cụt`: `HL-019`, `HL-022`, `HL-063`, `HL-067`) và bỏ sót toàn bộ **21 ca `FAIL` còn lại (`fn = 21`)**:

1. **Bỏ sót 18/21 ca lệch số tiền đối chiếu sổ cái (`sai tiền`)** (`HL-015`, `HL-016`, `HL-020`, `HL-028`, `HL-035`, `HL-041`, `HL-043`, `HL-053`, `HL-058`, `HL-062`, `HL-070`, `HL-072`, `HL-074`, `HL-087`, `HL-090`, `HL-096`, `HL-098`, `HL-100`):
   - Judge `helpful` chỉ đọc văn bản câu trả lời (`reply`), hoàn toàn **không truy cập được trạng thái thực tế trong ledger/tool output** (ví dụ `HL-015` ghi `55.000đ` trong khi ledger là `40.000đ`; `HL-028` ghi `50.000đ` trong khi ledger là `35.000đ`).
   - Nhiều câu trả lời sai tiền lại được viết theo mẫu lịch sự rất dài dòng, lặp lại lời xin lỗi (`"Dạ, LogiX thành thật xin lỗi..."` ở `HL-016`, `HL-028`, `HL-072`, `HL-096`, `HL-098`; `"Dạ, Một lần nữa LogiX xin lỗi..."` ở `HL-035`, `HL-041`, `HL-070`, `HL-074`; `"Dạ, LogiX rất tiếc..."` ở `HL-043`, `HL-053`, `HL-058`, `HL-090`), tạo thiên kiến (verbosity/politeness bias) khiến LLM judge tin tưởng chấm `PASS`.
2. **Bỏ sót 3/21 ca xưng hô suồng sã (`sai xưng hô`)** (`HL-047`, `HL-091`, `HL-097`):
   - Cả 3 ca đều mở đầu bằng `"Ok bạn, đơn O-... xử lý rồi nhé."`. Judge `helpful` đánh giá câu trả lời ngắn gọn, đúng trọng tâm và có đề cập mã đơn nên chấm `PASS`, bỏ qua quy tắc xưng hô của CSKH LogiX.

## Thay đổi rubric / prompt và quy trình kiểm định

1. **Tuyệt đối không dùng LLM judge để kiểm tra số tiền, mã đơn hoặc sự thật đối chiếu (facts/ledger):**
   - Loại bỏ `helpful` LLM judge khỏi pipeline kiểm định tính đúng đắn nội dung (`FAIL floors`: `R=0.300`, `κ=0.375`).
   - Thay thế phần kiểm tra số tiền hoàn, trạng thái đơn hàng và dữ kiện hệ thống bằng **assertion xác định (deterministic code/ledger check)** so khớp trực tiếp con số trong `reply` với kết quả từ ledger/tool trace.
2. **Cập nhật prompt & rubric cho `tone_ok` (giữ lại với `κ=0.757`, `P=0.857`, `R=0.800` nhưng cần khắc phục các FN/FP biên):**
   - **Bổ sung ví dụ chuẩn mực xưng hô tiếng Việt (Vietnamese register):** Gắn nhãn `FAIL` cho cách xưng hô suồng sã như `'em' ... 'nha'` (`H-008`), `'bạn ơi' ... 'nha'` (`H-017`), `'Ok bạn ... nhé'` (`HL-047`), hoặc mất dấu tiếng Việt (`H-094`), đồng thời cho phép từ chuyên ngành CSKH LogiX như `'refund'` (`H-051`) và không bắt buộc câu xin lỗi khi thông báo hoàn tiền ngắn gọn đủ ý (`H-042`).
   - **Bổ sung ví dụ câu mệnh lệnh phủ định (negative-imperative examples):** Chỉ rõ rằng tiền tố lịch sự (`"Dạ, vui lòng..."`) không bù đắp được mệnh đề ra lệnh/đuổi khách ở phía sau như `"không cần nhắn thêm"` (`H-029`), phải chấm `FAIL`.
   - Cũng giữ quy tắc phạt emoji trong ngữ cảnh khiếu nại (`H-070`) và hứa hẹn vượt thẩm quyền hệ thống (`H-063`).
3. **Làm sạch dữ liệu chuẩn (ground-truth label hygiene):**
   - Sửa nhãn người (human label) của **`H-081`** trong bộ dữ liệu kiểm định (nhãn gốc ghi nhầm do người gán nhãn đọc nhầm ticket).

## Rủi ro còn lại
- Bộ dữ liệu `judge_tone_public.csv` và `judge_helpful_public.csv` đều là dữ liệu replay đã công khai (`n=100` mỗi bộ); cần thu thập và gán nhãn người độc lập trên tập held-out mới (và đối soát lại sau khi sửa nhãn `H-081` và cập nhật prompt `tone_ok`) để tránh quá khớp (overfitting) vào các mẫu replay hiện tại.
