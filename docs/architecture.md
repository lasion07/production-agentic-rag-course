# Architecture Document

**Project:** arXiv Paper Curator (Mother of AI — Phase 1 RAG)  
**Package:** `moai-zero-to-rag` (`pyproject.toml`)  
**Source of truth:** `src/`, `compose.yml`, `airflow/dags/`, `.env.example`

This document describes the **implemented** architecture of the Agentic RAG system: infrastructure, application layers, API and agent flows, data pipelines, configuration, and dependencies.

---

## 1. System overview

The system is a production-style RAG stack that:

1. **Ingests** CS.AI papers from arXiv (Airflow → PDF parse → PostgreSQL)
2. **Indexes** section-aware chunks with embeddings into OpenSearch (BM25 + vector / RRF hybrid)
3. **Answers** questions via classic RAG (`/ask`, `/stream`) or LangGraph agentic RAG (`/ask-agentic`)
4. **Exposes** Gradio UI and optional Telegram bot
5. **Observes** requests with Langfuse and caches exact-match answers in Redis

```text
┌─────────────┐  ┌──────────────┐  ┌─────────────┐
│ Gradio UI   │  │ Telegram Bot │  │ HTTP Clients│
└──────┬──────┘  └──────┬───────┘  └──────┬──────┘
       │                │                 │
       └────────────────┼─────────────────┘
                        ▼
              ┌──────────────────┐
              │  FastAPI (api)   │  :8000
              │  src/main.py     │
              └────────┬─────────┘
         ┌─────────────┼─────────────┐
         ▼             ▼             ▼
   OpenSearch      Ollama         Redis
   PostgreSQL      Jina API       Langfuse
         ▲
         │
   Airflow DAGs (ingestion + hybrid indexing)
```

---

## 2. Folder structure

```text
production-agentic-rag-course/
├── src/                          # Application code
│   ├── main.py                   # FastAPI app + lifespan DI
│   ├── config.py                 # Pydantic Settings
│   ├── dependencies.py           # FastAPI Depends / typed Deps
│   ├── database.py               # Legacy DB helpers
│   ├── exceptions.py             # Domain exceptions
│   ├── middlewares.py            # Request logging helpers
│   ├── gradio_app.py             # Gradio chat UI
│   ├── routers/                  # HTTP endpoints
│   │   ├── ping.py               # Health
│   │   ├── hybrid_search.py      # BM25 / hybrid search
│   │   ├── ask.py                # Classic RAG + streaming
│   │   └── agentic_ask.py        # Agentic RAG + feedback
│   ├── services/                 # Business logic & clients
│   │   ├── agents/               # LangGraph agentic RAG
│   │   ├── arxiv/                # arXiv API client
│   │   ├── cache/                # Redis response cache
│   │   ├── embeddings/           # Jina embeddings
│   │   ├── indexing/             # Chunking + hybrid indexer
│   │   ├── langfuse/             # Tracing
│   │   ├── ollama/               # Local LLM client + prompts
│   │   ├── opensearch/           # Search index + queries
│   │   ├── pdf_parser/           # Docling PDF parsing
│   │   ├── telegram/             # Telegram bot
│   │   └── metadata_fetcher.py   # Ingestion orchestrator
│   ├── models/                   # SQLAlchemy ORM (Paper)
│   ├── repositories/             # PaperRepository
│   ├── schemas/                  # Pydantic API/domain models
│   └── db/                       # Database abstraction + factory
├── airflow/
│   └── dags/
│       ├── arxiv_paper_ingestion.py
│       └── arxiv_ingestion/      # setup, fetching, indexing, reporting
├── notebooks/week1–week7/        # Course labs (not runtime)
├── tests/                        # unit / api / integration
├── static/                       # Architecture diagrams for README
├── compose.yml                   # Docker services
├── Dockerfile                    # API image (uvicorn src.main:app)
├── gradio_launcher.py            # Gradio entry script
├── pyproject.toml / uv.lock      # Dependencies
└── .env.example                  # Environment template
```

