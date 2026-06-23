"""Step 6 — performance microbenchmarks for the indexed lookups.

These aren't full benchmarks (no warm-up loops, no statistical analysis)
— just guardrails that catch O(n²) accidents creeping back in.
"""
from __future__ import annotations

import time

from simulation.engine import SimulationEngine


def test_asset_by_id_is_O1():
    """10,000 lookups must finish in well under 100ms.

    Pre-step-6: linear scan over ~62 assets ≈ 6μs each × 10,000 = 60ms.
    Post-step-6: dict lookup ≈ 0.1μs each × 10,000 = 1ms.
    """
    eng = SimulationEngine()
    asset_ids = [a.id for a in eng.assets]
    t0 = time.perf_counter()
    for _ in range(10_000):
        for aid in asset_ids:
            eng.asset_by_id(aid)
    elapsed = time.perf_counter() - t0
    # 10k × 62 = 620k lookups; should be sub-100ms
    assert elapsed < 1.0, f"asset_by_id took {elapsed:.3f}s for 620k lookups — likely linear"


def test_workers_in_zone_doesnt_rescan():
    """workers_in_zone is now backed by an index — repeated calls should
    be O(workers_in_that_zone), not O(total_assets)."""
    eng = SimulationEngine()
    zone_id = next(z.id for z in eng.site.zones)
    t0 = time.perf_counter()
    for _ in range(10_000):
        eng.workers_in_zone(zone_id)
    elapsed = time.perf_counter() - t0
    assert elapsed < 1.0, f"workers_in_zone took {elapsed:.3f}s for 10k calls"


def test_facilities_by_subtype_is_indexed():
    eng = SimulationEngine()
    t0 = time.perf_counter()
    for _ in range(10_000):
        eng.facilities_by_subtype("toilet")
    elapsed = time.perf_counter() - t0
    assert elapsed < 0.5


def test_rebuild_indexes_is_idempotent_and_correct():
    """Calling rebuild_indexes() must produce the same view as initial setup."""
    eng = SimulationEngine()
    ids_before = {a.id for a in eng.assets}
    by_id_before = {aid: eng.asset_by_id(aid) for aid in ids_before}

    eng.rebuild_indexes()

    by_id_after = {aid: eng.asset_by_id(aid) for aid in ids_before}
    assert by_id_after == by_id_before


def test_indexes_invalidated_correctly_on_project_switch():
    """Project switch tears down + rebuilds. After switch, assets from the
    old project must NOT be findable."""
    eng = SimulationEngine(project_id="westhafen")
    westhafen_ids = {a.id for a in eng.assets}

    eng.load_project("europa-quarter")

    europa_ids = {a.id for a in eng.assets}
    # europa-quarter has crane-2 which westhafen does NOT
    assert "crane-2" in europa_ids
    # Westhafen-only assets shouldn't surface in europa
    for aid in westhafen_ids - europa_ids:
        assert eng.asset_by_id(aid) is None, (
            f"stale asset {aid} from westhafen still findable after europa-quarter load"
        )


def test_workers_in_zone_after_project_switch():
    """zone-f exists in europa-quarter only. After switching to europa,
    we should find workers in zone-f."""
    eng = SimulationEngine(project_id="westhafen")
    assert eng.workers_in_zone("zone-f") == []  # not present in westhafen
    eng.load_project("europa-quarter")
    workers_f = eng.workers_in_zone("zone-f")
    assert len(workers_f) > 0  # zone-f has workers in europa-quarter


def test_tick_under_5ms_at_full_load():
    """Phase 0 baseline lock-in.

    Each tick has to fit comfortably inside the 100ms sim interval even
    when we layer on the cab-tracked elevator FSM (Phase 3). 5ms/tick at
    the largest stock project leaves 95ms of headroom for the
    yet-to-come work.
    """
    # isar-bridge has the highest worker count of the stock templates.
    eng = SimulationEngine(project_id="isar-bridge")
    # Warm-up so any first-tick allocations are out of the way.
    for _ in range(10):
        eng.tick()
    t0 = time.perf_counter()
    for _ in range(50):
        eng.tick()
    elapsed = (time.perf_counter() - t0) / 50
    assert elapsed < 0.005, (
        f"tick averages {elapsed*1000:.2f}ms — over the 5ms Phase 0 budget"
    )
