# Báo cáo hoàn thành khóa học — Production Agentic RAG

Ngày chốt: 2026-09-09

Học viên: Lasion

Trạng thái: **Hoàn thành khóa học và capstone**

## Phạm vi đã hoàn thành

- Week 1–2: infrastructure, ingestion, idempotency, retry và consistency.
- Week 3–4: OpenSearch mapping, BM25, embeddings, hybrid retrieval, RRF,
  chunking và context diversity.
- Week 5: grounded generation, output validation, citations, streaming,
  cancellation và graceful degradation.
- Week 6: Redis cache semantics, stampede control, fail-open, metrics,
  Langfuse tracing và alerting.
- Week 7: bounded agent loop, typed state, deterministic routing, tool failure
  handling, fault injection, provider abstraction, OpenAI adapter và
  evaluation-driven hardening.
- Production hardening: API perimeter, deployment boundary, recoverable
  PostgreSQL/OpenSearch consistency, controlled migrations, health/readiness
  lifecycle và automated release gate.

## Kết quả học tập

- Bài kiểm tra Week 1–4: **81/100**.
- Bài kiểm tra Week 7: **85/100**.
- Bài phụ đạo degradation/reconciliation/diversity: hoàn thành.
- Học viên đã giải thích đúng các failure semantics quan trọng và có khả năng
  phân biệt business failure, infrastructure failure và observability failure.

## Graduation evidence

Kết quả chạy ngày 2026-09-09:

- `uv lock --check`: pass.
- Ruff trên source, Airflow, tests, migrations, scripts và experiments: pass.
- Unit/API suite: **263 passed**, 18 deprecation warnings.
- Local PostgreSQL/OpenSearch/Redis release contracts: **3/3 passed**.
- Release manifest: pass; 6 fault cases và 7 hosted-answer cases đều approved.
- Deterministic agent regression: **18/18 checks**, 0 fail, 0 blocked.
- Live OpenAI answer contracts: **7/7**, 0 fail.
- Docker API rebuild: pass; `/api/v1/live` healthy.
- Live Agentic RAG probe: HTTP 200, `business_status=success`, hybrid retrieval,
  3 context chunks và grounded quantitative answer.
- Langfuse trace `1185e281a4f058cc557a7015f0afd172`: 22 observations;
  candidate/final diagnostics record 12 candidates and three selected chunks.

GitHub Actions run `34367211091` did not execute these tests because GitHub
reported that the account was locked by a billing issue. Its red jobs are an
external CI setup blocker, not test failures. The equivalent quality, agent and
service gates above were therefore executed locally before merge. Future merges
must fail closed behind branch protection until GitHub Actions billing is restored.

## Những gì chứng nhận này khẳng định

Học viên đã hoàn thành lộ trình và capstone, có thể thiết kế, triển khai, kiểm thử
và phân tích một Production Agentic RAG theo hướng có bounded execution,
grounding, recoverability, observability và release controls.

Chứng nhận này không khẳng định hệ thống đã được phê duyệt để nhận production
traffic ở mọi quy mô. Production launch cần một quyết định triển khai riêng dựa
trên staging, tải dự kiến, SLO và yêu cầu bảo mật của dự án thật.

## Known limitations chuyển sang roadmap sau khóa học

- Readiness probe cho hosted OpenAI model có thể vượt strict timeout 2 giây dù
  E2E generation hoạt động; cần thiết kế lại probe không phụ thuộc latency của
  inference control plane.
- Candidate-only probe mới đạt full gold-context coverage 4/7, dù full answer
  contract đạt 7/7. Query decomposition và coverage-aware selection là bước
  retrieval tiếp theo.
- Citation allowlist và numeric presence đã có; semantic claim-to-citation
  entailment judge vẫn cần mutation calibration.
- Chưa hoàn tất load/backpressure drill, backup restore, canary rollback drill và
  reconciliation alert delivery trong staging thật.
- Serving image còn chứa dependency Docling/PyTorch nên build/export chậm.
- Async OpenSearch client, circuit breaker, cache namespace/coalescing và các
  deprecation warnings vẫn nằm trong backlog P1–P3.
- Basic arXiv integration test phụ thuộc upstream và có thể gặp HTTP 429; đây
  không phải hermetic release signal.

## Quyết định đóng khóa học

Khóa học dừng ở commit/tag course-completion. Các mục trên không kéo ngược trạng
thái học tập về “chưa hoàn thành”; chúng trở thành đầu vào của kế hoạch độc lập
**Production Launch Readiness**. Mọi tuyên bố production-ready sau này phải đáp
ứng Definition of Done trong `docs/production-readiness-audit.md`.
