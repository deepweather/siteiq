"""Deterministic demo backfill for the system of record.

We don't have a live construction site yet, so this synthesises a realistic
multi-week operational history from the activated `ProjectDocument` and
appends it through the SAME `EventLedger` the live simulation and a future
camera `LiveSource` use. The event *shapes* are identical to what the live
drain loop emits (`worker.timesheet`, `equipment.utilization`,
`equipment.state_changed`), plus the things a running sim doesn't model yet
(deliveries, inspections, incidents, and a few low-confidence camera
detections that land in the confirmation inbox).

Backfill covers the days strictly BEFORE the project's `start_day` (which
the live engine treats as "today"), so history and live emission form one
continuous, non-overlapping timeline. Synthesis is analytic (not a full
simulation run) so it's fast and deterministic: a fixed seed yields the
exact same ledger every time, which the tests assert against.
"""
from __future__ import annotations

import random
from datetime import datetime

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from config import WORKDAY_END, WORKDAY_START
from db.models import SiteEvent
from models.cost import default_rate_card
from models.project_document import ProjectDocument
from models.site_event import EventEnvelope, EventKind
from services.event_ledger import EventLedger, EventStatusValue
from services.sim_calendar import sim_to_datetime


RECORD_BACKFILL_DAYS = 21

# Nominal daily utilization (active fraction of the workday) per equipment
# subtype — mirrors the live duty cycles so backfill and live agree.
_EQUIPMENT_UTILIZATION = {
    "tower_crane": 0.57,
    "concrete_pump": 0.20,
    "excavator": 0.70,
    "sheet_pile": 1.0,
    "dewatering_pump": 0.80,
}

# (min_qty, max_qty, unit) per material subtype for synthesised deliveries.
_MATERIAL_QTY = {
    "rebar": (1.0, 3.0, "t"),
    "concrete": (6.0, 16.0, "m3"),
    "conduit": (50.0, 200.0, "m"),
    "drywall": (20.0, 120.0, "sheet"),
    "pipe": (30.0, 120.0, "m"),
    "aggregate": (5.0, 20.0, "t"),
}
_DEFAULT_QTY = (1.0, 5.0, "unit")

_WORKDAY_HOURS = (WORKDAY_END - WORKDAY_START) / 3600.0


def _seed_for(org_id: str, project_id: str, seed: int | None) -> random.Random:
    if seed is not None:
        return random.Random(seed)
    return random.Random(f"{org_id}:{project_id}")


def _enumerate_workers(doc: ProjectDocument) -> list[tuple[str, str, str]]:
    """Reproduce the engine's worker numbering so backfilled timesheets use
    the same `worker-001..` ids the live simulation does."""
    out: list[tuple[str, str, str]] = []
    n = 1
    for seed in doc.worker_seeds:
        if seed.count <= 0:
            continue
        for _ in range(seed.count):
            out.append((f"worker-{n:03d}", seed.trade, seed.zone_id))
            n += 1
    return out


