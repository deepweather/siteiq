from models.analytics import WasteSummary
from analytics.travel import compute_travel_metrics
from analytics.utilization import compute_equipment_utilization
from state.source import SiteStateSource
from config import WORKING_DAYS_PER_MONTH


def compute_waste_summary(source: SiteStateSource) -> WasteSummary:
    travel_metrics = compute_travel_metrics(source)
    equipment_metrics = compute_equipment_utilization(source)

    toilet_daily = sum(z.daily_toilet_walk_cost for z in travel_metrics)
    material_daily = sum(z.daily_material_walk_cost for z in travel_metrics)
    equipment_daily = sum(e.daily_idle_cost for e in equipment_metrics)

    return WasteSummary(
        toilet_walk_daily=round(toilet_daily, 2),
        toilet_walk_monthly=round(toilet_daily * WORKING_DAYS_PER_MONTH, 2),
        material_handling_daily=round(material_daily, 2),
        material_handling_monthly=round(material_daily * WORKING_DAYS_PER_MONTH, 2),
        equipment_idle_daily=round(equipment_daily, 2),
        equipment_idle_monthly=round(equipment_daily * WORKING_DAYS_PER_MONTH, 2),
        total_daily=round(toilet_daily + material_daily + equipment_daily, 2),
        total_monthly=round((toilet_daily + material_daily + equipment_daily) * WORKING_DAYS_PER_MONTH, 2),
        zone_metrics=travel_metrics,
        equipment_metrics=equipment_metrics,
    )
