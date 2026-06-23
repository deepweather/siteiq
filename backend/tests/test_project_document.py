"""Phase 0 — canonical schema tests.

The `ProjectDocument` is the foundation everything else depends on.
These tests verify:
  - content-hashing is deterministic + collision-sensitive
  - the seed bundle parses
  - validate_document catches the obvious schema violations
"""
from __future__ import annotations

from models.assets import DEFAULT_LEVEL_ID
from models.connection import Connection, ConnectionNode
from models.project_document import (
    EquipmentSpec,
    FacilitySpec,
    MaterialSpec,
    ProjectDocument,
    WorkerSeed,
    validate_document,
)
from models.site import Discipline, Level, Phase, ScheduleEntry, Zone
from seeds.loader import load_all_seed_documents, seed_slugs


def _minimal_doc(**overrides) -> ProjectDocument:
    defaults = dict(
        slug="test-proj",
        name="Test",
        description="d",
        discipline=Discipline.HOCHBAU,
        width=100.0,
        height=100.0,
        levels=[Level(id=DEFAULT_LEVEL_ID, name="EG", elevation_m=0.0, order=0)],
        zones=[Zone(id="z1", label="Z1", x=10, y=10, width=20, height=20,
                    phase=Phase.STRUCTURAL, phase_progress=0.5)],
        worker_seeds=[WorkerSeed(zone_id="z1", trade="general", count=2)],
    )
    defaults.update(overrides)
    return ProjectDocument(**defaults)


def test_content_hash_is_deterministic():
    a = _minimal_doc()
    b = _minimal_doc()
    assert a.content_hash() == b.content_hash()


def test_content_hash_changes_on_edit():
    a = _minimal_doc()
    b = _minimal_doc(name="Edited")
    assert a.content_hash() != b.content_hash()


def test_default_level_is_added_when_omitted():
    # Empty levels list → validator auto-creates the default L0
    doc = _minimal_doc(levels=[])
    assert len(doc.levels) == 1
    assert doc.levels[0].id == DEFAULT_LEVEL_ID


def test_validate_catches_unknown_zone_in_schedule():
    doc = _minimal_doc(schedule=[ScheduleEntry(
        zone_id="ghost", phase=Phase.STRUCTURAL,
        start_day=1, end_day=10, trades_required=[],
    )])
    issues = validate_document(doc)
    codes = {i.code for i in issues}
    assert "unknown_zone" in codes


def test_validate_catches_facility_on_unknown_level():
    doc = _minimal_doc(facilities=[FacilitySpec(
        id="t1", subtype="toilet", x=5, y=5, level_id="L42",
    )])
    issues = validate_document(doc)
    assert any(i.code == "unknown_level" for i in issues)


def test_validate_catches_inverted_schedule():
    doc = _minimal_doc(schedule=[ScheduleEntry(
        zone_id="z1", phase=Phase.STRUCTURAL,
        start_day=50, end_day=10, trades_required=[],
    )])
    issues = validate_document(doc)
    assert any(i.code == "schedule_inverted" for i in issues)


def test_validate_catches_degenerate_connection():
    doc = _minimal_doc(connections=[Connection(
        id="e1", kind="elevator",
        nodes=[ConnectionNode(level_id=DEFAULT_LEVEL_ID, x=10, y=10)],
    )])
    issues = validate_document(doc)
    assert any(i.code == "degenerate_connection" for i in issues)


def test_clean_doc_has_no_errors():
    doc = _minimal_doc()
    errors = [i for i in validate_document(doc) if i.severity == "error"]
    assert errors == []


def test_seed_bundle_parses_and_has_expected_slugs():
    seeds = load_all_seed_documents()
    slugs = seed_slugs()
    assert set(slugs) == set(seeds.keys())
    assert {"westhafen", "europa-quarter", "isar-bridge"} <= set(slugs)


def test_each_seed_validates_clean():
    for slug, doc in load_all_seed_documents().items():
        errors = [i for i in validate_document(doc) if i.severity == "error"]
        assert errors == [], f"{slug} has validation errors: {errors}"


def test_seed_levels_default_to_single_ground_floor():
    """Phase 0 migration: the 3 stock Hochbau seeds have exactly one
    auto-generated ground-floor level. Tiefbau seeds (Phase 5) can have
    additional levels (UG / Grabensohle) so we exempt them here."""
    for slug, doc in load_all_seed_documents().items():
        if doc.discipline.value == "tiefbau":
            # Tiefbau seeds may have UG levels; just verify there's a L0.
            assert any(lv.id == DEFAULT_LEVEL_ID for lv in doc.levels), (
                f"{slug} has no L0 level"
            )
            continue
        assert len(doc.levels) == 1, f"{slug} unexpectedly has {len(doc.levels)} levels"
        assert doc.levels[0].id == DEFAULT_LEVEL_ID, f"{slug} default level isn't L0"


def test_position_defaults_to_l0():
    """Every legacy consumer that builds a Position without level_id
    must still get a valid position on L0."""
    from models.assets import Position
    p = Position(x=10.0, y=20.0)
    assert p.level_id == DEFAULT_LEVEL_ID
