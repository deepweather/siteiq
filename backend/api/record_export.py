"""Exports for the system of record.

Exports are where the record pays off: cost certification / billing, payroll,
audit + insurance, and fleet reconciliation. Two access rules, both enforced
here:

1. Exporting requires member+ (viewers can glance on-screen but can't pull
   files out — an exfiltration guard; data leaving the system is higher-trust
   than a glance).
2. Every export is redacted by the caller's tier via the SAME `RecordAccess`
   the views use, so an export is never a backdoor around the privacy policy.
   Timesheets (payroll / personal data) are manager-only on top of that.

Streaming RFC 4180 CSV mirrors the existing `/api/orgs/current/audit.csv`
pattern; the frontend links via `<a download>` so the browser saves the file
with the auth cookie attached.
"""
from __future__ import annotations

import csv
import io
import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import (
    get_current_org,
    get_rate_card,
    get_source,
    require_role,
)
from api.record import get_record_access
from auth.errors import ApiError
from db.models import Org, Role
from db.session import get_db
from models.cost import RateCard
from models.site_event import EventKind
from services.cost_engine import compute_costs
from services.event_ledger import EventLedger, EventStatusValue
from services.record_access import RecordAccess
from services.record_projections import event_to_dict
from state.source import SiteStateSource


router = APIRouter(prefix="/api/record/exports", tags=["record-export"])


def _parse_ts(ts: str | None, *, field: str) -> datetime | None:
    if ts is None:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        raise ApiError(400, "invalid_timestamp", f"'{ts}' is not ISO-8601.", field=field)


def _date(value) -> str:
    return value.date().isoformat() if isinstance(value, datetime) else (value or "")


