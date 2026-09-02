from langchain_core.messages import AIMessage

from ..state import AgentState


async def ainvoke_insufficient_evidence_step(state: AgentState) -> dict:
    return {
        "messages": [AIMessage(content="I could not find sufficient evidence in the indexed papers to answer reliably.")],
        "business_status": "insufficient_evidence",
        "terminal_route": "insufficient_evidence",
        "relevant_documents": [],
        "relevant_sources": [],
    }


async def ainvoke_retrieval_unavailable_step(state: AgentState) -> dict:
    return {
        "messages": [AIMessage(content="Paper retrieval is temporarily unavailable. Please try again later.")],
        "business_status": "retrieval_unavailable",
        "terminal_route": "retrieval_unavailable",
        "relevant_documents": [],
        "relevant_sources": [],
        "actual_search_mode": "none",
    }
