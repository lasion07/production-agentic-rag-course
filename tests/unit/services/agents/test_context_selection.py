from langchain_core.documents import Document
from src.services.agents.context_selection import select_context_documents


def document(text: str, arxiv_id: str = "paper") -> Document:
    return Document(page_content=text, metadata={"arxiv_id": arxiv_id})


def test_quantitative_range_is_promoted_without_hard_coded_values():
    candidates = [
        document("The repair method adds noise and resumes iterative diffusion."),
        document("Related work was published between 2020 and 2024."),
        document("Across benchmarks, successful repair ranges from 41.7-73.9%."),
        document("The repair method adds noise and resumes the diffusion process."),
    ]

    selected = select_context_documents(
        "What success percentage range is reported, and how is repair performed?",
        candidates,
        final_k=2,
    )

    assert "41.7-73.9%" in selected[0].page_content
    assert any("adds noise" in item.page_content for item in selected)
    assert all(item.metadata["reranked"] is True for item in selected)


def test_near_duplicate_does_not_displace_distinct_context():
    candidates = [
        document("Transformers use self attention to model token relationships.", "A"),
        document("Transformers use self attention to model token relationships in sequences.", "A"),
        document("Experiments compare transformer accuracy on translation benchmarks.", "B"),
    ]

    selected = select_context_documents(
        "How do transformers use attention and what do experiments show?",
        candidates,
        final_k=2,
    )

    assert {item.metadata["arxiv_id"] for item in selected} == {"A", "B"}


def test_selection_respects_final_k_and_empty_input():
    assert select_context_documents("query", [], final_k=3) == []
    assert len(select_context_documents("query", [document("one"), document("two")], final_k=1)) == 1
