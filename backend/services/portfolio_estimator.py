"""Per-project portfolio waste estimator.

Replaces the legacy `workers * 50 * 0.12 * 22 + equipment * 150 * 0.4 * 11 * 22`
formula with the *actual* `compute_waste_summary` output from each
project template. We spin up a transient `SimulationEngine` per
template, tick it a few hundred times to get past warm-up (so the
analytics see at least one toilet round-trip + one equipment cycle),
then snapshot daily/monthly totals.

The estimate is deterministic for a given template, so we cache it
once per app lifetime in `app.state.portfolio_estimates`.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

from analytics.aggregator import compute_waste_summary
from simulation.engine import SimulationEngine
from simulation.site_factory import PROJECT_TEMPLATES


logger = logging.getLogger("siteiq.portfolio_estimator")


# Enough ticks for the analytics extrapolation to stabilize. Each tick
# is SIM_SECONDS_PER_TICK = 30 sim-seconds, so 240 ticks ~= 2 sim-hours.
WARMUP_TICKS = 240


@dataclass(frozen=True)
class PortfolioEstimate:
    daily_waste: float
    monthly_waste: float
    total_workers: int
    total_equipment: int
    idle_equipment: int
    zones: int
    start_day: int
    site_width: int
    site_height: int


def _estimate_one(project_id: str) -> PortfolioEstimate:
    eng = SimulationEngine(project_id=project_id)
    for _ in range(WARMUP_TICKS):
        eng.tick()
    summary = compute_waste_summary(eng)

    tmpl = PROJECT_TEMPLATES[project_id]
    total_workers = sum(count for zdef in tmpl["zones"] for _, count in zdef["workers"])
    total_equipment = len(tmpl["equipment"])
    idle_equipment = sum(1 for e in tmpl["equipment"] if e["state"] == "idle")
    return PortfolioEstimate(
        daily_waste=round(summary.total_daily, 0),
        monthly_waste=round(summary.total_monthly, 0),
        total_workers=total_workers,
        total_equipment=total_equipment,
        idle_equipment=idle_equipment,
        zones=len(tmpl["zones"]),
        start_day=tmpl["start_day"],
        site_width=tmpl["width"],
        site_height=tmpl["height"],
    )


def compute_all_estimates() -> dict[str, PortfolioEstimate]:
    """Returns one estimate per project template. Called once at app
    startup; cached on `app.state.portfolio_estimates`."""
    out: dict[str, PortfolioEstimate] = {}
    for pid in PROJECT_TEMPLATES.keys():
        try:
            out[pid] = _estimate_one(pid)
            logger.info(
                "portfolio_estimate_computed",
                extra={
                    "project_id": pid,
                    "daily": out[pid].daily_waste,
                    "monthly": out[pid].monthly_waste,
                },
            )
        except Exception:
            logger.exception("portfolio_estimate_failed", extra={"project_id": pid})
    return out
