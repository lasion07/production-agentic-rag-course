# Technical debt backlog — Production Agentic RAG

Quay lại: [Mục lục sổ học tập](README.md)

Mục đích: ghi lại lỗi và khoảng trống phát hiện trong khi học; chỉ triển khai sau khi hoàn thành khóa học, trừ khi lỗi chặn bài thực hành.

Production readiness audit: [docs/production-readiness-audit.md](../../docs/production-readiness-audit.md)

## Quy ước

- `P0`: launch blocker về security, correctness, recoverability hoặc release safety.
- `P1`: cần hoàn thành trước khi mở rộng production traffic.
- `P2`: cải tiến hiệu năng, chi phí hoặc maintainability sau launch blockers.
- Trạng thái được cập nhật theo từng mục sau đợt Week 7.5 hardening.

## Week 7.1–7.2

### TD-W7-01 — Tài liệu và graph không khớp về retrieval decision — P2

- Source: `src/routers/agentic_ask.py`, `src/services/agents/agentic_rag.py`.
- Hiện tại: tài liệu nói agent quyết định có cần retrieval; graph chỉ guardrail rồi retrieve, chưa có `direct_response`.
- Hướng sửa: router action schema `direct_response/retrieve/clarify/reject` và route tests.

### TD-W7-02 — Unsafe grading route và retry thừa — P1

- Source: `src/services/agents/agentic_rag.py`.
- Hiện tại: missing decision mặc định `generate_answer`; lần retrieval cuối vẫn có thể rewrite trước khi phát hiện hết attempts.
- Hướng sửa: fail-safe router kiểm tra evidence và attempts; test missing/contradictory state.
- Trạng thái: **Resolved** — deterministic router bắt buộc evidence và chặn rewrite sau round cuối.

### TD-W7-03 — Evidence và API sources có thể lệch nhau — P1

- Source: agent ToolMessage/grading flow và `_extract_sources()`.
- Hiện tại: generation có thể đọc tool context trong khi `relevant_sources` không được cập nhật, làm API trả sources rỗng.
- Hướng sửa: một canonical relevant-document set sinh context, citation allowlist và API sources.
- Trạng thái: **Resolved for deterministic v0** — `relevant_documents` sinh generation context, source list và actual chunk count; citation allowlist và numeric-claim validation đã chạy sau generation. Semantic claim-to-citation attribution được theo dõi tại `PR-P1-03` trong production readiness audit.

### TD-W7-04 — API báo requested K thay vì actual chunks — P2

- Source: `src/routers/agentic_ask.py`.
- Hiện tại: `chunks_used=request.top_k` dù số chunks thực tế có thể khác.
- Hướng sửa: trả actual evidence count từ final state.
- Trạng thái: **Resolved**.

## Week 7.3

### TD-W7-05 — OpenSearch exception bị che thành zero hits — P1

- Source: `src/services/opensearch/client.py::search_unified`.
- Hiện tại: catch-all trả empty result, khiến graph hiểu lỗi hạ tầng là semantic miss.
- Hướng sửa: typed error/structured outcome; test zero-result khác timeout.
- Trạng thái: **Resolved** — `search_unified` re-raise; structured executor phân biệt empty success và dependency error.

### TD-W7-06 — Embedding failure làm graph abort — P1

- Source: `src/services/embeddings/jina_client.py`, `src/services/agents/tools.py`.
- Hiện tại: Jina HTTP errors propagate qua ToolNode và endpoint có thể trả 500.
- Hướng sửa: bounded client retry, typed errors và BM25 fallback.
- Trạng thái: **Resolved** — tối đa hai embedding attempts, phân loại retryable và BM25 fallback.

### TD-W7-07 — Thiếu post-tool failure router — P1

- Source: `src/services/agents/agentic_rag.py`.
- Hiện tại: `tool_retrieve` luôn đi `grade_documents`; chưa có success/degraded/error contract.
- Hướng sửa: structured `RetrievalResult` và deterministic `route_after_tool`.
- Trạng thái: **Resolved** — error không còn đi vào grading.

### TD-W7-08 — Counter trộn semantic round và physical attempt — P2

- Source: `src/services/agents/nodes/retrieve_node.py`.
- Hiện tại: counter tăng khi tạo tool call, không cho biết dependency đã chạy thành công chưa.
- Hướng sửa: tách retrieval rounds, embedding attempts, search attempts, failures và fallbacks.
- Trạng thái: **Resolved**.

### TD-W7-09 — Sync OpenSearch trong async tool — P2

- Source: `src/services/agents/tools.py`, `src/services/opensearch/client.py`.
- Hiện tại: synchronous search có thể block event loop.
- Hướng sửa: async client hoặc bounded worker thread; kiểm thử timeout/cancellation.
- Trạng thái: **Mitigated** — sync search được đưa sang worker thread và có await timeout; chuyển hẳn sang async client vẫn còn mở.

### TD-W7-10 — Thiếu shared deadline và retry budget — P1

- Source: agent runtime context và dependency clients.
- Hiện tại: chưa reserve finish/generation time và chưa ngăn retry amplification.
- Hướng sửa: request deadline, per-attempt timeout, shared call budget và retry metrics.
- Trạng thái: **Resolved for bounded execution** — có outer 120s deadline, per-attempt timeout, generation reserve và HTTP 504 contract. Tối ưu phase budgets/latency vẫn còn mở.

### TD-W7-11 — Failure tests chưa đủ — P2

