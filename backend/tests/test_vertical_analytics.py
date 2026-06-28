"""Phase 4 — vertical-transport analytics + optimizer + per-level
facility placement tests."""
from __future__ import annotations

from analytics.aggregator import compute_waste_summary
from analytics.vertical_metrics import compute_vertical_metrics
from models.connection import Connection, ConnectionNode
from models.project_document import (
    FacilitySpec,
    ProjectDocument,
    WorkerSeed,
)
from models.site import Discipline, Level, Phase, Zone
from optimization.facility_placement import optimize_toilet_placement
from optimization.vertical_transport_optimizer import optimize_vertical_transport
from simulation.engine import SimulationEngine


# ── Vertical-transport metrics + aggregator ──────────────────────────


def _doc_with_busy_elevator() -> ProjectDocument:
    """Most workers live on L2; only toilet is on L0. Forces a busy
    elevator queue once the toilet timer ticks down."""
    return ProjectDocument(
        slug="busy",
        name="Busy Tower",
        description="EG..2.OG with one elevator, toilet on EG only",
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
            Zone(id="z-og", label="1.OG", x=5, y=5, width=70, height=50,
                 phase=Phase.STRUCTURAL, phase_progress=0.4, level_id="L1"),
            Zone(id="z-og2", label="2.OG", x=5, y=5, width=70, height=50,
                 phase=Phase.STRUCTURAL, phase_progress=0.3, level_id="L2"),
        ],
        facilities=[FacilitySpec(
            id="toilet-eg", subtype="toilet", x=70, y=5, level_id="L0",
        )],
        connections=[Connection(
            id="lift-1", kind="elevator",
            nodes=[
                ConnectionNode(level_id="L0", x=40, y=30),
                ConnectionNode(level_id="L1", x=40, y=30),
                ConnectionNode(level_id="L2", x=40, y=30),
            ],
            cab_capacity=1, cycle_time_s=120.0, speed_m_per_s=0.5,
        )],
        worker_seeds=[
            WorkerSeed(zone_id="z-og2", trade="general", count=4),
        ],
    )


def test_vertical_metrics_starts_at_zero():
    eng = SimulationEngine(document=_doc_with_busy_elevator())
    m = compute_vertical_metrics(eng)
    assert m.waste_daily == 0.0
    assert all(c.queued_now == 0 for c in m.cabs)


def test_vertical_metrics_accumulate_after_workers_use_elevator():
    eng = SimulationEngine(document=_doc_with_busy_elevator())
    # Force every worker on L2 to fire a toilet trip.
    for w in (a for a in eng.assets if a.type == "worker"):
        eng.worker_internals[w.id].next_toilet = -1.0
    # Spin enough ticks for at least one worker to be queueing.
    for _ in range(20):
        eng.tick()
    m = compute_vertical_metrics(eng)
    # Either someone is queued or there's accumulated wait time.
    assert m.total_worker_seconds > 0.0 or any(c.queued_now > 0 for c in m.cabs)


def test_waste_summary_includes_vertical_bucket():
    eng = SimulationEngine(document=_doc_with_busy_elevator())
    summary = compute_waste_summary(eng)
    assert hasattr(summary, "vertical_transport_daily")
    assert hasattr(summary, "vertical_transport_monthly")
    # Empty initially; might be 0.0 if no worker has queued yet.
    assert summary.vertical_transport_daily >= 0.0


def test_waste_summary_single_floor_keeps_vertical_at_zero():
    """The 3 stock seeds are single-floor — they must report 0 € of
    vertical-transport waste."""
    eng = SimulationEngine(project_id="westhafen")
    for _ in range(20):
        eng.tick()
    summary = compute_waste_summary(eng)
    assert summary.vertical_transport_daily == 0.0


# ── Optimizer ────────────────────────────────────────────────────────


