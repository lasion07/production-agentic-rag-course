# Bài kiểm tra thường xuyên số 2 — Week 7 Agentic RAG

Quay lại: [Tổng kết Week 7](week7-summary.md) · [Mục lục](README.md)

## Thông tin bài kiểm tra

- Phạm vi: agent loop, state/routing, tool failure handling, fault injection và evaluation.
- Tổng điểm: **100**.
- Thời gian đề xuất: **75–90 phút**.
- Lần làm đầu: không xem ghi chú và không chạy code.
- Trả lời tình huống phải nêu route, status và lý do.

## Phần A — Kiến thức cốt lõi (20 điểm)

Mỗi câu 2 điểm. Chọn một đáp án đúng nhất.

### Câu 1

Điểm khác biệt quan trọng nhất của bounded agent loop so với fixed RAG là:

A. Luôn dùng nhiều LLM hơn
B. Có state, conditional actions và deterministic stop budgets
C. Không cần retrieval
D. Không cần API

### Câu 2

Thành phần nào phù hợp nhất để đặt OpenSearch client và maximum attempts?

A. Message history
B. Retrieved document
C. Runtime Context
D. Final answer

### Câu 3

Một list field trong state không có reducer thường sẽ:

A. Tự append mọi update
B. Bị update mới overwrite
C. Được Redis merge
D. Không thể thay đổi

### Câu 4

Trong LangGraph đang dùng, `retrieve` node chủ yếu:

A. Trực tiếp gọi OpenSearch và generation
B. Tạo tool call; ToolNode mới thực thi tool
C. Chỉ ghi Langfuse score
D. Tạo PostgreSQL transaction

### Câu 5

Retrieval thành công nhưng documents không relevant. Nếu còn semantic round, route đúng là:

A. Retry cùng HTTP request với query cũ
B. Rewrite query
C. Mở circuit breaker
D. Trả HTTP 503

### Câu 6

OpenSearch connection timeout bị chuyển thành `hits=[]`. Rủi ro chính là:

A. BM25 score tăng
B. Lỗi hạ tầng bị hiểu thành semantic miss
C. PostgreSQL bị rollback
D. Query embedding đổi chiều

### Câu 7

Jina lỗi nhưng BM25 trả được evidence và answer grounded. Outcome đúng là:

A. HTTP 500 + error
B. HTTP 503 + unavailable
C. HTTP 200 + degraded, actual mode BM25
D. HTTP 200 + hybrid success

### Câu 8

OpenSearch trả HTTP 200 và zero hits hợp lệ. Circuit breaker nên:

A. Ghi một dependency failure
B. Mở ngay
C. Không ghi failure; đây là successful zero-result
D. Retry vô hạn

### Câu 9

Search chạy thành công nhưng sau mọi semantic rounds vẫn thiếu evidence. Outcome đúng là:

A. HTTP 200 + insufficient_evidence
B. HTTP 503 + retrieval_unavailable
C. HTTP 500 + tool_error
D. Generate không context

### Câu 10

Kiểm tra terminal route, HTTP status và call budget phù hợp nhất với:

A. LLM-as-a-judge
B. Code evaluator deterministic
C. Human preference only
D. Cosine similarity

## Phần B — Đọc state và tính budget (25 điểm)

### Câu 11 — Graph execution (7 điểm)

Cho execution:

```text
guardrail pass
→ retrieval round 1: success, documents irrelevant
→ rewrite
→ retrieval round 2: success, documents relevant
→ generate
```

Trả lời:

1. Terminal route là gì?
2. `retrieval_rounds` bằng bao nhiêu?
3. `rewrite_count` bằng bao nhiêu?
4. Đây có infrastructure retry không? Vì sao?

### Câu 12 — Retry amplification (6 điểm)

Một request có:

- Tối đa 2 semantic rounds.
- Mỗi round cho Jina tối đa 3 HTTP attempts.
- Proxy retry thêm 2 lần sau lần request đầu tiên.

1. Tối đa bao nhiêu lần toàn agent request được thực thi?
2. Tối đa bao nhiêu Jina HTTP attempts?
3. Nêu một cách ngăn amplification.

### Câu 13 — Merge semantics (6 điểm)

State ban đầu:

```python
messages = [HumanMessage("Q1")]
grading_results = [grade_round_1]
```

Node mới trả:

