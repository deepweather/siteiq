"""System-of-record HTTP surface.

Read access for any org member; writes (confirm/reject/capture/manual
events) require member+, demo regeneration requires admin+. Every event is
scoped to the org's active stream `(org_id, source.project_id)` so the
ledger lines up with the running simulation (and, later, the live camera
feed). Mutating routes write an `audit_events` row, matching `api/projects.py`.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import (
    get_capture_parser,
    get_current_org,
    get_current_user,
    get_query_responder,
    get_rate_card,
    get_source,
    require_role,
)
from auth.errors import ApiError
from db.models import AuditEvent, Org, Role, User
from db.session import get_db
from models.cost import CostBreakdown, RateCard
from models.project_document import ProjectDocument
from models.site_event import EventEnvelope
from seeds.loader import load_seed_document
from services.capture import CaptureParser
from services.cost_engine import compute_costs
from services.demo_record_generator import RECORD_BACKFILL_DAYS, generate_demo_history
from services.event_ledger import EventLedger, EventStatusValue
from services.record_projections import (
    daily_rollup,
    entity_projection,
    event_to_dict,
    list_subjects,
)
from services.record_query import QueryAnswer, QueryResponder
from state.source import SiteStateSource


router = APIRouter(prefix="/api/record", tags=["record"])


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def _audit(
    db: AsyncSession,
    *,
    kind: str,
    org_id: str | None,
    actor_user_id: str | None,
    payload: dict | None = None,
) -> None:
    db.add(AuditEvent(
        id=str(uuid.uuid4()),
        org_id=org_id,
        actor_user_id=actor_user_id,
        kind=kind,
        payload=payload or {},
    ))


# ── Request schemas ──────────────────────────────────────────────────


class RecordEventRequest(BaseModel):
    subject_type: str
    subject_id: str
    kind: str
    payload: dict = Field(default_factory=dict)
    occurred_at: datetime | None = None
    confidence: float = 1.0
    status: str = EventStatusValue.CONFIRMED
    evidence_ref: str | None = None


class CaptureRequest(BaseModel):
    text: str
    occurred_at: datetime | None = None


class QueryRequest(BaseModel):
    question: str


class ConfirmRequest(BaseModel):
    reason: str | None = None


class DemoGenerateRequest(BaseModel):
    days: int = RECORD_BACKFILL_DAYS
    seed: int | None = None


# ── Reads ────────────────────────────────────────────────────────────


@router.get("/events")
async def list_events(
    subject_type: str | None = None,
    subject_id: str | None = None,
    kind: str | None = None,
    source_filter: str | None = None,
    status: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    order: str = "desc",
    limit: int = 200,
    offset: int = 0,
    org: Org = Depends(get_current_org),
    src: SiteStateSource = Depends(get_source),
    db: AsyncSession = Depends(get_db),
):
    ledger = EventLedger(db)
    rows = await ledger.query(
        org.id, src.project_id,
        subject_type=subject_type,
        subject_id=subject_id,
        kinds=[kind] if kind else None,
        sources=[source_filter] if source_filter else None,
        statuses=[status] if status else None,
        since=since,
        until=until,
        order="asc" if order == "asc" else "desc",
        limit=min(max(limit, 1), 1000),
        offset=max(offset, 0),
    )
    return {"events": [event_to_dict(r) for r in rows], "project_id": src.project_id}


@router.get("/days")
async def list_days(
    org: Org = Depends(get_current_org),
    src: SiteStateSource = Depends(get_source),
    db: AsyncSession = Depends(get_db),
):
    """Per-day operational rollup for the day selector + overview."""
    ledger = EventLedger(db)
    rows = await ledger.query(org.id, src.project_id, order="asc", limit=100000)
    return {"days": daily_rollup(rows), "project_id": src.project_id}


@router.get("/timeline")
async def get_timeline(
    date: str | None = None,
    org: Org = Depends(get_current_org),
    src: SiteStateSource = Depends(get_source),
    db: AsyncSession = Depends(get_db),
):
    """Flight recorder: every event on a given calendar day (defaults to the
    most recent recorded day)."""
    ledger = EventLedger(db)
    if date is None:
        rollup = daily_rollup(
            await ledger.query(org.id, src.project_id, order="asc", limit=100000)
        )
        if not rollup:
            return {"date": None, "events": []}
        date = rollup[-1]["date"]
    try:
        day = datetime.fromisoformat(date).replace(tzinfo=timezone.utc)
    except ValueError:
        raise ApiError(400, "invalid_date", "date must be YYYY-MM-DD.", field="date")
    since = day.replace(hour=0, minute=0, second=0, microsecond=0)
    until = day.replace(hour=23, minute=59, second=59, microsecond=999999)
    rows = await ledger.query(
        org.id, src.project_id, since=since, until=until, order="asc", limit=5000
    )
    return {"date": date, "events": [event_to_dict(r) for r in rows]}


@router.get("/subjects")
async def list_directory(
    type: str | None = None,
    q: str | None = None,
    org: Org = Depends(get_current_org),
    src: SiteStateSource = Depends(get_source),
    db: AsyncSession = Depends(get_db),
):
    """Directory of distinct subjects (workers, equipment, materials, …) for
    the active stream, with a one-line descriptor + counts. The frontend
    groups by `subject_type` and filters by free text."""
    ledger = EventLedger(db)
    rows = await ledger.query(
        org.id, src.project_id,
        subject_type=type,
        statuses=[EventStatusValue.CONFIRMED, EventStatusValue.PROPOSED],
        order="asc", limit=200000,
    )
    subjects = list_subjects(rows)
    if q:
        needle = q.lower()
        subjects = [
            s for s in subjects
            if needle in s["subject_id"].lower()
            or (s["descriptor"] and needle in s["descriptor"].lower())
        ]
    # Counts per type for the category chips (computed over the unfiltered set
    # when no type filter is applied).
    counts: dict[str, int] = {}
    for s in subjects:
        counts[s["subject_type"]] = counts.get(s["subject_type"], 0) + 1
    return {"subjects": subjects, "counts": counts, "project_id": src.project_id}


@router.get("/entities/{subject_type}/{subject_id}")
async def get_entity(
    subject_type: str,
    subject_id: str,
    org: Org = Depends(get_current_org),
    src: SiteStateSource = Depends(get_source),
    db: AsyncSession = Depends(get_db),
):
    ledger = EventLedger(db)
    rows = await ledger.query(
        org.id, src.project_id,
        subject_type=subject_type, subject_id=subject_id,
        order="asc", limit=10000,
    )
    if not rows:
        raise ApiError(404, "entity_not_found", "No events for this subject.")
    return entity_projection(subject_type, subject_id, rows)


@router.get("/inbox")
async def get_inbox(
    org: Org = Depends(get_current_org),
    src: SiteStateSource = Depends(get_source),
    db: AsyncSession = Depends(get_db),
):
    """Low-confidence proposed events awaiting human confirmation."""
    ledger = EventLedger(db)
    rows = await ledger.query(
        org.id, src.project_id,
        statuses=[EventStatusValue.PROPOSED], order="desc", limit=500,
    )
    return {"events": [event_to_dict(r) for r in rows]}


@router.get("/costs", response_model=CostBreakdown)
async def get_costs(
    since: datetime | None = None,
    until: datetime | None = None,
    org: Org = Depends(get_current_org),
    src: SiteStateSource = Depends(get_source),
    rate_card: RateCard = Depends(get_rate_card),
    db: AsyncSession = Depends(get_db),
):
    ledger = EventLedger(db)
    rows = await ledger.query(
        org.id, src.project_id,
        statuses=[EventStatusValue.CONFIRMED],
        since=since, until=until, order="asc", limit=200000,
    )
    return compute_costs(rows, rate_card, since=since, until=until)


@router.get("/verify")
async def verify(
    org: Org = Depends(get_current_org),
    src: SiteStateSource = Depends(get_source),
    db: AsyncSession = Depends(get_db),
):
    """Tamper-evidence: recompute the hash chain for the active stream."""
    ledger = EventLedger(db)
    return await ledger.verify_chain(org.id, src.project_id)


# ── Writes ───────────────────────────────────────────────────────────


@router.post("/events/{event_id}/confirm")
async def confirm_event(
    event_id: str,
    req: ConfirmRequest,
    org: Org = Depends(get_current_org),
    user: User = Depends(get_current_user),
    _=Depends(require_role(Role.MEMBER)),
    db: AsyncSession = Depends(get_db),
):
    ledger = EventLedger(db)
    event = await ledger.get(org.id, event_id)
    if event is None:
        raise ApiError(404, "event_not_found", "Event not found.")
    if event.status == EventStatusValue.CONFIRMED:
        return event_to_dict(event)
    await ledger.set_status(
        event, new_status=EventStatusValue.CONFIRMED,
        actor_user_id=user.id, reason=req.reason,
    )
    await _audit(
        db, kind="record.event.confirmed", org_id=org.id, actor_user_id=user.id,
        payload={"event_id": event_id, "seq": event.seq},
    )
    return event_to_dict(event)


@router.post("/events/{event_id}/reject")
async def reject_event(
    event_id: str,
    req: ConfirmRequest,
    org: Org = Depends(get_current_org),
    user: User = Depends(get_current_user),
    _=Depends(require_role(Role.MEMBER)),
    db: AsyncSession = Depends(get_db),
):
    ledger = EventLedger(db)
    event = await ledger.get(org.id, event_id)
    if event is None:
        raise ApiError(404, "event_not_found", "Event not found.")
    await ledger.set_status(
        event, new_status=EventStatusValue.REJECTED,
        actor_user_id=user.id, reason=req.reason,
    )
    await _audit(
        db, kind="record.event.rejected", org_id=org.id, actor_user_id=user.id,
        payload={"event_id": event_id, "seq": event.seq},
    )
    return event_to_dict(event)


@router.post("/events")
async def create_event(
    req: RecordEventRequest,
    org: Org = Depends(get_current_org),
    user: User = Depends(get_current_user),
    _=Depends(require_role(Role.MEMBER)),
    src: SiteStateSource = Depends(get_source),
    db: AsyncSession = Depends(get_db),
):
    """Manual structured event entry (the explicit, high-trust path)."""
    ledger = EventLedger(db)
    row = await ledger.append(EventEnvelope(
        org_id=org.id,
        project_id=src.project_id,
        subject_type=req.subject_type,
        subject_id=req.subject_id,
        kind=req.kind,
        occurred_at=req.occurred_at or _now(),
        payload=req.payload,
        source="human",
        confidence=req.confidence,
        status=req.status,
        evidence_ref=req.evidence_ref,
        actor_user_id=user.id,
    ))
    await _audit(
        db, kind="record.event.created", org_id=org.id, actor_user_id=user.id,
        payload={"event_id": row.id, "kind": req.kind},
    )
    return event_to_dict(row)


@router.post("/capture")
async def capture(
    req: CaptureRequest,
    org: Org = Depends(get_current_org),
    user: User = Depends(get_current_user),
    _=Depends(require_role(Role.MEMBER)),
    src: SiteStateSource = Depends(get_source),
    parser: CaptureParser = Depends(get_capture_parser),
    db: AsyncSession = Depends(get_db),
):
    """Free-form capture: parse text into proposed events for the inbox."""
    envelopes = parser.parse(
        req.text,
        org_id=org.id,
        project_id=src.project_id,
        occurred_at=req.occurred_at,
        actor_user_id=user.id,
    )
    if not envelopes:
        return {"events": []}
    ledger = EventLedger(db)
    rows = await ledger.append_many(envelopes)
    await _audit(
        db, kind="record.captured", org_id=org.id, actor_user_id=user.id,
        payload={"count": len(rows)},
    )
    return {"events": [event_to_dict(r) for r in rows]}


@router.post("/query", response_model=QueryAnswer)
async def query(
    req: QueryRequest,
    org: Org = Depends(get_current_org),
    src: SiteStateSource = Depends(get_source),
    responder: QueryResponder = Depends(get_query_responder),
    rate_card: RateCard = Depends(get_rate_card),
    db: AsyncSession = Depends(get_db),
):
    """Conversational query over the ledger (read-only)."""
    return await responder.answer(
        db, org_id=org.id, project_id=src.project_id,
        question=req.question, rate_card=rate_card,
    )


@router.post("/demo/generate")
async def demo_generate(
    req: DemoGenerateRequest,
    org: Org = Depends(get_current_org),
    user: User = Depends(get_current_user),
    _=Depends(require_role(Role.ADMIN)),
    src: SiteStateSource = Depends(get_source),
    db: AsyncSession = Depends(get_db),
):
    """Regenerate demo history for the org's active project stream."""
    doc = await _resolve_active_document(db, org, fallback_slug=src.project_id)
    if doc is None:
        raise ApiError(404, "no_active_project", "No active project to backfill.")
    days = max(1, min(req.days, 120))
    summary = await generate_demo_history(
        db, org_id=org.id, document=doc, days=days, seed=req.seed
    )
    await _audit(
        db, kind="record.demo.generated", org_id=org.id, actor_user_id=user.id,
        payload={"project_id": summary["project_id"], "event_count": summary["event_count"]},
    )
    return summary


async def _resolve_active_document(
    db: AsyncSession, org: Org, *, fallback_slug: str
) -> ProjectDocument | None:
    """Resolve the org's active project document, matching `get_source`:
    pinned version first, then active seed slug, then the engine's slug."""
    if org.active_project_version_id:
        from db.project_repository import ProjectRepository

        repo = ProjectRepository(db)
        version = await repo.get_version(org.active_project_version_id)
        if version is not None:
            return ProjectDocument.model_validate(version.document)
    slug = org.active_project_id or fallback_slug
    doc = load_seed_document(slug)
    if doc is not None:
        return doc
    # Last resort: a project owned by the org or a public template by slug.
    from db.project_repository import ProjectRepository

    repo = ProjectRepository(db)
    project = await repo.get_project_by_slug(org_id=org.id, slug=slug)
    if project is not None:
        return await repo.load_document(project_id=project.id)
    return None
