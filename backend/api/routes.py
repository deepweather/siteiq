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
from simulation.site_factory import PROJECT_TEMPLATES
from state.source import SiteStateSource

router = APIRouter()


class SpeedRequest(BaseModel):
    speed: float


class LoadSeedRequest(BaseModel):
    slug: str


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


@router.post("/api/site/load-seed")
async def load_seed_project(
    req: LoadSeedRequest,
    source: SiteStateSource = Depends(get_source),
    rec_service: RecommendationService = Depends(get_rec_service),
    org: Org = Depends(get_current_org),
    db: AsyncSession = Depends(get_db),
):
    """Switch the org's simulation to one of the bundled seed projects
    by slug. Kept for the dashboard's stock-project switcher. Custom
    projects go through `POST /api/projects/{id}/activate` instead."""
    if req.slug not in PROJECT_TEMPLATES:
        raise HTTPException(status_code=404, detail="Project not found")
    # Idempotent: if the engine is already running this slug, don't
    # rebuild it. A rebuild would tear the engine down, wiping the
    # current sim day + every applied recommendation — the same user-
    # facing "I clicked the active project and lost my progress" bug
    # the activate endpoint guards against. Re-loading a *different*
    # seed still flows through `engine.load_project` as before.
    if isinstance(source, SimulationEngine) and source.project_id != req.slug:
        source.load_project(req.slug)
        rec_service.clear()
    # Persist so the choice survives a backend restart.
    org.active_project_id = req.slug
    # Drop any pinned doc version so the next access falls back to the
    # slug-based seed path instead of restoring the previous doc.
    org.active_project_version_id = None
    await db.flush()
    return {"status": "loaded", "slug": req.slug}


@router.post("/api/projects/{project_id}/load", deprecated=True)
async def load_project_legacy(
    project_id: str,
    source: SiteStateSource = Depends(get_source),
    rec_service: RecommendationService = Depends(get_rec_service),
    org: Org = Depends(get_current_org),
    db: AsyncSession = Depends(get_db),
):
    """Backwards-compat alias for the original slug-based load route.

    Removed once the dashboard's TopBar is migrated to call
    `POST /api/site/load-seed` directly. The path string `project_id`
    here is interpreted as a seed slug, not a UUID. UUID-keyed
    activation lives at `POST /api/projects/{uuid}/activate`.
    """
    if project_id not in PROJECT_TEMPLATES:
        raise HTTPException(status_code=404, detail="Project not found")
    if isinstance(source, SimulationEngine):
        source.load_project(project_id)
    rec_service.clear()
    org.active_project_id = project_id
    org.active_project_version_id = None
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
        # Multi-level surface (Phase 6). Single-floor projects emit the
        # one default L0 level + empty connections.
        "levels": [lv.model_dump() for lv in source.site.levels],
        "connections": [c.model_dump() for c in source.connections],
        "discipline": source.site.discipline.value if hasattr(source.site.discipline, "value") else source.site.discipline,
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
    """Mutate the simulation to enact a recommendation.

    Every branch here MUST produce a real, measurable change in the
    next analytics tick — otherwise the green-checkmark UX is a lie.
    """
    rec.applied = True

    # System-of-record: log the optimisation as a ledger event (no-op on
    # sources without the buffer, e.g. a future read-only LiveSource).
    from simulation.event_emit import record_event
    record_event(
        source, "optimization", rec.id, "optimization.applied",
        {
            "rec_id": rec.id,
            "rec_type": rec.type,
            "title": rec.title,
            "target_asset_id": rec.target_asset_id,
            "daily_savings": rec.daily_savings,
            "monthly_savings": rec.monthly_savings,
        },
        source="system",
    )

    # `add_equipment` targets a Connection (elevator), not an Asset.
    # Handle it before the asset lookup so the rest of the function
    # can assume `asset is not None`.
    if rec.type == "add_equipment":
        cabs = getattr(source, "cabs", None)
        if cabs is None:
            return
        cab = cabs.get(rec.target_asset_id)
        if cab is None:
            return
        # Doubling the cab capacity is a coarse stand-in for adding a
        # parallel cab on the same shaft — throughput doubles, the
        # queue empties faster, and vertical-transport waste drops on
        # the next analytics tick. Not a faithful kinematic model
        # (real second cab can be at a different floor at the same
        # instant) but the dashboard-level metric is what the demo
        # surfaces, and that's what changes.
        cab.capacity = max(cab.capacity * 2, cab.capacity + 1)
        cab.extra_cab_count += 1
        return

    asset = source.asset_by_id(rec.target_asset_id)
    if not asset:
        return

    if rec.type == "move_facility" and rec.to_position:
        # Multi-level: keep the asset on its current floor. Without
        # this, `Position(x=..., y=...)` defaults `level_id="L0"` and
        # the asset teleports to the ground floor.
        asset.position = Position(
            x=rec.to_position.x,
            y=rec.to_position.y,
            level_id=asset.position.level_id,
        )
    elif rec.type == "restage_material" and rec.to_position:
        asset.position = Position(
            x=rec.to_position.x,
            y=rec.to_position.y,
            level_id=asset.position.level_id,
        )
    elif rec.type == "release_equipment":
        # Hard release: return to rental pool. The asset is excluded
        # from `compute_equipment_utilization` once REMOVED, so its
        # idle cost contribution drops to zero immediately.
        asset.state = EquipmentState.REMOVED
    elif rec.type == "reschedule_equipment":
        # Batch operations: shrink the IDLE half of the duty cycle.
        # `update_equipment` multiplies the cycle's idle_duration by
        # `meta.get("idle_factor", 1.0)` — 0.4 halves-ish the idle
        # window, lifting utilization toward 60-70%. Real per-tick
        # behavior change; not a marker flag.
        asset.metadata["idle_factor"] = 0.4


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
    level_id: str | None = None,
    source: SiteStateSource = Depends(get_source),
    _: Org = Depends(get_current_org),
):
    """Cumulative foot-traffic density grid for the current sim day.

    Multi-level: pass `?level_id=L0` (or similar) to scope the grid
    to that level. Omit the param to pool every level into one map —
    backwards-compatible with single-floor clients.
    """
    if not isinstance(source, SimulationEngine):
        raise HTTPException(status_code=501, detail="heatmap only available for simulation source")
    return source.density_snapshot(level_id=level_id)
