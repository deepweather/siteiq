"""FastAPI app entrypoint.

No module-level globals. Long-lived objects (state source, recommendation
service, detector, latest analytics, DB session factory, email sender,
rate limiter) live on `app.state` so route handlers get them via
`Depends(...)` and tests can swap them per-app.
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys

# Ensure the backend directory is on the path for local imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from starlette.exceptions import HTTPException as StarletteHTTPException

from analytics.aggregator import compute_waste_summary
from api.camera import router as camera_router
from api.dev import router as dev_router
from api.health import router as health_router
from api.projects import router as projects_router
from api.project_assets import router as project_assets_router
from api.request_id import RequestIdMiddleware
from api.routes import router as api_router
from api.security_headers import SecurityHeadersMiddleware
from api.websocket import router as ws_router
from auth.auth_cleanup import run_cleanup_loop as run_auth_cleanup
from auth.csrf import CSRFMiddleware
from auth.email_sender import build_sender_from_settings
from auth.outbox_cleanup import run_cleanup_loop as run_outbox_cleanup
from auth.rate_limit import configure_storage, limiter, rate_limit_handler
from auth.routes import router as auth_router
from config import ANALYTICS_UPDATE_INTERVAL, SIM_TICK_INTERVAL
from db.engine import create_db_engine
import logging_config
from orgs.routes import router as orgs_router
from seeds.importer import import_seed_projects
from services.portfolio_estimator import compute_all_estimates
from settings import Settings, get_settings
from state.registry import make_registry, run_loops_for_registry
from vision.detector import VideoDetector


logger = logging.getLogger("siteiq.main")


async def _run_analytics_loop(app: FastAPI) -> None:
    """Background task: refresh WasteSummary for every active engine
    every ANALYTICS_UPDATE_INTERVAL s and tell the matching rec service
    to recompute on next access."""
    while True:
        registry = getattr(app.state, "registry", None)
        if registry is None:
            await asyncio.sleep(ANALYTICS_UPDATE_INTERVAL)
            continue
        for org_id, source in registry.items():
            try:
                summary = compute_waste_summary(source)
                registry.set_latest_analytics(org_id, summary)
                registry.rec_service_for(org_id).mark_dirty()
            except Exception:
                logger.exception(
                    "analytics_tick_failed",
                    extra={
                        "org_id": org_id,
                        "project_id": getattr(source, "project_id", None),
                    },
                )
        await asyncio.sleep(ANALYTICS_UPDATE_INTERVAL)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings: Settings = app.state.settings

    # ---- DB ----
    engine, session_factory = create_db_engine(settings.database_url)
    app.state.db_engine = engine
    app.state.db_session_factory = session_factory

    # ---- Email ----
    app.state.email_sender = build_sender_from_settings(settings)

    # ---- Rate limit ----
    # Module-level singleton so the @limiter.limit decorators on auth
    # routes can resolve at import time. We swap its storage to Redis in
    # prod. Tests flip `app.state.limiter.enabled = False` to opt out.
    configure_storage(settings.rate_limit_redis_url)
    app.state.limiter = limiter

    # ---- Seeds ----
    # Import the bundled `seeds/projects/*.json` documents as public-template
    # rows. Idempotent: same content hash → no-op. Updated seed → new version.
    try:
        await import_seed_projects(session_factory)
    except Exception:
        logger.exception("seed_import_failed")

    # ---- Simulation ----
    registry = make_registry(default_project_id=settings.default_project_id)
    detector = VideoDetector()
    # Per-project portfolio waste estimates — deterministic given the
    # templates, so compute once at startup and cache for app lifetime.
    # Tests can opt out via SITEIQ_COMPUTE_PORTFOLIO_AT_STARTUP=false to
    # keep TestClient lifespans fast.
    portfolio_estimates = (
        compute_all_estimates() if settings.compute_portfolio_at_startup else {}
    )

    app.state.registry = registry
    app.state.detector = detector
    app.state.portfolio_estimates = portfolio_estimates

    logger.info(
        "vision_initialised",
        extra={"camera_count": len(detector.get_video_ids()),
               "camera_ids": detector.get_video_ids()},
    )

    sim_task = asyncio.create_task(
        run_loops_for_registry(registry, tick_interval=SIM_TICK_INTERVAL)
    )
    analytics_task = asyncio.create_task(_run_analytics_loop(app))
    outbox_task = asyncio.create_task(
        run_outbox_cleanup(
            session_factory,
            retention_days=settings.email_outbox_retention_days,
            interval_seconds=settings.email_outbox_cleanup_interval_seconds,
        )
    )
    auth_cleanup_task = asyncio.create_task(
        run_auth_cleanup(
            session_factory,
            session_retention_days=settings.auth_session_retention_days,
            token_retention_days=settings.auth_token_retention_days,
            interval_seconds=settings.auth_cleanup_interval_seconds,
        )
    )

    try:
        yield
    finally:
        for eng in registry.all_engines():
            eng.running = False
        bg_tasks = (sim_task, analytics_task, outbox_task, auth_cleanup_task)
        for task in bg_tasks:
            task.cancel()
        # Drain the cancellations — without this, `engine.dispose()` can
        # race with an in-flight cleanup and the lifespan never
        # returns control to the TestClient.
        for task in bg_tasks:
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass
        detector.cleanup()
        await engine.dispose()


def create_app(settings: Settings | None = None) -> FastAPI:
    """Factory — used by tests to spin up isolated apps with their own state.

    Pass an explicit `settings` to override env-driven defaults (useful
    for tests that want a specific log level / CORS origin / project).
    """
    cfg = settings or get_settings()
    logging_config.configure(cfg.log_level, cfg.log_format)
    app = FastAPI(title="SiteIQ Backend", lifespan=lifespan)
    app.state.settings = cfg

    # Order matters: CORS first (handles preflight), then CSRF, then routes.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cfg.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(
        CSRFMiddleware,
        allowed_origins=cfg.cors_origins,
    )
    # Outermost: every response gets baseline security headers.
    # SecurityHeadersMiddleware is a pure ASGI middleware (not
    # BaseHTTPMiddleware) — required for the stack to play nicely with
    # the TestClient.
    app.add_middleware(
        SecurityHeadersMiddleware,
        is_prod=cfg.is_prod,
        frontend_origin=cfg.frontend_origin,
    )
    # Even further out: request-id binding. Every log emitted while
    # serving a request will carry the same id, and the response echoes
    # it on `X-Request-Id` so support tickets are searchable.
    app.add_middleware(RequestIdMiddleware)

    # Standard error envelope. The frontend expects {error: {code, message, field?, request_id?}}.
    @app.exception_handler(StarletteHTTPException)
    async def _http_exc(request: Request, exc: StarletteHTTPException):
        from api.request_id import get_current_request_id
        rid = get_current_request_id()
        if isinstance(exc.detail, dict) and "error" in exc.detail:
            payload = dict(exc.detail)
            if rid:
                payload["error"] = {**payload["error"], "request_id": rid}
            return JSONResponse(status_code=exc.status_code, content=payload)
        err = {"code": "http_error", "message": str(exc.detail)}
        if rid:
            err["request_id"] = rid
        return JSONResponse(status_code=exc.status_code, content={"error": err})

    @app.exception_handler(RateLimitExceeded)
    async def _rate_limit_exc(request: Request, exc: RateLimitExceeded):
        return await rate_limit_handler(request, exc)

    @app.exception_handler(RequestValidationError)
    async def _validation_exc(request: Request, exc: RequestValidationError):
        # Surface the first field-error as the canonical envelope.
        errors = exc.errors()
        if errors:
            first = errors[0]
            field = ".".join(str(p) for p in first.get("loc", []) if p not in ("body", "query"))
            return JSONResponse(
                status_code=422,
                content={
                    "error": {
                        "code": "validation_error",
                        "message": first.get("msg", "Invalid input"),
                        "field": field or None,
                    }
                },
            )
        return JSONResponse(
            status_code=422,
            content={"error": {"code": "validation_error", "message": "Invalid input"}},
        )

    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(orgs_router)
    app.include_router(projects_router)
    app.include_router(project_assets_router)
    app.include_router(api_router)
    app.include_router(ws_router)
    app.include_router(camera_router)
    if cfg.is_dev:
        app.include_router(dev_router)
    return app


app = create_app()
