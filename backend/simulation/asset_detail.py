"""AssetDetailService — builds the detail view for any asset.

Replaces the 130-line `SimulationEngine.get_asset_detail()` god-method.
Per-type builders are dispatched via a table, so adding a new asset type
means: define `_my_type_detail(...)` and add one line to `DETAIL_BUILDERS`.
"""
from __future__ import annotations

from math import sqrt
from typing import Any, Callable

from models.assets import Asset
from simulation.equipment_behavior import EQUIPMENT_DUTY_CYCLES
from simulation.worker_internals import WorkerInternals
from state.source import SiteStateSource
from config import (
    CRANE_HOURLY_RATE, EXCAVATOR_HOURLY_RATE, PUMP_HOURLY_RATE,
    WORKDAY_END, WORKDAY_START,
)

_WORKDAY_HOURS = (WORKDAY_END - WORKDAY_START) / 3600
_EQUIPMENT_RATES = {
    "tower_crane": CRANE_HOURLY_RATE,
    "concrete_pump": PUMP_HOURLY_RATE,
    "excavator": EXCAVATOR_HOURLY_RATE,
}


def asset_detail(source: SiteStateSource, asset_id: str) -> dict[str, Any] | None:
    """Build the AssetDetail dict served by GET /api/assets/{id}.

    Returns None if no asset exists with that ID. Otherwise returns a
    dict ready to JSON-serialize.
    """
    asset = source.asset_by_id(asset_id)
    if asset is None:
        return None

    base = _base_detail(source, asset)

    builder = _DETAIL_BUILDERS.get(asset.type)
    if builder is not None:
        base["detail"] = builder(source, asset)

    # Workers have a movement trail rendered on the map — preserve original
    # API contract by exposing it at the top level (not nested under detail).
    if asset.type == "worker":
        base["trail"] = list(source.position_history_for(asset_id))

    base["activity_log"] = list(source.activity_log_for(asset_id))
    return base


# ─── Base header ─────────────────────────────────────────────────────────

def _base_detail(source: SiteStateSource, asset: Asset) -> dict[str, Any]:
    assigned_zone_label = None
    if asset.assigned_zone:
        z = source.zone_by_id(asset.assigned_zone)
        if z is not None:
            assigned_zone_label = z.label

    return {
        "id": asset.id,
        "type": asset.type,
        "subtype": asset.subtype,
        "x": round(asset.position.x, 1),
        "y": round(asset.position.y, 1),
        "state": asset.state,
        "assigned_zone": asset.assigned_zone,
        "assigned_zone_label": assigned_zone_label,
    }


# ─── Worker ──────────────────────────────────────────────────────────────

def _worker_detail(source: SiteStateSource, asset: Asset) -> dict[str, Any]:
    internals = source.worker_internals_for(asset.id)
    if internals is None:
        return {}

    # Allow either typed WorkerInternals or a raw dict (FakeSource paths)
    if isinstance(internals, WorkerInternals):
        t_work = internals.time_working
        t_walk = internals.time_walking
        t_fac = internals.time_at_facilities
        total_dist = internals.total_distance
        toilet_trips = internals.toilet_trips_today
        toilet_rt = internals.toilet_total_round_trip
        mat_trips = internals.material_trips_today
        mat_rt = internals.material_total_round_trip
    else:
        t_work = internals.get("time_working", 0)
        t_walk = internals.get("time_walking", 0)
        t_fac = internals.get("time_at_facilities", 0)
        total_dist = internals.get("total_distance", 0)
        toilet_trips = internals.get("toilet_trips_today", 0)
        toilet_rt = internals.get("toilet_total_round_trip", 0)
        mat_trips = internals.get("material_trips_today", 0)
        mat_rt = internals.get("material_total_round_trip", 0)

    total_t = t_work + t_walk + t_fac
    productivity = t_work / total_t if total_t > 0 else 0
    avg_toilet_rt = (toilet_rt / toilet_trips / 60) if toilet_trips > 0 else 0
    avg_mat_rt = (mat_rt / mat_trips / 60) if mat_trips > 0 else 0

    return {
        "productivity": round(productivity, 3),
        "total_distance_m": round(total_dist, 1),
        "toilet_trips_today": toilet_trips,
        "avg_toilet_round_trip_min": round(avg_toilet_rt, 1),
        "material_trips_today": mat_trips,
        "avg_material_round_trip_min": round(avg_mat_rt, 1),
        "time_working_s": round(t_work, 0),
        "time_walking_s": round(t_walk, 0),
        "time_at_facilities_s": round(t_fac, 0),
    }


