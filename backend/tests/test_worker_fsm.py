"""Per-state FSM handler tests for worker_behavior.

Each handler is exercised in isolation with a minimal stub engine, so a
broken transition surfaces precisely instead of being lost in a sea of
ticks.
"""
from __future__ import annotations

from dataclasses import dataclass, field


from models.assets import Asset, Position, WorkerState
from models.site import Site, Zone
from simulation.worker_behavior import (
    STATE_HANDLERS,
    _on_at_break,
    _on_at_toilet,
    _on_carrying_material,
    _on_walking_to_break,
    _on_walking_to_material,
    _on_walking_to_toilet,
    _on_walking_to_work,
    _on_working,
    update_worker,
)
from simulation.worker_internals import WorkerInternals


@dataclass
class _StubEngine:
    assets: list[Asset] = field(default_factory=list)
    site: Site = field(default_factory=lambda: Site(
        id="s", name="S", width=100, height=100, current_day=1,
        zones=[Zone(id="zone-a", label="A", x=0, y=0, width=50, height=50,
                    phase="structural", phase_progress=0.5)],
        schedule=[],
    ))
    worker_internals: dict[str, WorkerInternals] = field(default_factory=dict)
    sim_time: float = 0.0
    activity_log: list[tuple[str, str]] = field(default_factory=list)
    cabs: dict = field(default_factory=dict)
    connections: list = field(default_factory=list)

    def log_activity(self, asset_id: str, event: str) -> None:
        self.activity_log.append((asset_id, event))

    def facilities_by_subtype(
        self, subtype: str, level_id: str | None = None
    ) -> list[Asset]:
        out = [a for a in self.assets if a.type == "facility" and a.subtype == subtype]
        if level_id is not None:
            out = [a for a in out if a.position.level_id == level_id]
        return out

    def materials(self) -> list[Asset]:
        return [a for a in self.assets if a.type == "material"]

    def connections_from_level(self, level_id: str) -> list:
        return [c for c in self.connections if any(n.level_id == level_id for n in c.nodes)]


def _make_worker_and_engine(state: str = WorkerState.WORKING) -> tuple[Asset, WorkerInternals, _StubEngine]:
    worker = Asset(
        id="w1", type="worker", subtype="general",
        position=Position(x=25, y=25), state=state,
        assigned_zone="zone-a",
    )
    internals = WorkerInternals(next_toilet=7200, next_break=14400, next_material=7200)
    eng = _StubEngine(assets=[worker], worker_internals={"w1": internals})
    return worker, internals, eng


# ─── Dispatch table integrity ────────────────────────────────────────────

def test_dispatch_table_covers_every_active_worker_state():
    """Every state the FSM can transition INTO must have a handler.
    IDLE is the only state with no handler today (no one ever sets it)."""
    expected = {
        WorkerState.WORKING,
        WorkerState.WALKING_TO_TOILET,
        WorkerState.AT_TOILET,
        WorkerState.WALKING_TO_MATERIAL,
        WorkerState.CARRYING_MATERIAL,
        WorkerState.WALKING_TO_BREAK,
        WorkerState.AT_BREAK,
        WorkerState.WALKING_TO_WORK,
        # Phase 3: multi-level routing.
        WorkerState.WALKING_TO_VERTICAL,
        WorkerState.TRAVERSING_VERTICAL,
    }
    assert set(STATE_HANDLERS.keys()) == expected


def test_unknown_state_is_noop_not_crash():
    """Defensive: worker in an unrecognized state should not crash the tick."""
    worker, _, eng = _make_worker_and_engine(state="completely-bogus-state")
    # Should not raise
    update_worker(worker, 1.0, eng)
    # And worker stays where it was
    assert worker.state == "completely-bogus-state"


# ─── WORKING handler ─────────────────────────────────────────────────────

def test_working_transitions_to_walking_to_toilet_when_due_and_toilet_exists():
    worker, internals, eng = _make_worker_and_engine()
    eng.assets.append(Asset(
        id="t1", type="facility", subtype="toilet",
        position=Position(x=10, y=10), state="active",
    ))
    internals.next_toilet = -1.0
    _on_working(worker, internals, 30.0, eng)
    assert worker.state == WorkerState.WALKING_TO_TOILET
    assert internals.toilet_trips_today == 1
    assert internals.target is not None
    assert (internals.target.x, internals.target.y) == (10, 10)


def test_working_defers_toilet_when_no_toilet_exists():
    """Bug #11 regression — timer must reset positive, not pin at <0."""
    worker, internals, eng = _make_worker_and_engine()
    internals.next_toilet = -1.0
    _on_working(worker, internals, 30.0, eng)
    assert worker.state == WorkerState.WORKING, "should NOT transition without a toilet"
    assert internals.next_toilet > 0, "timer must be re-jittered, not stuck at -1"


