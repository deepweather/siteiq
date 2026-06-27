"""Rule-based capture parser tests (deterministic, no LLM)."""
from __future__ import annotations

from services.capture import RuleBasedCaptureParser


def _parse(text):
    return RuleBasedCaptureParser().parse(text, org_id="o", project_id="p")


def test_delivery_with_quantity_and_zone():
    evs = _parse("3 tonnes of rebar delivered to zone C")
    assert len(evs) == 1
    e = evs[0]
    assert e.kind == "material.delivered"
    assert e.payload["subtype"] == "rebar"
    assert e.payload["quantity"] == 3.0
    assert e.payload["zone_id"] == "zone-c"
    assert e.status == "proposed"
    assert e.source == "human"


def test_incident():
    e = _parse("near miss in zone B")[0]
    assert e.kind == "incident.flagged"
    assert e.payload["zone_id"] == "zone-b"


def test_inspection_failed():
    e = _parse("inspection failed on zone A")[0]
    assert e.kind == "inspection.failed"


def test_inspection_passed():
    e = _parse("inspection of zone A")[0]
    assert e.kind == "inspection.passed"


def test_fallback_note():
    e = _parse("crane was parked all morning")[0]
    assert e.kind == "note"
    assert e.subject_type == "site"


def test_empty_input_yields_nothing():
    assert _parse("   ") == []


def test_note_preserves_original_text():
    e = _parse("3 tonnes of rebar delivered to zone C")[0]
    assert "rebar" in e.payload["note"]
