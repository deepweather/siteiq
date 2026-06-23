from models.analytics import Recommendation
from models.assets import EquipmentState
from state.source import SiteStateSource
from config import (
    CRANE_HOURLY_RATE, PUMP_HOURLY_RATE, EXCAVATOR_HOURLY_RATE,
    WORKING_DAYS_PER_MONTH, WORKDAY_START, WORKDAY_END,
)

HOURLY_RATES = {
    "tower_crane": CRANE_HOURLY_RATE,
    "concrete_pump": PUMP_HOURLY_RATE,
    "excavator": EXCAVATOR_HOURLY_RATE,
}

EQUIPMENT_LABELS = {
    "tower_crane": "Tower Crane",
    "concrete_pump": "Concrete Pump",
    "excavator": "Excavator",
}

WORKDAY_HOURS = (WORKDAY_END - WORKDAY_START) / 3600  # 11h


def _zone_label(source: SiteStateSource, zone_id: str | None) -> str:
    if not zone_id:
        return "its current zone"
    zone = source.zone_by_id(zone_id)
    return zone.label if zone else zone_id


def optimize_equipment(source: SiteStateSource) -> list[Recommendation]:
    recommendations = []

    for asset in source.assets:
        if asset.type != "equipment":
            continue
        if asset.state == EquipmentState.REMOVED:
            continue

        hours_active = asset.metadata.get("hours_active", 0.0)
        hours_idle = asset.metadata.get("hours_idle", 0.0)
        total = hours_active + hours_idle
        utilization = hours_active / total if total > 0.1 else 0.5
        rate = HOURLY_RATES.get(asset.subtype, 200)
        label = EQUIPMENT_LABELS.get(asset.subtype, asset.subtype)
        zone_label = _zone_label(source, asset.assigned_zone)
        # Stable: idle fraction × an 11h workday. Doesn't blow up early in the
        # sim when only a few minutes of activity have been recorded.
        daily_idle_hours = (1.0 - utilization) * WORKDAY_HOURS

        if utilization < 0.40:
            # "Release" — return to rental pool entirely. Eliminates the
            # equipment's idle cost contribution (apply sets state=REMOVED).
            daily_savings = daily_idle_hours * rate * 0.8

            recommendations.append(Recommendation(
                id=f"opt-release-{asset.id}",
                type="release_equipment",
                title=f"Release {label}",
                description=f"{label} at {utilization:.0%} utilization. "
                            f"Return to rental pool — {zone_label} doesn't require "
                            f"continuous operation at this phase.",
                target_asset_id=asset.id,
                from_position={"x": round(asset.position.x, 1), "y": round(asset.position.y, 1)},
                to_position=None,
                daily_savings=round(daily_savings, 2),
                monthly_savings=round(daily_savings * WORKING_DAYS_PER_MONTH, 2),
            ))
        elif utilization < 0.60:
            # "Reschedule" — keep the equipment on site but batch its
            # operations so it idles less. Apply sets `idle_factor=0.4`
            # in metadata; equipment_behavior shrinks the idle half of
            # the duty cycle accordingly.
            daily_savings = daily_idle_hours * rate * 0.3

            recommendations.append(Recommendation(
                id=f"opt-reschedule-{asset.id}",
                type="reschedule_equipment",
                title=f"Reschedule {label} Operations",
                description=f"{label} at {utilization:.0%} utilization. "
                            f"Batch operations to reduce idle gaps between active periods.",
                target_asset_id=asset.id,
                from_position={"x": round(asset.position.x, 1), "y": round(asset.position.y, 1)},
                to_position=None,
                daily_savings=round(daily_savings, 2),
                monthly_savings=round(daily_savings * WORKING_DAYS_PER_MONTH, 2),
            ))

    return recommendations
