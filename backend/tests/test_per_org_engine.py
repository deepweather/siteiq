"""Per-org simulation engines must not leak state across orgs."""
from __future__ import annotations


PW = "correct-horse-battery-staple-x"
A = {"email": "alpha@example.com", "name": "Alpha", "company": "AlphaCo", "password": PW}
B = {"email": "beta@example.com", "name": "Beta", "company": "BetaCo", "password": PW}


def _csrf(client) -> dict:
    csrf = client.get("/auth/csrf").json()["csrf_token"]
    return {"X-CSRF-Token": csrf, "Origin": "http://test.example.com"}


def test_two_orgs_have_independent_simulations(client):
    """A loads westhafen (default), B switches to europa-quarter. A's
    /api/site must still report westhafen — proving the engines are
    per-org, not shared."""
    # Sign up A.
    h = _csrf(client)
    client.post("/auth/signup", json=A, headers=h)
    site_a_before = client.get("/api/site").json()
    assert "Westhafen" in site_a_before["name"]
    client.post("/auth/logout", headers=h)

    # Sign up B and switch B's project to europa-quarter.
    h2 = _csrf(client)
    client.post("/auth/signup", json=B, headers=h2)
    r = client.post("/api/projects/europa-quarter/load", headers=h2)
    assert r.status_code == 200
    site_b = client.get("/api/site").json()
    assert "Europaviertel" in site_b["name"]

    # Switch back to A's session — A's site must still be westhafen.
    client.post("/auth/logout", headers=h2)
    h3 = _csrf(client)
    client.post("/auth/login", json={"email": A["email"], "password": PW}, headers=h3)
    site_a_after = client.get("/api/site").json()
    assert "Westhafen" in site_a_after["name"], (
        f"A's project leaked into B's switch: {site_a_after['name']}"
    )


def test_org_deletion_discards_engine(client):
    """Deleting an org must drop its engine from the registry. Probe
    via internals: the registry's all_engines() shrinks by one."""
    h = _csrf(client)
    client.post("/auth/signup", json=A, headers=h)
    # Force engine creation.
    client.get("/api/site")
    registry = client.app.state.registry
    assert len(registry.all_engines()) == 1

    # Delete the org.
    r = client.request(
        "DELETE",
        "/api/orgs/current",
        json={"confirm_name": "AlphaCo", "current_password": PW},
        headers=h,
    )
    assert r.status_code == 200
    assert len(registry.all_engines()) == 0
