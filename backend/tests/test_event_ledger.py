"""Unit tests for the event ledger: hash chain, verify, bitemporal status."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from models.site_event import EventEnvelope, EventKind, SubjectType, event_hash
from services.event_ledger import EventLedger, EventStatusValue


@pytest.fixture
def session(ledger_session):
    """Alias the shared in-memory session fixture under a shorter name."""
    return ledger_session


def _env(org="o1", project="p1", seq_kind="worker.timesheet", **payload):
    return EventEnvelope(
        org_id=org,
        project_id=project,
        subject_type="worker",
        subject_id="w1",
        kind=seq_kind,
        occurred_at=datetime(2026, 1, 2, 8, 0, tzinfo=timezone.utc),
        payload=payload or {"hours_total": 8},
        source="generator",
    )


@pytest.mark.asyncio
async def test_append_assigns_gapfree_seq_and_chains_hash(session):
    ledger = EventLedger(session)
    rows = await ledger.append_many([_env(), _env(), _env()])
    assert [r.seq for r in rows] == [1, 2, 3]
    assert rows[0].prev_hash == ""
    assert rows[1].prev_hash == rows[0].hash
    assert rows[2].prev_hash == rows[1].hash
    assert len({r.hash for r in rows}) == 3


@pytest.mark.asyncio
async def test_streams_are_independent(session):
    ledger = EventLedger(session)
    await ledger.append(_env(project="p1"))
    await ledger.append(_env(project="p1"))
    r = await ledger.append(_env(project="p2"))
    # p2 starts its own seq counter at 1.
    assert r.seq == 1


@pytest.mark.asyncio
async def test_verify_chain_ok(session):
    ledger = EventLedger(session)
    await ledger.append_many([_env(), _env(), _env()])
    result = await ledger.verify_chain("o1", "p1")
    assert result == {"ok": True, "count": 3, "broken_at": None}


@pytest.mark.asyncio
async def test_verify_chain_detects_tampering(session):
    ledger = EventLedger(session)
    rows = await ledger.append_many([_env(), _env(), _env()])
    # Tamper with the payload of the 2nd event without re-chaining.
    rows[1].payload = {"hours_total": 999}
    await session.flush()
    result = await ledger.verify_chain("o1", "p1")
    assert result["ok"] is False
    assert result["broken_at"] == 2


@pytest.mark.asyncio
async def test_set_status_appends_companion_and_updates_cache(session):
    ledger = EventLedger(session)
    ev = await ledger.append(EventEnvelope(
        org_id="o1", project_id="p1", subject_type="material", subject_id="m1",
        kind=EventKind.MATERIAL_DELIVERED.value,
        occurred_at=datetime(2026, 1, 2, 8, 0, tzinfo=timezone.utc),
        payload={"subtype": "rebar"}, source="camera", confidence=0.8,
        status=EventStatusValue.PROPOSED,
    ))
    companion = await ledger.set_status(
        ev, new_status=EventStatusValue.CONFIRMED, actor_user_id="u1",
    )
    # Cache updated...
    assert ev.status == EventStatusValue.CONFIRMED
    # ...and a companion event recorded the change, keeping the log the truth.
    assert companion.subject_type == SubjectType.EVENT.value
    assert companion.subject_id == ev.id
    assert companion.kind == EventKind.EVENT_CONFIRMED.value
    # Chain still verifies after the append-only status change.
    result = await ledger.verify_chain("o1", "p1")
    assert result["ok"] is True


@pytest.mark.asyncio
async def test_query_excludes_companion_events_by_default(session):
    ledger = EventLedger(session)
    ev = await ledger.append(EventEnvelope(
        org_id="o1", project_id="p1", subject_type="material", subject_id="m1",
        kind=EventKind.MATERIAL_DELIVERED.value,
        occurred_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
        payload={}, status=EventStatusValue.PROPOSED,
    ))
    await ledger.set_status(ev, new_status=EventStatusValue.REJECTED, actor_user_id="u1")
    visible = await ledger.query("o1", "p1")
    assert all(e.subject_type != SubjectType.EVENT.value for e in visible)
    assert len(visible) == 1


def test_event_hash_changes_with_content():
    base = dict(
        seq=1, occurred_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        subject_type="worker", subject_id="w1", kind="worker.timesheet",
        payload={"h": 8}, source="generator", confidence=1.0,
        supersedes_event_id=None,
    )
    h1 = event_hash("", **base)
    h2 = event_hash("", **{**base, "payload": {"h": 9}})
    assert h1 != h2
