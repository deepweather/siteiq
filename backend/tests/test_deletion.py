"""Account + workspace deletion."""
from __future__ import annotations

import re

from fastapi.testclient import TestClient


PW = "correct-horse-battery-staple-x"
OWNER = {"email": "alpha@example.com", "name": "Alpha", "company": "AlphaCo", "password": PW}
TEAMMATE = {"email": "beta@example.com", "name": "Beta", "company": "BetaCo", "password": PW}


def _csrf(client: TestClient) -> dict:
    csrf = client.get("/auth/csrf").json()["csrf_token"]
    return {"X-CSRF-Token": csrf, "Origin": "http://test.example.com"}


def _signup(client: TestClient, body: dict) -> None:
    client.post("/auth/signup", json=body, headers=_csrf(client))


def test_account_delete_requires_password(client):
    _signup(client, OWNER)
    h = _csrf(client)
    r = client.post("/auth/delete-account", json={"current_password": "wrong-x"}, headers=h)
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "invalid_password"
    # Account still exists.
    assert client.get("/auth/me").json()["user"] is not None


def test_account_delete_succeeds_and_wipes_sole_owner_org(client):
    _signup(client, OWNER)
    h = _csrf(client)
    r = client.post("/auth/delete-account", json={"current_password": PW}, headers=h)
    assert r.status_code == 200
    assert len(r.json()["orgs_deleted"]) == 1
    # Cookie cleared → /auth/me returns null.
    assert client.get("/auth/me").json()["user"] is None
    # Login should fail (account gone).
    r = client.post(
        "/auth/login",
        json={"email": OWNER["email"], "password": PW},
        headers=_csrf(client),
    )
    assert r.status_code == 401


def test_account_delete_keeps_org_with_other_owner(client):
    """Owner A invites B as admin, promotes B to owner, A deletes account
    → AlphaCo survives (B is still an owner)."""
    _signup(client, OWNER)
    h = _csrf(client)
    # Invite B as member, accept, promote to owner.
    client.post("/api/orgs/current/invites", json={"email": TEAMMATE["email"], "role": "member"}, headers=h)
    rows = client.get("/dev/outbox").json()
    invite = next(r for r in rows if r["to"] == TEAMMATE["email"])
    token = re.search(r"token=([\w\-_]+)", invite["text"]).group(1)
    client.post("/auth/logout", headers=h)

    _signup(client, TEAMMATE)
    h2 = _csrf(client)
    client.post("/api/orgs/accept-invite", json={"token": token}, headers=h2)
    me = client.get("/auth/me").json()
    teammate_user_id = me["user"]["id"]
    alpha_org_id = next(o["id"] for o in me["memberships"] if o["name"] == "AlphaCo")
    client.post("/auth/logout", headers=h2)

    # Owner A logs in, promotes B to owner, deletes account.
    h3 = _csrf(client)
    client.post("/auth/login", json={"email": OWNER["email"], "password": PW}, headers=h3)
    r = client.patch(
        f"/api/orgs/current/members/{teammate_user_id}",
        json={"role": "owner"},
        headers=h3,
    )
    assert r.status_code == 200
    r = client.post("/auth/delete-account", json={"current_password": PW}, headers=h3)
    assert r.status_code == 200
    assert r.json()["orgs_deleted"] == []  # AlphaCo survives because B is owner

    # B can still see AlphaCo.
    h4 = _csrf(client)
    client.post("/auth/login", json={"email": TEAMMATE["email"], "password": PW}, headers=h4)
    me = client.get("/auth/me").json()
    assert any(o["id"] == alpha_org_id for o in me["memberships"])


def test_workspace_delete_requires_owner(client):
    """Member can't delete the workspace."""
    _signup(client, OWNER)
    h = _csrf(client)
    client.post("/api/orgs/current/invites", json={"email": TEAMMATE["email"], "role": "member"}, headers=h)
    rows = client.get("/dev/outbox").json()
    invite = next(r for r in rows if r["to"] == TEAMMATE["email"])
    token = re.search(r"token=([\w\-_]+)", invite["text"]).group(1)
    client.post("/auth/logout", headers=h)

    _signup(client, TEAMMATE)
    h2 = _csrf(client)
    client.post("/api/orgs/accept-invite", json={"token": token}, headers=h2)
    me = client.get("/auth/me").json()
    alpha_id = next(o["id"] for o in me["memberships"] if o["name"] == "AlphaCo")
    client.post("/api/orgs/switch", json={"org_id": alpha_id}, headers=h2)

    r = client.request(
        "DELETE",
        "/api/orgs/current",
        json={"confirm_name": "AlphaCo", "current_password": PW},
        headers=h2,
    )
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "insufficient_role"


def test_workspace_delete_requires_exact_name_and_password(client):
    _signup(client, OWNER)
    h = _csrf(client)
    # Wrong name.
    r = client.request(
        "DELETE", "/api/orgs/current",
        json={"confirm_name": "WrongName", "current_password": PW},
        headers=h,
    )
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "name_mismatch"

    # Wrong password.
    r = client.request(
        "DELETE", "/api/orgs/current",
        json={"confirm_name": "AlphaCo", "current_password": "nope"},
        headers=h,
    )
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "invalid_password"


def test_workspace_delete_succeeds(client):
    _signup(client, OWNER)
    h = _csrf(client)
    r = client.request(
        "DELETE", "/api/orgs/current",
        json={"confirm_name": "AlphaCo", "current_password": PW},
        headers=h,
    )
    assert r.status_code == 200
    # Now /auth/me has no active org.
    me = client.get("/auth/me").json()
    assert me["org"] is None
    assert me["memberships"] == []
