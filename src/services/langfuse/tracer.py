"""Typed Langfuse observations for the serving RAG pipeline."""

import time
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Dict, List, Optional

from .client import LangfuseTracer


class RAGTracer:
    def __init__(self, tracer: LangfuseTracer):
        self.tracer = tracer

    @contextmanager
    def trace_request(self, user_id: str, query: str):
        with self.tracer.trace_attributes(
            user_id=user_id,
            session_id=f"session-{user_id}",
            trace_name="rag-request",
            tags=["serving-rag"],
        ):
            with self.tracer.start_span(
                name="rag-request",
                as_type="chain",
                input_data={"query": self.tracer.safe_content(query)},
                metadata={"pipeline": "serving-rag"},
            ) as trace:
                yield trace

    @contextmanager
    def trace_cache(self, operation: str):
        with self.tracer.start_span(
            name=f"cache-{operation}",
            input_data={"operation": operation},
            metadata={"backend": "redis"},
        ) as span:
            yield span

    def end_cache(self, span: Any, result: str) -> None:
        self.tracer.update_span(
            span,
            output={"result": result},
            level="WARNING" if result == "error" else None,
            status_message="Redis failed; request continued fail-open" if result == "error" else None,
        )

    @contextmanager
    def trace_embedding(self, trace: Any, query: str):
        started = time.perf_counter()
        with self.tracer.start_span(
            name="query-embedding",
            as_type="embedding",
            input_data={"query": self.tracer.safe_content(query), "query_chars": len(query)},
        ) as span:
            try:
                yield span
            finally:
                self.tracer.update_span(
                    span,
                    output={"duration_ms": round((time.perf_counter() - started) * 1000, 2)},
                )

    @contextmanager
    def trace_search(self, trace: Any, query: str, top_k: int):
        with self.tracer.start_span(
            name="search-retrieval",
            as_type="retriever",
            input_data={"query": self.tracer.safe_content(query), "top_k": top_k},
        ) as span:
            yield span

    def end_search(self, span: Any, chunks: List[Dict], arxiv_ids: List[str], total_hits: int) -> None:
        self.tracer.update_span(
            span,
            output={
                "chunks_returned": len(chunks),
                "unique_papers": len(set(arxiv_ids)),
                "total_hits": total_hits,
                "arxiv_ids": sorted(set(arxiv_ids)),
            },
        )

    @contextmanager
    def trace_prompt_construction(self, trace: Any, chunks: List[Dict]):
        with self.tracer.start_span(
            name="prompt-construction",
            as_type="chain",
            input_data={"chunk_count": len(chunks)},
        ) as span:
            yield span

    def end_prompt(self, span: Any, prompt: str) -> None:
        self.tracer.update_span(
            span,
            output={"prompt_chars": len(prompt), "prompt": self.tracer.safe_content(prompt)},
        )

    @contextmanager
    def trace_generation(self, trace: Any, model: str, prompt: str):
        with self.tracer.start_span(
            name="llm-generation",
            as_type="generation",
            model=model,
            model_parameters={"num_predict": 128, "temperature": 0.7, "top_p": 0.9},
            input_data={"prompt": self.tracer.safe_content(prompt), "prompt_chars": len(prompt)},
        ) as span:
            yield span

    def end_generation(
        self,
        span: Any,
        response: str,
        model: str,
        *,
        usage_metadata: Optional[Dict[str, Any]] = None,
        completion_start_time: Optional[datetime] = None,
        finish_reason: Optional[str] = None,
    ) -> None:
        self.tracer.update_generation(
            span,
            output={"answer": self.tracer.safe_content(response), "answer_chars": len(response), "model": model},
            usage_metadata=usage_metadata,
            completion_start_time=completion_start_time,
            finish_reason=finish_reason,
        )

    def end_request(self, trace: Any, response: str, total_duration: float, *, status: str = "ok") -> None:
        self.tracer.update_span(
            trace,
            output={
                "answer": self.tracer.safe_content(response),
                "duration_seconds": round(total_duration, 3),
                "answer_chars": len(response),
                "status": status,
            },
            level="ERROR" if status == "error" else None,
        )

    def mark_error(self, span: Any, error: Exception) -> None:
        self.tracer.update_span(
            span,
            output={"error_type": type(error).__name__},
            level="ERROR",
            status_message=str(error)[:500],
        )
