# Week 7.5 — Evaluation-driven hardening với sáu regression cases

Quay lại: [Tổng kết Week 7](week7-summary.md) · [Technical debt](technical-debt-backlog.md) · [Mục lục](README.md)

## Mục tiêu

Dùng dataset v0 làm release contract: chụp baseline, sửa P1 theo từng failure boundary, chạy candidate và chỉ kết luận trong phạm vi tín hiệu đã đo.

## Kết quả ngắn gọn

```text
Baseline:  pass=3, fail=9, blocked=6
Candidate: pass=18, fail=0, blocked=0
```

Đây là **18 deterministic contract checks**, không phải điểm semantic answer quality.

## Vì sao phải sửa test harness trước?

Runner ban đầu hard-code actual failures của W7E-04/05/06. Source có được sửa thì test vẫn đỏ. Runner mới gọi production functions và deterministic routers, vì vậy score thay đổi do behavior thay đổi.

Nguyên tắc:

```text
Test phải quan sát system under test, không được tự viết sẵn kết quả muốn chứng minh.
```

## Các contract đã harden

### 1. Construction và config propagation

- Factory nhận `model` đúng contract.
- API truyền `model`, `top_k`, `use_hybrid`, `categories` xuyên suốt.
- Response lấy `chunks_used` và `search_mode` từ actual execution.

### 2. Structured retrieval outcome

```text
success  → grade_documents
degraded → grade_documents, business_status=degraded
error    → retrieval_unavailable, không grade error message
```

Outcome chứa documents, requested/actual mode, error type, retryable và các counters.

### 3. Infrastructure failure khác semantic miss

- OpenSearch zero hits hợp lệ: `success + documents=[]`.
- OpenSearch timeout: explicit `error`, tối đa hai physical attempts.
- Jina timeout: tối đa hai attempts rồi BM25 fallback.
- `429 Retry-After` dài hơn deadline: không chờ; chuyển BM25 để giữ generation reserve.

### 4. Evidence và routing invariant

```text
generate_answer ⇒ relevant_documents không rỗng
```

Sau round cuối, empty/irrelevant evidence đi thẳng `insufficient_evidence`, không rewrite thừa và không generation rỗng context.

### 5. Source of truth cho response

Canonical `relevant_documents` được dùng để tạo:

- generation context;
- API sources;
- `chunks_used`;
- citation/evidence boundary.

## Lỗi chỉ runtime mới phát hiện

Mock Ollama có `get_langchain_model()` nhưng production `OllamaClient` ban đầu không có. Unit tests cũ xanh nhưng request thật fallback guardrail score 50 và reject nhầm query nghiên cứu. Adapter `ChatOllama` đã được thêm vào production client và có contract test riêng.

## Bằng chứng kiểm thử

- Sáu cases: **18/18 deterministic checks pass**.
- Agent + agentic API tests: **61/61 pass** tại mốc đầu.
- Toàn bộ hermetic tests, không gồm external arXiv integration: **138/138 pass**.
- Full graph tests bao phủ success, two-zero-results và OpenSearch unavailable.
- Langfuse candidate run: [candidate-p1-hardening-2026-09-02](https://us.cloud.langfuse.com/project/cmti23w7n0atbad0hayhhjbby/datasets/cmtjmji6k00njad0d50dt5ypg/runs/cc5bd897-982a-480c-a9c3-2d17d074caf6), 6 items × 3 deterministic evaluators.
- Docker image rebuild bị dừng ở bước export layer; runtime được smoke-test bằng source copy vào container tạm.
- Runtime chứng minh service construct được, retrieve đúng paper/source và outer deadline trả `HTTP 504/deadline_exceeded` ở khoảng 120 giây thay vì treo vô hạn.
- Degraded extractive generation trước outer deadline có unit contract; cleanup margin cuối chưa được smoke-test lại trên container thật.

## Giới hạn chưa được chứng minh

- Chưa có semantic answer evaluator đã hiệu chỉnh bằng human labels.
- Circuit breaker chưa được triển khai.
- Guardrail/grading có thể tiêu tốn phần lớn total deadline; cần phase budgets hoặc router rẻ hơn để đạt success SLO trên M1.
- Async timeout không thể dừng thread OpenSearch sync đã chạy; chỉ dừng việc await.
- External arXiv integration test không thuộc hermetic regression suite.
- Canonical evidence/source đã đồng nhất, nhưng citation allowlist/claim-level validation chưa nằm trong sáu-item v0.

## Câu hỏi ôn tập

1. Vì sao `18/18` không đồng nghĩa answer quality hoàn hảo?
2. Vì sao zero hits và timeout phải có hai structured outcomes khác nhau?
3. Tại sao response phải lấy `actual_search_mode` từ execution thay vì request?
4. Mock interface drift đã che lỗi Ollama adapter như thế nào?

## Đề xuất thực hành

Thêm một case `guardrail_dependency_failure` với expected policy rõ ràng: fail-open sang bounded retrieval hay fail-closed/out-of-scope. Không chọn policy bằng accident của threshold mặc định.
