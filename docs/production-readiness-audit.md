# Production Readiness Audit

Audit date: 2026-09-06  
Repository baseline: `a559143`  
Scope: ingestion, serving, security, deployment, data consistency, observability, and release quality.

## Executive verdict

The repository is a strong development and learning system, but it is **not ready for a public production deployment** yet. The agentic serving path has bounded retries, explicit degraded outcomes, tracing, deterministic citation checks, and regression coverage. The remaining launch blockers are concentrated at the system boundaries: API access control, production-safe deployment, PostgreSQL/OpenSearch consistency, migrations, readiness semantics, and automated release gates.

Cost optimization remains a `P2` improvement. Existing cost alerts are sufficient as a guardrail while correctness, security, and recoverability are completed.

## Verified baseline

- `uv run pytest -q`: **175 passed**, 18 deprecation warnings.
- `uv run ruff check src tests`: passed.
- `uv lock --check`: passed.
- Docker Compose configuration validates.
- Runtime containers: API, PostgreSQL, OpenSearch, and Redis healthy.
- `/api/v1/health`: HTTP 200 with database, OpenSearch, OpenAI, and agent graph reported healthy.
- GitNexus index: 4,037 symbols, 6,890 relationships, and 201 execution flows at `a559143`.

## Existing production strengths

- Provider-neutral LLM interface with an OpenAI adapter, model allowlist, output-token cap, and translated provider errors.
- Agent request deadline, bounded embedding/search attempts, BM25 degradation, and explicit `retrieval_unavailable` outcome.
- Search runs in a worker thread so the synchronous OpenSearch client does not directly block the event loop.
- Canonical relevant-document set, context diversity, citation allowlist, and deterministic numeric-claim checks.
- Langfuse traces, regression datasets, fault injection, feedback capture, and generation-cost alerting.
- Input bounds for query length and `top_k`.

## P0 — launch blockers

### PR-P0-01 — Protect the API perimeter

**Implementation status: Complete (2026-09-06).** API-key authentication, authenticated trace identity,
per-identity and global Redis rate limits, trace-owner feedback authorization, public `/live`, protected
dependency health, correlation IDs, body-free access logs, typed sanitized errors, production configuration
guardrails, and hermetic perimeter tests are implemented. Full regression: **187 passed**.
The rebuilt Docker API is healthy; `/api/v1/live` returned HTTP 200 in under 1 ms with `X-Request-ID`,
and a rejected request returned the sanitized typed HTTP 422 envelope without echoing its input.

**Evidence**

- All routers are registered without authentication or authorization in `src/main.py:137`.
- `/ask-agentic` and `/feedback` have no caller identity or rate limit in `src/routers/agentic_ask.py:8` and `src/routers/agentic_ask.py:91`.
- Middleware is explicitly marked as not integrated in `src/middlewares.py:6`.
- Unexpected exceptions are returned with `str(e)` in `src/routers/agentic_ask.py:87`, and generation errors can also be exposed in `src/services/agents/nodes/generate_answer_node.py:171`.
- Raw queries are written to application logs in `src/services/agents/agentic_rag.py:188`, independent of the Langfuse content policy.

**Risk**

An internet-facing deployment permits unbounded paid-model usage, forged feedback, accidental information disclosure, and weak incident correlation.

**Acceptance criteria**

- Require an API key or trusted identity on every non-liveness endpoint.
- Derive `user_id` from authenticated identity; never use a shared default user for production traces.
- Enforce per-identity and global rate limits; return HTTP 429 with a stable error schema.
- Add request/correlation IDs and structured access logs.
- Return public error codes/messages; retain exception details only in logs/traces.
- Add tests for missing/invalid credentials, rate-limit exhaustion, feedback ownership, and sanitized failures.

### PR-P0-02 — Create a production-safe deployment boundary

