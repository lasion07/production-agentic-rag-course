from src.services.agents.prompts import GENERATE_ANSWER_PROMPT


def test_answer_prompt_requires_exact_quantitative_evidence():
    assert "preserve the exact values and units" in GENERATE_ANSWER_PROMPT
    assert "retrieved evidence does not provide them" in GENERATE_ANSWER_PROMPT
