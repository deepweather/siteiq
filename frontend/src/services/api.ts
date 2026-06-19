import type { Site } from '../types/site';
import type { Recommendation } from '../types/analytics';

const API_BASE = 'http://localhost:8000';

export async function fetchSite(): Promise<Site> {
  const res = await fetch(`${API_BASE}/api/site`);
  return res.json();
}

export async function fetchRecommendations(): Promise<Recommendation[]> {
  const res = await fetch(`${API_BASE}/api/recommendations`);
  return res.json();
}

export async function applyRecommendation(id: string): Promise<void> {
  await fetch(`${API_BASE}/api/recommendations/${id}/apply`, { method: 'POST' });
}

export async function applyAllRecommendations(): Promise<void> {
  await fetch(`${API_BASE}/api/recommendations/apply-all`, { method: 'POST' });
}

export async function setSimSpeed(speed: number): Promise<void> {
  await fetch(`${API_BASE}/api/simulation/speed`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ speed }),
  });
}

export async function togglePause(): Promise<void> {
  await fetch(`${API_BASE}/api/simulation/pause`, { method: 'POST' });
}

export async function fetchAssetDetail(id: string): Promise<AssetDetail> {
  const res = await fetch(`${API_BASE}/api/assets/${id}`);
  return res.json();
}

export interface ActivityLogEntry {
  time: number;
  day: number;
  event: string;
}

export interface AssetDetail {
  id: string;
  type: string;
  subtype: string;
  x: number;
  y: number;
  state: string;
  assigned_zone: string | null;
  trail?: [number, number][];
  activity_log?: ActivityLogEntry[];
  detail?: {
    productivity?: number;
    total_distance_m?: number;
    toilet_trips_today?: number;
    avg_toilet_round_trip_min?: number;
    material_trips_today?: number;
    avg_material_round_trip_min?: number;
    time_working_s?: number;
    time_walking_s?: number;
    time_at_facilities_s?: number;
    utilization?: number;
    hours_active?: number;
    hours_idle?: number;
    daily_idle_cost?: number;
    cycle_timer_s?: number;
    operate_duration_s?: number;
    idle_duration_s?: number;
    workers_present?: { id: string; subtype: string }[];
    needed_in_zone?: string;
    distance_to_zone_m?: number;
  };
}
