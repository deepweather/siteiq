"""CSRF protection — double-submit cookie pattern.

Flow:
1. Frontend calls GET /auth/csrf, which sets a non-HttpOnly cookie
   `siteiq_csrf` and returns the same token in the body.
2. For every state-changing request (POST/PUT/PATCH/DELETE) the frontend
   echoes the cookie value back via the `X-CSRF-Token` header.
3. The middleware compares cookie vs header — if they don't match, 403.

Why this works: a cross-origin attacker can't read the cookie value
(SameSite=Lax + browser SOP), so they can't construct the matching
header. Nothing on the backend has to track per-session state.

We additionally check `Origin` for state-changing requests and reject
unknown origins; this is a belt-and-suspenders defense if a browser bug
ever leaks the cookie value.
"""
from __future__ import annotations

import hmac
import logging
import secrets
from typing import Iterable

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response, JSONResponse


logger = logging.getLogger("siteiq.auth.csrf")


CSRF_COOKIE = "siteiq_csrf"
CSRF_HEADER = "X-CSRF-Token"
SAFE_METHODS = {"GET", "HEAD", "OPTIONS", "TRACE"}
# Paths the middleware should never gate. WebSocket upgrades skip the
# middleware naturally, but the explicit prefix list documents what's
# unauthenticated by design.
EXEMPT_PREFIXES: tuple[str, ...] = (
    "/ws",
    "/auth/csrf",
    # Device ingestion uses bearer-token auth (no cookie), so CSRF — which
    # protects cookie-authenticated browser requests — does not apply. These
    # are called server-to-server by edge agents, not from a browser origin.
    "/api/ingest",
)


def generate_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def constant_time_eq(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


class CSRFMiddleware(BaseHTTPMiddleware):
    """Rejects state-changing requests without a matching CSRF cookie+header
    or with an unknown Origin."""

    def __init__(self, app, *, allowed_origins: Iterable[str], exempt_prefixes: tuple[str, ...] = EXEMPT_PREFIXES) -> None:
        super().__init__(app)
        self._allowed_origins = {o.rstrip("/") for o in allowed_origins}
        self._exempt = exempt_prefixes

    async def dispatch(self, request: Request, call_next):
        if request.method in SAFE_METHODS:
            return await call_next(request)

        path = request.url.path
        if any(path.startswith(p) for p in self._exempt):
            return await call_next(request)

        origin = request.headers.get("origin")
        if origin is not None and origin.rstrip("/") not in self._allowed_origins:
            logger.warning(
                "csrf_origin_rejected",
                extra={"path": path, "origin": origin},
            )
            return _csrf_error("origin_not_allowed")

        cookie_token = request.cookies.get(CSRF_COOKIE)
        header_token = request.headers.get(CSRF_HEADER)
        if not cookie_token or not header_token or not constant_time_eq(cookie_token, header_token):
            logger.info(
                "csrf_token_mismatch",
                extra={"path": path, "has_cookie": bool(cookie_token), "has_header": bool(header_token)},
            )
            return _csrf_error("csrf_token_invalid")

        return await call_next(request)


def _csrf_error(code: str) -> Response:
    return JSONResponse(
        status_code=403,
        content={"error": {"code": code, "message": "CSRF check failed"}},
    )