def _csv_response(filename: str, header: list[str], rows):
    """Stream `rows` (iterable of lists) as an RFC 4180 CSV attachment."""
    def _gen():
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(header)
        yield buf.getvalue()
        buf.seek(0); buf.truncate()
        for row in rows:
            w.writerow(row)
            yield buf.getvalue()
            buf.seek(0); buf.truncate()

    return StreamingResponse(
        _gen(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ── Cost report ──────────────────────────────────────────────────────


@router.get("/costs.csv")
async def export_costs_csv(
    since: str | None = None,
    until: str | None = None,
    org: Org = Depends(get_current_org),
    src: SiteStateSource = Depends(get_source),
    access: RecordAccess = Depends(get_record_access),
    rate_card: RateCard = Depends(get_rate_card),
    _=Depends(require_role(Role.MEMBER)),
    db: AsyncSession = Depends(get_db),
):
    """Per-line cost report. Per-worker labour lines are stripped for
    non-managers (tier policy)."""
    s, u = _parse_ts(since, field="since"), _parse_ts(until, field="until")
    ledger = EventLedger(db)
    rows = await ledger.query(
        org.id, src.project_id, statuses=[EventStatusValue.CONFIRMED],
        since=s, until=u, order="asc", limit=200000,
    )
    breakdown = access.redact_cost(compute_costs(rows, rate_card, since=s, until=u))
    out = [
        [
            l.category, l.label, f"{l.amount:.2f}", l.occurred_on or "",
            l.zone_id or "", l.subject_type or "", l.subject_id or "",
            len(l.supporting_event_ids),
        ]
        for l in breakdown.lines
    ]
    return _csv_response(
        f"siteiq-costs-{src.project_id}.csv",
        ["category", "label", "amount_eur", "date", "zone", "subject_type",
         "subject_id", "supporting_events"],
        out,
    )


# ── Event ledger ─────────────────────────────────────────────────────


@router.get("/events.csv")
async def export_events_csv(
    since: str | None = None,
    until: str | None = None,
    kind: str | None = None,
    org: Org = Depends(get_current_org),
    src: SiteStateSource = Depends(get_source),
    access: RecordAccess = Depends(get_record_access),
    _=Depends(require_role(Role.MEMBER)),
    db: AsyncSession = Depends(get_db),
):
    """The ledger as CSV, filtered/redacted to the caller's tier."""
    s, u = _parse_ts(since, field="since"), _parse_ts(until, field="until")
    ledger = EventLedger(db)
    rows = await ledger.query(
        org.id, src.project_id, kinds=[kind] if kind else None,
        since=s, until=u, order="asc", limit=200000,
    )
    events = access.filter_events([event_to_dict(r) for r in rows])
    out = [
        [
            e["seq"], e["occurred_at"], e["recorded_at"], e["subject_type"],
            e["subject_id"], e["kind"], e["source"], e["confidence"], e["status"],
            json.dumps(e["payload"], separators=(",", ":")),
        ]
        for e in events
    ]
    return _csv_response(
        f"siteiq-ledger-{src.project_id}.csv",
        ["seq", "occurred_at", "recorded_at", "subject_type", "subject_id",
         "kind", "source", "confidence", "status", "payload_json"],
        out,
    )


@router.get("/events.json")
async def export_events_json(
    since: str | None = None,
    until: str | None = None,
    org: Org = Depends(get_current_org),
    src: SiteStateSource = Depends(get_source),
    access: RecordAccess = Depends(get_record_access),
    _=Depends(require_role(Role.MEMBER)),
    db: AsyncSession = Depends(get_db),
):
    """Verifiable JSON export: tier-filtered events (with hash chain) plus a
    system integrity attestation over the full stream, so an auditor can
    confirm the record wasn't tampered with."""
    s, u = _parse_ts(since, field="since"), _parse_ts(until, field="until")
    ledger = EventLedger(db)
    rows = await ledger.query(
        org.id, src.project_id, since=s, until=u, order="asc", limit=200000,
    )
    events = access.filter_events([
        {**event_to_dict(r), "prev_hash": r.prev_hash, "hash": r.hash} for r in rows
    ])
    integrity = await ledger.verify_chain(org.id, src.project_id)
    payload = {
        "project_id": src.project_id,
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "tier": "manager" if access.is_manager else ("supervisor" if access.can_see_personal else "crew"),
        "integrity": integrity,
        "event_count": len(events),
        "events": events,
    }
    filename = f"siteiq-ledger-{src.project_id}.json"
    return JSONResponse(
        content=payload,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ── Timesheets (payroll) — managers only ─────────────────────────────


@router.get("/timesheets.csv")
async def export_timesheets_csv(
    since: str | None = None,
    until: str | None = None,
    org: Org = Depends(get_current_org),
    src: SiteStateSource = Depends(get_source),
    rate_card: RateCard = Depends(get_rate_card),
    _=Depends(require_role(Role.ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    """Per-worker timesheets with labour cost. Manager-only (personal data)."""
    s, u = _parse_ts(since, field="since"), _parse_ts(until, field="until")
    ledger = EventLedger(db)
    rows = await ledger.query(
        org.id, src.project_id, kinds=[EventKind.WORKER_TIMESHEET.value],
        statuses=[EventStatusValue.CONFIRMED], since=s, until=u,
        order="asc", limit=200000,
    )
    out = []
    for r in rows:
        p = r.payload or {}
        trade = p.get("trade")
        rate = rate_card.labor_rate(trade)
        total = float(p.get("hours_total", 0.0))
        out.append([
            _date(r.occurred_at), p.get("worker_id") or r.subject_id, trade or "",
            p.get("zone_id") or "", p.get("hours_worked", 0), p.get("hours_walking", 0),
            p.get("hours_facilities", 0), p.get("hours_vertical", 0), total,
            f"{rate:.2f}", f"{total * rate:.2f}",
        ])
    return _csv_response(
        f"siteiq-timesheets-{src.project_id}.csv",
        ["date", "worker_id", "trade", "zone", "hours_worked", "hours_walking",
         "hours_facilities", "hours_vertical", "hours_total", "rate_eur_h",
         "labor_cost_eur"],
        out,
    )


# ── Equipment utilization ────────────────────────────────────────────


@router.get("/equipment.csv")
async def export_equipment_csv(
    since: str | None = None,
    until: str | None = None,
    org: Org = Depends(get_current_org),
    src: SiteStateSource = Depends(get_source),
    rate_card: RateCard = Depends(get_rate_card),
    _=Depends(require_role(Role.MEMBER)),
    db: AsyncSession = Depends(get_db),
):
    """Per-equipment daily utilization + idle cost (operational; member+)."""
    s, u = _parse_ts(since, field="since"), _parse_ts(until, field="until")
    ledger = EventLedger(db)
    rows = await ledger.query(
        org.id, src.project_id, kinds=[EventKind.EQUIPMENT_UTILIZATION.value],
        statuses=[EventStatusValue.CONFIRMED], since=s, until=u,
        order="asc", limit=200000,
    )
    out = []
    for r in rows:
        p = r.payload or {}
        subtype = p.get("subtype")
        rate = rate_card.equipment_rate(subtype)
        active = float(p.get("hours_active", 0.0))
        idle = float(p.get("hours_idle", 0.0))
        util = active / (active + idle) if (active + idle) > 0 else 0.0
        out.append([
            _date(r.occurred_at), p.get("equipment_id") or r.subject_id, subtype or "",
            active, idle, f"{util:.3f}", f"{rate:.2f}", f"{idle * rate:.2f}",
        ])
    return _csv_response(
        f"siteiq-equipment-{src.project_id}.csv",
        ["date", "equipment_id", "subtype", "hours_active", "hours_idle",
         "utilization", "rate_eur_h", "idle_cost_eur"],
        out,
    )
