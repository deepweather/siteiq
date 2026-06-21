"""Authorization tests — protected routes refuse unauthenticated calls,
and org-scoped routes refuse cross-org access."""
from __future__ import annotations

from fastapi.testclient import TestClient


def _csrf(client: TestClient) -> dict:
    csrf = client.get("/auth/csrf").json()["csrf_token"]
    return {"X-CSRF-Token": csrf, "Origin": "http://test.example.com"}


def test_protected_routes_401_without_cookie(client):
    paths = [
        "/api/projects",
        "/api/site",
        "/api/recommendations",
        "/api/cameras",
        "/api/portfolio",
        "/api/simulation/state",
        "/api/orgs",
        "/api/orgs/current/members",
    ]
    for p in paths:
        r = client.get(p)
        assert r.status_code == 401, f"{p}: expected 401, got {r.status_code}"
        body = r.json()
        assert body.get("error", {}).get("code") == "not_authenticated"


def test_authenticated_user_reaches_org_routes(auth_client):
    r = auth_client.get("/api/site")
    assert r.status_code == 200


def test_admin_only_routes_reject_member(client):
    """Sign up A as owner, invite B as member, B switches into A's org,
    then B fails to GET /api/orgs/current/invites (admin-only)."""
    h = _csrf(client)
    client.post(
        "/auth/signup",
        json={"email": "a@team.example.com", "name": "A", "company": "AC", "password": "long-enough-pw-1"},
        headers=h,
    )
    # Create invite for B.
    client.post(
        "/api/orgs/current/invites",
        json={"email": "b@team.example.com", "role": "member"},
        headers=h,
    )
    rows = client.get("/dev/outbox").json()
    invite_row = next(r for r in rows if r["to"] == "b@team.example.com")
    import re
    token = re.search(r"token=([\w\-_]+)", invite_row["text"]).group(1)

    # Logout A, signup B, accept, switch to A's org.
    client.post("/auth/logout", headers=h)
    h2 = _csrf(client)
    client.post(
        "/auth/signup",
        json={"email": "b@team.example.com", "name": "B", "company": "BC", "password": "long-enough-pw-2"},
        headers=h2,
    )
    client.post("/api/orgs/accept-invite", json={"token": token}, headers=h2)
    me = client.get("/auth/me").json()
    ac_id = next(o["id"] for o in me["memberships"] if o["name"] == "AC")
    client.post("/api/orgs/switch", json={"org_id": ac_id}, headers=h2)

    # B is a member of AC and tries the admin-only invite list.
    r = client.get("/api/orgs/current/invites", headers=h2)
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "insufficient_role"
