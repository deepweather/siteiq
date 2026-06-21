from pydantic import BaseModel


class ZoneTravelMetrics(BaseModel):
    zone_id: str
    num_workers: int
    avg_toilet_round_trip_min: float
    avg_toilet_trips_per_day: float
    daily_toilet_walk_minutes: float
    daily_toilet_walk_cost: float
    avg_material_round_trip_min: float
    daily_material_walk_cost: float
    productivity_rate: float


class EquipmentMetrics(BaseModel):
    asset_id: str
    subtype: str
    utilization_rate: float
    hours_active: float
    hours_idle: float
    daily_idle_cost: float


class WasteSummary(BaseModel):
    toilet_walk_daily: float
    toilet_walk_monthly: float
    material_handling_daily: float
    material_handling_monthly: float
    equipment_idle_daily: float
    equipment_idle_monthly: float
    total_daily: float
    total_monthly: float
    zone_metrics: list[ZoneTravelMetrics]
    equipment_metrics: list[EquipmentMetrics]


class PositionXY(BaseModel):
    x: float
    y: float


class Recommendation(BaseModel):
    id: str
    type: str
    title: str
    description: str
    target_asset_id: str
    from_position: PositionXY
    to_position: PositionXY | None = None
    daily_savings: float
    monthly_savings: float
    applied: bool = False
