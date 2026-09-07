# Production Agentic RAG — Sổ ghi chú học tập

Tài liệu này tổng hợp kiến thức sau mỗi bài học theo hướng ngắn gọn, dễ ôn tập và gắn với tư duy production.

## Tiến độ

- **Bằng chứng Week 3:** index lab 6 documents, OR/AND/filter/fuzzy/highlight/pagination hoạt động, QueryBuilder 8/8 tests
- **Đã hoàn thành:** Week 1 — Infrastructure; Week 2 — Ingestion; Week 3 — OpenSearch/BM25; Week 4 — Chunking, embeddings và hybrid retrieval; Week 5 — Generation và complete RAG serving; Week 6 — Caching và observability
- **Bằng chứng Week 4:** 3 papers, 81 real embeddings, 0 indexing errors, FastAPI hybrid HTTP 200, 6/6 queries rank relevant paper #1
- **Bằng chứng Week 5:** RAG stream hoàn tất, TTFT 3.275s, total latency 49.772s, 128 token events; đã phân tích SSE buffering, truncation và citation grounding
- **Đã hoàn thành:** Week 7 — Agentic RAG; bài kiểm tra tổng kết đạt **85/100**
- **Đã hoàn thành trong Week 5:** Bài 5.1 — Context; Bài 5.2 — Generation validation; Bài 5.3 — Streaming; Bài 5.4 — Complete RAG practical
- **Đã hoàn thành trong Week 6:** Bài 6.1 — Cache semantics; Bài 6.2 — Stampede/fail-open/metrics; Bài 6.3 — Tracing/latency/alerts; Bài 6.4 — Langfuse runtime hardening
- **Bằng chứng Week 6.2:** 100 requests tạo 100 generations khi không lock, 4 với local locks và 1 với Redis distributed lock; fail-open trả đủ 10/10 responses
- **Bằng chứng Week 6.3:** dựng trace tree 50s với generation chiếm 96%; đánh giá đúng critical RAG error, warning Redis degradation và trace delivery gap
- **Bằng chứng Week 6.4:** Langfuse Cloud nhận trace RAG thật gồm 6 observations; generation 1.620 tokens; privacy audit pass; API container healthy
- **Đã hoàn thành trong Week 7:** Bài 7.1 — Từ fixed pipeline đến bounded agent loop; Bài 7.2 — Agent state, nodes, conditional edges và routing; Bài 7.3 — Tool execution, retries và agent failure handling; Bài 7.4 — Agentic RAG practical, fault injection và evaluation
- **Bằng chứng Week 7.4:** 6-case regression dataset đã upload Langfuse; local fault injection đạt pass=3, fail=9, blocked=6 và tái hiện đúng error masking/fallback gaps
- **Bằng chứng Week 7.6:** OpenAI full E2E HTTP 200/10,31s; Langfuse có 22 observations, 4.941 tokens, ~$0,00537; raw public-paper content capture đã được phê duyệt và kiểm chứng ở trace riêng
- **Technical-debt verification:** 6 fault cases đạt 18/18; quantitative answer case đã chuyển xanh sau candidate reranking/context selection
- **Bằng chứng Week 7.7:** 12 candidates → 3 final chunks; quantitative claim `56.4–68.2%` có đúng source; full suite 168 pass
- **Production hardening:** PR-P0-01 đến PR-P0-04 đã hoàn thành; migration drill PostgreSQL pass và OpenSearch cutover/rollback giữ đủ 81/81 chunks
- **Technical debt:** Các lỗi source được hoãn có chủ đích đến sau khóa học và theo dõi trong backlog riêng
- **Cần ôn lại:** ingestion ordering, serving dependencies và BM25 fallback

## Mục lục

### Bài kiểm tra

1. [Bài kiểm tra thường xuyên số 1 — Tổng hợp Week 1–4](assessment-01-weeks1-4.md)
2. [Kết quả bài kiểm tra số 1 — 81/100](assessment-01-weeks1-4-result.md)
3. [Bài phụ đạo 1 — Degradation, reconciliation và context diversity](remedial-01-degradation-reconciliation-diversity.md)
4. [Technical debt backlog — Các lỗi source cần cải thiện sau khóa học](technical-debt-backlog.md)
5. [Bài kiểm tra thường xuyên số 2 — Week 7 Agentic RAG](assessment-02-week7-agentic-rag.md)
6. [Kết quả bài kiểm tra số 2 — Week 7 Agentic RAG — 85/100](assessment-02-week7-agentic-rag-result.md)

### Phần 1 — Nền tảng kiến trúc

1. [Tổng kết Week 1 — Hạ tầng và hai luồng hệ thống](week1-infrastructure-summary.md)
2. [Đồng bộ PostgreSQL và OpenSearch](01-postgresql-opensearch-consistency.md)

### Phần 2 — Data ingestion

