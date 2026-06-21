"""Tests for org membership: invites, role changes, removal, switch."""
from __future__ import annotations

import re

from fastapi.testclient import TestClient


OWNER = {
    "email": "owner@team.example.com",
    "name": "Owner",
    "company": "TeamCo",
    "password": "long-enough-owner-password",
}
GUEST = {
    "email": "guest@team.example.com",
    "name": "Guest",
    "company": "GuestCo",  # Will create their own org on signup.
    "password": "long-enough-guest-password",
}


def _csrf(client: TestClient) -> dict:
    csrf = client.get("/auth/csrf").json()["csrf_token"]
    return {"X-CSRF-Token": csrf, "Origin": "http://test.example.com"}


def _signup(client: TestClient, body: dict) -> None:
    client.post("/auth/signup", json=body, headers=_csrf(client))


def _login(client: TestClient, email: str, password: str) -> None:
    h = _csrf(client)
    r = client.post("/auth/login", json={"email": email, "password": password}, headers=h)
    assert r.status_code == 200, r.text


def test_signup_creates_org_with_owner_role(client):
    _signup(client, OWNER)
    me = client.get("/auth/me").json()
    assert me["org"]["role"] == "owner"
    assert me["org"]["name"] == "TeamCo"


def test_member_cannot_invite(client):
    _signup(client, OWNER)
    h = _csrf(client)
    # Invite Guest as a member of TeamCo.
    invite_resp = client.post(
        "/api/orgs/current/invites",
        json={"email": GUEST["email"], "role": "member"},
        headers=h,
    )
    assert invite_resp.status_code == 200, invite_resp.text

    # Get the token from the outbox.
    rows = client.get("/dev/outbox").json()
    invite_row = next(r for r in rows if r["to"] == GUEST["email"] and "invite" in r["subject"].lower() or "join" in r["subject"].lower())
    m = re.search(r"/accept-invite\?token=([\w\-_]+)", invite_row["text"])
    assert m
    token = m.group(1)

    # Logout owner, sign Guest up (creates GuestCo), accept invite.
    client.post("/auth/logout", headers=h)
    _signup(client, GUEST)
    h2 = _csrf(client)
    r = client.post("/api/orgs/accept-invite", json={"token": token}, headers=h2)
    assert r.status_code == 200, r.text

    # Guest now has 2 orgs. Switch to TeamCo.
    me = client.get("/auth/me").json()
    teamco_id = next(o["id"] for o in me["memberships"] if o["name"] == "TeamCo")
    r = client.post("/api/orgs/switch", json={"org_id": teamco_id}, headers=h2)
    assert r.status_code == 200

    # As member, Guest cannot invite anyone.
    r = client.post(
        "/api/orgs/current/invites",
        json={"email": "third@team.example.com", "role": "member"},
        headers=h2,
    )
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "insufficient_role"


def test_invite_email_mismatch_rejected(client):
    _signup(client, OWNER)
    h = _csrf(client)
    client.post(
        "/api/orgs/current/invites",
        json={"email": "intended@team.example.com", "role": "member"},
        headers=h,
    )
    rows = client.get("/dev/outbox").json()
    invite_row = next(r for r in rows if r["to"] == "intended@team.example.com")
    m = re.search(r"/accept-invite\?token=([\w\-_]+)", invite_row["text"])
    token = m.group(1)

    # Different user tries to redeem the link — refused.
    client.post("/auth/logout", headers=h)
    _signup(client, GUEST)
    h2 = _csrf(client)
    r = client.post("/api/orgs/accept-invite", json={"token": token}, headers=h2)
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "invite_email_mismatch"


def test_owner_can_change_member_role(client):
    _signup(client, OWNER)
    h = _csrf(client)
    client.post(
        "/api/orgs/current/invites",
        json={"email": GUEST["email"], "role": "member"},
        headers=h,
    )
    rows = client.get("/dev/outbox").json()
    invite_row = next(r for r in rows if r["to"] == GUEST["email"])
    token = re.search(r"token=([\w\-_]+)", invite_row["text"]).group(1)

    client.post("/auth/logout", headers=h)
    _signup(client, GUEST)
    h2 = _csrf(client)
    client.post("/api/orgs/accept-invite", json={"token": token}, headers=h2)
    guest_user_id = client.get("/auth/me").json()["user"]["id"]

    # Owner promotes Guest to admin.
    client.post("/auth/logout", headers=h2)
    _login(client, OWNER["email"], OWNER["password"])
    h3 = _csrf(client)
    r = client.patch(
        f"/api/orgs/current/members/{guest_user_id}",
        json={"role": "admin"},
        headers=h3,
    )
    assert r.status_code == 200

    members = client.get("/api/orgs/current/members", headers=h3).json()
    guest_row = next(m for m in members if m["email"] == GUEST["email"])
    assert guest_row["role"] == "admin"


def test_cannot_change_own_role(client):
    _signup(client, OWNER)
    h = _csrf(client)
    me = client.get("/auth/me").json()
    r = client.patch(
        f"/api/orgs/current/members/{me['user']['id']}",
        json={"role": "member"},
        headers=h,
    )
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "cannot_change_own_role"


def test_unauth_request_returns_401(client):
    """A protected route without a session cookie returns 401 with the envelope."""
    r = client.get("/api/site")
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "not_authenticated"


def test_audit_events_visible_to_owner(client):
    _signup(client, OWNER)
    h = _csrf(client)
    events = client.get("/api/orgs/current/audit", headers=h).json()
    kinds = {e["kind"] for e in events}
    assert "user.signup" in kinds
    assert "org.created" in kinds
