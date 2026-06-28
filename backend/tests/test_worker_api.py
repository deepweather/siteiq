"""Worker PWA API — crew entries, idempotency, reads, and the crew tier."""
from __future__ import annotations

import re

from fastapi.testclient import TestClient


OWNER = {
    "email": "boss@crew.example.com",
    "name": "Boss",
    "company": "CrewCo",
    "password": "long-enough-owner-password",
}
WORKER = {
    "email": "hands@crew.example.com",
    "name": "Hands",
    "company": "HandsCo",  # own org on signup; joins CrewCo as viewer
    "password": "long-enough-worker-password",
}


def _csrf(client: TestClient) -> dict:
    csrf = client.get("/auth/csrf").json()["csrf_token"]
    return {"X-CSRF-Token": csrf, "Origin": "http://test.example.com"}


def _signup(client: TestClient, body: dict) -> None:
    client.post("/auth/signup", json=body, headers=_csrf(client))


def _delivery(client, headers, *, cid="cid-aaaa1111", **payload_over):
    payload = {"subtype": "rebar", "quantity": 5, "unit": "t", "zone_id": "zone-a"}
    payload.update(payload_over)
    return client.post(
        "/api/worker/entry",
        json={"kind": "delivery", "client_event_id": cid, "payload": payload},
        headers=headers,
    )


# ── entry submission ─────────────────────────────────────────────────


def test_entry_lands_proposed_and_in_inbox(client):
    _signup(client, OWNER)
    h = _csrf(client)
    r = _delivery(client, h)
    assert r.status_code == 200, r.text
    ev = r.json()
    assert ev["status"] == "proposed"
    assert ev["source"] == "human"
    assert ev["kind"] == "material.delivered"
    assert ev["payload"]["quantity"] == 5

    inbox = client.get("/api/record/inbox")
    assert any(e["id"] == ev["id"] for e in inbox.json()["events"])

    # Supervisor confirms via the existing record route.
    c = client.post(f"/api/record/events/{ev['id']}/confirm", json={}, headers=h)
    assert c.status_code == 200
    assert c.json()["status"] == "confirmed"


def test_entry_rejects_unknown_kind(client):
    _signup(client, OWNER)
    h = _csrf(client)
    r = client.post(
        "/api/worker/entry",
        json={"kind": "sabotage", "client_event_id": "cid-bbbb2222", "payload": {}},
        headers=h,
    )
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "unsupported_entry_kind"


def test_entry_is_idempotent_on_client_event_id(client):
    _signup(client, OWNER)
    h = _csrf(client)
    first = _delivery(client, h, cid="cid-dupe-0001")
    assert first.status_code == 200
    second = _delivery(client, h, cid="cid-dupe-0001", quantity=999)
    assert second.status_code == 200
    # Same row returned; the replay's payload is ignored.
    assert second.json()["id"] == first.json()["id"]
    assert second.json()["payload"]["quantity"] == 5

    # Exactly one matching event exists, and the chain still verifies.
    evs = client.get(
        "/api/record/events?kind=material.delivered&source_filter=human&limit=50"
    ).json()["events"]
    assert sum(1 for e in evs if e["id"] == first.json()["id"]) == 1
    assert client.get("/api/record/verify").json()["ok"] is True


# ── reads ────────────────────────────────────────────────────────────


def test_overview_reports_site_and_pending(client):
    _signup(client, OWNER)
    h = _csrf(client)
    _delivery(client, h, cid="cid-ov-0001")

    ov = client.get("/api/worker/overview").json()
    assert ov["project_id"] == "westhafen"
    assert ov["site_name"]
    # My freshly-submitted (proposed) entry is counted as pending.
    assert ov["my_pending"] >= 1


def test_assets_populated_from_site_without_ledger(client):
    # The Assets tab must show the project's real equipment/materials/zones
    # immediately, even before any ledger history exists (the "no data found"
    # bug). Sourced from the SiteStateSource, like /api/worker/zones.
    _signup(client, OWNER)
    body = client.get("/api/worker/assets").json()
    assert body["assets"], body
    types = {a["subject_type"] for a in body["assets"]}
    assert {"equipment", "zone"} & types