**Implementation status: Complete as a deployable template (2026-09-06).** `compose.yml` is explicitly
development-only. `compose.production.yml` publishes only a Caddy TLS gateway; API and optional Airflow
scheduler run non-root with read-only filesystems, dropped capabilities, resource/PID limits, restart and
termination policies. Managed/private PostgreSQL, Redis, OpenSearch and Langfuse connections require
authentication plus verified TLS. Secrets use file mounts and allowlisted entrypoints. Production startup
rejects insecure URLs, placeholder credentials and unapproved content capture. Full regression: **201 passed**;
both Dockerfiles and the production Compose model validate without warnings. Actual deployment still requires
operator-provisioned private dependencies, CA chains, secret files, DNS and an immutable image registry.

**Evidence**

- Compose publishes PostgreSQL, Redis, OpenSearch, Dashboards, Airflow, and observability stores to the host in `compose.yml`.
- OpenSearch security is disabled at `compose.yml:57`.
- Development database credentials are embedded at `compose.yml:28` and `compose.yml:156`.
- The self-hosted Langfuse bootstrap uses a fixed admin identity/password at `compose.yml:294`.
- Airflow creates `admin/admin` at `airflow/entrypoint.sh:18`.
- The API image has no non-root runtime user in `Dockerfile`.
- `Settings` defaults to `debug=True` and `environment=development` at `src/config.py:185`.

**Risk**

The current Compose file is appropriate for local learning only. Reusing it as a production manifest exposes data stores and known credentials.

**Acceptance criteria**

- Keep the current Compose file explicitly development-only and add a production deployment profile/template.
- Expose only the ingress/API; place stateful services on private networks.
- Enable TLS and authentication for PostgreSQL, Redis, OpenSearch, Airflow, and observability services.
- Load secrets from a secret manager or mounted secret files, not defaults in source.
- Fail startup when `ENVIRONMENT=production` is combined with debug mode, placeholder secrets, insecure URLs, disabled auth, or content capture without explicit policy approval.
- Run API and workers as non-root users; add resource requests/limits and restart/termination policy.

### PR-P0-03 — Make ingestion and indexing recoverably consistent

**Implementation status: Complete, including controlled migration (2026-09-07).** PostgreSQL now owns a durable
paper/index state machine with source/index versions, attempts, lease/retry timestamps and sanitized errors.
Ingestion commits or rolls back one paper at a time, preserves last-good parsed content and passes exact paper
IDs to indexing. OpenSearch chunk writes use deterministic paper/version/chunk IDs, while fenced claim tokens
prevent an older worker from acknowledging a newer source version. An hourly Airflow reconciler claims work
with leases, retries with exponential backoff and records exhausted work as dead-letter with a critical alert
hook. The non-atomic `is_active/update_by_query` approach is intentionally excluded; atomic visibility moves
to versioned-index alias cutover in PR-P0-04. The model and mapping changes were applied and validated by
the controlled PostgreSQL/OpenSearch migration drill in PR-P0-04.

**Evidence**

- The Paper model has no `source_version`, `indexed_version`, `index_status`, retry metadata, or last error in `src/models/paper.py`.
- Per-paper repository methods commit internally at `src/repositories/paper.py:15` and `src/repositories/paper.py:79`; the batch catches an exception without rolling the failed session back at `src/services/metadata_fetcher.py:390`.
- A failed reprocessing run writes `pdf_processed=False` into an existing record at `src/services/metadata_fetcher.py:375`, potentially downgrading a previously good paper state.
- The indexing task guesses which rows belong to a run using `created_at` plus a count at `airflow/dags/arxiv_ingestion/indexing.py:60`, rather than passing stable paper IDs.
- Replacement deletes searchable chunks before the replacement is proven valid at `src/services/indexing/hybrid_indexer.py:136` and `src/services/indexing/hybrid_indexer.py:157`.
- Bulk actions have no deterministic `_id` at `src/services/opensearch/client.py:343`, so repeated indexing can create duplicate chunks.
- `index_paper` converts exceptions into statistics at `src/services/indexing/hybrid_indexer.py:114`; the Airflow task can finish successfully despite per-paper indexing failures.

