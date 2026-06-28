"""Phase 2 — multi-level engine core tests.

Verifies that the engine's per-level indexes are correctly built from a
multi-level project document, and that workers prefer same-level
facilities when nearest-toilet is queried.
"""
from __future__ import annotations

from models.assets import DEFAULT_LEVEL_ID
from models.connection import Connection, ConnectionNode
from models.project_document import (
    FacilitySpec,
    ProjectDocument,
    WorkerSeed,
)
from models.site import Discipline, Level, Phase, Zone
from simulation.engine import SimulationEngine
from state.source import SiteStateSource


def _multilevel_doc() -> ProjectDocument:
    """A tiny 2-level project: EG with a toilet, 1.OG without one."""
    return ProjectDocument(
        slug="multi-1",
        name="Two-Floor House",
        description="EG + 1. OG",
        discipline=Discipline.HOCHBAU,
        width=80.0,
        height=60.0,
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
            FacilitySpec(id="break-eg", subtype="breakroom", x=5, y=5, level_id="L0"),
        ],
        connections=[
            Connection(
                id="stair-1", kind="stair",
                nodes=[
                    ConnectionNode(level_id="L0", x=40, y=30),
                    ConnectionNode(level_id="L1", x=40, y=30),
                ],
            ),
        ],
        worker_seeds=[
            WorkerSeed(zone_id="z-eg", trade="general", count=2),
            WorkerSeed(zone_id="z-og", trade="general", count=2),
        ],
    )


def _engine_from_doc() -> SimulationEngine:
    return SimulationEngine(document=_multilevel_doc())


def test_engine_reports_levels_in_order():
    eng = _engine_from_doc()
    ids = [lv.id for lv in eng.levels]
    assert ids == ["L0", "L1"]


def test_level_by_id_lookup():
    eng = _engine_from_doc()
    assert eng.level_by_id("L0").name == "EG"
    assert eng.level_by_id("L1").name == "1. OG"
    assert eng.level_by_id("L42") is None


def test_facilities_by_subtype_level_filter():
    eng = _engine_from_doc()
    # All toilets
    all_toilets = eng.facilities_by_subtype("toilet")
    assert {f.id for f in all_toilets} == {"toilet-eg"}
    # Same-level lookup
    on_l0 = eng.facilities_by_subtype("toilet", "L0")
    on_l1 = eng.facilities_by_subtype("toilet", "L1")
    assert [f.id for f in on_l0] == ["toilet-eg"]
    assert on_l1 == []


def test_workers_in_level_filters_by_position():
    eng = _engine_from_doc()
    # Document places 2 workers in EG zone (L0) and 2 in 1.OG zone (L1).
    on_l0 = eng.workers_in_level("L0")
    on_l1 = eng.workers_in_level("L1")
    assert len(on_l0) == 2
    assert len(on_l1) == 2
    assert all(w.position.level_id == "L0" for w in on_l0)
    assert all(w.position.level_id == "L1" for w in on_l1)


def test_workers_in_level_recomputed_after_position_change():
    """If a worker is teleported to a different level mid-sim, the
    `workers_in_level` view must reflect the new state without
    needing rebuild_indexes."""
    eng = _engine_from_doc()
    worker = next(w for w in eng.assets if w.type == "worker")
    original_level = worker.position.level_id
    target_level = "L1" if original_level == "L0" else "L0"
    worker.position.level_id = target_level
    assert worker in eng.workers_in_level(target_level)
    assert worker not in eng.workers_in_level(original_level)


def test_connections_index_built_correctly():
    eng = _engine_from_doc()
    assert len(eng.connections) == 1
    assert eng.connections[0].id == "stair-1"
    # Both endpoints index back to the same Connection.
    l0_conns = eng.connections_from_level("L0")
    l1_conns = eng.connections_from_level("L1")
    assert [c.id for c in l0_conns] == ["stair-1"]
    assert [c.id for c in l1_conns] == ["stair-1"]


def test_engine_satisfies_protocol_with_multilevel_surface():
    eng = _engine_from_doc()
    assert isinstance(eng, SiteStateSource)


def test_legacy_single_level_engine_still_satisfies_protocol():
    """The 3 seed projects today are single-level (one auto-generated L0).
    They must still satisfy the extended Protocol."""
    eng = SimulationEngine(project_id="westhafen")
    assert isinstance(eng, SiteStateSource)
    assert len(eng.levels) == 1
    assert eng.levels[0].id == DEFAULT_LEVEL_ID
    assert eng.connections == []
    assert eng.connections_from_level(DEFAULT_LEVEL_ID) == []


def test_worker_prefers_same_level_facility():
    """A worker on L0 with a toilet on L0 picks L0's toilet.
    A worker on L1 with no toilet on L1 falls back to L0's toilet.
    (Phase 2 still uses 2D distance for the cross-level fallback —
    Phase 3 adds the vertical-transport routing.)"""
    from simulation.worker_behavior import _find_nearest_facility

    eng = _engine_from_doc()
    # Pick the first worker on L1; force them to look for a toilet.
    l1_worker = next(w for w in eng.workers_in_level("L1"))
    target = _find_nearest_facility(l1_worker, eng, "toilet")
    assert target is not None
    assert target.id == "toilet-eg"  # only toilet, cross-level fallback

    # L0 worker should find the L0 toilet directly.
    l0_worker = next(w for w in eng.workers_in_level("L0"))
    target_l0 = _find_nearest_facility(l0_worker, eng, "toilet")
    assert target_l0 is not None
    assert target_l0.id == "toilet-eg"
    assert target_l0.position.level_id == "L0"
