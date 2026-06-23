"""Per-builder tests for asset_detail.py.

Each builder is tested with a hand-rolled FakeSource so we don't need to
spin up an entire SimulationEngine — proving the asset_detail service
truly only depends on the SiteStateSource Protocol.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

import pytest

from models.assets import Asset, EquipmentState, Position, WorkerState
from models.site import Site, Zone
from simulation.asset_detail import asset_detail
from simulation.worker_internals import WorkerInternals


@dataclass
class _FakeSource:
    project_id: str = "fake"
    sim_time: float = 0.0
    sim_day: int = 1
    _site: Site = field(default_factory=lambda: Site(
        id="s", name="S", width=100, height=100, current_day=1,
        zones=[
            Zone(id="zone-a", label="Block A", x=10, y=10, width=40, height=40,
                 phase="structural", phase_progress=0.5),
            Zone(id="zone-b", label="Turm Ost", x=60, y=10, width=30, height=40,
                 phase="finishes", phase_progress=0.5),
        ],
        schedule=[],
    ))
    _assets: list[Asset] = field(default_factory=list)
    _internals: dict[str, WorkerInternals] = field(default_factory=dict)
    _activity: dict[str, list[dict]] = field(default_factory=dict)
    _trails: dict[str, list[tuple[float, float]]] = field(default_factory=dict)

    @property
    def site(self) -> Site: return self._site
    @property
    def assets(self) -> list[Asset]: return self._assets
    def asset_by_id(self, asset_id: str) -> Asset | None:
        return next((a for a in self._assets if a.id == asset_id), None)
    def zone_by_id(self, zone_id: str) -> Zone | None:
        return next((z for z in self._site.zones if z.id == zone_id), None)
    def workers_in_zone(self, zone_id: str) -> list[Asset]:
        return [a for a in self._assets if a.type == "worker" and a.assigned_zone == zone_id]
    def worker_internals_for(self, worker_id: str): return self._internals.get(worker_id)
    def activity_log_for(self, asset_id: str) -> Iterable[dict[str, Any]]:
        return self._activity.get(asset_id, [])
    def position_history_for(self, worker_id: str): return self._trails.get(worker_id, [])


# ─── Base detail ─────────────────────────────────────────────────────────

def test_returns_none_for_unknown_asset():
    src = _FakeSource()
    assert asset_detail(src, "ghost") is None


def test_base_fields_present_for_known_asset():
    src = _FakeSource()
    src._assets.append(Asset(
        id="w1", type="worker", subtype="structural",
        position=Position(x=11.111, y=22.222), state=WorkerState.WORKING,
        assigned_zone="zone-a",
    ))
    d = asset_detail(src, "w1")
    assert d["id"] == "w1"
    assert d["type"] == "worker"
    assert d["subtype"] == "structural"
    assert d["state"] == "working"
    # Position is rounded to 1 decimal place
    assert d["x"] == 11.1
    assert d["y"] == 22.2
    assert d["assigned_zone"] == "zone-a"
    # Real zone label substituted (NOT raw ID — bug #16 regression guard)
    assert d["assigned_zone_label"] == "Block A"


def test_assigned_zone_label_none_when_no_assignment():
    src = _FakeSource()
    src._assets.append(Asset(
        id="t1", type="facility", subtype="toilet",
        position=Position(x=0, y=0), state="active",
    ))
    d = asset_detail(src, "t1")
    assert d["assigned_zone"] is None
    assert d["assigned_zone_label"] is None


# ─── Worker builder ──────────────────────────────────────────────────────

def test_worker_detail_uses_typed_internals():
    src = _FakeSource()
    src._assets.append(Asset(
        id="w1", type="worker", subtype="finishing",
        position=Position(x=0, y=0), state=WorkerState.WORKING,
        assigned_zone="zone-a",
    ))
    src._internals["w1"] = WorkerInternals(
        next_toilet=0, next_break=0, next_material=0,
        time_working=600, time_walking=200, time_at_facilities=100,
        toilet_trips_today=2, toilet_total_round_trip=400,
        material_trips_today=1, material_total_round_trip=300,
        total_distance=42.0,
    )
    d = asset_detail(src, "w1")
    assert d["detail"]["productivity"] == round(600 / 900, 3)
    assert d["detail"]["total_distance_m"] == 42.0
    assert d["detail"]["toilet_trips_today"] == 2
    assert d["detail"]["avg_toilet_round_trip_min"] == round(400 / 2 / 60, 1)
    assert d["detail"]["material_trips_today"] == 1


def test_worker_detail_handles_missing_internals():
    src = _FakeSource()
    src._assets.append(Asset(
        id="w1", type="worker", subtype="finishing",
        position=Position(x=0, y=0), state=WorkerState.WORKING,
        assigned_zone="zone-a",
    ))
    # No internals registered — builder should return {} not crash
    d = asset_detail(src, "w1")
    assert d["detail"] == {}


def test_worker_trail_at_top_level_not_nested():
    """API contract preservation: trail lives on base, not under detail."""
    src = _FakeSource()
    src._assets.append(Asset(
        id="w1", type="worker", subtype="finishing",
        position=Position(x=0, y=0), state=WorkerState.WORKING,
        assigned_zone="zone-a",
    ))
    src._internals["w1"] = WorkerInternals(next_toilet=0, next_break=0, next_material=0)
    src._trails["w1"] = [(0, 0), (1, 1), (2, 2)]
    d = asset_detail(src, "w1")
    assert d["trail"] == [(0, 0), (1, 1), (2, 2)]
    assert "trail" not in d["detail"]


# ─── Equipment builder ───────────────────────────────────────────────────

def test_equipment_detail_calculates_utilization_and_cost():
    src = _FakeSource()
    src._assets.append(Asset(
        id="crane-1", type="equipment", subtype="tower_crane",
        position=Position(x=50, y=50), state=EquipmentState.OPERATING,
        metadata={"hours_active": 5.0, "hours_idle": 6.0, "cycle_timer": 100},
    ))
    d = asset_detail(src, "crane-1")
    assert d["detail"]["utilization"] == round(5.0 / 11.0, 3)
    assert d["detail"]["hours_active"] == 5.0
    assert d["detail"]["hours_idle"] == 6.0
    # daily idle cost = idle_fraction × 11h × €180/h = 6/11 × 11 × 180 = €1080
    assert d["detail"]["daily_idle_cost"] == 1080.0


def test_equipment_detail_handles_zero_data():
    """Brand-new equipment has 0 hours_active/hours_idle. Don't crash."""
    src = _FakeSource()
    src._assets.append(Asset(
        id="pump-1", type="equipment", subtype="concrete_pump",
        position=Position(x=0, y=0), state=EquipmentState.IDLE,
        metadata={},
    ))
    d = asset_detail(src, "pump-1")
    # Total is ~0 → fall back to 0.5 utilization
    assert d["detail"]["utilization"] == 0.5


