"""orgs.active_project_id survives a backend restart."""
from __future__ import annotations



def _csrf(client):
    csrf = client.get("/auth/csrf").json()["csrf_token"]
    return {"X-CSRF-Token": csrf, "Origin": "http://test.example.com"}


def test_load_project_persists_active_project_on_org(client):
    """After a project switch, the org row carries the choice and a
    fresh registry (simulating a backend restart) boots the engine on
    that project."""
    h = _csrf(client)
    client.post(
        "/auth/signup",
        json={
            "email": "owner@example.com",
            "name": "Owner",
            "company": "PersistCo",
            "password": "long-enough-password-x",
        },
        headers=h,
    )

    # Default project is westhafen — confirm.
    site = client.get("/api/site").json()
    assert "Westhafen" in site["name"]

    # Switch to europa-quarter.
    r = client.post("/api/projects/europa-quarter/load", headers=h)
    assert r.status_code == 200

    # Simulate "backend restart": replace the registry with a fresh one
    # so any cached engine is gone. The next /api/site call must rebuild
    # from the persisted org column.
    from state.registry import make_registry
    client.app.state.registry = make_registry(default_project_id="westhafen")

    site = client.get("/api/site").json()
    assert "Europaviertel" in site["name"], (
        f"active project lost after registry reset: {site['name']}"
    )
