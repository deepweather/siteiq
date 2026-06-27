"""Integration tests: navmesh wired into the worker FSM and optimizer.

These don't re-test the navmesh internals (test_navmesh.py does that) —
they assert the cross-module wiring works end-to-end.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from models.assets import Asset, Position, WorkerState
from models.site import Discipline, Level, Phase, Site, Zone
from simulation.engine import SimulationEngine
from simulation.navmesh import NavMesh
from simulation.worker_behavior import (
    _on_walking_to_toilet,
    _on_working,
    follow_path,
    set_path,
)
from simulation.worker_internals import WorkerInternals


# ── Stub engine reused across tests ─────────────────────────────────


@dataclass
class _StubEngine:
    assets: list[Asset] = field(default_factory=list)
    site: Site = field(default_factory=lambda: Site(
        id="s", name="S", width=80.0, height=80.0, current_day=1,
        zones=[Zone(id="zone-a", label="A", x=0, y=0, width=50, height=50,
                    phase=Phase.STRUCTURAL, phase_progress=0.5)],
        schedule=[],
        discipline=Discipline.HOCHBAU,
        levels=[Level(id="L0", name="EG", elevation_m=0.0, order=0)],
    ))
    worker_internals: dict[str, WorkerInternals] = field(default_factory=dict)
    sim_time: float = 0.0
    activity_log: list[tuple[str, str]] = field(default_factory=list)
    cabs: dict = field(default_factory=dict)
    connections: list = field(default_factory=list)
    navmesh: NavMesh | None = None

    def log_activity(self, asset_id: str, event: str) -> None:
        self.activity_log.append((asset_id, event))

    def facilities_by_subtype(self, subtype, level_id=None):
        out = [a for a in self.assets if a.type == "facility" and a.subtype == subtype]
        if level_id is not None:
            out = [a for a in out if a.position.level_id == level_id]
        return out

    def materials(self):
        return [a for a in self.assets if a.type == "material"]

    def connections_from_level(self, level_id):
        return [c for c in self.connections if any(n.level_id == level_id for n in c.nodes)]

    def navmesh_for_level(self, level_id):
        return self.navmesh


def _make_worker(state=WorkerState.WORKING) -> Asset:
    return Asset(
        id="w1", type="worker", subtype="general",
        position=Position(x=25, y=25, level_id="L0"),
        state=state, assigned_zone="zone-a",
    )


# ── set_path / follow_path basics ──────────────────────────────────


def test_set_path_stores_navmesh_waypoints():
    eng = _StubEngine()
    eng.navmesh = NavMesh.build(level_id="L0", site=eng.site, equipment=[])
    w = _make_worker()
    internals = WorkerInternals(next_toilet=7200, next_break=14400, next_material=7200)
    dest = Position(x=70, y=70, level_id="L0")
    set_path(w, internals, eng, dest)
    assert internals.path, "set_path must populate the waypoint list"
    assert internals.path_index == 0
    # Last waypoint is the exact destination so the worker reaches the
    # facility, not a 2 m-off cell centre.
    assert internals.path[-1].x == dest.x
    assert internals.path[-1].y == dest.y


def test_set_path_without_navmesh_falls_back_to_single_target():
    """When the engine has no navmesh registered for the level, the FSM
    keeps walking — straight line to the destination."""
    eng = _StubEngine()
    eng.navmesh = None
    w = _make_worker()
    internals = WorkerInternals(next_toilet=7200, next_break=14400, next_material=7200)
    dest = Position(x=70, y=70, level_id="L0")
    set_path(w, internals, eng, dest)
    assert internals.path == []
    assert internals.target == dest


def test_follow_path_advances_through_waypoints():
    """Two-waypoint path: the worker walks past the first then onto the
    second, and finally returns arrived=True at the last."""
    eng = _StubEngine()
    eng.navmesh = NavMesh.build(level_id="L0", site=eng.site, equipment=[])
    w = _make_worker()
    internals = WorkerInternals(next_toilet=7200, next_break=14400, next_material=7200)
    # Two synthetic waypoints — short hops the worker can complete in a
    # handful of ticks at WORKER_SPEED * dt = 1.2 * 30 = 36 m / tick.
    internals.path = [
        Position(x=40, y=25, level_id="L0"),
        Position(x=40, y=40, level_id="L0"),
    ]
    internals.path_index = 0
    internals.target = internals.path[0]
    arrived, _ = follow_path(w, internals, dt_sim=30.0)
    # 36 m / tick covers the first waypoint (15 m away) AND advances
    # the index. We're not arrived-at-final yet — index points to wp 2.
    assert internals.path_index == 1
    # Run again to finish.
    arrived, _ = follow_path(w, internals, dt_sim=30.0)
    assert arrived
    assert internals.path == []


# ── Worker detours around an equipment obstacle ────────────────────


def test_worker_detours_around_crane_when_heading_to_toilet():
    """The straight line worker -> toilet crosses a crane. The path
    must avoid every cell in the crane's footprint."""
    site = Site(
        id="s", name="S", width=100.0, height=100.0, current_day=1,
        zones=[Zone(id="zone-a", label="A", x=0, y=0, width=50, height=50,
                    phase=Phase.STRUCTURAL, phase_progress=0.5)],
        schedule=[],
        discipline=Discipline.HOCHBAU,
        levels=[Level(id="L0", name="EG", elevation_m=0.0, order=0)],
    )
    crane = Asset(
        id="crane-1", type="equipment", subtype="tower_crane",
        position=Position(x=50, y=25, level_id="L0"),
        state="operating",
    )
    eng = _StubEngine(site=site)
    eng.navmesh = NavMesh.build(level_id="L0", site=site, equipment=[crane])

    worker = Asset(
        id="w1", type="worker", subtype="general",
        position=Position(x=10, y=25, level_id="L0"),
        state=WorkerState.WORKING, assigned_zone="zone-a",
    )
    toilet = Asset(
        id="t1", type="facility", subtype="toilet",
        position=Position(x=90, y=25, level_id="L0"),
        state="active",
    )
    eng.assets = [worker, crane, toilet]
    internals = WorkerInternals(next_toilet=0, next_break=14400, next_material=7200)
    eng.worker_internals["w1"] = internals

    _on_working(worker, internals, dt_sim=30.0, engine=eng)
    # The worker should be on a path toward the toilet that routes
    # around the crane — every waypoint walkable, none crossing
    # the crane footprint.
    assert internals.path, "trip should produce a multi-waypoint path"
    for w in internals.path:
        assert eng.navmesh.is_walkable(w.x, w.y), (
            f"path waypoint ({w.x},{w.y}) sits on an impassable cell"
        )


