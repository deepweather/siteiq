from math import sqrt
from models.analytics import Recommendation
from models.assets import Position
from state.source import SiteStateSource
from config import LOADED_HOURLY_RATE, WORKER_SPEED, WORKING_DAYS_PER_MONTH


def _distance(x1, y1, x2, y2) -> float:
    return sqrt((x1 - x2) ** 2 + (y1 - y2) ** 2)


def _path_distance(
    source: SiteStateSource,
    level_id: str,
    x1: float,
    y1: float,
    x2: float,
    y2: float,
) -> float:
    """Path distance via the per-level navmesh; falls back to euclidean."""
    nm = source.navmesh_for_level(level_id) if hasattr(source, "navmesh_for_level") else None
    if nm is None:
        return _distance(x1, y1, x2, y2)
    return nm.distance(
        Position(x=x1, y=y1, level_id=level_id),
        Position(x=x2, y=y2, level_id=level_id),
    )


def _snap_to_walkable(
    source: SiteStateSource,
    level_id: str,
    x: float,
    y: float,
) -> tuple[float, float]:
    nm = source.navmesh_for_level(level_id) if hasattr(source, "navmesh_for_level") else None
    if nm is None:
        return x, y
    snapped = nm.nearest_walkable(x, y)
    return snapped if snapped is not None else (x, y)


def optimize_material_staging(source: SiteStateSource) -> list[Recommendation]:
    recommendations = []

    for asset in source.assets:
        if asset.type != "material":
            continue

        target_zone_id = asset.metadata.get("needed_in_zone")
        if not target_zone_id:
            continue

        zone = source.zone_by_id(target_zone_id)
        if not zone:
            continue

        zx = zone.x + zone.width / 2
        zy = zone.y + zone.height / 2
        level_id = asset.position.level_id
        current_dist = _path_distance(
            source, level_id, asset.position.x, asset.position.y, zx, zy
        )
        if current_dist < 20:
            continue

        # Candidate staging positions along each zone edge, 3m outside the
        # boundary. We pick the candidate closest to the material's existing
        # location so the logistics path from the gate doesn't change — the
        # original implementation always chose the shorter zone dimension,
        # which could move material to the opposite side of the site.
        margin = 3
        candidates = [
            (zone.x - margin, zy),                # left edge
            (zone.x + zone.width + margin, zy),   # right edge
            (zx, zone.y - margin),                # top edge
            (zx, zone.y + zone.height + margin),  # bottom edge
        ]
        best_pos = None
        best_pos_score = float("inf")
        for cx, cy in candidates:
            cx = max(2, min(source.site.width - 2, cx))
            cy = max(2, min(source.site.height - 2, cy))
            # Snap to a walkable cell so we never suggest staging in the
            # crane's swept area or off-site.
            cx, cy = _snap_to_walkable(source, level_id, cx, cy)
            # Score = candidate's distance from where the material is now.
            score = _path_distance(
                source, level_id, asset.position.x, asset.position.y, cx, cy
            )
            if score < best_pos_score:
                best_pos_score = score
                best_pos = (cx, cy)

        if best_pos is None:
            continue

        opt_x, opt_y = best_pos
        # Savings calculation uses worker→zone path-distance (the relevant cost).
        best_new_dist = _path_distance(source, level_id, opt_x, opt_y, zx, zy)
        dist_saved = current_dist - best_new_dist
        if dist_saved < 5:
            continue

        workers_in_zone = len(source.workers_in_zone(target_zone_id))
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