---

## 3. Major modules

| Module | Path | Responsibility |
|--------|------|----------------|
| API boot | `src/main.py` | Create FastAPI app, lifespan init of clients, mount routers, start Telegram |
| Config | `src/config.py` | Nested `Settings` via pydantic-settings |
| DI | `src/dependencies.py` | Read clients from `request.app.state`; build `AgenticRAGService` |
| Classic RAG | `src/routers/ask.py` | Retrieve → prompt → Ollama; cache + Langfuse |
| Hybrid search | `src/routers/hybrid_search.py` | Unified OpenSearch BM25/hybrid |
| Agentic RAG | `src/services/agents/` | LangGraph workflow + nodes + tools |
| Search engine | `src/services/opensearch/` | Index setup, RRF pipeline, `search_unified` |
| Embeddings | `src/services/embeddings/jina_client.py` | Query/doc embeddings (1024-d) |
| LLM | `src/services/ollama/` | Generate / stream RAG answers |
| Ingestion | `src/services/metadata_fetcher.py` + Airflow DAGs | Fetch → parse → Postgres |
| Indexing | `src/services/indexing/` | `TextChunker` + `HybridIndexingService` |
| Cache | `src/services/cache/` | Exact-match Redis cache for ask responses |
| Observability | `src/services/langfuse/` | Traces, spans, feedback |
| Mobile | `src/services/telegram/` | Bot commands → agentic RAG |
| UI | `src/gradio_app.py` | Interactive chat against API |

---

## 4. Entry points

| Entry | How it runs | Notes |
|-------|-------------|--------|
| **API** | `uvicorn src.main:app` (Dockerfile `CMD`, compose `api` service) | Port **8000** |
| **Gradio** | `uv run python gradio_launcher.py` → `src.gradio_app.main` | Port **7861** (typical) |
| **Airflow DAG** | `airflow/dags/arxiv_paper_ingestion.py` | Schedule: weekdays 06:00 UTC |
| **Telegram** | Started inside API lifespan via `make_telegram_service(...).start()` | Requires `TELEGRAM__*` |
| **Notebooks** | `uv run jupyter notebook notebooks/weekN/...` | Learning only |

### API lifespan (`src/main.py`)

On startup the app:

1. Loads `Settings`
2. Connects PostgreSQL (`make_database`)
3. Creates OpenSearch client and `setup_indices()` (hybrid index + RRF pipeline)
4. Instantiates arXiv, PDF parser, embeddings, Ollama, Langfuse, Redis cache
5. Optionally starts `TelegramBot`
6. On shutdown: stops Telegram, tears down DB

Clients are stored on `app.state` and injected through `src/dependencies.py`.

---

## 5. Infrastructure (Docker Compose)

Defined in `compose.yml` on network `rag-network`:

| Service | Container | Host ports | Role |
|---------|-----------|------------|------|
| `api` | `rag-api` | 8000 | FastAPI |
| `postgres` | `rag-postgres` | 5432 | Paper metadata/content |
| `opensearch` | `rag-opensearch` | 9200, 9600 | Hybrid search |
| `opensearch-dashboards` | `rag-dashboards` | 5601 | Search UI |
| `airflow` | `rag-airflow` | 8080 | Ingestion orchestration |
| `ollama` | `rag-ollama` | 11434 | Local LLM |
| `redis` | `rag-redis` | 6379 | RAG response cache |
| `langfuse-web` | `rag-langfuse-web` | 3001→3000 | Tracing UI |
| `langfuse-worker` | `rag-langfuse-worker` | 3030 | Async Langfuse worker |
| `langfuse-postgres` / `langfuse-redis` / `langfuse-minio` / `clickhouse` | — | — | Langfuse backend |

API depends on healthy `postgres`, `opensearch`, and `redis`.

---

## 6. API flow

