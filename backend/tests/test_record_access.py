"""Unit tests for the record visibility policy (RecordAccess)."""
from __future__ import annotations

from models.cost import CostBreakdown, CostLine
from services.record_access import RecordAccess


def _events():
    return [
        {"kind": "worker.timesheet", "subject_type": "worker",
         "payload": {"hours_worked": 8, "hours_facilities": 1, "hours_walking": 2, "hours_total": 11}},
        {"kind": "equipment.utilization", "subject_type": "equipment",
         "payload": {"hours_idle": 3}},
        {"kind": "material.delivered", "subject_type": "material", "payload": {"subtype": "rebar"}},
    ]


def test_tier_flags():
    assert RecordAccess("owner").is_manager
    assert RecordAccess("admin").is_manager
    assert not RecordAccess("member").is_manager
    assert RecordAccess("member").can_see_personal
    assert not RecordAccess("viewer").can_see_personal


def test_viewer_sees_only_operational_events():
    out = RecordAccess("viewer").filter_events(_events())
    kinds = {e["kind"] for e in out}
    assert kinds == {"equipment.utilization", "material.delivered"}


def test_member_sees_worker_events_without_behavioral_fields():
    out = RecordAccess("member").filter_events(_events())
    ts = next(e for e in out if e["kind"] == "worker.timesheet")
    assert "hours_worked" in ts["payload"]
    assert "hours_total" in ts["payload"]
    assert "hours_facilities" not in ts["payload"]
    assert "hours_walking" not in ts["payload"]


def test_manager_sees_everything_unredacted():
    out = RecordAccess("owner").filter_events(_events())
    ts = next(e for e in out if e["kind"] == "worker.timesheet")
    assert ts["payload"]["hours_facilities"] == 1
    assert ts["payload"]["hours_walking"] == 2


def test_filter_subjects_hides_workers_from_viewer():
    subjects = [
        {"subject_type": "worker", "subject_id": "worker-001"},
        {"subject_type": "equipment", "subject_id": "crane-1"},
    ]
    assert [s["subject_type"] for s in RecordAccess("viewer").filter_subjects(subjects)] == ["equipment"]
    assert len(RecordAccess("member").filter_subjects(subjects)) == 2


def test_can_view_subject_type():
    assert not RecordAccess("viewer").can_view_subject_type("worker")
    assert RecordAccess("viewer").can_view_subject_type("equipment")
    assert RecordAccess("member").can_view_subject_type("worker")


def test_redact_entity_strips_behavioral_for_member():
    proj = {
        "subject_type": "worker",
        "metrics": {"total_hours": 100, "walking_hours": 20, "days_logged": 10},
        "state": {"trade": "carpenter", "hours_facilities": 1.2, "hours_walking": 2.5},
        "events": [{"kind": "worker.timesheet", "subject_type": "worker",
                    "payload": {"hours_worked": 8, "hours_walking": 2}}],
    }
    out = RecordAccess("member").redact_entity(proj)
    assert "walking_hours" not in out["metrics"]
    assert "total_hours" in out["metrics"]
    assert "hours_facilities" not in out["state"]
    assert "hours_walking" not in out["events"][0]["payload"]
    # Manager keeps everything.
    full = RecordAccess("owner").redact_entity(proj)
    assert full["metrics"]["walking_hours"] == 20


def test_redact_cost_drops_per_worker_lines_for_non_manager():
    bd = CostBreakdown(
        labor_cost=500, equipment_idle_cost=300, material_cost=200, total_cost=1000,
        lines=[
            CostLine(category="labor", label="carpenter 8h", amount=440,
                     subject_type="worker", subject_id="worker-001", supporting_event_ids=["e1"]),
            CostLine(category="equipment_idle", label="crane idle", amount=300,
                     subject_type="equipment", subject_id="crane-1", supporting_event_ids=["e2"]),
        ],
    )
    out = RecordAccess("member").redact_cost(bd)
    cats = {l.category for l in out.lines}
    assert "labor" not in cats
    assert "equipment_idle" in cats
    # Aggregate totals are untouched.
    assert out.labor_cost == 500
