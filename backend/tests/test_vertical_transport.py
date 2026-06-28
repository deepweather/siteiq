"""Phase 3 — cab-tracked vertical transport tests."""
from __future__ import annotations

import time

from models.assets import WorkerState
from models.connection import Connection, ConnectionNode
from models.project_document import (
    FacilitySpec,
    ProjectDocument,
    WorkerSeed,
)
from models.site import Discipline, Level, Phase, Zone
from simulation.engine import SimulationEngine
from simulation.worker_behavior import _find_connection_to


def _doc_with_two_floors_and_stair() -> ProjectDocument:
    return ProjectDocument(
        slug="house-stair",
        name="Stair House",
        description="EG + 1.OG with a stair, toilet only on EG",
        discipline=Discipline.HOCHBAU,
        width=80.0, height=60.0,
        levels=[
            Level(id="L0", name="EG", elevation_m=0.0, order=0),
            Level(id="L1", name="1. OG", elevation_m=3.5, order=1),
        ],
        zones=[
            Zone(id="z-eg", label="EG", x=5, y=5, width=70, height=50,
                 phase=Phase.STRUCTURAL, phase_progress=0.5, level_id="L0"),
            Zone(id="z-og", label="1. OG", x=5, y=5, width=70, height=50,
                 phase=Phase.STRUCTURAL, phase_progress=0.4, level_id="L1"),
        ],
        facilities=[
            FacilitySpec(id="toilet-eg", subtype="toilet", x=70, y=5, level_id="L0"),
        ],
        connections=[
            Connection(
                id="stair-1", kind="stair",
                nodes=[
                    ConnectionNode(level_id="L0", x=40, y=30),
                    ConnectionNode(level_id="L1", x=40, y=30),
                ],
                seconds_per_level_climb=10.0,
            ),
        ],
        worker_seeds=[
            WorkerSeed(zone_id="z-og", trade="general", count=1),
        ],
    )


def _doc_with_two_floors_and_elevator() -> ProjectDocument:
    return ProjectDocument(
        slug="house-elevator",
        name="Elevator House",
        description="EG + 1.OG + 2.OG, elevator only, toilet on EG",
        discipline=Discipline.HOCHBAU,
        width=80.0, height=60.0,
        levels=[
            Level(id="L0", name="EG", elevation_m=0.0, order=0),
            Level(id="L1", name="1. OG", elevation_m=3.5, order=1),
            Level(id="L2", name="2. OG", elevation_m=7.0, order=2),
        ],
        zones=[
            Zone(id="z-eg", label="EG", x=5, y=5, width=70, height=50,
                 phase=Phase.STRUCTURAL, phase_progress=0.5, level_id="L0"),
            Zone(id="z-og", label="1. OG", x=5, y=5, width=70, height=50,
                 phase=Phase.STRUCTURAL, phase_progress=0.4, level_id="L1"),
            Zone(id="z-og2", label="2. OG", x=5, y=5, width=70, height=50,
                 phase=Phase.STRUCTURAL, phase_progress=0.3, level_id="L2"),
        ],
        facilities=[
            FacilitySpec(id="toilet-eg", subtype="toilet", x=70, y=5, level_id="L0"),
        ],
        connections=[
            Connection(
                id="lift-1", kind="elevator",
                nodes=[
                    ConnectionNode(level_id="L0", x=40, y=30),
                    ConnectionNode(level_id="L1", x=40, y=30),
                    ConnectionNode(level_id="L2", x=40, y=30),
                ],
                cab_capacity=2, cycle_time_s=20.0, speed_m_per_s=2.0,
            ),
        ],
        worker_seeds=[
            WorkerSeed(zone_id="z-og2", trade="general", count=3),
        ],
    )


# ── Routing primitive ────────────────────────────────────────────────


def test_find_connection_to_returns_direct_link():
    eng = SimulationEngine(document=_doc_with_two_floors_and_stair())
    conn = _find_connection_to(eng, "L0", "L1")
    assert conn is not None and conn.id == "stair-1"


def test_find_connection_to_returns_none_for_disconnected():
    eng = SimulationEngine(document=_doc_with_two_floors_and_stair())
    conn = _find_connection_to(eng, "L0", "L42")
    assert conn is None


# ── Stair traversal ──────────────────────────────────────────────────


