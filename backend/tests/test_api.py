"""End-to-end HTTP tests against the FastAPI app via TestClient (in-process,
real lifespan, real engine + analytics loop)."""
from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient


class _NoopDetector:
    """Stub that skips YOLO model loading — keeps tests fast/deterministic."""
    def get_video_ids(self): return []
    def get_video_info(self, _): return None
    def get_next_frame(self, *_args, **_kw): return None
    def cleanup(self): pass


@pytest.fixture
def client():
    # Force the camera detector to a no-op for the duration of this test.
    import vision.detector as vd
    original = vd.VideoDetector
    vd.VideoDetector = _NoopDetector  # type: ignore[misc]
    try:
        # Build a fresh app per fixture so app.state is isolated.
        from main import create_app
        app = create_app()
        with TestClient(app) as c:
            # Allow the analytics task to compute at least once
            time.sleep(1.2)
            yield c
    finally:
        vd.VideoDetector = original


def test_get_projects(client):
    r = client.get("/api/projects")
    assert r.status_code == 200
    projects = r.json()
    assert len(projects) == 3
    ids = {p["id"] for p in projects}
    assert ids == {"westhafen", "europa-quarter", "isar-bridge"}


def test_get_site_returns_zones_and_schedule(client):
    r = client.get("/api/site")
    assert r.status_code == 200
    site = r.json()
    assert "zones" in site
    assert "schedule" in site
    assert len(site["zones"]) >= 5  # westhafen has 5


def test_recommendations_become_available(client):
    """After analytics loop has had time to run, recs should appear."""
    # Wait up to 5s for first recs
    for _ in range(10):
        r = client.get("/api/recommendations")
        if r.status_code == 200 and len(r.json()) > 0:
            break
        time.sleep(0.5)
    assert r.status_code == 200
    recs = r.json()
    assert len(recs) > 0, "no recommendations after waiting"
    # Each rec should have a TYPED from_position object now (not raw dict)
    for rec in recs:
        assert "from_position" in rec
        assert "x" in rec["from_position"]
        assert "y" in rec["from_position"]


def test_bug1_project_switch_clears_recs_immediately(client):
    """Switching projects must purge old project's recs from the cache."""
    # Force at least one rec computation for westhafen
    for _ in range(10):
        r = client.get("/api/recommendations")
        if len(r.json()) > 0:
            break
        time.sleep(0.5)
    west_recs = r.json()
    west_targets = {x["target_asset_id"] for x in west_recs}

    # Switch to europa-quarter
    r = client.post("/api/projects/europa-quarter/load")
    assert r.status_code == 200
    assert r.json()["status"] == "loaded"

    # The very next recommendations call must yield europa-quarter recs
    # (project_id mismatch detection should force a refresh on first call)
    r2 = client.get("/api/recommendations")
    assert r2.status_code == 200
    frank_recs = r2.json()
    frank_targets = {x["target_asset_id"] for x in frank_recs}

    # europa-quarter has crane-2 — westhafen does NOT
    # westhafen has exactly 3 equipment (crane-1, pump-1, excavator-1)
    # europa-quarter has 4 (crane-1, crane-2, pump-1, excavator-1)
    # Verify the sets are different
    assert frank_targets != west_targets or len(frank_targets) != len(west_targets), (
        f"recommendations didn't change after project switch: {frank_targets}"
    )


def test_bug16_asset_detail_zone_label_in_response(client):
    r = client.get("/api/site")
    site = r.json()
    # Find a worker asset id by checking the websocket-equivalent state snapshot
    r2 = client.get("/api/simulation/state")
    state = r2.json()
    worker = next(a for a in state["assets"] if a["type"] == "worker")
    r3 = client.get(f"/api/assets/{worker['id']}")
    assert r3.status_code == 200
    data = r3.json()
    assert "assigned_zone_label" in data
    assert data["assigned_zone_label"] is not None


def test_bug3_404_handled_cleanly(client):
    """A 404 on /api/assets/{id} should return a JSON 404, not crash."""
    r = client.get("/api/assets/does-not-exist")
    assert r.status_code == 404
    assert r.json() == {"detail": "Asset not found"}


def test_bug3_load_invalid_project_returns_404(client):
    r = client.post("/api/projects/no-such-project/load")
    assert r.status_code == 404


def test_apply_recommendation_uses_typed_position(client):
    """Bug #28 regression: apply must read .x/.y, not ["x"]/["y"]."""
    # Wait for recs to be populated
    for _ in range(10):
        recs = client.get("/api/recommendations").json()
        if recs:
            break
        time.sleep(0.5)
    assert recs

    # Pick a move_facility rec (which has a to_position)
    movable = next((r for r in recs if r["type"] == "move_facility"), None)
    if movable is None:
        movable = next((r for r in recs if r["type"] == "restage_material"), None)
    assert movable is not None, "no rec with a to_position to test apply"

    r = client.post(f"/api/recommendations/{movable['id']}/apply")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] in {"applied", "already_applied"}


def test_apply_all_succeeds(client):
    """End-to-end apply-all flow."""
    for _ in range(10):
        if client.get("/api/recommendations").json():
            break
        time.sleep(0.5)
    r = client.post("/api/recommendations/apply-all")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
