"""Shared pytest fixtures.

The auth-aware fixtures here build a fresh FastAPI app + dedicated
SQLite file per test, run Alembic migrations, swap in a cheap argon2
hasher, and (optionally) sign up a real user so tests can call protected
routes with a real session cookie.
"""
import os
import sys
import tempfile
from pathlib import Path

# Make backend imports work like the live app
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from fastapi.testclient import TestClient
from simulation.engine import SimulationEngine


@pytest.fixture
def engine() -> SimulationEngine:
    """A fresh SimulationEngine using the default westhafen project."""
    return SimulationEngine()


@pytest.fixture
def frankfurt_engine() -> SimulationEngine:
    """europa-quarter has 6 zones (incl. zone-f) and 3 toilets."""
    return SimulationEngine(project_id="europa-quarter")


@pytest.fixture
def munich_engine() -> SimulationEngine:
    """isar-bridge runs to day 210 with start_day=135."""
    return SimulationEngine(project_id="isar-bridge")


# ---------------------------------------------------------------------------
# Auth-aware fixtures
# ---------------------------------------------------------------------------


class _NoopDetector:
    """Skip YOLO loading entirely in tests."""
    def get_video_ids(self): return []
    def get_video_info(self, _): return None
    def get_next_frame(self, *_a, **_k): return None
    def cleanup(self): pass


def _apply_migrations(database_url: str) -> None:
    """Run Alembic upgrade against the given URL — used to set up the
    per-test SQLite DB before the app starts."""
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(Path(__file__).resolve().parent.parent / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", database_url)
    cfg.set_main_option(
        "script_location",
        str(Path(__file__).resolve().parent.parent / "alembic"),
    )
    command.upgrade(cfg, "head")


@pytest.fixture
def app_settings(tmp_path):
    """Build a Settings object pointing at a per-test SQLite file."""
    from settings import Settings

    db_path = tmp_path / "test.db"
    return Settings(
        # /dev/outbox is mounted only when env=dev; tests rely on it to
        # discover verification + reset tokens, so we run as "dev" here.
        env="dev",
        database_url=f"sqlite+aiosqlite:///{db_path}",
        cors_origins="http://test.example.com",
        frontend_origin="http://test.example.com",
        cookie_secure=False,
        session_secret="test-secret-for-tests-only",
        email_provider="console",
        # Skip the per-project warm-up estimator to keep lifespan fast.
        compute_portfolio_at_startup=False,
    )


@pytest.fixture
def app_factory(app_settings, monkeypatch):
    """Returns a callable that builds a fresh FastAPI app for the test.
    Applies migrations to the per-test DB and swaps in the noop detector
    + a fast argon2 hasher so tests stay snappy."""
    import vision.detector as vd
    monkeypatch.setattr(vd, "VideoDetector", _NoopDetector)

    # Speed up argon2 in tests.
    import auth.passwords as pw
    monkeypatch.setattr(pw, "_DEFAULT", pw.cheap_hasher())

    _apply_migrations(app_settings.database_url)

    def _make():
        from main import create_app
        app = create_app(app_settings)
        # Disable rate limiting by default so the auth fixture's signup
        # call doesn't compete with concurrent tests across the same
        # in-memory limiter. The `limiter` test below re-enables it.
        from auth.rate_limit import limiter
        limiter.enabled = False
        if hasattr(app.state, "limiter"):
            app.state.limiter.enabled = False
        return app

    return _make


@pytest.fixture
def client(app_factory):
    """Plain TestClient — no session yet."""
    app = app_factory()
    with TestClient(app) as c:
        yield c


def authenticate(client):
    """Helper for tests that build their own TestClient — signs up a user,
    sets the session cookie + CSRF + Origin headers, and returns the
    same client. Tests that don't use the `auth_client` fixture (because
    they want their own settings or app variant) call this directly.

    Migrations must already be applied to the DB the app points at.
    """
    csrf = client.get("/auth/csrf").json()["csrf_token"]
    client.headers.update({
        "X-CSRF-Token": csrf,
        "Origin": "http://test.example.com",
    })
    r = client.post(
        "/auth/signup",
        json={
            "email": "owner@example.com",
            "name": "Test Owner",
            "company": "TestCo",
            "password": "correct-horse-battery-staple-x",
        },
    )
    assert r.status_code == 200, r.text
    return client


def setup_test_db(database_url: str) -> None:
    """Run alembic migrations against the given SQLite URL. Used by tests
    that create their own Settings + app outside of the standard fixtures."""
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(Path(__file__).resolve().parent.parent / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", database_url)
    cfg.set_main_option(
        "script_location",
        str(Path(__file__).resolve().parent.parent / "alembic"),
    )
    command.upgrade(cfg, "head")


@pytest.fixture
def auth_client(client):
    """A TestClient with a signed-up user + session cookie + CSRF token
    pre-attached. Use this for tests that exercise org-scoped routes."""
    return authenticate(client)
