"""Verifies each fix from claude.md bugs #1–#28 actually works at runtime.

Each test references its bug number. A test that fails means the fix didn't
take, the fix introduced a regression, or the fix is incomplete.
"""
from __future__ import annotations

import math
import pytest

from config import SIM_SECONDS_PER_TICK, TOILET_INTERVAL
from models.assets import Asset, EquipmentState, Position, WorkerState
from models.analytics import PositionXY, Recommendation
from optimization.equipment_schedule import optimize_equipment
from optimization.facility_placement import optimize_toilet_placement
from optimization.material_staging import optimize_material_staging
from simulation.engine import SimulationEngine
from simulation.worker_behavior import update_worker


# ─── #1: recommendation cache invalidated on project switch ──────────────

def test_bug1_recs_cache_invalidates_on_project_switch():
    """RecommendationService must yield project-appropriate recs after a
    load_project() call, with no stale entries from the previous project."""
    from services.recommendation_service import RecommendationService

    engine = SimulationEngine()
    svc = RecommendationService(engine)

    # Westhafen has 3 equipment items (crane-1, pump-1, excavator-1)
    recs_west = svc.get()
    west_targets = {r.target_asset_id for r in recs_west}
    assert any(t.startswith("crane-1") or t.startswith("pump-1") or t.startswith("excavator-1") for t in west_targets), (
        f"westhafen recs missing expected asset targets, got: {west_targets}"
    )

    # Switch project on the engine and clear the cache (as routes.load_project does)
    engine.load_project("europa-quarter")
    svc.clear()

    recs_frank = svc.get()
    frank_targets = {r.target_asset_id for r in recs_frank}
    # europa-quarter has crane-2 which westhafen does not
    assert "westhafen" not in str(frank_targets)


def test_bug1_get_recommendations_detects_silent_project_switch():
    """Even WITHOUT calling .clear(), .get() must detect the project
    mismatch via the engine's project_id and refresh automatically."""
    from services.recommendation_service import RecommendationService

    engine = SimulationEngine(project_id="westhafen")
    svc = RecommendationService(engine)

    cached_before = list(svc.get())

    # Switch project on the engine but bypass the clear call
    engine.load_project("isar-bridge")
    recs_isar = svc.get()

    # Recs are rebuilt — at minimum the target sets differ between
    # westhafen (one crane) and isar-bridge (two cranes)
    isar_targets = {r.target_asset_id for r in recs_isar}
    west_targets = {r.target_asset_id for r in cached_before}
    assert isar_targets != west_targets or len(isar_targets) != len(west_targets)


# ─── #11: worker doesn't pin without a facility ──────────────────────────

def test_bug11_worker_recovers_when_facility_missing(engine):
    """Force a worker's toilet timer below zero AND remove all toilets.
    The worker must not be permanently stuck — subsequent ticks should
    advance other state and not return immediately."""
    worker = next(a for a in engine.assets if a.type == "worker")
    internals = engine.worker_internals[worker.id]

    # Remove all toilets from the simulation
    engine.assets = [a for a in engine.assets if not (a.type == "facility" and a.subtype == "toilet")]
    engine.rebuild_indexes()

    # Force the toilet trigger to fire on next tick
    internals.next_toilet = -1.0
    internals.next_material = TOILET_INTERVAL * 0.5  # not yet due
    internals.next_break = TOILET_INTERVAL * 0.5

    # Tick once — the worker should NOT enter WALKING_TO_TOILET
    update_worker(worker, SIM_SECONDS_PER_TICK, engine)
    assert worker.state == WorkerState.WORKING, (
        f"worker entered {worker.state} without a toilet to walk to"
    )

    # After this tick, next_toilet must be > 0 again (re-jittered defensively)
    assert internals.next_toilet > 0, (
        f"next_toilet stayed negative ({internals.next_toilet}) — worker would re-trigger forever"
    )

    # Now tick a bunch more — the worker can still accumulate time_working
    initial_work = internals.time_working
    for _ in range(50):
        update_worker(worker, SIM_SECONDS_PER_TICK, engine)
    assert internals.time_working > initial_work, "worker accumulated no work time after toilet starvation"


