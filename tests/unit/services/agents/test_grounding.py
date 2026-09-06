from langchain_core.documents import Document
from src.services.agents.grounding import (
    allowed_citation_ids,
    format_evidence_context,
    validate_grounded_answer,
)


def _document(arxiv_id: str, text: str) -> Document:
    return Document(
        page_content=text,
        metadata={"arxiv_id": arxiv_id, "title": "Paper title", "section": "Results"},
    )


def test_context_preserves_source_identity_as_data() -> None:
    document = _document("2508.11110v1", "Repair succeeds in 56.4–68.2% of cases.")

    context = format_evidence_context([document])

    assert '"arxiv_id": "2508.11110v1"' in context
    assert '"text": "Repair succeeds in 56.4–68.2% of cases."' in context
    assert allowed_citation_ids([document]) == ("2508.11110v1",)


def test_accepts_allowlisted_citation_and_supported_range() -> None:
    document = _document("2508.11110v1", "Repair succeeds in 56.4–68.2% of cases.")

    result = validate_grounded_answer(
        "The reported range is 56.4% to 68.2% [arXiv:2508.11110].",
        [document],
    )

    assert result.valid is True
    assert result.invalid_citations == ()
    assert result.unsupported_numeric_claims == ()


def test_rejects_citation_outside_evidence_allowlist() -> None:
    document = _document("2508.11110v1", "Repair succeeds in 56.4–68.2% of cases.")

    result = validate_grounded_answer(
        "The reported range is 56.4% to 68.2% [arXiv:2508.99999].",
        [document],
    )

    assert result.valid is False
    assert result.invalid_citations == ("2508.99999",)


def test_rejects_unsupported_quantitative_claim() -> None:
    document = _document("2508.11110v1", "Repair succeeds in 56.4–68.2% of cases.")

    result = validate_grounded_answer(
        "The reported rate is 99.9% [arXiv:2508.11110v1].",
        [document],
    )

    assert result.valid is False
    assert result.unsupported_numeric_claims == ("99.9",)


def test_requires_citation_when_evidence_has_source_ids() -> None:
    document = _document("2508.11110v1", "Repair succeeds in many cases.")

    result = validate_grounded_answer("Repair succeeds in many cases.", [document])

    assert result.valid is False
    assert result.missing_citation is True
