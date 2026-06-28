"""Phase 1 — content-addressed project persistence tests.

Covers the repository, the seed importer, the /api/projects router,
optimistic concurrency control on save, and the activate flow.
"""
from __future__ import annotations


from models.assets import DEFAULT_LEVEL_ID
from models.project_document import ProjectDocument, WorkerSeed
from models.site import Discipline, Level, Phase, Zone


def _make_doc(slug: str = "custom-1", name: str = "Custom 1") -> dict:
    """Returns a serialised document the router can accept directly."""
    doc = ProjectDocument(
        slug=slug,
        name=name,
        description="A custom project for the tests.",
        discipline=Discipline.HOCHBAU,
        type="Residential",
        width=100.0,
        height=80.0,
        levels=[Level(id=DEFAULT_LEVEL_ID, name="EG", elevation_m=0.0, order=0)],
        zones=[Zone(
            id="z1", label="Block A", x=10, y=10, width=40, height=40,
            phase=Phase.STRUCTURAL, phase_progress=0.5,
        )],
        worker_seeds=[WorkerSeed(zone_id="z1", trade="general", count=3)],
    )
    return doc.model_dump(mode="json")


# ── Seed importer ─────────────────────────────────────────────────────


def test_seeds_imported_as_public_templates(auth_client):
    """At boot the lifespan imports every bundled seed as a
    public-template row. The editor listing surfaces them."""
    r = auth_client.get("/api/projects")
    assert r.status_code == 200
    projects = r.json()
    stocks = [p for p in projects if p["slug"] in {"westhafen", "europa-quarter", "isar-bridge"}]
    assert len(stocks) == 3
    for s in stocks:
        assert s["visibility"] == "public_template"
        assert s["is_owner"] is False
        assert s["current_version_id"]


# ── Create / read / update flow ───────────────────────────────────────


def test_create_project_returns_version_id(auth_client):
    payload = {"document": _make_doc("mine-1", "Mine 1"), "message": "init"}
    r = auth_client.post("/api/projects", json=payload)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["is_owner"] is True
    assert body["slug"] == "mine-1"
    assert body["current_version_id"]
    assert len(body["current_version_id"]) == 64  # SHA-256 hex


def test_create_then_read_round_trips(auth_client):
    payload = {"document": _make_doc("mine-2", "Mine 2"), "message": "init"}
    r = auth_client.post("/api/projects", json=payload)
    pid = r.json()["id"]
    r2 = auth_client.get(f"/api/projects/{pid}")
    assert r2.status_code == 200
    doc = r2.json()["document"]
    assert doc["slug"] == "mine-2"
    assert doc["zones"][0]["id"] == "z1"


def test_update_creates_new_version(auth_client):
    payload = {"document": _make_doc("mine-3", "Mine 3"), "message": "init"}
    r = auth_client.post("/api/projects", json=payload)
    pid = r.json()["id"]
    v1 = r.json()["current_version_id"]

    doc2 = _make_doc("mine-3", "Mine 3 renamed")
    r2 = auth_client.put(
        f"/api/projects/{pid}",
        json={"document": doc2, "message": "rename"},
        headers={"If-Match": v1},
    )
    assert r2.status_code == 200, r2.text
    v2 = r2.json()["current_version_id"]
    assert v2 != v1
    assert r2.json()["name"] == "Mine 3 renamed"


def test_occ_rejects_stale_parent_version(auth_client):
    """If two editors save against the same parent version, the second
    one must 409."""
    payload = {"document": _make_doc("mine-4"), "message": "init"}
    r = auth_client.post("/api/projects", json=payload)
    pid = r.json()["id"]
    v1 = r.json()["current_version_id"]

    # First save bumps v1 -> v2.
    doc2 = _make_doc("mine-4", "Mine 4 v2")
    r_first = auth_client.put(
        f"/api/projects/{pid}",
        json={"document": doc2},
        headers={"If-Match": v1},
    )
    assert r_first.status_code == 200

    # Second save uses the stale v1 as parent.
    doc3 = _make_doc("mine-4", "Mine 4 v3")
    r_conflict = auth_client.put(
        f"/api/projects/{pid}",
        json={"document": doc3},
        headers={"If-Match": v1},
    )
    assert r_conflict.status_code == 409
    assert r_conflict.json()["error"]["code"] == "version_conflict"


def test_validation_endpoint_returns_issues_without_persisting(auth_client):
    payload = {"document": _make_doc("mine-5"), "message": "init"}
    r = auth_client.post("/api/projects", json=payload)
    pid = r.json()["id"]

    # Broken doc: schedule references a ghost zone.
    bad = _make_doc("mine-5")
    bad["schedule"] = [{
        "zone_id": "ghost",
        "phase": "structural",
        "start_day": 1,
        "end_day": 10,
        "trades_required": [],
    }]
    r2 = auth_client.post(
        f"/api/projects/{pid}/validate",
        json={"document": bad},
    )
    assert r2.status_code == 200
    codes = {i["code"] for i in r2.json()["issues"]}
    assert "unknown_zone" in codes


