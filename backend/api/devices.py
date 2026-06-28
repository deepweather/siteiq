"""Device fleet management (`/api/devices/*`).

Browser/admin surface: cookie-authenticated, `require_role(ADMIN)` for
mutations, CSRF-protected (unlike `/api/ingest/*`). Lets operators provision
(claim codes), monitor (health), rename, calibrate, revoke, and rotate
devices. Every mutation writes an `audit_events` row via `device_service`.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_current_org, get_current_user, get_settings, require_role
from auth.errors import ApiError
from db.models import Device, DeviceBlob, DeviceKind, Org, Role, SiteEvent, User
from db.session import get_db
from services import device_service as svc


router = APIRouter(prefix="/api/devices", tags=["devices"])

# A device is "online" if it has phoned home within this window.
ONLINE_WINDOW_SECONDS = 120


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def _health(device: Device) -> str:
    last = _as_utc(device.last_seen_at)
    if last is None:
        return "never_seen"
    if (_now() - last) <= timedelta(seconds=ONLINE_WINDOW_SECONDS):
        return "online"
    return "offline"


def _device_dict(device: Device, *, events_total: int = 0, last_event_at=None) -> dict:
    return {
        "id": device.id,
        "name": device.name,
        "kind": device.kind,
        "project_id": device.project_id,
        "status": device.status,
        "health": _health(device),
        "agent_version": device.agent_version,
        "queue_depth": device.queue_depth,
        "last_seen_at": _as_utc(device.last_seen_at).isoformat() if device.last_seen_at else None,
        "created_at": _as_utc(device.created_at).isoformat() if device.created_at else None,
        "capabilities": device.capabilities or {},
        "has_calibration": bool(device.calibration),
        "events_total": events_total,
        "last_event_at": last_event_at.isoformat() if isinstance(last_event_at, datetime) else None,
    }


# ── schemas ──────────────────────────────────────────────────────────


class ClaimCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    kind: str = DeviceKind.CAMERA.value
    project_id: str | None = None  # defaults to the org's active project


class DevicePatchRequest(BaseModel):
    name: str | None = None
    capabilities: dict | None = None


class CalibrationRequest(BaseModel):
    calibration: dict


# ── reads ────────────────────────────────────────────────────────────


@router.get("")
async def list_devices(
    org: Org = Depends(get_current_org),
    _=Depends(require_role(Role.MEMBER)),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Device).where(Device.org_id == org.id).order_by(Device.created_at.desc())
    )
    devices = list(result.scalars().all())
    # Per-device event counts in one grouped query.
    counts: dict[str, tuple[int, datetime | None]] = {}
    if devices:
        rows = await db.execute(
            select(
                SiteEvent.device_id,
                func.count(SiteEvent.id),
                func.max(SiteEvent.occurred_at),
            )
            .where(SiteEvent.org_id == org.id, SiteEvent.device_id.isnot(None))
            .group_by(SiteEvent.device_id)
        )
        for did, n, last in rows.all():
            counts[did] = (int(n), last)
    return [
        _device_dict(d, events_total=counts.get(d.id, (0, None))[0],
                     last_event_at=counts.get(d.id, (0, None))[1])
        for d in devices
    ]


@router.get("/{device_id}")
async def get_device(
    device_id: str,
    org: Org = Depends(get_current_org),
    _=Depends(require_role(Role.MEMBER)),
    db: AsyncSession = Depends(get_db),
):
    device = await db.get(Device, device_id)
    if device is None or device.org_id != org.id:
        raise ApiError(404, "device_not_found", "Device not found.")
    cnt = await db.execute(
        select(func.count(SiteEvent.id), func.max(SiteEvent.occurred_at))
        .where(SiteEvent.org_id == org.id, SiteEvent.device_id == device.id)
    )
    n, last = cnt.one()
    out = _device_dict(device, events_total=int(n or 0), last_event_at=last)
    out["calibration"] = device.calibration or {}
    return out


# ── evidence blobs (served to the Record Inbox thumbnails) ───────────


@router.get("/blobs/{blob_id}")
async def get_blob(
    blob_id: str,
    org: Org = Depends(get_current_org),
    _=Depends(require_role(Role.MEMBER)),
    db: AsyncSession = Depends(get_db),
):
    """Serve an evidence frame/clip (referenced by an event's
    `evidence_ref="blob:<id>"`). Org-scoped; member+."""
    blob = await db.get(DeviceBlob, blob_id)
    if blob is None or blob.org_id != org.id:
        raise ApiError(404, "blob_not_found", "Evidence not found.")
    return Response(
        content=blob.data,
        media_type=blob.content_type,
        headers={
            "Cache-Control": "private, max-age=86400",
            "ETag": blob.content_hash,
        },
    )


# ── provisioning ─────────────────────────────────────────────────────


@router.post("/claims")
async def create_claim(
    req: ClaimCreateRequest,
    org: Org = Depends(get_current_org),
    user: User = Depends(get_current_user),
    _=Depends(require_role(Role.ADMIN)),
    settings=Depends(get_settings),
    db: AsyncSession = Depends(get_db),
):
    """Mint a one-time claim code. The plaintext code is returned ONCE."""
    if req.kind not in {k.value for k in DeviceKind}:
        raise ApiError(400, "invalid_kind", f"Unknown device kind '{req.kind}'.", field="kind")
    project_id = req.project_id or org.active_project_id or settings.default_project_id
    claim, code = await svc.create_claim(
        db,
        org_id=org.id,
        project_id=project_id,
        kind=req.kind,
        name=req.name,
        created_by_user_id=user.id,
        ttl_hours=settings.device_claim_ttl_hours,
    )
    return {
        "claim_id": claim.id,
        "code": code,
        "kind": req.kind,
        "name": req.name,
        "project_id": project_id,
        "expires_at": _as_utc(claim.expires_at).isoformat(),
        # Convenience payload for a QR the installer scans.
        "qr": {"code": code, "project_id": project_id, "kind": req.kind},
    }


# ── mutations ────────────────────────────────────────────────────────


@router.patch("/{device_id}")
async def patch_device(
    device_id: str,
    req: DevicePatchRequest,
    org: Org = Depends(get_current_org),
    _=Depends(require_role(Role.ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    device = await db.get(Device, device_id)
    if device is None or device.org_id != org.id:
        raise ApiError(404, "device_not_found", "Device not found.")
    if req.name is not None:
        device.name = req.name
    if req.capabilities is not None:
        device.capabilities = req.capabilities
    return _device_dict(device)


@router.delete("/{device_id}")
async def revoke_device(
    device_id: str,
    org: Org = Depends(get_current_org),
    user: User = Depends(get_current_user),
    _=Depends(require_role(Role.ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    device = await db.get(Device, device_id)
    if device is None or device.org_id != org.id:
        raise ApiError(404, "device_not_found", "Device not found.")
    await svc.revoke_device(db, device, actor_user_id=user.id)
    return {"status": "revoked", "device_id": device.id}


@router.post("/{device_id}/rotate")
async def rotate_device(
    device_id: str,
    org: Org = Depends(get_current_org),
    user: User = Depends(get_current_user),
    _=Depends(require_role(Role.ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    device = await db.get(Device, device_id)
    if device is None or device.org_id != org.id:
        raise ApiError(404, "device_not_found", "Device not found.")
    token = await svc.rotate_device(db, device, actor_user_id=user.id)
    return {"status": "rotated", "device_id": device.id, "token": token}


@router.put("/{device_id}/calibration")
async def set_calibration(
    device_id: str,
    req: CalibrationRequest,
    org: Org = Depends(get_current_org),
    user: User = Depends(get_current_user),
    _=Depends(require_role(Role.ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    device = await db.get(Device, device_id)
    if device is None or device.org_id != org.id:
        raise ApiError(404, "device_not_found", "Device not found.")
    device.calibration = req.calibration
    await svc._audit(
        db, kind="device.config_changed", org_id=org.id, actor_user_id=user.id,
        payload={"device_id": device.id},
    )
    return {"status": "ok", "device_id": device.id}
