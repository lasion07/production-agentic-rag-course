import asyncio
import logging
import time
from typing import Dict, List

from langchain_core.messages import AIMessage
from langgraph.runtime import Runtime

from ..context import Context
from ..grounding import allowed_citation_ids, format_evidence_context, validate_grounded_answer
from ..prompts import GENERATE_ANSWER_PROMPT
from ..state import AgentState
from .utils import get_latest_context, get_latest_query

logger = logging.getLogger(__name__)


async def ainvoke_generate_answer_step(
    state: AgentState,
    runtime: Runtime[Context],
) -> Dict[str, List[AIMessage]]:
    """Generate final answer using retrieved documents.

    This node generates a comprehensive answer to the
    user's question based on the retrieved context using an LLM.

    :param state: Current agent state
    :param runtime: Runtime context
    :returns: Dictionary with messages containing the generated answer
    """
    logger.info("NODE: generate_answer")
    start_time = time.time()

    # Get question and context
    question = get_latest_query(state["messages"])
    context = get_latest_context(state["messages"])
    relevant_documents = state.get("relevant_documents", [])
    if relevant_documents:
        context = format_evidence_context(relevant_documents)
    citation_allowlist = allowed_citation_ids(relevant_documents)

    # Count sources from relevant_sources
    sources_count = len(state.get("relevant_sources", []))

    if not context:
        context = "No relevant documents found."
        logger.warning("No context available for answer generation")

    logger.debug(f"Generating answer for query: {question[:100]}...")
    logger.debug(f"Using context of length: {len(context)} characters")

    # Extract document chunks preview for logging
    chunks_preview = []
    if context:
        context_preview = context[:1000] + "..." if len(context) > 1000 else context
        chunks_preview = [{"text_preview": context_preview, "length": len(context)}]

    # Create span for answer generation
    span = None
    if runtime.context.langfuse_enabled and runtime.context.trace:
        try:
            span = runtime.context.langfuse_tracer.create_span(
                trace=runtime.context.trace,
                name="answer_generation",
                input_data={
                    "query": question,
                    "context_length": len(context),
                    "sources_count": sources_count,
                    "chunks_used": chunks_preview,
                },
                metadata={
                    "node": "generate_answer",
                    "model": runtime.context.model_name,
                    "temperature": runtime.context.temperature,
                },
                # The LangChain callback records the actual model invocation as
                # a GENERATION (with authoritative token/cost usage). Keep this
                # wrapper as a CHAIN so Langfuse does not double-count it.
                as_type="chain",
            )
            logger.debug("Created Langfuse span for answer generation")
        except Exception as e:
            logger.warning(f"Failed to create span for generate_answer node: {e}")

    try:
        # Create answer generation prompt from template
        answer_prompt = GENERATE_ANSWER_PROMPT.format(
            context=context,
            question=question,
        )

        # Get LLM from runtime context
        llm = runtime.context.llm_client.get_langchain_model(
            model=runtime.context.model_name,
            temperature=runtime.context.temperature,
            num_predict=512,
        )

        # Invoke LLM for answer generation
        logger.info("Invoking LLM for answer generation")
        if runtime.context.deadline_monotonic is None:
            response = await llm.ainvoke(answer_prompt)
        else:
            remaining = runtime.context.deadline_monotonic - time.monotonic()
            cleanup_margin_seconds = 10.0
            if remaining <= cleanup_margin_seconds:
                raise TimeoutError("request deadline exhausted before generation")
            response = await asyncio.wait_for(
                llm.ainvoke(answer_prompt),
                timeout=remaining - cleanup_margin_seconds,
            )

        # Extract content from response
        content = response.content if hasattr(response, "content") else response
        if isinstance(content, list):
            # Responses API messages use typed content blocks while the API
            # contract exposes one answer string.
            answer = "".join(
                block.get("text", "") if isinstance(block, dict) else getattr(block, "text", str(block))
                for block in content
            )
        else:
            answer = str(content)
        logger.info(f"Generated answer of length: {len(answer)} characters")

        grounding = validate_grounded_answer(answer, relevant_documents)
        if not grounding.valid:
            logger.warning(
                "Grounding validation failed: invalid_citations=%s unsupported_numeric_claims=%s missing_citation=%s",
                grounding.invalid_citations,
                grounding.unsupported_numeric_claims,
                grounding.missing_citation,
            )
            answer = (
                "I could not produce an answer that passed evidence and citation validation. "
                "Please retry or narrow the question."
            )
            grounding_failed = True

        # Update span with successful result
        if span:
            execution_time = (time.time() - start_time) * 1000
            runtime.context.langfuse_tracer.end_span(
                span,
                output={
                    "answer_length": len(answer),
                    "sources_used": sources_count,
                    "grounding_valid": grounding.valid,
                    "citations": list(grounding.citations),
                    "invalid_citations": list(grounding.invalid_citations),
                    "unsupported_numeric_claims": list(grounding.unsupported_numeric_claims),
                },
                metadata={
                    "execution_time_ms": execution_time,
                    "context_length": len(context),
                    "citation_allowlist": list(citation_allowlist),
                },
            )

    except Exception as e:
        logger.error(f"LLM answer generation failed: {e}, falling back to error message")

        # Fallback to error message if LLM fails
        if isinstance(e, TimeoutError) and context:
            citations = " ".join(f"[arXiv:{arxiv_id}]" for arxiv_id in citation_allowlist)
            answer = (
                "Generation exceeded its time budget. Here is the most relevant retrieved evidence:"
                f"\n\n{context[:1500]}\n\n{citations}"
            )
        else:
            answer = (
                f"I apologize, but I encountered an error while generating the answer: {str(e)}\n\n"
                "Please try again or rephrase your question."
            )
        generation_failed = True

        # Update span with error
        if span:
            execution_time = (time.time() - start_time) * 1000
            runtime.context.langfuse_tracer.update_span(
                span,
                output={"error": str(e), "fallback": True},
                metadata={"execution_time_ms": execution_time},
                level="ERROR",
            )
            runtime.context.langfuse_tracer.end_span(span)

    business_status = state.get("business_status") or "success"
    if "generation_failed" in locals() and business_status == "success":
        business_status = "degraded"
    terminal_route = "generate_answer"
    if "grounding_failed" in locals():
        business_status = "insufficient_evidence"
        terminal_route = "insufficient_evidence"

    return {
        "messages": [AIMessage(content=answer)],
        "business_status": business_status,
        "terminal_route": terminal_route,
    }
