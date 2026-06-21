"""WebSocket authentication helper.

WS upgrades go through CORS but not the CSRF middleware (the middleware
exempts /ws). To keep them safe we:

1. Verify Origin against the configured `frontend_origin` (or any
   `cors_origins` entry) — blocks cross-site upgrade attempts.
2. Read the session cookie and verify it against `auth_sessions`.

If either fails, close the socket with code 4401 (custom — convention
mirrors HTTP 401 for clarity in browser dev tools).
"""
from __future__ import annotations

import logging

from fastapi import WebSocket

from auth.sessions import cookie_name, get_session


logger = logging.getLogger("siteiq.api.ws_auth")


async def authenticate_ws(websocket: WebSocket) -> bool:
    settings = websocket.app.state.settings
    origin = websocket.headers.get("origin")
    allowed = {settings.frontend_origin.rstrip("/")} | {o.rstrip("/") for o in settings.cors_origins}
    if origin is not None and origin.rstrip("/") not in allowed:
        logger.warning("ws_origin_rejected", extra={"origin": origin})
        await websocket.close(code=4403, reason="origin_not_allowed")
        return False

    factory = getattr(websocket.app.state, "db_session_factory", None)
    if factory is None:
        await websocket.close(code=1011, reason="db_not_ready")
        return False

    token = websocket.cookies.get(cookie_name(settings))
    if not token:
        await websocket.close(code=4401, reason="not_authenticated")
        return False

    async with factory() as db:
        session = await get_session(db, token)
        if session is None:
            await websocket.close(code=4401, reason="session_invalid")
            return False
    return True
