"""Request-ID middleware + logging filter.

Why: when a user reports a bug, the question "what was your X-Request-Id?"
beats "what time was it, exactly?" by a wide margin. Every request now
carries one — either echoed from upstream (e.g. a load balancer) or
freshly generated — and every log line emitted while serving that
request gets the same id attached. The id is also returned to the
client via `X-Request-Id` so support can paste it back.

Implementation: a `contextvars.ContextVar` holds the current id; the
middleware sets it at request start. A `logging.Filter` reads from the
ContextVar and stamps every record. ASGI middleware (not
BaseHTTPMiddleware) — we only inspect headers and decorate responses.
"""
from __future__ import annotations

import contextvars
import logging
import uuid

from starlette.types import ASGIApp, Message, Receive, Scope, Send


HEADER = "x-request-id"

# ContextVar so handlers + log filters see the id without explicit
# threading. Default is empty (e.g. for boot-time logs).
_current: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="")


def get_current_request_id() -> str:
    return _current.get()


class RequestIdFilter(logging.Filter):
    """Stamps `request_id` on every emitted record."""

    def filter(self, record: logging.LogRecord) -> bool:
        rid = _current.get()
        if rid:
            record.request_id = rid
        return True


class RequestIdMiddleware:
    """Reads `X-Request-Id` (or generates one), binds it to the
    ContextVar for the duration of the request, and echoes it back
    on the response."""

    def __init__(self, app: ASGIApp, *, header: str = HEADER) -> None:
        self.app = app
        self._header = header.lower().encode("latin-1")

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        # Read incoming X-Request-Id if present, else generate.
        incoming: str | None = None
        for name, value in scope.get("headers", []):
            if name.lower() == self._header:
                incoming = value.decode("latin-1")
                break
        rid = incoming or uuid.uuid4().hex
        token = _current.set(rid)

        async def wrapped_send(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.append((self._header, rid.encode("latin-1")))
                message["headers"] = headers
            await send(message)

        try:
            await self.app(scope, receive, wrapped_send)
        finally:
            _current.reset(token)
