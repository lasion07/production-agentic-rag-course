from __future__ import annotations

import asyncio
import time
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from src.services.agents.agentic_rag import AgenticRAGService
from src.services.agents.config import GraphConfig
from src.services.agents.models import GradeDocuments, GuardrailScoring
from src.services.agents.nodes.generate_answer_node import ainvoke_generate_answer_step
from src.services.agents.nodes.grade_documents_node import route_after_grading
from src.services.agents.nodes.rewrite_query_node import QueryRewriteOutput
from src.services.agents.nodes.tool_execution_node import route_after_tool
from src.services.agents.tools import execute_retrieval

HIT = {
    "chunk_id": "1706.03762:v1:c1",
    "chunk_text": "Transformers use attention to model token relationships.",
    "arxiv_id": "1706.03762",
    "title": "Attention Is All You Need",
    "authors": "Vaswani et al.",
    "score": 0.99,
}


class TimeoutEmbeddings:
    def __init__(self) -> None:
        self.attempts = 0

    async def embed_query(self, _query: str) -> list[float]:
        self.attempts += 1
        raise httpx.ReadTimeout(
            "timeout",
            request=httpx.Request("POST", "https://api.jina.ai/v1/embeddings"),
        )


class UnexpectedEmbeddings:
    async def embed_query(self, _query: str) -> list[float]:
        raise AssertionError("BM25 mode must not call the embedding dependency")


class RateLimitedEmbeddings:
    def __init__(self) -> None:
        self.attempts = 0

    async def embed_query(self, _query: str) -> list[float]:
        self.attempts += 1
        request = httpx.Request("POST", "https://api.jina.ai/v1/embeddings")
        response = httpx.Response(429, headers={"Retry-After": "20"}, request=request)
        raise httpx.HTTPStatusError("rate limited", request=request, response=response)


class SuccessfulEmbeddings:
    async def embed_query(self, _query: str) -> list[float]:
        return [0.1, 0.2]


