"""Request-Id middleware contract."""
from __future__ import annotations


def test_response_has_x_request_id(client):
    r = client.get("/healthz")
    rid = r.headers.get("x-request-id")
    assert rid is not None
    assert len(rid) >= 16  # uuid4 hex


def test_incoming_x_request_id_is_echoed(client):
    r = client.get("/healthz", headers={"X-Request-Id": "trace-abc-123"})
    assert r.headers["x-request-id"] == "trace-abc-123"


def test_each_request_gets_a_distinct_id_when_unset(client):
    r1 = client.get("/healthz")
    r2 = client.get("/healthz")
    assert r1.headers["x-request-id"] != r2.headers["x-request-id"]


def test_error_envelope_includes_request_id(client):
    """A protected route returns 401 with the rid in the envelope."""
    r = client.get("/api/site")
    assert r.status_code == 401
    body = r.json()
    assert "request_id" in body["error"]
    assert body["error"]["request_id"] == r.headers["x-request-id"]