def test_assets_overlay_ledger_metrics_on_material(client):
    _signup(client, OWNER)
    h = _csrf(client)
    _delivery(client, h, cid="cid-as-0001", quantity=12)
    # Confirm it so the projection counts it.
    ev_id = client.get("/api/record/inbox").json()["events"][0]["id"]
    client.post(f"/api/record/events/{ev_id}/confirm", json={}, headers=h)

    mats = client.get("/api/worker/assets?type=material").json()["assets"]
    assert mats
    assert all(m["subject_type"] == "material" for m in mats)
    # At least the delivered material now reports an on-hand quantity.
    assert any("on_hand_qty" in m["metrics"] for m in mats)


def test_asset_detail_falls_back_to_site(client):
    # Opening a real site asset with no ledger history returns its definition
    # instead of 404.
    _signup(client, OWNER)
    equip = next(
        a for a in client.get("/api/worker/assets?type=equipment").json()["assets"]
    )
    detail = client.get(f"/api/worker/assets/equipment/{equip['subject_id']}")
    assert detail.status_code == 200
    assert detail.json()["subject_type"] == "equipment"


def test_zones_come_from_site_definition(client):
    # Zones must be available even with an empty ledger (sourced from the
    # active project, not from events) so the entry wizard never dead-ends.
    _signup(client, OWNER)
    body = client.get("/api/worker/zones").json()
    assert body["project_id"] == "westhafen"
    assert len(body["zones"]) > 0
    assert all("id" in z and "label" in z for z in body["zones"])


def test_my_entries_returns_own_submissions(client):
    _signup(client, OWNER)
    h = _csrf(client)
    _delivery(client, h, cid="cid-me-0001")
    mine = client.get("/api/worker/my-entries").json()["entries"]
    assert len(mine) >= 1
    assert mine[0]["kind"] == "material.delivered"


# ── crew (viewer) tier ───────────────────────────────────────────────


def _invite_worker_as_viewer(client) -> str:
    """Owner invites WORKER as viewer; WORKER signs up + accepts + switches
    into CrewCo. Returns nothing; client ends logged in as the viewer in
    CrewCo's active stream."""
    _signup(client, OWNER)
    h = _csrf(client)
    # Seed worker subjects into the stream while we're the owner.
    client.post("/api/record/demo/generate", json={"days": 4, "seed": 3}, headers=h)
    client.post(
        "/api/orgs/current/invites",
        json={"email": WORKER["email"], "role": "viewer"},
        headers=h,
    )
    row = next(
        r for r in client.get("/dev/outbox").json()
        if r["to"] == WORKER["email"] and "invited" in r["subject"].lower()
    )
    token = re.search(r"/accept-invite\?token=([\w\-_]+)", row["text"]).group(1)
    client.post("/auth/logout", headers=h)

    _signup(client, WORKER)
    h2 = _csrf(client)
    client.post("/api/orgs/accept-invite", json={"token": token}, headers=h2)
    me = client.get("/auth/me").json()
    crewco_id = next(o["id"] for o in me["memberships"] if o["name"] == "CrewCo")
    client.post("/api/orgs/switch", json={"org_id": crewco_id}, headers=h2)
    return crewco_id


def test_viewer_can_submit_entry(client):
    _invite_worker_as_viewer(client)
    h = _csrf(client)
    r = _delivery(client, h, cid="cid-viewer-0001")
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "proposed"


def test_viewer_blocked_from_worker_entity(client):
    _invite_worker_as_viewer(client)
    # Find a real worker subject id from the seeded stream.
    subjects = client.get("/api/worker/assets").json()["assets"]
    assert all(a["subject_type"] != "worker" for a in subjects)

    # The directory (manager-only worker view) isn't reachable as crew, so
    # just probe a plausible worker subject id — the route 403s on the tier
    # before it even looks for the row.
    r = client.get("/api/worker/assets/worker/worker-0")
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "forbidden"