def test_working_transitions_to_walking_to_material():
    worker, internals, eng = _make_worker_and_engine()
    eng.assets.append(Asset(
        id="m1", type="material", subtype="rebar",
        position=Position(x=40, y=40), state="staged",
        metadata={"needed_in_zone": "zone-a"},
    ))
    internals.next_material = -1.0
    _on_working(worker, internals, 30.0, eng)
    assert worker.state == WorkerState.WALKING_TO_MATERIAL
    assert internals.material_trips_today == 1


def test_working_accumulates_time_working():
    worker, internals, eng = _make_worker_and_engine()
    _on_working(worker, internals, 30.0, eng)
    assert internals.time_working == 30.0


# ─── WALKING_TO_TOILET handler ───────────────────────────────────────────

def test_walking_to_toilet_advances_position_and_distance():
    worker, internals, _ = _make_worker_and_engine(WorkerState.WALKING_TO_TOILET)
    eng = _StubEngine(assets=[worker], worker_internals={"w1": internals})
    internals.target = Position(x=100, y=25)  # far away — won't arrive
    _on_walking_to_toilet(worker, internals, 5.0, eng)
    assert worker.position.x > 25
    assert internals.total_distance > 0
    assert worker.state == WorkerState.WALKING_TO_TOILET  # not arrived yet


def test_walking_to_toilet_arrives_close_target():
    worker, internals, _ = _make_worker_and_engine(WorkerState.WALKING_TO_TOILET)
    eng = _StubEngine(assets=[worker], worker_internals={"w1": internals})
    internals.target = Position(x=25.5, y=25)  # 0.5m away
    _on_walking_to_toilet(worker, internals, 5.0, eng)
    assert worker.state == WorkerState.AT_TOILET
    assert internals.action_timer > 0


# ─── AT_TOILET handler ───────────────────────────────────────────────────

def test_at_toilet_counts_facility_time_and_decrements_action_timer():
    worker, internals, eng = _make_worker_and_engine(WorkerState.AT_TOILET)
    internals.action_timer = 240
    _on_at_toilet(worker, internals, 30.0, eng)
    assert internals.time_at_facilities == 30.0
    assert internals.action_timer == 210


def test_at_toilet_transitions_to_walking_to_work_when_done():
    worker, internals, eng = _make_worker_and_engine(WorkerState.AT_TOILET)
    internals.action_timer = 5
    _on_at_toilet(worker, internals, 30.0, eng)
    assert worker.state == WorkerState.WALKING_TO_WORK
    assert internals.returning_from == "toilet"
    assert internals.target is not None  # random point in zone


# ─── WALKING_TO_MATERIAL + CARRYING_MATERIAL ─────────────────────────────

def test_walking_to_material_arrives_and_starts_dwell():
    worker, internals, _ = _make_worker_and_engine(WorkerState.WALKING_TO_MATERIAL)
    eng = _StubEngine(assets=[worker], worker_internals={"w1": internals})
    internals.target = Position(x=25.1, y=25)
    _on_walking_to_material(worker, internals, 5.0, eng)
    assert worker.state == WorkerState.CARRYING_MATERIAL
    assert internals.action_timer > 0
    assert internals.carrying_target is not None


def test_carrying_material_dwells_then_walks_back():
    worker, internals, eng = _make_worker_and_engine(WorkerState.CARRYING_MATERIAL)
    internals.action_timer = 100
    _on_carrying_material(worker, internals, 30.0, eng)
    # Still dwelling
    assert internals.action_timer == 70
    assert worker.state == WorkerState.CARRYING_MATERIAL

    # Drop dwell to 0, set a carrying_target — now should move
    internals.action_timer = 0
    internals.carrying_target = Position(x=30, y=25)
    _on_carrying_material(worker, internals, 5.0, eng)
    assert internals.total_distance > 0


# ─── BREAK path ──────────────────────────────────────────────────────────

def test_walking_to_break_arrives():
    worker, internals, _ = _make_worker_and_engine(WorkerState.WALKING_TO_BREAK)
    eng = _StubEngine(assets=[worker], worker_internals={"w1": internals})
    internals.target = Position(x=25.5, y=25)
    _on_walking_to_break(worker, internals, 5.0, eng)
    assert worker.state == WorkerState.AT_BREAK


def test_at_break_transitions_back_to_work():
    worker, internals, eng = _make_worker_and_engine(WorkerState.AT_BREAK)
    internals.action_timer = 1
    _on_at_break(worker, internals, 30.0, eng)
    assert worker.state == WorkerState.WALKING_TO_WORK
    assert internals.returning_from == "break"


# ─── WALKING_TO_WORK accounting ──────────────────────────────────────────

def test_walking_to_work_records_toilet_round_trip():
    worker, internals, eng = _make_worker_and_engine(WorkerState.WALKING_TO_WORK)
    internals.target = Position(x=25.5, y=25)
    internals.returning_from = "toilet"
    internals.toilet_trip_start_time = 0
    eng.sim_time = 600.0  # 10-minute round trip
    _on_walking_to_work(worker, internals, 5.0, eng)
    assert worker.state == WorkerState.WORKING
    assert internals.toilet_total_round_trip == 600.0
    assert internals.returning_from == ""
    assert internals.toilet_trip_start_time == 0.0