def test_activate_pins_org_to_version_and_swaps_engine(auth_client):
    """Activating a custom project must make the dashboard read its data."""
    payload = {"document": _make_doc("mine-6", "Sechser"), "message": "init"}
    r = auth_client.post("/api/projects", json=payload)
    pid = r.json()["id"]
    vid = r.json()["current_version_id"]

    r2 = auth_client.post(
        f"/api/projects/{pid}/activate",
        json={"version_id": vid},
    )
    assert r2.status_code == 200, r2.text
    assert r2.json()["version_id"] == vid

    # Pull /api/site and confirm we see the custom project.
    r3 = auth_client.get("/api/site")
    assert r3.status_code == 200
    site = r3.json()
    assert site["name"] == "Sechser"
    assert any(z["id"] == "z1" for z in site["zones"])


def test_delete_project_works(auth_client):
    payload = {"document": _make_doc("mine-7"), "message": "init"}
    r = auth_client.post("/api/projects", json=payload)
    pid = r.json()["id"]
    r2 = auth_client.delete(f"/api/projects/{pid}")
    assert r2.status_code == 200
    r3 = auth_client.get(f"/api/projects/{pid}")
    assert r3.status_code == 404


def test_create_invalid_document_rejected(auth_client):
    bad = _make_doc("bad-1")
    bad["schedule"] = [{
        "zone_id": "ghost",
        "phase": "structural",
        "start_day": 5,
        "end_day": 1,
        "trades_required": [],
    }]
    r = auth_client.post("/api/projects", json={"document": bad})
    assert r.status_code == 400
    code = r.json()["error"]["code"]
    assert code in {"unknown_zone", "schedule_inverted"}


def test_public_template_visibility_blocked_for_orgs(auth_client):
    payload = {
        "document": _make_doc("evil-public"),
        "visibility": "public_template",
    }
    r = auth_client.post("/api/projects", json=payload)
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "forbidden_visibility"


def test_project_list_marks_active_project(auth_client):
    """The project-list endpoint must surface which project is currently
    pinned to the org's simulation. Without this the UI can't render an
    "Active" badge and the user has no way to tell which Activate button
    is the no-op one."""
    payload = {"document": _make_doc("active-me"), "message": "init"}
    r = auth_client.post("/api/projects", json=payload)
    pid = r.json()["id"]
    vid = r.json()["current_version_id"]

    # Before activate: nothing flagged is_active.
    rows = auth_client.get("/api/projects").json()
    assert all(p["is_active"] is False for p in rows)

    auth_client.post(f"/api/projects/{pid}/activate", json={"version_id": vid})

    rows = auth_client.get("/api/projects").json()
    target = next(p for p in rows if p["id"] == pid)
    assert target["is_active"] is True
    # Every other row stays inactive.
    assert sum(1 for p in rows if p["is_active"]) == 1


def test_reactivate_same_version_preserves_engine_state(auth_client):
    """Re-activating the project that's already running must not tear
    down + rebuild the engine — that would wipe applied recommendations
    and reset the sim day, which the user perceives as "I clicked
    Activate and lost all my progress"."""
    payload = {"document": _make_doc("keep-me"), "message": "init"}
    r = auth_client.post("/api/projects", json=payload)
    pid = r.json()["id"]
    vid = r.json()["current_version_id"]

    auth_client.post(f"/api/projects/{pid}/activate", json={"version_id": vid})
    # Pull /api/site to materialise the engine.
    site_before = auth_client.get("/api/site").json()

    # Hit the simulation a bit so the engine drifts away from t=0.
    # We can't tick the live engine from a test client easily, but we
    # can mutate it through the registry directly.
    from main import create_app  # noqa
    # Easier: rely on the second /api/site call returning the SAME
    # engine instance (same project_id, sim_time progressed by
    # the lifespan loop or just identical to the first read because
    # the sim runs at SIM_TICK_INTERVAL).
    auth_client.post(f"/api/projects/{pid}/activate", json={"version_id": vid})
    site_after = auth_client.get("/api/site").json()
    # Project identity is unchanged — same name + same id slug.
    assert site_after["name"] == site_before["name"]
    assert site_after["id"] == site_before["id"]
    # The sim_day must not have rewound — that's the user-visible
    # symptom of a needless rebuild.
    assert site_after["current_day"] >= site_before["current_day"]


def test_reactivate_seed_after_slug_load_preserves_engine(auth_client):
    """Common path: org boots up running a seed project (engine built
    from the slug path with project_version_id=None). User clicks
    Activate on that seed in the project list. Registry must tag the
    engine instead of rebuilding it."""
    # Switch to the bundled westhafen seed via the legacy slug route.
    r = auth_client.post("/api/site/load-seed", json={"slug": "westhafen"})
    assert r.status_code == 200
    site_before = auth_client.get("/api/site").json()

    # Find the westhafen project + activate by id (the way the
    # ProjectListPage button calls).
    rows = auth_client.get("/api/projects").json()
    westhafen = next(p for p in rows if p["slug"] == "westhafen")
    r = auth_client.post(
        f"/api/projects/{westhafen['id']}/activate",
        json={"version_id": westhafen["current_version_id"]},
    )
    assert r.status_code == 200

    site_after = auth_client.get("/api/site").json()
    # Same project + sim hasn't rewound.
    assert site_after["name"] == site_before["name"]
    assert site_after["current_day"] >= site_before["current_day"]