# ── Engine builds navmeshes per level ──────────────────────────────


def test_simulation_engine_builds_one_navmesh_per_level():
    """End-to-end: the engine produces a navmesh per level after init."""
    eng = SimulationEngine("westhafen")
    assert eng.navmeshes, "engine must build navmeshes during _rebuild_indexes"
    # Westhafen has at least one level — every level has a navmesh.
    for lv in eng.site.levels:
        assert eng.navmesh_for_level(lv.id) is not None


# ── Optimizer uses path distance + walkable clamp ──────────────────


def test_optimizer_clamps_placement_to_walkable_cells():
    """When the optimal centroid sits on a crane, the recommendation
    must propose a snapped position (walkable cell), not the
    impassable one."""
    from optimization.facility_placement import optimize_toilet_placement

    site = Site(
        id="s", name="S", width=100.0, height=100.0, current_day=1,
        zones=[Zone(id="zone-a", label="A", x=20, y=20, width=60, height=60,
                    phase=Phase.STRUCTURAL, phase_progress=0.5)],
        schedule=[],
        discipline=Discipline.HOCHBAU,
        levels=[Level(id="L0", name="EG", elevation_m=0.0, order=0)],
    )
    crane = Asset(
        id="crane-1", type="equipment", subtype="tower_crane",
        position=Position(x=50, y=50, level_id="L0"),
        state="operating",
    )
    # The zone centroid is (50, 50) — exactly on the crane. k-means
    # would suggest that as the toilet's new home; snap_to_walkable
    # must push it off.
    workers = [
        Asset(id=f"w{i}", type="worker", subtype="general",
              position=Position(x=30 + i * 5, y=30, level_id="L0"),
              state=WorkerState.WORKING, assigned_zone="zone-a")
        for i in range(3)
    ]
    toilet = Asset(
        id="toilet-1", type="facility", subtype="toilet",
        position=Position(x=95, y=95, level_id="L0"),
        state="active",
    )

    eng = _StubEngine(site=site)
    eng.assets = [crane, toilet, *workers]
    eng.navmesh = NavMesh.build(level_id="L0", site=site, equipment=[crane])

    # _StubEngine doesn't implement the full SiteStateSource Protocol
    # for the optimizer; add the few extras the optimizer needs.
    eng.workers_in_zone = lambda zid: [a for a in eng.assets if a.type == "worker" and a.assigned_zone == zid]
    # zone_by_id is unused by this optimizer but required by Protocol;
    # leave it unmodified.
    eng.zone_by_id = lambda zid: next(
        (z for z in eng.site.zones if z.id == zid), None
    )

    recs = optimize_toilet_placement(eng)  # type: ignore[arg-type]
    # The single produced rec must land on a walkable cell, not on the
    # crane footprint.
    assert recs, "optimizer must produce at least one recommendation"
    new_pos = recs[0].to_position
    assert new_pos is not None
    assert eng.navmesh.is_walkable(new_pos.x, new_pos.y), (
        f"optimizer proposed ({new_pos.x},{new_pos.y}) on an impassable cell"
    )
