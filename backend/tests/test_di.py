"""Step 2 — proves DI works: two TestClient instances over two different
FastAPI() apps with different state DO NOT share global state."""
from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient


class _NoopDetector:
    def get_video_ids(self): return []
    def get_video_info(self, _): return None
    def get_next_frame(self, *_args, **_kw): return None
    def cleanup(self): pass


@pytest.fixture(autouse=True)
def _patch_detector():
    import vision.detector as vd
    original = vd.VideoDetector
    vd.VideoDetector = _NoopDetector  # type: ignore[misc]
    yield
    vd.VideoDetector = original


def test_no_module_level_engine_global():
    """The `engine` module global from before the refactor should be gone."""
    import main
    assert not hasattr(main, "engine"), (
        "main.engine still exists as a module-level global — DI refactor incomplete"
    )
    assert not hasattr(main, "cached_recommendations"), \
        "main.cached_recommendations leaked"
    assert not hasattr(main, "cached_project_id"), \
        "main.cached_project_id leaked"
    assert not hasattr(main, "recs_dirty"), \
        "main.recs_dirty leaked"


def test_no_module_level_globals_in_api_modules():
    """Same for api/routes.py, api/websocket.py, api/camera.py."""
    from api import routes, websocket, camera
    for mod in (routes, websocket, camera):
        for forbidden in ("_engine", "_get_recommendations",
                          "_clear_recommendations_cache", "_detector",
                          "_get_analytics"):
            assert not hasattr(mod, forbidden), (
                f"{mod.__name__}.{forbidden} still exists — DI refactor incomplete"
            )


def test_two_apps_have_isolated_state():
    """Two FastAPI apps created via create_app() must not share project state."""
    from main import create_app
    app1 = create_app()
    app2 = create_app()
    assert app1 is not app2
    with TestClient(app1) as c1, TestClient(app2) as c2:
        time.sleep(0.3)
        # Switch app1 to europa-quarter
        assert c1.post("/api/projects/europa-quarter/load").status_code == 200
        # app2 should still report westhafen (the default)
        site2 = c2.get("/api/site").json()
        assert "Westhafen" in site2["name"], (
            f"app2 unexpectedly affected by app1's project switch: {site2['name']}"
        )
        # And app1 should be on europa-quarter
        site1 = c1.get("/api/site").json()
        assert "Europaviertel" in site1["name"]


def test_503_when_dependencies_missing():
    """A bare FastAPI() without lifespan should get 503 from endpoints
    that need the source — proving Depends actually checks app.state."""
    from fastapi import FastAPI
    from api.routes import router as api_router
    bare = FastAPI()
    bare.include_router(api_router)
    with TestClient(bare) as c:
        r = c.get("/api/site")
        assert r.status_code == 503
        assert "not ready" in r.json()["detail"].lower()


def test_dependency_override_pattern_works():
    """app.dependency_overrides should swap dependencies for tests —
    confirming Depends() is wired correctly."""
    from fastapi.testclient import TestClient
    from main import create_app
    from api.deps import get_source
    from simulation.engine import SimulationEngine

    app = create_app()

    custom_engine = SimulationEngine(project_id="isar-bridge")
    app.dependency_overrides[get_source] = lambda: custom_engine

    with TestClient(app) as c:
        # Should serve isar-bridge despite the lifespan setting up westhafen
        site = c.get("/api/site").json()
        assert "Isarbrücke" in site["name"]
