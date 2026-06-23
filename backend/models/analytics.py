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


class ZoneShoringCompliance(BaseModel):
    """Tiefbau KPI: how well-shored an EXCAVATION zone is.

    `compliance` is 1.0 if a sheet pile sits within the influence
    radius of the zone centre, 0.0 otherwise. Surfaced in the
    WasteReport when any value is < 1.0 ("uncovered cut" alert).
    """

    zone_id: str
    zone_label: str
    compliance: float
    nearest_sheet_pile_id: str | None = None
    nearest_distance_m: float | None = None


class WasteSummary(BaseModel):
    toilet_walk_daily: float
    toilet_walk_monthly: float
    material_handling_daily: float
    material_handling_monthly: float
    equipment_idle_daily: float
    equipment_idle_monthly: float
    # Phase 4: vertical-transport waste (€ spent by workers queueing
    # for or riding elevators). Defaults to 0.0 so single-floor sites
    # behave exactly as before.
    vertical_transport_daily: float = 0.0
    vertical_transport_monthly: float = 0.0
    total_daily: float
    total_monthly: float
    zone_metrics: list[ZoneTravelMetrics]
    equipment_metrics: list[EquipmentMetrics]
    # Phase 5: Tiefbau shoring compliance, per EXCAVATION zone. Empty
    # on Hochbau projects. The frontend renders a warning row when any
    # entry has compliance < 1.0.
    shoring_compliance: list[ZoneShoringCompliance] = []


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
