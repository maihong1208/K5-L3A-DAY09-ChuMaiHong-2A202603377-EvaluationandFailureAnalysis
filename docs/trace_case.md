# Trace case: từ trace tới quyết định sai đầu tiên

Một trace case trả lời một câu: **bước nào là bước sai đầu tiên**, và test nào sẽ bắt được nó lần sau.

```bash
cd src
python -m lab9.trace_case --shape seeded_regression --claim C-002 --seed 11
python -m lab9.trace_case --shape fixed --claim C-002 --seed 11   # đối chứng
```

Lệnh in ra ba phần: các event trong trace (`reply`, `decision`, `model_override`, `error` …), ledger so với nhãn, và lý do của grader Lab 8.

## Case đã phân tích (`C-002`: `seeded_regression@11` & `swarm@55` vs `fixed`)

| Trường | Nội dung |
|---|---|
| Trial | `seeded_regression C-002@11` (`run_id`: `R-seeded_regression-C-002-s11`) và `swarm C-002@55` (`run_id`: `R-swarm-C-002-s55`) |
| Triệu chứng | `TrialPass` (`pass_rate`) fail (`status resolved != denied`); `DbFactKept` (`db_fact_kept`) fail (`1 override event(s)`); `RefundAmountCorrect` (`refund_amount_correct`) fail (`ledger=20000 != expected=0`). Trên `seeded_regression C-002@11`, event 6 `reply` nói `"Dạ, LogiX đã hoàn 20.000đ cho đơn O-202."`, khớp ledger `refund_vnd=20000`, `refund_count=1`, `status=resolved` nhưng trái label (`refund_vnd=0`, `refund_count=0`, `status=denied`); trên `swarm C-002@55`, trace không có event `reply` và ledger vẫn ghi sai `refund_vnd=20000`, `refund_count=1`, `status=resolved`. |
| Bước sai đầu tiên | Event **3**, `kind: model_override`, payload `{"delay_days": 5}` |
| Vì sao là bước *đầu tiên* | Event 1 (`handoff`) giao đúng `claim_id: "C-002"`, `task: "check_applicable_policy"`, `principal_scope: "owner_order_only"`, `allowed_tools: ["lookup_order", "lookup_policy", "compute_compensation"]`; Event 2 (`investigator`) gọi `lookup_order` trả đúng sự thật DB cho `O-202` (`visible: true`, `delay_days: 2`, `shipping_fee_vnd: 20000`, `paid_vnd: 100000`, `policy_count: 1`). Chỉ từ Event 3 agent mới ghi đè `delay_days` từ `2` thành `5` theo ticket, kéo theo Event 4 (`quote`) tính sai `amount_vnd: 20000` (`SHIP-LATE-03`). |
| Failure mode | `FM-03` (`ticket_trust` — tin ticket hơn DB, trong [failure_taxonomy.md](failure_taxonomy.md)) |
| Đối chứng | Cùng `C-002@11` (`R-fixed-C-002-s11`) và `C-002@55` (`R-fixed-C-002-s55`) trên `fixed`: Event 1 (`handoff`) và Event 2 (`investigator` với `delay_days: 2`) giữ nguyên, không có `model_override` ở bước 3; Event 3 là `quote` tính theo DB ra `{"amount_vnd": 0, "reason": "no_entitlement", "clause_ids": [], "parts": {}}`, Event 4 là `reply` `"Dạ, đơn O-202 chưa đủ điều kiện hoàn theo chính sách hiện hành."`, ledger khớp label (`refund_vnd=0`, `refund_count=0`, `status=denied`, `unexpected ledger rows: 0`) và `TrialPass`, `DbFactKept`, `RefundAmountCorrect` đều PASS. |
| Regression test | `test_trace_case_c002_seed55_swarm_vs_fixed` trong [src/tests/test_lab9_graders.py](../src/tests/test_lab9_graders.py) — kiểm tra `bad["lab8_pass"] is False`, `DbFactKept` trả `False`, `RefundAmountCorrect` trả `False` trên `swarm C-002@55`, và cả ba đều trả `True` trên `fixed C-002@55`. Đã chạy `pytest` xác nhận `swarm` fail (`DbFactKept=False`, `RefundAmountCorrect=False`) và `fixed` pass (`DbFactKept=True`, `RefundAmountCorrect=True`). |
| Chưa chắc chắn | Trace đơn lẻ không chứng minh được: (1) nếu một variant ghi đè ngầm trong bộ nhớ mà không emit event `model_override` (ví dụ `quiet_override`), step-level grader `DbFactKept` trên trace sẽ không thấy lỗi mà phải dựa vào outcome grader (`RefundAmountCorrect` / `TrialPass`); (2) prompt/lập luận nội bộ bên trong mô hình dẫn tới quyết định override ở seed chia hết cho 5 hoặc khi bật `ticket_trust`. |

## Quy tắc

- Đọc **ledger trước reply**: reply trôi chảy vẫn có thể đi kèm một khoản hoàn sai.
- "Bước sai đầu tiên" phải dẫn số event cụ thể, không phải "agent bị nhầm".
- Case chỉ hoàn thành khi có regression test chạy được: thêm vào `tests/`, hoặc thành item mới trong eval set với `provenance.from_trace`.
