"""Device lifecycle: claim codes, token auth, revoke/rotate.

Mirrors the session/invite machinery (`auth/sessions.py`, `orgs/service.py`):
opaque tokens stored only as `sha256`, single SQL revoke/rotate, every
mutation writes an `audit_events` row. A device is least-privilege — scoped
to exactly one `(org_id, project_id)` stream, append-only, and unable to
read other tenants or confirm/reject events (that authority is human).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth.tokens import generate_token, hash_token
from db.models import AuditEvent, Device, DeviceClaim, DeviceStatus


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


async def _audit(
    db: AsyncSession,
    *,
    kind: str,
    org_id: str,
    actor_user_id: Optional[str],
    payload: Optional[dict] = None,
) -> None:
    db.add(AuditEvent(
        id=str(uuid.uuid4()),
        org_id=org_id,
        actor_user_id=actor_user_id,
        kind=kind,
        payload=payload or {},
    ))


# ── claim codes ──────────────────────────────────────────────────────


async def create_claim(
    db: AsyncSession,
    *,
    org_id: str,
    project_id: str,
    kind: str,
    name: str,
    created_by_user_id: str,
    ttl_hours: int,
) -> tuple[DeviceClaim, str]:
    """Mint a one-time provisioning code. Returns (row, plaintext_code).
    The plaintext is shown to the admin once and never stored."""
    code = generate_token()
    row = DeviceClaim(
        id=str(uuid.uuid4()),
        org_id=org_id,
        project_id=project_id,
        kind=kind,
        name=name,
        token_hash=hash_token(code),
        expires_at=_now() + timedelta(hours=ttl_hours),
        created_by_user_id=created_by_user_id,
    )
    db.add(row)
    await db.flush()
    await _audit(
        db, kind="device.claim_created", org_id=org_id,
        actor_user_id=created_by_user_id,
        payload={"claim_id": row.id, "device_kind": kind, "name": name},
    )
    return row, code


async def claim_device(
    db: AsyncSession,
    *,
    code: str,
    agent_version: str | None = None,
) -> tuple[Device, str]:
    """Exchange a claim code for a registered device + its bearer token.
    Returns (device, plaintext_token). Single-use; raises on bad/expired."""
    result = await db.execute(
        select(DeviceClaim).where(DeviceClaim.token_hash == hash_token(code))
    )
    claim = result.scalar_one_or_none()
    if claim is None:
        raise ValueError("invalid_claim")
    if claim.consumed_at is not None:
        raise ValueError("claim_used")
    expires = _as_utc(claim.expires_at)
    if expires is not None and expires <= _now():
        raise ValueError("claim_expired")

    token = generate_token()
    device = Device(
        id=str(uuid.uuid4()),
        org_id=claim.org_id,
        project_id=claim.project_id,
        name=claim.name,
        kind=claim.kind,
        capabilities={},
        token_hash=hash_token(token),
        status=DeviceStatus.ACTIVE.value,
        agent_version=agent_version,
        last_seen_at=_now(),
    )
    db.add(device)
    claim.consumed_at = _now()
    await db.flush()
    await _audit(
        db, kind="device.registered", org_id=device.org_id, actor_user_id=None,
        payload={"device_id": device.id, "kind": device.kind, "name": device.name},
    )
    return device, token


# ── token auth ───────────────────────────────────────────────────────


async def authenticate_device(db: AsyncSession, token: str) -> Optional[Device]:
    """Resolve a live (active) device by its bearer token, or None."""
    if not token:
        return None
    result = await db.execute(
        select(Device).where(Device.token_hash == hash_token(token))
    )
    device = result.scalar_one_or_none()
    if device is None or device.status != DeviceStatus.ACTIVE.value:
        return None
    return device


async def touch_device(
    db: AsyncSession,
    device: Device,
    *,
    agent_version: str | None = None,
    queue_depth: int | None = None,
) -> None:
    device.last_seen_at = _now()
    if agent_version is not None:
        device.agent_version = agent_version
    if queue_depth is not None:
        device.queue_depth = queue_depth


# ── lifecycle ────────────────────────────────────────────────────────


async def revoke_device(
    db: AsyncSession, device: Device, *, actor_user_id: str | None
) -> None:
    device.status = DeviceStatus.REVOKED.value
    device.revoked_at = _now()
    await _audit(
        db, kind="device.revoked", org_id=device.org_id, actor_user_id=actor_user_id,
        payload={"device_id": device.id},
    )


async def rotate_device(
    db: AsyncSession, device: Device, *, actor_user_id: str | None
) -> str:
    """Issue a fresh token (invalidating the old one). Returns plaintext."""
    token = generate_token()
    device.token_hash = hash_token(token)
    device.status = DeviceStatus.ACTIVE.value
    device.revoked_at = None
    await _audit(
        db, kind="device.rotated", org_id=device.org_id, actor_user_id=actor_user_id,
        payload={"device_id": device.id},
    )
    return token