Routers mounted in `src/main.py`:

| Method | Path | Router file | Behavior |
|--------|------|-------------|----------|
| `GET` | `/api/v1/health` | `ping.py` | Service health |
| `POST` | `/api/v1/hybrid-search/` | `hybrid_search.py` | BM25 or hybrid chunk search |
| `POST` | `/api/v1/ask` | `ask.py` (`ask_router`) | Classic RAG (JSON) |
| `POST` | `/api/v1/stream` | `ask.py` (`stream_router`) | Classic RAG (SSE-style chunks) |
| `POST` | `/api/v1/ask-agentic` | `agentic_ask.py` | LangGraph agentic RAG |
| `POST` | `/api/v1/feedback` | `agentic_ask.py` | Langfuse user feedback |

Interactive docs: `http://localhost:8000/docs`.

### Classic RAG (`POST /api/v1/ask`)

Implemented in `src/routers/ask.py` → `ask_question`:

```text
AskRequest
  → CacheClient.find_cached_response (exact match; optional)
  → _prepare_chunks_and_sources
       → (optional) JinaEmbeddingsClient.embed_query
       → OpenSearchClient.search_unified
  → RAGPromptBuilder (src/services/ollama/prompts.py)
  → OllamaClient.generate_rag_answer
  → AskResponse
  → CacheClient.store_response
  (spans via RAGTracer / LangfuseTracer)
```

Streaming (`POST /api/v1/stream`) follows the same retrieve/prompt path but uses `OllamaClient.generate_rag_answer_stream` and yields `data: {...}` events.

### Hybrid search (`POST /api/v1/hybrid-search/`)

```text
HybridSearchRequest
  → optional embed_query if use_hybrid
  → OpenSearchClient.search_unified(...)
  → SearchResponse (hits with chunk_text, scores, highlights)
```

Falls back to BM25 if embedding generation fails.

### Agentic RAG (`POST /api/v1/ask-agentic`)

```text
AskRequest
  → AgenticRAGDep (make_agentic_rag_service)
  → AgenticRAGService.ask(query)
  → AgenticAskResponse (answer, sources, reasoning_steps, retrieval_attempts, trace_id)
```

---

## 7. Agent workflow

**Orchestrator:** `AgenticRAGService` in `src/services/agents/agentic_rag.py`  
**Graph:** LangGraph `StateGraph(AgentState, context_schema=Context)`  
**Config defaults:** `GraphConfig` in `src/services/agents/config.py` (`max_retrieval_attempts=2`, `guardrail_threshold=60`, `top_k=3`, `use_hybrid=True`)

### Nodes (`src/services/agents/nodes/`)

| Node | File | Role |
|------|------|------|
| `guardrail` | `guardrail_node.py` | Score in-domain relevance; route continue vs out-of-scope |
| `out_of_scope` | `out_of_scope_node.py` | Safe refusal for off-domain queries |
| `retrieve` | `retrieve_node.py` | Emit tool call for retrieval |
| `tool_retrieve` | LangGraph `ToolNode` | Runs retriever tool (`tools.py`) against OpenSearch |
| `grade_documents` | `grade_documents_node.py` | Semantic relevance grading |
| `rewrite_query` | `rewrite_query_node.py` | Rewrite query and retry retrieve |
| `generate_answer` | `generate_answer_node.py` | Final LLM answer with sources |

### Graph topology (from `_build_graph`)

```text
START
  → guardrail
       ├─ out_of_scope → END
       └─ retrieve
            → tool_retrieve (ToolNode)
            → grade_documents
                 ├─ generate_answer → END
                 └─ rewrite_query → retrieve  (loop until max attempts / generate)
```

Routing after guardrail uses `continue_after_guardrail`. After grading, `state["routing_decision"]` chooses `generate_answer` or `rewrite_query`.

### State & context