```python
{
  "messages": [HumanMessage("Q2")],
  "grading_results": [grade_round_2]
}
```

Biết `messages` dùng `add_messages`, còn `grading_results` không có reducer:

1. Hai field cuối cùng có nội dung gì?
2. Nếu cần current grade và history rõ ràng, hãy đề xuất schema tốt hơn.

### Câu 14 — Evaluation result (6 điểm)

Fault runner báo:

```text
pass=3, fail=9, blocked=6
```

1. Vì sao không thể kết luận agent quality bằng `3/18`?
2. `blocked` khác `fail` thế nào?
3. Khi dependency construction được sửa, nhóm check nào nên chạy lại đầu tiên?

## Phần C — Tình huống production (35 điểm)

### Câu 15 — Contradictory state (7 điểm)

Grading node trả `routing_decision="generate_answer"`, nhưng canonical `relevant_documents=[]`.

Bạn sẽ route thế nào? Cần trace điều gì? Vì sao không nên mặc định rewrite hoặc generate?

### Câu 16 — Deadline và Retry-After (7 điểm)

Jina trả `429 Retry-After: 20`, nhưng request chỉ còn 8 giây và cần reserve 5 giây cho generation.

Trình bày quyết định retry/fallback, HTTP/business status nếu BM25:

1. Trả được relevant evidence.
2. Cũng không thể hoạt động.

### Câu 17 — False observability (7 điểm)

Request gửi `top_k=5`, `use_hybrid=false`, model B. Router không truyền các tham số này xuống service; service dùng `top_k=3`, hybrid và model A. Response vẫn ghi `chunks_used=5`, `search_mode=bm25`.

1. Đây là lỗi gì?
2. Ảnh hưởng debugging/evaluation thế nào?
3. Thiết kế contract sửa lỗi này.

### Câu 18 — Health và readiness (7 điểm)

PostgreSQL, OpenSearch và Ollama đều healthy nhưng factory không construct được AgenticRAGService.

1. Health endpoint hiện tại nên vẫn green hay không?
2. Readiness của `/ask-agentic` là gì?
3. Đề xuất một bounded readiness check không gọi generation tốn kém.

### Câu 19 — Tool error routing (7 điểm)

Bạn đổi thành `ToolNode(handle_tool_errors=True)`, nhưng vẫn nối thẳng `tool_retrieve → grade_documents`.

1. Rủi ro gì còn tồn tại?
2. Đề xuất structured tool result.
3. Vẽ route cho success, degraded và error.

## Phần D — Thiết kế và evaluation (20 điểm)

### Câu 20 — Hardened agent graph (12 điểm)

Thiết kế graph production cho các action:

```text
reject, direct_response, retrieve, clarify
```

Câu trả lời phải có:

- State và Context chính.
- Post-tool router.
- Semantic round và tool retry budget riêng.
- Generation reserve/total deadline.
- Terminal outcomes.
- Evidence/citation/source invariant.

### Câu 21 — Regression evaluation plan (8 điểm)

Sau khóa học, bạn sửa toàn bộ P1 issues và muốn chứng minh hệ thống tốt hơn baseline.

Thiết kế evaluation plan gồm:

- Cách dùng sáu-item Langfuse dataset v0.
- Code evaluators cần chạy.
- Baseline và candidate comparison.
- Khi nào thêm manual review hoặc LLM judge.
- Điều kiện cutover và rollback.

## Thang đánh giá

- **90–100:** Nắm chắc Agentic RAG production và evaluation.
- **80–89:** Hiểu tốt; còn một vài khoảng trống về invariant hoặc failure contract.
- **70–79:** Đạt; cần ôn routing/budget/evaluation.
- **60–69:** Hiểu khái niệm nhưng thiết kế production chưa ổn định.
- **Dưới 60:** Cần ôn có hướng dẫn trước khi sang phần tiếp theo.

Điểm đạt: **70/100**, đồng thời không phần nào dưới 50% số điểm của phần đó.

## Mẫu nộp bài

```text
PHẦN A
1. ...
...
10. ...

PHẦN B
11. ...
12. ...
13. ...
14. ...

PHẦN C
15. ...
16. ...
17. ...
18. ...
19. ...

PHẦN D
20. ...
21. ...
```

Sau khi nộp, bài sẽ được chấm theo từng phần và tạo kế hoạch ôn cá nhân hóa.
