"""Level background image upload/serve/delete.

Pins:
- happy path uploads a PNG, flips the level's `background_image_url`
- content_type validation rejects non-image payloads
- size cap stops big images
- role gating: viewer 403 / unauthenticated 401
- the GET asset route serves the bytes with a 1-year immutable Cache-Control
- DELETE strips the URL + drops the asset row
"""
from __future__ import annotations

import re
import struct
import zlib

from models.assets import DEFAULT_LEVEL_ID
from models.project_document import ProjectDocument, WorkerSeed
from models.site import Discipline, Level, Phase, Zone


def _make_doc(slug: str = "bg-host", *, levels: list[Level] | None = None) -> dict:
    lv = levels or [Level(id=DEFAULT_LEVEL_ID, name="EG", elevation_m=0.0, order=0)]
    doc = ProjectDocument(
        slug=slug, name=f"BG {slug}", description="bg test",
        discipline=Discipline.HOCHBAU, type="Residential",
        width=80.0, height=60.0,
        levels=lv,
        zones=[Zone(
            id="z1", label="Z", x=10, y=10, width=40, height=30,
            phase=Phase.STRUCTURAL, phase_progress=0.5,
            level_id=lv[0].id,
        )],
        worker_seeds=[WorkerSeed(zone_id="z1", trade="general", count=1)],
    )
    return doc.model_dump(mode="json")


def _create(auth_client, slug: str = "bg-host") -> tuple[str, str]:
    r = auth_client.post("/api/projects", json={"document": _make_doc(slug), "message": "init"})
    assert r.status_code == 200, r.text
    body = r.json()
    return body["id"], body["current_version_id"]


def _tiny_png() -> bytes:
    """Produce a minimal valid 1x1 PNG. We construct it inline instead
    of bundling a fixture so the test stays in-tree and reviewable."""
    sig = b"\x89PNG\r\n\x1a\n"

    def chunk(kind: bytes, body: bytes) -> bytes:
        return (
            struct.pack(">I", len(body))
            + kind + body
            + struct.pack(">I", zlib.crc32(kind + body) & 0xFFFFFFFF)
        )

    ihdr = chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
    raw = b"\x00\xff\x00\x00"  # filter byte + 1 RGB pixel
    idat = chunk(b"IDAT", zlib.compress(raw))
    iend = chunk(b"IEND", b"")
    return sig + ihdr + idat + iend


PNG_BYTES = _tiny_png()


# ── Happy path ───────────────────────────────────────────────────────


