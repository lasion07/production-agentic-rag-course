import logging

from fastapi import APIRouter, Request
from src.api_errors import PUBLIC_ERROR_RESPONSES, PublicAPIError
from src.dependencies import AgenticRAGDep, LangfuseDep
from src.schemas.api.ask import AgenticAskResponse, AskRequest, FeedbackRequest, FeedbackResponse
from src.security import APIIdentityDep, record_trace_owner, verify_trace_owner

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["agentic-rag"], responses=PUBLIC_ERROR_RESPONSES)


@router.post("/ask-agentic", response_model=AgenticAskResponse)
async def ask_agentic(
    request: AskRequest,
    http_request: Request,
    agentic_rag: AgenticRAGDep,
    identity: APIIdentityDep,
) -> AgenticAskResponse:
    """
    Agentic RAG endpoint with intelligent retrieval and query refinement.

    Features:
    - Decides if retrieval is needed
    - Grades document relevance
    - Rewrites queries if needed
    - Provides reasoning transparency

    The agent will automatically:
    1. Determine if the question requires research paper retrieval
    2. If needed, search for relevant papers
    3. Grade retrieved documents for relevance
    4. Rewrite the query if documents aren't relevant
    5. Generate an answer with citations

    Args:
        request: Question and parameters
        agentic_rag: Injected agentic RAG service

    Returns:
        Answer with sources and reasoning steps

    Raises:
        HTTPException: If processing fails
    """
    try:
        result = await agentic_rag.ask(
            query=request.query,
            model=request.model,
            top_k=request.top_k,
            use_hybrid=request.use_hybrid,
            categories=request.categories,
            user_id=identity.user_id,
        )

        if result.get("business_status") == "retrieval_unavailable":
            raise PublicAPIError(
                status_code=503,
                code="retrieval_unavailable",
                message=result.get("answer", "Retrieval is temporarily unavailable."),
            )
        if result.get("business_status") == "deadline_exceeded":
            raise PublicAPIError(
                status_code=504,
                code="deadline_exceeded",
                message=result.get("answer", "The request deadline was exceeded."),
            )

        response = AgenticAskResponse(
            query=result["query"],
            answer=result["answer"],
            sources=result.get("sources", []),
            chunks_used=result.get("chunks_used", len(result.get("sources", []))),
            search_mode=result.get("actual_search_mode", "none"),
            reasoning_steps=result.get("reasoning_steps", []),
            retrieval_attempts=result.get("retrieval_attempts", 0),
            trace_id=result.get("trace_id"),
            rewritten_query=result.get("rewritten_query"),
            business_status=result.get("business_status", "success"),
            requested_search_mode=result.get("requested_search_mode", "hybrid" if request.use_hybrid else "bm25"),
            embedding_attempts=result.get("embedding_attempts", 0),
            tool_attempts=result.get("tool_attempts", 0),
            tool_failures=result.get("tool_failures", 0),
            fallbacks=result.get("fallbacks", 0),
        )
        await record_trace_owner(http_request, identity, response.trace_id)
        return response

    except PublicAPIError:
        raise
    except ValueError as exc:
        logger.info("Agentic request rejected: %s", type(exc).__name__)
        raise PublicAPIError(422, "invalid_request", "The request parameters are invalid.") from exc
    except Exception as exc:
        logger.exception("Agentic request failed request_id=%s", getattr(http_request.state, "request_id", "unknown"))
        raise PublicAPIError(500, "internal_error", "The request could not be completed.") from exc


@router.post("/feedback", response_model=FeedbackResponse)
async def submit_feedback(
    request: FeedbackRequest,
    http_request: Request,
    langfuse_tracer: LangfuseDep,
    identity: APIIdentityDep,
) -> FeedbackResponse:
    """
    Submit user feedback for an agentic RAG response.

    This endpoint allows users to rate the quality of answers and provide
    optional comments. Feedback is tracked in Langfuse for continuous improvement.

    Args:
        request: Feedback data including trace_id, score, and optional comment
        langfuse_tracer: Injected Langfuse tracer service

    Returns:
        FeedbackResponse indicating success or failure

    Raises:
        HTTPException: If feedback submission fails
    """
    try:
        await verify_trace_owner(http_request, identity, request.trace_id)
        if not langfuse_tracer:
            raise PublicAPIError(503, "observability_unavailable", "Feedback is temporarily unavailable.")

        success = langfuse_tracer.submit_feedback(
            trace_id=request.trace_id,
            score=request.score,
            comment=request.comment,
        )

        if success:
            # Flush to ensure feedback is sent immediately
            langfuse_tracer.flush()

            return FeedbackResponse(success=True, message="Feedback recorded successfully")
        else:
            raise PublicAPIError(503, "feedback_unavailable", "Feedback is temporarily unavailable.")

    except PublicAPIError:
        raise
    except Exception as exc:
        logger.exception("Feedback submission failed request_id=%s", getattr(http_request.state, "request_id", "unknown"))
        raise PublicAPIError(500, "internal_error", "Feedback could not be submitted.") from exc