def build_backfill_envelopes(
    org_id: str,
    document: ProjectDocument,
    *,
    days: int = RECORD_BACKFILL_DAYS,
    seed: int | None = None,
) -> list[EventEnvelope]:
    """Pure builder — returns the envelopes a backfill would append, sorted
    by `occurred_at`. Separated from the DB write so tests can assert on the
    deterministic output directly."""
    project_id = document.slug
    rng = _seed_for(org_id, project_id, seed)
    rate_card = default_rate_card()

    workers = _enumerate_workers(document)
    multilevel = len(document.levels) > 1 and bool(document.connections)
    zone_ids = [z.id for z in document.zones] or ["zone-a"]

    start_day = document.start_day
    first_day = start_day - days
    envelopes: list[EventEnvelope] = []

    def add(
        subject_type: str,
        subject_id: str,
        kind: str,
        occurred_at: datetime,
        payload: dict,
        *,
        source: str = "generator",
        confidence: float = 1.0,
        status: str = EventStatusValue.CONFIRMED,
    ) -> None:
        envelopes.append(EventEnvelope(
            org_id=org_id,
            project_id=project_id,
            subject_type=subject_type,
            subject_id=subject_id,
            kind=kind,
            occurred_at=occurred_at,
            payload=payload,
            source=source,
            confidence=confidence,
            status=status,
        ))

    for offset in range(days):
        day = first_day + offset
        eod = sim_to_datetime(day, WORKDAY_END)

        # ── Worker timesheets ──────────────────────────────────────
        for wid, trade, zone_id in workers:
            worked = rng.uniform(5.5, 8.0)
            walking = rng.uniform(1.8, 3.6)
            facilities = rng.uniform(0.7, 1.3)
            vertical = rng.uniform(0.2, 1.0) if multilevel else 0.0
            total = worked + walking + facilities + vertical
            add(
                "worker", wid, EventKind.WORKER_TIMESHEET.value, eod,
                {
                    "worker_id": wid,
                    "trade": trade,
                    "zone_id": zone_id,
                    "day": day,
                    "hours_worked": round(worked, 2),
                    "hours_walking": round(walking, 2),
                    "hours_facilities": round(facilities, 2),
                    "hours_vertical": round(vertical, 2),
                    "hours_total": round(total, 2),
                },
            )

        # ── Equipment daily utilization + a couple of state changes ─
        for e in document.equipment:
            util = _EQUIPMENT_UTILIZATION.get(e.subtype, 0.5)
            util = max(0.0, min(1.0, util + rng.uniform(-0.08, 0.08)))
            active = round(util * _WORKDAY_HOURS, 2)
            idle = round((1.0 - util) * _WORKDAY_HOURS, 2)
            add(
                "equipment", e.id, EventKind.EQUIPMENT_UTILIZATION.value, eod,
                {
                    "equipment_id": e.id,
                    "subtype": e.subtype,
                    "day": day,
                    "hours_active": active,
                    "hours_idle": idle,
                },
            )
            # A few intraday transitions for timeline texture.
            for _ in range(rng.randint(1, 3)):
                t = rng.uniform(WORKDAY_START, WORKDAY_END)
                add(
                    "equipment", e.id, EventKind.EQUIPMENT_STATE_CHANGED.value,
                    sim_to_datetime(day, t),
                    {
                        "equipment_id": e.id,
                        "subtype": e.subtype,
                        "state": rng.choice(["operating", "idle"]),
                    },
                )

        # ── Deliveries (from the document's materials) ─────────────
        for m in document.materials:
            # Each material is delivered on ~1 in 4 days, spread out.
            if rng.random() > 0.28:
                continue
            lo, hi, unit = _MATERIAL_QTY.get(m.subtype, _DEFAULT_QTY)
            qty = round(rng.uniform(lo, hi), 1)
            t = rng.uniform(WORKDAY_START, WORKDAY_START + 4 * 3600)
            unit_cost = rate_card.material_unit_cost(m.subtype)
            # ~1 in 6 deliveries is a low-confidence camera detection that
            # lands in the confirmation inbox instead of ground truth.
            camera = rng.random() < 0.16
            add(
                "material", m.id, EventKind.MATERIAL_DELIVERED.value,
                sim_to_datetime(day, t),
                {
                    "material_id": m.id,
                    "subtype": m.subtype,
                    "quantity": qty,
                    "unit": unit,
                    "unit_cost": unit_cost,
                    "zone_id": m.needed_in,
                    "lot_id": f"lot-{day}-{m.id}",
                },
                source="camera" if camera else "generator",
                confidence=round(rng.uniform(0.72, 0.9), 2) if camera else 1.0,
                status=EventStatusValue.PROPOSED if camera else EventStatusValue.CONFIRMED,
            )

        # ── Inspections (~ every 5 days) ───────────────────────────
        if offset % 5 == 4:
            zid = rng.choice(zone_ids)
            passed = rng.random() < 0.8
            kind = (
                EventKind.INSPECTION_PASSED.value if passed
                else EventKind.INSPECTION_FAILED.value
            )
            add(
                "inspection", f"insp-{day}", kind,
                sim_to_datetime(day, rng.uniform(WORKDAY_START, WORKDAY_END)),
                {"zone_id": zid, "result": "pass" if passed else "fail"},
            )

        # ── Incidents (rare) ───────────────────────────────────────
        if rng.random() < 0.1:
            zid = rng.choice(zone_ids)
            add(
                "incident", f"inc-{day}", EventKind.INCIDENT_FLAGGED.value,
                sim_to_datetime(day, rng.uniform(WORKDAY_START, WORKDAY_END)),
                {
                    "zone_id": zid,
                    "severity": rng.choice(["low", "medium"]),
                    "note": "Unattended object detected near active zone.",
                },
                source="camera",
                confidence=round(rng.uniform(0.8, 0.95), 2),
            )

    envelopes.sort(key=lambda e: e.occurred_at)
    return envelopes


async def generate_demo_history(
    db: AsyncSession,
    *,
    org_id: str,
    document: ProjectDocument,
    days: int = RECORD_BACKFILL_DAYS,
    seed: int | None = None,
    clear_existing: bool = True,
) -> dict:
    """Synthesise and persist demo history for `(org_id, document.slug)`.

    Idempotent when `clear_existing=True`: wipes the stream first so the seq
    + hash chain restart cleanly. Returns a small summary for the API."""
    project_id = document.slug
    if clear_existing:
        await db.execute(
            delete(SiteEvent).where(
                SiteEvent.org_id == org_id,
                SiteEvent.project_id == project_id,
            )
        )
        await db.flush()

    envelopes = build_backfill_envelopes(
        org_id, document, days=days, seed=seed
    )
    ledger = EventLedger(db)
    rows = await ledger.append_many(envelopes)

    kinds: dict[str, int] = {}
    proposed = 0
    for r in rows:
        kinds[r.kind] = kinds.get(r.kind, 0) + 1
        if r.status == EventStatusValue.PROPOSED:
            proposed += 1
    return {
        "project_id": project_id,
        "days": days,
        "event_count": len(rows),
        "proposed_count": proposed,
        "kinds": kinds,
    }


async def ensure_demo_history(
    db: AsyncSession,
    *,
    org_id: str,
    document: ProjectDocument,
    days: int = RECORD_BACKFILL_DAYS,
) -> dict | None:
    """Backfill demo history for a stream ONLY if it's currently empty.

    Called when an org starts running a project (activate / seed switch) so
    every project the org touches has a populated record from the first view,
    instead of starting at zero and slowly filling via live emission. No-op
    (returns None) when the stream already has events, so it never clobbers
    real/live data."""
    ledger = EventLedger(db)
    if not await ledger.stream_is_empty(org_id, document.slug):
        return None
    return await generate_demo_history(
        db, org_id=org_id, document=document, days=days, clear_existing=False
    )