- **`AgentState`** (`state.py`): messages, original/rewritten query, retrieval_attempts, guardrail/grading results, sources, metadata
- **`Context`** (`context.py`): immutable runtime deps — Ollama, OpenSearch, embeddings, Langfuse, model/top_k/thresholds
- **Retriever tool** (`tools.py`): hybrid/BM25 search via OpenSearch + embeddings

---

## 8. Data flow

### 8.1 Ingestion (write path)

DAG: `arxiv_paper_ingestion` in `airflow/dags/arxiv_paper_ingestion.py`

```text
setup_environment
  → fetch_daily_papers          # arxiv_ingestion/fetching.py
       → MetadataFetcher.fetch_and_process_papers
            → ArxivClient (API)
            → PDFParserService / DoclingParser
            → PaperRepository → PostgreSQL `papers`
  → index_papers_hybrid         # arxiv_ingestion/indexing.py
       → HybridIndexingService.index_papers_batch
            → TextChunker (section-based, overlap)
            → JinaEmbeddingsClient
            → OpenSearchClient.bulk_index_chunks
  → generate_daily_report
  → cleanup_temp_files
```

Schedule: `0 6 * * 1-5` (Mon–Fri 06:00 UTC). Default category: `cs.AI` (`ARXIV__SEARCH_CATEGORY`).

### 8.2 Persistence model

**PostgreSQL** — table `papers` (`src/models/paper.py`):

- Metadata: `arxiv_id`, title, authors, abstract, categories, `published_date`, `pdf_url`
- Parsed content: `raw_text`, `sections`, `references`
- Processing flags: `pdf_processed`, `parser_used`, timestamps

**OpenSearch** — hybrid chunk index `{index_name}-{chunk_index_suffix}` (default `arxiv-papers-chunks`):

- Chunk text + metadata + vector embeddings
- RRF pipeline (`OPENSEARCH__RRF_PIPELINE_NAME`) for hybrid fusion
- Queried primarily via `OpenSearchClient.search_unified`

### 8.3 Query (read path)

```text
User question
  → FastAPI router
  → (optional Redis exact cache)
  → Embed query (Jina) if hybrid
  → OpenSearch retrieval (BM25 and/or vector+RRF)
  → Prompt construction
  → Ollama generation
  → Response (+ Langfuse trace; optional cache store)
```

Agentic path inserts guardrail / grade / rewrite around retrieval before generation.

---

## 9. Important classes

| Class | File | Role |
|-------|------|------|
| `Settings` (+ nested settings) | `src/config.py` | Central configuration |
| `AgenticRAGService` | `src/services/agents/agentic_rag.py` | Builds/runs LangGraph |
| `GraphConfig` | `src/services/agents/config.py` | Agent execution knobs |
| `Context` | `src/services/agents/context.py` | Node dependency injection |
| `OpenSearchClient` | `src/services/opensearch/client.py` | Index + search API |
| `QueryBuilder` | `src/services/opensearch/query_builder.py` | Query DSL helpers |
| `JinaEmbeddingsClient` | `src/services/embeddings/jina_client.py` | Embeddings |
| `OllamaClient` | `src/services/ollama/client.py` | LLM generate/stream |
| `RAGPromptBuilder` | `src/services/ollama/prompts.py` | RAG prompt assembly |
| `MetadataFetcher` | `src/services/metadata_fetcher.py` | End-to-end paper ingest |
| `ArxivClient` | `src/services/arxiv/client.py` | arXiv HTTP/API |
| `PDFParserService` / `DoclingParser` | `src/services/pdf_parser/` | PDF → structured text |
| `TextChunker` | `src/services/indexing/text_chunker.py` | Section-aware chunking |
| `HybridIndexingService` | `src/services/indexing/hybrid_indexer.py` | Chunk + embed + index |
| `Paper` | `src/models/paper.py` | ORM entity |
| `PaperRepository` | `src/repositories/paper.py` | DB CRUD |
| `PostgreSQLDatabase` | `src/db/interfaces/postgresql.py` | Engine/session |
| `CacheClient` | `src/services/cache/client.py` | Redis ask-cache |
| `LangfuseTracer` / `RAGTracer` | `src/services/langfuse/` | Observability |
| `TelegramBot` | `src/services/telegram/bot.py` | Messaging interface |

