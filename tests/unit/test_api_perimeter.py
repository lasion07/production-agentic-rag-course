from types import SimpleNamespace
from typing import Annotated

import pytest
from fastapi import FastAPI, Query, Request
from fastapi.testclient import TestClient
from pydantic import SecretStr, ValidationError
from src.api_errors import register_exception_handlers
from src.config import LangfuseSettings, OpenSearchSettings, RedisSettings, Settings, TelegramSettings
from src.middlewares import RequestContextMiddleware
from src.security import APIIdentityDep, record_trace_owner, verify_trace_owner


class FakeRedis:
    def __init__(self):
        self.counts: dict[str, int] = {}
        self.values: dict[str, str] = {}

    def eval(self, _script, _numkeys, key, window):
        self.counts[key] = self.counts.get(key, 0) + 1
        return [self.counts[key], int(window)]

    def set(self, key, value, **_kwargs):
        self.values[key] = value
        return True

    def get(self, key):
        return self.values.get(key)


class FailingRedis(FakeRedis):
    def eval(self, _script, _numkeys, key, window):
        raise TimeoutError("redis-internal-detail")


def make_client(*, request_limit: int = 2, global_limit: int = 100, redis_client=None) -> TestClient:
    app = FastAPI()
    app.state.settings = Settings(
        _env_file=None,
        api_auth_enabled=True,
        api_keys=["test-api-key-with-at-least-32-characters"],
        api_rate_limit_enabled=True,
        api_rate_limit_requests=request_limit,
        api_global_rate_limit_requests=global_limit,
        api_rate_limit_window_seconds=60,
    )
    app.state.cache_client = SimpleNamespace(redis=redis_client or FakeRedis())
    app.add_middleware(RequestContextMiddleware)
    register_exception_handlers(app)

    @app.get("/protected")
    async def protected(identity: APIIdentityDep):
        return {"user_id": identity.user_id}

    @app.get("/explode")
    async def explode(_identity: APIIdentityDep):
        raise RuntimeError("provider-secret-must-not-leak")

    @app.get("/validate")
    async def validate(
        _identity: APIIdentityDep,
        value: Annotated[str, Query(max_length=3)],
    ):
        return {"value": value}

    @app.post("/traces/{trace_id}")
    async def own_trace(trace_id: str, request: Request, identity: APIIdentityDep):
        await record_trace_owner(request, identity, trace_id)
        return {"recorded": True}

    @app.post("/feedback-test/{trace_id}")
    async def feedback_test(trace_id: str, request: Request, identity: APIIdentityDep):
        await verify_trace_owner(request, identity, trace_id)
        return {"allowed": True}

    return TestClient(app, raise_server_exceptions=False)


def test_production_rejects_unsafe_perimeter_configuration():
    with pytest.raises(ValidationError, match="Unsafe production configuration"):
        Settings(_env_file=None, environment="production", debug=True)


def test_production_accepts_explicit_safe_perimeter_configuration():
    settings = Settings(
        _env_file=None,
        environment="production",
        debug=False,
        opensearch_schema_management_enabled=False,
        api_auth_enabled=True,
        api_keys=["production-key-with-at-least-32-characters"],
        api_rate_limit_enabled=True,
        postgres_database_url=(
            "postgresql+psycopg2://rag_prod:D7m9K2q8N4v6X1z3@db.internal/rag"
            "?sslmode=verify-full"
        ),
        llm_provider="openai",
        openai_api_key="sk-production-value-with-sufficient-entropy",
        jina_api_key="jina-production-value-with-sufficient-entropy",
        opensearch=OpenSearchSettings(
            _env_file=None,
            host="https://search.internal:9200",
            username="rag_service",
            password="Os9xK4v2N7m5Q8z1",
            verify_certs=True,
        ),
        redis=RedisSettings(
            _env_file=None,
            host="redis.internal",
            password="Rd8kP3m7X2v9N5q1",
            ssl=True,
            ssl_cert_reqs="required",
        ),
        langfuse=LangfuseSettings(
            _env_file=None,
            enabled=True,
            base_url="https://us.cloud.langfuse.com",
            public_key="pk-production",
            secret_key="lf9K2m7X4v8N1q5Z",
            capture_content=False,
        ),
        telegram=TelegramSettings(_env_file=None),
    )

    assert settings.environment == "production"


def test_missing_and_invalid_api_keys_use_sanitized_error_envelope():
    client = make_client()

    missing = client.get("/protected")
    invalid = client.get("/protected", headers={"X-API-Key": "wrong"})

    assert missing.status_code == 401
    assert missing.json()["error"]["code"] == "authentication_required"
    assert missing.json()["error"]["request_id"] == missing.headers["X-Request-ID"]
    assert invalid.status_code == 401
    assert invalid.json()["error"]["code"] == "invalid_api_key"


