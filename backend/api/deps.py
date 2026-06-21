"""FastAPI dependency providers.

These pull objects off `request.app.state` so route handlers get them
via `Depends(...)` and tests can override them with `app.dependency_overrides`.
No module-level globals here.
"""
from __future__ import annotations

from fastapi import HTTPException, Request

from services.recommendation_service import RecommendationService
from state.source import SiteStateSource
from vision.detector import VideoDetector


def get_source(request: Request) -> SiteStateSource:
    source = getattr(request.app.state, "source", None)
    if source is None:
        raise HTTPException(status_code=503, detail="State source not ready")
    return source


def get_rec_service(request: Request) -> RecommendationService:
    svc = getattr(request.app.state, "rec_service", None)
    if svc is None:
        raise HTTPException(status_code=503, detail="Recommendation service not ready")
    return svc


def get_detector(request: Request) -> VideoDetector:
    det = getattr(request.app.state, "detector", None)
    if det is None:
        raise HTTPException(status_code=503, detail="Detector not ready")
    return det


def get_analytics(request: Request):
    """Latest WasteSummary or None. The analytics loop writes to app.state.latest_analytics."""
    return getattr(request.app.state, "latest_analytics", None)
