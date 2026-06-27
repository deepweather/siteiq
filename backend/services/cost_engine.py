"""Cost engine — costs as a projection over the event ledger.

`compute_costs` folds confirmed ledger events against a `RateCard` into a
`CostBreakdown`. There is no separately-maintained cost table: the ledger
is the truth, and every `CostLine` records the event ids that justify it so
the UI can drill from a euro figure straight to the supporting observation.

Event payload contracts consumed here (emitted by the demo generator and
the live simulation drain loop):

- ``worker.timesheet``   {trade, zone_id, hours_total, hours_walking,
                          hours_vertical, ...}
- ``equipment.utilization`` {subtype, hours_idle, hours_active, ...}
- ``material.delivered`` {subtype, quantity, unit_cost?, zone_id, ...}
"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Iterable

from models.cost import (
    CATEGORY_EQUIPMENT_IDLE,
    CATEGORY_LABOR,
    CATEGORY_LABOR_WASTE,
    CATEGORY_MATERIAL,
    CostBreakdown,
    CostGroup,
    CostLine,
    RateCard,
)
from models.site_event import EventKind


def _date_str(value) -> str | None:
    if isinstance(value, datetime):
        return value.date().isoformat()
    return None


def _round(x: float) -> float:
    return round(float(x), 2)


def compute_costs(
    events: Iterable,
    rate_card: RateCard,
    *,
    since: datetime | None = None,
    until: datetime | None = None,
) -> CostBreakdown:
    """Fold confirmed cost-bearing events into a `CostBreakdown`.

    `events` is any iterable of objects exposing `.kind`, `.payload`,
    `.occurred_at`, `.id`, `.status` (ORM `SiteEvent` rows, or stubs in
    tests). Non-confirmed events are skipped — costs reflect ground truth.
    """
    lines: list[CostLine] = []

    for ev in events:
        if getattr(ev, "status", "confirmed") != "confirmed":
            continue
        kind = ev.kind
        payload = ev.payload or {}
        occurred_on = _date_str(getattr(ev, "occurred_at", None))

        if kind == EventKind.WORKER_TIMESHEET.value:
            trade = payload.get("trade")
            rate = rate_card.labor_rate(trade)
            hours_total = float(payload.get("hours_total", 0.0))
            hours_waste = float(payload.get("hours_walking", 0.0)) + float(
                payload.get("hours_vertical", 0.0)
            )
            if hours_total > 0:
                lines.append(CostLine(
                    category=CATEGORY_LABOR,
                    label=f"{trade or 'labour'} — {hours_total:.1f}h",
                    amount=_round(hours_total * rate),
                    occurred_on=occurred_on,
                    zone_id=payload.get("zone_id"),
                    subject_type="worker",
                    subject_id=payload.get("worker_id") or ev.subject_id,
                    supporting_event_ids=[ev.id],
                ))
            if hours_waste > 0:
                # Sub-figure of labour (walking + vertical transport). NOT
                # added to total_cost — shown separately as recoverable.
                lines.append(CostLine(
                    category=CATEGORY_LABOR_WASTE,
                    label=f"{trade or 'labour'} non-productive — {hours_waste:.1f}h",
                    amount=_round(hours_waste * rate),
                    occurred_on=occurred_on,
                    zone_id=payload.get("zone_id"),
                    subject_type="worker",
                    subject_id=payload.get("worker_id") or ev.subject_id,
                    supporting_event_ids=[ev.id],
                ))

        elif kind == EventKind.EQUIPMENT_UTILIZATION.value:
            subtype = payload.get("subtype")
            rate = rate_card.equipment_rate(subtype)
            hours_idle = float(payload.get("hours_idle", 0.0))
            if hours_idle > 0:
                lines.append(CostLine(
                    category=CATEGORY_EQUIPMENT_IDLE,
                    label=f"{subtype or 'equipment'} idle — {hours_idle:.1f}h",
                    amount=_round(hours_idle * rate),
                    occurred_on=occurred_on,
                    zone_id=payload.get("zone_id"),
                    subject_type="equipment",
                    subject_id=payload.get("equipment_id") or ev.subject_id,
                    supporting_event_ids=[ev.id],
                ))

        elif kind == EventKind.MATERIAL_DELIVERED.value:
            subtype = payload.get("subtype")
            quantity = float(payload.get("quantity", 0.0))
            unit_cost = payload.get("unit_cost")
            if unit_cost is None:
                unit_cost = rate_card.material_unit_cost(subtype)
            amount = quantity * float(unit_cost)
            if amount > 0:
                unit = payload.get("unit", "")
                lines.append(CostLine(
                    category=CATEGORY_MATERIAL,
                    label=f"{subtype or 'material'} — {quantity:g}{unit}",
                    amount=_round(amount),
                    occurred_on=occurred_on,
                    zone_id=payload.get("zone_id"),
                    subject_type="material",
                    subject_id=payload.get("material_id") or ev.subject_id,
                    supporting_event_ids=[ev.id],
                ))

    return _aggregate(lines, since=since, until=until)


_CATEGORY_LABELS = {
    CATEGORY_LABOR: "Labour",
    CATEGORY_LABOR_WASTE: "Labour (non-productive)",
    CATEGORY_EQUIPMENT_IDLE: "Equipment idle",
    CATEGORY_MATERIAL: "Materials",
}


def _aggregate(
    lines: list[CostLine],
    *,
    since: datetime | None,
    until: datetime | None,
) -> CostBreakdown:
    labor = sum(l.amount for l in lines if l.category == CATEGORY_LABOR)
    labor_waste = sum(l.amount for l in lines if l.category == CATEGORY_LABOR_WASTE)
    equip = sum(l.amount for l in lines if l.category == CATEGORY_EQUIPMENT_IDLE)
    material = sum(l.amount for l in lines if l.category == CATEGORY_MATERIAL)
    # labor_waste is a subset of labor, so it is excluded from the total.
    total = labor + equip + material

    by_cat: list[CostGroup] = []
    for cat in (CATEGORY_LABOR, CATEGORY_EQUIPMENT_IDLE, CATEGORY_MATERIAL):
        amt = sum(l.amount for l in lines if l.category == cat)
        if amt:
            by_cat.append(CostGroup(key=cat, label=_CATEGORY_LABELS[cat], amount=_round(amt)))

    by_day_map: dict[str, float] = defaultdict(float)
    by_zone_map: dict[str, float] = defaultdict(float)
    for l in lines:
        if l.category == CATEGORY_LABOR_WASTE:
            continue  # don't double-count in day/zone totals
        if l.occurred_on:
            by_day_map[l.occurred_on] += l.amount
        if l.zone_id:
            by_zone_map[l.zone_id] += l.amount

    by_day = [
        CostGroup(key=d, label=d, amount=_round(v))
        for d, v in sorted(by_day_map.items())
    ]
    by_zone = [
        CostGroup(key=z, label=z, amount=_round(v))
        for z, v in sorted(by_zone_map.items(), key=lambda kv: -kv[1])
    ]

    return CostBreakdown(
        since=since.isoformat() if since else None,
        until=until.isoformat() if until else None,
        labor_cost=_round(labor),
        labor_waste_cost=_round(labor_waste),
        equipment_idle_cost=_round(equip),
        material_cost=_round(material),
        total_cost=_round(total),
        by_category=by_cat,
        by_day=by_day,
        by_zone=by_zone,
        lines=lines,
    )
