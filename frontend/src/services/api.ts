import type { Site } from '../types/site';
import type { Recommendation } from '../types/analytics';

export const API_BASE = 'http://localhost:8000';
export const WS_BASE = 'ws://localhost:8000';

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`);
  if (!res.ok) {
    throw new Error(`GET ${path} failed: ${res.status} ${res.statusText}`);
  }
  return res.json() as Promise<T>;
}

async function postJson(path: string, body?: unknown): Promise<unknown> {
  const init: RequestInit = { method: 'POST' };
  if (body !== undefined) {
    init.headers = { 'Content-Type': 'application/json' };
    init.body = JSON.stringify(body);
  }
  const res = await fetch(`${API_BASE}${path}`, init);
  if (!res.ok) {
    throw new Error(`POST ${path} failed: ${res.status} ${res.statusText}`);
  }
  try {
    return await res.json();
  } catch {
    return undefined;
  }
}

export interface ProjectSummary {
  id: string;
  name: string;
  description: string;
  type: string;
}

export function fetchProjects(): Promise<ProjectSummary[]> {
  return getJson<ProjectSummary[]>('/api/projects');
}

export async function loadProject(id: string): Promise<void> {
  await postJson(`/api/projects/${id}/load`);
}

export interface PortfolioSite {
  id: string;
  name: string;
  type: string;
  description: string;
  workers: number;
  equipment: number;
  idle_equipment: number;
  zones: number;
  day: number;
  site_width: number;
  site_height: number;
  estimated_monthly_waste: number;
  active: boolean;
}

export function fetchPortfolio(): Promise<PortfolioSite[]> {
  return getJson<PortfolioSite[]>('/api/portfolio');
}

export function fetchSite(): Promise<Site> {
  return getJson<Site>('/api/site');
}

export function fetchRecommendations(): Promise<Recommendation[]> {
  return getJson<Recommendation[]>('/api/recommendations');
}

export async function applyRecommendation(id: string): Promise<void> {
  await postJson(`/api/recommendations/${id}/apply`);
}

export async function applyAllRecommendations(): Promise<void> {
  await postJson('/api/recommendations/apply-all');
}

export async function setSimSpeed(speed: number): Promise<void> {
  await postJson('/api/simulation/speed', { speed });
}

export async function togglePause(): Promise<void> {
  await postJson('/api/simulation/pause');
}

export interface CameraInfo {
  id: string;
  width: number;
  height: number;
  fps: number;
  total_frames: number;
}

export function fetchCameras(): Promise<CameraInfo[]> {
  return getJson<CameraInfo[]>('/api/cameras');
}

/** Cumulative foot-traffic density grid. `cells` entries are
 *  [col, row, normalised_intensity (0..1)]. */
export interface HeatmapData {
  cell_size: number;
  site_width: number;
  site_height: number;
  max_count: number;
  cells: [number, number, number][];
}

export function fetchHeatmap(): Promise<HeatmapData> {
  return getJson<HeatmapData>('/api/simulation/heatmap');
}

export function fetchAssetDetail(id: string): Promise<AssetDetail> {
  return getJson<AssetDetail>(`/api/assets/${id}`);
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
  assigned_zone_label: string | null;
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
    needed_in_zone_label?: string;
    distance_to_zone_m?: number;
  };
}
