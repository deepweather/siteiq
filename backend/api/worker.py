"""Worker PWA surface — the field-crew app's backend.

A deliberately narrow, big-button-friendly slice of the system of record
for workers on site. Reads (overview, assets) are open to any org member
(viewer+); the crew tier in `RecordAccess` keeps individual worker records
out. Writes go through one endpoint (`POST /entry`) that always emits a
`proposed` event, so a worker proposes and a supervisor confirms via the
existing Inbox ("confirm, don't create").

Everything funnels through the same `EventLedger` as the simulation, the
demo generator, and a future camera LiveSource. The only worker-specific
addition is the client idempotency key, which makes the offline outbox
safe to replay.
"""
from __future__ import annotations

import logging
import uuid
from collections import defaultdict
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_current_org, get_current_user, get_source
from api.record import get_record_access
from auth.errors import ApiError
from db.models import AuditEvent, Org, User
from db.session import get_db
from models.site_event import EventEnvelope, EventKind, SubjectType
from services.event_ledger import EventLedger, EventStatusValue
from services.record_access import RecordAccess
from services.record_projections import (
    daily_rollup,
    entity_projection,
    event_to_dict,
)
from state.source import SiteStateSource


router = APIRouter(prefix="/api/worker", tags=["worker"])
logger = logging.getLogger("siteiq.worker")


def _now() -> datetime:
    return datetime.now(timezone.utc)


# Subject types a worker can browse / look up. Worker subjects are excluded
# on purpose (privacy tier) and filtered again by RecordAccess as a backstop.
ASSET_SUBJECT_TYPES = (
    SubjectType.EQUIPMENT.value,
    SubjectType.MATERIAL.value,
    SubjectType.ZONE.value,
)

# Default subject ids for entries that don't reference a concrete asset.
_DEFAULT_SUBJECT_ID = {
    "incident": "capture-incident",
    "inspection": "capture-inspection",
    "note": "site",
}


# ── Request schemas ──────────────────────────────────────────────────


class WorkerEntryRequest(BaseModel):
    """A single big-button entry from the field. `kind` is one of the
    allow-listed worker kinds; `payload` carries the kind-specific fields
    the form collected (e.g. quantity/unit/zone for a delivery)."""

    kind: str
    # Client-generated idempotency key (a uuid created when the form opens),
    # so the offline outbox can replay the POST exactly once.
    client_event_id: str = Field(min_length=8, max_length=64)
    subject_id: str | None = None
    payload: dict = Field(default_factory=dict)
    occurred_at: datetime | None = None


# ── Reads ────────────────────────────────────────────────────────────


@router.get("/overview")
async def overview(
    org: Org = Depends(get_current_org),
    user: User = Depends(get_current_user),
    src: SiteStateSource = Depends(get_source),
    db: AsyncSession = Depends(get_db),
):
    """Home-screen summary: which site, today's activity counts, and how
    many of my own entries are still awaiting supervisor review."""
    ledger = EventLedger(db)
    rows = await ledger.query(org.id, src.project_id, order="asc", limit=100000)
    days = daily_rollup(rows)
    today = days[-1] if days else None

    my_pending = sum(
        1
        for r in rows
        if r.status == EventStatusValue.PROPOSED and r.actor_user_id == user.id
    )

    site = src.site
    return {
        "project_id": src.project_id,
        "site_name": getattr(site, "name", src.project_id),
        "sim_day": src.sim_day,
        "today": {
            "deliveries": today["deliveries"] if today else 0,
            "incidents": today["incidents"] if today else 0,
            "inspections": today["inspections"] if today else 0,
        },
        "my_pending": my_pending,
    }


def _state_str(value) -> str | None:
    if value is None:
        return None
    return getattr(value, "value", None) or str(value)


def _row(subject_type: str, subject_id: str, descriptor: str | None, last_state: str | None) -> dict:
    return {
        "subject_type": subject_type,
        "subject_id": subject_id,
        "descriptor": descriptor,
        "last_state": last_state,
        "event_count": 0,
        "last_seen": None,
        "pending": 0,
        "metrics": {},
        "state": {},
    }


