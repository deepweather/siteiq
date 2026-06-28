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
    assert all(len(line["supporting_event_ids"]) >= 1 for line in costs["lines"])


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


# ── Tiered visibility policy ─────────────────────────────────────────


from contextlib import contextmanager  # noqa: E402


@contextmanager
def _as_role(client, role):
    """Override the record visibility policy to a given role for the block,
    so we can exercise crew/supervisor/manager tiers without inviting extra
    users."""
    from api.record import get_record_access
    from services.record_access import RecordAccess

    client.app.dependency_overrides[get_record_access] = lambda: RecordAccess(role)
    try:
        yield
    finally:
        client.app.dependency_overrides.pop(get_record_access, None)


def test_viewer_cannot_see_workers_in_directory(auth_client):
    _generate(auth_client)
    with _as_role(auth_client, "viewer"):
        body = auth_client.get("/api/record/subjects").json()
    assert all(s["subject_type"] != "worker" for s in body["subjects"])
    assert "worker" not in body["counts"]
    assert any(s["subject_type"] == "equipment" for s in body["subjects"])


def test_viewer_blocked_from_worker_entity(auth_client):
    _generate(auth_client)
    with _as_role(auth_client, "viewer"):
        r = auth_client.get("/api/record/entities/worker/worker-001")
        # Equipment is still fine.
        ok = auth_client.get("/api/record/entities/equipment/crane-1")
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "forbidden"
    assert ok.status_code == 200


def test_viewer_timeline_excludes_worker_events(auth_client):
    _generate(auth_client)
    with _as_role(auth_client, "viewer"):
        ts = auth_client.get("/api/record/events?kind=worker.timesheet&limit=50").json()
        allev = auth_client.get("/api/record/events?limit=500").json()
    assert ts["events"] == []
    assert all(e["subject_type"] != "worker" for e in allev["events"])


def test_viewer_costs_have_no_per_worker_lines_but_keep_totals(auth_client):
    _generate(auth_client)
    with _as_role(auth_client, "viewer"):
        costs = auth_client.get("/api/record/costs").json()
    assert all(line["category"] not in ("labor", "labor_waste") for line in costs["lines"])
    # Aggregate labour total is still reported.
    assert costs["labor_cost"] > 0


def test_member_sees_worker_but_behavioral_redacted(auth_client):
    _generate(auth_client)
    with _as_role(auth_client, "member"):
        proj = auth_client.get("/api/record/entities/worker/worker-001").json()
    assert proj["subject_type"] == "worker"
    assert "total_hours" in proj["metrics"]
    assert "walking_hours" not in proj["metrics"]
    ts = [e for e in proj["events"] if e["kind"] == "worker.timesheet"]
    assert ts and "hours_facilities" not in ts[0]["payload"]
    assert "hours_walking" not in ts[0]["payload"]


def test_switching_project_backfills_empty_record(auth_client):
    # Switching to a fresh seed should auto-populate its record so the
    # directory isn't empty on first view.
    r = auth_client.post("/api/site/load-seed", json={"slug": "europa-quarter"})
    assert r.status_code == 200, r.text
    body = auth_client.get("/api/record/subjects").json()
    assert body["project_id"] == "europa-quarter"
    assert len(body["subjects"]) > 0
    # Idempotent: switching again doesn't duplicate the backfill.
    before = auth_client.get("/api/record/events?limit=1000").json()["events"]
    auth_client.post("/api/site/load-seed", json={"slug": "europa-quarter"})
    after = auth_client.get("/api/record/events?limit=1000").json()["events"]
    assert len(after) == len(before)


def test_manager_sees_full_worker_detail(auth_client):
    _generate(auth_client)
    # Default auth_client is the org owner (manager) — no override.
    proj = auth_client.get("/api/record/entities/worker/worker-001").json()
    assert "walking_hours" in proj["metrics"]
    costs = auth_client.get("/api/record/costs").json()
    assert any(line["category"] == "labor" for line in costs["lines"])
