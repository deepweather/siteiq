"""Device ingestion: claim flow, bearer auth, staging idempotency, the
single chain-writer fold (confidence routing + gap-free seq + verify), and
fleet admin endpoints."""
from __future__ import annotations

import uuid

import pytest

from db.models import DeviceInbound
from services.event_ledger import EventLedger
from services.ingest_writer import drain_device_inbound


# ── HTTP: claim + ingest + fleet (via auth_client = owner/admin) ─────


def _claim_device(auth_client, *, name="Cam 1", kind="camera"):
    r = auth_client.post("/api/devices/claims", json={"name": name, "kind": kind})
    assert r.status_code == 200, r.text
    code = r.json()["code"]
    c = auth_client.post("/api/ingest/claim", json={"code": code})
    assert c.status_code == 200, c.text
    return c.json()  # {device_id, token, org_id, project_id, ...}


def _events(token, items):
    return {"events": items}


def test_claim_flow_issues_device_token(auth_client):
    dev = _claim_device(auth_client)
    assert dev["token"] and dev["device_id"]
    assert dev["project_id"] == "westhafen"


def test_claim_code_is_single_use(auth_client):
    r = auth_client.post("/api/devices/claims", json={"name": "X", "kind": "camera"})
    code = r.json()["code"]
    assert auth_client.post("/api/ingest/claim", json={"code": code}).status_code == 200
    again = auth_client.post("/api/ingest/claim", json={"code": code})
    assert again.status_code == 400
    assert again.json()["error"]["code"] == "claim_used"


def test_ingest_requires_device_token(auth_client):
    # No Authorization header -> 401 (cookie/CSRF are irrelevant here).
    r = auth_client.post(
        "/api/ingest/events",
        json={"events": []},
        headers={"Authorization": ""},
    )
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "device_not_authenticated"


def _ev(cid, *, kind="material.delivered", confidence=0.9):
    return {
        "subject_type": "material",
        "subject_id": "capture-rebar",
        "kind": kind,
        "client_event_id": cid,
        "payload": {"subtype": "rebar", "quantity": 3, "unit": "t"},
        "confidence": confidence,
        "source": "camera",
    }


def test_ingest_stages_events_idempotently(auth_client):
    dev = _claim_device(auth_client)
    h = {"Authorization": f"Bearer {dev['token']}"}
    first = auth_client.post(
        "/api/ingest/events",
        json={"events": [_ev("cid-dev-0001"), _ev("cid-dev-0002")], "agent_version": "0.1.0"},
        headers=h,
    )
    assert first.status_code == 202, first.text
    assert first.json() == {"accepted": 2, "duplicates": 0, "received": 2}

    # Replaying the same client_event_id is a no-op.
    dup = auth_client.post(
        "/api/ingest/events", json={"events": [_ev("cid-dev-0001")]}, headers=h
    )
    assert dup.json()["duplicates"] == 1
    assert dup.json()["accepted"] == 0


def test_revoked_device_token_is_rejected(auth_client):
    dev = _claim_device(auth_client)
    h = {"Authorization": f"Bearer {dev['token']}"}
    # Revoke via the admin fleet endpoint.
    rv = auth_client.delete(f"/api/devices/{dev['device_id']}")
    assert rv.status_code == 200
    r = auth_client.post("/api/ingest/events", json={"events": [_ev("cid-rev-0001")]}, headers=h)
    assert r.status_code == 401


def test_rotate_issues_working_token_and_breaks_old(auth_client):
    dev = _claim_device(auth_client)
    old = {"Authorization": f"Bearer {dev['token']}"}
    rot = auth_client.post(f"/api/devices/{dev['device_id']}/rotate")
    assert rot.status_code == 200
    new = {"Authorization": f"Bearer {rot.json()['token']}"}
    assert auth_client.post("/api/ingest/events", json={"events": [_ev("cid-new-0001")]}, headers=new).status_code == 202
    assert auth_client.post("/api/ingest/events", json={"events": [_ev("cid-old-0001")]}, headers=old).status_code == 401


def test_fleet_list_reports_device_and_health(auth_client):
    dev = _claim_device(auth_client, name="Tower Cam")
    listing = auth_client.get("/api/devices").json()
    row = next(d for d in listing if d["id"] == dev["device_id"])
    assert row["name"] == "Tower Cam"
    assert row["health"] in ("online", "offline", "never_seen")
    assert row["kind"] == "camera"


def test_claim_requires_authentication(client):
    # Unauthenticated (no session) cannot mint claim codes. Pass CSRF + Origin
    # so the request clears the CSRF middleware and is rejected by auth (401),
    # not CSRF (403).
    csrf = client.get("/auth/csrf").json()["csrf_token"]
    r = client.post(
        "/api/devices/claims",
        json={"name": "x", "kind": "camera"},
        headers={"X-CSRF-Token": csrf, "Origin": "http://test.example.com"},
    )
    assert r.status_code == 401


# ── Writer unit test (in the test's own loop, via ledger_session) ────


@pytest.mark.asyncio
async def test_chain_writer_folds_inbound_with_confidence_routing(ledger_session):
    org_id, project_id, device_id = "org-1", "proj-1", "dev-1"

    def _inbound(cid, conf):
        return DeviceInbound(
            id=str(uuid.uuid4()),
            org_id=org_id,
            project_id=project_id,
            device_id=device_id,
            client_event_id=cid,
            envelope={
                "subject_type": "equipment",
                "subject_id": "crane-1",
                "kind": "equipment.state_changed",
                "occurred_at": "2026-02-01T08:00:00+00:00",
                "payload": {"state": "operating"},
                "confidence": conf,
                "source": "camera",
            },
        )

    ledger_session.add(_inbound("c-hi", 0.95))   # >= floor -> confirmed
    ledger_session.add(_inbound("c-lo", 0.40))   # < floor  -> proposed
    await ledger_session.flush()

    written = await drain_device_inbound(
        ledger_session, org_id=org_id, project_id=project_id, confidence_floor=0.75
    )
    assert written == 2

    ledger = EventLedger(ledger_session)
    rows = await ledger.all_for_stream(org_id, project_id)
    by_cid = {r.client_event_id: r for r in rows}
    assert by_cid["c-hi"].status == "confirmed"
    assert by_cid["c-lo"].status == "proposed"
    assert by_cid["c-hi"].device_id == device_id
    # Gap-free seq + intact tamper-evident chain.
    assert [r.seq for r in rows] == [1, 2]
    chk = await ledger.verify_chain(org_id, project_id)
    assert chk["ok"] is True

    # Re-draining is a no-op (rows marked processed).
    assert await drain_device_inbound(
        ledger_session, org_id=org_id, project_id=project_id, confidence_floor=0.75
    ) == 0
