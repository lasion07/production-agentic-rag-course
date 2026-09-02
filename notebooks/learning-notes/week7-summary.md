# Tổng kết Week 7 — Production Agentic RAG

Quay lại: [Mục lục sổ học tập](README.md)

## Mục tiêu đã đạt

- Phân biệt fixed RAG với bounded agent loop.
- Đọc được state, context, node, reducer và conditional edge.
- Tách semantic decision khỏi deterministic policy.
- Phân biệt infrastructure retry với semantic retry.
- Thiết kế tool outcome, fallback, deadline và counters.
- Xây regression dataset và fault-injection baseline.

## Tóm tắt một phút

Production agent không phải LLM được phép lặp tự do. Nó là state machine có action schema, deterministic budgets, typed tool outcomes và fail-safe terminal routes. LLM đánh giá ngữ nghĩa; code bảo vệ invariant. Tool error không được biến thành semantic miss. Evaluation đi theo thứ tự availability/contract → agent policy → semantic quality.

## Luồng agent mục tiêu

```text
START
→ guardrail/router
   ├─ reject → END
   ├─ direct_response → END
   └─ retrieve
       → execute_tool
       → inspect_tool_result
          ├─ success + documents → grade
          │    ├─ relevant → generate → validate → END
          │    └─ irrelevant + còn round → rewrite → retrieve
          ├─ success + empty + còn round → rewrite → retrieve
          ├─ success + empty + hết round → insufficient_evidence → END
          ├─ degraded + documents → grade → grounded degraded answer
          └─ error + hết recovery budget → retrieval_unavailable → END
```

## State, Context và reducers

```text
State   = agent biết gì và đã làm gì trong execution
Context = dependency/config agent được phép dùng
```

- State: messages, original/rewritten query, rounds, routing result, evidence, grading.
- Context: clients, model, thresholds, limits và deadline.
- Node trả partial update.
- Không có reducer: giá trị mới thường overwrite.
- `add_messages`: merge message history theo message semantics.

## Invariants trước generation

```text
relevant_documents không rỗng
context = documents đã được grade relevant
citations/sources = evidence thực sự dùng
route thuộc allowlist
attempts và deadline còn hợp lệ
```

Missing hoặc contradictory state phải fail-safe, không default generation.

## Retry và failure handling

```text
Infrastructure retry:
cùng query, cùng operation, lỗi tạm thời

Semantic retry:
search thành công nhưng evidence không relevant
→ rewrite query
```

Tool outcome cần phân biệt:

- `success`: dependency chạy đúng, kể cả zero hits.
- `degraded`: fallback chạy được và vẫn có evidence.
- `error`: không thể thực hiện retrieval.

Terminal outcomes:

- HTTP 200 + `degraded`: fallback vẫn trả grounded answer.
- HTTP 200 + `insufficient_evidence`: search thành công nhưng thiếu evidence.
- HTTP 503 + `retrieval_unavailable`: không thể kiểm tra corpus.

## Budgets và counters

Tách riêng:

- `retrieval_rounds`
- `embedding_http_attempts`
- `search_attempts`
- `tool_failures`
- `zero_result_rounds`
- `fallbacks_total`

Ngăn retry amplification:

```text
client attempts × tool attempts × semantic rounds × whole-request attempts
```

Mọi action phải còn đủ deadline cho chính nó và minimum finish/generation reserve.

## Evaluation

Ba tầng:

1. Availability/contract.
2. Agent policy.
3. Semantic quality.

Deterministic contract dùng code evaluator. Semantic judge chỉ thêm sau khi có valid outputs, observed failure modes và human labels để calibration.

Không gộp checks khác nghĩa hoặc blocked checks thành generic quality score.

## Bằng chứng thực hành

- GitNexus: 191 files, 3.212 symbols, 168 flows.
- OpenSearch corpus: 81 chunks.
- Agent test baseline: 30 pass, 2 behavioral failures, 22 setup errors.
- Fault injection: pass=3, fail=9, blocked=6.
- Langfuse regression dataset: 6/6 active items.
- Dataset: `production-agentic-rag-week7-regression-v0`.

## Những lỗi source quan trọng

1. Factory/dependency mismatch làm `/ask-agentic` trả 500.
2. Unsafe default generation và rewrite thừa.
3. Evidence có thể lệch API sources.
4. OpenSearch exception bị che thành zero hits.
5. Jina error propagate, chưa BM25 fallback.
6. Request parameters bị bỏ qua nhưng response báo requested values.
7. Agent test fixtures bị thiếu.

Chi tiết: [Technical debt backlog](technical-debt-backlog.md).

## Câu hỏi tự ôn

1. Vì sao bounded agent loop an toàn hơn loop do LLM tự dừng?
2. Khi nào rewrite query và khi nào retry cùng tool call?
3. Vì sao zero hits không phải circuit-breaker failure?
4. `insufficient_evidence` khác `retrieval_unavailable` thế nào?
5. Vì sao health xanh chưa đủ kết luận endpoint ready?
6. Khi nào LLM-as-a-judge đáng được thêm?

## Trạng thái

**Week 7 hoàn thành về kiến thức và practical baseline. Chờ bài kiểm tra tổng kết.**
