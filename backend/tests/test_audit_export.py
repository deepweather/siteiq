"""Audit log CSV export."""
from __future__ import annotations


def _csrf(client):
    csrf = client.get("/auth/csrf").json()["csrf_token"]
    return {"X-CSRF-Token": csrf, "Origin": "http://test.example.com"}


def _signup_owner(client):
    client.post(
        "/auth/signup",
        json={
            "email": "audit@example.com",
            "name": "Auditor",
            "company": "AuditCo",
            "password": "long-enough-password-x",
        },
        headers=_csrf(client),
    )


def test_audit_csv_owner_can_download(client):
    _signup_owner(client)
    r = client.get("/api/orgs/current/audit.csv")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    assert 'attachment; filename="siteiq-audit-auditco.csv"' in r.headers["content-disposition"]
    body = r.text
    # Header row + at least the signup + org-created rows.
    lines = [ln for ln in body.splitlines() if ln]
    assert lines[0] == "created_at,kind,actor_user_id,payload_json"
    assert any("user.signup" in ln for ln in lines[1:])
    assert any("org.created" in ln for ln in lines[1:])


def test_audit_csv_rejects_bad_timestamp(client):
    _signup_owner(client)
    r = client.get("/api/orgs/current/audit.csv?since=not-a-date")
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "invalid_timestamp"


def test_audit_csv_admin_role_blocked(client):
    """Admins can read /audit (owner-only) per spec — verify."""
    _signup_owner(client)
    # The signup user is owner; demote-self isn't allowed, but we can
    # simulate via direct DB. Easiest: spin up a separate non-owner user
    # and check they get 403. Do this through invite + accept flow.
    import re
    h = _csrf(client)
    client.post(
        "/api/orgs/current/invites",
        json={"email": "admin@example.com", "role": "admin"},
        headers=h,
    )
    rows = client.get("/dev/outbox").json()
    invite = next(r for r in rows if r["to"] == "admin@example.com")
    token = re.search(r"token=([\w\-_]+)", invite["text"]).group(1)
    client.post("/auth/logout", headers=h)

    h2 = _csrf(client)
    client.post(
        "/auth/signup",
        json={
            "email": "admin@example.com",
            "name": "Admin",
            "company": "AdminCo",
            "password": "long-enough-password-x",
        },
        headers=h2,
    )
    client.post("/api/orgs/accept-invite", json={"token": token}, headers=h2)
    me = client.get("/auth/me").json()
    audit_org_id = next(o["id"] for o in me["memberships"] if o["name"] == "AuditCo")
    client.post("/api/orgs/switch", json={"org_id": audit_org_id}, headers=h2)

    r = client.get("/api/orgs/current/audit.csv")
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "insufficient_role"
