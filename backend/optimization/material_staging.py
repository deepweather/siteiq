from math import sqrt
from models.analytics import Recommendation
from config import LOADED_HOURLY_RATE, WORKER_SPEED, WORKING_DAYS_PER_MONTH


def _distance(x1, y1, x2, y2) -> float:
    return sqrt((x1 - x2) ** 2 + (y1 - y2) ** 2)


def optimize_material_staging(engine) -> list[Recommendation]:
    recommendations = []

    for asset in engine.assets:
        if asset.type != "material":
            continue

        target_zone_id = asset.metadata.get("needed_in_zone")
        if not target_zone_id:
            continue

        zone = engine.get_zone_by_id(target_zone_id)
        if not zone:
            continue

        zx = zone.x + zone.width / 2
        zy = zone.y + zone.height / 2
        current_dist = _distance(asset.position.x, asset.position.y, zx, zy)
        if current_dist < 20:
            continue

        # Place adjacent to the nearest zone edge, 3m outside boundary
        margin = 3
        candidates = [
            (zone.x - margin, zy),               # left edge
            (zone.x + zone.width + margin, zy),   # right edge
            (zx, zone.y - margin),                # top edge
            (zx, zone.y + zone.height + margin),  # bottom edge
        ]
        best_pos = None
        best_new_dist = float("inf")
        for cx, cy in candidates:
            cx = max(2, min(engine.site.width - 2, cx))
            cy = max(2, min(engine.site.height - 2, cy))
            d = _distance(cx, cy, zx, zy)
            if d < best_new_dist:
                best_new_dist = d
                best_pos = (cx, cy)

        if best_pos is None:
            continue

        opt_x, opt_y = best_pos
        dist_saved = current_dist - best_new_dist
        if dist_saved < 5:
            continue

        workers_in_zone = len(engine.get_workers_in_zone(target_zone_id))
        if workers_in_zone == 0:
            continue

        time_saved_per_trip = (dist_saved * 2) / WORKER_SPEED / 60
        trips_per_day = 2.0 * workers_in_zone
        daily_savings = time_saved_per_trip * trips_per_day * LOADED_HOURLY_RATE / 60

        recommendations.append(Recommendation(
            id=f"opt-{asset.id}",
            type="restage_material",
            title=f"Restage {asset.subtype.title()} near {zone.label}",
            description=f"Move {asset.subtype} from gate area ({current_dist:.0f}m away) to "
                        f"adjacent staging ({best_new_dist:.0f}m). "
                        f"Saves {time_saved_per_trip:.1f} min per material run.",
            target_asset_id=asset.id,
            from_position={"x": round(asset.position.x, 1), "y": round(asset.position.y, 1)},
            to_position={"x": round(opt_x, 1), "y": round(opt_y, 1)},
            daily_savings=round(daily_savings, 2),
            monthly_savings=round(daily_savings * WORKING_DAYS_PER_MONTH, 2),
        ))

    return recommendations
