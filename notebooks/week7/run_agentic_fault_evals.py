"""Deterministic Week 7.4 fault-injection suite through the real graph and API.

The production ``AgenticRAGService`` and ``/api/v1/ask-agentic`` route execute for
every case. Only external LLM, embedding, and search transports are replaced by
scripted adapters, so the suite remains deterministic and makes no network calls.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import sys
from pathlib import Path
from typing import Any

import httpx
from langchain_core.messages import AIMessage

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src import dependencies
from src.config import Settings
from src.main import app
from src.services.agents.agentic_rag import AgenticRAGService
from src.services.agents.config import GraphConfig
from src.services.agents.models import GradeDocuments, GuardrailScoring
from src.services.agents.nodes.rewrite_query_node import QueryRewriteOutput

DATASET_PATH = Path(__file__).with_name("agentic_eval_dataset_v0.json")


HIT = {
    "chunk_text": "Transformers use attention to model relevant token relationships.",
    "arxiv_id": "1706.03762",
    "title": "Attention Is All You Need",
    "authors": "Vaswani et al.",
    "score": 1.0,
}


class ScriptedStructuredLLM:
    def __init__(self, owner: "ScriptedLLM", schema: type):
        self.owner = owner
        self.schema = schema

    async def ainvoke(self, _prompt: str) -> Any:
        if self.schema is GuardrailScoring:
            score = self.owner.guardrail_scores.pop(0)
            return GuardrailScoring(score=score, reason=f"Injected guardrail score: {score}")
        if self.schema is GradeDocuments:
            grade = self.owner.grades.pop(0)
            return GradeDocuments(binary_score=grade, reasoning=f"Injected grade: {grade}")
        if self.schema is QueryRewriteOutput:
            self.owner.rewrite_count += 1
            return QueryRewriteOutput(
                rewritten_query="rewritten research query",
                reasoning="Injected semantic recovery",
            )
        raise AssertionError(f"Unexpected structured schema: {self.schema}")


class ScriptedLangChainModel:
    def __init__(self, owner: "ScriptedLLM"):
        self.owner = owner

    def with_structured_output(self, schema: type) -> ScriptedStructuredLLM:
        return ScriptedStructuredLLM(self.owner, schema)

    async def ainvoke(self, _prompt: str) -> AIMessage:
        self.owner.generation_count += 1
        return AIMessage(content="Grounded deterministic answer [arXiv:1706.03762].")


class ScriptedLLM:
    provider_name = "deterministic"

    def __init__(self, *, guardrail_scores: list[int], grades: list[str]):
        self.guardrail_scores = list(guardrail_scores)
        self.grades = list(grades)
        self.rewrite_count = 0
        self.generation_count = 0

    def validate_model(self, model: str | None = None) -> str:
        return model or "fault-injection-model"

    def get_langchain_model(self, **_kwargs: Any) -> ScriptedLangChainModel:
        return ScriptedLangChainModel(self)


class TimeoutEmbeddings:
    def __init__(self) -> None:
        self.attempts = 0

    async def embed_query(self, _query: str) -> list[float]:
        self.attempts += 1
        request = httpx.Request("POST", "https://api.jina.ai/v1/embeddings")
        raise httpx.ReadTimeout("Injected Jina timeout", request=request)


class SearchDouble:
    def __init__(self, effects: list[Any]):
        self.effects = list(effects)
        self.calls: list[dict[str, Any]] = []

    def search_unified(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        if not self.effects:
            raise AssertionError("Unexpected OpenSearch call")
        effect = self.effects.pop(0)
        if isinstance(effect, Exception):
            raise effect
        return effect


class SuccessfulEmbeddings:
    async def embed_query(self, _query: str) -> list[float]:
        return [0.1, 0.2]


class RecordingAgenticService:
    def __init__(self, service: AgenticRAGService):
        self.service = service
        self.last_result: dict[str, Any] | None = None

    async def ask(self, **kwargs: Any) -> dict[str, Any]:
        self.last_result = await self.service.ask(**kwargs)
        return self.last_result


def _case_dependencies(case_id: str) -> tuple[ScriptedLLM, Any, SearchDouble]:
    relevant = {"total": 1, "hits": [HIT]}
    empty = {"total": 0, "hits": []}
    if case_id == "W7E-01":
        return ScriptedLLM(guardrail_scores=[20], grades=[]), SuccessfulEmbeddings(), SearchDouble([])
    if case_id == "W7E-02":
        return ScriptedLLM(guardrail_scores=[90], grades=["yes"]), SuccessfulEmbeddings(), SearchDouble([relevant])
    if case_id == "W7E-03":
        return (
            ScriptedLLM(guardrail_scores=[90], grades=["no", "yes"]),
            SuccessfulEmbeddings(),
            SearchDouble([relevant, relevant]),
        )
    if case_id == "W7E-04":
        return ScriptedLLM(guardrail_scores=[90], grades=[]), SuccessfulEmbeddings(), SearchDouble([empty, empty])
    if case_id == "W7E-05":
        return ScriptedLLM(guardrail_scores=[90], grades=["yes"]), TimeoutEmbeddings(), SearchDouble([relevant])
    if case_id == "W7E-06":
        return (
            ScriptedLLM(guardrail_scores=[90], grades=[]),
            SuccessfulEmbeddings(),
            SearchDouble([TimeoutError("Injected timeout 1"), TimeoutError("Injected timeout 2")]),
        )
    raise ValueError(f"Unknown case: {case_id}")


def _make_recording_service(case_id: str) -> tuple[RecordingAgenticService, ScriptedLLM, SearchDouble]:
    llm, embeddings, search = _case_dependencies(case_id)
    service = AgenticRAGService(
        opensearch_client=search,
        llm_client=llm,
        embeddings_client=embeddings,
        langfuse_tracer=None,
        graph_config=GraphConfig(
            model="fault-injection-model",
            max_retrieval_attempts=2,
            max_embedding_attempts=2,
            max_search_attempts=2,
            total_deadline_seconds=30,
            generation_reserve_seconds=2,
        ),
    )
    return RecordingAgenticService(service), llm, search


def dependency_construction_blocker() -> str | None:
    try:
        _make_recording_service("W7E-01")
    except Exception as exc:
        return f"{type(exc).__name__}: {exc}"
    return None


async def probe_case(case_id: str, query: str) -> dict[str, Any]:
    service, scripted_llm, search = _make_recording_service(case_id)
    app.state.settings = Settings(_env_file=None, api_auth_enabled=False, api_rate_limit_enabled=False)
    app.dependency_overrides[dependencies.get_agentic_rag_service] = lambda: service
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://fault-eval") as client:
            response = await client.post(
                "/api/v1/ask-agentic",
                json={"query": query, "top_k": 3, "use_hybrid": True},
            )
    finally:
        app.dependency_overrides.pop(dependencies.get_agentic_rag_service, None)

    payload = response.json()
    graph_result = service.last_result or {}
    business_status = payload.get("business_status") or payload.get("error", {}).get("code")
    terminal_route = graph_result.get("terminal_route")
    retrieval_rounds = graph_result.get("retrieval_attempts", 0)
    source_count = len(payload.get("sources", []))
    generation_count = scripted_llm.generation_count
    return {
        "terminal_route": terminal_route,
        "business_status": business_status,
        "http_status": response.status_code,
        "retrieval_expected": retrieval_rounds > 0,
        "retrieval_rounds": retrieval_rounds,
        "rewrite_expected": scripted_llm.rewrite_count > 0,
        "rewrite_count": scripted_llm.rewrite_count,
        "generation_expected": generation_count > 0,
        "source_count": source_count,
        "requested_search_mode": graph_result.get("requested_search_mode"),
        "actual_search_mode": graph_result.get("actual_search_mode"),
        "embedding_attempts": graph_result.get("embedding_attempts", 0),
        "tool_attempts": graph_result.get("tool_attempts", 0),
        "tool_failures": graph_result.get("tool_failures", 0),
        "fallbacks": graph_result.get("fallbacks", 0),
        "error_masked_as_empty": business_status == "insufficient_evidence"
        and graph_result.get("tool_failures", 0) > 0,
    }


def compare_exact(expected: dict[str, Any], actual: dict[str, Any], keys: list[str]) -> str:
    comparable = [key for key in keys if key in expected]
    if not comparable:
        return "pass"
    return "pass" if all(actual.get(key) == expected[key] for key in comparable) else "fail"


def evaluate(expected: dict[str, Any], actual: dict[str, Any], blocker: str | None) -> dict[str, str]:
    route_status = compare_exact(
        expected,
        actual,
        [
            "terminal_route",
            "business_status",
            "retrieval_expected",
            "generation_expected",
            "requested_search_mode",
            "actual_search_mode",
        ],
    )

    budget_status = compare_exact(
        expected,
        actual,
        ["retrieval_rounds", "embedding_attempts", "tool_attempts", "tool_failures", "fallbacks"],
    )
    if "maximum_rewrites" in expected and actual.get("rewrite_count", 0) > expected["maximum_rewrites"]:
        budget_status = "fail"

    if "minimum_sources" in expected and actual.get("source_count", 0) < expected["minimum_sources"]:
        route_status = "fail"

    response_status = "blocked" if blocker else compare_exact(expected, actual, ["http_status"])
    return {
        "route_contract_pass": route_status,
        "call_budget_pass": budget_status,
        "response_contract_pass": response_status,
    }


async def main() -> None:
    dataset = json.loads(DATASET_PATH.read_text())
    blocker = dependency_construction_blocker()
    results = []

    print(f"dataset={DATASET_PATH.name} items={len(dataset)}")
    print(
        f"factory_signature={inspect.signature(__import__('src.services.agents.factory', fromlist=['make_agentic_rag_service']).make_agentic_rag_service)}"
    )
    print(f"e2e_blocker={blocker or 'none'}")

    for item in dataset:
        case_id = item["metadata"]["case_id"]
        actual = await probe_case(case_id, item["input"]["query"])
        scores = evaluate(item["expectedOutput"], actual, blocker)
        results.append(scores)
        print(
            f"{case_id} route={scores['route_contract_pass']} "
            f"budget={scores['call_budget_pass']} response={scores['response_contract_pass']} "
            f"actual={json.dumps(actual, sort_keys=True)}"
        )

    counts = {
        status: sum(score == status for result in results for score in result.values()) for status in ("pass", "fail", "blocked")
    }
    print(f"score_summary={json.dumps(counts, sort_keys=True)}")
    raise SystemExit(1 if counts["fail"] or counts["blocked"] else 0)


if __name__ == "__main__":
    asyncio.run(main())
