# Execution Flow: HTTP → LLM Response

**Source of truth:** `src/routers/ask.py`, `src/routers/agentic_ask.py`, `src/services/ollama/client.py`, `src/services/agents/`

This document traces request handling from the HTTP endpoint until an LLM answer is returned. There are two paths:

- **Path A — Classic RAG:** `POST /api/v1/ask` (complete linear flow to Ollama `/api/generate`)
- **Path B — Agentic RAG:** `POST /api/v1/ask-agentic` (LangGraph workflow around retrieval + generation)

Streaming classic RAG (`POST /api/v1/stream`) follows Path A until generation, then streams tokens.

---

## Path A — Classic RAG (`POST /api/v1/ask`)

### Call stack (summary)

```text
HTTP POST /api/v1/ask
  → ask_question()                              # src/routers/ask.py
  → (optional) CacheClient.find_cached_response
  → _prepare_chunks_and_sources()
       → JinaEmbeddingsClient.embed_query       # if use_hybrid
       → OpenSearchClient.search_unified
            → _search_hybrid_native | _search_bm25_only
  → RAGPromptBuilder.create_structured_prompt / create_rag_prompt
  → OllamaClient.generate_rag_answer
       → RAGPromptBuilder (again inside client)
       → OllamaClient.generate
            → HTTP POST {OLLAMA_HOST}/api/generate
  → AskResponse JSON returned
  → (optional) CacheClient.store_response
```

### Minimal stack

```text
ask_question
  └─ _prepare_chunks_and_sources
       └─ OpenSearchClient.search_unified
  └─ OllamaClient.generate_rag_answer
       └─ OllamaClient.generate
            └─ POST http://ollama:11434/api/generate
  └─ return AskResponse(answer=...)
```

---

### Step-by-step

#### 1. Router entry

- `src/main.py` mounts `ask_router` at prefix `/api/v1`.
- FastAPI injects clients from `app.state` via `src/dependencies.py`:
  - `OpenSearchDep`
  - `EmbeddingsDep`
  - `OllamaDep`
  - `LangfuseDep`
  - `CacheDep`
- Handler: `ask_question` in `src/routers/ask.py`.

#### 2. `ask_question` start

File: `src/routers/ask.py`

1. Creates `RAGTracer(langfuse_tracer)` and opens `trace_request("api_user", request.query)`.
2. **Cache check:** if `cache_client` is present, calls `await cache_client.find_cached_response(request)`.
   - On hit → returns cached `AskResponse` immediately (**no LLM call**).
3. Calls `_prepare_chunks_and_sources(...)`.

#### 3. Retrieval — `_prepare_chunks_and_sources`

Same file: `src/routers/ask.py`

1. If `request.use_hybrid`:
   - `query_embedding = await embeddings_service.embed_query(request.query)`
   - (`JinaEmbeddingsClient` in `src/services/embeddings/jina_client.py`)
   - On embedding failure → logs warning and falls back toward BM25 (no embedding).
2. Search:
   - `opensearch_client.search_unified(...)` in `src/services/opensearch/client.py`
   - If no embedding or hybrid disabled → `_search_bm25_only`
   - Else → `_search_hybrid_native` (BM25 query + kNN fused via RRF pipeline)
3. Maps hits into:
   - `chunks`: `{arxiv_id, chunk_text}`
   - `sources`: `https://arxiv.org/pdf/{id}.pdf` URLs
4. If `chunks` is empty → returns canned “couldn’t find…” `AskResponse` (**no LLM call**).

#### 4. Prompt construction

Still in `ask_question` (`src/routers/ask.py`):

- Instantiates `RAGPromptBuilder` from `src/services/ollama/prompts.py`
- Tries `create_structured_prompt(query, chunks)`
- Falls back to `create_rag_prompt(query, chunks)`
- Langfuse: `trace_prompt_construction` / `end_prompt`

#### 5. LLM generation

`await ollama_client.generate_rag_answer(query=..., chunks=..., model=request.model)`

File: `src/services/ollama/client.py` → `OllamaClient.generate_rag_answer`

1. Builds prompt via `RAGPromptBuilder` again (structured or plain).
2. Calls `self.generate(model=..., prompt=..., temperature=0.7, top_p=0.9)`.
3. `generate` POSTs JSON to `{settings.ollama_host}/api/generate` using `httpx.AsyncClient`.
4. Reads `result["response"]` as answer text.
5. Attaches usage metadata when present (`prompt_eval_count`, `eval_count`, durations).
6. Returns dict: `answer`, `sources`, `confidence`, `citations`.

#### 6. HTTP response

Back in `ask_question`:

1. Builds `AskResponse(query, answer, sources, chunks_used, search_mode)`.
2. Ends Langfuse request span (`end_request`).
3. Optionally `await cache_client.store_response(request, response)`.
4. Returns JSON to the client.

---

## Path A′ — Streaming (`POST /api/v1/stream`)

Handler: `ask_question_stream` in `src/routers/ask.py` (`stream_router`).

Same flow through cache + `_prepare_chunks_and_sources`, then:

1. Yields metadata event: `{sources, chunks_used, search_mode}`
2. Builds prompt with `RAGPromptBuilder.create_rag_prompt`
3. Calls `ollama_client.generate_rag_answer_stream` → `generate_stream`
4. Streams lines from Ollama `POST /api/generate` with `stream: true`
5. Yields `data: {"chunk": "..."}` events, then `{"answer": "...", "done": true}`
6. Optionally stores full answer in Redis

