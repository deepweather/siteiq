from models.analytics import EquipmentMetrics
from models.assets import EquipmentState
from config import (
    CRANE_HOURLY_RATE, PUMP_HOURLY_RATE, EXCAVATOR_HOURLY_RATE,
    WORKDAY_START, WORKDAY_END,
)

HOURLY_RATES = {
    "tower_crane": CRANE_HOURLY_RATE,
    "concrete_pump": PUMP_HOURLY_RATE,
    "excavator": EXCAVATOR_HOURLY_RATE,
}

WORKDAY_HOURS = (WORKDAY_END - WORKDAY_START) / 3600  # 11 hours


def compute_equipment_utilization(engine) -> list[EquipmentMetrics]:
    results = []
    for asset in engine.assets:
        if asset.type != "equipment":
            continue

        hours_active = asset.metadata.get("hours_active", 0.0)
        hours_idle = asset.metadata.get("hours_idle", 0.0)
        total = hours_active + hours_idle
        utilization = hours_active / total if total > 0.01 else 0.5
        rate = HOURLY_RATES.get(asset.subtype, 200)

        # Normalize to daily: idle_fraction * workday_hours * rate
        idle_fraction = 1.0 - utilization
        daily_idle_cost = idle_fraction * WORKDAY_HOURS * rate

        if asset.state == EquipmentState.REMOVED:
            daily_idle_cost = 0

        results.append(EquipmentMetrics(
            asset_id=asset.id,
            subtype=asset.subtype,
            utilization_rate=round(utilization, 3),
            hours_active=round(hours_active, 2),
            hours_idle=round(hours_idle, 2),
            daily_idle_cost=round(daily_idle_cost, 2),
        ))

    return results
