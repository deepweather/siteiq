"""Every response must carry the baseline security headers."""
from __future__ import annotations


def test_baseline_headers_present(client):
    r = client.get("/auth/csrf")
    assert r.headers["X-Content-Type-Options"] == "nosniff"
    assert r.headers["X-Frame-Options"] == "DENY"
    assert r.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"
    assert "geolocation=()" in r.headers["Permissions-Policy"]
    csp = r.headers["Content-Security-Policy"]
    assert "frame-ancestors 'none'" in csp
    assert "object-src 'none'" in csp


def test_hsts_only_in_prod(client, app_settings):
    """HSTS must NOT be set in dev/test (would force HTTPS upgrades on
    localhost). The default fixture runs as dev → no HSTS."""
    r = client.get("/auth/csrf")
    assert app_settings.env == "dev"
    assert "Strict-Transport-Security" not in r.headers


def test_hsts_emitted_in_prod(tmp_path):
    """A prod-configured app must include HSTS."""
    from fastapi.testclient import TestClient
    from main import create_app
    from settings import Settings
    from tests.conftest import setup_test_db

    db = tmp_path / "prod.db"
    s = Settings(
        env="prod",
        database_url=f"sqlite+aiosqlite:///{db}",
        cors_origins="https://siteiq.example.com",
        frontend_origin="https://siteiq.example.com",
        cookie_secure=False,
        session_secret="prod-test-secret",
    )
    setup_test_db(s.database_url)
    import vision.detector as vd

    class _Noop:
        def get_video_ids(self): return []
        def get_video_info(self, _): return None
        def get_next_frame(self, *_a, **_k): return None
        def cleanup(self): pass

    orig = vd.VideoDetector
    vd.VideoDetector = _Noop  # type: ignore[misc]
    try:
        app = create_app(s)
        with TestClient(app) as c:
            r = c.get("/auth/csrf")
            assert "Strict-Transport-Security" in r.headers
            assert "max-age=31536000" in r.headers["Strict-Transport-Security"]
    finally:
        vd.VideoDetector = orig
