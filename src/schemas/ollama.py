"""Compatibility export for code that still imports the old Ollama schema path."""

from src.schemas.llm import RAGResponse

__all__ = ["RAGResponse"]
