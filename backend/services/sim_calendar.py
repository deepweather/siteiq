"""Map the simulation clock to calendar timestamps for the ledger.

The simulation tracks `sim_day` (1-based) + `sim_time` (seconds since
midnight, constrained to the workday window). The ledger needs real
`occurred_at` datetimes. This single helper does the mapping so the demo
generator's backfill and the live drain loop produce one continuous,
deterministic timeline. A real camera `LiveSource` would use wall-clock
time and skip this entirely.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from config import RECORD_EPOCH_DATE


def sim_to_datetime(
    sim_day: int, sim_time: float, *, epoch: date | None = None
) -> datetime:
    base = epoch or RECORD_EPOCH_DATE
    start = datetime(base.year, base.month, base.day, tzinfo=timezone.utc)
    return start + timedelta(days=max(sim_day - 1, 0), seconds=float(sim_time))