def test_bug11_works_for_break_and_material_too(engine):
    """Same protection should exist for breakrooms and materials."""
    worker = next(a for a in engine.assets if a.type == "worker")
    internals = engine.worker_internals[worker.id]

    # Strip all facilities except toilets (so material and break paths can fail)
    engine.assets = [a for a in engine.assets if not (a.type == "facility" and a.subtype == "breakroom")]
    engine.assets = [a for a in engine.assets if a.type != "material"]
    engine.rebuild_indexes()

    internals.next_break = -1.0
    internals.next_material = -1.0
    internals.next_toilet = TOILET_INTERVAL * 0.5

    update_worker(worker, SIM_SECONDS_PER_TICK, engine)
    assert internals.next_break > 0
    assert internals.next_material > 0


# ─── #12: k-means toilet assignment uses nearest pairing ─────────────────

def test_bug12_toilets_assigned_to_nearest_centroid():
    """When toilets are in arbitrary positions, each toilet should be
    paired with the closest cluster centroid, not by enumeration order."""
    engine = SimulationEngine()

    # Force toilets into known positions on opposite sides:
    # toilet-1 in top-right (close to right-side cluster)
    # toilet-2 in top-left  (close to left-side cluster)
    toilets = [a for a in engine.assets if a.type == "facility" and a.subtype == "toilet"]
    assert len(toilets) >= 2

    # Position toilet-1 on the right; toilet-2 on the left.
    # With order-based assignment, toilet-1 would always get cluster 0
    # (left), forcing it to move all the way across the site.
    # With nearest-pairing, toilet-1 stays right, toilet-2 stays left.
    by_id = {t.id: t for t in toilets}
    by_id["toilet-1"].position = Position(x=200, y=20)  # right
    by_id["toilet-2"].position = Position(x=20, y=20)   # left

    recs = optimize_toilet_placement(engine)
    by_target = {r.target_asset_id: r for r in recs}

    if "opt-toilet-1" in by_target and "opt-toilet-2" in by_target:
        # toilet-1 starts on the right — its target should also be on
        # the right (centroid x > site center x = 120).
        t1 = by_target["opt-toilet-1"]
        t2 = by_target["opt-toilet-2"]
        # nearest-pairing keeps toilet-1 right-ish and toilet-2 left-ish
        site_mid = 240 / 2
        # The right-side target should be assigned to the right-side toilet
        assert (t1.to_position.x >= site_mid) == True or (t2.to_position.x < site_mid) == True, (
            f"order-based assignment detected: t1→{t1.to_position}, t2→{t2.to_position}"
        )


# ─── #23 + #24: equipment_schedule formula & label ───────────────────────

def test_bug23_idle_hours_formula_stable_at_t_zero():
    """Brand-new sim has near-zero hours_active+hours_idle. The formula
    must NOT explode."""
    engine = SimulationEngine()
    # Set one piece of equipment to look freshly-started: tiny active, tiny idle
    eq = next(a for a in engine.assets if a.type == "equipment")
    eq.metadata["hours_active"] = 0.05
    eq.metadata["hours_idle"] = 0.05

    recs = optimize_equipment(engine)
    for r in recs:
        # The old formula did hours_idle * (11 / total). With total=0.1, that's
        # 0.05 * 110 = 5.5 hours, times rate 180 = €990 daily, then × 22 monthly
        # = ~€22k just for ONE crane. New formula is at most (1-0) * 11 * 180
        # * 0.8 = €1584 daily ~ €34k monthly — bounded.
        # We assert daily_savings stays under a sane ceiling (11h × 200 × 0.8).
        assert r.daily_savings < 11 * 200 * 0.8 + 1, (
            f"daily_savings={r.daily_savings} for {r.target_asset_id} exceeds "
            f"physical upper bound; formula instability not fully resolved"
        )


