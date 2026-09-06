"""Versioned public error response models."""

from typing import Any

from pydantic import BaseModel, Field


class APIErrorDetail(BaseModel):
    """A sanitized validation detail that never echoes submitted values."""

    location: list[str]
    type: str
    message: str


class APIErrorBody(BaseModel):
    """Stable machine-readable error returned by every public endpoint."""

    code: str
    message: str
    request_id: str
    details: list[APIErrorDetail] | dict[str, Any] | None = Field(default=None)


class APIErrorResponse(BaseModel):
    """Top-level error envelope."""

    error: APIErrorBody
