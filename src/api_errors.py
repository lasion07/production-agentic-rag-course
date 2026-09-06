"""Stable, sanitized HTTP error contracts for public API consumers."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from src.schemas.api.errors import APIErrorBody, APIErrorResponse

logger = logging.getLogger(__name__)

PUBLIC_ERROR_RESPONSES = {
    status_code: {"model": APIErrorResponse}
    for status_code in (401, 403, 422, 429, 500, 503, 504)
}


@dataclass
class PublicAPIError(Exception):
    """An expected failure that is safe to expose through the API."""

    status_code: int
    code: str
    message: str
    headers: dict[str, str] = field(default_factory=dict)


def _request_id(request: Request) -> str:
    return str(getattr(request.state, "request_id", "unknown"))


def _payload(request: Request, code: str, message: str, details: Any = None) -> dict[str, Any]:
    payload = APIErrorResponse(
        error=APIErrorBody(
            code=code,
            message=message,
            request_id=_request_id(request),
            details=details,
        )
    )
    return payload.model_dump(exclude_none=True)


def _response_headers(request: Request, headers: dict[str, str] | None = None) -> dict[str, str]:
    result = dict(headers or {})
    result.setdefault("X-Request-ID", _request_id(request))
    return result


async def public_api_error_handler(request: Request, exc: PublicAPIError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content=_payload(request, exc.code, exc.message),
        headers=_response_headers(request, exc.headers),
    )


async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    details = [
        {
            "location": [str(part) for part in error.get("loc", ())],
            "type": error.get("type", "validation_error"),
            "message": error.get("msg", "Invalid value"),
        }
        for error in exc.errors()
    ]
    return JSONResponse(
        status_code=422,
        content=_payload(request, "validation_error", "Request validation failed.", details),
        headers=_response_headers(request),
    )


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    detail = exc.detail
    if isinstance(detail, dict):
        code = str(detail.get("business_status") or detail.get("code") or "request_failed")
        message = str(detail.get("message") or "Request failed.")
    elif exc.status_code < 500:
        code = "request_failed"
        message = str(detail)
    else:
        code = "service_unavailable" if exc.status_code == 503 else "internal_error"
        message = "The service is temporarily unavailable." if exc.status_code == 503 else "The request could not be completed."
    return JSONResponse(
        status_code=exc.status_code,
        content=_payload(request, code, message),
        headers=_response_headers(request, exc.headers),
    )


async def unexpected_error_handler(request: Request, exc: Exception) -> JSONResponse:
    request_id = _request_id(request)
    logger.error(
        "Unhandled API error request_id=%s",
        request_id,
        exc_info=(type(exc), exc, exc.__traceback__),
    )
    return JSONResponse(
        status_code=500,
        content=_payload(request, "internal_error", "The request could not be completed."),
        headers=_response_headers(request),
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Register one stable public error envelope for every API failure class."""

    app.add_exception_handler(PublicAPIError, public_api_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(Exception, unexpected_error_handler)
