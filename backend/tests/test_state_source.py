"""Proves analytics + optimization depend ONLY on the SiteStateSource
Protocol — not on any concrete SimulationEngine.

We construct a `FakeSource` from scratch (no engine, no FSM, no tick loop)
and feed it to every consumer. If anything tries to access an engine-only
attribute, the test crashes.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

import pytest

from analytics.aggregator import compute_waste_summary
from analytics.travel import compute_travel_metrics
from analytics.utilization import compute_equipment_utilization
from models.assets import Asset, EquipmentState, Position, WorkerState
from models.site import Site, Zone
from optimization.equipment_schedule import optimize_equipment
from optimization.facility_placement import optimize_toilet_placement
from optimization.material_staging import optimize_material_staging
from state.source import SiteStateSource


@dataclass
class FakeSource:
    """Hand-rolled SiteStateSource — proves the Protocol surface is enough."""
    project_id: str = "fake-project"
    sim_time: float = 8 * 3600.0  # 8 AM
    sim_day: int = 1
    _site: Site = field(default_factory=lambda: Site(
        id="fake", name="Fake Site", width=100, height=100, current_day=1,
        zones=[
            Zone(id="zone-a", label="Block A", x=10, y=10, width=40, height=40,
                 phase="structural", phase_progress=0.5),
            Zone(id="zone-b", label="Block B", x=60, y=10, width=30, height=40,
                 phase="finishes", phase_progress=0.5),
        ],
        schedule=[],
    ))
    _assets: list[Asset] = field(default_factory=list)
    _internals: dict[str, dict] = field(default_factory=dict)
    _activity: dict[str, list[dict]] = field(default_factory=dict)
    _trails: dict[str, list[tuple[float, float]]] = field(default_factory=dict)

    @property
    def site(self) -> Site:
        return self._site

    @property
    def assets(self) -> list[Asset]:
        return self._assets

    def asset_by_id(self, asset_id: str) -> Asset | None:
        return next((a for a in self._assets if a.id == asset_id), None)

    def zone_by_id(self, zone_id: str) -> Zone | None:
        return next((z for z in self._site.zones if z.id == zone_id), None)

    def workers_in_zone(self, zone_id: str) -> list[Asset]:
        return [a for a in self._assets if a.type == "worker" and a.assigned_zone == zone_id]

    def worker_internals_for(self, worker_id: str):
        return self._internals.get(worker_id)

    def activity_log_for(self, asset_id: str) -> Iterable[dict]:
        return self._activity.get(asset_id, [])

    def position_history_for(self, worker_id: str):
        return self._trails.get(worker_id, [])

    # ── Phase-2 multi-level surface ──────────────────────────────────
    #
    # The fake source defaults to a single ground-floor level and no
    # vertical connections. Real multi-level fake sources can override
    # these in their own subclasses; the analytics / optimization layer
    # doesn't depend on them.

    @property
    def levels(self):
        from models.assets import DEFAULT_LEVEL_ID
        from models.site import Level
        return [Level(id=DEFAULT_LEVEL_ID, name="EG", elevation_m=0.0, order=0)]

    def level_by_id(self, level_id: str):
        for lv in self.levels:
            if lv.id == level_id:
                return lv
        return None

    def workers_in_level(self, level_id: str):
        return [
            a for a in self._assets
            if a.type == "worker" and a.position.level_id == level_id
        ]

    @property
    def connections(self):
        return []

    def connections_from_level(self, level_id: str):
        return []

    def navmesh_for_level(self, level_id: str):
        """No navmesh on the fake source — optimizer + worker FSM both
        fall back to euclidean / straight-line behaviour, which is what
        these tests asserted before pathfinding existed."""
        return None


def _make_realistic_fake() -> FakeSource:
    src = FakeSource()
    # 2 workers in zone-a, 1 in zone-b
    src._assets.extend([
        Asset(id="w1", type="worker", subtype="structural",
              position=Position(x=20, y=20), state=WorkerState.WORKING, assigned_zone="zone-a"),
        Asset(id="w2", type="worker", subtype="finishing",
              position=Position(x=30, y=30), state=WorkerState.WORKING, assigned_zone="zone-a"),
        Asset(id="w3", type="worker", subtype="finishing",
              position=Position(x=70, y=20), state=WorkerState.WORKING, assigned_zone="zone-b"),
    ])
    # Toilet on opposite side of site (begs to be moved)
    src._assets.append(
        Asset(id="toilet-1", type="facility", subtype="toilet",
              position=Position(x=95, y=95), state="active", assigned_zone=None),
    )
    # A material far from its zone
    src._assets.append(
        Asset(id="mat-rebar", type="material", subtype="rebar",
              position=Position(x=5, y=95), state="staged",
              assigned_zone=None, metadata={"needed_in_zone": "zone-b"}),
    )
    # Some idle equipment
    src._assets.append(
        Asset(id="crane-1", type="equipment", subtype="tower_crane",
              position=Position(x=50, y=50), state=EquipmentState.IDLE,
              metadata={"hours_active": 1.0, "hours_idle": 10.0, "cycle_timer": 0}),
    )
    # Worker internals — match the dict shape worker_behavior uses today
    for wid in ("w1", "w2", "w3"):
        src._internals[wid] = {
            "next_toilet": 7200, "next_break": 14400, "next_material": 7200,
            "action_timer": 0, "target": None, "return_position": None,
            "total_distance": 100.0,
            "time_working": 600.0, "time_walking": 120.0, "time_at_facilities": 60.0,
            "toilet_trips_today": 1, "toilet_trip_start_time": 0,
            "toilet_total_round_trip": 480.0,
            "material_trips_today": 1, "material_trip_start_time": 0,
            "material_total_round_trip": 360.0,
        }
    return src


def test_protocol_runtime_check():
    """FakeSource and SimulationEngine should both pass isinstance."""
    from simulation.engine import SimulationEngine
    assert isinstance(SimulationEngine(), SiteStateSource)
    assert isinstance(_make_realistic_fake(), SiteStateSource)


def test_compute_travel_metrics_against_fake():
    src = _make_realistic_fake()
    metrics = compute_travel_metrics(src)
    assert len(metrics) == 2  # both zones have workers
    by_zone = {m.zone_id: m for m in metrics}
    assert by_zone["zone-a"].num_workers == 2
    assert by_zone["zone-b"].num_workers == 1
    # Productivity computed from internals
    assert 0 < by_zone["zone-a"].productivity_rate <= 1


def test_compute_equipment_utilization_against_fake():
    src = _make_realistic_fake()
    metrics = compute_equipment_utilization(src)
    assert len(metrics) == 1
    assert metrics[0].asset_id == "crane-1"
    # 1h active / 11h total ~= 9% — daily_idle_cost should be positive
    assert metrics[0].daily_idle_cost > 0


def test_compute_waste_summary_against_fake():
    src = _make_realistic_fake()
    summary = compute_waste_summary(src)
    assert summary.total_daily > 0
    assert summary.total_monthly > summary.total_daily * 20


def test_optimize_toilet_placement_against_fake():
    src = _make_realistic_fake()
    recs = optimize_toilet_placement(src)
    # Toilet is in far corner — should recommend a move
    assert len(recs) >= 1
    rec = recs[0]
    assert rec.target_asset_id == "toilet-1"
    assert rec.from_position.x == 95
    assert rec.to_position is not None


def test_optimize_material_staging_against_fake():
    src = _make_realistic_fake()
    recs = optimize_material_staging(src)
    # Material at (5,95) targeting zone-b at center (75, 30) — clearly far
    assert len(recs) >= 1
    assert recs[0].target_asset_id == "mat-rebar"


def test_optimize_equipment_against_fake():
    src = _make_realistic_fake()
    recs = optimize_equipment(src)
    # Crane util ~ 9% → should recommend release
    assert len(recs) >= 1
    assert recs[0].target_asset_id == "crane-1"
    assert "Release" in recs[0].title


def test_consumers_never_touch_engine_specific_attrs():
    """The killer test — every consumer must work even if the source has
    NO engine-specific attrs (no .tick, no .paused, no .speed_multiplier,
    no .worker_internals dict, no .position_history dict, no .activity_log
    dict, no .running flag)."""
    src = _make_realistic_fake()
    # FakeSource has NONE of those attributes:
    for forbidden in ("tick", "paused", "speed_multiplier", "running",
                      "worker_internals", "position_history", "activity_log"):
        assert not hasattr(src, forbidden), (
            f"FakeSource accidentally has '{forbidden}' — drop it to keep "
            f"the test honest."
        )
    # All consumers run without crashing
    compute_waste_summary(src)
    optimize_toilet_placement(src)
    optimize_material_staging(src)
    optimize_equipment(src)


def test_fake_source_passes_isinstance_protocol():
    """Belt-and-braces: confirm @runtime_checkable Protocol acceptance."""
    assert isinstance(_make_realistic_fake(), SiteStateSource)
