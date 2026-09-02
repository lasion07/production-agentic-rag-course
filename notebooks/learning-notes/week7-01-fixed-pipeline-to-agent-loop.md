# Week 7.1 — Từ fixed RAG pipeline đến agent loop

Quay lại: [Mục lục sổ học tập](README.md)

## Mục tiêu học tập

- Phân biệt fixed pipeline với bounded agent loop.
- Hiểu vai trò của state, context, node, edge và tool.
- Tách guardrail khỏi routing decision.
- Thiết kế stop condition, retry và resource budget.
- Chọn fallback an toàn khi router, evidence hoặc deadline gặp lỗi.

## Tóm tắt một phút

Fixed RAG luôn chạy một đường `retrieve → generate`. Agent loop quan sát state, chọn action, gọi tool, cập nhật state rồi có thể lặp lại. Production agent phải là bounded loop: retry, LLM calls, token và deadline đều có giới hạn deterministic. LLM xử lý quyết định ngữ nghĩa; code bảo vệ invariant. Generation vẫn phải tính vào tổng budget và nên được reserve từ đầu. Degraded/error response không nên được cache với TTL bình thường.

## Fixed pipeline và agent loop

```text
Fixed RAG:
query → retrieve → context → generate → response

Agent loop:
observe state → decide → act/tool → update state
     ↑                                  │
     └──────── retry nếu còn budget ────┘
```

Một agent loop cần:

- State để nhớ lịch sử và kết quả trung gian.
- Decision point để chọn action tiếp theo.
- Tool để truy cập hệ thống bên ngoài.
- Loop để sửa sai hoặc thử lại.
- Stop condition để không chạy vô hạn.

## Graph hiện có

```text
START
  ↓
guardrail
  ├─ score < 60 → out_of_scope → END
  └─ score ≥ 60 → retrieve → tool_retrieve → grade_documents
                                      ├─ relevant → generate_answer → END
                                      └─ irrelevant → rewrite_query → retrieve
```

Graph hiện tại là conditional agentic workflow, chưa phải agent tự do kiểu ReAct.

## State và Context

```text
State = agent đã biết và đã làm gì
Context = agent được dùng gì và bị giới hạn thế nào
```

State thay đổi:

- `messages`
- `original_query`, `rewritten_query`
- `retrieval_attempts`
- `guardrail_result`, `routing_decision`
- `grading_results`, `relevant_sources`

Context tương đối ổn định:

- Ollama, OpenSearch, embedding và tracing clients.
- Model, `top_k`, threshold.
- Maximum retrieval attempts.

## Guardrail khác Router

```text
Guardrail: request có được phép xử lý không?
Router: request hợp lệ nên được xử lý bằng cách nào?
```

Action schema phù hợp hơn:

```text
direct_response
retrieve
clarify
reject
```

Direct response chỉ nên dùng cho greeting, mô tả chức năng hoặc clarification. Factual claims về corpus nên retrieval để có evidence.

## Phát hiện từ code audit

1. README nói agent quyết định khi nào retrieval, nhưng graph thực tế chỉ route `out_of_scope` hoặc `retrieve`; chưa có `direct_response`.
2. Khi lần retrieval cuối không relevant, graph vẫn rewrite thêm một lần rồi mới phát hiện đã hết attempts. LLM rewrite này bị lãng phí.
3. `retrieval_attempts` tăng khi tool call được tạo, chưa phân biệt tool thực thi thành công hay timeout.

Thiết kế tốt hơn:

```text
grade irrelevant
├─ attempts < max → rewrite → retrieve
└─ attempts ≥ max → fallback → END
```

## Production budgets

Không chỉ giới hạn retrieval:

```text
retrieval attempt budget
rewrite budget
LLM call budget
token budget
tool error budget
total deadline
```

Generation phải được tính và reserve:

```text
total_llm_budget = planning_budget + generation_reserve
```

Trước khi chạy action:

```python
used + next_action_cost + minimum_finish_cost <= total_budget
```

Không nên bắt đầu một nhánh mà agent không còn đủ budget để tới terminal success.

## Graceful degradation

Router timeout nhưng deadline còn đủ:

```text
route_decision = fallback_retrieve
router_status = error
degraded = true
→ fixed RAG
```

Nếu fixed RAG thành công, root request có thể `ok`; router child observation vẫn `error`.

Evidence tốt nhưng không đủ thời gian generation:

```text
cancel pending work
→ degraded extractive response + sources
→ trace deadline_exceeded
```

Evidence relevance thấp và không còn planning budget:

```text
insufficient_evidence
```

Cache policy:

- Validated answer: TTL bình thường.
- Degraded extractive response: không cache hoặc TTL rất ngắn.
- Timeout/error/insufficient evidence: thường không cache.

## Câu hỏi ôn tập

1. Agent loop khác fixed RAG ở đâu?
2. Vì sao retry limit phải do code kiểm soát?
3. Guardrail và router trả lời hai câu hỏi nào?
4. Vì sao generation phải nằm trong LLM budget?
5. Khi nào child router `error` nhưng root request vẫn `ok`?

<details>
<summary>Đáp án gợi ý</summary>

1. Agent có state, conditional action, tool, loop và stop condition.
2. LLM nondeterministic; invariant production phải deterministic.
3. Guardrail kiểm tra được phép; router chọn cách xử lý request hợp lệ.
4. Đây thường là call chậm và tốn tài nguyên nhất; bỏ nó làm budget sai nghĩa.
5. Khi router lỗi nhưng fixed-RAG fallback trả response thành công.

</details>

## Checklist tự đánh giá

- [x] Phân biệt fixed pipeline và agent loop.
- [x] Đọc được graph hiện tại.
- [x] Phân biệt State và Context.
- [x] Tách guardrail, router và clarification.
- [x] Thiết kế bounded loop và generation reserve.
- [x] Chọn đúng fallback theo evidence và deadline.
- [x] Phát hiện mismatch giữa tài liệu và code.

**Trạng thái: Week 7.1 hoàn thành.**
