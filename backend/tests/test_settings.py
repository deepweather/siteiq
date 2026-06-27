"""Tests for the Settings class (step 7)."""
from __future__ import annotations

import pytest

from settings import Settings


def test_defaults_match_previous_hardcoded_values():
    """Out-of-the-box settings must reproduce the legacy behavior so no
    operational surprises. We pass `_env_file=None` so the local
    `backend/.env` a developer might use to run the dev server doesn't
    leak into the hardcoded-defaults assertion."""
    s = Settings(_env_file=None)  # type: ignore[call-arg]
    assert s.cors_origins == ["http://localhost:5173", "http://localhost:5174"]
    assert s.default_project_id == "westhafen"
    assert s.log_level == "INFO"
    assert s.log_format == "text"
    assert s.yolo_model_path == "yolov8n.pt"


def test_env_override_log_level(monkeypatch):
    monkeypatch.setenv("SITEIQ_LOG_LEVEL", "DEBUG")
    s = Settings()
    assert s.log_level == "DEBUG"


def test_env_override_default_project(monkeypatch):
    monkeypatch.setenv("SITEIQ_DEFAULT_PROJECT_ID", "isar-bridge")
    s = Settings()
    assert s.default_project_id == "isar-bridge"


def test_cors_origins_accepts_comma_separated_string(monkeypatch):
    monkeypatch.setenv("SITEIQ_CORS_ORIGINS", "https://a.com,https://b.com, https://c.com")
    s = Settings()
    assert s.cors_origins == ["https://a.com", "https://b.com", "https://c.com"]


def test_invalid_log_level_rejected(monkeypatch):
    monkeypatch.setenv("SITEIQ_LOG_LEVEL", "PANIC")
    with pytest.raises(Exception):  # pydantic ValidationError
        Settings()


def test_invalid_log_format_rejected(monkeypatch):
    monkeypatch.setenv("SITEIQ_LOG_FORMAT", "csv")
    with pytest.raises(Exception):
        Settings()


def test_log_level_is_case_insensitive(monkeypatch):
    monkeypatch.setenv("SITEIQ_LOG_LEVEL", "debug")
    s = Settings()
    assert s.log_level == "DEBUG"


def test_explicit_settings_passed_to_create_app(tmp_path):
    """create_app(settings=...) must use the passed settings, not env."""
    from fastapi.testclient import TestClient
    from main import create_app
    from tests.conftest import authenticate, setup_test_db

    db = tmp_path / "ex.db"
    custom = Settings(
        env="dev",
        default_project_id="isar-bridge",
        log_level="WARNING",
        database_url=f"sqlite+aiosqlite:///{db}",
        cors_origins="http://test.example.com",
        frontend_origin="http://test.example.com",
        cookie_secure=False,
    )
    setup_test_db(custom.database_url)
    app = create_app(settings=custom)
    assert app.state.settings is custom

    import vision.detector as vd
    class _Noop:
        def get_video_ids(self): return []
        def get_video_info(self, _): return None
        def get_next_frame(self, *_a, **_k): return None
        def cleanup(self): pass
    orig = vd.VideoDetector
    vd.VideoDetector = _Noop  # type: ignore[misc]
    try:
        with TestClient(app) as c:
            authenticate(c)
            site = c.get("/api/site").json()
            assert "Isarbrücke" in site["name"]
    finally:
        vd.VideoDetector = orig
