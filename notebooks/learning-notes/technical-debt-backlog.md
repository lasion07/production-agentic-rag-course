# Technical debt backlog — Production Agentic RAG

Quay lại: [Mục lục sổ học tập](README.md)

Mục đích: ghi lại lỗi và khoảng trống phát hiện trong khi học; chỉ triển khai sau khi hoàn thành khóa học, trừ khi lỗi chặn bài thực hành.

## Quy ước

- `P1`: ảnh hưởng correctness/availability production.
- `P2`: ảnh hưởng reliability, observability hoặc hiệu năng.
- Trạng thái hiện tại: `Deferred until course completion`.

## Week 7.1–7.2

### TD-W7-01 — Tài liệu và graph không khớp về retrieval decision — P2

- Source: `src/routers/agentic_ask.py`, `src/services/agents/agentic_rag.py`.
- Hiện tại: tài liệu nói agent quyết định có cần retrieval; graph chỉ guardrail rồi retrieve, chưa có `direct_response`.
- Hướng sửa: router action schema `direct_response/retrieve/clarify/reject` và route tests.

### TD-W7-02 — Unsafe grading route và retry thừa — P1

- Source: `src/services/agents/agentic_rag.py`.
- Hiện tại: missing decision mặc định `generate_answer`; lần retrieval cuối vẫn có thể rewrite trước khi phát hiện hết attempts.
- Hướng sửa: fail-safe router kiểm tra evidence và attempts; test missing/contradictory state.

### TD-W7-03 — Evidence và API sources có thể lệch nhau — P1

- Source: agent ToolMessage/grading flow và `_extract_sources()`.
- Hiện tại: generation có thể đọc tool context trong khi `relevant_sources` không được cập nhật, làm API trả sources rỗng.
- Hướng sửa: một canonical relevant-document set sinh context, citation allowlist và API sources.

### TD-W7-04 — API báo requested K thay vì actual chunks — P2

- Source: `src/routers/agentic_ask.py`.
- Hiện tại: `chunks_used=request.top_k` dù số chunks thực tế có thể khác.
- Hướng sửa: trả actual evidence count từ final state.

## Week 7.3

### TD-W7-05 — OpenSearch exception bị che thành zero hits — P1

- Source: `src/services/opensearch/client.py::search_unified`.
- Hiện tại: catch-all trả empty result, khiến graph hiểu lỗi hạ tầng là semantic miss.
- Hướng sửa: typed error/structured outcome; test zero-result khác timeout.

### TD-W7-06 — Embedding failure làm graph abort — P1

- Source: `src/services/embeddings/jina_client.py`, `src/services/agents/tools.py`.
- Hiện tại: Jina HTTP errors propagate qua ToolNode và endpoint có thể trả 500.
- Hướng sửa: bounded client retry, typed errors và BM25 fallback.

### TD-W7-07 — Thiếu post-tool failure router — P1

- Source: `src/services/agents/agentic_rag.py`.
- Hiện tại: `tool_retrieve` luôn đi `grade_documents`; chưa có success/degraded/error contract.
- Hướng sửa: structured `RetrievalResult` và deterministic `route_after_tool`.

### TD-W7-08 — Counter trộn semantic round và physical attempt — P2

- Source: `src/services/agents/nodes/retrieve_node.py`.
- Hiện tại: counter tăng khi tạo tool call, không cho biết dependency đã chạy thành công chưa.
- Hướng sửa: tách retrieval rounds, embedding attempts, search attempts, failures và fallbacks.

### TD-W7-09 — Sync OpenSearch trong async tool — P2

- Source: `src/services/agents/tools.py`, `src/services/opensearch/client.py`.
- Hiện tại: synchronous search có thể block event loop.
- Hướng sửa: async client hoặc bounded worker thread; kiểm thử timeout/cancellation.

### TD-W7-10 — Thiếu shared deadline và retry budget — P1

- Source: agent runtime context và dependency clients.
- Hiện tại: chưa reserve finish/generation time và chưa ngăn retry amplification.
- Hướng sửa: request deadline, per-attempt timeout, shared call budget và retry metrics.

### TD-W7-11 — Failure tests chưa đủ — P2

- Source: `tests/unit/services/agents/test_tools.py`, `test_nodes.py`, `test_agentic_rag.py`.
- Hiện tại: chủ yếu test success/empty result và graph exception tổng quát.
- Hướng sửa: fault injection cho timeout, 401, 429, 503, fallback, deadline, max-call invariant và circuit breaker.

## Trạng thái

Tất cả mục trên: **Deferred until course completion**.
