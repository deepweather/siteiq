from models.analytics import WasteSummary, ZoneShoringCompliance
from analytics.travel import compute_travel_metrics
from analytics.utilization import compute_equipment_utilization
from analytics.vertical_metrics import compute_vertical_metrics
from simulation.tiefbau_behavior import compute_shoring_compliance
from state.source import SiteStateSource
from config import WORKING_DAYS_PER_MONTH


def compute_waste_summary(source: SiteStateSource) -> WasteSummary:
    travel_metrics = compute_travel_metrics(source)
    equipment_metrics = compute_equipment_utilization(source)
    vertical = compute_vertical_metrics(source)
    shoring = compute_shoring_compliance(source)

    toilet_daily = sum(z.daily_toilet_walk_cost for z in travel_metrics)
    material_daily = sum(z.daily_material_walk_cost for z in travel_metrics)
    equipment_daily = sum(e.daily_idle_cost for e in equipment_metrics)
    vertical_daily = vertical.waste_daily

    total_daily = toilet_daily + material_daily + equipment_daily + vertical_daily

    # Map raw shoring entries to the API-facing model, attaching zone
    # labels so the frontend doesn't have to cross-reference site.zones.
    zone_label_by_id = {z.id: z.label for z in source.site.zones}
    shoring_out = [
        ZoneShoringCompliance(
            zone_id=s.zone_id,
            zone_label=zone_label_by_id.get(s.zone_id, s.zone_id),
            compliance=s.compliance,
            nearest_sheet_pile_id=s.nearest_sheet_pile_id,
            nearest_distance_m=(round(s.nearest_distance_m, 1) if s.nearest_distance_m is not None else None),
        )
        for s in shoring
    ]

    return WasteSummary(
        toilet_walk_daily=round(toilet_daily, 2),
        toilet_walk_monthly=round(toilet_daily * WORKING_DAYS_PER_MONTH, 2),
        material_handling_daily=round(material_daily, 2),
        material_handling_monthly=round(material_daily * WORKING_DAYS_PER_MONTH, 2),
        equipment_idle_daily=round(equipment_daily, 2),
        equipment_idle_monthly=round(equipment_daily * WORKING_DAYS_PER_MONTH, 2),
        vertical_transport_daily=round(vertical_daily, 2),
        vertical_transport_monthly=round(vertical_daily * WORKING_DAYS_PER_MONTH, 2),
        total_daily=round(total_daily, 2),
        total_monthly=round(total_daily * WORKING_DAYS_PER_MONTH, 2),
        zone_metrics=travel_metrics,
        equipment_metrics=equipment_metrics,
        shoring_compliance=shoring_out,
    )
