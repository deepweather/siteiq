"""Vertical-transport waste analytics.

Captures the cost of workers waiting for / riding elevators. The two
inputs are:
  - per-worker `time_in_vertical_transport` (accumulated by the FSM)
  - per-elevator queue depth (live cab state)

For the demo, the daily cost is `sum(workers' time_in_vertical) *
LOADED_HOURLY_RATE / 3600`. Per-cab metrics let the Phase-4 optimizer
recommend a second cab when one is consistently saturated.
"""
from __future__ import annotations

from dataclasses import dataclass

from config import LOADED_HOURLY_RATE, WORKDAY_END, WORKDAY_START, WORKING_DAYS_PER_MONTH
from state.source import SiteStateSource


@dataclass(frozen=True)
class CabMetrics:
    """Per-elevator-cab snapshot the optimizer + UI consume."""

    connection_id: str
    queued_now: int
    riding_now: int
    capacity: int
    saturation: float  # queued / capacity, capped at 1.0
    longest_wait_s: float


@dataclass(frozen=True)
class VerticalMetrics:
    """Site-wide vertical-transport snapshot."""

    waste_daily: float
    waste_monthly: float
    total_worker_seconds: float
    cabs: list[CabMetrics]


def compute_vertical_metrics(source: SiteStateSource) -> VerticalMetrics:
    """Aggregate per-worker vertical-transport time and convert to €.

    `time_in_vertical_transport` resets daily, so we extrapolate the
    accumulated number to a full day by dividing by the day fraction
    elapsed. This mirrors the approach `analytics/travel.py` already
    uses for partial-day data.
    """
    workday_seconds = max(WORKDAY_END - WORKDAY_START, 1)
    day_fraction = max(min((source.sim_time - WORKDAY_START) / workday_seconds, 1.0), 0.05)

    workers = [a for a in source.assets if a.type == "worker"]
    total_seconds = 0.0
    for w in workers:
        internals = source.worker_internals_for(w.id)
        if internals is None:
            continue
        total_seconds += getattr(internals, "time_in_vertical_transport", 0.0)
    extrapolated_seconds = total_seconds / day_fraction

    waste_daily = (extrapolated_seconds / 3600.0) * LOADED_HOURLY_RATE

    # Per-cab snapshot.
    cabs = []
    cab_map = getattr(source, "cabs", {}) or {}
    for conn_id, cab in cab_map.items():
        queued_now = sum(len(q) for q in cab.queue_per_level.values())
        longest_wait = 0.0
        if cab.queue_enter_time:
            longest_wait = max(
                source.sim_time - t for t in cab.queue_enter_time.values()
            )
        cabs.append(CabMetrics(
            connection_id=conn_id,
            queued_now=queued_now,
            riding_now=len(cab.passengers),
            capacity=cab.capacity,
            saturation=min(queued_now / max(cab.capacity, 1), 1.0),
            longest_wait_s=longest_wait,
        ))

    return VerticalMetrics(
        waste_daily=round(waste_daily, 2),
        waste_monthly=round(waste_daily * WORKING_DAYS_PER_MONTH, 2),
        total_worker_seconds=round(extrapolated_seconds, 1),
        cabs=cabs,
    )
