/**
 * System-of-record API client.
 *
 * Mirrors `backend/api/record.py`. The ledger is the operational source of
 * truth; these calls read projections (events, timeline, costs, entities)
 * and drive the human-in-the-loop flows (capture, confirm, reject) plus the
 * demo backfill and conversational query.
 */
import { getJson, postJson } from './api';

export type EventStatus = 'proposed' | 'confirmed' | 'rejected' | 'superseded';
export type EventSource =
  | 'simulation'
  | 'generator'
  | 'human'
  | 'camera'
  | 'sensor'
  | 'integration'
  | 'system';

export interface SiteEventDTO {
  id: string;
  seq: number;
  occurred_at: string;
  recorded_at: string;
  subject_type: string;
  subject_id: string;
  kind: string;
  payload: Record<string, unknown>;
  source: EventSource | string;
  confidence: number;
  evidence_ref: string | null;
  status: EventStatus | string;
  supersedes_event_id: string | null;
  actor_user_id: string | null;
}

export interface DayRollup {
  date: string;
  deliveries: number;
  timesheets: number;
  incidents: number;
  inspections: number;
  equipment_summaries: number;
  workers_active: number;
  event_count: number;
}

export interface EntityProjection {
  subject_type: string;
  subject_id: string;
  event_count: number;
  first_seen: string | null;
  last_seen: string | null;
  kinds: Record<string, number>;
  state: Record<string, unknown>;
  metrics: Record<string, number>;
  events: SiteEventDTO[];
}

export interface CostLine {
  category: string;
  label: string;
  amount: number;
  occurred_on: string | null;
  zone_id: string | null;
  subject_type: string | null;
  subject_id: string | null;
  supporting_event_ids: string[];
}

export interface CostGroup {
  key: string;
  label: string;
  amount: number;
}

export interface CostBreakdown {
  since: string | null;
  until: string | null;
  labor_cost: number;
  labor_waste_cost: number;
  equipment_idle_cost: number;
  material_cost: number;
  total_cost: number;
  by_category: CostGroup[];
  by_day: CostGroup[];
  by_zone: CostGroup[];
  lines: CostLine[];
}

export interface VerifyResult {
  ok: boolean;
  count: number;
  broken_at: number | null;
}

export interface QueryAnswer {
  intent: string;
  answer: string;
  data: Record<string, unknown>;
  supporting_event_ids: string[];
}

export interface DemoSummary {
  project_id: string;
  days: number;
  event_count: number;
  proposed_count: number;
  kinds: Record<string, number>;
}

export interface EventQuery {
  subject_type?: string;
  subject_id?: string;
  kind?: string;
  source?: string;
  status?: string;
  since?: string;
  until?: string;
  order?: 'asc' | 'desc';
  limit?: number;
  offset?: number;
}

function qs(params: Record<string, string | number | undefined>): string {
  const sp = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== '') sp.set(k, String(v));
  }
  const s = sp.toString();
  return s ? `?${s}` : '';
}

export const recordApi = {
  listEvents: (q: EventQuery = {}) =>
    getJson<{ events: SiteEventDTO[]; project_id: string }>(
      `/api/record/events${qs({
        subject_type: q.subject_type,
        subject_id: q.subject_id,
        kind: q.kind,
        source_filter: q.source,
        status: q.status,
        since: q.since,
        until: q.until,
        order: q.order,
        limit: q.limit,
        offset: q.offset,
      })}`,
    ),
  listDays: () => getJson<{ days: DayRollup[]; project_id: string }>('/api/record/days'),
  getTimeline: (date?: string) =>
    getJson<{ date: string | null; events: SiteEventDTO[] }>(
      `/api/record/timeline${qs({ date })}`,
    ),
  getEntity: (subjectType: string, subjectId: string) =>
    getJson<EntityProjection>(
      `/api/record/entities/${encodeURIComponent(subjectType)}/${encodeURIComponent(subjectId)}`,
    ),
  getInbox: () => getJson<{ events: SiteEventDTO[] }>('/api/record/inbox'),
  confirmEvent: (id: string, reason?: string) =>
    postJson<SiteEventDTO>(`/api/record/events/${id}/confirm`, { reason }),
  rejectEvent: (id: string, reason?: string) =>
    postJson<SiteEventDTO>(`/api/record/events/${id}/reject`, { reason }),
  createEvent: (body: {
    subject_type: string;
    subject_id: string;
    kind: string;
    payload?: Record<string, unknown>;
    occurred_at?: string;
    confidence?: number;
    status?: string;
  }) => postJson<SiteEventDTO>('/api/record/events', body),
  getCosts: (since?: string, until?: string) =>
    getJson<CostBreakdown>(`/api/record/costs${qs({ since, until })}`),
  verify: () => getJson<VerifyResult>('/api/record/verify'),
  capture: (text: string, occurredAt?: string) =>
    postJson<{ events: SiteEventDTO[] }>('/api/record/capture', {
      text,
      occurred_at: occurredAt,
    }),
  query: (question: string) =>
    postJson<QueryAnswer>('/api/record/query', { question }),
  generateDemo: (days?: number, seed?: number) =>
    postJson<DemoSummary>('/api/record/demo/generate', { days, seed }),
};
