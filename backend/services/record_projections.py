"""Projections — read models folded from the event ledger.

The ledger is the source of truth; current state is always a fold over a
subject's events. These are pure functions over `SiteEvent`-like rows so
they're trivially unit-testable without a database.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime
from typing import Iterable

from models.site_event import EventKind


def event_to_dict(ev) -> dict:
    """Serialise a `SiteEvent` row to the wire shape the API + UI use."""
    occurred = getattr(ev, "occurred_at", None)
    recorded = getattr(ev, "recorded_at", None)
    return {
        "id": ev.id,
        "seq": ev.seq,
        "occurred_at": occurred.isoformat() if isinstance(occurred, datetime) else occurred,
        "recorded_at": recorded.isoformat() if isinstance(recorded, datetime) else recorded,
        "subject_type": ev.subject_type,
        "subject_id": ev.subject_id,
        "kind": ev.kind,
        "payload": ev.payload or {},
        "source": ev.source,
        "confidence": ev.confidence,
        "evidence_ref": ev.evidence_ref,
        "status": ev.status,
        "supersedes_event_id": ev.supersedes_event_id,
        "actor_user_id": ev.actor_user_id,
    }


def _iso(value) -> str | None:
    return value.isoformat() if isinstance(value, datetime) else value


def entity_projection(subject_type: str, subject_id: str, events: list) -> dict:
    """Current state + history for one subject, folded from its events.

    `events` should already be filtered to this subject and ordered by
    `occurred_at` ascending.
    """
    confirmed = [e for e in events if getattr(e, "status", "confirmed") == "confirmed"]
    kinds = Counter(e.kind for e in confirmed)
    first = confirmed[0].occurred_at if confirmed else None
    last = confirmed[-1].occurred_at if confirmed else None

    state: dict = {}
    # Latest non-null payload fields win — a simple last-write fold that
    # gives a usable "current state" for any subject type.
    for e in confirmed:
        for k, v in (e.payload or {}).items():
            if v is not None:
                state[k] = v

    metrics: dict = {}
    if subject_type == "worker":
        metrics["days_logged"] = sum(
            1 for e in confirmed if e.kind == EventKind.WORKER_TIMESHEET.value
        )
        metrics["total_hours"] = round(sum(
            float((e.payload or {}).get("hours_total", 0.0))
            for e in confirmed if e.kind == EventKind.WORKER_TIMESHEET.value
        ), 1)
        metrics["walking_hours"] = round(sum(
            float((e.payload or {}).get("hours_walking", 0.0))
            for e in confirmed if e.kind == EventKind.WORKER_TIMESHEET.value
        ), 1)
    elif subject_type == "equipment":
        metrics["idle_hours"] = round(sum(
            float((e.payload or {}).get("hours_idle", 0.0))
            for e in confirmed if e.kind == EventKind.EQUIPMENT_UTILIZATION.value
        ), 1)
        metrics["active_hours"] = round(sum(
            float((e.payload or {}).get("hours_active", 0.0))
            for e in confirmed if e.kind == EventKind.EQUIPMENT_UTILIZATION.value
        ), 1)
        total = metrics["idle_hours"] + metrics["active_hours"]
        metrics["utilization"] = round(
            metrics["active_hours"] / total, 3
        ) if total > 0 else 0.0
    elif subject_type == "material":
        metrics["delivered_qty"] = round(sum(
            float((e.payload or {}).get("quantity", 0.0))
            for e in confirmed if e.kind == EventKind.MATERIAL_DELIVERED.value
        ), 1)
        metrics["consumed_qty"] = round(sum(
            float((e.payload or {}).get("quantity", 0.0))
            for e in confirmed if e.kind == EventKind.MATERIAL_CONSUMED.value
        ), 1)

    return {
        "subject_type": subject_type,
        "subject_id": subject_id,
        "event_count": len(confirmed),
        "first_seen": _iso(first),
        "last_seen": _iso(last),
        "kinds": dict(kinds),
        "state": state,
        "metrics": metrics,
        "events": [event_to_dict(e) for e in events],
    }


def daily_rollup(events: Iterable) -> list[dict]:
    """Per-day operational summary across a stream (confirmed events only)."""
    by_day: dict[str, dict] = defaultdict(lambda: {
        "deliveries": 0,
        "timesheets": 0,
        "incidents": 0,
        "inspections": 0,
        "equipment_summaries": 0,
        "event_count": 0,
        "workers_active": set(),
    })
    for e in events:
        if getattr(e, "status", "confirmed") != "confirmed":
            continue
        occurred = getattr(e, "occurred_at", None)
        if not isinstance(occurred, datetime):
            continue
        day = occurred.date().isoformat()
        row = by_day[day]
        row["event_count"] += 1
        if e.kind == EventKind.MATERIAL_DELIVERED.value:
            row["deliveries"] += 1
        elif e.kind == EventKind.WORKER_TIMESHEET.value:
            row["timesheets"] += 1
            wid = (e.payload or {}).get("worker_id") or e.subject_id
            row["workers_active"].add(wid)
        elif e.kind == EventKind.INCIDENT_FLAGGED.value:
            row["incidents"] += 1
        elif e.kind in (
            EventKind.INSPECTION_PASSED.value,
            EventKind.INSPECTION_FAILED.value,
        ):
            row["inspections"] += 1
        elif e.kind == EventKind.EQUIPMENT_UTILIZATION.value:
            row["equipment_summaries"] += 1

    out: list[dict] = []
    for day in sorted(by_day.keys()):
        row = by_day[day]
        out.append({
            "date": day,
            "deliveries": row["deliveries"],
            "timesheets": row["timesheets"],
            "incidents": row["incidents"],
            "inspections": row["inspections"],
            "equipment_summaries": row["equipment_summaries"],
            "workers_active": len(row["workers_active"]),
            "event_count": row["event_count"],
        })
    return out
