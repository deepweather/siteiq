"""Rate limiting — slowapi wrapper.

Why slowapi: integrates cleanly with FastAPI's Depends, supports both
in-memory (dev) and Redis (prod) via a single URL knob.

We limit by IP for unauth flows (signup, login, forgot-password) and by
user-id for authed flows. The limiter is attached to `app.state` so
tests can swap or disable it.
"""
from __future__ import annotations

from typing import Optional

from slowapi import Limiter
from slowapi.util import get_remote_address


def build_limiter(redis_url: str = "") -> Limiter:
    """In-memory if redis_url is empty (dev/test). Use Redis in prod for
    multi-process correctness."""
    if redis_url:
        return Limiter(key_func=get_remote_address, storage_uri=redis_url)
    return Limiter(key_func=get_remote_address)


def get_limiter(request) -> Optional[Limiter]:
    return getattr(request.app.state, "limiter", None)
