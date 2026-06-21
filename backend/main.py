"""FastAPI app entrypoint.

No module-level globals. Long-lived objects (state source, recommendation
service, detector, latest analytics) live on `app.state` so route handlers
get them via `Depends(...)` and tests can swap them per-app.
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys

# Ensure the backend directory is on the path for local imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from analytics.aggregator import compute_waste_summary
from api.camera import router as camera_router
from api.routes import router as api_router
from api.websocket import router as ws_router
from config import ANALYTICS_UPDATE_INTERVAL
import logging_config
from services.recommendation_service import RecommendationService
from settings import Settings, get_settings
from simulation.engine import SimulationEngine, run_simulation_loop
from vision.detector import VideoDetector


logger = logging.getLogger("siteiq.main")


async def _run_analytics_loop(app: FastAPI) -> None:
    """Background task: refresh WasteSummary every ANALYTICS_UPDATE_INTERVAL s
    and tell the rec service to recompute on next access."""
    while True:
        source = getattr(app.state, "source", None)
        rec_service = getattr(app.state, "rec_service", None)
        if source is None or rec_service is None:
            await asyncio.sleep(ANALYTICS_UPDATE_INTERVAL)
            continue
        try:
            app.state.latest_analytics = compute_waste_summary(source)
            rec_service.mark_dirty()
        except Exception:
            logger.exception(
                "analytics_tick_failed",
                extra={"project_id": getattr(source, "project_id", None)},
            )
        await asyncio.sleep(ANALYTICS_UPDATE_INTERVAL)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings: Settings = app.state.settings
    source = SimulationEngine(project_id=settings.default_project_id)
    rec_service = RecommendationService(source)
    detector = VideoDetector()

    app.state.source = source
    app.state.rec_service = rec_service
    app.state.detector = detector
    app.state.latest_analytics = None

    logger.info(
        "vision_initialised",
        extra={"camera_count": len(detector.get_video_ids()),
               "camera_ids": detector.get_video_ids()},
    )

    sim_task = asyncio.create_task(run_simulation_loop(source))
    analytics_task = asyncio.create_task(_run_analytics_loop(app))

    try:
        yield
    finally:
        source.running = False
        sim_task.cancel()
        analytics_task.cancel()
        detector.cleanup()


def create_app(settings: Settings | None = None) -> FastAPI:
    """Factory — used by tests to spin up isolated apps with their own state.

    Pass an explicit `settings` to override env-driven defaults (useful
    for tests that want a specific log level / CORS origin / project).
    """
    cfg = settings or get_settings()
    logging_config.configure(cfg.log_level, cfg.log_format)
    app = FastAPI(title="SiteIQ Backend", lifespan=lifespan)
    app.state.settings = cfg
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cfg.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(api_router)
    app.include_router(ws_router)
    app.include_router(camera_router)
    return app


app = create_app()
