"""Liveness, readiness, and version endpoints.

`/healthz` — cheap liveness probe. Returns 200 as long as the process
is up. Containers + load balancers use this to decide "should I
restart this pod?".

`/readyz` — readiness probe. Returns 200 only when the DB is
reachable AND the simulation registry has been initialised. Returns
503 otherwise so traffic is held off briefly during startup.

`/api/version` — build-time identity. Returns commit SHA + build
timestamp from env (set by Docker build) or falls back to a `version.txt`
file shipped next to `main.py`. Useful for support tickets, browser
console banners, and prod diagnostics.

All three are deliberately unauthenticated — infra-facing, GET-only,
exempt from CSRF (which only gates state-changing methods). They
never hit the simulation or YOLO model so they're fast.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from pathlib import Path

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


def _read_version_fallback() -> tuple[str, str]:
    """Reads commit + build time from `version.txt` next to main.py
    (Docker build writes this file). Falls back to "dev" when
    neither env nor file is present."""
    try:
        path = Path(__file__).resolve().parent.parent / "version.txt"
        if path.is_file():
            text = path.read_text().strip().splitlines()
            commit = text[0].strip() if text else "dev"
            built_at = text[1].strip() if len(text) > 1 else ""
            return commit, built_at
    except Exception:
        logger.exception("version_file_read_failed")
    return "dev", ""


@router.get("/api/version")
async def version():
    """Build-time identity — commit SHA + build timestamp. Stable for
    the lifetime of the deployed binary."""
    commit = os.environ.get("SITEIQ_COMMIT_SHA") or _read_version_fallback()[0]
    built_at = os.environ.get("SITEIQ_BUILT_AT") or _read_version_fallback()[1]
    return {
        "commit": commit,
        "built_at": built_at,
        # Lets a frontend banner say "v2026.06.21-dev" without needing
        # to parse a SHA. Fallbacks keep the response shape stable.
        "short": commit[:7] if commit and commit != "dev" else "dev",
    }
