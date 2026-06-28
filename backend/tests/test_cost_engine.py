"""Cost engine: folds events against the rate card with traceability."""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace as NS

from models.cost import default_rate_card
from services.cost_engine import compute_costs


def _ev(kind, payload, *, status="confirmed", eid="e", day=2):
    return NS(
        id=eid, seq=1, status=status, kind=kind,
        subject_type="x", subject_id="x",
        occurred_at=datetime(2026, 1, day, tzinfo=timezone.utc),
        recorded_at=datetime(2026, 1, day, tzinfo=timezone.utc),
        payload=payload,
    )


def test_labor_equipment_material_costs():
    rc = default_rate_card()
    events = [
        _ev("worker.timesheet", {
            "trade": "carpenter", "zone_id": "A", "hours_total": 10,
            "hours_walking": 2, "hours_vertical": 0.5, "worker_id": "w1",
        }, eid="e1"),
        _ev("equipment.utilization", {
            "subtype": "tower_crane", "hours_idle": 4, "hours_active": 7,
            "equipment_id": "c1",
        }, eid="e2"),
        _ev("material.delivered", {
            "subtype": "rebar", "quantity": 2, "unit": "t", "zone_id": "A",
            "material_id": "m1",
        }, eid="e3"),
    ]
    b = compute_costs(events, rc)
    assert b.labor_cost == 550.0          # 10h * 55
    assert b.labor_waste_cost == 137.5    # 2.5h * 55
    assert b.equipment_idle_cost == 720.0  # 4h * 180
    assert b.material_cost == 1900.0       # 2t * 950
    # labor_waste excluded from total.
    assert b.total_cost == 550.0 + 720.0 + 1900.0


def test_lines_carry_supporting_event_ids():
    rc = default_rate_card()
    b = compute_costs([
        _ev("material.delivered", {"subtype": "concrete", "quantity": 5, "unit": "m3"}, eid="ev-x"),
    ], rc)
    assert b.lines
    assert all(line.supporting_event_ids for line in b.lines)
    assert b.lines[0].supporting_event_ids == ["ev-x"]


def test_proposed_events_are_excluded():
    rc = default_rate_card()
    b = compute_costs([
        _ev("material.delivered", {"subtype": "rebar", "quantity": 2}, status="proposed"),
    ], rc)
    assert b.material_cost == 0.0
    assert b.total_cost == 0.0


def test_explicit_unit_cost_overrides_rate_card():
    rc = default_rate_card()
    b = compute_costs([
        _ev("material.delivered", {"subtype": "rebar", "quantity": 1, "unit_cost": 100.0}),
    ], rc)
    assert b.material_cost == 100.0