def test_worker_uses_stair_to_reach_cross_level_toilet():
    """A worker on L1 with the only toilet on L0 must transition into
    WALKING_TO_VERTICAL, then TRAVERSING_VERTICAL, then end up on L0."""
    eng = SimulationEngine(document=_doc_with_two_floors_and_stair())
    worker = next(a for a in eng.assets if a.type == "worker")
    internals = eng.worker_internals[worker.id]

    # Force the toilet check to fire on the next tick.
    internals.next_toilet = -1.0
    eng.tick()
    # Should have transitioned to WALKING_TO_VERTICAL.
    assert worker.state == WorkerState.WALKING_TO_VERTICAL

    # Spin many ticks. Eventually the worker must reach L0.
    for _ in range(400):
        eng.tick()
        if worker.position.level_id == "L0":
            break
    assert worker.position.level_id == "L0", (
        f"worker stuck on {worker.position.level_id} after 400 ticks; "
        f"state={worker.state}"
    )


def test_single_level_project_skips_vertical_routing():
    """The 3 stock seeds are single-level; no worker should ever enter
    WALKING_TO_VERTICAL."""
    eng = SimulationEngine(project_id="westhafen")
    for _ in range(100):
        eng.tick()
    assert all(
        a.state != WorkerState.WALKING_TO_VERTICAL
        and a.state != WorkerState.TRAVERSING_VERTICAL
        for a in eng.assets if a.type == "worker"
    )


# ── Cab queue ────────────────────────────────────────────────────────


def test_elevator_cab_built_for_elevator_connection():
    eng = SimulationEngine(document=_doc_with_two_floors_and_elevator())
    assert "lift-1" in eng.cabs
    cab = eng.cabs["lift-1"]
    # Cab idles on the lowest served level
    assert cab.current_level_id == "L0"
    assert set(cab.queue_per_level.keys()) == {"L0", "L1", "L2"}


def test_worker_boards_elevator_and_reaches_target():
    eng = SimulationEngine(document=_doc_with_two_floors_and_elevator())
    workers = [a for a in eng.assets if a.type == "worker"]
    for w in workers:
        eng.worker_internals[w.id].next_toilet = -1.0
    # Run the simulation long enough for the cab to make at least one
    # full sweep up + down.
    for _ in range(800):
        eng.tick()
        if all(w.position.level_id == "L0" for w in workers):
            break
    # All workers should have ridden to L0 (where the toilet is).
    assert all(
        w.position.level_id == "L0" for w in workers
    ), [(w.id, w.state, w.position.level_id) for w in workers]


# ── Microbench gate ──────────────────────────────────────────────────


def test_tick_under_5ms_with_six_cabs_and_workers():
    """Phase 3 merge gate.

    Build a synthetic project with 6 elevators across 6 levels and 250
    workers. Each tick must average under 5ms — the same 100ms-of-real-
    time budget the rest of the engine has to fit in.
    """
    levels = [
        Level(id=f"L{i}", name=f"Level {i}", elevation_m=i * 3.5, order=i)
        for i in range(6)
    ]
    zones = [
        Zone(
            id=f"z{i}", label=f"Zone {i}", x=5, y=5, width=70, height=50,
            phase=Phase.STRUCTURAL, phase_progress=0.5, level_id=f"L{i}",
        )
        for i in range(6)
    ]
    facilities = [
        FacilitySpec(id="toilet-eg", subtype="toilet", x=70, y=5, level_id="L0"),
        FacilitySpec(id="break-eg", subtype="breakroom", x=5, y=5, level_id="L0"),
    ]
    connections = [
        Connection(
            id=f"lift-{i}", kind="elevator",
            nodes=[
                ConnectionNode(level_id=f"L{j}", x=40.0 + i * 2.0, y=30.0)
                for j in range(6)
            ],
            cab_capacity=6, cycle_time_s=60.0, speed_m_per_s=1.5,
        )
        for i in range(6)
    ]
    worker_seeds = [
        WorkerSeed(zone_id=f"z{i}", trade="general", count=42)
        for i in range(6)
    ]
    doc = ProjectDocument(
        slug="bench-multilevel",
        name="Microbench",
        description="6 levels x 6 elevators x 42 workers/level",
        discipline=Discipline.HOCHBAU,
        width=80.0, height=60.0,
        levels=levels,
        zones=zones,
        facilities=facilities,
        connections=connections,
        worker_seeds=worker_seeds,
    )
    eng = SimulationEngine(document=doc)
    # Warm-up so first-tick allocations are out of the way.
    for _ in range(10):
        eng.tick()
    t0 = time.perf_counter()
    for _ in range(50):
        eng.tick()
    elapsed = (time.perf_counter() - t0) / 50
    assert elapsed < 0.005, (
        f"tick averages {elapsed*1000:.2f}ms with 6 cabs * ~250 workers "
        f"— over the 5ms Phase 3 merge gate"
    )
