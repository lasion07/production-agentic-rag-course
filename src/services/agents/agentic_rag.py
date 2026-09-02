import asyncio
import logging
import time
from typing import List, Optional

from langchain_core.messages import HumanMessage
from langgraph.graph import END, START, StateGraph
from src.services.embeddings.jina_client import JinaEmbeddingsClient
from src.services.langfuse.client import LangfuseTracer
from src.services.ollama.client import OllamaClient
from src.services.opensearch.client import OpenSearchClient

from .config import GraphConfig
from .context import Context
from .nodes import (
    ainvoke_generate_answer_step,
    ainvoke_grade_documents_step,
    ainvoke_guardrail_step,
    ainvoke_insufficient_evidence_step,
    ainvoke_out_of_scope_step,
    ainvoke_retrieval_unavailable_step,
    ainvoke_retrieve_step,
    ainvoke_rewrite_query_step,
    ainvoke_tool_retrieve_step,
    continue_after_guardrail,
    route_after_grading,
    route_after_retrieve,
    route_after_tool,
)
from .state import AgentState

logger = logging.getLogger(__name__)


class AgenticRAGService:
    """Agentic RAG service

    This implementation uses:
    - context_schema for dependency injection
    - Runtime[Context] for type-safe access in nodes
    - Direct client invocation (no pre-built runnables)
    - Lightweight nodes as pure functions
    """

    def __init__(
        self,
        opensearch_client: OpenSearchClient,
        ollama_client: OllamaClient,
        embeddings_client: JinaEmbeddingsClient,
        langfuse_tracer: Optional[LangfuseTracer] = None,
        graph_config: Optional[GraphConfig] = None,
    ):
        """Initialize agentic RAG service.

        :param opensearch_client: Client for document search
        :param ollama_client: Client for LLM generation
        :param embeddings_client: Client for embeddings
        :param langfuse_tracer: Optional Langfuse tracer
        :param graph_config: Configuration for graph execution
        """
        self.opensearch = opensearch_client
        self.ollama = ollama_client
        self.embeddings = embeddings_client
        self.langfuse_tracer = langfuse_tracer
        self.graph_config = graph_config or GraphConfig()

        logger.info("Initializing AgenticRAGService with configuration:")
        logger.info(f"  Model: {self.graph_config.model}")
        logger.info(f"  Top-k: {self.graph_config.top_k}")
        logger.info(f"  Hybrid search: {self.graph_config.use_hybrid}")
        logger.info(f"  Max retrieval attempts: {self.graph_config.max_retrieval_attempts}")
        logger.info(f"  Guardrail threshold: {self.graph_config.guardrail_threshold}")

        # Build graph once (no runnables needed!)
        self.graph = self._build_graph()
        logger.info("✓ AgenticRAGService initialized successfully")

    def _build_graph(self):
        """Build and compile the LangGraph workflow.

        Uses context_schema for type-safe dependency injection.
        Nodes are lightweight functions that receive Runtime[Context].

        :returns: Compiled graph ready for invocation
        """
        logger.info("Building LangGraph workflow with context_schema")

        # Create workflow with AgentState and Context schema
        workflow = StateGraph(AgentState, context_schema=Context)

        # Add nodes (just function references - no closures needed!)
        logger.info("Adding nodes to workflow graph")
        workflow.add_node("guardrail", ainvoke_guardrail_step)
        workflow.add_node("out_of_scope", ainvoke_out_of_scope_step)
        workflow.add_node("retrieve", ainvoke_retrieve_step)
        workflow.add_node("tool_retrieve", ainvoke_tool_retrieve_step)
        workflow.add_node("grade_documents", ainvoke_grade_documents_step)
        workflow.add_node("rewrite_query", ainvoke_rewrite_query_step)
        workflow.add_node("generate_answer", ainvoke_generate_answer_step)
        workflow.add_node("insufficient_evidence", ainvoke_insufficient_evidence_step)
        workflow.add_node("retrieval_unavailable", ainvoke_retrieval_unavailable_step)

        # Add edges
        logger.info("Configuring graph edges and routing logic")

        # Start → guardrail validation
        workflow.add_edge(START, "guardrail")

        # Guardrail → route based on score
        workflow.add_conditional_edges(
            "guardrail",
            continue_after_guardrail,
            {
                "continue": "retrieve",
                "out_of_scope": "out_of_scope",
            },
        )

        # Out of scope → END
        workflow.add_edge("out_of_scope", END)

        # Retrieve node creates tool call
        workflow.add_conditional_edges(
            "retrieve",
            route_after_retrieve,
            {
                "tool_retrieve": "tool_retrieve",
                "insufficient_evidence": "insufficient_evidence",
            },
        )

        workflow.add_conditional_edges(
            "tool_retrieve",
            route_after_tool,
            {
                "grade_documents": "grade_documents",
                "retrieval_unavailable": "retrieval_unavailable",
            },
        )

        # After grading → route based on relevance
        workflow.add_conditional_edges(
            "grade_documents",
            route_after_grading,
            {
                "generate_answer": "generate_answer",
                "rewrite_query": "rewrite_query",
                "insufficient_evidence": "insufficient_evidence",
            },
        )

        # After rewriting → try retrieve again
        workflow.add_edge("rewrite_query", "retrieve")

        # After answer generation → done
        workflow.add_edge("generate_answer", END)
        workflow.add_edge("insufficient_evidence", END)
        workflow.add_edge("retrieval_unavailable", END)

        # Compile graph
        logger.info("Compiling LangGraph workflow")
        compiled_graph = workflow.compile()
        logger.info("✓ Graph compilation successful")

        return compiled_graph

    async def ask(
        self,
        query: str,
        user_id: str = "api_user",
        model: Optional[str] = None,
        top_k: Optional[int] = None,
        use_hybrid: Optional[bool] = None,
        categories: Optional[List[str]] = None,
    ) -> dict:
        """Ask a question using agentic RAG.

        :param query: User question
        :param user_id: User identifier for tracing
        :param model: Optional model override
        :returns: Dictionary with answer, sources, reasoning steps, and metadata
        :raises ValueError: If query is empty
        """
        model_to_use = model or self.graph_config.model
        effective_top_k = top_k if top_k is not None else self.graph_config.top_k
        effective_use_hybrid = use_hybrid if use_hybrid is not None else self.graph_config.use_hybrid

        logger.info("=" * 80)
        logger.info("Starting Agentic RAG Request")
        logger.info(f"Query: {query}")
        logger.info(f"User ID: {user_id}")
        logger.info(f"Model: {model_to_use}")
        logger.info("=" * 80)

        # Validate input
        if not query or len(query.strip()) == 0:
            logger.error("Empty query received")
            raise ValueError("Query cannot be empty")

        try:
            if self.langfuse_tracer:
                metadata = {
                    "environment": self.graph_config.settings.environment,
                    "service": "agentic-rag",
                    "user_id": user_id,
                    "top_k": effective_top_k,
                    "use_hybrid": effective_use_hybrid,
                    "categories": categories,
                    "model": model_to_use,
                }
                with self.langfuse_tracer.trace_attributes(
                    user_id=user_id,
                    session_id=f"session-{user_id}",
                    trace_name="agentic-rag-request",
                    tags=["agentic-rag"],
                ):
                    with self.langfuse_tracer.start_span(
                        name="agentic-rag-request",
                        as_type="agent",
                        input_data={"query": self.langfuse_tracer.safe_content(query)},
                        metadata=metadata,
                    ) as trace:
                        return await self._run_workflow(query, model_to_use, user_id, trace, top_k, use_hybrid, categories)
            return await self._run_workflow(query, model_to_use, user_id, None, top_k, use_hybrid, categories)
        except Exception as e:
            logger.error(f"Error in Agentic RAG execution: {str(e)}")
            logger.exception("Full traceback:")
            raise

    async def _run_workflow(
        self,
        query: str,
        model_to_use: str,
        user_id: str,
        trace,
        top_k: Optional[int],
        use_hybrid: Optional[bool],
        categories: Optional[List[str]],
    ) -> dict:
        """Execute the workflow with the given trace context."""
        try:
            start_time = time.time()

            logger.info("Invoking LangGraph workflow")

            # State initialization
            state_input = {
                "messages": [HumanMessage(content=query)],
                "retrieval_attempts": 0,
                "guardrail_result": None,
                "routing_decision": None,
                "retrieved_documents": [],
                "relevant_documents": [],
                "sources": None,
                "relevant_sources": [],
                "relevant_tool_artefacts": None,
                "grading_results": [],
                "metadata": {},
                "original_query": None,
                "rewritten_query": None,
                "tool_status": None,
                "requested_search_mode": "hybrid"
                if (use_hybrid if use_hybrid is not None else self.graph_config.use_hybrid)
                else "bm25",
                "actual_search_mode": "none",
                "business_status": None,
                "terminal_route": None,
                "embedding_attempts": 0,
                "tool_attempts": 0,
                "tool_failures": 0,
                "fallbacks": 0,
            }

            effective_top_k = top_k if top_k is not None else self.graph_config.top_k
            effective_use_hybrid = use_hybrid if use_hybrid is not None else self.graph_config.use_hybrid

            # Runtime context (dependencies)
            runtime_context = Context(
                ollama_client=self.ollama,
                opensearch_client=self.opensearch,
                embeddings_client=self.embeddings,
                langfuse_tracer=self.langfuse_tracer,
                trace=trace,
                langfuse_enabled=self.langfuse_tracer is not None and self.langfuse_tracer.client is not None,
                model_name=model_to_use,
                temperature=self.graph_config.temperature,
                top_k=effective_top_k,
                use_hybrid=effective_use_hybrid,
                categories=categories,
                max_retrieval_attempts=self.graph_config.max_retrieval_attempts,
                max_embedding_attempts=self.graph_config.max_embedding_attempts,
                max_search_attempts=self.graph_config.max_search_attempts,
                embedding_attempt_timeout_seconds=self.graph_config.embedding_attempt_timeout_seconds,
                search_attempt_timeout_seconds=self.graph_config.search_attempt_timeout_seconds,
                deadline_monotonic=time.monotonic() + self.graph_config.total_deadline_seconds,
                generation_reserve_seconds=self.graph_config.generation_reserve_seconds,
                guardrail_threshold=self.graph_config.guardrail_threshold,
            )

            # Callback observations automatically inherit the current trace.
            config = {"thread_id": f"user_{user_id}_session_{int(time.time())}"}

            if self.langfuse_tracer and trace:
                try:
                    callback_handler = self.langfuse_tracer.get_callback_handler()
                    if callback_handler:
                        config["callbacks"] = [callback_handler]
                        logger.info("✓ Langfuse CallbackHandler added")
                except Exception as e:
                    logger.warning(f"Failed to create CallbackHandler: {e}")

            try:
                result = await asyncio.wait_for(
                    self.graph.ainvoke(
                        state_input,
                        config=config,
                        context=runtime_context,
                    ),
                    timeout=self.graph_config.total_deadline_seconds,
                )
            except TimeoutError:
                execution_time = time.time() - start_time
                if trace:
                    trace.update(
                        output={"business_status": "deadline_exceeded"},
                        level="ERROR",
                        status_message="Agent request deadline exceeded",
                    )
                return {
                    "query": query,
                    "answer": "The request exceeded its processing deadline. Please try again.",
                    "sources": [],
                    "reasoning_steps": ["Stopped because the total request deadline was exceeded"],
                    "retrieval_attempts": 0,
                    "rewritten_query": None,
                    "execution_time": execution_time,
                    "guardrail_score": None,
                    "business_status": "deadline_exceeded",
                    "terminal_route": "deadline_exceeded",
                    "requested_search_mode": "hybrid" if effective_use_hybrid else "bm25",
                    "actual_search_mode": "none",
                    "chunks_used": 0,
                    "embedding_attempts": 0,
                    "tool_attempts": 0,
                    "tool_failures": 0,
                    "fallbacks": 0,
                    "trace_id": getattr(trace, "id", None) if trace else None,
                }

            execution_time = time.time() - start_time
            logger.info(f"✓ Graph execution completed in {execution_time:.2f}s")

            # Extract results
            answer = self._extract_answer(result)
            sources = self._extract_sources(result)
            retrieval_attempts = result.get("retrieval_attempts", 0)
            reasoning_steps = self._extract_reasoning_steps(result)

            # Update trace (cleanup handled by context manager)
            if trace:
                trace.update(
                    output={
                        "answer": self.langfuse_tracer.safe_content(answer),
                        "sources_count": len(sources),
                        "retrieval_attempts": retrieval_attempts,
                        "reasoning_steps": reasoning_steps,
                        "execution_time": execution_time,
                    }
                )

            logger.info("=" * 80)
            logger.info("Agentic RAG Request Completed Successfully")
            logger.info(f"Answer length: {len(answer)} characters")
            logger.info(f"Sources found: {len(sources)}")
            logger.info(f"Retrieval attempts: {retrieval_attempts}")
            logger.info(f"Execution time: {execution_time:.2f}s")
            logger.info("=" * 80)

            return {
                "query": query,
                "answer": answer,
                "sources": sources,
                "reasoning_steps": reasoning_steps,
                "retrieval_attempts": retrieval_attempts,
                "rewritten_query": result.get("rewritten_query"),
                "execution_time": execution_time,
                "guardrail_score": result.get("guardrail_result").score if result.get("guardrail_result") else None,
                "business_status": result.get("business_status") or "success",
                "terminal_route": result.get("terminal_route"),
                "requested_search_mode": result.get("requested_search_mode"),
                "actual_search_mode": result.get("actual_search_mode", "none"),
                "chunks_used": len(result.get("relevant_documents", [])),
                "embedding_attempts": result.get("embedding_attempts", 0),
                "tool_attempts": result.get("tool_attempts", 0),
                "tool_failures": result.get("tool_failures", 0),
                "fallbacks": result.get("fallbacks", 0),
                "trace_id": getattr(trace, "id", None) if trace else None,
            }

        except Exception as e:
            logger.error(f"Error in workflow execution: {str(e)}")
            logger.exception("Full traceback:")

            # Update trace with error (cleanup handled by context manager)
            if trace:
                trace.update(
                    output={"error_type": type(e).__name__},
                    level="ERROR",
                    status_message=str(e)[:500],
                )

            raise

    def _extract_answer(self, result: dict) -> str:
        """Extract final answer from graph result."""
        messages = result.get("messages", [])
        if not messages:
            return "No answer generated."

        final_message = messages[-1]
        return final_message.content if hasattr(final_message, "content") else str(final_message)

    def _extract_sources(self, result: dict) -> List[str]:
        """Extract sources from graph result."""
        sources = []
        relevant_sources = result.get("relevant_sources", [])

        for source in relevant_sources:
            if hasattr(source, "url") and source.url:
                sources.append(source.url)
            elif isinstance(source, dict) and source.get("url"):
                sources.append(source["url"])

        return sources

    def _extract_reasoning_steps(self, result: dict) -> List[str]:
        """Extract reasoning steps from graph result."""
        steps = []
        retrieval_attempts = result.get("retrieval_attempts", 0)
        guardrail_result = result.get("guardrail_result")
        grading_results = result.get("grading_results", [])

        if guardrail_result:
            steps.append(f"Validated query scope (score: {guardrail_result.score}/100)")

        if retrieval_attempts > 0:
            steps.append(f"Retrieved documents ({retrieval_attempts} attempt(s))")

        if grading_results:
            relevant_count = sum(1 for g in grading_results if g.is_relevant)
            steps.append(f"Graded documents ({relevant_count} relevant)")

        if result.get("rewritten_query"):
            steps.append("Rewritten query for better results")

        if result.get("terminal_route") == "generate_answer":
            steps.append("Generated answer from context")

        return steps

    def get_graph_visualization(self) -> bytes:
        """Get the LangGraph workflow visualization as PNG.

        This method generates a visual representation of the graph workflow
        using mermaid diagram format, then converts it to PNG.

        :returns: PNG image bytes
        :raises ImportError: If required dependencies (pygraphviz/graphviz) are not installed
        :raises Exception: If graph visualization generation fails

        Example:
            >>> service = AgenticRAGService(...)
            >>> png_bytes = service.get_graph_visualization()
            >>> with open("graph.png", "wb") as f:
            ...     f.write(png_bytes)
        """
        try:
            logger.info("Generating graph visualization as PNG")
            png_bytes = self.graph.get_graph().draw_mermaid_png()
            logger.info(f"✓ Generated PNG visualization ({len(png_bytes)} bytes)")
            return png_bytes
        except ImportError as e:
            logger.error(f"Failed to generate visualization - missing dependencies: {e}")
            logger.error("Install with: pip install pygraphviz or apt-get install graphviz")
            raise ImportError(
                "Graph visualization requires pygraphviz. Install with: pip install pygraphviz (requires graphviz system package)"
            ) from e
        except Exception as e:
            logger.error(f"Failed to generate graph visualization: {e}")
            raise

    def get_graph_mermaid(self) -> str:
        """Get the LangGraph workflow as a mermaid diagram string.

        This method generates the graph workflow representation in mermaid
        diagram syntax, which can be rendered in markdown or mermaid viewers.

        :returns: Mermaid diagram syntax as string

        Example:
            >>> service = AgenticRAGService(...)
            >>> mermaid = service.get_graph_mermaid()
            >>> print(mermaid)
            graph TD
                __start__ --> guardrail
                ...
        """
        try:
            logger.info("Generating graph as mermaid diagram")
            mermaid_str = self.graph.get_graph().draw_mermaid()
            logger.info(f"✓ Generated mermaid diagram ({len(mermaid_str)} characters)")
            return mermaid_str
        except Exception as e:
            logger.error(f"Failed to generate mermaid diagram: {e}")
            raise

    def get_graph_ascii(self) -> str:
        """Get ASCII representation of the graph.

        This method generates a simple ASCII art representation of the
        graph structure, useful for quick inspection in terminals.

        :returns: ASCII art representation of the graph

        Example:
            >>> service = AgenticRAGService(...)
            >>> print(service.get_graph_ascii())
        """
        try:
            logger.info("Generating ASCII graph representation")
            ascii_str = self.graph.get_graph().print_ascii()
            logger.info("✓ Generated ASCII graph representation")
            return ascii_str
        except Exception as e:
            logger.error(f"Failed to generate ASCII graph: {e}")
            raise