# ─── Facility builder ────────────────────────────────────────────────────

@pytest.mark.parametrize("subtype,radius,required_state", [
    ("toilet", 5, "at_toilet"),
    ("breakroom", 10, "at_break"),
    ("office", 15, None),
    ("toolcrib", 8, None),
])
def test_facility_radius_and_state_rules(subtype, radius, required_state):
    src = _FakeSource()
    facility_pos = Position(x=50, y=50)
    src._assets.append(Asset(
        id="f1", type="facility", subtype=subtype,
        position=facility_pos, state="active",
    ))
    # Worker inside radius, in the required state (if any)
    src._assets.append(Asset(
        id="w_in", type="worker", subtype="general",
        position=Position(x=facility_pos.x + (radius - 1), y=facility_pos.y),
        state=required_state if required_state else WorkerState.WORKING,
        assigned_zone="zone-a",
    ))
    # Worker outside radius
    src._assets.append(Asset(
        id="w_out", type="worker", subtype="general",
        position=Position(x=facility_pos.x + (radius + 5), y=facility_pos.y),
        state=required_state if required_state else WorkerState.WORKING,
        assigned_zone="zone-a",
    ))
    # Worker inside radius but WRONG state (only matters when required_state set)
    src._assets.append(Asset(
        id="w_wrong_state", type="worker", subtype="general",
        position=Position(x=facility_pos.x + (radius - 1), y=facility_pos.y + 1),
        state=WorkerState.WORKING,
        assigned_zone="zone-a",
    ))
    d = asset_detail(src, "f1")
    present = {p["id"] for p in d["detail"]["workers_present"]}
    assert "w_in" in present
    assert "w_out" not in present
    if required_state and required_state != WorkerState.WORKING:
        assert "w_wrong_state" not in present


