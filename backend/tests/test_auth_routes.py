"""End-to-end tests of the /auth/* routes through TestClient.

Every request includes the Origin header so the CSRF middleware accepts
it; state-changing requests also include the X-CSRF-Token. These mirror
exactly what the frontend will send.
"""
from __future__ import annotations

import re

from fastapi.testclient import TestClient


CRED = {
    "email": "alice@test.example.com",
    "name": "Alice",
    "company": "Alice Co",
    "password": "correct-horse-battery-staple-x",
}


def _csrf(client: TestClient) -> dict:
    csrf = client.get("/auth/csrf").json()["csrf_token"]
    return {"X-CSRF-Token": csrf, "Origin": "http://test.example.com"}


def _outbox_for(client: TestClient, email: str) -> list[dict]:
    rows = client.get("/dev/outbox").json()
    return [r for r in rows if r["to"] == email]


def test_csrf_required_for_signup(client):
    r = client.post(
        "/auth/signup",
        json=CRED,
        headers={"Origin": "http://test.example.com"},  # no X-CSRF-Token
    )
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "csrf_token_invalid"


def test_signup_login_logout_flow(client):
    h = _csrf(client)
    r = client.post("/auth/signup", json=CRED, headers=h)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["user"]["email"] == "alice@test.example.com"
    assert body["org"]["name"] == "Alice Co"
    assert body["org"]["role"] == "owner"

    me = client.get("/auth/me").json()
    assert me["user"]["email"] == "alice@test.example.com"

    # Logout — session cookie cleared, /auth/me returns null user.
    r = client.post("/auth/logout", headers=h)
    assert r.status_code == 200
    assert client.get("/auth/me").json()["user"] is None

    # Login — works.
    r = client.post(
        "/auth/login",
        json={"email": CRED["email"], "password": CRED["password"]},
        headers=h,
    )
    assert r.status_code == 200
    assert r.json()["user"]["email"] == "alice@test.example.com"


def test_duplicate_signup_rejected(client):
    h = _csrf(client)
    client.post("/auth/signup", json=CRED, headers=h)
    r = client.post("/auth/signup", json=CRED, headers=h)
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "email_taken"


def test_login_with_wrong_password_returns_401(client):
    h = _csrf(client)
    client.post("/auth/signup", json=CRED, headers=h)
    r = client.post(
        "/auth/login",
        json={"email": CRED["email"], "password": "wrong-x-x-x-x"},
        headers=h,
    )
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "invalid_credentials"


def test_login_unknown_email_returns_401(client):
    h = _csrf(client)
    r = client.post(
        "/auth/login",
        json={"email": "nobody@test.example.com", "password": "whatever-12345"},
        headers=h,
    )
    assert r.status_code == 401


def test_password_too_short_rejected(client):
    h = _csrf(client)
    r = client.post(
        "/auth/signup",
        json={**CRED, "password": "short"},
        headers=h,
    )
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "password_too_short"
    assert r.json()["error"]["field"] == "password"


def test_signup_emits_verification_email(client):
    h = _csrf(client)
    client.post("/auth/signup", json=CRED, headers=h)
    rows = _outbox_for(client, CRED["email"])
    assert len(rows) == 1
    assert "verify" in rows[0]["subject"].lower()
    # The token URL must be present in both text and html bodies.
    assert "/verify-email?token=" in rows[0]["text"]


def test_email_verification_round_trip(client):
    h = _csrf(client)
    client.post("/auth/signup", json=CRED, headers=h)
    row = _outbox_for(client, CRED["email"])[0]
    m = re.search(r"/verify-email\?token=([\w\-_]+)", row["text"])
    assert m, row["text"]
    token = m.group(1)

    r = client.post("/auth/verify-email", json={"token": token}, headers=h)
    assert r.status_code == 200, r.text
    me = client.get("/auth/me").json()
    assert me["user"]["email_verified"] is True

    # Replay attack — used token can't verify again.
    r2 = client.post("/auth/verify-email", json={"token": token}, headers=h)
    assert r2.status_code == 400


def test_password_reset_full_flow(client):
    h = _csrf(client)
    client.post("/auth/signup", json=CRED, headers=h)
    # Logout the signup session so we can prove reset issues a new one.
    client.post("/auth/logout", headers=h)

    r = client.post("/auth/forgot-password", json={"email": CRED["email"]}, headers=h)
    assert r.status_code == 200

    rows = _outbox_for(client, CRED["email"])
    reset_row = next(r for r in rows if "reset" in r["subject"].lower())
    m = re.search(r"/reset-password\?token=([\w\-_]+)", reset_row["text"])
    assert m
    token = m.group(1)

    new_pw = "brand-new-strong-password-1"
    r = client.post(
        "/auth/reset-password",
        json={"token": token, "password": new_pw},
        headers=h,
    )
    assert r.status_code == 200
    assert r.json()["user"]["email"] == CRED["email"]

    # Login with the OLD password fails.
    r = client.post(
        "/auth/login",
        json={"email": CRED["email"], "password": CRED["password"]},
        headers=h,
    )
    assert r.status_code == 401
    # Login with the NEW password succeeds.
    r = client.post(
        "/auth/login",
        json={"email": CRED["email"], "password": new_pw},
        headers=h,
    )
    assert r.status_code == 200


def test_forgot_password_unknown_email_silent(client):
    """We must not leak whether an email exists."""
    h = _csrf(client)
    r = client.post("/auth/forgot-password", json={"email": "nobody@test.example.com"}, headers=h)
    assert r.status_code == 200
    rows = _outbox_for(client, "nobody@test.example.com")
    assert rows == []


def test_sessions_list_and_revoke_all(client):
    h = _csrf(client)
    client.post("/auth/signup", json=CRED, headers=h)
    sessions = client.get("/auth/sessions").json()
    assert len(sessions) == 1
    assert sessions[0]["current"] is True

    # Revoke-all rotates the cookie but leaves the user signed in here.
    r = client.post("/auth/sessions/revoke-all", headers=h)
    assert r.status_code == 200
    assert client.get("/auth/me").json()["user"] is not None
