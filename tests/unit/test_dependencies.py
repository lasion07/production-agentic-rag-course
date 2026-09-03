from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from src.dependencies import get_agentic_rag_service


def request_with_agent_state(service=None, error=None):
    state = SimpleNamespace(agentic_rag_service=service, agentic_rag_error=error)
    return SimpleNamespace(app=SimpleNamespace(state=state))


def test_get_agentic_rag_service_returns_startup_validated_singleton():
    service = object()

    assert get_agentic_rag_service(request_with_agent_state(service=service)) is service


def test_get_agentic_rag_service_fails_with_readiness_contract():
    with pytest.raises(HTTPException) as captured:
        get_agentic_rag_service(request_with_agent_state(error="RuntimeError: graph compilation failed"))

    assert captured.value.status_code == 503
    assert captured.value.detail == {
        "business_status": "agentic_unavailable",
        "message": "RuntimeError: graph compilation failed",
    }
