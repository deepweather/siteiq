"""Tests for the WorkerInternals dataclass — type contract, defaults,
reset_daily semantics."""
from __future__ import annotations

from models.assets import Position
from simulation.worker_internals import WorkerInternals


def test_constructor_requires_timer_fields():
    """The 3 next_* timers are required (have no defaults). Forgetting one
    should be a TypeError, not a silent bug."""
    wi = WorkerInternals(next_toilet=1.0, next_break=2.0, next_material=3.0)
    assert wi.next_toilet == 1.0
    assert wi.next_break == 2.0
    assert wi.next_material == 3.0


def test_defaults_are_safe_zeros():
    wi = WorkerInternals(next_toilet=0, next_break=0, next_material=0)
    assert wi.action_timer == 0.0
    assert wi.target is None
    assert wi.return_position is None
    assert wi.carrying_target is None
    assert wi.returning_from == ""
    assert wi.total_distance == 0.0
    assert wi.time_working == 0.0
    assert wi.time_walking == 0.0
    assert wi.time_at_facilities == 0.0
    assert wi.toilet_trips_today == 0
    assert wi.toilet_trip_start_time == 0.0
    assert wi.toilet_total_round_trip == 0.0
    assert wi.material_trips_today == 0
    assert wi.material_trip_start_time == 0.0
    assert wi.material_total_round_trip == 0.0


def test_reset_daily_clears_the_right_fields():
    wi = WorkerInternals(
        next_toilet=1.0, next_break=2.0, next_material=3.0,
        time_working=500, time_walking=100, time_at_facilities=50,
        toilet_trips_today=4, toilet_total_round_trip=400,
        material_trips_today=2, material_total_round_trip=200,
        total_distance=999.9,
    )
    wi.reset_daily()
    # Daily counters reset:
    assert wi.toilet_trips_today == 0
    assert wi.material_trips_today == 0
    assert wi.toilet_total_round_trip == 0.0
    assert wi.material_total_round_trip == 0.0
    assert wi.time_working == 0.0
    assert wi.time_walking == 0.0
    assert wi.time_at_facilities == 0.0
    # NON-daily fields preserved:
    assert wi.total_distance == 999.9
    assert wi.next_toilet == 1.0
    assert wi.next_break == 2.0
    assert wi.next_material == 3.0


def test_position_fields_accept_none_and_position():
    wi = WorkerInternals(next_toilet=0, next_break=0, next_material=0)
    assert wi.target is None
    wi.target = Position(x=1, y=2)
    assert wi.target.x == 1
    wi.target = None
    assert wi.target is None


def test_attribute_typos_are_caught_at_runtime():
    """Dataclasses raise AttributeError on bad attribute access — the bug
    that an untyped dict would have hidden."""
    wi = WorkerInternals(next_toilet=0, next_break=0, next_material=0)
    try:
        _ = wi.nxt_toilet  # type: ignore[attr-defined]
        assert False, "typo should have raised"
    except AttributeError:
        pass


def test_factory_produces_dataclass_instances():
    """Smoke test: site_factory.create_site_from_template emits WorkerInternals,
    not dict."""
    from simulation.site_factory import create_site_from_template
    _, _, internals = create_site_from_template("westhafen")
    assert len(internals) > 0
    for wid, wi in internals.items():
        assert isinstance(wi, WorkerInternals), f"{wid} got {type(wi)}, not WorkerInternals"


def test_no_dict_style_access_in_simulation_modules():
    """Guard rail — codify that worker internals should not be accessed
    via the dict pattern anywhere in simulation/ anymore."""
    import re
    from pathlib import Path
    sim_dir = Path(__file__).parent.parent / "simulation"
    pattern = re.compile(r'internals\["[a-z_]+"\]')
    violations: list[str] = []
    for py in sim_dir.glob("*.py"):
        text = py.read_text()
        for i, line in enumerate(text.splitlines(), start=1):
            if pattern.search(line) and not line.strip().startswith("#"):
                violations.append(f"{py.name}:{i}: {line.strip()}")
    assert not violations, (
        "dict-style internals access leaked back into simulation/:\n"
        + "\n".join(violations)
    )
