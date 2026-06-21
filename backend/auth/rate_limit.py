"""Rate limiting — slowapi.

slowapi's `@limiter.limit("…")` decorator captures the `Limiter` at
decoration time, which forces the limiter to live as a module-level
singleton. We keep that constraint visible here.

In dev/tests the in-memory backend is fine. In prod, set
`SITEIQ_RATE_LIMIT_REDIS_URL=redis://…` and `configure_storage()` from
the lifespan handler will rebind the limiter's storage so multiple
uvicorn workers share the same counters.

Tests can flip `limiter.enabled = False` per-app via `app.state.limiter`
(the lifespan also exposes the same singleton on `app.state`) to
deactivate limits without changing route signatures.
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import Request
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address


logger = logging.getLogger("siteiq.auth.rate_limit")


# Module-level singleton — required because @limiter.limit must reference
# a stable Limiter at decoration time.
limiter: Limiter = Limiter(key_func=get_remote_address)


def configure_storage(redis_url: str) -> None:
    """Switch the limiter's storage at runtime. Called from the lifespan
    once Settings are available."""
    if not redis_url:
        return  # Keep the default in-memory storage.
    # slowapi's Limiter exposes `storage` via the `_storage` private attr.
    # Re-build a Limiter with the prod storage and copy its internals.
    new = Limiter(key_func=get_remote_address, storage_uri=redis_url)
    limiter._storage = new._storage  # type: ignore[attr-defined]
    limiter._storage_uri = redis_url  # type: ignore[attr-defined]
    logger.info("rate_limiter_storage_configured", extra={"backend": "redis"})


def get_limiter(request: Request) -> Optional[Limiter]:
    return getattr(request.app.state, "limiter", None)


async def rate_limit_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    """Convert slowapi's exception into our standard error envelope."""
    detail = str(exc.detail) if exc.detail else "Too many requests. Try again shortly."
    return JSONResponse(
        status_code=429,
        content={
            "error": {
                "code": "rate_limited",
                "message": detail,
            }
        },
    )
