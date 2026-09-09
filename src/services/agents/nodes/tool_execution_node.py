import json
from typing import Literal

from langchain_core.messages import ToolMessage
from langgraph.runtime import Runtime

from ..context import Context
from ..state import AgentState
from ..tools import execute_retrieval
from .utils import get_latest_query


async def ainvoke_tool_retrieve_step(state: AgentState, runtime: Runtime[Context]) -> dict:
    """Execute retrieval and expose a structured outcome to the graph."""

    query = get_latest_query(state["messages"])
    outcome = await execute_retrieval(
        query=query,
        opensearch_client=runtime.context.opensearch_client,
        embeddings_client=runtime.context.embeddings_client,
        top_k=runtime.context.top_k,
        use_hybrid=runtime.context.use_hybrid,
        categories=runtime.context.categories,
        max_embedding_attempts=runtime.context.max_embedding_attempts,
        max_search_attempts=runtime.context.max_search_attempts,
        embedding_attempt_timeout_seconds=runtime.context.embedding_attempt_timeout_seconds,
        search_attempt_timeout_seconds=runtime.context.search_attempt_timeout_seconds,
        deadline_monotonic=runtime.context.deadline_monotonic,
        generation_reserve_seconds=runtime.context.generation_reserve_seconds,
    )
    tool_call_id = f"retrieve_{state.get('retrieval_attempts', 0)}"
    if outcome.documents:
        content = "\n\n".join(document.page_content for document in outcome.documents)
    elif outcome.status == "error":
        content = json.dumps(
            {"status": outcome.status, "error_type": outcome.error_type},
            sort_keys=True,
        )
    else:
        content = ""

    updates = {
        "messages": [ToolMessage(content=content, tool_call_id=tool_call_id, name="retrieve_papers")],
        "retrieved_documents": outcome.documents,
        "tool_status": outcome.status,
        "requested_search_mode": outcome.requested_search_mode,
        "actual_search_mode": outcome.actual_search_mode,
        "embedding_attempts": state.get("embedding_attempts", 0) + outcome.embedding_attempts,
        "tool_attempts": state.get("tool_attempts", 0) + outcome.tool_attempts,
        "tool_failures": state.get("tool_failures", 0) + outcome.tool_failures,
        "fallbacks": state.get("fallbacks", 0) + outcome.fallbacks,
        "retrieval_diagnostics": [
            *state.get("retrieval_diagnostics", []),
            {
                "retrieval_round": state.get("retrieval_attempts", 0),
                "query": query,
                "search_mode": outcome.actual_search_mode,
                **outcome.diagnostics,
            },
        ],
    }
    if outcome.status == "degraded":
        updates["business_status"] = "degraded"
    elif outcome.status == "error":
        updates["business_status"] = "retrieval_unavailable"
        updates["routing_decision"] = "retrieval_unavailable"
        updates["metadata"] = {"retrieval_error_type": outcome.error_type}
    return updates


def route_after_tool(state: AgentState) -> Literal["grade_documents", "retrieval_unavailable"]:
    """Never allow an error ToolMessage to enter document grading."""

    return "retrieval_unavailable" if state.get("tool_status") == "error" else "grade_documents"