Factories follow `make_*` naming under each service package and in `src/db/factory.py`.

---

## 10. Configuration

### Loading

- **Library:** pydantic-settings (`BaseSettings`)
- **File:** `.env` (see `.env.example`)
- **Nested delimiter:** `__` (e.g. `ARXIV__MAX_RESULTS`)
- **Accessor:** `get_settings()` in `src/config.py` / cached in `src/dependencies.py`

### Nested setting groups (`src/config.py`)

| Class | Env prefix | Key fields |
|-------|------------|------------|
| `ArxivSettings` | `ARXIV__` | `base_url`, `max_results`, `search_category`, rate limits, concurrency |
| `PDFParserSettings` | `PDF_PARSER__` | `max_pages`, OCR/table flags |
| `ChunkingSettings` | `CHUNKING__` | `chunk_size`, `overlap_size`, `section_based` |
| `OpenSearchSettings` | `OPENSEARCH__` | host, index names, vector dim, RRF pipeline |
| `LangfuseSettings` | `LANGFUSE__` | keys, host, flush, enabled |
| `RedisSettings` | `REDIS__` | host, port, TTL |
| `TelegramSettings` | `TELEGRAM__` | `bot_token`, `enabled` |
| `Settings` (root) | (no prefix) | `postgres_database_url`, `ollama_*`, `jina_api_key`, `debug`, `environment` |

### Agent graph config

`GraphConfig` (not env-driven by default) controls agent behavior; model often taken from `settings.ollama_model` when constructing the service in `get_agentic_rag_service`.

---

## 11. Environment variables

Primary template: `.env.example`. Compose overrides container hostnames for API/Airflow.

### Application & data stores

| Variable | Purpose |
|----------|---------|
| `DEBUG` / `ENVIRONMENT` | App mode |
| `POSTGRES_DATABASE_URL` | SQLAlchemy Postgres URL |
| `OPENSEARCH_HOST` / `OPENSEARCH__HOST` | OpenSearch endpoint |
| `OLLAMA_HOST` / `OLLAMA_MODEL` / `OLLAMA_TIMEOUT` | Local LLM |
| `JINA_API_KEY` | Embeddings (required for hybrid) |

### arXiv & PDF

| Variable | Purpose |
|----------|---------|
| `ARXIV__MAX_RESULTS` | Cap per fetch |
| `ARXIV__BASE_URL` | arXiv API |
| `ARXIV__PDF_CACHE_DIR` | PDF cache path |
| `ARXIV__RATE_LIMIT_DELAY` | Throttle |
| `ARXIV__SEARCH_CATEGORY` | Default `cs.AI` |
| `ARXIV__MAX_CONCURRENT_DOWNLOADS` / `ARXIV__MAX_CONCURRENT_PARSING` | Pipeline concurrency |
| `PDF_PARSER__MAX_PAGES` / `PDF_PARSER__DO_OCR` / … | Docling limits |

### Search & chunking

| Variable | Purpose |
|----------|---------|
| `OPENSEARCH__INDEX_NAME` | Base index name (`arxiv-papers`) |
| `OPENSEARCH__CHUNK_INDEX_SUFFIX` | Chunk index suffix (`chunks`) |
| `OPENSEARCH__VECTOR_DIMENSION` | Default `1024` (Jina) |
| `OPENSEARCH__RRF_PIPELINE_NAME` | Hybrid fusion pipeline |
| `CHUNKING__CHUNK_SIZE` / `OVERLAP_SIZE` / `SECTION_BASED` | Chunker |

### Observability, cache, Telegram