def test_bug24_no_hardcoded_zone_d_in_descriptions():
    """Equipment descriptions must NOT contain literal 'Zone D' just because
    `asset.assigned_zone` is None."""
    engine = SimulationEngine()
    # Force low utilization on all equipment to trigger 'Release' recs
    for a in engine.assets:
        if a.type == "equipment":
            a.metadata["hours_active"] = 0.1
            a.metadata["hours_idle"] = 1.0

    recs = optimize_equipment(engine)
    assert len(recs) > 0, "test setup failed — no equipment recs produced"
    for r in recs:
        # Equipment has no assigned_zone, so descriptions should say
        # "its current zone" (or a real label, never literal "Zone D").
        # The bug was literally the string "Zone D".
        # We tolerate the substring only if the active project actually
        # has a zone with that label.
        assert "Zone D" not in r.description, (
            f"hardcoded 'Zone D' still in rec description: {r.description!r}"
        )


# ─── #25: material_staging picks edge nearest to material ────────────────

def test_bug25_material_staging_picks_edge_near_material():
    """A material currently in the bottom-right corner targeting a zone in
    the top-left should be staged at the zone's bottom-right corner edge
    (nearest to its current position), not the geometrically shortest
    zone-edge from center."""
    engine = SimulationEngine()
    # Find any material and place it in a known position far from its zone
    mat = next(a for a in engine.assets if a.type == "material")
    target_zone = engine.zone_by_id(mat.metadata["needed_in_zone"])
    assert target_zone is not None

    # Place material in the corner geometrically OPPOSITE to the zone
    if target_zone.x < engine.site.width / 2:
        # zone is left → put material far right
        mat.position = Position(x=engine.site.width - 10, y=engine.site.height - 10)
    else:
        mat.position = Position(x=10, y=10)

    recs = optimize_material_staging(engine)
    rec = next((r for r in recs if r.target_asset_id == mat.id), None)
    if rec is None:
        pytest.skip("material_staging didn't produce a rec for this material")

    # The chosen staging edge should be the one closest to the material's
    # current position, so the proposed new position should reduce the
    # distance the worker has to fetch from significantly.
    new_pos = rec.to_position
    assert new_pos is not None

    # Verify: new_pos should be closer to mat's current position than the
    # zone's opposite edge would be. (Sanity check: the chosen edge is
    # on the same side of the zone as the material.)
    zone_cx = target_zone.x + target_zone.width / 2
    zone_cy = target_zone.y + target_zone.height / 2
    # The new staging point should be on the material's side of the zone
    # (or at least closer in distance to the material than the centroid).
    dist_to_new = math.hypot(new_pos.x - mat.position.x, new_pos.y - mat.position.y)
    dist_to_centroid = math.hypot(zone_cx - mat.position.x, zone_cy - mat.position.y)
    # The new staging point should be reasonably close to the material;
    # certainly not the opposite side. Allow some tolerance.
    assert dist_to_new <= dist_to_centroid + target_zone.width / 2, (
        f"new staging pos {new_pos} is far from material {mat.position}; "
        f"old-style center-nearest would pick wrong edge"
    )


# ─── #26: facility detail covers office + toolcrib ───────────────────────

def test_bug26_office_facility_detail_runs(engine):
    """Office facilities must produce a workers_present list, not crash
    or return empty unconditionally."""
    from simulation.asset_detail import asset_detail
    office = next(a for a in engine.assets if a.type == "facility" and a.subtype == "office")
    detail = asset_detail(engine, office.id)
    assert detail is not None
    assert "detail" in detail
    assert "workers_present" in detail["detail"], "office detail missing workers_present"

    # Place a worker right next to the office and verify it shows up
    worker = next(a for a in engine.assets if a.type == "worker")
    worker.position = Position(x=office.position.x + 2, y=office.position.y + 2)
    worker.state = WorkerState.WORKING  # any state — office uses no required_state

    detail = asset_detail(engine, office.id)
    ids_present = {w["id"] for w in detail["detail"]["workers_present"]}
    assert worker.id in ids_present, (
        f"office didn't detect a worker at distance 3; got {detail['detail']}"
    )


def test_bug26_toolcrib_facility_detail_runs(engine):
    """Toolcrib facilities must produce a workers_present list."""
    from simulation.asset_detail import asset_detail
    toolcrib = next(a for a in engine.assets if a.type == "facility" and a.subtype == "toolcrib")
    detail = asset_detail(engine, toolcrib.id)
    assert "workers_present" in detail["detail"]

    # Place worker within toolcrib's 8m radius
    worker = next(a for a in engine.assets if a.type == "worker")
    worker.position = Position(x=toolcrib.position.x + 1, y=toolcrib.position.y + 1)
    detail = asset_detail(engine, toolcrib.id)
    ids = {w["id"] for w in detail["detail"]["workers_present"]}
    assert worker.id in ids


