from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()

# These get set by main.py after engine initialization
_engine = None
_recommendations_cache: list = []
_get_recommendations = None


def init_routes(engine, get_recs_fn):
    global _engine, _get_recommendations
    _engine = engine
    _get_recommendations = get_recs_fn


class SpeedRequest(BaseModel):
    speed: float


@router.get("/api/projects")
async def list_projects():
    from simulation.site_factory import get_project_list
    return get_project_list()


@router.get("/api/portfolio")
async def get_portfolio():
    """Returns simulated portfolio metrics for all project templates."""
    from simulation.site_factory import PROJECT_TEMPLATES
    portfolio = []
    for key, tmpl in PROJECT_TEMPLATES.items():
        total_workers = sum(count for zdef in tmpl["zones"] for _, count in zdef["workers"])
        total_equipment = len(tmpl["equipment"])
        idle_equipment = sum(1 for e in tmpl["equipment"] if e["state"] == "idle")
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
            "estimated_monthly_waste": round(total_workers * 50 * 0.12 * 22 + total_equipment * 150 * 0.4 * 11 * 22, 0),
            "active": key == (_engine.project_id if _engine else "westhafen"),
        })
    return portfolio


@router.post("/api/projects/{project_id}/load")
async def load_project(project_id: str):
    if not _engine:
        raise HTTPException(status_code=503, detail="Engine not ready")
    from simulation.site_factory import PROJECT_TEMPLATES
    if project_id not in PROJECT_TEMPLATES:
        raise HTTPException(status_code=404, detail="Project not found")
    _engine.load_project(project_id)
    global _recommendations_cache
    _recommendations_cache = []
    return {"status": "loaded", "project_id": project_id}


@router.get("/api/site")
async def get_site():
    if not _engine:
        raise HTTPException(status_code=503, detail="Engine not ready")
    return {
        "id": _engine.site.id,
        "name": _engine.site.name,
        "width": _engine.site.width,
        "height": _engine.site.height,
        "zones": [z.model_dump() for z in _engine.site.zones],
        "current_day": _engine.sim_day,
        "schedule": [s.model_dump() for s in _engine.site.schedule],
    }


@router.get("/api/recommendations")
async def get_recommendations():
    if not _engine:
        raise HTTPException(status_code=503, detail="Engine not ready")
    recs = _get_recommendations()
    return [r.model_dump() for r in recs]


@router.post("/api/recommendations/{rec_id}/apply")
async def apply_recommendation(rec_id: str):
    if not _engine:
        raise HTTPException(status_code=503, detail="Engine not ready")
    recs = _get_recommendations()
    rec = None
    for r in recs:
        if r.id == rec_id:
            rec = r
            break
    if not rec:
        raise HTTPException(status_code=404, detail="Recommendation not found")
    if rec.applied:
        return {"status": "already_applied"}

    _apply_rec(rec)
    return {"status": "applied", "id": rec.id}


@router.post("/api/recommendations/apply-all")
async def apply_all():
    if not _engine:
        raise HTTPException(status_code=503, detail="Engine not ready")
    recs = _get_recommendations()
    applied = 0
    for r in recs:
        if not r.applied:
            _apply_rec(r)
            applied += 1
    return {"status": "ok", "applied": applied}


def _apply_rec(rec):
    from models.assets import Position, EquipmentState

    rec.applied = True
    asset = _engine.get_asset_by_id(rec.target_asset_id)
    if not asset:
        return

    if rec.type == "move_facility" and rec.to_position:
        asset.position = Position(x=rec.to_position["x"], y=rec.to_position["y"])
    elif rec.type == "restage_material" and rec.to_position:
        asset.position = Position(x=rec.to_position["x"], y=rec.to_position["y"])
    elif rec.type == "reschedule_equipment":
        if rec.to_position is None:
            asset.state = EquipmentState.REMOVED


@router.get("/api/assets/{asset_id}")
async def get_asset_detail(asset_id: str):
    if not _engine:
        raise HTTPException(status_code=503, detail="Engine not ready")
    detail = _engine.get_asset_detail(asset_id)
    if not detail:
        raise HTTPException(status_code=404, detail="Asset not found")
    return detail


@router.post("/api/simulation/speed")
async def set_speed(req: SpeedRequest):
    if not _engine:
        raise HTTPException(status_code=503, detail="Engine not ready")
    _engine.speed_multiplier = max(0.5, min(20.0, req.speed))
    return {"speed": _engine.speed_multiplier}


@router.post("/api/simulation/pause")
async def toggle_pause():
    if not _engine:
        raise HTTPException(status_code=503, detail="Engine not ready")
    _engine.paused = not _engine.paused
    return {"paused": _engine.paused}


@router.get("/api/simulation/state")
async def get_sim_state():
    if not _engine:
        raise HTTPException(status_code=503, detail="Engine not ready")
    return _engine.get_state_snapshot()