# ─── Material builder ────────────────────────────────────────────────────

def test_material_detail_includes_zone_label_and_distance():
    src = _FakeSource()
    src._assets.append(Asset(
        id="mat-rebar", type="material", subtype="rebar",
        position=Position(x=5, y=5), state="staged",
        metadata={"needed_in_zone": "zone-b"},
    ))
    d = asset_detail(src, "mat-rebar")
    # zone-b center: (60+15, 10+20) = (75, 30) ; from (5,5) = sqrt(70² + 25²) ≈ 74.3
    assert d["detail"]["needed_in_zone"] == "zone-b"
    assert d["detail"]["needed_in_zone_label"] == "Turm Ost"
    assert d["detail"]["distance_to_zone_m"] > 0


def test_material_detail_no_target_zone():
    src = _FakeSource()
    src._assets.append(Asset(
        id="mat-loose", type="material", subtype="rebar",
        position=Position(x=0, y=0), state="staged",
        metadata={},
    ))
    d = asset_detail(src, "mat-loose")
    assert d["detail"]["needed_in_zone"] is None
    assert d["detail"]["needed_in_zone_label"] is None
    assert d["detail"]["distance_to_zone_m"] is None


# ─── Activity log ────────────────────────────────────────────────────────

def test_activity_log_attached_to_response():
    src = _FakeSource()
    src._assets.append(Asset(
        id="w1", type="worker", subtype="general",
        position=Position(x=0, y=0), state=WorkerState.WORKING,
        assigned_zone="zone-a",
    ))
    src._internals["w1"] = WorkerInternals(next_toilet=0, next_break=0, next_material=0)
    src._activity["w1"] = [
        {"time": 100, "day": 1, "event": "Started work"},
        {"time": 200, "day": 1, "event": "Walking to toilet"},
    ]
    d = asset_detail(src, "w1")
    assert len(d["activity_log"]) == 2
    assert d["activity_log"][-1]["event"] == "Walking to toilet"


# ─── Engine size budget ──────────────────────────────────────────────────

def test_simulation_engine_loc_is_reasonable():
    """Guardrail against god-object regression.

    Original engine was 243 LOC. Step 4 extracted AssetDetailService and
    brought it to 124. Subsequent additions:
      - step 6: `_rebuild_indexes` + indexed-lookup methods (~25 LOC)
      - heatmap: 1 field + 2 small methods (~10 LOC)
      - Phase 1: `load_document` + ProjectDocument-aware constructor (~25 LOC)
      - Phase 2: per-level facility + connection indexes,
        `workers_in_level`, `connections_from_level` (~35 LOC)
      - Phase 3: `cabs` instantiation + `_tick_cabs` wrapper (~20 LOC)
      - Phase 6 audit fix: cabs summary in WS state snapshot (~15 LOC)
    Budget = 340 keeps responsibility creep visible without being too tight."""
    from pathlib import Path
    engine_py = Path(__file__).parent.parent / "simulation" / "engine.py"
    loc = sum(1 for _ in engine_py.read_text().splitlines())
    assert loc <= 340, f"engine.py is {loc} LOC — over the budget of 340"