- Source: `tests/unit/services/agents/test_tools.py`, `test_nodes.py`, `test_agentic_rag.py`.
- Hiện tại: chủ yếu test success/empty result và graph exception tổng quát.
- Hướng sửa: fault injection cho timeout, 401, 429, 503, fallback, deadline, max-call invariant và circuit breaker.
- Trạng thái: **Partially resolved** — đã có timeout, `429 Retry-After`, zero-hit, fallback và max-call tests; circuit breaker chưa triển khai.

## Week 7.4

### TD-W7-12 — Agentic dependency construction bị lỗi — P1

- Source: `src/dependencies.py`, `src/services/agents/factory.py`.
- Hiện tại: dependency truyền `model`, factory không nhận tham số này; mọi `/ask-agentic` request trả 500 trước guardrail/trace.
- Hướng sửa: thống nhất factory contract và thêm endpoint readiness smoke test.
- Trạng thái: **Resolved** — factory nhận model và service construct được trong regression/runtime.

### TD-W7-13 — Request parameters bị bỏ qua và response báo sai execution — P1

- Source: `src/routers/agentic_ask.py`.
- Hiện tại: `model/top_k/use_hybrid/categories` không được truyền đầy đủ; response suy ra chunks/mode từ request thay vì actual execution.
- Hướng sửa: typed execution config, trả actual mode/chunk count; API tests assert forwarding.
- Trạng thái: **Resolved** — request config truyền xuyên suốt; response lấy actual execution.

### TD-W7-14 — Agentic response schema làm mất field — P2

- Source: `src/schemas/api/ask.py`, `src/routers/agentic_ask.py`.
- Hiện tại: service có `rewritten_query` nhưng `AgenticAskResponse` không khai báo nên FastAPI loại khỏi response.
- Hướng sửa: thống nhất service/API schema và contract tests cho mọi response field.
- Trạng thái: **Resolved**.

### TD-W7-15 — Shared agent test fixtures bị thiếu — P2

- Source: `tests/conftest.py`, agent unit tests.
- Hiện tại: 22 setup errors do fixtures được tham chiếu nhưng không định nghĩa.
- Hướng sửa: bổ sung typed shared fixtures và tách setup health khỏi behavior assertions.
- Trạng thái: **Resolved** — agent/API tests chạy hermetic.

### TD-W7-16 — Health chưa kiểm tra agentic endpoint readiness — P2

- Source: health router/startup smoke tests.
- Hiện tại: backend services healthy nhưng dependency construction của agentic endpoint lỗi.
- Hướng sửa: readiness check construct service hoặc chạy bounded internal smoke path.
- Trạng thái: **Resolved** — service được construct một lần lúc startup; health báo degraded và endpoint trả `503/agentic_unavailable` nếu graph không sẵn sàng.

### TD-W7-17 — Ollama production client thiếu LangChain adapter — P1

- Source: `src/services/ollama/client.py`, toàn bộ agent LLM nodes.
- Hiện tại khi phát hiện: mocks có `get_langchain_model()` nhưng production client không có, làm guardrail fallback và reject nhầm query hợp lệ.
- Hướng sửa: adapter `ChatOllama` dùng chung host/timeout với client và contract test.
- Trạng thái: **Resolved**.

### TD-W7-18 — Hosted LLM production controls chưa đầy đủ — P2

- Source: LLM provider factory, OpenAI adapter và deployment configuration.
- Đã có: provider-neutral contract, Responses API, streaming, structured output, token usage, provider-aware health và model-aware cache identity.
- Đã kiểm chứng: full E2E trên ba public arXiv papers và Langfuse trace audit; privacy masking, trace ID, business metadata và generation cost không bị đếm đôi.
- Đã có: model snapshot allowlist, hard cap output tokens, Metrics API checker và Langfuse native cost alert có Slack automation.
- Trạng thái: **Resolved for production controls v0** — cost/context optimization tiếp tục ở mức `P2`, không phải launch blocker.

### TD-W7-20 — Câu trả lời bỏ sót quantitative claim — P2

- Source: answer-generation prompt và E2E query hỏi range.
- Hiện tượng: câu trả lời mô tả đúng phương pháp nhưng bỏ sót range số liệu dù user hỏi trực tiếp.
- Hướng sửa: prompt rule tổng quát cho số liệu/đơn vị, candidate retrieval sâu hơn, rerank/context selection và một live answer-contract regression case.
- Bằng chứng: hai live runs đều lấy đúng paper nhưng thiếu `56.4–68.2`; Langfuse trace `230f22f8df72e3ec0d0f2c79ef5bb73a` xác nhận hai số không có trong generation input, nên model đã từ chối bịa đúng contract.
- Trạng thái: **Resolved for v0** — lấy 12 candidates, query-aware rerank và diversity selection xuống 3 chunks; live regression pass với đúng claim/source. Cần mở rộng labeled dataset để hiệu chỉnh trọng số trước production cutover.

### TD-W7-19 — API image vẫn nặng dù đã bỏ local inference — P3

- Source: API image chứa Docling/PyTorch cho parsing.
- Ảnh hưởng: build/export chậm và footprint lớn; không làm API tiêu tốn RAM cho Ollama inference.
- Hướng sửa: tách ingestion/parser worker khỏi serving image.
- Trạng thái: **Backlog**.

## Trạng thái

- Đã giải quyết: TD-W7-02, 03, 04, 05, 06, 07, 08, 10, 12, 13, 14, 15, 17, 18.
- Đã giảm rủi ro nhưng còn việc: TD-W7-09, 11.
- Chưa triển khai: TD-W7-01.
- Cần mở rộng evaluation coverage: TD-W7-20.
- Launch blockers tổng thể: `PR-P0-01` đến `PR-P0-04` đã hoàn thành; tiếp theo là PR-P0-05 và PR-P0-06.
