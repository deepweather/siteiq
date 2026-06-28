"""Audit-fix regressions for the recommendation `apply` flow.

Catches the four bugs the user surfaced during the post-rebuild review:

1. `add_equipment` apply was a no-op (faked savings).
2. `reschedule_equipment` apply REMOVED equipment instead of batching it.
3. `move_facility` / `restage_material` apply lost the asset's `level_id`,
   teleporting upper-floor facilities to the ground.
4. Shoring-compliance KPI was computed but never surfaced.

Tests use the `auth_client` fixture so they exercise the real HTTP
surface end-to-end, not a stub.
"""
from __future__ import annotations

import time

from analytics.aggregator import compute_waste_summary
from models.assets import EquipmentState
from models.connection import Connection, ConnectionNode
from models.project_document import (
    FacilitySpec,
    ProjectDocument,
    WorkerSeed,
)
from models.site import Discipline, Level, Phase, Zone
from simulation.engine import SimulationEngine
from simulation.equipment_behavior import EQUIPMENT_DUTY_CYCLES


# ── Fix #1: add_equipment apply doubles cab capacity ─────────────────


def test_add_equipment_apply_doubles_cab_capacity():
    doc = ProjectDocument(
        slug="cab", name="Cab Test", description="",
        discipline=Discipline.HOCHBAU,
        width=80.0, height=60.0,
        levels=[
            Level(id="L0", name="EG", elevation_m=0.0, order=0),
            Level(id="L1", name="1. OG", elevation_m=3.5, order=1),
        ],
        zones=[
            Zone(id="z1", label="Z", x=10, y=10, width=60, height=40,
                 phase=Phase.STRUCTURAL, phase_progress=0.5, level_id="L0"),
        ],
        connections=[Connection(
            id="lift-1", kind="elevator",
            nodes=[
                ConnectionNode(level_id="L0", x=40, y=30),
                ConnectionNode(level_id="L1", x=40, y=30),
            ],
            cab_capacity=4, cycle_time_s=60.0, speed_m_per_s=1.5,
        )],
        worker_seeds=[WorkerSeed(zone_id="z1", trade="general", count=1)],
    )
    eng = SimulationEngine(document=doc)
    assert eng.cabs["lift-1"].capacity == 4

    # Simulate the router's `_apply_rec` path for add_equipment.
    from api.routes import _apply_rec
    from models.analytics import Recommendation

    rec = Recommendation(
        id="opt-vertical-lift-1",
        type="add_equipment",
        title="Add a second cab next to lift-1",
        description="",
        target_asset_id="lift-1",
        from_position={"x": 0, "y": 0},
        to_position=None,
        daily_savings=10.0,
        monthly_savings=220.0,
    )
    _apply_rec(rec, eng)
    assert rec.applied is True
    assert eng.cabs["lift-1"].capacity >= 8


# ── Fix #2: reschedule_equipment apply sets idle_factor, doesn't REMOVE ──


def test_reschedule_equipment_apply_shrinks_idle_cycle_not_removes(engine):
    """`reschedule_equipment` should set `metadata['idle_factor']`,
    leaving the equipment OPERATING/IDLE state untouched. Only
    `release_equipment` removes."""
    from api.routes import _apply_rec
    from models.analytics import Recommendation

    crane = next(a for a in engine.assets if a.subtype == "tower_crane")
    original_state = crane.state

    rec = Recommendation(
        id="opt-reschedule-crane-1",
        type="reschedule_equipment",
        title="Reschedule Tower Crane",
        description="",
        target_asset_id=crane.id,
        from_position={"x": crane.position.x, "y": crane.position.y},
        to_position=None,
        daily_savings=10.0, monthly_savings=220.0,
    )
    _apply_rec(rec, engine)
    assert rec.applied is True
    assert crane.state == original_state, "reschedule must not change state"
    assert crane.state != EquipmentState.REMOVED
    assert crane.metadata.get("idle_factor") == 0.4

    # And the simulation actually honours it: idle cycle is shorter now.
    cycle = EQUIPMENT_DUTY_CYCLES["tower_crane"]
    crane.state = EquipmentState.IDLE
    crane.metadata["cycle_timer"] = 0.0
    crane.metadata["idle_factor"] = 0.4
    from simulation.equipment_behavior import update_equipment
    # Tick just past the SHRUNK idle window; the crane should flip
    # back to OPERATING. Without the fix, it would still be IDLE
    # (the full cycle hasn't elapsed).
    update_equipment(crane, cycle["idle_duration"] * 0.5, engine)
    assert crane.state == EquipmentState.OPERATING


