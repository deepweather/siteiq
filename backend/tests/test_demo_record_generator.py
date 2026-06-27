"""Demo record generator: deterministic, continuous-with-live backfill."""
from __future__ import annotations

from collections import Counter

from seeds.loader import load_all_seed_documents
from services.demo_record_generator import build_backfill_envelopes


def _doc():
    docs = load_all_seed_documents()
    return next(iter(docs.values()))


def test_backfill_is_deterministic():
    doc = _doc()
    a = build_backfill_envelopes("org1", doc, days=14, seed=42)
    b = build_backfill_envelopes("org1", doc, days=14, seed=42)
    assert [e.model_dump() for e in a] == [e.model_dump() for e in b]


def test_backfill_has_expected_volume_and_kinds():
    doc = _doc()
    workers = sum(s.count for s in doc.worker_seeds)
    days = 10
    envs = build_backfill_envelopes("org1", doc, days=days, seed=1)
    kinds = Counter(e.kind for e in envs)
    # One timesheet per worker per day.
    assert kinds["worker.timesheet"] == workers * days
    # One utilization summary per equipment per day.
    assert kinds["equipment.utilization"] == len(doc.equipment) * days


def test_backfill_is_sorted_and_precedes_start_day():
    doc = _doc()
    envs = build_backfill_envelopes("org1", doc, days=7, seed=3)
    times = [e.occurred_at for e in envs]
    assert times == sorted(times)


def test_backfill_emits_some_proposed_for_inbox():
    doc = _doc()
    # Larger window so the ~1-in-6 camera deliveries surface at least one.
    envs = build_backfill_envelopes("org1", doc, days=30, seed=5)
    proposed = [e for e in envs if e.status == "proposed"]
    assert len(proposed) >= 1
    assert all(e.source == "camera" for e in proposed)
