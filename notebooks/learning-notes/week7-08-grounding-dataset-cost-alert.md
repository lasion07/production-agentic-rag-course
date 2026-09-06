# Week 7.8 — Labeled answer eval, grounding validation và cost alert

## 1. Labeled answer dataset

- Dataset v0 có 7 case, phủ đủ 3 public arXiv papers và 1 case cross-paper.
- `input`: request thực thi.
- `expectedOutput`: contract có thể kiểm tra tự động.
- `metadata`: nhóm lỗi, paper làm evidence và trạng thái review.
- Gold answer do AI soạn chỉ là **provisional**; cần human review trước khi dùng làm release gate.

## 2. Citation allowlist

- Mỗi evidence chunk mang theo `arxiv_id`.
- Answer chỉ được cite ID thuộc evidence pool của đúng request.
- Citation chuẩn: `[arXiv:<arxiv_id>]`.
- Citation hợp lệ về cú pháp nhưng không thuộc allowlist vẫn là lỗi grounding.

## 3. Claim validation

- Validator deterministic hiện kiểm tra decimal, percentage, range và magnitude.
- Một measured value trong answer phải xuất hiện trong evidence.
- Validator này không chứng minh semantic entailment; ví dụ số đúng nhưng gán nhầm paper vẫn cần dataset evaluator hoặc human review phát hiện.
- Output không pass validation không được trả như answer thành công; API chuyển thành `insufficient_evidence`.

## 4. Cost alert

- Langfuse tự ghi token và cost trên `ChatOpenAI` generation.
- Baseline quan sát: p95 khoảng `$0.0034` cho một generation.
- Budget ban đầu: warning `$0.005`, alert `$0.010`, cửa sổ 1 giờ.
- Sau regression 7 case, p95 tăng lên khoảng `$0.00695` và checker báo `warning`; case cross-paper với `top_k=6` là ứng viên cần tối ưu evidence budget.
- Native Langfuse alert `OpenAI generation p95 cost budget` đã ACTIVE/OK và liên kết với Slack automation `slack_production_agentic_rag`.
- Alert theo generation không bằng tổng cost của một agent request vì request còn guardrail, grading và có thể rewrite.
- Script kiểm tra có exit code: `0=ok/no_data`, `2=warning`, `3=alert`.

## 5. Câu hỏi ôn tập

1. Vì sao schema-valid citation vẫn có thể là citation sai?
2. Vì sao kiểm tra một con số có trong evidence chưa đủ chứng minh claim đúng?
3. Khi nào nên alert theo generation cost, khi nào nên tổng hợp theo trace?
4. Vì sao expected output do AI tạo chưa thể xem là ground truth?

## 6. Technical debt còn lại

- Human-review 7 expected outputs và nâng dataset lên trạng thái approved.
- Thêm attribution validator ở mức từng claim–citation, không chỉ toàn evidence pool.
- Ghi tổng cost của toàn agent request thành trace-level metric/score để alert chính xác hơn.
