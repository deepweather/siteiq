"""Device ingestion chain-writer.

Devices append to `device_inbound` (cheap, idempotent). This module is the
*single* writer that folds those staged rows into the hash-chained
`site_events` via `EventLedger`, preserving the gap-free per-stream `seq`
without locking the device-facing path. It is driven by the one drain task
in `main._run_event_drain_loop` (the same task that drains the simulation's
`engine.pending_events`), so device and simulation writes to a given
`(org, project)` stream are serialized within one coroutine — no `seq`
collisions.

Confidence policy: events at/above `confidence_floor` are written
`confirmed`; below it they land `proposed` and surface in the Record Inbox
for human review ("confirm, don't create").
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import DeviceInbound
from models.site_event import EventEnvelope
from services.event_ledger import EventLedger, EventStatusValue


logger = logging.getLogger("siteiq.ingest")

# Allowed provenance for device-submitted events. A device can never claim
# to be a human/simulation/system source.
ALLOWED_SOURCES = {"camera", "sensor", "integration"}

_BATCH = 500


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_occurred(value, fallback: datetime) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return fallback
    return fallback


async def distinct_unprocessed_streams(
    session: AsyncSession,
) -> list[tuple[str, str]]:
    """Every `(org_id, project_id)` with staged-but-unwritten device events."""
    result = await session.execute(
        select(DeviceInbound.org_id, DeviceInbound.project_id)
        .where(DeviceInbound.processed_at.is_(None))
        .distinct()
    )
    return [(row[0], row[1]) for row in result.all()]


async def drain_device_inbound(
    session: AsyncSession,
    *,
    org_id: str,
    project_id: str,
    confidence_floor: float,
) -> int:
    """Fold one stream's unprocessed inbound rows into the ledger. Returns
    the number of events written. Must be called from the single drain task
    so it is the sole writer for the stream."""
    result = await session.execute(
        select(DeviceInbound)
        .where(
            DeviceInbound.org_id == org_id,
            DeviceInbound.project_id == project_id,
            DeviceInbound.processed_at.is_(None),
        )
        .order_by(DeviceInbound.received_at.asc(), DeviceInbound.id.asc())
        .limit(_BATCH)
    )
    rows = list(result.scalars().all())
    if not rows:
        return 0

    ledger = EventLedger(session)
    envelopes: list[EventEnvelope] = []
    for row in rows:
        e = row.envelope or {}
        source = str(e.get("source", "camera"))
        if source not in ALLOWED_SOURCES:
            source = "sensor"
        confidence = float(e.get("confidence", 1.0))
        status = (
            EventStatusValue.CONFIRMED
            if confidence >= confidence_floor
            else EventStatusValue.PROPOSED
        )
        envelopes.append(EventEnvelope(
            org_id=org_id,
            project_id=project_id,
            subject_type=str(e.get("subject_type", "site")),
            subject_id=str(e.get("subject_id", "site")),
            kind=str(e.get("kind", "note")),
            occurred_at=_parse_occurred(e.get("occurred_at"), row.received_at),
            payload=e.get("payload") or {},
            source=source,
            confidence=confidence,
            evidence_ref=e.get("evidence_ref"),
            status=status,
            device_id=row.device_id,
            client_event_id=row.client_event_id,
        ))

    await ledger.append_many(envelopes)
    now = _now()
    for row in rows:
        row.processed_at = now
    await session.flush()
    logger.info(
        "device_inbound_drained",
        extra={"org_id": org_id, "project_id": project_id, "count": len(rows)},
    )
    return len(rows)