1. [Week 2.1 — Trách nhiệm thành phần và graceful degradation](week2-01-ingestion-responsibilities.md)
2. [Week 2.2 — Rate limit, retry và failure scope](week2-02-rate-limit-and-retry.md)
3. [Week 2.3 — PDF validation, concurrency và resource control](week2-03-pdf-resource-control.md)
4. [Week 2.4 — Upsert, transaction và idempotency](week2-04-upsert-transactions.md)
5. [Tổng kết Week 2 — Production ingestion pipeline](week2-summary.md)

### Phần 3 — Keyword retrieval

1. [Week 3.1 — Mapping, analyzer và inverted index](week3-01-mapping-analyzers-inverted-index.md)
2. [Week 3.2 — BM25 scoring](week3-02-bm25-scoring.md)
3. [Week 3.3 — Query DSL, boosting và filtering](week3-03-query-dsl.md)
4. [Week 3.4 — Retrieval evaluation và practical validation](week3-04-retrieval-evaluation.md)

### Phần 4 — Semantic và hybrid retrieval

1. [Week 4.1 — Chunking strategy và overlap](week4-01-chunking-overlap.md)
2. [Week 4.2 — Embeddings và vector similarity](week4-02-embeddings-vector-similarity.md)
3. [Week 4.3 — HNSW, k-NN và RRF](week4-03-hnsw-knn-rrf.md)
4. [Week 4.4 — Thực hành và đánh giá hybrid retrieval](week4-04-hybrid-practical-evaluation.md)
5. [Tổng kết Week 4 — Chunking, embeddings và hybrid retrieval](week4-summary.md)

### Phần 5 — Generation và complete RAG serving

1. [Week 5.1 — Context construction và grounded prompt](week5-01-context-grounded-prompt.md)
2. [Week 5.2 — Generation controls và output validation](week5-02-generation-validation.md)
3. [Week 5.3 — Streaming, latency và cancellation](week5-03-streaming-latency-cancellation.md)
4. [Week 5.4 — Complete RAG practical và đánh giá streaming](week5-04-complete-rag-practical.md)
5. [Tổng kết Week 5 — Generation và complete RAG serving](week5-summary.md)

### Phần 6 — Caching và observability

1. [Week 6.1 — Redis cache semantics, cache key và invalidation](week6-01-cache-semantics-key-invalidation.md)
2. [Week 6.2 — Cache stampede, Redis fail-open và observability metrics](week6-02-stampede-fail-open-observability.md)
3. [Week 6.3 — Langfuse tracing, latency breakdown và production alerts](week6-03-langfuse-latency-alerts.md)
4. [Week 6.4 — Langfuse runtime hardening và trace thật](week6-04-langfuse-runtime-hardening.md)

### Phần 7 — Agentic RAG

1. [Week 7.1 — Từ fixed RAG pipeline đến agent loop](week7-01-fixed-pipeline-to-agent-loop.md)
2. [Week 7.2 — Agent state, nodes, conditional edges và routing](week7-02-state-nodes-conditional-routing.md)
3. [Week 7.3 — Tool execution, retries và agent failure handling](week7-03-tool-execution-retries-failure-handling.md)
4. [Week 7.4 — Agentic RAG practical, fault injection và evaluation](week7-04-agentic-practical-fault-evaluation.md)
5. [Tổng kết Week 7 — Production Agentic RAG](week7-summary.md)
6. [Week 7.5 — Evaluation-driven hardening với sáu regression cases](week7-05-evaluation-driven-hardening.md)
7. [Week 7.6 — LLM provider abstraction và OpenAI adapter](week7-06-llm-provider-abstraction-openai.md)
8. [Week 7.7 — Candidate reranking và context selection](week7-07-candidate-reranking-context-selection.md)

### Production hardening

1. [Production 02 — Deployment boundary](production-02-deployment-boundary.md)
2. [Production 03 — Consistency và reconciliation](production-03-consistency-reconciliation.md)
3. [Production 04 — Alembic và OpenSearch alias cutover](production-04-controlled-migrations.md)
4. [Production 05 — Liveness, readiness và dependency health](production-05-health-readiness-lifecycle.md)

## Cách sử dụng ghi chú

Sau mỗi bài học:

1. Đọc phần **Tóm tắt một phút**.
2. Tự trả lời **Câu hỏi ôn tập** mà chưa xem đáp án.
3. Làm **Bài tập thực hành đề xuất**.
4. Ghi lại điểm chưa rõ để kiểm tra trong notebook hoặc mã nguồn.

## Mẫu cho các bài tiếp theo

Mỗi bài sẽ gồm:

- Mục tiêu học tập
- Tóm tắt một phút
- Kiến thức cốt lõi
- Luồng xử lý
- Lỗi thường gặp
- Câu hỏi ôn tập và đáp án gợi ý
- Bài tập thực hành đề xuất
- Checklist tự đánh giá
