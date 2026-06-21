"""WorkerInternals — per-worker FSM + analytics state, typed.

Replaces the previous `dict[str, Any]` access pattern. Attribute access
gives mypy/Pyright + autocomplete, prevents typos that previously caused
silent KeyError → None propagation.

Each worker owns one instance, mutated by `worker_behavior.update_worker()`
and read by `analytics.travel.compute_travel_metrics()` and by the asset
detail builder.
"""
from __future__ import annotations

from dataclasses import dataclass

from models.assets import Position


@dataclass
class WorkerInternals:
    # Countdown timers (sim-seconds remaining until the event fires). Set
    # by the factory at worker creation with a randomised initial delay so
    # not all workers go to the toilet simultaneously.
    next_toilet: float
    next_break: float
    next_material: float

    # Current movement target & "I came from here" anchor for trips
    target: Position | None = None
    return_position: Position | None = None
    carrying_target: Position | None = None

    # Counts-down inside dwell states (AT_TOILET, AT_BREAK, picking up material)
    action_timer: float = 0.0

    # Set to "toilet" or "break" while walking back to work so we know
    # what kind of trip just ended (for analytics).
    returning_from: str = ""

    # Cumulative distance walked since sim start (m)
    total_distance: float = 0.0

    # Per-state time accumulators (sim-seconds, reset daily)
    time_working: float = 0.0
    time_walking: float = 0.0
    time_at_facilities: float = 0.0

    # Toilet trip stats (reset daily)
    toilet_trips_today: int = 0
    toilet_trip_start_time: float = 0.0
    toilet_total_round_trip: float = 0.0

    # Material trip stats (reset daily)
    material_trips_today: int = 0
    material_trip_start_time: float = 0.0
    material_total_round_trip: float = 0.0

    def reset_daily(self) -> None:
        """Clear all per-day counters. Called at the day boundary."""
        self.toilet_trips_today = 0
        self.material_trips_today = 0
        self.toilet_total_round_trip = 0.0
        self.material_total_round_trip = 0.0
        self.time_working = 0.0
        self.time_walking = 0.0
        self.time_at_facilities = 0.0