# ─── Equipment ───────────────────────────────────────────────────────────

def _equipment_detail(_source: SiteStateSource, asset: Asset) -> dict[str, Any]:
    hours_active = asset.metadata.get("hours_active", 0)
    hours_idle = asset.metadata.get("hours_idle", 0)
    total = hours_active + hours_idle
    utilization = hours_active / total if total > 0.01 else 0.5
    cycle = EQUIPMENT_DUTY_CYCLES.get(asset.subtype, {})
    rate = _EQUIPMENT_RATES.get(asset.subtype, 200)
    daily_idle_cost = (1 - utilization) * _WORKDAY_HOURS * rate

    return {
        "utilization": round(utilization, 3),
        "hours_active": round(hours_active, 2),
        "hours_idle": round(hours_idle, 2),
        "daily_idle_cost": round(daily_idle_cost, 2),
        "cycle_timer_s": round(asset.metadata.get("cycle_timer", 0), 0),
        "operate_duration_s": cycle.get("operate_duration", 0),
        "idle_duration_s": cycle.get("idle_duration", 0),
    }


# ─── Facility ────────────────────────────────────────────────────────────

# Proximity radius (m) for "who's currently here" lookup per facility type
_FACILITY_RADIUS = {
    "toilet": 5,
    "breakroom": 10,
    "office": 15,
    "toolcrib": 8,
}
# Some facility types only count workers in a specific FSM state; others
# (office, toolcrib) just count proximity.
_FACILITY_STATE = {
    "toilet": "at_toilet",
    "breakroom": "at_break",
}


def _facility_detail(source: SiteStateSource, asset: Asset) -> dict[str, Any]:
    radius = _FACILITY_RADIUS.get(asset.subtype, 10)
    required_state = _FACILITY_STATE.get(asset.subtype)

    workers_here = []
    for a in source.assets:
        if a.type != "worker":
            continue
        if required_state and a.state != required_state:
            continue
        d = sqrt(
            (a.position.x - asset.position.x) ** 2
            + (a.position.y - asset.position.y) ** 2
        )
        if d < radius:
            workers_here.append({"id": a.id, "subtype": a.subtype})
    return {"workers_present": workers_here}


# ─── Material ────────────────────────────────────────────────────────────

def _material_detail(source: SiteStateSource, asset: Asset) -> dict[str, Any]:
    target_zone_id = asset.metadata.get("needed_in_zone")
    dist = None
    target_zone_label = None
    if target_zone_id:
        zone = source.zone_by_id(target_zone_id)
        if zone is not None:
            target_zone_label = zone.label
            dx = asset.position.x - (zone.x + zone.width / 2)
            dy = asset.position.y - (zone.y + zone.height / 2)
            dist = round(sqrt(dx * dx + dy * dy), 1)
    return {
        "needed_in_zone": target_zone_id,
        "needed_in_zone_label": target_zone_label,
        "distance_to_zone_m": dist,
    }


# Dispatch table — adding a new asset type means: write a builder + add a line.
_DETAIL_BUILDERS: dict[str, Callable[[SiteStateSource, Asset], dict[str, Any]]] = {
    "worker": _worker_detail,
    "equipment": _equipment_detail,
    "facility": _facility_detail,
    "material": _material_detail,
}
