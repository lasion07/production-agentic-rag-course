import json
import logging
import re
import time
import uuid

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

logger = logging.getLogger(__name__)

_SAFE_REQUEST_ID = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")


class RequestContextMiddleware:
    """Attach a correlation ID and emit body-free structured access logs."""

    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        app = scope.get("app")
        settings = getattr(getattr(app, "state", None), "settings", None)
        header_name = b"x-request-id"
        incoming = next((value.decode("latin-1") for key, value in scope.get("headers", []) if key == header_name), None)
        trust_incoming = bool(getattr(settings, "trust_incoming_request_id", False))
        request_id = incoming if trust_incoming and incoming and _SAFE_REQUEST_ID.fullmatch(incoming) else uuid.uuid4().hex

        state = scope.setdefault("state", {})
        state["request_id"] = request_id
        status_code = 500
        started_at = time.monotonic()

        async def send_with_request_id(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = int(message["status"])
                headers = MutableHeaders(scope=message)
                headers["X-Request-ID"] = request_id
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        finally:
            logger.info(
                json.dumps(
                    {
                        "event": "request_completed",
                        "request_id": request_id,
                        "method": scope.get("method"),
                        "path": scope.get("path"),
                        "status_code": status_code,
                        "duration_ms": round((time.monotonic() - started_at) * 1000, 2),
                        "user_id": state.get("user_id", "unauthenticated"),
                    },
                    sort_keys=True,
                )
            )


# Legacy Week 1 helpers retained for notebook compatibility. Production request
# timing and correlation are handled by RequestContextMiddleware above.


def log_request(method: str, path: str) -> None:
    """Simple request logging for Week 1."""
    logger.info(f"{method} {path}")


def log_error(error: str, method: str, path: str) -> None:
    """Simple error logging for Week 1."""
    logger.error(f"Error in {method} {path}: {error}")
