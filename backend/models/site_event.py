"""The site event — one immutable entry in the operational ledger.

`EventEnvelope` is the shape callers (demo generator, live simulation,
manual capture, future cameras) hand to `services.event_ledger.EventLedger`.
The ledger stamps the stream `seq`, `prev_hash`, and chained `hash` and
persists a `db.models.SiteEvent` row. `event_hash` is the single hashing
function so the writer and the `verify_chain` reader agree byte-for-byte.

Enums mirror the string columns on `SiteEvent`. `kind` is left as a free
string on the envelope so capture can emit bespoke kinds, but the common
kinds are enumerated here so producers/consumers share one vocabulary.
"""
from __future__ import annotations

import enum
import hashlib
import json
from datetime import datetime, timezone

from pydantic import BaseModel, Field


class SubjectType(str, enum.Enum):
    WORKER = "worker"
    EQUIPMENT = "equipment"
    MATERIAL = "material"
    ZONE = "zone"
    INSPECTION = "inspection"
    INCIDENT = "incident"
    DELIVERY = "delivery"
    OPTIMIZATION = "optimization"
    SITE = "site"
    # Companion events that record a status change ABOUT another event
    # (confirm/reject/supersede). subject_id is the target event id.
    EVENT = "event"


class EventKind(str, enum.Enum):
    # Workers
    WORKER_CLOCKED_IN = "worker.clocked_in"
    WORKER_CLOCKED_OUT = "worker.clocked_out"
    WORKER_TIMESHEET = "worker.timesheet"
    # Equipment
    EQUIPMENT_STATE_CHANGED = "equipment.state_changed"
    EQUIPMENT_UTILIZATION = "equipment.utilization"
    EQUIPMENT_RELEASED = "equipment.released"
    # Materials / deliveries
    MATERIAL_DELIVERED = "material.delivered"
    MATERIAL_STAGED = "material.staged"
    MATERIAL_CONSUMED = "material.consumed"
    # Zones / progress
    ZONE_PHASE_STARTED = "zone.phase_started"
    ZONE_PHASE_COMPLETED = "zone.phase_completed"
    # QA / safety
    INSPECTION_PASSED = "inspection.passed"
    INSPECTION_FAILED = "inspection.failed"
    INCIDENT_FLAGGED = "incident.flagged"
    # Optimisation
    OPTIMIZATION_APPLIED = "optimization.applied"
    # Companion lifecycle events (status changes about other events)
    EVENT_CONFIRMED = "event.confirmed"
    EVENT_REJECTED = "event.rejected"
    EVENT_SUPERSEDED = "event.superseded"
    # Free-form note captured by a human
    NOTE = "note"


class EventEnvelope(BaseModel):
    """An event to append. The ledger fills in seq + hash chain."""

    org_id: str
    project_id: str
    subject_type: str
    subject_id: str
    kind: str
    occurred_at: datetime
    payload: dict = Field(default_factory=dict)
    source: str = "system"
    confidence: float = 1.0
    evidence_ref: str | None = None
    status: str = "confirmed"
    supersedes_event_id: str | None = None
    actor_user_id: str | None = None


def _canonical_payload(payload: dict) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def _canonical_dt(dt: datetime) -> str:
    """Normalise a datetime to UTC-naive microsecond ISO so the hash is
    stable across the DB round-trip. SQLite's `DateTime(timezone=True)`
    returns naive datetimes while Postgres returns tz-aware UTC; both must
    rehash identically. We always store UTC, so dropping the tzinfo after
    converting is lossless."""
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt.isoformat(timespec="microseconds")


def event_hash(
    prev_hash: str,
    *,
    seq: int,
    occurred_at: datetime,
    subject_type: str,
    subject_id: str,
    kind: str,
    payload: dict,
    source: str,
    confidence: float,
    supersedes_event_id: str | None,
) -> str:
    """SHA-256 over `prev_hash` + the event's immutable content fields.

    Chaining `prev_hash` makes the per-stream log tamper-evident: editing
    or deleting any row breaks every subsequent hash, which `verify_chain`
    detects. Same inputs always produce the same digest.

    `status` is deliberately EXCLUDED: it is a denormalised cache that
    legitimately changes (proposed -> confirmed/rejected/superseded), and
    every such change is itself recorded as an immutable companion event.
    Hashing only the immutable content keeps the chain stable across those
    review transitions while still detecting tampering with what happened.
    """
    core = "|".join([
        prev_hash,
        str(seq),
        _canonical_dt(occurred_at),
        subject_type,
        subject_id,
        kind,
        _canonical_payload(payload),
        source,
        f"{confidence:.6f}",
        supersedes_event_id or "",
    ])
    return hashlib.sha256(core.encode("utf-8")).hexdigest()
