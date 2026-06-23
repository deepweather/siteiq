"""Preview-run endpoint tests.

`POST /api/projects/{id}/preview` runs a transient simulation against
an in-memory draft document and returns the resulting waste +
recommendations without ever touching the org's live engine. These
tests pin every constraint that lives in the spec for that feature.
"""
from __future__ import annotations

import re

from models.assets import DEFAULT_LEVEL_ID
from models.project_document import ProjectDocument, WorkerSeed
from models.site import Discipline, Level, Phase, Zone


def _doc(slug: str = "prev-1", *, level_pairs: list[tuple[str, str, float, int]] | None = None) -> dict:
    """Build a minimal valid document. `level_pairs` lets a multi-level
    test pass `[(id, name, elevation_m, order), ...]`."""
    if level_pairs is None:
        level_pairs = [(DEFAULT_LEVEL_ID, "EG", 0.0, 0)]
    levels = [Level(id=l[0], name=l[1], elevation_m=l[2], order=l[3]) for l in level_pairs]
    doc = ProjectDocument(
        slug=slug,
        name=f"Preview {slug}",
        description="preview test",
        discipline=Discipline.HOCHBAU,
        type="Residential",
        width=80.0,
        height=60.0,
        levels=levels,
        zones=[Zone(
            id="z1", label="Zone 1",
            x=10, y=10, width=40, height=30,
            phase=Phase.STRUCTURAL, phase_progress=0.5,
            level_id=levels[0].id,
        )],
        worker_seeds=[WorkerSeed(zone_id="z1", trade="general", count=2)],
    )
    return doc.model_dump(mode="json")


def _create_project(auth_client, slug: str = "preview-host") -> str:
    """Helper: create the host project the preview routes against. The
    preview endpoint only reads the URL's id for the auth/ownership
    check; the document under test is sent in the body."""
    r = auth_client.post("/api/projects", json={
        "document": _doc(slug),
        "message": "init",
    })
    assert r.status_code == 200, r.text
    return r.json()["id"]


# ── Happy path ───────────────────────────────────────────────────────


def test_preview_returns_shaped_response(auth_client):
    pid = _create_project(auth_client)
    body = {"document": _doc("preview-host"), "ticks": 60}
    r = auth_client.post(f"/api/projects/{pid}/preview", json=body)
    assert r.status_code == 200, r.text
    payload = r.json()
    assert set(payload.keys()) >= {
        "sim_time", "sim_day", "site", "assets", "waste", "recommendations",
    }
    assert payload["site"]["name"] == "Preview preview-host"
    # Every preview must have produced at least the seeded workers.
    assert any(a["type"] == "worker" for a in payload["assets"])
    # Waste fields are present and numeric.
    assert isinstance(payload["waste"]["total_daily"], (int, float))


def test_preview_default_ticks_runs_when_omitted(auth_client):
    pid = _create_project(auth_client)
    r = auth_client.post(f"/api/projects/{pid}/preview", json={
        "document": _doc("preview-host"),
    })
    assert r.status_code == 200
    # Default warmup advances the sim clock past t=0.
    assert r.json()["sim_time"] > 0


def test_preview_multi_level_document_surfaces_levels(auth_client):
    pid = _create_project(auth_client)
    doc = _doc("preview-host", level_pairs=[
        (DEFAULT_LEVEL_ID, "EG", 0.0, 0),
        ("L1", "1. OG", 3.5, 1),
    ])
    r = auth_client.post(f"/api/projects/{pid}/preview", json={
        "document": doc, "ticks": 30,
    })
    assert r.status_code == 200, r.text
    payload = r.json()
    level_ids = {lv["id"] for lv in payload["site"]["levels"]}
    assert level_ids == {DEFAULT_LEVEL_ID, "L1"}
    # Asset payloads must carry `lvl` so the frontend can filter.
    workers = [a for a in payload["assets"] if a["type"] == "worker"]
    assert workers, "expected at least one seeded worker"
    assert all("lvl" in a for a in workers)


# ── Isolation: live engine untouched ────────────────────────────────