def test_upload_sets_level_background_image_url(auth_client):
    pid, _ = _create(auth_client)
    r = auth_client.post(
        f"/api/projects/{pid}/levels/{DEFAULT_LEVEL_ID}/background",
        files={"file": ("plan.png", PNG_BYTES, "image/png")},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["url"].startswith(f"/api/projects/{pid}/assets/")
    assert body["asset_id"]
    assert body["content_hash"]
    # The next GET on the project returns the patched document.
    detail = auth_client.get(f"/api/projects/{pid}").json()
    level = next(lv for lv in detail["document"]["levels"] if lv["id"] == DEFAULT_LEVEL_ID)
    assert level["background_image_url"] == body["url"]


def test_serve_asset_returns_bytes_with_immutable_cache(auth_client):
    pid, _ = _create(auth_client)
    up = auth_client.post(
        f"/api/projects/{pid}/levels/{DEFAULT_LEVEL_ID}/background",
        files={"file": ("plan.png", PNG_BYTES, "image/png")},
    ).json()
    r = auth_client.get(up["url"])
    assert r.status_code == 200
    assert r.content == PNG_BYTES
    assert r.headers["content-type"] in ("image/png", "image/png; charset=utf-8")
    cache_control = r.headers["cache-control"]
    assert "max-age=31536000" in cache_control
    assert "immutable" in cache_control
    assert r.headers["etag"] == f'"{up["content_hash"]}"'


def test_delete_strips_url_and_drops_asset(auth_client):
    pid, _ = _create(auth_client)
    up = auth_client.post(
        f"/api/projects/{pid}/levels/{DEFAULT_LEVEL_ID}/background",
        files={"file": ("plan.png", PNG_BYTES, "image/png")},
    ).json()

    r = auth_client.delete(f"/api/projects/{pid}/levels/{DEFAULT_LEVEL_ID}/background")
    assert r.status_code == 200, r.text
    assert r.json()["asset_id"] == up["asset_id"]

    detail = auth_client.get(f"/api/projects/{pid}").json()
    level = next(lv for lv in detail["document"]["levels"] if lv["id"] == DEFAULT_LEVEL_ID)
    assert level["background_image_url"] is None

    # The blob row is gone too: GET returns 404.
    r2 = auth_client.get(up["url"])
    assert r2.status_code == 404


# ── Validation ──────────────────────────────────────────────────────


def test_reject_non_image_content_type(auth_client):
    pid, _ = _create(auth_client)
    r = auth_client.post(
        f"/api/projects/{pid}/levels/{DEFAULT_LEVEL_ID}/background",
        files={"file": ("plan.pdf", b"%PDF-1.4\n%fake", "application/pdf")},
    )
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "invalid_content_type"


def test_reject_oversize_upload(auth_client):
    pid, _ = _create(auth_client)
    # 2 MB + 1 byte payload — the route reads MAX+1 and rejects.
    too_big = b"\x00" * (2 * 1024 * 1024 + 100)
    r = auth_client.post(
        f"/api/projects/{pid}/levels/{DEFAULT_LEVEL_ID}/background",
        files={"file": ("plan.png", too_big, "image/png")},
    )
    assert r.status_code == 413
    assert r.json()["error"]["code"] == "file_too_large"


def test_reject_unknown_level(auth_client):
    pid, _ = _create(auth_client)
    r = auth_client.post(
        f"/api/projects/{pid}/levels/L-99/background",
        files={"file": ("plan.png", PNG_BYTES, "image/png")},
    )
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "level_not_found"


# ── Role gating ─────────────────────────────────────────────────────


def test_upload_unauthenticated_is_401(client):
    csrf = client.get("/auth/csrf").json()["csrf_token"]
    r = client.post(
        "/api/projects/anything/levels/L0/background",
        files={"file": ("plan.png", PNG_BYTES, "image/png")},
        headers={"Origin": "http://test.example.com", "X-CSRF-Token": csrf},
    )
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "not_authenticated"


def test_upload_viewer_role_is_403(client):
    """Owner creates a project, invites viewer B, B fails to upload."""
    csrf = client.get("/auth/csrf").json()["csrf_token"]
    headers = {"X-CSRF-Token": csrf, "Origin": "http://test.example.com"}
    client.post("/auth/signup", json={
        "email": "owner@bg.example", "name": "O", "company": "OC",
        "password": "long-enough-pw-1",
    }, headers=headers)
    r = client.post("/api/projects", json={"document": _make_doc("bg-host"), "message": "init"}, headers=headers)
    pid = r.json()["id"]
    client.post(
        "/api/orgs/current/invites",
        json={"email": "viewer@bg.example", "role": "viewer"},
        headers=headers,
    )
    rows = client.get("/dev/outbox").json()
    invite = next(r for r in rows if r["to"] == "viewer@bg.example")
    token = re.search(r"token=([\w\-_]+)", invite["text"]).group(1)

    client.post("/auth/logout", headers=headers)
    csrf_b = client.get("/auth/csrf").json()["csrf_token"]
    h_b = {"X-CSRF-Token": csrf_b, "Origin": "http://test.example.com"}
    client.post("/auth/signup", json={
        "email": "viewer@bg.example", "name": "V", "company": "VC",
        "password": "long-enough-pw-2",
    }, headers=h_b)
    client.post("/api/orgs/accept-invite", json={"token": token}, headers=h_b)
    me = client.get("/auth/me").json()
    oc_id = next(o["id"] for o in me["memberships"] if o["name"] == "OC")
    client.post("/api/orgs/switch", json={"org_id": oc_id}, headers=h_b)

    r = client.post(
        f"/api/projects/{pid}/levels/{DEFAULT_LEVEL_ID}/background",
        files={"file": ("plan.png", PNG_BYTES, "image/png")},
        headers=h_b,
    )
    assert r.status_code == 403


# ── Hot-path metadata ───────────────────────────────────────────────


def test_upload_creates_new_version(auth_client):
    """A successful upload must bump the project's `current_version_id`
    because it writes the URL into a new ProjectDocument."""
    pid, v1 = _create(auth_client)
    up = auth_client.post(
        f"/api/projects/{pid}/levels/{DEFAULT_LEVEL_ID}/background",
        files={"file": ("plan.png", PNG_BYTES, "image/png")},
    ).json()
    assert up["current_version_id"] != v1
    after = auth_client.get(f"/api/projects/{pid}").json()
    assert after["current_version_id"] == up["current_version_id"]
