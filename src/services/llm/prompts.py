"""Provider-neutral prompt construction and response parsing."""

import json
import re
from pathlib import Path
from typing import Any, Dict, List

from pydantic import ValidationError
from src.schemas.llm import RAGResponse


class RAGPromptBuilder:
    """Build grounded prompts shared by local and hosted LLMs."""

    def __init__(self):
        self.prompts_dir = Path(__file__).parents[1] / "ollama" / "prompts"
        self.system_prompt = self._load_system_prompt()

    def _load_system_prompt(self) -> str:
        prompt_file = self.prompts_dir / "rag_system.txt"
        if not prompt_file.exists():
            return (
                "You are an AI assistant specialized in answering questions about "
                "academic papers from arXiv. Base your answer STRICTLY on the provided "
                "paper excerpts."
            )
        return prompt_file.read_text().strip()

    def create_rag_prompt(self, query: str, chunks: List[Dict[str, Any]]) -> str:
        prompt = f"{self.system_prompt}\n\n### Context from Papers:\n\n"
        for index, chunk in enumerate(chunks, 1):
            chunk_text = chunk.get("chunk_text", chunk.get("content", ""))
            arxiv_id = chunk.get("arxiv_id", "")
            prompt += f"[{index}. arXiv:{arxiv_id}]\n{chunk_text}\n\n"
        prompt += f"### Question:\n{query}\n\n"
        prompt += (
            "### Answer:\nProvide a natural, conversational response (not JSON) "
            "and cite sources using [arXiv:id] format.\n\n"
        )
        return prompt

    def create_structured_prompt(self, query: str, chunks: List[Dict[str, Any]]) -> Dict[str, Any]:
        return {
            "prompt": self.create_rag_prompt(query, chunks),
            "format": RAGResponse.model_json_schema(),
        }


class ResponseParser:
    """Parse structured output from any LLM provider."""

    @staticmethod
    def parse_structured_response(response: str) -> Dict[str, Any]:
        try:
            return RAGResponse(**json.loads(response)).model_dump()
        except (json.JSONDecodeError, ValidationError):
            return ResponseParser._extract_json_fallback(response)

    @staticmethod
    def _extract_json_fallback(response: str) -> Dict[str, Any]:
        json_match = re.search(r"\{.*\}", response, re.DOTALL)
        if json_match:
            try:
                return RAGResponse(**json.loads(json_match.group())).model_dump()
            except (json.JSONDecodeError, ValidationError):
                pass
        return {
            "answer": response,
            "sources": [],
            "confidence": "low",
            "citations": [],
        }