def test_vertical_optimizer_no_recs_for_calm_cab():
    eng = SimulationEngine(document=_doc_with_busy_elevator())
    # No workers have moved yet — cab is idle.
    recs = optimize_vertical_transport(eng)
    assert recs == []


def test_vertical_optimizer_recommends_second_cab_when_saturated():
    eng = SimulationEngine(document=_doc_with_busy_elevator())
    for w in (a for a in eng.assets if a.type == "worker"):
        eng.worker_internals[w.id].next_toilet = -1.0
    # Tick enough that all 4 workers pile into a 1-capacity cab queue.
    for _ in range(40):
        eng.tick()
    metrics = compute_vertical_metrics(eng)
    recs = optimize_vertical_transport(eng)
    # At least one should fire (queue saturation or long wait).
    assert recs, (
        f"expected at least one vertical-transport rec; "
        f"got metrics={metrics}, recs={recs}"
    )
    assert any(r.target_asset_id == "lift-1" for r in recs)


def test_recommendation_service_includes_vertical_optimizer():
    """RecommendationService default optimizer set must include the
    new vertical optimizer."""
    from services.recommendation_service import DEFAULT_OPTIMIZERS
    from optimization.vertical_transport_optimizer import optimize_vertical_transport
    assert optimize_vertical_transport in DEFAULT_OPTIMIZERS


# ── Per-level facility placement ─────────────────────────────────────


def _doc_with_two_levels_two_toilets() -> ProjectDocument:
    """One toilet on each of two levels, each badly placed. The
    optimizer should recommend moves on BOTH levels."""
    return ProjectDocument(
        slug="two-level-toilets",
        name="Two-Level Toilets",
        description="",
        discipline=Discipline.HOCHBAU,
        width=100.0, height=80.0,
        levels=[
            Level(id="L0", name="EG", elevation_m=0.0, order=0),
            Level(id="L1", name="1. OG", elevation_m=3.5, order=1),
        ],
        zones=[
            Zone(id="z-eg", label="EG", x=5, y=5, width=80, height=60,
                 phase=Phase.STRUCTURAL, phase_progress=0.5, level_id="L0"),
            Zone(id="z-og", label="1.OG", x=5, y=5, width=80, height=60,
                 phase=Phase.STRUCTURAL, phase_progress=0.4, level_id="L1"),
        ],
        facilities=[
            # Both toilets in opposite far corners — clearly far from the workers.
            FacilitySpec(id="toilet-eg", subtype="toilet", x=95, y=75, level_id="L0"),
            FacilitySpec(id="toilet-og", subtype="toilet", x=95, y=75, level_id="L1"),
        ],
        worker_seeds=[
            WorkerSeed(zone_id="z-eg", trade="general", count=4),
            WorkerSeed(zone_id="z-og", trade="general", count=4),
        ],
    )


def test_facility_placement_runs_per_level():
    eng = SimulationEngine(document=_doc_with_two_levels_two_toilets())
    recs = optimize_toilet_placement(eng)
    # Should produce recs for at least one toilet per level.
    target_ids = {r.target_asset_id for r in recs}
    assert "toilet-eg" in target_ids
    assert "toilet-og" in target_ids


def test_facility_placement_keeps_each_toilet_on_its_level():
    """A toilet on L1 can only move to a centroid of L1's zones, not L0's."""
    eng = SimulationEngine(document=_doc_with_two_levels_two_toilets())
    recs = optimize_toilet_placement(eng)
    by_id = {r.target_asset_id: r for r in recs}
    # We can't directly read level_id off the recommendation (the
    # PositionXY model is 2D), but we can check that the move stays
    # within the level's zone footprint (5,5)..(85,65).
    for rec_id in ("toilet-eg", "toilet-og"):
        rec = by_id.get(rec_id)
        if rec is None or rec.to_position is None:
            continue
        # Centroid of either level's single zone is around (45, 35).
        # Both moves should land near that point.
        assert 30 <= rec.to_position.x <= 70
        assert 20 <= rec.to_position.y <= 50