| Variable | Purpose |
|----------|---------|
| `LANGFUSE_ENABLED` / `LANGFUSE_HOST` / `LANGFUSE_PUBLIC_KEY` / `LANGFUSE_SECRET_KEY` | SDK-style keys in `.env.example` |
| `LANGFUSE__*` | Nested settings prefix used by `LangfuseSettings` |
| `LANGFUSE_NEXTAUTH_SECRET` / `LANGFUSE_SALT` / `LANGFUSE_ENCRYPTION_KEY` / MinIO keys | Langfuse Docker services |
| `REDIS__HOST` / `REDIS__PORT` / `REDIS__TTL_HOURS` | Cache |
| `TELEGRAM__ENABLED` / `TELEGRAM__BOT_TOKEN` | Bot |

### Airflow

| Variable | Purpose |
|----------|---------|
| `AIRFLOW__CORE__EXECUTOR` | Executor type |
| `AIRFLOW__DATABASE__SQL_ALCHEMY_CONN` | Airflow metadata DB (shared Postgres in compose) |

> **Note:** Prefer checking both `.env.example` and `src/config.py` when adding variables. Nested groups require the `GROUP__FIELD` form; some Langfuse keys in `.env.example` use the official single-underscore SDK names and compose env overrides.

---

## 12. Dependencies

Defined in `pyproject.toml` (`requires-python = ">=3.12,<3.13"`). Managed with **uv** (`uv.lock`).

### Runtime

| Package | Use |
|---------|-----|
| `fastapi[standard]`, `uvicorn` | HTTP API |
| `pydantic`, `pydantic-settings` | Schemas + config |
| `sqlalchemy`, `psycopg2-binary`, `alembic` | Postgres ORM/migrations |
| `opensearch-py` | Search client |
| `httpx`, `requests` | HTTP |
| `docling` | Scientific PDF parsing |
| `sentence-transformers` | Embedding-related tooling |
| `gradio` | Web UI |
| `langfuse` | Tracing |
| `redis` | Caching |
| `python-telegram-bot` | Telegram |
| `langgraph`, `langchain`, `langchain-core`, `langchain-community`, `langchain-ollama` | Agentic RAG |

### Dev (`dependency-groups.dev`)

`pytest` (+ plugins), `ruff`, `mypy`, `pre-commit`, `jupyter`/`notebook`, `testcontainers`, `polyfactory`, etc.

### External services (not PyPI)

- Docker images: OpenSearch 2.19, Postgres 16, Redis 7, Ollama, Airflow custom image, Langfuse 3 stack
- **Jina AI** HTTP API for embeddings
- **arXiv** Atom API (`export.arxiv.org`)

---

## 13. Layering conventions

1. **Routers** — HTTP only; validate with `src/schemas/`; call services via deps  
2. **Services** — I/O and domain logic; construct via `make_*` factories  
3. **Repositories** — Postgres only  
4. **README / notebooks** — teaching material; **`src/` + `compose.yml`** define runtime behavior  

When docs and code disagree, trust the code paths listed above.

---

## 14. Quick reference: request → code

| User action | First code | Core services |
|-------------|------------|---------------|
| Health check | `src/routers/ping.py` | OpenSearch/DB health probes |
| Keyword/hybrid search | `src/routers/hybrid_search.py` | `OpenSearchClient`, `JinaEmbeddingsClient` |
| Ask (classic) | `src/routers/ask.py` | OpenSearch → Ollama → Cache/Langfuse |
| Ask (agentic) | `src/routers/agentic_ask.py` | `AgenticRAGService` graph |
| Daily ingest | `airflow/dags/arxiv_paper_ingestion.py` | `MetadataFetcher` → `HybridIndexingService` |
| Telegram message | `src/services/telegram/bot.py` | Agentic RAG stack |
| Gradio chat | `src/gradio_app.py` | Calls API endpoints |

---

*Generated from the repository implementation. Update this file when routers, graph topology, or compose services change.*
