from models.assets import Asset, EquipmentState

EQUIPMENT_DUTY_CYCLES = {
    "tower_crane": {"operate_duration": 2400, "idle_duration": 1800},
    "concrete_pump": {"operate_duration": 600, "idle_duration": 2400},
    "excavator": {"operate_duration": 2520, "idle_duration": 1080},
}


def update_equipment(asset: Asset, dt_sim: float, engine) -> None:
    if asset.state == EquipmentState.REMOVED:
        return

    cycle = EQUIPMENT_DUTY_CYCLES.get(asset.subtype)
    if not cycle:
        return

    meta = asset.metadata
    meta["cycle_timer"] = meta.get("cycle_timer", 0.0) + dt_sim

    if asset.state == EquipmentState.OPERATING:
        meta["hours_active"] = meta.get("hours_active", 0.0) + dt_sim / 3600
        if meta["cycle_timer"] >= cycle["operate_duration"]:
            asset.state = EquipmentState.IDLE
            meta["cycle_timer"] = 0.0
            engine.log_activity(asset.id, "Cycle complete, now idle")
    elif asset.state == EquipmentState.IDLE:
        meta["hours_idle"] = meta.get("hours_idle", 0.0) + dt_sim / 3600
        if meta["cycle_timer"] >= cycle["idle_duration"]:
            asset.state = EquipmentState.OPERATING
            meta["cycle_timer"] = 0.0
            engine.log_activity(asset.id, "Restarted, now operating")