def test_valid_api_key_derives_identity_without_exposing_secret():
    client = make_client()
    key = "test-api-key-with-at-least-32-characters"

    response = client.get("/protected", headers={"X-API-Key": key})

    assert response.status_code == 200
    assert response.json()["user_id"].startswith("api-key:")
    assert key not in response.text
    assert response.headers["X-RateLimit-Limit"] == "2"


def test_distributed_rate_limit_returns_429_and_retry_after():
    client = make_client(request_limit=2)
    headers = {"X-API-Key": "test-api-key-with-at-least-32-characters"}

    assert client.get("/protected", headers=headers).status_code == 200
    assert client.get("/protected", headers=headers).status_code == 200
    limited = client.get("/protected", headers=headers)

    assert limited.status_code == 429
    assert limited.json()["error"]["code"] == "rate_limit_exceeded"
    assert limited.headers["Retry-After"] == "60"
    assert limited.headers["X-RateLimit-Remaining"] == "0"


def test_global_rate_limit_is_shared_across_identities():
    client = make_client(request_limit=10, global_limit=2)
    first = {"X-API-Key": "test-api-key-with-at-least-32-characters"}
    second = {"X-API-Key": "second-test-api-key-with-at-least-32-characters"}
    client.app.state.settings.api_keys.append(SecretStr(second["X-API-Key"]))

    assert client.get("/protected", headers=first).status_code == 200
    assert client.get("/protected", headers=second).status_code == 200
    limited = client.get("/protected", headers=second)

    assert limited.status_code == 429
    assert limited.json()["error"]["code"] == "global_rate_limit_exceeded"
    assert limited.headers["X-RateLimit-Global-Remaining"] == "0"


def test_feedback_is_limited_to_the_authenticated_trace_owner():
    client = make_client(request_limit=10)
    owner = {"X-API-Key": "test-api-key-with-at-least-32-characters"}
    other = {"X-API-Key": "second-test-api-key-with-at-least-32-characters"}
    client.app.state.settings.api_keys.append(SecretStr(other["X-API-Key"]))

    assert client.post("/traces/trace-123", headers=owner).status_code == 200
    assert client.post("/feedback-test/trace-123", headers=owner).status_code == 200
    forbidden = client.post("/feedback-test/trace-123", headers=other)

    assert forbidden.status_code == 403
    assert forbidden.json()["error"]["code"] == "feedback_forbidden"


def test_security_redis_failure_is_fast_and_sanitized():
    client = make_client(redis_client=FailingRedis())

    response = client.get(
        "/protected",
        headers={"X-API-Key": "test-api-key-with-at-least-32-characters"},
    )

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "security_dependency_unavailable"
    assert "redis-internal-detail" not in response.text
    assert response.headers["Retry-After"] == "1"


def test_validation_errors_do_not_echo_rejected_input():
    client = make_client()

    response = client.get(
        "/validate",
        params={"value": "private-query-content"},
        headers={"X-API-Key": "test-api-key-with-at-least-32-characters"},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
    assert "private-query-content" not in response.text


def test_unexpected_errors_do_not_leak_internal_exception_text():
    client = make_client()

    response = client.get(
        "/explode",
        headers={"X-API-Key": "test-api-key-with-at-least-32-characters"},
    )

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "internal_error"
    assert "provider-secret" not in response.text
    assert response.json()["error"]["request_id"] == response.headers["X-Request-ID"]


def test_incoming_request_id_is_not_trusted_by_default():
    client = make_client()

    response = client.get(
        "/protected",
        headers={
            "X-API-Key": "test-api-key-with-at-least-32-characters",
            "X-Request-ID": "attacker-controlled",
        },
    )

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] != "attacker-controlled"


def test_only_liveness_route_is_public_in_openapi_contract():
    from src.main import app

    paths = app.openapi()["paths"]
    assert paths["/api/v1/live"]["get"].get("security") is None
    for path, method in (
        ("/api/v1/health", "get"),
        ("/api/v1/hybrid-search/", "post"),
        ("/api/v1/ask", "post"),
        ("/api/v1/stream", "post"),
        ("/api/v1/ask-agentic", "post"),
        ("/api/v1/feedback", "post"),
    ):
        assert paths[path][method]["security"] == [{"APIKeyHeader": []}]
        assert paths[path][method]["responses"]["429"]["content"]["application/json"]["schema"]


def test_readiness_route_remains_protected():
    from src.main import app

    operation = app.openapi()["paths"]["/api/v1/ready"]["get"]
    assert operation["security"] == [{"APIKeyHeader": []}]