**Risk**

Users can receive stale, duplicated, partially indexed, or missing evidence while orchestration reports success. A failed replacement can remove the last good index version.

**Acceptance criteria**

- Add a durable paper/index state machine with `source_version`, `indexed_version`, status, attempt count, timestamps, and sanitized last error.
- Use one isolated transaction per paper, including rollback before continuing after a database error.
- Preserve the last good parsed/indexed version when a refresh fails.
- Pass exact paper IDs or durable outbox events between ingestion stages.
- Use deterministic chunk IDs containing paper/version/chunk identity.
- Index a complete new version before atomically activating it; never delete the last good version first.
- Reconciliation periodically detects `source_version > indexed_version`, requeues work, and eventually sends exhausted work to a DLQ plus alert.
- Airflow must fail or explicitly report partial failure when any required paper remains inconsistent.
- Add fault tests for duplicate delivery, partial bulk failure, crash between PostgreSQL and OpenSearch, and safe replay.

### PR-P0-04 — Add controlled database and index migrations

**Implementation status: Code and live migration validation complete (2026-09-07).** Alembic now owns
the PostgreSQL schema and application startup performs connectivity checks only. Development and production
Compose manifests expose explicit one-off migration jobs. OpenSearch uses versioned physical indices plus
separate read/write aliases; prepare, validated atomic cutover, status and rollback are available through the
migration CLI. Legacy documents can be copied into the first generation without deleting the legacy index.
The development drill migrated PostgreSQL from legacy revision `5f2621c13b39` through `20260906_0001` to
head `20260907_0004`, copied
81/81 chunks into `v1`, cut over both aliases, rolled back to retained `v0`, then restored `v1` successfully.

**Evidence**

- Prior to this PR, PostgreSQL startup used `Base.metadata.create_all()` and there was no checked-in Alembic revision.
- Prior to this PR, OpenSearch reads and writes used the same concrete name without an atomic cutover boundary.

**Risk**

Schema changes cannot be reviewed, rolled forward/back safely, or reproduced consistently across environments. A mapping change can require destructive reindexing during API startup.

**Acceptance criteria**

- Initialize Alembic and check immutable revisions into source control.
- Run migrations as a deployment job before application rollout; application startup must not mutate schemas.
- Version OpenSearch indices and cut over through an alias after validation.
- Document and test rollback plus PostgreSQL/OpenSearch backup and restore procedures.

### PR-P0-05 — Separate liveness, readiness, and dependency health

**Status: implemented and runtime-verified.**

**Previous evidence**

- One `/health` endpoint performs database, OpenSearch, and hosted LLM checks at `src/routers/ping.py:10`.
- The endpoint always returns a normal response model, so a degraded payload still produces HTTP 200.
- Docker considers any HTTP response from this endpoint healthy at `compose.yml:15`.
- Redis construction calls `PING` and raises at startup at `src/services/cache/factory.py:27`, so an optional cache is not actually fail-open.
- API startup also performs index setup at `src/main.py:47`.
- Shutdown closes Langfuse and PostgreSQL but not the embeddings HTTP client, Redis client, OpenSearch transport, or LLM client at `src/main.py:120`.

**Risk**

Orchestrators cannot distinguish “process alive” from “ready to serve.” Optional dependency failure may prevent startup, while a degraded required dependency may still appear healthy.

**Acceptance criteria**

- `/live` checks only the process/event loop and returns quickly.
- `/ready` validates only required serving dependencies with strict timeouts and returns HTTP 503 when unavailable.
- Expose detailed dependency status separately and avoid calling a hosted model API on every liveness probe.
- Redis remains optional and fail-open with a short connection timeout.
- Move schema/index setup out of API startup.
- Close every network client during lifespan shutdown; verify with lifecycle tests.

**Implemented evidence**

