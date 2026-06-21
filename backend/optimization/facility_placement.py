from math import sqrt
from models.analytics import Recommendation
from state.source import SiteStateSource
from config import LOADED_HOURLY_RATE, WORKER_SPEED, WORKING_DAYS_PER_MONTH


def _distance(x1, y1, x2, y2) -> float:
    return sqrt((x1 - x2) ** 2 + (y1 - y2) ** 2)


def _weighted_centroid(points_weights: list[tuple[float, float, float]]) -> tuple[float, float]:
    """Returns (x, y) weighted centroid. Each entry is (x, y, weight)."""
    total_w = sum(w for _, _, w in points_weights)
    if total_w == 0:
        return 120, 80
    cx = sum(x * w for x, y, w in points_weights) / total_w
    cy = sum(y * w for x, y, w in points_weights) / total_w
    return cx, cy


def optimize_toilet_placement(source: SiteStateSource) -> list[Recommendation]:
    recommendations = []
    toilets = [a for a in source.assets if a.type == "facility" and a.subtype == "toilet"]
    zones = source.site.zones

    zone_data = []
    for z in zones:
        workers = source.workers_in_zone(z.id)
        n = len(workers)
        if n > 0:
            zone_data.append((z.x + z.width / 2, z.y + z.height / 2, float(n)))

    if not zone_data or not toilets:
        return []

    if len(toilets) >= 2:
        # k-means with k=2 to split zones into two clusters
        c1x, c1y = zone_data[0][0], zone_data[0][1]
        c2x, c2y = zone_data[-1][0], zone_data[-1][1]

        for _ in range(20):
            cluster1, cluster2 = [], []
            for zx, zy, w in zone_data:
                d1 = _distance(zx, zy, c1x, c1y)
                d2 = _distance(zx, zy, c2x, c2y)
                if d1 <= d2:
                    cluster1.append((zx, zy, w))
                else:
                    cluster2.append((zx, zy, w))

            if cluster1:
                c1x, c1y = _weighted_centroid(cluster1)
            if cluster2:
                c2x, c2y = _weighted_centroid(cluster2)

        # Clamp to site bounds with margin
        margin = 5
        c1x = max(margin, min(source.site.width - margin, c1x))
        c1y = max(margin, min(source.site.height - margin, c1y))
        c2x = max(margin, min(source.site.width - margin, c2x))
        c2y = max(margin, min(source.site.height - margin, c2y))

        optimal_positions = [(c1x, c1y), (c2x, c2y)]
    else:
        cx, cy = _weighted_centroid(zone_data)
        cx = max(5, min(source.site.width - 5, cx))
        cy = max(5, min(source.site.height - 5, cy))
        optimal_positions = [(cx, cy)]

    # Assign each toilet to its NEAREST optimal position (greedy by closest
    # pair) rather than by enumeration order — otherwise toilet-1 might be
    # sent to the cluster centroid that toilet-2 is already next to.
    remaining_targets = list(optimal_positions)
    toilet_target: dict[str, tuple[float, float]] = {}
    for toilet in sorted(toilets, key=lambda t: t.id):
        if not remaining_targets:
            break
        best_idx = 0
        best_d = float("inf")
        for slot, (tx, ty) in enumerate(remaining_targets):
            d = _distance(toilet.position.x, toilet.position.y, tx, ty)
            if d < best_d:
                best_d = d
                best_idx = slot
        toilet_target[toilet.id] = remaining_targets.pop(best_idx)

    for toilet in toilets:
        if toilet.id not in toilet_target:
            continue
        opt_x, opt_y = toilet_target[toilet.id]
        old_x, old_y = toilet.position.x, toilet.position.y

        improvement = _distance(old_x, old_y, opt_x, opt_y)
        if improvement < 20:
            continue

        # Estimate savings: compute avg distance reduction for all workers
        total_workers = sum(w for _, _, w in zone_data)
        old_avg_dist = sum(
            _distance(zx, zy, old_x, old_y) * w for zx, zy, w in zone_data
        ) / total_workers
        new_avg_dist = sum(
            _distance(zx, zy, opt_x, opt_y) * w for zx, zy, w in zone_data
        ) / total_workers

        dist_saved = old_avg_dist - new_avg_dist
        if dist_saved <= 0:
            continue

        # round trip savings per visit, ~3-4 visits/day per worker
        time_saved_per_trip = (dist_saved * 2) / WORKER_SPEED / 60  # minutes
        trips_per_day = 3.5
        affected_workers = total_workers / len(toilets)
        daily_savings = time_saved_per_trip * trips_per_day * affected_workers * LOADED_HOURLY_RATE / 60

        # Friendly title: "Move Portable Toilet #1 closer to crews"
        num_match = toilet.id.rsplit("-", 1)[-1]
        toilet_label = f"Portable Toilet #{num_match}" if num_match.isdigit() else toilet.id.replace("-", " ").title()
        recommendations.append(Recommendation(
            id=f"opt-{toilet.id}",
            type="move_facility",
            title=f"Move {toilet_label} closer to crews",
            description=f"Relocate to worker-weighted centroid. "
                        f"Cuts the average toilet round-trip by {time_saved_per_trip:.0f} min per visit.",
            target_asset_id=toilet.id,
            from_position={"x": round(old_x, 1), "y": round(old_y, 1)},
            to_position={"x": round(opt_x, 1), "y": round(opt_y, 1)},
            daily_savings=round(daily_savings, 2),
            monthly_savings=round(daily_savings * WORKING_DAYS_PER_MONTH, 2),
        ))

    return recommendations
