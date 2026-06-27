"""End-to-end tests for the system-of-record HTTP surface."""
from __future__ import annotations


def _generate(auth_client, days=6):
    r = auth_client.post("/api/record/demo/generate", json={"days": days, "seed": 7})
    assert r.status_code == 200, r.text
    return r.json()


def test_demo_generate_populates_ledger(auth_client):
    summary = _generate(auth_client)
    assert summary["event_count"] > 0
    assert summary["project_id"] == "westhafen"
    assert "worker.timesheet" in summary["kinds"]


def test_demo_generate_is_idempotent(auth_client):
    a = _generate(auth_client, days=5)
    b = _generate(auth_client, days=5)
    # Regenerate clears + rebuilds, so counts match exactly.
    assert a["event_count"] == b["event_count"]
    # And the chain re-verifies after a regenerate (seq restarts cleanly).
    v = auth_client.get("/api/record/verify").json()
    assert v["ok"] is True


def test_events_and_days_and_timeline(auth_client):
    _generate(auth_client)
    days = auth_client.get("/api/record/days").json()["days"]
    assert len(days) > 0
    last_day = days[-1]["date"]

    tl = auth_client.get(f"/api/record/timeline?date={last_day}").json()
    assert tl["date"] == last_day
    assert isinstance(tl["events"], list)

    evs = auth_client.get("/api/record/events?kind=worker.timesheet&limit=5").json()
    assert len(evs["events"]) == 5
    assert all(e["kind"] == "worker.timesheet" for e in evs["events"])


def test_costs_are_positive_and_traceable(auth_client):
    _generate(auth_client)
    costs = auth_client.get("/api/record/costs").json()
    assert costs["total_cost"] > 0
    assert costs["labor_cost"] > 0
    # Every line traces back to at least one supporting event.
    assert all(len(l["supporting_event_ids"]) >= 1 for l in costs["lines"])


def test_verify_detects_intact_chain(auth_client):
    _generate(auth_client)
    v = auth_client.get("/api/record/verify").json()
    assert v["ok"] is True
    assert v["count"] > 0
    assert v["broken_at"] is None


def test_inbox_confirm_flow(auth_client):
    # Capture text -> a proposed event in the inbox -> confirm it.
    r = auth_client.post(
        "/api/record/capture",
        json={"text": "3 tonnes of rebar delivered to zone A"},
    )
    assert r.status_code == 200, r.text
    captured = r.json()["events"]
    assert len(captured) == 1
    ev = captured[0]
    assert ev["status"] == "proposed"
    assert ev["kind"] == "material.delivered"

    inbox = auth_client.get("/api/record/inbox").json()["events"]
    assert any(e["id"] == ev["id"] for e in inbox)

    c = auth_client.post(f"/api/record/events/{ev['id']}/confirm", json={})
    assert c.status_code == 200, c.text
    assert c.json()["status"] == "confirmed"

    # Now gone from the inbox.
    inbox2 = auth_client.get("/api/record/inbox").json()["events"]
    assert all(e["id"] != ev["id"] for e in inbox2)


def test_reject_flow(auth_client):
    r = auth_client.post("/api/record/capture", json={"text": "near miss in zone B"})
    ev = r.json()["events"][0]
    rej = auth_client.post(f"/api/record/events/{ev['id']}/reject", json={"reason": "false alarm"})
    assert rej.status_code == 200
    assert rej.json()["status"] == "rejected"


def test_manual_event_creation(auth_client):
    r = auth_client.post(
        "/api/record/events",
        json={
            "subject_type": "material",
            "subject_id": "mat-x",
            "kind": "material.delivered",
            "payload": {"subtype": "concrete", "quantity": 8, "unit": "m3", "zone_id": "zone-a"},
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["source"] == "human"
    assert r.json()["status"] == "confirmed"


def test_query_intents(auth_client):
    _generate(auth_client)
    for q, intent in [
        ("how many idle equipment hours and what did they cost?", "equipment_idle"),
        ("how many deliveries?", "deliveries"),
        ("how many worker hours were logged?", "labor"),
        ("what is the total cost?", "cost"),
    ]:
        r = auth_client.post("/api/record/query", json={"question": q})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["intent"] == intent
        assert isinstance(body["answer"], str) and body["answer"]


def test_entity_projection(auth_client):
    _generate(auth_client)
    proj = auth_client.get("/api/record/entities/worker/worker-001").json()
    assert proj["subject_type"] == "worker"
    assert proj["event_count"] > 0
    assert "total_hours" in proj["metrics"]


def test_subjects_directory(auth_client):
    _generate(auth_client)
    body = auth_client.get("/api/record/subjects").json()
    subjects = body["subjects"]
    assert len(subjects) > 0
    # Westhafen has 50 workers.
    workers = [s for s in subjects if s["subject_type"] == "worker"]
    assert body["counts"]["worker"] == len(workers) == 50
    assert any(s["subject_type"] == "equipment" for s in subjects)
    w = workers[0]
    assert w["descriptor"]  # trade
    assert w["event_count"] > 0


def test_subjects_filter_by_type_and_query(auth_client):
    _generate(auth_client)
    only_equipment = auth_client.get("/api/record/subjects?type=equipment").json()
    assert only_equipment["subjects"]
    assert all(s["subject_type"] == "equipment" for s in only_equipment["subjects"])

    one = auth_client.get("/api/record/subjects?q=worker-001").json()["subjects"]
    assert any(s["subject_id"] == "worker-001" for s in one)


def test_record_routes_require_auth(client):
    # No session -> 401 envelope.
    r = client.get("/api/record/events")
    assert r.status_code == 401
    assert r.json()["error"]["code"] == "not_authenticated"