- Public `/live` checks only the event loop. Protected `/ready` probes required serving dependencies
  concurrently with a configurable two-second ceiling and returns HTTP 503 when any required probe fails.
- Protected `/health` exposes component state without turning optional degradation into an orchestrator restart.
- Redis construction is lazy and uses one-second connect/read timeouts. Cache failures are fail-open, while Redis
  becomes a required readiness dependency when Redis-backed API rate limiting is enabled.
- API startup no longer performs PostgreSQL connectivity or OpenSearch schema/index mutations; migration remains
  an explicit release job.
- Lifespan cleanup closes embeddings, LLM, Redis, OpenSearch, Langfuse, Telegram and PostgreSQL clients independently.
- Unit coverage verifies readiness status, bounded timeout, Redis dual semantics and client lifecycle cleanup.
- Docker smoke: `/live` returned 200, `/ready` returned 200 with all required dependencies healthy, and detailed
  `/health` returned 200. With Redis intentionally stopped in cache-only development mode, `/ready` remained 200
  while `/health` became `degraded`; Redis was then restored healthy. A restart drill logged successful shutdown of
  Telegram, embeddings, OpenAI, Redis, OpenSearch, Langfuse and PostgreSQL clients before the new process started.

### PR-P0-06 — Establish an automated release gate

**Implementation status: repository gate complete; external activation pending.** The checked-in release workflow
runs lock verification, Ruff, unit/API contracts, deterministic full-graph/API agent regressions, fresh PostgreSQL migrations,
OpenSearch/Redis integration contracts and an API image build. Main-branch builds publish a commit-addressed GHCR
image with SBOM, provenance attestation and release metadata. A separate manually approved Langfuse workflow is
prepared for staging answer evaluation. It intentionally refuses to run while the seven answer expectations remain
`needs_human_review`. GitHub authentication, branch-protection required checks and environment secrets/reviewers must
still be configured on the remote repository before this is an enforceable deployment boundary.

**Evidence before implementation**

- The repository has no CI workflow.
- Existing `tests/integration/test_services.py` checks basic types/connectivity but does not run the API, ingestion replay, or failure recovery end to end.
- The seven answer cases are still provisional and require human review.

**Risk**

A green local test run cannot prevent an unreviewed commit or dependency/configuration change from reaching deployment.

**Acceptance criteria**

- CI runs lock verification, Ruff, unit/API tests, migration checks, and container build on every change.
- A service-backed test job runs PostgreSQL/OpenSearch/Redis integration contracts.
- Agent regression and fault suites are deployment gates with immutable expected outcomes.
- Human-review and approve the initial answer dataset; record dataset, prompt, retrieval, model, and schema versions.
- Produce a versioned image and deployment artifact; support canary plus one-command rollback.

**Implemented evidence**

- `.github/workflows/release-gate.yml` runs on pull requests, main pushes and manual dispatch. Every third-party action
  is pinned to an immutable commit SHA.
- The six approved fault cases are checksum-pinned and require 18/18 route, budget and response checks. Each case
  executes the compiled production graph and ASGI route with deterministic external-service adapters; the runner exits
  non-zero on either `fail` or `blocked`.
- `evals/release_manifest.json` records dataset checksums and model, prompt, retrieval and response-schema versions.
- The integration job provisions digest-pinned PostgreSQL 16, OpenSearch 2.19 and Redis 7, migrates a fresh database,
  rejects Alembic drift, bootstraps versioned search aliases and runs service round-trip contracts.
- Main pushes publish `ghcr.io/<repository>:sha-<commit>` with SBOM/provenance and upload digest metadata.
- `deploy/release-image.sh` accepts digest-pinned images only and provides canary, promote and rollback commands with
  protected readiness verification plus automatic restoration of the prior digest on a failed replacement.
- `.github/workflows/hosted-answer-gate.yml` follows the Langfuse experiment-action contract and requires a protected
  `staging-evaluation` environment plus 100% answer-contract pass rate. It deploys the supplied candidate digest and
  verifies the served commit before evaluation; dataset/application metadata comes from the validated manifest.

