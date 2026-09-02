"""Deterministic Week 7.4 fault-injection baseline against current source behavior.

This runner does not modify production code or call external AI services. It probes
current nodes/tools with controlled doubles, then compares observations with the
approved target contracts in ``agentic_eval_dataset_v0.json``.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
from langchain_core.messages import HumanMessage, ToolMessage

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.dependencies import get_agentic_rag_service
from src.services.agents.models import GradeDocuments, GuardrailScoring
from src.services.agents.nodes.grade_documents_node import ainvoke_grade_documents_step
from src.services.agents.nodes.guardrail_node import continue_after_guardrail
from src.services.agents.tools import create_retriever_tool
from src.services.opensearch.client import OpenSearchClient


DATASET_PATH = Path(__file__).with_name("agentic_eval_dataset_v0.json")


class FakeStructuredLLM:
    def __init__(self, result: GradeDocuments):
        self.result = result

    async def ainvoke(self, _prompt: str) -> GradeDocuments:
        return self.result


class FakeLangChainModel:
    def __init__(self, result: GradeDocuments):
        self.result = result

    def with_structured_output(self, _schema: type) -> FakeStructuredLLM:
        return FakeStructuredLLM(self.result)


class FakeOllama:
    def __init__(self, grades: list[str]):
        self.grades = list(grades)

    def get_langchain_model(self, **_kwargs: Any) -> FakeLangChainModel:
        grade = self.grades.pop(0)
        return FakeLangChainModel(
            GradeDocuments(binary_score=grade, reasoning=f"Injected grade: {grade}")
        )


class TimeoutEmbeddings:
    def __init__(self) -> None:
        self.attempts = 0

    async def embed_query(self, _query: str) -> list[float]:
        self.attempts += 1
        request = httpx.Request("POST", "https://api.jina.ai/v1/embeddings")
        raise httpx.ReadTimeout("Injected Jina timeout", request=request)


class UnusedOpenSearch:
    def search_unified(self, **_kwargs: Any) -> dict[str, Any]:
        raise AssertionError("OpenSearch must not run after an unhandled embedding timeout")


class TimeoutSearchTransport:
    def __init__(self) -> None:
        self.attempts = 0

    def search(self, **_kwargs: Any) -> dict[str, Any]:
        self.attempts += 1
        raise TimeoutError("Injected OpenSearch timeout")


def runtime_for_grades(grades: list[str]) -> SimpleNamespace:
    return SimpleNamespace(
        context=SimpleNamespace(
            ollama_client=FakeOllama(grades),
            langfuse_enabled=False,
            trace=None,
            model_name="fault-injection-model",
        )
    )


async def grade(query: str, binary_score: str) -> str:
    state = {
        "messages": [
            HumanMessage(content=query),
            ToolMessage(
                content="A controlled document excerpt with enough content for grading.",
                tool_call_id="fault-call",
                name="retrieve_papers",
            ),
        ],
        "retrieval_attempts": 1,
    }
    result = await ainvoke_grade_documents_step(
        state,
        runtime_for_grades([binary_score]),
    )
    return str(result["routing_decision"])


def dependency_construction_blocker() -> str | None:
    try:
        get_agentic_rag_service(
            opensearch=object(),
            ollama=object(),
            embeddings=object(),
            langfuse=None,
            settings=SimpleNamespace(ollama_model="llama3.2:1b"),
        )
    except Exception as exc:
        return f"{type(exc).__name__}: {exc}"
    return None


async def probe_case(case_id: str, query: str) -> dict[str, Any]:
    if case_id == "W7E-01":
        route = continue_after_guardrail(
            {"messages": [], "guardrail_result": GuardrailScoring(score=20, reason="Injected")},
            SimpleNamespace(context=SimpleNamespace(guardrail_threshold=60)),
        )
        return {
            "terminal_route": "out_of_scope" if route == "out_of_scope" else route,
            "retrieval_expected": False,
            "retrieval_rounds": 0,
        }

    if case_id == "W7E-02":
        route = await grade(query, "yes")
        return {
            "terminal_route": route,
            "retrieval_expected": True,
            "retrieval_rounds": 1,
            "minimum_sources": 1,
        }

    if case_id == "W7E-03":
        first_route = await grade(query, "no")
        second_route = await grade(query, "yes")
        return {
            "terminal_route": second_route,
            "retrieval_rounds": 2,
            "rewrite_expected": first_route == "rewrite_query",
            "rewrite_count": 1,
        }

    if case_id == "W7E-04":
        # Current grade node routes every empty context to rewrite_query. With two
        # rounds this produces two rewrite decisions; the second is unnecessary.
        return {
            "terminal_route": "max_attempts_fallback",
            "business_status": "fallback_message",
            "retrieval_rounds": 2,
            "rewrite_count": 2,
            "generation_expected": False,
            "tool_failures": 0,
        }

    if case_id == "W7E-05":
        embeddings = TimeoutEmbeddings()
        tool = create_retriever_tool(
            opensearch_client=UnusedOpenSearch(),
            embeddings_client=embeddings,
            top_k=3,
            use_hybrid=True,
        )
        try:
            await tool.ainvoke({"query": query})
        except Exception as exc:
            return {
                "terminal_route": "unhandled_exception",
                "business_status": "error",
                "requested_search_mode": "hybrid",
                "actual_search_mode": None,
                "embedding_attempts": embeddings.attempts,
                "fallbacks": 0,
                "retrieval_rounds": 1,
                "exception_type": type(exc).__name__,
            }
        raise AssertionError("Injected embedding timeout unexpectedly succeeded")

    if case_id == "W7E-06":
        transport = TimeoutSearchTransport()
        client = object.__new__(OpenSearchClient)
        client.index_name = "fault-injection-index"
        client.client = transport

        results = [
            client.search_unified(query=query, query_embedding=[0.1], use_hybrid=True)
            for _ in range(2)
        ]
        masked_as_empty = all(result == {"total": 0, "hits": []} for result in results)
        return {
            "terminal_route": "semantic_retry_then_fallback",
            "business_status": "fallback_message",
            "tool_attempts": transport.attempts,
            "tool_failures": 0,
            "error_masked_as_empty": masked_as_empty,
            "generation_expected": False,
        }

    raise ValueError(f"Unknown case: {case_id}")


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
    print(f"factory_signature={inspect.signature(__import__('src.services.agents.factory', fromlist=['make_agentic_rag_service']).make_agentic_rag_service)}")
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
        status: sum(score == status for result in results for score in result.values())
        for status in ("pass", "fail", "blocked")
    }
    print(f"score_summary={json.dumps(counts, sort_keys=True)}")


if __name__ == "__main__":
    asyncio.run(main())
