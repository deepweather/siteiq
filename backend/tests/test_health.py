"""/healthz + /readyz endpoints."""
from __future__ import annotations


def test_healthz_is_unauthenticated_and_cheap(client):
    """Liveness endpoint must work without any auth setup."""
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_readyz_reports_ok_when_db_and_registry_are_up(client):
    r = client.get("/readyz")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["checks"]["database"] == "ok"
    assert body["checks"]["registry"] == "ok"
    assert "ts" in body


def test_readyz_returns_503_when_db_is_dead(client):
    """Simulate the engine being torn down — readyz must flip to 503."""
    factory = client.app.state.db_session_factory
    client.app.state.db_session_factory = None
    try:
        r = client.get("/readyz")
        assert r.status_code == 503
        assert r.json()["status"] == "degraded"
        assert "not_configured" in r.json()["checks"]["database"]
    finally:
        client.app.state.db_session_factory = factory


def test_version_endpoint_returns_shape(client):
    r = client.get("/api/version")
    assert r.status_code == 200
    body = r.json()
    assert "commit" in body
    assert "built_at" in body
    assert "short" in body


def test_version_endpoint_reads_env_overrides(client, monkeypatch):
    monkeypatch.setenv("SITEIQ_COMMIT_SHA", "abcdef1234567890")
    monkeypatch.setenv("SITEIQ_BUILT_AT", "2026-06-21T10:00:00Z")
    r = client.get("/api/version")
    body = r.json()
    assert body["commit"] == "abcdef1234567890"
    assert body["built_at"] == "2026-06-21T10:00:00Z"
    assert body["short"] == "abcdef1"
