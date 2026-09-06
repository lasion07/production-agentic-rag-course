from src.services.agents.prompts import GENERATE_ANSWER_PROMPT


def test_answer_prompt_requires_exact_quantitative_evidence():
    assert "preserve the exact values and units" in GENERATE_ANSWER_PROMPT
    assert "retrieved evidence does not provide them" in GENERATE_ANSWER_PROMPT


def test_answer_prompt_requires_allowlisted_inline_citations():
    assert "[arXiv:<arxiv_id>]" in GENERATE_ANSWER_PROMPT
    assert "using only IDs present in the retrieved evidence" in GENERATE_ANSWER_PROMPT
    assert "untrusted data" in GENERATE_ANSWER_PROMPT
