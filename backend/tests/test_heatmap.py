"""Tests for the cumulative heatmap (density grid) feature."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from simulation.engine import SimulationEngine


def test_density_grid_starts_empty():
    eng = SimulationEngine()
    snap = eng.density_snapshot()
    assert snap["max_count"] == 0
    assert snap["cells"] == []
    assert snap["cell_size"] == SimulationEngine.DENSITY_CELL_SIZE


def test_density_grid_accumulates_over_ticks():
    eng = SimulationEngine()
    for _ in range(50):
        eng.tick()
    snap = eng.density_snapshot()
    assert snap["max_count"] > 0
    assert len(snap["cells"]) > 0
    # Every cell is [col, row, normalised_intensity in 0..1]
    for col, row, intensity in snap["cells"]:
        assert isinstance(col, int) and isinstance(row, int)
        assert 0 < intensity <= 1.0


def test_density_grid_resets_at_day_boundary():
    eng = SimulationEngine()
    for _ in range(50):
        eng.tick()
    pre = eng.density_snapshot()
    assert pre["max_count"] > 0

    # Force a day rollover
    eng._reset_daily_counters()
    post = eng.density_snapshot()
    assert post["max_count"] == 0
    assert post["cells"] == []


def test_density_grid_sparse_only_visited_cells():
    """The grid should not pre-allocate empty cells across the whole site."""
    eng = SimulationEngine()
    eng.tick()
    snap = eng.density_snapshot()
    # 240×160 / 4×4 = 60 × 40 = 2400 possible cells. After 1 tick we have
    # at most 50 cells (one per worker, often fewer due to collisions).
    assert len(snap["cells"]) <= 50


def test_heatmap_endpoint_returns_shape(auth_client):
    r = auth_client.get("/api/simulation/heatmap")
    assert r.status_code == 200
    body = r.json()
    for k in ("cell_size", "site_width", "site_height", "max_count", "cells"):
        assert k in body, f"missing key {k}"
    assert body["site_width"] > 0


def test_heatmap_endpoint_payload_stays_small():
    """Sparse grid is a hard requirement — fail loud if anyone changes
    density_snapshot to emit a dense array."""
    import json
    eng = SimulationEngine()
    for _ in range(500):  # ~25 sim-minutes
        eng.tick()
    snap = eng.density_snapshot()
    raw = json.dumps(snap)
    # 60 × 40 = 2400 possible cells × ~15 chars each = 36 KB upper bound.
    # In practice workers cluster so we see far less.
    assert len(raw) < 60_000, (
        f"heatmap payload is {len(raw)} bytes — probably emitting a dense grid"
    )


def test_heatmap_density_concentrates_near_busy_areas():
    """Force-place all workers near a single point and verify the heatmap
    cell containing that point becomes the hotspot."""
    from models.assets import Position
    eng = SimulationEngine()
    workers = [a for a in eng.assets if a.type == "worker"]
    # Pin them at (50, 50) — the cell containing this point should win
    for w in workers:
        w.position = Position(x=50.0, y=50.0)
    # Trigger position-record (engine.tick does this last)
    for _ in range(10):
        eng._record_positions()
    snap = eng.density_snapshot()
    # The cell at col=12, row=12 (50 // 4 = 12) should have intensity 1.0
    hotspot = next(((c, r, i) for c, r, i in snap["cells"] if c == 12 and r == 12), None)
    assert hotspot is not None, "hotspot cell missing"
    assert hotspot[2] == 1.0  # normalised peak
