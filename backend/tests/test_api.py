"""End-to-end HTTP tests against the FastAPI app via TestClient (in-process,
real lifespan, real engine + analytics loop).

Now uses the `auth_client` fixture from conftest, which signs up a real
user and attaches a session cookie + CSRF header so the org-scoped
routes accept the requests.
"""
from __future__ import annotations

import time


def test_get_projects(auth_client):
    r = auth_client.get("/api/projects")
    assert r.status_code == 200
    projects = r.json()
    assert len(projects) == 3
    ids = {p["id"] for p in projects}
    assert ids == {"westhafen", "europa-quarter", "isar-bridge"}


def test_get_site_returns_zones_and_schedule(auth_client):
    r = auth_client.get("/api/site")
    assert r.status_code == 200
    site = r.json()
    assert "zones" in site
    assert "schedule" in site
    assert len(site["zones"]) >= 5  # westhafen has 5


def test_recommendations_become_available(auth_client):
    """After analytics loop has had time to run, recs should appear."""
    for _ in range(10):
        r = auth_client.get("/api/recommendations")
        if r.status_code == 200 and len(r.json()) > 0:
            break
        time.sleep(0.5)
    assert r.status_code == 200
    recs = r.json()
    assert len(recs) > 0, "no recommendations after waiting"
    for rec in recs:
        assert "from_position" in rec
        assert "x" in rec["from_position"]
        assert "y" in rec["from_position"]


def test_bug1_project_switch_clears_recs_immediately(auth_client):
    """Switching projects must purge old project's recs from the cache."""
    for _ in range(10):
        r = auth_client.get("/api/recommendations")
        if len(r.json()) > 0:
            break
        time.sleep(0.5)
    west_recs = r.json()
    west_targets = {x["target_asset_id"] for x in west_recs}

    r = auth_client.post("/api/projects/europa-quarter/load")
    assert r.status_code == 200
    assert r.json()["status"] == "loaded"

    r2 = auth_client.get("/api/recommendations")
    assert r2.status_code == 200
    frank_recs = r2.json()
    frank_targets = {x["target_asset_id"] for x in frank_recs}

    assert frank_targets != west_targets or len(frank_targets) != len(west_targets), (
        f"recommendations didn't change after project switch: {frank_targets}"
    )


def test_bug16_asset_detail_zone_label_in_response(auth_client):
    auth_client.get("/api/site")
    r2 = auth_client.get("/api/simulation/state")
    state = r2.json()
    worker = next(a for a in state["assets"] if a["type"] == "worker")
    r3 = auth_client.get(f"/api/assets/{worker['id']}")
    assert r3.status_code == 200
    data = r3.json()
    assert "assigned_zone_label" in data
    assert data["assigned_zone_label"] is not None


def test_bug3_404_handled_cleanly(auth_client):
    """A 404 on /api/assets/{id} should return the canonical error envelope."""
    r = auth_client.get("/api/assets/does-not-exist")
    assert r.status_code == 404
    body = r.json()
    assert "error" in body
    assert body["error"]["message"] == "Asset not found"


def test_bug3_load_invalid_project_returns_404(auth_client):
    r = auth_client.post("/api/projects/no-such-project/load")
    assert r.status_code == 404


def test_apply_recommendation_uses_typed_position(auth_client):
    """Bug #28 regression: apply must read .x/.y, not ["x"]/["y"]."""
    for _ in range(10):
        recs = auth_client.get("/api/recommendations").json()
        if recs:
            break
        time.sleep(0.5)
    assert recs

    movable = next((r for r in recs if r["type"] == "move_facility"), None)
    if movable is None:
        movable = next((r for r in recs if r["type"] == "restage_material"), None)
    assert movable is not None, "no rec with a to_position to test apply"

    r = auth_client.post(f"/api/recommendations/{movable['id']}/apply")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] in {"applied", "already_applied"}


def test_apply_all_succeeds(auth_client):
    """End-to-end apply-all flow."""
    for _ in range(10):
        if auth_client.get("/api/recommendations").json():
            break
        time.sleep(0.5)
    r = auth_client.post("/api/recommendations/apply-all")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
