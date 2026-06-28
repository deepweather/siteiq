"""Device ingestion surface (`/api/ingest/*`).

Bearer-token authenticated (see `api.deps.get_current_device`), CSRF-exempt,
called server-to-server by edge agents. Devices append to durable staging
(`device_inbound`); the single chain-writer (`services.ingest_writer`) folds
those into the ledger. Append-only and scoped to the device's own
`(org, project)` — any client-supplied org/project is ignored.
"""
from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, Request, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_current_device, get_settings
from auth.errors import ApiError
from db.models import Device, DeviceBlob, DeviceInbound
from db.session import get_db
from services.device_service import claim_device, touch_device
from services.ingest_writer import ALLOWED_SOURCES


router = APIRouter(prefix="/api/ingest", tags=["ingest"])


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ── schemas ──────────────────────────────────────────────────────────


class EnvelopeIn(BaseModel):
    subject_type: str
    subject_id: str
    kind: str
    client_event_id: str = Field(min_length=8, max_length=64)
    occurred_at: datetime | None = None
    payload: dict = Field(default_factory=dict)
    confidence: float = 1.0
    source: str = "camera"
    evidence_ref: str | None = None


class EventsRequest(BaseModel):
    events: list[EnvelopeIn]
    agent_version: str | None = None
    queue_depth: int | None = None


class ClaimRequest(BaseModel):
    code: str
    agent_version: str | None = None


class HeartbeatRequest(BaseModel):
    agent_version: str | None = None
    queue_depth: int | None = None
    health: dict = Field(default_factory=dict)


# ── claim (no device token yet — uses the one-time code) ─────────────


@router.post("/claim")
async def claim(req: ClaimRequest, db: AsyncSession = Depends(get_db)):
    """Exchange a one-time claim code for a long-lived device token."""
    try:
        device, token = await claim_device(
            db, code=req.code, agent_version=req.agent_version
        )
    except ValueError as exc:
        raise ApiError(400, str(exc), "Claim code is invalid, used, or expired.")
    return {
        "device_id": device.id,
        "token": token,
        "org_id": device.org_id,
        "project_id": device.project_id,
        "name": device.name,
        "kind": device.kind,
    }


# ── event ingestion ──────────────────────────────────────────────────


@router.post("/events", status_code=202)
async def ingest_events(
    req: EventsRequest,
    device: Device = Depends(get_current_device),
    settings=Depends(get_settings),
    db: AsyncSession = Depends(get_db),
):
    """Stage a batch of events. Idempotent on `client_event_id`; the
    chain-writer folds staged rows into the ledger asynchronously."""
    if not getattr(settings, "ingest_enabled", True):
        raise ApiError(503, "ingest_disabled", "Ingestion is disabled.")

    cids = [e.client_event_id for e in req.events]
    existing: set[str] = set()
    if cids:
        result = await db.execute(
            select(DeviceInbound.client_event_id).where(
                DeviceInbound.org_id == device.org_id,
                DeviceInbound.project_id == device.project_id,
                DeviceInbound.client_event_id.in_(cids),
            )
        )
        existing = {row[0] for row in result.all()}

    accepted = 0
    duplicates = 0
    seen_in_batch: set[str] = set()
    for e in req.events:
        if e.client_event_id in existing or e.client_event_id in seen_in_batch:
            duplicates += 1
            continue
        seen_in_batch.add(e.client_event_id)
        source = e.source if e.source in ALLOWED_SOURCES else "sensor"
        envelope = {
            "subject_type": e.subject_type,
            "subject_id": e.subject_id,
            "kind": e.kind,
            "occurred_at": (e.occurred_at or _now()).isoformat(),
            "payload": e.payload,
            "confidence": e.confidence,
            "source": source,
            "evidence_ref": e.evidence_ref,
        }
        db.add(DeviceInbound(
            id=str(uuid.uuid4()),
            org_id=device.org_id,
            project_id=device.project_id,
            device_id=device.id,
            client_event_id=e.client_event_id,
            envelope=envelope,
        ))
        accepted += 1

    try:
        await db.flush()
    except IntegrityError:
        # A concurrent batch staged the same key first — safe to treat as dup.
        await db.rollback()
        return {"accepted": 0, "duplicates": len(req.events), "received": len(req.events)}

    await touch_device(
        db, device, agent_version=req.agent_version, queue_depth=req.queue_depth
    )
    return {"accepted": accepted, "duplicates": duplicates, "received": len(req.events)}


# ── evidence blobs ───────────────────────────────────────────────────


@router.post("/blobs")
async def ingest_blob(
    file: UploadFile = File(...),
    device: Device = Depends(get_current_device),
    settings=Depends(get_settings),
    db: AsyncSession = Depends(get_db),
):
    """Upload an evidence frame/clip; returns a `blob:<id>` ref to put in an
    event's `evidence_ref`."""
    data = await file.read()
    max_bytes = getattr(settings, "device_blob_max_bytes", 5 * 1024 * 1024)
    if len(data) > max_bytes:
        raise ApiError(413, "blob_too_large", f"Evidence exceeds {max_bytes} bytes.")
    blob = DeviceBlob(
        id=str(uuid.uuid4()),
        org_id=device.org_id,
        device_id=device.id,
        content_type=file.content_type or "application/octet-stream",
        data=data,
        content_hash=hashlib.sha256(data).hexdigest(),
    )
    db.add(blob)
    await db.flush()
    return {"id": blob.id, "ref": f"blob:{blob.id}"}


# ── heartbeat + config ───────────────────────────────────────────────


@router.post("/heartbeat")
async def heartbeat(
    req: HeartbeatRequest,
    device: Device = Depends(get_current_device),
    db: AsyncSession = Depends(get_db),
):
    await touch_device(
        db, device, agent_version=req.agent_version, queue_depth=req.queue_depth
    )
    return {"ok": True, "server_time": _now().isoformat()}


@router.get("/config")
async def get_config(
    request: Request,
    device: Device = Depends(get_current_device),
):
    """Calibration + zone/model config the agent pulls. `config_version` lets
    the agent skip re-applying unchanged config."""
    calibration = device.calibration or {}
    import json
    version = hashlib.sha256(
        json.dumps(calibration, sort_keys=True).encode("utf-8")
    ).hexdigest()[:16]
    return {
        "project_id": device.project_id,
        "calibration": calibration,
        "config_version": version,
        "server_time": _now().isoformat(),
    }
