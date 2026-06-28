"""Tiefbau (civil / underground) discipline-specific simulation logic.

Two pieces today:
  - **Dewatering pumps**: equipment that runs longer-duty cycles than
    a concrete pump (typically 70-80% utilization). Tracked via the
    existing equipment metadata so the same hours_active / hours_idle
    surface flows into the dashboard.
  - **Slope-stability KPI**: zones in EXCAVATION phase that AREN'T
    backed by a sheet-pile / shoring asset within a reasonable radius
    get a compliance score of 0.0; backed zones get 1.0. The KPI
    surfaces as a synthetic line in the asset-detail view and gives
    the demo a "we caught an unshored cut" moment.

Sheet piles are modelled as equipment with subtype "sheet_pile" and a
permanent OPERATING state — they're installed and stay installed.
"""
from __future__ import annotations

from dataclasses import dataclass
from math import sqrt

from models.assets import Asset, EquipmentState
from models.site import Phase, Zone
from state.source import SiteStateSource


# Dewatering pumps cycle ~80% operating / 20% idle (vs concrete pumps
# at ~20% / 80%) because groundwater control runs continuously while
# excavation is open.
DEWATERING_DUTY = {"operate_duration": 3600 * 2, "idle_duration": 3600 * 0.5}

# Distance threshold for a sheet pile to "back" an excavation zone.
SHORING_INFLUENCE_RADIUS_M = 25.0


def update_tiefbau_equipment(asset: Asset, dt_sim: float, engine) -> None:
    """Per-tick behaviour for dewatering pumps + sheet piles.

    Routed to from `engine._tick_tiefbau_assets`. Returns silently for
    any non-Tiefbau-equipment asset so the dispatch is cheap.
    """
    if asset.type != "equipment":
        return
    if asset.subtype == "sheet_pile":
        # Sheet piles are passive — once placed they don't change state.
        # Just keep hours_active accumulating so the dashboard shows
        # them as "installed".
        asset.metadata.setdefault("hours_active", 0.0)
        asset.metadata["hours_active"] += dt_sim / 3600
        return
    if asset.subtype != "dewatering_pump":
        return
    meta = asset.metadata
    meta["cycle_timer"] = meta.get("cycle_timer", 0.0) + dt_sim
    if asset.state == EquipmentState.OPERATING:
        meta["hours_active"] = meta.get("hours_active", 0.0) + dt_sim / 3600
        if meta["cycle_timer"] >= DEWATERING_DUTY["operate_duration"]:
            asset.state = EquipmentState.IDLE
            meta["cycle_timer"] = 0.0
            engine.log_activity(asset.id, "Dewatering paused")
            _emit_state_changed(engine, asset, "idle")
    elif asset.state == EquipmentState.IDLE:
        meta["hours_idle"] = meta.get("hours_idle", 0.0) + dt_sim / 3600
        if meta["cycle_timer"] >= DEWATERING_DUTY["idle_duration"]:
            asset.state = EquipmentState.OPERATING
            meta["cycle_timer"] = 0.0
            engine.log_activity(asset.id, "Dewatering resumed")
            _emit_state_changed(engine, asset, "operating")


def _emit_state_changed(engine, asset: Asset, new_state: str) -> None:
    """Record a dewatering-pump state transition in the ledger (no-op on
    engines without the system-of-record buffer)."""
    from simulation.event_emit import record_event

    record_event(
        engine, "equipment", asset.id, "equipment.state_changed",
        {"equipment_id": asset.id, "subtype": asset.subtype, "state": new_state},
    )


@dataclass(frozen=True)
class ShoringCompliance:
    """Per-zone shoring compliance: 1.0 = backed by a sheet pile within
    the influence radius; 0.0 = uncovered excavation."""

    zone_id: str
    compliance: float
    nearest_sheet_pile_id: str | None
    nearest_distance_m: float | None


def compute_shoring_compliance(source: SiteStateSource) -> list[ShoringCompliance]:
    """For every EXCAVATION-phase zone, find the nearest sheet pile and
    score the zone 1.0 if within range, 0.0 otherwise."""
    excavation_zones: list[Zone] = [
        z for z in source.site.zones if z.phase == Phase.EXCAVATION
    ]
    if not excavation_zones:
        return []
    sheet_piles = [
        a for a in source.assets
        if a.type == "equipment" and a.subtype == "sheet_pile"
    ]
    out: list[ShoringCompliance] = []
    for z in excavation_zones:
        cx = z.x + z.width / 2
        cy = z.y + z.height / 2
        nearest_id: str | None = None
        nearest_dist: float | None = None
        for sp in sheet_piles:
            if sp.position.level_id != z.level_id:
                continue
            dx = sp.position.x - cx
            dy = sp.position.y - cy
            d = sqrt(dx * dx + dy * dy)
            if nearest_dist is None or d < nearest_dist:
                nearest_dist = d
                nearest_id = sp.id
        compliance = 1.0 if (nearest_dist is not None and nearest_dist <= SHORING_INFLUENCE_RADIUS_M) else 0.0
        out.append(ShoringCompliance(
            zone_id=z.id,
            compliance=compliance,
            nearest_sheet_pile_id=nearest_id,
            nearest_distance_m=nearest_dist,
        ))
    return out
