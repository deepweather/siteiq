"""Exports for the system of record + their tiered access enforcement."""
from __future__ import annotations

import csv
import io
from contextlib import contextmanager
from types import SimpleNamespace


def _generate(auth_client, days=6):
    r = auth_client.post("/api/record/demo/generate", json={"days": days, "seed": 7})
    assert r.status_code == 200, r.text
    return r.json()


@contextmanager
def _as_role(client, role):
    """Override the caller's membership role so BOTH require_role gates and
    the RecordAccess redaction (which derive from get_current_membership)
    see the test tier."""
    from api.deps import get_current_membership

    client.app.dependency_overrides[get_current_membership] = lambda: SimpleNamespace(role=role)
    try:
        yield
    finally:
        client.app.dependency_overrides.pop(get_current_membership, None)


def _csv_rows(text):
    return list(csv.reader(io.StringIO(text)))


def test_costs_csv_export(auth_client):
    _generate(auth_client)
    r = auth_client.get("/api/record/exports/costs.csv")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    assert "attachment" in r.headers["content-disposition"]
    rows = _csv_rows(r.text)
    assert rows[0] == [
        "category", "label", "amount_eur", "date", "zone", "subject_type",
        "subject_id", "supporting_events",
    ]
    assert len(rows) > 1


def test_events_csv_and_json_export(auth_client):
    _generate(auth_client)
    csv_resp = auth_client.get("/api/record/exports/events.csv")
    assert csv_resp.status_code == 200
    assert len(_csv_rows(csv_resp.text)) > 1

    js = auth_client.get("/api/record/exports/events.json")
    assert js.status_code == 200
    body = js.json()
    assert body["integrity"]["ok"] is True
    assert body["event_count"] == len(body["events"])
    assert body["tier"] == "manager"
    # JSON rows carry the hash chain for third-party verification.
    assert "hash" in body["events"][0] and "prev_hash" in body["events"][0]


def test_timesheets_export_is_manager_only(auth_client):
    _generate(auth_client)
    # Owner (manager) can.
    ok = auth_client.get("/api/record/exports/timesheets.csv")
    assert ok.status_code == 200
    rows = _csv_rows(ok.text)
    assert "labor_cost_eur" in rows[0]
    assert len(rows) > 1
    # Member cannot (admin+ required).
    with _as_role(auth_client, "member"):
        denied = auth_client.get("/api/record/exports/timesheets.csv")
    assert denied.status_code == 403


def test_equipment_export(auth_client):
    _generate(auth_client)
    r = auth_client.get("/api/record/exports/equipment.csv")
    assert r.status_code == 200
    rows = _csv_rows(r.text)
    assert rows[0][0] == "date" and "idle_cost_eur" in rows[0]


def test_viewer_cannot_export(auth_client):
    _generate(auth_client)
    with _as_role(auth_client, "viewer"):
        costs = auth_client.get("/api/record/exports/costs.csv")
        events = auth_client.get("/api/record/exports/events.csv")
    # require_role(MEMBER) blocks viewers from pulling files out.
    assert costs.status_code == 403
    assert events.status_code == 403


def test_member_cost_export_has_no_per_worker_lines(auth_client):
    _generate(auth_client)
    with _as_role(auth_client, "member"):
        r = auth_client.get("/api/record/exports/costs.csv")
    rows = _csv_rows(r.text)
    categories = {row[0] for row in rows[1:]}
    assert "labor" not in categories
    assert "labor_waste" not in categories


def test_member_events_export_redacts_behavioral_fields(auth_client):
    _generate(auth_client)
    with _as_role(auth_client, "member"):
        r = auth_client.get("/api/record/exports/events.csv")
    rows = _csv_rows(r.text)
    # payload_json is the last column; worker timesheets keep totals but drop
    # toilet/break/movement detail.
    ts_payloads = [row[-1] for row in rows[1:] if row[5] == "worker.timesheet"]
    assert ts_payloads
    assert all("hours_facilities" not in p and "hours_walking" not in p for p in ts_payloads)
    assert any("hours_total" in p for p in ts_payloads)


def test_exports_require_auth(client):
    assert client.get("/api/record/exports/costs.csv").status_code == 401