def _base_assets_from_site(src: SiteStateSource, type_filter: str | None) -> dict[tuple[str, str], dict]:
    """The site's real equipment / materials / zones from the active project,
    so the Assets tab is populated immediately — even before any ledger
    history exists (mirrors how `/api/worker/zones` is sourced)."""
    rows: dict[tuple[str, str], dict] = {}
    want = (type_filter,) if type_filter else ASSET_SUBJECT_TYPES
    if "equipment" in want or "material" in want:
        for a in src.assets:
            if a.type == "equipment" and ("equipment" in want):
                rows[("equipment", a.id)] = _row(
                    "equipment", a.id, getattr(a, "subtype", None),
                    _state_str(getattr(a, "state", None)),
                )
            elif a.type == "material" and ("material" in want):
                rows[("material", a.id)] = _row(
                    "material", a.id, getattr(a, "subtype", None), None
                )
    if "zone" in want:
        for z in src.site.zones:
            rows[("zone", z.id)] = _row(
                "zone", z.id, getattr(z, "label", z.id), _state_str(getattr(z, "phase", None))
            )
    return rows


def _asset_from_site(src: SiteStateSource, subject_type: str, subject_id: str) -> dict | None:
    """A minimal entity projection synthesised from the live site definition,
    for assets that have no ledger history yet."""
    state: dict = {}
    descriptor: str | None = None
    if subject_type in ("equipment", "material"):
        asset = src.asset_by_id(subject_id)
        if asset is None or asset.type != subject_type:
            return None
        descriptor = getattr(asset, "subtype", None)
        state = {"subtype": descriptor, "state": _state_str(getattr(asset, "state", None))}
    elif subject_type == "zone":
        zone = src.zone_by_id(subject_id)
        if zone is None:
            return None
        descriptor = getattr(zone, "label", subject_id)
        state = {"phase": _state_str(getattr(zone, "phase", None)), "label": descriptor}
    else:
        return None
    return {
        "subject_type": subject_type,
        "subject_id": subject_id,
        "event_count": 0,
        "first_seen": None,
        "last_seen": None,
        "kinds": {},
        "state": state,
        "metrics": {},
        "events": [],
        "descriptor": descriptor,
    }


def _merge_material_metrics(metrics: dict) -> dict:
    out = dict(metrics)
    if "delivered_qty" in out or "consumed_qty" in out:
        out["on_hand_qty"] = round(
            float(out.get("delivered_qty", 0.0)) - float(out.get("consumed_qty", 0.0)), 1
        )
    return out


def _asset_rows(
    src: SiteStateSource, ledger_rows: list, access: RecordAccess, type_filter: str | None
) -> list[dict]:
    """The site's assets (always present) overlaid with ledger-derived metrics
    (material on-hand, equipment utilisation) where events exist. Subjects that
    only exist in the ledger (e.g. captured deliveries, device subjects) are
    appended too."""
    rows = _base_assets_from_site(src, type_filter)

    by_subject: dict[tuple[str, str], list] = defaultdict(list)
    for r in ledger_rows:
        if r.subject_type in ASSET_SUBJECT_TYPES:
            by_subject[(r.subject_type, r.subject_id)].append(r)

    for (st, sid), evs in by_subject.items():
        if type_filter and st != type_filter:
            continue
        proj = entity_projection(st, sid, evs)
        metrics = dict(proj.get("metrics") or {})
        if st == SubjectType.MATERIAL.value:
            metrics = _merge_material_metrics(metrics)
        if (st, sid) in rows:
            rows[(st, sid)]["metrics"] = {**rows[(st, sid)]["metrics"], **metrics}
            rows[(st, sid)]["state"] = proj.get("state") or {}
            rows[(st, sid)]["event_count"] = proj.get("event_count", 0)
            rows[(st, sid)]["last_seen"] = proj.get("last_seen")
        else:
            state = proj.get("state") or {}
            rows[(st, sid)] = {
                **_row(st, sid, state.get("subtype") or state.get("trade") or sid, None),
                "metrics": metrics,
                "state": state,
                "event_count": proj.get("event_count", 0),
                "last_seen": proj.get("last_seen"),
            }

    # Tier filter (drops nothing for equipment/material/zone, but is the
    # backstop that would hide worker subjects if they ever slipped in).
    return access.filter_subjects(list(rows.values()))