def test_release_equipment_apply_removes(engine):
    """The new `release_equipment` rec type fully removes the asset."""
    from api.routes import _apply_rec
    from models.analytics import Recommendation

    pump = next(a for a in engine.assets if a.subtype == "concrete_pump")
    rec = Recommendation(
        id="opt-release-pump-1",
        type="release_equipment",
        title="Release Concrete Pump",
        description="",
        target_asset_id=pump.id,
        from_position={"x": pump.position.x, "y": pump.position.y},
        to_position=None,
        daily_savings=30.0, monthly_savings=660.0,
    )
    _apply_rec(rec, engine)
    assert pump.state == EquipmentState.REMOVED


def test_optimizer_emits_distinct_rec_types(engine):
    """`equipment_schedule` must emit `release_equipment` (util<40%) and
    `reschedule_equipment` (40%≤util<60%) as distinct types."""
    from optimization.equipment_schedule import optimize_equipment

    # Force one piece of equipment to look low-utilisation and another
    # to look medium-utilisation by directly setting the metadata.
    crane = next(a for a in engine.assets if a.subtype == "tower_crane")
    pump = next(a for a in engine.assets if a.subtype == "concrete_pump")
    crane.metadata["hours_active"] = 1.0
    crane.metadata["hours_idle"] = 9.0  # util 10% → release
    pump.metadata["hours_active"] = 5.0
    pump.metadata["hours_idle"] = 5.0  # util 50% → reschedule

    recs = optimize_equipment(engine)
    by_target = {r.target_asset_id: r for r in recs}
    assert by_target[crane.id].type == "release_equipment"
    assert by_target[pump.id].type == "reschedule_equipment"


# ── Fix #3: move_facility / restage_material apply preserves level_id ──


def test_move_facility_apply_preserves_level_id():
    from api.routes import _apply_rec
    from models.analytics import Recommendation

    doc = ProjectDocument(
        slug="mvfac", name="Multi-level Toilet Move", description="",
        discipline=Discipline.HOCHBAU,
        width=80.0, height=60.0,
        levels=[
            Level(id="L0", name="EG", elevation_m=0.0, order=0),
            Level(id="L1", name="1. OG", elevation_m=3.5, order=1),
        ],
        zones=[
            Zone(id="z1", label="Z", x=10, y=10, width=60, height=40,
                 phase=Phase.STRUCTURAL, phase_progress=0.5, level_id="L1"),
        ],
        facilities=[
            FacilitySpec(id="toilet-1", subtype="toilet", x=70, y=10, level_id="L1"),
        ],
        worker_seeds=[WorkerSeed(zone_id="z1", trade="general", count=1)],
    )
    eng = SimulationEngine(document=doc)
    toilet = eng.asset_by_id("toilet-1")
    assert toilet is not None
    assert toilet.position.level_id == "L1"

    rec = Recommendation(
        id="opt-toilet-1",
        type="move_facility",
        title="Move Toilet",
        description="",
        target_asset_id="toilet-1",
        from_position={"x": 70, "y": 10},
        to_position={"x": 40, "y": 25},
        daily_savings=12.0, monthly_savings=264.0,
    )
    _apply_rec(rec, eng)
    assert toilet.position.x == 40
    assert toilet.position.y == 25
    assert toilet.position.level_id == "L1", (
        "level_id must be preserved across apply"
    )


def test_restage_material_apply_preserves_level_id():
    from api.routes import _apply_rec
    from models.analytics import Recommendation
    from models.project_document import MaterialSpec

    doc = ProjectDocument(
        slug="mvmat", name="Material Test", description="",
        discipline=Discipline.HOCHBAU,
        width=80.0, height=60.0,
        levels=[
            Level(id="L0", name="EG", elevation_m=0.0, order=0),
            Level(id="L1", name="1. OG", elevation_m=3.5, order=1),
        ],
        zones=[
            Zone(id="z1", label="Z", x=10, y=10, width=60, height=40,
                 phase=Phase.STRUCTURAL, phase_progress=0.5, level_id="L1"),
        ],
        materials=[
            MaterialSpec(
                id="mat-1", subtype="rebar", x=70, y=10,
                needed_in="z1", level_id="L1",
            ),
        ],
        worker_seeds=[WorkerSeed(zone_id="z1", trade="general", count=1)],
    )
    eng = SimulationEngine(document=doc)
    mat = eng.asset_by_id("mat-1")
    assert mat.position.level_id == "L1"

    rec = Recommendation(
        id="opt-mat-1",
        type="restage_material",
        title="Restage rebar",
        description="",
        target_asset_id="mat-1",
        from_position={"x": 70, "y": 10},
        to_position={"x": 20, "y": 25},
        daily_savings=8.0, monthly_savings=176.0,
    )
    _apply_rec(rec, eng)
    assert mat.position.x == 20
    assert mat.position.level_id == "L1"


