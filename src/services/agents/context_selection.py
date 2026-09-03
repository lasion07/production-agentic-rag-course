"""Deterministic candidate reranking and diversity-aware context selection."""

from __future__ import annotations

import re
from typing import Iterable

from langchain_core.documents import Document

_TOKEN_PATTERN = re.compile(r"[a-z0-9]+")
_PERCENT_PATTERN = re.compile(r"\b\d+(?:\.\d+)?\s*%")
_PERCENT_RANGE_PATTERN = re.compile(
    r"\b\d+(?:\.\d+)?\s*(?:-|–|—|to)\s*\d+(?:\.\d+)?\s*%",
    re.IGNORECASE,
)
_QUANTITATIVE_MARKERS = {
    "accuracy",
    "how many",
    "how much",
    "percent",
    "percentage",
    "range",
    "rate",
    "score",
}
_STOP_WORDS = {
    "and",
    "does",
    "for",
    "from",
    "how",
    "is",
    "it",
    "of",
    "the",
    "this",
    "to",
    "what",
}


def _terms(text: str) -> set[str]:
    return {token for token in _TOKEN_PATTERN.findall(text.lower()) if token not in _STOP_WORDS}


def _jaccard(left: set[str], right: set[str]) -> float:
    union = left | right
    return len(left & right) / len(union) if union else 0.0


def _quantitative_intent(query: str) -> bool:
    normalized = query.lower()
    return any(marker in normalized for marker in _QUANTITATIVE_MARKERS)


def _quantitative_evidence_score(query: str, text: str) -> float:
    if not _quantitative_intent(query):
        return 0.0
    if _PERCENT_RANGE_PATTERN.search(text):
        return 1.0
    if _PERCENT_PATTERN.search(text):
        return 0.5
    return 0.0


def select_context_documents(
    query: str,
    candidates: Iterable[Document],
    final_k: int,
    diversity_weight: float = 0.35,
) -> list[Document]:
    """Select final evidence using retrieval rank, lexical coverage and diversity.

    Numeric evidence receives a generic boost only when the query has a
    quantitative intent. Selection is deterministic and never invents evidence.
    """

    candidate_list = list(candidates)
    if final_k <= 0 or not candidate_list:
        return []

    query_terms = _terms(query)
    scored: list[tuple[int, Document, set[str], float]] = []
    for rank, document in enumerate(candidate_list, start=1):
        document_terms = _terms(document.page_content)
        lexical_coverage = len(query_terms & document_terms) / len(query_terms) if query_terms else 0.0
        retrieval_rank_score = 1.0 / rank
        quantitative_score = _quantitative_evidence_score(query, document.page_content)
        relevance = 0.35 * retrieval_rank_score + 0.45 * lexical_coverage + 0.40 * quantitative_score
        scored.append((rank, document, document_terms, relevance))

    selected: list[Document] = []
    selected_terms: list[set[str]] = []
    remaining = scored
    while remaining and len(selected) < final_k:
        def utility(item: tuple[int, Document, set[str], float]) -> tuple[float, int]:
            rank, _document, terms, relevance = item
            redundancy = max((_jaccard(terms, chosen) for chosen in selected_terms), default=0.0)
            return relevance - diversity_weight * redundancy, -rank

        best = max(remaining, key=utility)
        rank, document, terms, relevance = best
        document.metadata = {
            **document.metadata,
            "candidate_rank": rank,
            "selection_score": round(utility(best)[0], 6),
            "reranked": True,
        }
        selected.append(document)
        selected_terms.append(terms)
        remaining = [item for item in remaining if item is not best]

    return selected