@router.get("/zones")
async def list_zones(
    org: Org = Depends(get_current_org),
    src: SiteStateSource = Depends(get_source),
):
    """Site zones for the entry wizard's "where?" step. Sourced from the
    active project/site definition (not the ledger) so a worker always has
    somewhere to file an entry, even on a brand-new stream."""
    zones = [{"id": z.id, "label": getattr(z, "label", z.id)} for z in src.site.zones]
    return {"zones": zones, "project_id": src.project_id}


@router.get("/assets")
async def list_assets(
    type: str | None = None,
    q: str | None = None,
    org: Org = Depends(get_current_org),
    src: SiteStateSource = Depends(get_source),
    access: RecordAccess = Depends(get_record_access),
    db: AsyncSession = Depends(get_db),
):
    """Material / equipment / zone subjects with their current status, for
    the Assets tab and lookup search."""
    ledger = EventLedger(db)
    rows = await ledger.query(
        org.id, src.project_id,
        statuses=[EventStatusValue.CONFIRMED, EventStatusValue.PROPOSED],
        order="asc", limit=200000,
    )
    assets = _asset_rows(src, rows, access, type)
    if q:
        needle = q.lower()
        assets = [
            a for a in assets
            if needle in a["subject_id"].lower()
            or (a["descriptor"] and needle in a["descriptor"].lower())
        ]
    counts: dict[str, int] = {}
    for a in assets:
        counts[a["subject_type"]] = counts.get(a["subject_type"], 0) + 1
    return {"assets": assets, "counts": counts, "project_id": src.project_id}


@router.get("/assets/{subject_type}/{subject_id}")
async def asset_detail(
    subject_type: str,
    subject_id: str,
    org: Org = Depends(get_current_org),
    src: SiteStateSource = Depends(get_source),
    access: RecordAccess = Depends(get_record_access),
    db: AsyncSession = Depends(get_db),
):
    """Full status for one asset. Worker subjects are blocked here (the
    crew tier never exposes individual workers)."""
    if not access.can_view_subject_type(subject_type):
        raise ApiError(
            403, "forbidden",
            "Your role doesn't have access to individual worker records.",
        )
    ledger = EventLedger(db)
    rows = await ledger.query(
        org.id, src.project_id,
        subject_type=subject_type, subject_id=subject_id,
        order="asc", limit=10000,
    )
    if not rows:
        # No ledger history yet — fall back to the live site definition so a
        # real asset still opens (matches the Assets list behaviour).
        base = _asset_from_site(src, subject_type, subject_id)
        if base is None:
            raise ApiError(404, "entity_not_found", "No record for this asset.")
        return base
    proj = access.redact_entity(entity_projection(subject_type, subject_id, rows))
    if subject_type == SubjectType.MATERIAL.value:
        metrics = proj.get("metrics") or {}
        proj["metrics"] = {
            **metrics,
            "on_hand_qty": round(
                float(metrics.get("delivered_qty", 0.0))
                - float(metrics.get("consumed_qty", 0.0)),
                1,
            ),
        }
    return proj


@router.get("/my-entries")
async def my_entries(
    limit: int = 50,
    org: Org = Depends(get_current_org),
    user: User = Depends(get_current_user),
    src: SiteStateSource = Depends(get_source),
    db: AsyncSession = Depends(get_db),
):
    """My recent submissions, newest-first, with their review status so the
    worker sees their input land (proposed -> confirmed/rejected)."""
    ledger = EventLedger(db)
    rows = await ledger.query(
        org.id, src.project_id, order="desc", limit=2000,
    )
    mine = [event_to_dict(r) for r in rows if r.actor_user_id == user.id]
    return {"entries": mine[: max(1, min(limit, 200))]}


