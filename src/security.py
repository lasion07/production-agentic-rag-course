"""Authentication, caller identity, rate limiting, and feedback ownership."""

from __future__ import annotations

import asyncio
import hashlib
import logging
import secrets
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Request, Response, Security
from fastapi.security import APIKeyHeader
from src.api_errors import PublicAPIError
from src.config import Settings

logger = logging.getLogger(__name__)

API_KEY_HEADER_NAME = "X-API-Key"
_api_key_header = APIKeyHeader(name=API_KEY_HEADER_NAME, auto_error=False)
_RATE_LIMIT_SCRIPT = """
local count = redis.call('INCR', KEYS[1])
if count == 1 then
  redis.call('EXPIRE', KEYS[1], ARGV[1])
end
local ttl = redis.call('TTL', KEYS[1])
return {count, ttl}
"""


@dataclass(frozen=True)
class APIIdentity:
    """Stable non-secret caller identity derived from an authenticated API key."""

    user_id: str
    key_fingerprint: str


def _settings(request: Request) -> Settings:
    settings = getattr(request.app.state, "settings", None)
    return settings if settings is not None else Settings()


def _fingerprint(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def _authenticate(settings: Settings, provided_key: str | None) -> APIIdentity:
    if not settings.api_auth_enabled:
        return APIIdentity(user_id="development-anonymous", key_fingerprint="auth-disabled")
    if not provided_key:
        raise PublicAPIError(
            status_code=401,
            code="authentication_required",
            message=f"Provide a valid {API_KEY_HEADER_NAME} header.",
            headers={"WWW-Authenticate": "ApiKey"},
        )

    for configured_secret in settings.api_keys:
        configured_key = configured_secret.get_secret_value()
        if configured_key and secrets.compare_digest(provided_key, configured_key):
            fingerprint = _fingerprint(configured_key)
            return APIIdentity(user_id=f"api-key:{fingerprint}", key_fingerprint=fingerprint)

    raise PublicAPIError(
        status_code=401,
        code="invalid_api_key",
        message="The supplied API key is invalid.",
        headers={"WWW-Authenticate": "ApiKey"},
    )


def _redis_client(request: Request):
    cache_client = getattr(request.app.state, "cache_client", None)
    return getattr(cache_client, "redis", None)


async def _redis_call(settings: Settings, func, *args, **kwargs):
    try:
        return await asyncio.wait_for(
            asyncio.to_thread(func, *args, **kwargs),
            timeout=settings.api_security_redis_timeout_seconds,
        )
    except Exception as exc:
        logger.warning("API security Redis operation failed: %s", type(exc).__name__)
        raise PublicAPIError(
            status_code=503,
            code="security_dependency_unavailable",
            message="Request protection is temporarily unavailable.",
            headers={"Retry-After": "1"},
        ) from exc


async def _enforce_rate_limit(
    request: Request,
    response: Response,
    settings: Settings,
    identity: APIIdentity,
) -> None:
    if not settings.api_rate_limit_enabled:
        return

    redis_client = _redis_client(request)
    if redis_client is None:
        raise PublicAPIError(
            status_code=503,
            code="security_dependency_unavailable",
            message="Request protection is temporarily unavailable.",
            headers={"Retry-After": "1"},
        )

    async def consume(bucket: str) -> tuple[int, int]:
        count, ttl = await _redis_call(
            settings,
            redis_client.eval,
            _RATE_LIMIT_SCRIPT,
            1,
            bucket,
            settings.api_rate_limit_window_seconds,
        )
        return int(count), max(1, int(ttl))

    window = settings.api_rate_limit_window_seconds
    global_count, global_ttl = await consume(f"api-rate-limit:{settings.environment}:global:{window}")
    global_remaining = max(0, settings.api_global_rate_limit_requests - global_count)
    response.headers["X-RateLimit-Global-Limit"] = str(settings.api_global_rate_limit_requests)
    response.headers["X-RateLimit-Global-Remaining"] = str(global_remaining)
    if global_count > settings.api_global_rate_limit_requests:
        raise PublicAPIError(
            status_code=429,
            code="global_rate_limit_exceeded",
            message="The service request limit has been reached. Retry later.",
            headers={
                "Retry-After": str(global_ttl),
                "X-RateLimit-Global-Limit": str(settings.api_global_rate_limit_requests),
                "X-RateLimit-Global-Remaining": "0",
            },
        )

    bucket = f"api-rate-limit:{settings.environment}:{identity.key_fingerprint}:{window}"
    count, ttl = await consume(bucket)
    remaining = max(0, settings.api_rate_limit_requests - count)
    response.headers["X-RateLimit-Limit"] = str(settings.api_rate_limit_requests)
    response.headers["X-RateLimit-Remaining"] = str(remaining)

    if count > settings.api_rate_limit_requests:
        raise PublicAPIError(
            status_code=429,
            code="rate_limit_exceeded",
            message="Too many requests. Retry after the current rate-limit window.",
            headers={
                "Retry-After": str(ttl),
                "X-RateLimit-Limit": str(settings.api_rate_limit_requests),
                "X-RateLimit-Remaining": "0",
            },
        )


async def enforce_api_access(
    request: Request,
    response: Response,
    provided_key: Annotated[str | None, Security(_api_key_header)],
) -> APIIdentity:
    """Authenticate a request, attach identity, then apply a distributed limit."""

    settings = _settings(request)
    identity = _authenticate(settings, provided_key)
    request.state.user_id = identity.user_id
    await _enforce_rate_limit(request, response, settings, identity)
    return identity


APIIdentityDep = Annotated[APIIdentity, Depends(enforce_api_access)]


def _trace_owner_key(trace_id: str) -> str:
    return f"trace-owner:{_fingerprint(trace_id)}"


async def record_trace_owner(request: Request, identity: APIIdentity, trace_id: str | None) -> None:
    """Persist trace ownership so feedback cannot be submitted for another caller."""

    settings = _settings(request)
    if not settings.api_auth_enabled or not trace_id:
        return
    redis_client = _redis_client(request)
    if redis_client is None:
        raise PublicAPIError(503, "security_dependency_unavailable", "Feedback protection is temporarily unavailable.")
    await _redis_call(
        settings,
        redis_client.set,
        _trace_owner_key(trace_id),
        identity.user_id,
        ex=settings.feedback_ownership_ttl_seconds,
    )


async def verify_trace_owner(request: Request, identity: APIIdentity, trace_id: str) -> None:
    """Reject feedback unless the authenticated caller owns the referenced trace."""

    settings = _settings(request)
    if not settings.api_auth_enabled:
        return
    redis_client = _redis_client(request)
    if redis_client is None:
        raise PublicAPIError(503, "security_dependency_unavailable", "Feedback protection is temporarily unavailable.")
    owner = await _redis_call(settings, redis_client.get, _trace_owner_key(trace_id))
    if isinstance(owner, bytes):
        owner = owner.decode("utf-8", errors="replace")
    if owner is None or not secrets.compare_digest(str(owner), identity.user_id):
        raise PublicAPIError(403, "feedback_forbidden", "Feedback is not allowed for this trace.")