Returns `StreamingResponse` (`media_type="text/plain"`).

---

## Path B — Agentic RAG (`POST /api/v1/ask-agentic`)

### Call stack (summary)

```text
HTTP POST /api/v1/ask-agentic
  → ask_agentic()                               # src/routers/agentic_ask.py
  → AgenticRAGDep → make_agentic_rag_service    # dependencies.py / agents/factory.py
  → AgenticRAGService.ask(query)                # agents/agentic_rag.py
  → graph.ainvoke(state, context=Context(...))
       → guardrail          # LLM: in-domain score
       → retrieve           # emit tool call
       → tool_retrieve      # ToolNode → retrieve_papers
            → embed_query + search_unified
       → grade_documents    # LLM: relevance
       → rewrite_query?     # LLM rewrite → loop to retrieve
       → generate_answer    # LLM final answer
  → _extract_answer / _extract_sources
  → AgenticAskResponse
```

### Step-by-step

#### 1. Router entry

File: `src/routers/agentic_ask.py`

- `POST /api/v1/ask-agentic` → `ask_agentic(request, agentic_rag: AgenticRAGDep)`
- DI: `get_agentic_rag_service` in `src/dependencies.py` → `make_agentic_rag_service` in `src/services/agents/factory.py`

#### 2. `AgenticRAGService.ask`

File: `src/services/agents/agentic_rag.py`

1. Validates non-empty query.
2. Optionally starts Langfuse span `agentic_rag_request`.
3. Calls `_run_workflow(query, model, user_id, trace)`.

#### 3. `_run_workflow`

1. Initializes `AgentState` (`messages=[HumanMessage(query)]`, counters, empty grading/sources).
2. Builds runtime `Context` with Ollama, OpenSearch, embeddings, Langfuse, `top_k`, thresholds (`src/services/agents/context.py`).
3. `await self.graph.ainvoke(state_input, config=..., context=runtime_context)`.

#### 4. Graph nodes

Topology from `AgenticRAGService._build_graph` (`src/services/agents/agentic_rag.py`):

| Order | Node | File | Role |
|-------|------|------|------|
| 1 | `guardrail` | `nodes/guardrail_node.py` | Score query in-domain; `continue_after_guardrail` |
| 2a | `out_of_scope` | `nodes/out_of_scope_node.py` | Refuse off-domain → END |
| 2b | `retrieve` | `nodes/retrieve_node.py` | Emit retriever tool call |
| 3 | `tool_retrieve` | LangGraph `ToolNode` | Runs `retrieve_papers` |
| 4 | `grade_documents` | `nodes/grade_documents_node.py` | Route `generate_answer` or `rewrite_query` |
| 5a | `rewrite_query` | `nodes/rewrite_query_node.py` | Rewrite → back to `retrieve` |
| 5b | `generate_answer` | `nodes/generate_answer_node.py` | Final LLM answer → END |

Retriever tool (`src/services/agents/tools.py` → `retrieve_papers`):

1. `embeddings_client.embed_query(query)`
2. `opensearch_client.search_unified(..., use_hybrid=...)`
3. Converts hits to LangChain `Document`s

#### 5. Final LLM (intended)

File: `src/services/agents/nodes/generate_answer_node.py` → `ainvoke_generate_answer_step`

1. Reads latest query + retrieved context from messages.
2. Formats `GENERATE_ANSWER_PROMPT` (`src/services/agents/prompts.py`).
3. Intended call:
   ```python
   llm = runtime.context.ollama_client.get_langchain_model(...)
   response = await llm.ainvoke(answer_prompt)
   ```
4. Appends `AIMessage(content=answer)` to state.

Guardrail, grade, and rewrite nodes use the same `get_langchain_model` pattern.

#### 6. HTTP response

Back in `AgenticRAGService._run_workflow` / `ask`:

1. `_extract_answer(result)` — last message content
2. `_extract_sources(result)` / reasoning steps / retrieval attempts
3. Router maps to `AgenticAskResponse` and returns JSON

---

## Implementation note (agentic LLM adapter)

Classic Path A reaches Ollama through `OllamaClient.generate` → `POST /api/generate`.

Agentic nodes call `ollama_client.get_langchain_model(...)`. In the current tree, **`get_langchain_model` is not defined** on `OllamaClient` (`src/services/ollama/client.py`) and has no other definition in the repo. Path A is the path that clearly completes HTTP → Ollama → response as implemented today.

---

## Quick reference

| Concern | File |
|---------|------|
| Mount routers | `src/main.py` |
| Classic ask / stream | `src/routers/ask.py` |
| Agentic ask | `src/routers/agentic_ask.py` |
| DI | `src/dependencies.py` |
| OpenSearch unified search | `src/services/opensearch/client.py` |
| Jina embeddings | `src/services/embeddings/jina_client.py` |
| Ollama HTTP client | `src/services/ollama/client.py` |
| RAG prompts (classic) | `src/services/ollama/prompts.py` |
| Redis cache | `src/services/cache/client.py` |
| LangGraph orchestration | `src/services/agents/agentic_rag.py` |
| Agent nodes | `src/services/agents/nodes/` |
| Retriever tool | `src/services/agents/tools.py` |

---

*Update this document when router handlers, graph edges, or `OllamaClient` generation APIs change.*
