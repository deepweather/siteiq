export interface ZoneTravelMetrics {
  zone_id: string;
  num_workers: number;
  avg_toilet_round_trip_min: number;
  avg_toilet_trips_per_day: number;
  daily_toilet_walk_minutes: number;
  daily_toilet_walk_cost: number;
  avg_material_round_trip_min: number;
  daily_material_walk_cost: number;
  productivity_rate: number;
}

export interface EquipmentMetrics {
  asset_id: string;
  subtype: string;
  utilization_rate: number;
  hours_active: number;
  hours_idle: number;
  daily_idle_cost: number;
}

export interface WasteSummary {
  toilet_walk_daily: number;
  toilet_walk_monthly: number;
  material_handling_daily: number;
  material_handling_monthly: number;
  equipment_idle_daily: number;
  equipment_idle_monthly: number;
  total_daily: number;
  total_monthly: number;
  zone_metrics: ZoneTravelMetrics[];
  equipment_metrics: EquipmentMetrics[];
}

export interface Recommendation {
  id: string;
  type: string;
  title: string;
  description: string;
  target_asset_id: string;
  from_position: { x: number; y: number };
  to_position: { x: number; y: number } | null;
  daily_savings: number;
  monthly_savings: number;
  applied: boolean;
}
