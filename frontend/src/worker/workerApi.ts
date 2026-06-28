/**
 * Worker PWA API client. Thin typed wrapper over the shared `services/api`
 * fetch helpers (which already attach the session cookie + CSRF header), so
 * the worker app reuses the exact same auth plumbing as the dashboard.
 */
import { getJson, postJson } from '../services/api';

export interface WorkerOverview {
  project_id: string;
  site_name: string;
  sim_day: number;
  today: { deliveries: number; incidents: number; inspections: number };
  my_pending: number;
}

export interface WorkerAsset {
  subject_type: string;
  subject_id: string;
  descriptor: string | null;
  last_state: string | null;
  event_count: number;
  last_seen: string | null;
  pending: number;
  metrics: Record<string, number>;
  state: Record<string, unknown>;
}

export interface AssetsResponse {
  assets: WorkerAsset[];
  counts: Record<string, number>;
  project_id: string;
}

export interface WorkerEvent {
  id: string;
  seq: number;
  occurred_at: string;
  subject_type: string;
  subject_id: string;
  kind: string;
  payload: Record<string, unknown>;
  status: string;
  source: string;
}

export interface EntityDetail {
  subject_type: string;
  subject_id: string;
  event_count: number;
  first_seen: string | null;
  last_seen: string | null;
  kinds: Record<string, number>;
  state: Record<string, unknown>;
  metrics: Record<string, number>;
  events: WorkerEvent[];
}

export type EntryKind = 'delivery' | 'incident' | 'inspection' | 'note';

export interface EntryRequest {
  kind: EntryKind;
  client_event_id: string;
  subject_id?: string | null;
  payload: Record<string, unknown>;
  occurred_at?: string;
}

export interface ZoneOption {
  id: string;
  label: string;
}

export const workerApi = {
  overview: () => getJson<WorkerOverview>('/api/worker/overview'),
  zones: () => getJson<{ zones: ZoneOption[] }>('/api/worker/zones'),
  assets: (type?: string, q?: string) => {
    const qs = new URLSearchParams();
    if (type) qs.set('type', type);
    if (q) qs.set('q', q);
    const tail = qs.toString();
    return getJson<AssetsResponse>(`/api/worker/assets${tail ? `?${tail}` : ''}`);
  },
  asset: (type: string, id: string) =>
    getJson<EntityDetail>(`/api/worker/assets/${encodeURIComponent(type)}/${encodeURIComponent(id)}`),
  myEntries: () => getJson<{ entries: WorkerEvent[] }>('/api/worker/my-entries'),
  submitEntry: (body: EntryRequest) => postJson<WorkerEvent>('/api/worker/entry', body),
};
