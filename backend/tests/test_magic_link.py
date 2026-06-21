"""Magic-link login flow."""
from __future__ import annotations

import re

from fastapi.testclient import TestClient


CRED = {
    "email": "magic@example.com",
    "name": "Magic User",
    "company": "MagicCo",
    "password": "correct-horse-battery-staple-x",
}


def _csrf(client: TestClient) -> dict:
    csrf = client.get("/auth/csrf").json()["csrf_token"]
    return {"X-CSRF-Token": csrf, "Origin": "http://test.example.com"}


def _signup(client: TestClient) -> None:
    client.post("/auth/signup", json=CRED, headers=_csrf(client))


def _outbox_for(client: TestClient, email: str):
    return [r for r in client.get("/dev/outbox").json() if r["to"] == email]


def test_request_magic_link_silently_succeeds_for_unknown_email(client):
    h = _csrf(client)
    r = client.post(
        "/auth/request-magic-link",
        json={"email": "nobody@example.com"},
        headers=h,
    )
    assert r.status_code == 200
    # Nothing leaked to outbox.
    assert _outbox_for(client, "nobody@example.com") == []


def test_request_magic_link_emails_known_account(client):
    _signup(client)
    h = _csrf(client)
    # Signup created a verification email; request a magic link too.
    client.post("/auth/request-magic-link", json={"email": CRED["email"]}, headers=h)
    rows = _outbox_for(client, CRED["email"])
    magic = [r for r in rows if "sign in" in r["subject"].lower()]
    assert len(magic) == 1
    assert "/magic-link?token=" in magic[0]["text"]


def test_login_with_magic_link_round_trip(client):
    _signup(client)
    h = _csrf(client)
    # Sign out the signup session so the magic link is the only path.
    client.post("/auth/logout", headers=h)
    h2 = _csrf(client)
    client.post("/auth/request-magic-link", json={"email": CRED["email"]}, headers=h2)
    row = next(
        r for r in _outbox_for(client, CRED["email"])
        if "sign in" in r["subject"].lower()
    )
    token = re.search(r"/magic-link\?token=([\w\-_]+)", row["text"]).group(1)

    r = client.post("/auth/login-with-token", json={"token": token}, headers=h2)
    assert r.status_code == 200
    me = r.json()
    assert me["user"]["email"] == CRED["email"]

    # /auth/me confirms the cookie was set.
    assert client.get("/auth/me").json()["user"]["email"] == CRED["email"]


def test_magic_link_token_is_single_use(client):
    _signup(client)
    h = _csrf(client)
    client.post("/auth/logout", headers=h)
    h2 = _csrf(client)
    client.post("/auth/request-magic-link", json={"email": CRED["email"]}, headers=h2)
    row = next(
        r for r in _outbox_for(client, CRED["email"])
        if "sign in" in r["subject"].lower()
    )
    token = re.search(r"/magic-link\?token=([\w\-_]+)", row["text"]).group(1)

    assert client.post("/auth/login-with-token", json={"token": token}, headers=h2).status_code == 200
    # Replay attack — used token rejected.
    r2 = client.post("/auth/login-with-token", json={"token": token}, headers=h2)
    assert r2.status_code == 400
    assert r2.json()["error"]["code"] == "token_used"
