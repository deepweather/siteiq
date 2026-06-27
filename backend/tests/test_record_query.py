"""Deterministic query responder over a seeded ledger."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from models.cost import default_rate_card
from models.site_event import EventEnvelope
from services.event_ledger import EventLedger
from services.record_query import DeterministicQueryResponder


async def _seed(session):
    ledger = EventLedger(session)
    await ledger.append_many([
        EventEnvelope(
            org_id="o1", project_id="p1", subject_type="worker", subject_id="w1",
            kind="worker.timesheet",
            occurred_at=datetime(2026, 1, 2, 17, tzinfo=timezone.utc),
            payload={"trade": "carpenter", "hours_total": 10, "worker_id": "w1"},
            source="generator",
        ),
        EventEnvelope(
            org_id="o1", project_id="p1", subject_type="equipment", subject_id="c1",
            kind="equipment.utilization",
            occurred_at=datetime(2026, 1, 2, 17, tzinfo=timezone.utc),
            payload={"subtype": "tower_crane", "hours_idle": 4, "hours_active": 7},
            source="generator",
        ),
        EventEnvelope(
            org_id="o1", project_id="p1", subject_type="material", subject_id="m1",
            kind="material.delivered",
            occurred_at=datetime(2026, 1, 2, 9, tzinfo=timezone.utc),
            payload={"subtype": "rebar", "quantity": 2, "unit": "t"},
            source="generator",
        ),
    ])


@pytest.mark.asyncio
async def test_equipment_intent(ledger_session):
    await _seed(ledger_session)
    r = await DeterministicQueryResponder().answer(
        ledger_session, org_id="o1", project_id="p1",
        question="how many idle crane hours and cost?", rate_card=default_rate_card(),
    )
    assert r.intent == "equipment_idle"
    assert r.data["idle_hours"] == 4
    assert r.data["idle_cost"] == 720.0
    assert r.supporting_event_ids


@pytest.mark.asyncio
async def test_labor_intent(ledger_session):
    await _seed(ledger_session)
    r = await DeterministicQueryResponder().answer(
        ledger_session, org_id="o1", project_id="p1",
        question="how many worker hours?", rate_card=default_rate_card(),
    )
    assert r.intent == "labor"
    assert r.data["total_hours"] == 10
    assert r.data["distinct_workers"] == 1


@pytest.mark.asyncio
async def test_cost_intent(ledger_session):
    await _seed(ledger_session)
    r = await DeterministicQueryResponder().answer(
        ledger_session, org_id="o1", project_id="p1",
        question="what is the total spend?", rate_card=default_rate_card(),
    )
    assert r.intent == "cost"
    assert r.data["total_cost"] == 550.0 + 720.0 + 1900.0


@pytest.mark.asyncio
async def test_fallback_intent(ledger_session):
    await _seed(ledger_session)
    r = await DeterministicQueryResponder().answer(
        ledger_session, org_id="o1", project_id="p1",
        question="hello there", rate_card=default_rate_card(),
    )
    assert r.intent == "summary"
    assert r.data["event_count"] == 3