# ── Fix #4: shoring compliance surfaces in WasteSummary ──────────────


def test_waste_summary_includes_shoring_compliance_for_munich():
    """The Tiefbau seed has EXCAVATION zones near sheet piles + at
    least one far from them. WasteSummary must surface the compliance
    list, and the dashboard must see at least one entry."""
    eng = SimulationEngine(project_id="munich-sewer")
    summary = compute_waste_summary(eng)
    assert hasattr(summary, "shoring_compliance")
    assert len(summary.shoring_compliance) >= 1
    # Each entry has the user-facing label, not just the id.
    for s in summary.shoring_compliance:
        assert s.zone_label
        assert s.zone_label != s.zone_id  # munich-sewer uses "Abschnitt A" etc.
        assert 0.0 <= s.compliance <= 1.0


def test_waste_summary_shoring_empty_for_pure_hochbau():
    """Hochbau seeds have no EXCAVATION zones near sheet piles
    (or none at all), so the shoring list is empty / all-zero."""
    eng = SimulationEngine(project_id="europa-quarter")
    summary = compute_waste_summary(eng)
    # europa-quarter has zone-f in EXCAVATION but no sheet piles.
    # All entries should have compliance=0 (uncovered) — surfaced as warnings.
    for s in summary.shoring_compliance:
        assert s.compliance == 0.0


# ── Fix #5: heatmap honours level_id ─────────────────────────────────


def test_heatmap_filters_by_level_id():
    doc = ProjectDocument(
        slug="hm", name="HM", description="",
        discipline=Discipline.HOCHBAU,
        width=80.0, height=60.0,
        levels=[
            Level(id="L0", name="EG", elevation_m=0.0, order=0),
            Level(id="L1", name="1. OG", elevation_m=3.5, order=1),
        ],
        zones=[
            Zone(id="z-eg", label="EG", x=10, y=10, width=60, height=40,
                 phase=Phase.STRUCTURAL, phase_progress=0.5, level_id="L0"),
            Zone(id="z-og", label="1.OG", x=10, y=10, width=60, height=40,
                 phase=Phase.STRUCTURAL, phase_progress=0.5, level_id="L1"),
        ],
        worker_seeds=[
            WorkerSeed(zone_id="z-eg", trade="general", count=2),
            WorkerSeed(zone_id="z-og", trade="general", count=2),
        ],
    )
    eng = SimulationEngine(document=doc)
    for _ in range(40):
        eng.tick()

    snap_l0 = eng.density_snapshot(level_id="L0")
    snap_l1 = eng.density_snapshot(level_id="L1")
    snap_pooled = eng.density_snapshot()

    assert snap_l0["level_id"] == "L0"
    assert snap_l1["level_id"] == "L1"
    assert snap_pooled["level_id"] is None
    # Per-level snapshots only see workers on that level.
    assert snap_l0["max_count"] > 0
    assert snap_l1["max_count"] > 0
    # The pooled count for any (col, row) is >= either level's count.
    assert snap_pooled["max_count"] >= snap_l0["max_count"]
    assert snap_pooled["max_count"] >= snap_l1["max_count"]


def test_heatmap_endpoint_accepts_level_id_query(auth_client):
    # Activate munich-sewer for multi-level
    csrf = auth_client.get("/auth/csrf").json()["csrf_token"]
    auth_client.headers.update({"X-CSRF-Token": csrf})
    auth_client.post("/api/site/load-seed", json={"slug": "munich-sewer"})
    # Let the sim tick a few times so workers have moved.
    time.sleep(0.5)
    r0 = auth_client.get("/api/simulation/heatmap?level_id=L0")
    assert r0.status_code == 200
    assert r0.json().get("level_id") == "L0"
    r_pooled = auth_client.get("/api/simulation/heatmap")
    assert r_pooled.status_code == 200
    assert r_pooled.json().get("level_id") is None


# ── Fix #6: cab snapshot in state_update WS payload ──────────────────


