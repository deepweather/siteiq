"""Security headers — applied to every HTTP response.

Pure ASGI middleware (NOT `BaseHTTPMiddleware`). starlette's
`BaseHTTPMiddleware` is incompatible with the pattern of
`CORSMiddleware → CSRFMiddleware → BaseHTTPMiddleware`-style stacks —
the third layer in the chain deadlocks the TestClient when an inner
middleware short-circuits a request. This implementation only inspects
and decorates the outgoing `http.response.start` message, so it has
none of those interactions.

Defaults:
- HSTS: 1 year + subdomains, but ONLY in prod (sending HSTS over plain
  HTTP/localhost would force browsers to upgrade dev requests).
- X-Content-Type-Options: nosniff — blocks MIME-sniffing attacks.
- X-Frame-Options: DENY — we never embed in iframes.
- Referrer-Policy: strict-origin-when-cross-origin.
- Permissions-Policy: deny camera/mic/geolocation/payment — the
  product never asks for these.
- Content-Security-Policy: forbid object/embed and frame ancestors,
  allow self + the configured frontend + the HIBP API endpoint.
"""
from __future__ import annotations

from starlette.types import ASGIApp, Message, Receive, Scope, Send


def _csp(frontend_origin: str) -> str:
    return "; ".join(
        [
            "default-src 'self'",
            "img-src 'self' data: blob:",
            "style-src 'self' 'unsafe-inline'",
            "script-src 'self' 'unsafe-inline'",
            f"connect-src 'self' {frontend_origin} ws: wss: https://api.pwnedpasswords.com",
            "font-src 'self' data:",
            "object-src 'none'",
            "frame-ancestors 'none'",
            "base-uri 'self'",
            "form-action 'self'",
        ]
    )


def _baseline(is_prod: bool, csp_value: str) -> list[tuple[bytes, bytes]]:
    headers: list[tuple[bytes, bytes]] = [
        (b"x-content-type-options", b"nosniff"),
        (b"x-frame-options", b"DENY"),
        (b"referrer-policy", b"strict-origin-when-cross-origin"),
        (b"permissions-policy", b"geolocation=(), microphone=(), camera=(), payment=()"),
        (b"content-security-policy", csp_value.encode("latin-1")),
    ]
    if is_prod:
        headers.append((b"strict-transport-security", b"max-age=31536000; includeSubDomains"))
    return headers


class SecurityHeadersMiddleware:
    def __init__(self, app: ASGIApp, *, is_prod: bool, frontend_origin: str) -> None:
        self.app = app
        self._extra = _baseline(is_prod, _csp(frontend_origin))

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def wrapped_send(message: Message) -> None:
            if message["type"] == "http.response.start":
                existing = list(message.get("headers", []))
                existing_keys = {k.lower() for (k, _v) in existing}
                for key, value in self._extra:
                    if key not in existing_keys:
                        existing.append((key, value))
                message["headers"] = existing
            await send(message)

        await self.app(scope, receive, wrapped_send)