class SearchDouble:
    def __init__(self, effects: list[Any]) -> None:
        self.effects = list(effects)
        self.calls: list[dict[str, Any]] = []

    def search_unified(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        effect = self.effects.pop(0)
        if isinstance(effect, Exception):
            raise effect
        return effect


@pytest.mark.asyncio
async def test_embedding_timeout_twice_degrades_to_bm25() -> None:
    embeddings = TimeoutEmbeddings()
    search = SearchDouble([{"total": 1, "hits": [HIT]}])

    outcome = await execute_retrieval(
        query="attention",
        opensearch_client=search,
        embeddings_client=embeddings,
        use_hybrid=True,
    )

    assert outcome.status == "degraded"
    assert outcome.embedding_attempts == 2
    assert outcome.fallbacks == 1
    assert outcome.actual_search_mode == "bm25"
    assert len(outcome.documents) == 1
    assert search.calls[0]["use_hybrid"] is False


@pytest.mark.asyncio
async def test_search_timeout_is_not_masked_as_zero_hits() -> None:
    search = SearchDouble([TimeoutError("one"), TimeoutError("two")])

    outcome = await execute_retrieval(
        query="attention",
        opensearch_client=search,
        embeddings_client=SuccessfulEmbeddings(),
        use_hybrid=True,
    )

    assert outcome.status == "error"
    assert outcome.documents == []
    assert outcome.tool_attempts == 2
    assert outcome.tool_failures == 2
    assert route_after_tool({"tool_status": outcome.status}) == "retrieval_unavailable"


@pytest.mark.asyncio
async def test_valid_zero_hits_remains_semantic_miss() -> None:
    outcome = await execute_retrieval(
        query="absent",
        opensearch_client=SearchDouble([{"total": 0, "hits": []}]),
        embeddings_client=SuccessfulEmbeddings(),
        use_hybrid=True,
    )

    assert outcome.status == "success"
    assert outcome.documents == []
    assert outcome.tool_failures == 0
    assert route_after_tool({"tool_status": outcome.status}) == "grade_documents"


@pytest.mark.asyncio
async def test_retrieval_diagnostics_distinguish_candidates_from_final_context() -> None:
    secondary_hit = {
        **HIT,
        "chunk_id": "1706.03762:v1:c2",
        "chunk_text": "A secondary discussion with little query overlap.",
        "score": None,
    }
    outcome = await execute_retrieval(
        query="How does transformer attention work?",
        opensearch_client=SearchDouble(
            [{"total": 2, "hits": [HIT, secondary_hit]}]
        ),
        embeddings_client=SuccessfulEmbeddings(),
        top_k=1,
        use_hybrid=True,
    )

    diagnostics = outcome.diagnostics
    assert diagnostics["candidate_count"] == 2
    assert diagnostics["selected_count"] == 1
    assert diagnostics["selected_chunk_ids"] == ["1706.03762:v1:c1"]
    selected_row = diagnostics["candidate_chunks"][0]
    assert selected_row["chunk_id"] == "1706.03762:v1:c1"
    assert selected_row["arxiv_id"] == "1706.03762"
    assert selected_row["candidate_rank"] == 1
    assert selected_row["retrieval_score"] == 0.99
    assert selected_row["selected"] is True
    assert selected_row["selected_rank"] == 1
    assert isinstance(selected_row["selection_score"], float)
    assert diagnostics["candidate_chunks"][1]["selected"] is False
    assert diagnostics["candidate_chunks"][1]["retrieval_score"] == 0.0


@pytest.mark.asyncio
async def test_retry_after_longer_than_deadline_uses_bm25_without_waiting() -> None:
    embeddings = RateLimitedEmbeddings()
    search = SearchDouble([{"total": 1, "hits": [HIT]}])
    started = time.monotonic()

    outcome = await execute_retrieval(
        query="attention",
        opensearch_client=search,
        embeddings_client=embeddings,
        use_hybrid=True,
        deadline_monotonic=time.monotonic() + 8,
        generation_reserve_seconds=5,
    )

    assert time.monotonic() - started < 1
    assert embeddings.attempts == 1
    assert outcome.status == "degraded"
    assert outcome.actual_search_mode == "bm25"


def test_contradictory_generate_decision_fails_safe() -> None:
    runtime = type("Runtime", (), {"context": type("Context", (), {"max_retrieval_attempts": 2})()})()
    state = {
        "routing_decision": "generate_answer",
        "relevant_documents": [],
        "retrieval_attempts": 2,
    }

    assert route_after_grading(state, runtime) == "insufficient_evidence"


class StructuredModel:
    def __init__(self, schema: type) -> None:
        self.schema = schema

    async def ainvoke(self, _prompt: str) -> Any:
        if self.schema is GuardrailScoring:
            return GuardrailScoring(score=90, reason="research query")
        if self.schema is GradeDocuments:
            return GradeDocuments(binary_score="yes", reasoning="relevant")
        if self.schema is QueryRewriteOutput:
            return QueryRewriteOutput(
                rewritten_query="rewritten research query",
                reasoning="semantic recovery",
            )
        raise AssertionError(f"Unexpected schema: {self.schema}")


class FakeModel:
    def with_structured_output(self, schema: type) -> StructuredModel:
        return StructuredModel(schema)

    async def ainvoke(self, _prompt: str) -> AIMessage:
        return AIMessage(
            content="Grounded answer citing Attention Is All You Need [arXiv:1706.03762]."
        )


class FakeOllama:
    def validate_model(self, model: str | None = None) -> str:
        return model or "test-model"

    def get_langchain_model(self, **_kwargs: Any) -> FakeModel:
        return FakeModel()


class SlowModel:
    def with_structured_output(self, _schema: type):
        return self

    async def ainvoke(self, _prompt: str):
        await asyncio.sleep(1)
        return GuardrailScoring(score=90, reason="late")


class SlowOllama:
    def validate_model(self, model: str | None = None) -> str:
        return model or "test-model"

    def get_langchain_model(self, **_kwargs: Any) -> SlowModel:
        return SlowModel()


@pytest.mark.asyncio
async def test_full_graph_reports_actual_execution_contract() -> None:
    search = SearchDouble([{"total": 1, "hits": [HIT]}])
    service = AgenticRAGService(
        opensearch_client=search,
        llm_client=FakeOllama(),
        embeddings_client=UnexpectedEmbeddings(),
        graph_config=GraphConfig(
            model="model-a",
            top_k=3,
            use_hybrid=True,
            max_retrieval_attempts=2,
        ),
    )

    result = await service.ask(
        query="How does transformer attention work?",
        model="model-b",
        top_k=5,
        use_hybrid=False,
        categories=["cs.AI"],
    )

    assert result["business_status"] == "success"
    assert result["terminal_route"] == "generate_answer"
    assert result["requested_search_mode"] == "bm25"
    assert result["actual_search_mode"] == "bm25"
    assert result["chunks_used"] == 1
    assert result["sources"] == ["https://arxiv.org/pdf/1706.03762.pdf"]
    assert search.calls[0]["size"] == 20
    assert search.calls[0]["categories"] == ["cs.AI"]


@pytest.mark.asyncio
async def test_full_graph_two_zero_results_terminates_without_second_rewrite() -> None:
    search = SearchDouble(
        [
            {"total": 0, "hits": []},
            {"total": 0, "hits": []},
        ]
    )
    service = AgenticRAGService(
        opensearch_client=search,
        llm_client=FakeOllama(),
        embeddings_client=UnexpectedEmbeddings(),
        graph_config=GraphConfig(max_retrieval_attempts=2),
    )

    result = await service.ask(query="An absent research topic", use_hybrid=False)

    assert result["business_status"] == "insufficient_evidence"
    assert result["terminal_route"] == "insufficient_evidence"
    assert result["retrieval_attempts"] == 2
    assert result["rewritten_query"] == "rewritten research query"
    assert result["chunks_used"] == 0
    assert len(search.calls) == 2


@pytest.mark.asyncio
async def test_full_graph_search_failure_terminates_as_unavailable() -> None:
    search = SearchDouble([TimeoutError("one"), TimeoutError("two")])
    service = AgenticRAGService(
        opensearch_client=search,
        llm_client=FakeOllama(),
        embeddings_client=UnexpectedEmbeddings(),
        graph_config=GraphConfig(max_search_attempts=2),
    )

    result = await service.ask(query="How does attention work?", use_hybrid=False)

    assert result["business_status"] == "retrieval_unavailable"
    assert result["terminal_route"] == "retrieval_unavailable"
    assert result["tool_attempts"] == 2
    assert result["tool_failures"] == 2
    assert result["chunks_used"] == 0


@pytest.mark.asyncio
async def test_outer_deadline_bounds_slow_agent_nodes() -> None:
    service = AgenticRAGService(
        opensearch_client=SearchDouble([{"total": 0, "hits": []}]),
        llm_client=SlowOllama(),
        embeddings_client=UnexpectedEmbeddings(),
        graph_config=GraphConfig(total_deadline_seconds=0.01),
    )

    result = await service.ask(query="A research question", use_hybrid=False)

    assert result["business_status"] == "deadline_exceeded"
    assert result["terminal_route"] == "deadline_exceeded"


@pytest.mark.asyncio
async def test_generation_timeout_returns_grounded_degraded_extract() -> None:
    runtime = SimpleNamespace(
        context=SimpleNamespace(
            llm_client=SlowOllama(),
            model_name="slow-model",
            temperature=0.0,
            deadline_monotonic=time.monotonic() + 10.02,
            langfuse_enabled=False,
            trace=None,
        )
    )
    state = {
        "messages": [
            HumanMessage(content="What is attention?"),
            ToolMessage(
                content="Attention weights relevant token relationships.",
                tool_call_id="retrieve_1",
                name="retrieve_papers",
            ),
        ],
        "relevant_sources": [{"url": "https://arxiv.org/pdf/1706.03762.pdf"}],
        "business_status": None,
    }

    result = await ainvoke_generate_answer_step(state, runtime)

    assert result["business_status"] == "degraded"
    assert "most relevant retrieved evidence" in result["messages"][0].content
    assert "Attention weights" in result["messages"][0].content
