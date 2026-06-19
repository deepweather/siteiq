from models.analytics import Recommendation
from models.assets import EquipmentState
from config import CRANE_HOURLY_RATE, PUMP_HOURLY_RATE, EXCAVATOR_HOURLY_RATE, WORKING_DAYS_PER_MONTH

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


def optimize_equipment(engine) -> list[Recommendation]:
    recommendations = []

    for asset in engine.assets:
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

        if utilization < 0.40:
            daily_idle_hours = hours_idle * (11.0 / max(total, 0.1))
            daily_savings = daily_idle_hours * rate * 0.8

            recommendations.append(Recommendation(
                id=f"opt-{asset.id}",
                type="reschedule_equipment",
                title=f"Release {label}",
                description=f"{label} at {utilization:.0%} utilization. "
                            f"Return to rental pool — Zone {asset.assigned_zone or 'D'} doesn't require "
                            f"continuous operation at this phase.",
                target_asset_id=asset.id,
                from_position={"x": round(asset.position.x, 1), "y": round(asset.position.y, 1)},
                to_position=None,
                daily_savings=round(daily_savings, 2),
                monthly_savings=round(daily_savings * WORKING_DAYS_PER_MONTH, 2),
            ))
        elif utilization < 0.60:
            daily_idle_hours = hours_idle * (11.0 / max(total, 0.1))
            daily_savings = daily_idle_hours * rate * 0.3

            recommendations.append(Recommendation(
                id=f"opt-{asset.id}",
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