# ── Write (the core loop) ────────────────────────────────────────────


def _build_entry_envelope(
    req: WorkerEntryRequest, *, org_id: str, project_id: str, actor_user_id: str
) -> EventEnvelope:
    """Translate a worker entry into a `proposed` ledger envelope, mirroring
    the kinds `RuleBasedCaptureParser` emits."""
    payload = dict(req.payload or {})
    kind = req.kind

    if kind == "delivery":
        subtype = str(payload.get("subtype") or payload.get("material") or "material")
        subject_type = SubjectType.MATERIAL.value
        subject_id = req.subject_id or f"capture-{subtype}"
        event_kind = EventKind.MATERIAL_DELIVERED.value
        payload.setdefault("subtype", subtype)
    elif kind == "incident":
        subject_type = SubjectType.INCIDENT.value
        subject_id = req.subject_id or _DEFAULT_SUBJECT_ID["incident"]
        event_kind = EventKind.INCIDENT_FLAGGED.value
        payload.setdefault("severity", payload.get("severity", "unknown"))
    elif kind == "inspection":
        failed = str(payload.get("result", "pass")).lower() == "fail"
        subject_type = SubjectType.INSPECTION.value
        subject_id = req.subject_id or _DEFAULT_SUBJECT_ID["inspection"]
        event_kind = (
            EventKind.INSPECTION_FAILED.value if failed
            else EventKind.INSPECTION_PASSED.value
        )
        payload.setdefault("result", "fail" if failed else "pass")
    else:  # note
        subject_type = SubjectType.SITE.value
        subject_id = req.subject_id or _DEFAULT_SUBJECT_ID["note"]
        event_kind = EventKind.NOTE.value

    return EventEnvelope(
        org_id=org_id,
        project_id=project_id,
        subject_type=subject_type,
        subject_id=subject_id,
        kind=event_kind,
        occurred_at=req.occurred_at or _now(),
        payload=payload,
        source="human",
        confidence=0.9,
        status=EventStatusValue.PROPOSED,
        actor_user_id=actor_user_id,
        client_event_id=req.client_event_id,
    )


@router.post("/entry")
async def create_entry(
    req: WorkerEntryRequest,
    org: Org = Depends(get_current_org),
    user: User = Depends(get_current_user),
    access: RecordAccess = Depends(get_record_access),
    src: SiteStateSource = Depends(get_source),
    db: AsyncSession = Depends(get_db),
):
    """Submit one field entry. Always lands as `proposed` for the
    supervisor Inbox. Idempotent on `client_event_id` so the offline
    outbox can replay safely."""
    if not access.can_submit_entry(req.kind):
        raise ApiError(
            400, "unsupported_entry_kind",
            f"{req.kind!r} is not a valid worker entry kind.", field="kind",
        )

    ledger = EventLedger(db)
    existing = await ledger.find_by_client_event_id(
        org.id, src.project_id, req.client_event_id
    )
    if existing is not None:
        # Replay of an already-recorded entry — return it unchanged.
        return event_to_dict(existing)

    env = _build_entry_envelope(
        req, org_id=org.id, project_id=src.project_id, actor_user_id=user.id
    )
    try:
        # SAVEPOINT so a concurrent duplicate (same key) can be caught and
        # resolved without poisoning the request's outer transaction.
        async with db.begin_nested():
            row = await ledger.append(env)
    except IntegrityError:
        existing = await ledger.find_by_client_event_id(
            org.id, src.project_id, req.client_event_id
        )
        if existing is not None:
            return event_to_dict(existing)
        raise

    db.add(AuditEvent(
        id=str(uuid.uuid4()),
        org_id=org.id,
        actor_user_id=user.id,
        kind="worker.entry.created",
        payload={"event_id": row.id, "kind": req.kind, "subject_id": row.subject_id},
    ))
    return event_to_dict(row)
