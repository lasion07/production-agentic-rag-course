"""Deterministic citation allowlist and quantitative-claim validation."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Iterable

from langchain_core.documents import Document

_CITATION_PATTERN = re.compile(r"\[arXiv:([^\]]+)\]", re.IGNORECASE)
_VERSION_SUFFIX = re.compile(r"v\d+$", re.IGNORECASE)
_DECIMAL_PATTERN = re.compile(r"\b\d+\.\d+\b")
_PERCENT_RANGE_PATTERN = re.compile(
    r"\b(\d+(?:\.\d+)?)\s*(?:-|–|—|to)\s*(\d+(?:\.\d+)?)\s*(?:%|percent)",
    re.IGNORECASE,
)
_MEASURED_VALUE_PATTERN = re.compile(
    r"\b(\d+(?:\.\d+)?)\s*[- ]?(?:%|percent|million|billion|thousand)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class GroundingValidation:
    """Result of deterministic post-generation grounding checks."""

    valid: bool
    citations: tuple[str, ...]
    invalid_citations: tuple[str, ...]
    unsupported_numeric_claims: tuple[str, ...]
    missing_citation: bool


def _canonical_arxiv_id(value: str) -> str:
    normalized = value.strip().lower()
    normalized = normalized.removeprefix("arxiv:")
    normalized = normalized.removeprefix("https://arxiv.org/abs/")
    normalized = normalized.removeprefix("https://arxiv.org/pdf/")
    normalized = normalized.removesuffix(".pdf")
    return _VERSION_SUFFIX.sub("", normalized)


def allowed_citation_ids(documents: Iterable[Document]) -> tuple[str, ...]:
    """Return the exact non-empty arXiv IDs present in the evidence pool."""

    return tuple(
        dict.fromkeys(
            str(document.metadata.get("arxiv_id", "")).strip()
            for document in documents
            if str(document.metadata.get("arxiv_id", "")).strip()
        )
    )


def format_evidence_context(documents: Iterable[Document]) -> str:
    """Serialize evidence with source identity while keeping document text data-only."""

    payload = [
        {
            "arxiv_id": str(document.metadata.get("arxiv_id", "")),
            "title": str(document.metadata.get("title", "")),
            "section": str(document.metadata.get("section", "")),
            "text": document.page_content,
        }
        for document in documents
    ]
    return json.dumps(payload, ensure_ascii=False)


def _numeric_claims(answer: str) -> set[str]:
    answer_without_citations = _CITATION_PATTERN.sub("", answer)
    claims = set(_DECIMAL_PATTERN.findall(answer_without_citations))
    for lower, upper in _PERCENT_RANGE_PATTERN.findall(answer_without_citations):
        claims.update((lower, upper))
    claims.update(_MEASURED_VALUE_PATTERN.findall(answer_without_citations))
    return claims


def validate_grounded_answer(
    answer: str,
    documents: Iterable[Document],
) -> GroundingValidation:
    """Validate citation membership and measured values against retrieved evidence.

    This deliberately does not claim semantic entailment. It catches two
    deterministic failure classes: citations outside the evidence allowlist and
    decimal/percentage/magnitude values absent from the evidence text.
    """

    document_list = list(documents)
    exact_allowed_ids = allowed_citation_ids(document_list)
    canonical_allowed_ids = {_canonical_arxiv_id(value) for value in exact_allowed_ids}
    citations = tuple(match.strip() for match in _CITATION_PATTERN.findall(answer))
    invalid_citations = tuple(
        citation
        for citation in citations
        if _canonical_arxiv_id(citation) not in canonical_allowed_ids
    )
    evidence_text = "\n".join(document.page_content for document in document_list)
    evidence_numbers = set(re.findall(r"\b\d+(?:\.\d+)?\b", evidence_text.replace(",", "")))
    unsupported_numeric_claims = tuple(
        sorted(value for value in _numeric_claims(answer.replace(",", "")) if value not in evidence_numbers)
    )
    missing_citation = bool(exact_allowed_ids) and not citations
    valid = not (invalid_citations or unsupported_numeric_claims or missing_citation)
    return GroundingValidation(
        valid=valid,
        citations=citations,
        invalid_citations=invalid_citations,
        unsupported_numeric_claims=unsupported_numeric_claims,
        missing_citation=missing_citation,
    )