def test_preview_does_not_swap_org_active_engine(auth_client):
    """Preview must not mutate the org's active project. Reading /api/site
    after a preview against a doc with a different name must still show
    the seed project the org is pinned to."""
    pid = _create_project(auth_client)
    before = auth_client.get("/api/site").json()
    body = {
        "document": _doc("preview-host"),
        "ticks": 30,
    }
    r = auth_client.post(f"/api/projects/{pid}/preview", json=body)
    assert r.status_code == 200
    after = auth_client.get("/api/site").json()
    assert after["name"] == before["name"]
    assert after["id"] == before["id"]


# ── Validation + bounds ─────────────────────────────────────────────


def test_preview_rejects_validation_errors(auth_client):
    pid = _create_project(auth_client)
    bad = _doc("preview-host")
    bad["materials"] = [{
        "id": "m1", "subtype": "rebar",
        "x": 5, "y": 5, "needed_in": "ghost-zone",
    }]
    r = auth_client.post(f"/api/projects/{pid}/preview", json={"document": bad})
    assert r.status_code == 400
    assert r.json()["error"]["code"] in {"unknown_zone"}


def test_preview_rejects_ticks_over_max(auth_client):
    pid = _create_project(auth_client)
    r = auth_client.post(f"/api/projects/{pid}/preview", json={
        "document": _doc("preview-host"),
        "ticks": 9999,
    })
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "ticks_out_of_range"


# ── Role gating ─────────────────────────────────────────────────────


def test_preview_unauthenticated_is_401(client):
    """Plain client (no session) hits the route and gets the standard
    not_authenticated envelope.

    We still grab a CSRF token first so the request makes it past the
    double-submit middleware — without it we'd 403 on CSRF before the
    session check runs, hiding the actual route gate."""
    csrf = client.get("/auth/csrf").json()["csrf_token"]
    r = client.post(
        "/api/projects/anything/preview",
        json={"document": _doc("preview-host")},
        headers={
            "Origin": "http://test.example.com",
            "X-CSRF-Token": csrf,
        },
    )
    assert r.status_code == 401, r.text
    assert r.json()["error"]["code"] == "not_authenticated"


def test_preview_viewer_role_is_403(client):
    """Sign up A (owner), invite B as viewer, B switches into A's org,
    B's preview attempt returns 403 insufficient_role."""
    csrf_a = client.get("/auth/csrf").json()["csrf_token"]
    headers_a = {"X-CSRF-Token": csrf_a, "Origin": "http://test.example.com"}
    client.post(
        "/auth/signup",
        json={"email": "owner@p.example", "name": "O", "company": "OC",
              "password": "longer-than-twelve-chars"},
        headers=headers_a,
    )
    # Create a project as owner.
    r = client.post("/api/projects", json={
        "document": _doc("rolegate"), "message": "init",
    }, headers=headers_a)
    assert r.status_code == 200
    pid = r.json()["id"]

    # Owner invites a viewer.
    client.post(
        "/api/orgs/current/invites",
        json={"email": "viewer@p.example", "role": "viewer"},
        headers=headers_a,
    )
    rows = client.get("/dev/outbox").json()
    invite = next(r for r in rows if r["to"] == "viewer@p.example")
    token = re.search(r"token=([\w\-_]+)", invite["text"]).group(1)

    # Swap to viewer B.
    client.post("/auth/logout", headers=headers_a)
    csrf_b = client.get("/auth/csrf").json()["csrf_token"]
    headers_b = {"X-CSRF-Token": csrf_b, "Origin": "http://test.example.com"}
    client.post(
        "/auth/signup",
        json={"email": "viewer@p.example", "name": "V", "company": "VC",
              "password": "longer-than-twelve-chars"},
        headers=headers_b,
    )
    client.post("/api/orgs/accept-invite", json={"token": token}, headers=headers_b)
    me = client.get("/auth/me").json()
    oc_id = next(o["id"] for o in me["memberships"] if o["name"] == "OC")
    client.post("/api/orgs/switch", json={"org_id": oc_id}, headers=headers_b)

    r = client.post(
        f"/api/projects/{pid}/preview",
        json={"document": _doc("rolegate")},
        headers=headers_b,
    )
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "insufficient_role"