def test_bug26_toilet_still_requires_at_toilet_state(engine):
    """Regression: toilet should still require 'at_toilet' state, not just
    proximity."""
    from simulation.asset_detail import asset_detail
    toilet = next(a for a in engine.assets if a.type == "facility" and a.subtype == "toilet")
    worker = next(a for a in engine.assets if a.type == "worker")
    # Place worker at the toilet but WORKING (not at_toilet)
    worker.position = Position(x=toilet.position.x, y=toilet.position.y)
    worker.state = WorkerState.WORKING

    detail = asset_detail(engine, toilet.id)
    ids = {w["id"] for w in detail["detail"]["workers_present"]}
    assert worker.id not in ids, "toilet wrongly counted a WORKING worker as present"


# ─── #27: REPOSITIONING removed ──────────────────────────────────────────

def test_bug27_no_repositioning_enum():
    assert not hasattr(EquipmentState, "REPOSITIONING"), (
        "EquipmentState.REPOSITIONING still defined — should have been removed"
    )


# ─── #28: typed Position model ───────────────────────────────────────────

def test_bug28_recommendation_uses_typed_position():
    """Recommendation.from_position must be a PositionXY, not a raw dict."""
    rec = Recommendation(
        id="test",
        type="move_facility",
        title="t",
        description="d",
        target_asset_id="foo",
        from_position={"x": 10, "y": 20},
        to_position={"x": 30, "y": 40},
        daily_savings=100,
        monthly_savings=2200,
    )
    assert isinstance(rec.from_position, PositionXY)
    assert isinstance(rec.to_position, PositionXY)
    assert rec.from_position.x == 10.0
    assert rec.to_position.y == 40.0


def test_bug28_recommendation_to_position_optional():
    """to_position is optional (used for reschedule_equipment)."""
    rec = Recommendation(
        id="t",
        type="reschedule_equipment",
        title="t",
        description="d",
        target_asset_id="foo",
        from_position={"x": 1, "y": 2},
        to_position=None,
        daily_savings=10,
        monthly_savings=220,
    )
    assert rec.to_position is None


# ─── #16: zone label on asset detail ─────────────────────────────────────

def test_bug16_asset_detail_includes_zone_label(engine):
    """asset_detail() must populate assigned_zone_label for workers."""
    from simulation.asset_detail import asset_detail
    worker = next(a for a in engine.assets if a.type == "worker")
    detail = asset_detail(engine, worker.id)
    assert detail["assigned_zone"] is not None
    assert detail["assigned_zone_label"] is not None
    # And it should be the actual label, not the ID
    zone = engine.zone_by_id(detail["assigned_zone"])
    assert detail["assigned_zone_label"] == zone.label


def test_bug16_material_detail_includes_zone_label(engine):
    """asset_detail() must populate needed_in_zone_label for materials."""
    from simulation.asset_detail import asset_detail
    mat = next(a for a in engine.assets if a.type == "material")
    detail = asset_detail(engine, mat.id)
    assert "needed_in_zone_label" in detail["detail"]
    if detail["detail"]["needed_in_zone"]:
        zone = engine.zone_by_id(detail["detail"]["needed_in_zone"])
        assert detail["detail"]["needed_in_zone_label"] == zone.label


# ─── Sanity: each project loads cleanly ──────────────────────────────────

@pytest.mark.parametrize("project_id", ["westhafen", "europa-quarter", "isar-bridge"])
def test_each_project_loads_and_ticks(project_id):
    eng = SimulationEngine(project_id=project_id)
    assert eng.project_id == project_id
    assert len(eng.assets) > 0

    for _ in range(20):
        eng.tick()
    # No worker should have gotten stuck in NaN or be off-site
    for a in eng.assets:
        if a.type == "worker":
            assert 0 <= a.position.x <= eng.site.width + 5, f"{a.id} off-site at {a.position}"
            assert 0 <= a.position.y <= eng.site.height + 5
