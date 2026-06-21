"""Liveness + readiness endpoints.

`/healthz` — cheap liveness probe. Returns 200 as long as the process
is up. Containers + load balancers use this to decide "should I
restart this pod?".

`/readyz` — readiness probe. Returns 200 only when the DB is
reachable AND the simulation registry has been initialised. Returns
503 otherwise so traffic is held off briefly during startup.

Both are deliberately unauthenticated — they're called by infra, not
users — and exempt from CSRF (GET only). They never hit the simulation
or YOLO model so they're fast.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text


router = APIRouter()
logger = logging.getLogger("siteiq.api.health")


@router.get("/healthz")
async def liveness():
    """Process is up. Cheapest possible response."""
    return {"status": "ok"}


@router.get("/readyz")
async def readiness(request: Request):
    """All hard dependencies are ready: DB ping + state registry."""
    checks: dict[str, str] = {}
    ok = True

    # DB ping — `SELECT 1` against the configured engine.
    factory = getattr(request.app.state, "db_session_factory", None)
    if factory is None:
        checks["database"] = "not_configured"
        ok = False
    else:
        try:
            async with factory() as db:
                await db.execute(text("SELECT 1"))
            checks["database"] = "ok"
        except Exception as e:
            logger.exception("readiness_db_check_failed")
            checks["database"] = f"error: {type(e).__name__}"
            ok = False

    registry = getattr(request.app.state, "registry", None)
    checks["registry"] = "ok" if registry is not None else "not_ready"
    if registry is None:
        ok = False

    payload = {
        "status": "ok" if ok else "degraded",
        "checks": checks,
        "ts": datetime.now(timezone.utc).isoformat(),
    }
    return JSONResponse(status_code=200 if ok else 503, content=payload)
