"""Recommendations that target the vertical-transport bottleneck.

If any single cab is over-saturated for an extended window we surface
a "Add a second freight elevator at this core" recommendation. The
demo's storyline is "cameras spot the queue, SiteIQ proposes the fix".
The recommendation is informational (`type=add_equipment`) — applying
it doesn't physically conjure a new cab in the simulation. A future
revision could mark the recommendation as applied and reduce the
queue waste by half, but the conservative move for v1 is to surface
the insight rather than auto-mutate the project.
"""
from __future__ import annotations

from analytics.vertical_metrics import compute_vertical_metrics
from config import WORKING_DAYS_PER_MONTH
from models.analytics import Recommendation
from state.source import SiteStateSource


# Saturation level above which we flag a cab as overloaded (instantaneous).
SATURATION_THRESHOLD = 0.6
# Minimum seconds-of-queue-wait observed to consider this worth surfacing.
MIN_LONGEST_WAIT_S = 60.0
# Minimum extrapolated daily waste per cab to surface a "build a
# second cab" rec, even if the queue is empty at this snapshot.
MIN_DAILY_WASTE_PER_CAB = 5.0


def optimize_vertical_transport(source: SiteStateSource) -> list[Recommendation]:
    """Returns a Recommendation per saturated cab.

    Fires on either:
      - instantaneous queue saturation / long wait — captures a cab
        that's actively congested right now, or
      - cumulative daily waste per cab — captures a cab that quietly
        eats hours of worker time over the day without ever showing a
        big queue at any one moment.

    Daily savings is heuristic: assumes a second cab halves the daily
    waste attributable to that cab. We don't have per-cab waste right
    now (the FSM accumulates time on workers, not cabs), so this is
    `vertical_waste_total / num_cabs / 2`.

    Idempotency: once an operator has applied `add_equipment` on a
    cab, the cab's `extra_cab_count` ticks up and we suppress further
    recommendations for it. Without this, a transient
    rec-disappear-then-reappear cycle would let the user double the
    capacity repeatedly (8 → 16 → 32 …) for the same cab.
    """
    metrics = compute_vertical_metrics(source)
    if not metrics.cabs:
        return []
    num_cabs = max(len(metrics.cabs), 1)
    avg_daily_per_cab = metrics.waste_daily / num_cabs

    cab_states = getattr(source, "cabs", {}) or {}

    out: list[Recommendation] = []
    for cab in metrics.cabs:
        live_cab = cab_states.get(cab.connection_id)
        if live_cab is not None and getattr(live_cab, "extra_cab_count", 0) > 0:
            # Already enhanced once — suppress further recs to prevent
            # compounding apply.
            continue
        instant_busy = (
            cab.saturation >= SATURATION_THRESHOLD
            or cab.longest_wait_s >= MIN_LONGEST_WAIT_S
        )
        historically_busy = avg_daily_per_cab >= MIN_DAILY_WASTE_PER_CAB
        if not instant_busy and not historically_busy:
            continue
        daily_savings = avg_daily_per_cab / 2.0
        if daily_savings <= 0:
            continue
        if instant_busy:
            reason = (
                f"at {int(cab.saturation * 100)}% saturation, longest queue "
                f"wait {cab.longest_wait_s / 60:.1f} min"
            )
        else:
            reason = (
                f"costs ~€{avg_daily_per_cab:.0f}/day in worker queue + ride time"
            )
        out.append(Recommendation(
            id=f"opt-vertical-{cab.connection_id}",
            type="add_equipment",
            title=f"Add a second cab next to {cab.connection_id}",
            description=(
                f"{cab.connection_id} {reason}. Adding a parallel cab "
                "splits the queue and roughly halves vertical-transport waste."
            ),
            target_asset_id=cab.connection_id,
            from_position={"x": 0, "y": 0},
            to_position=None,
            daily_savings=round(daily_savings, 2),
            monthly_savings=round(daily_savings * WORKING_DAYS_PER_MONTH, 2),
        ))
    return out
