"""REST API routes.

All dependencies (state source, recommendation service) flow through
FastAPI's Depends — no module-level globals. Route handlers are pure
functions of their inputs, which makes them trivially testable.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_current_org, get_rec_service, get_source
from db.models import Org
from db.session import get_db
from models.assets import Position, EquipmentState
from services.recommendation_service import RecommendationService
from simulation.engine import SimulationEngine
from simulation.site_factory import PROJECT_TEMPLATES, get_project_list
from state.source import SiteStateSource

router = APIRouter()


class SpeedRequest(BaseModel):
    speed: float


@router.get("/api/projects")
async def list_projects(_: Org = Depends(get_current_org)):
    return get_project_list()


@router.get("/api/portfolio")
async def get_portfolio(
    request: Request,
    source: SiteStateSource = Depends(get_source),
    _: Org = Depends(get_current_org),
):
    """Returns per-project portfolio metrics for every template.

    Waste numbers come from `services.portfolio_estimator` which warms a
    transient `SimulationEngine` per project at app startup — so each
    card shows the actual `compute_waste_summary` output for that
    template, not a coarse formula.
    """
    estimates = getattr(request.app.state, "portfolio_estimates", {})
    portfolio = []
    for key, tmpl in PROJECT_TEMPLATES.items():
        est = estimates.get(key)
        total_workers = (
            est.total_workers
            if est is not None
            else sum(count for zdef in tmpl["zones"] for _, count in zdef["workers"])
        )
        total_equipment = est.total_equipment if est is not None else len(tmpl["equipment"])
        idle_equipment = (
            est.idle_equipment
            if est is not None
            else sum(1 for e in tmpl["equipment"] if e["state"] == "idle")
        )
        portfolio.append({
            "id": key,
            "name": tmpl["name"],
            "type": tmpl["type"],
            "description": tmpl["description"],
            "workers": total_workers,
            "equipment": total_equipment,
            "idle_equipment": idle_equipment,
            "zones": len(tmpl["zones"]),
            "day": tmpl["start_day"],
            "site_width": tmpl["width"],
            "site_height": tmpl["height"],
            "estimated_daily_waste": est.daily_waste if est is not None else 0.0,
            "estimated_monthly_waste": (
                est.monthly_waste
                if est is not None
                # Fallback formula — only used if the estimator ran into
                # an exception at startup.
                else round(
                    total_workers * 50 * 0.12 * 22
                    + total_equipment * 150 * 0.4 * 11 * 22,
                    0,
                )
            ),
            "active": key == source.project_id,
        })
    return portfolio


@router.post("/api/projects/{project_id}/load")
async def load_project(
    project_id: str,
    source: SiteStateSource = Depends(get_source),
    rec_service: RecommendationService = Depends(get_rec_service),
    org: Org = Depends(get_current_org),
    db: AsyncSession = Depends(get_db),
):
    if project_id not in PROJECT_TEMPLATES:
        raise HTTPException(status_code=404, detail="Project not found")
    # The source's project-switch capability is simulation-specific. We accept
    # the duck-typed approach for now — LiveSource would expose its own
    # "subscribe to a different site" semantics.
    if isinstance(source, SimulationEngine):
        source.load_project(project_id)
    rec_service.clear()
    # Persist so the choice survives a backend restart (the registry
    # rebuilds engines from `org.active_project_id` on first access).
    org.active_project_id = project_id
    await db.flush()
    return {"status": "loaded", "project_id": project_id}


@router.get("/api/site")
async def get_site(
    source: SiteStateSource = Depends(get_source),
    _: Org = Depends(get_current_org),
):
    return {
        "id": source.site.id,
        "name": source.site.name,
        "width": source.site.width,
        "height": source.site.height,
        "zones": [z.model_dump() for z in source.site.zones],
        "current_day": source.sim_day,
        "schedule": [s.model_dump() for s in source.site.schedule],
    }


@router.get("/api/recommendations")
async def get_recommendations(
    rec_service: RecommendationService = Depends(get_rec_service),
    _: Org = Depends(get_current_org),
):
    return [r.model_dump() for r in rec_service.get()]


@router.post("/api/recommendations/{rec_id}/apply")
async def apply_recommendation(
    rec_id: str,
    source: SiteStateSource = Depends(get_source),
    rec_service: RecommendationService = Depends(get_rec_service),
    _: Org = Depends(get_current_org),
):
    rec = rec_service.by_id(rec_id)
    if not rec:
        raise HTTPException(status_code=404, detail="Recommendation not found")
    if rec.applied:
        return {"status": "already_applied"}
    _apply_rec(rec, source)
    return {"status": "applied", "id": rec.id}


@router.post("/api/recommendations/apply-all")
async def apply_all(
    source: SiteStateSource = Depends(get_source),
    rec_service: RecommendationService = Depends(get_rec_service),
    _: Org = Depends(get_current_org),
):
    applied = 0
    for r in rec_service.get():
        if not r.applied:
            _apply_rec(r, source)
            applied += 1
    return {"status": "ok", "applied": applied}


def _apply_rec(rec, source: SiteStateSource) -> None:
    rec.applied = True
    asset = source.asset_by_id(rec.target_asset_id)
    if not asset:
        return
    if rec.type == "move_facility" and rec.to_position:
        asset.position = Position(x=rec.to_position.x, y=rec.to_position.y)
    elif rec.type == "restage_material" and rec.to_position:
        asset.position = Position(x=rec.to_position.x, y=rec.to_position.y)
    elif rec.type == "reschedule_equipment":
        if rec.to_position is None:
            asset.state = EquipmentState.REMOVED


@router.get("/api/assets/{asset_id}")
async def get_asset_detail(
    asset_id: str,
    source: SiteStateSource = Depends(get_source),
    _: Org = Depends(get_current_org),
):
    from simulation.asset_detail import asset_detail
    detail = asset_detail(source, asset_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Asset not found")
    return detail


@router.post("/api/simulation/speed")
async def set_speed(
    req: SpeedRequest,
    source: SiteStateSource = Depends(get_source),
    _: Org = Depends(get_current_org),
):
    # Simulation-specific control surface
    if not isinstance(source, SimulationEngine):
        raise HTTPException(status_code=501, detail="speed control only available for simulation source")
    source.speed_multiplier = max(0.5, min(20.0, req.speed))
    return {"speed": source.speed_multiplier}


@router.post("/api/simulation/pause")
async def toggle_pause(
    source: SiteStateSource = Depends(get_source),
    _: Org = Depends(get_current_org),
):
    if not isinstance(source, SimulationEngine):
        raise HTTPException(status_code=501, detail="pause only available for simulation source")
    source.paused = not source.paused
    return {"paused": source.paused}


@router.get("/api/simulation/state")
async def get_sim_state(
    source: SiteStateSource = Depends(get_source),
    _: Org = Depends(get_current_org),
):
    if not isinstance(source, SimulationEngine):
        raise HTTPException(status_code=501, detail="state snapshot only available for simulation source")
    return source.get_state_snapshot()


@router.get("/api/simulation/heatmap")
async def get_heatmap(
    source: SiteStateSource = Depends(get_source),
    _: Org = Depends(get_current_org),
):
    """Cumulative foot-traffic density grid for the current sim day."""
    if not isinstance(source, SimulationEngine):
        raise HTTPException(status_code=501, detail="heatmap only available for simulation source")
    return source.density_snapshot()
