"""System-of-record event emission for the simulation engine.

Kept out of `engine.py` so the engine stays lean (and under its LOC
budget). These free functions operate on any object exposing the engine's
surface (`pending_events`, `sim_day`, `assets`, `worker_internals`), so
they no-op gracefully on lightweight test stubs that lack the buffer.

The engine buffers discrete operational events on state transitions (NOT
every tick); the drain loop in `main.py` flushes them into the ledger.
"""
from __future__ import annotations

from config import WORKDAY_END


def record_event(
    engine,
    subject_type: str,
    subject_id: str,
    kind: str,
    payload: dict,
    *,
    source: str = "simulation",
    confidence: float = 1.0,
    sim_day: int | None = None,
    sim_time: float | None = None,
) -> None:
    """Buffer one operational event. No-op on engines without the buffer.

    Stamps the engine's current project_id + sim clock so a mid-batch
    project switch can be grouped correctly by the drain loop."""
    buf = getattr(engine, "pending_events", None)
    if buf is None:
        return
    buf.append({
        "project_id": engine.project_id,
        "subject_type": subject_type,
        "subject_id": subject_id,
        "kind": kind,
        "payload": payload,
        "source": source,
        "confidence": confidence,
        "sim_day": engine.sim_day if sim_day is None else sim_day,
        "sim_time": engine.sim_time if sim_time is None else sim_time,
    })


def drain(engine) -> list[dict]:
    """Return and clear the buffered events (called by the drain loop)."""
    buf = getattr(engine, "pending_events", None)
    if not buf:
        return []
    out = list(buf)
    buf.clear()
    return out


def emit_end_of_day(engine) -> None:
    """Emit per-worker timesheets + per-equipment daily utilization for the
    day that just completed. Stamped at WORKDAY_END of that day; reads the
    daily counters BEFORE the engine resets them."""
    day = engine.sim_day
    for asset in engine.assets:
        if asset.type == "worker":
            internals = engine.worker_internals.get(asset.id)
            if internals is None:
                continue
            worked = internals.time_working / 3600.0
            walking = internals.time_walking / 3600.0
            facilities = internals.time_at_facilities / 3600.0
            vertical = internals.time_in_vertical_transport / 3600.0
            total = worked + walking + facilities + vertical
            if total < 0.1:
                continue
            record_event(
                engine, "worker", asset.id, "worker.timesheet",
                {
                    "worker_id": asset.id,
                    "trade": asset.subtype,
                    "zone_id": asset.assigned_zone,
                    "day": day,
                    "hours_worked": round(worked, 2),
                    "hours_walking": round(walking, 2),
                    "hours_facilities": round(facilities, 2),
                    "hours_vertical": round(vertical, 2),
                    "hours_total": round(total, 2),
                },
                sim_day=day, sim_time=WORKDAY_END,
            )
        elif asset.type == "equipment":
            meta = asset.metadata
            if asset.state == "removed":
                continue
            active = meta.get("hours_active", 0.0)
            idle = meta.get("hours_idle", 0.0)
            day_active = active - meta.get("_day_active_base", 0.0)
            day_idle = idle - meta.get("_day_idle_base", 0.0)
            meta["_day_active_base"] = active
            meta["_day_idle_base"] = idle
            if day_active <= 0 and day_idle <= 0:
                continue
            record_event(
                engine, "equipment", asset.id, "equipment.utilization",
                {
                    "equipment_id": asset.id,
                    "subtype": asset.subtype,
                    "zone_id": asset.assigned_zone,
                    "day": day,
                    "hours_active": round(day_active, 2),
                    "hours_idle": round(day_idle, 2),
                },
                sim_day=day, sim_time=WORKDAY_END,
            )
