"""Rate-limit tests.

The default fixture turns the limiter off (see conftest) so the bulk of
the auth suite isn't affected by per-IP counters from concurrent tests
or from the `auth_client` fixture's signup call. These tests opt back in
locally.
"""
from __future__ import annotations

import pytest


def _csrf(client) -> dict:
    csrf = client.get("/auth/csrf").json()["csrf_token"]
    return {"X-CSRF-Token": csrf, "Origin": "http://test.example.com"}


@pytest.fixture
def limited_client(client):
    """A `client` with the per-app limiter re-enabled and counters reset.

    slowapi's in-memory limiter is module-level, so we also reset the
    Limiter so previous tests' hits don't bleed over.
    """
    from auth.rate_limit import limiter
    limiter.reset()
    limiter.enabled = True
    client.app.state.limiter.enabled = True
    yield client
    limiter.enabled = False
    client.app.state.limiter.enabled = False


def test_login_returns_429_after_burst(limited_client):
    """11th /auth/login from the same IP within a minute must hit the limit."""
    h = _csrf(limited_client)
    body = {"email": "nobody@example.com", "password": "wrong-but-long-enough"}
    last_status = None
    for _ in range(11):
        last_status = limited_client.post("/auth/login", json=body, headers=h).status_code
    assert last_status == 429
    payload = limited_client.post("/auth/login", json=body, headers=h).json()
    assert payload["error"]["code"] == "rate_limited"


def test_signup_rate_limited_after_5_in_an_hour(limited_client):
    """6th signup attempt from the same IP within an hour must hit the limit."""
    h = _csrf(limited_client)
    last_status = None
    for i in range(6):
        last_status = limited_client.post(
            "/auth/signup",
            json={
                "email": f"u{i}@example.com",
                "name": f"User {i}",
                "company": f"Co {i}",
                "password": "long-enough-password-x",
            },
            headers=h,
        ).status_code
    assert last_status == 429


def test_forgot_password_rate_limited(limited_client):
    h = _csrf(limited_client)
    last_status = None
    for _ in range(6):
        last_status = limited_client.post(
            "/auth/forgot-password",
            json={"email": "ghost@example.com"},
            headers=h,
        ).status_code
    assert last_status == 429
