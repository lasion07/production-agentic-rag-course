# Kết quả bài kiểm tra số 2 — Week 7 Agentic RAG

Quay lại: [Đề kiểm tra](assessment-02-week7-agentic-rag.md) · [Tổng kết Week 7](week7-summary.md) · [Mục lục](README.md)

## Kết quả

- **Tổng điểm: 85/100 — Đạt, mức hiểu tốt.**
- Phần A: **20/20**
- Phần B: **24/25**
- Phần C: **25/35**
- Phần D: **16/20**
- Không phần nào dưới 50%.

Em đã nắm chắc bounded agent loop, state merge semantics, semantic round, retry amplification, false observability và tư duy regression evaluation. Phần cần củng cố là failure contract: mọi nhánh phải nói rõ route, HTTP status, business status, counter và lý do.

## Chấm chi tiết

### Phần A — 20/20

Cả 10 câu đều đúng: **B, C, B, B, B, B, C, C, A, B**.

### Phần B — 24/25

#### Câu 11 — 7/7

- Terminal route: `generate`/`generate_answer`.
- `retrieval_rounds=2`, `rewrite_count=1`.
- Không có infrastructure retry: cả hai lần retrieval đều thực thi thành công; lần thứ hai là semantic recovery bằng query mới.

#### Câu 12 — 5/6

Tính đúng:

- Toàn agent chạy tối đa `1 + 2 = 3` lần.
- Jina chạy tối đa `3 agent executions × 2 rounds × 3 HTTP attempts = 18` attempts.

Ý “mỗi failure scope có một retry owner” đúng. Để ngăn amplification đầy đủ hơn, cần thêm **shared deadline/global attempt budget** hoặc không cho proxy retry một request không idempotent/đã tiêu hết retry budget.

#### Câu 13 — 6/6

Đúng hoàn toàn:

```python
messages = [HumanMessage("Q1"), HumanMessage("Q2")]
grading_results = [grade_round_2]
```

Schema `current_grading` và `grading_history` có reducer giúp tách current state khỏi audit history.

#### Câu 14 — 6/6

Phân biệt đúng `blocked` và `fail`, đồng thời không đánh đồng `3/18` với agent quality. Sau khi sửa dependency construction, cần chạy lại các response/E2E contract từng bị blocked.

### Phần C — 25/35

#### Câu 15 — 5/7

Em nhận ra không được generate khi canonical evidence rỗng và biết trace nguyên nhân. Tuy nhiên, điều đầu tiên cần gọi tên là **state invariant violation**:

```text
routing_decision=generate_answer
AND relevant_documents=[]
```

Safe default nên là `insufficient_evidence` hoặc internal error theo contract. Chỉ rewrite khi một policy recovery rõ ràng xác nhận còn semantic round; không tự suy diễn từ routing decision mâu thuẫn. Trace tối thiểu: node, decision, canonical document count/IDs, grading output, retrieval rounds và tool status.

#### Câu 16 — 3/7

Chọn BM25 fallback là đúng, nhưng thiếu quyết định deadline và status cụ thể.

- Không chờ Jina 20 giây vì chỉ còn 8 giây và phải giữ 5 giây generation reserve.
- BM25 có relevant evidence: `HTTP 200`, `business_status=degraded`, `actual_search_mode=bm25`.
- BM25/OpenSearch cũng không hoạt động: `HTTP 503`, `business_status=retrieval_unavailable`; không generation.

#### Câu 17 — 7/7

Đúng: đây là false observability kết hợp config propagation failure. Contract cần truyền typed execution config xuyên suốt và response/trace phải lấy **actual values** từ kết quả thực thi, không phản chiếu request ban đầu.

#### Câu 18 — 5/7

Phần readiness đúng, nhưng cần tách hai khái niệm:

- Component health endpoint vẫn có thể green vì PostgreSQL, OpenSearch và Ollama đang sống.
- Riêng capability `/ask-agentic` phải **not ready** vì không construct được service.

Bounded readiness check phù hợp: construct dependency graph/service và chạy deterministic dry-run/smoke route không gọi generation đắt tiền.

#### Câu 19 — 5/7

Nhận diện đúng nguy cơ error message bị grade như evidence và route tổng quát đúng. Structured result cần đầy đủ hơn:

```python
{
    "status": "success | degraded | error",
    "documents": [],
    "actual_search_mode": "hybrid | bm25 | none",
    "error_type": None,
    "retryable": False,
    "attempts": 1,
}
```

Post-tool router: `success/degraded → grade_documents`; `error retryable + budget → retry`; `error + fallback available → fallback`; hết khả năng phục hồi → `retrieval_unavailable`.

### Phần D — 16/20

#### Câu 20 — 10/12

Thiết kế giàu ý và có đầy đủ state/context, router ban đầu, budget, deadline, terminal outcomes và citation invariant. Điểm cần chỉnh:

- Tách **initial action router** (`reject/direct_response/clarify/retrieve`) khỏi **post-tool router**.
- Tool error hết retry không phải lúc nào cũng `SYSTEM_FALLBACK`: thử fallback mode nếu khả dụng; nếu retrieval hoàn toàn hỏng thì terminal contract nên là `retrieval_unavailable`.
- `retrieval_rounds`, `tool_attempts`, `embedding_attempts`, `fallbacks` nên là counter riêng.
- Khi không còn đủ generation reserve, không “force synthesis”; chỉ bắt đầu generation khi phần thời gian còn lại đủ reserve, nếu không trả bounded fallback.

#### Câu 21 — 6/8

Baseline/candidate comparison, manual/LLM judge, canary, cutover và rollback đều tốt. Tuy nhiên sáu-item dataset v0 hiện có gold contract về **route, status, mode và call budget**, không phải mỗi item tương ứng một P1 hay luôn có gold citation/language.

Code evaluators ưu tiên cho dataset hiện tại:

- `route_contract_pass`
- `response_contract_pass` — HTTP/business status
- `call_budget_pass` — rounds, attempts, failures, fallbacks
- actual search mode và source-count invariant

Faithfulness/citation judge chỉ nên thêm sau khi endpoint chạy được, có output thật và đã hiệu chỉnh bằng human labels.

## Ba mẫu cần ghi nhớ

### 1. Failure decision record

Mỗi tình huống production nên trả lời đủ:

```text
Failure class → retry? → fallback? → next route
→ HTTP status → business status → counters/trace
```

### 2. Health không đồng nghĩa readiness

```text
Dependencies alive ≠ capability constructible ≠ endpoint behavior correct
```

Health đo thành phần sống; readiness đo endpoint đã sẵn sàng nhận traffic; smoke/evaluation đo hành vi đúng.

### 3. Hai loại retry

```text
Same query + same operation = infrastructure/tool retry
New/re-written query = semantic retrieval round
```

Hai loại phải có counter, budget và owner riêng.

## Kế hoạch ôn tập cá nhân

1. Với mỗi fault của dataset v0, viết một dòng đủ bảy trường trong failure decision record.
2. Viết truth table cho `tool status × retryable × budget × fallback availability`.
3. Viết ba probes riêng: liveness, agentic readiness và behavioral smoke test.
4. Sau khi sửa technical debt P1, chạy lại sáu case và so sánh baseline/candidate bằng deterministic evaluators trước khi thêm LLM judge.

## Kết luận

**Week 7 đã hoàn thành.** Em đủ nền tảng để thiết kế một bounded Agentic RAG có state và routing rõ ràng. Trước khi coi thiết kế đạt production-grade, cần biến failure handling thành contract máy kiểm tra được thay vì chỉ mô tả bằng ý định.