## P1 — required before broader production use

### PR-P1-01 — Backpressure and dependency protection

- Add global/per-provider concurrency limits, queue bounds, circuit breakers, and overload responses.
- Define a single retry owner for each failure scope and export attempt/fallback counters.
- Load-test simultaneous cache misses and paid-model calls; verify deadlines and cancellation under disconnects.

### PR-P1-02 — Operational telemetry and SLOs

- Integrate request middleware; emit request count, latency, error, degraded-rate, retry, fallback, retrieval quality, and reconciliation-lag metrics.
- Use bounded-cardinality labels only.
- Define availability/latency/freshness SLOs, alert windows, ownership, and runbooks.
- Retain Langfuse as AI tracing; do not treat trace delivery as the only operational signal.

### PR-P1-03 — Strengthen answer-quality contracts

- Human-label the seven current answer cases and expand by intent, language, paper, no-match, and adversarial prompt-injection cases.
- Add claim-to-citation attribution/entailment checks; current validation proves citation membership and numeric presence, not that each cited source supports each claim.
- Require no regression in deterministic contracts and manual review of high-risk/borderline cases.

### PR-P1-04 — Complete cache correctness

- The current exact cache key at `src/services/cache/client.py:22` has no corpus, prompt, retrieval, or response-schema version.
- Redis calls are synchronous inside async methods and use 30-second defaults at `src/config.py:164`.
- Implement versioned namespaces, short fail-open timeouts, distributed request coalescing, and cache metrics before relying on the cache for production traffic.

### PR-P1-05 — Clarify product/API contracts

- Version and document the public error envelope and business statuses.
- Decide whether `reasoning_steps` is a stable public field or internal diagnostic metadata.
- Add pagination/limits and ownership rules for any future ingestion, administration, or feedback endpoints.

## P2 — improvements after launch blockers

### PR-P2-01 — Cost and context optimization

Keep the current Langfuse alert. Add token-aware packing, model routing, and context compression only after production gates are stable.

### PR-P2-02 — Split serving and ingestion images

The API image currently carries Docling/PyTorch dependencies required by parsing. Separate serving and ingestion dependency groups/images to reduce build time, attack surface, and memory footprint.

### PR-P2-03 — Remove deprecations and tighten static typing

Resolve the 18 current Pydantic/SQLAlchemy/LangGraph warnings and replace `mypy.ignore_errors=true` with an incremental strictness plan.

## Recommended execution order

1. **Production perimeter:** PR-P0-01 and PR-P0-02 complete.
2. **Data correctness:** PR-P0-03.
3. **Controlled lifecycle:** PR-P0-04 and PR-P0-05.
4. **Release safety:** PR-P0-06.
5. **Operational hardening:** P1 backpressure, telemetry, quality, and cache work.
6. **Efficiency:** P2 cost and image optimization.

## First implementation slice

Start with a small, reviewable **production perimeter** change:

1. Add production settings for API keys, trusted proxy behavior, request IDs, and rate limits.
2. Fail configuration validation when production uses unsafe defaults.
3. Protect `/ask`, `/ask/stream`, `/ask-agentic`, `/hybrid-search`, and `/feedback`; keep only `/live` public.
4. Replace exception strings in client responses with a typed public error envelope.
5. Add hermetic API tests for authentication, authorization, rate limiting, request IDs, and sanitized errors.

This slice reduces immediate abuse and data-leak risk without changing retrieval quality or increasing model cost.

## Production-ready definition of done

The system can be considered ready for a real project when all P0 items pass in a staging environment, the approved regression suite has no P0 regressions, a load test demonstrates bounded behavior, reconciliation heals an injected PostgreSQL/OpenSearch inconsistency, backup restore is demonstrated, alerts reach an owner, and a canary can be rolled back without data loss.