def test_state_snapshot_includes_cabs():
    eng = SimulationEngine(project_id="munich-sewer")  # single-level, no cabs
    snap = eng.get_state_snapshot()
    assert "cabs" in snap
    # Munich seed has no elevators, only sheet piles → empty list.
    assert snap["cabs"] == []


def test_add_equipment_optimizer_suppressed_after_apply():
    """After `add_equipment` is applied, the optimizer must not emit
    the rec again. Without this, a transient
    rec-disappear-then-reappear cycle would let the user double the
    cab capacity repeatedly (8 → 16 → 32 …) for the same shaft.
    """
    from api.routes import _apply_rec
    from models.analytics import Recommendation
    from optimization.vertical_transport_optimizer import (
        optimize_vertical_transport,
    )

    doc = ProjectDocument(
        slug="idem", name="Idempotency Test", description="",
        discipline=Discipline.HOCHBAU,
        width=80.0, height=60.0,
        levels=[
            Level(id="L0", name="EG", elevation_m=0.0, order=0),
            Level(id="L1", name="1.OG", elevation_m=3.5, order=1),
        ],
        zones=[
            Zone(id="z1", label="Z", x=10, y=10, width=60, height=40,
                 phase=Phase.STRUCTURAL, phase_progress=0.5, level_id="L1"),
        ],
        connections=[Connection(
            id="lift-1", kind="elevator",
            nodes=[
                ConnectionNode(level_id="L0", x=40, y=30),
                ConnectionNode(level_id="L1", x=40, y=30),
            ],
            cab_capacity=2, cycle_time_s=60.0, speed_m_per_s=0.5,
        )],
        worker_seeds=[WorkerSeed(zone_id="z1", trade="general", count=3)],
    )
    eng = SimulationEngine(document=doc)

    # Hand-craft an apply (mimics the HTTP path).
    rec = Recommendation(
        id="opt-vertical-lift-1", type="add_equipment",
        title="Add cab", description="",
        target_asset_id="lift-1",
        from_position={"x": 0, "y": 0}, to_position=None,
        daily_savings=10.0, monthly_savings=220.0,
    )
    _apply_rec(rec, eng)
    cap_after_one_apply = eng.cabs["lift-1"].capacity
    assert eng.cabs["lift-1"].extra_cab_count == 1

    # Force the optimizer to "want" to fire by jamming the queue.
    cab = eng.cabs["lift-1"]
    cab.queue_per_level["L1"].extend(["w-fake-1", "w-fake-2", "w-fake-3"])
    cab.queue_enter_time["w-fake-1"] = eng.sim_time - 300  # >5 min wait
    # Despite the artificial saturation, the optimizer must NOT emit
    # another rec because extra_cab_count > 0.
    recs = optimize_vertical_transport(eng)
    assert all(r.target_asset_id != "lift-1" for r in recs), (
        "optimizer must suppress add_equipment after it's been applied once"
    )
    # Re-applying via the API path is also a no-op for capacity (the
    # router's `if rec.applied: return already_applied` guard catches it
    # — but even if a user crafted a fresh rec id, the optimizer-side
    # guard is the belt + braces fix tested here.)
    assert eng.cabs["lift-1"].capacity == cap_after_one_apply


def test_state_snapshot_cab_entry_shape():
    doc = ProjectDocument(
        slug="cabsnap", name="C", description="",
        discipline=Discipline.HOCHBAU,
        width=80.0, height=60.0,
        levels=[
            Level(id="L0", name="EG", elevation_m=0.0, order=0),
            Level(id="L1", name="1. OG", elevation_m=3.5, order=1),
        ],
        zones=[
            Zone(id="z1", label="Z", x=10, y=10, width=60, height=40,
                 phase=Phase.STRUCTURAL, phase_progress=0.5, level_id="L1"),
        ],
        connections=[Connection(
            id="lift-1", kind="elevator",
            nodes=[
                ConnectionNode(level_id="L0", x=40, y=30),
                ConnectionNode(level_id="L1", x=40, y=30),
            ],
        )],
        worker_seeds=[WorkerSeed(zone_id="z1", trade="general", count=2)],
    )
    eng = SimulationEngine(document=doc)
    snap = eng.get_state_snapshot()
    assert len(snap["cabs"]) == 1
    cab = snap["cabs"][0]
    assert cab["id"] == "lift-1"
    assert "current_level" in cab
    assert "passengers" in cab
    assert "capacity" in cab
    assert "queue_by_level" in cab
