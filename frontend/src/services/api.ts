import type { Site } from '../types/site';
import type { Recommendation } from '../types/analytics';

// Vite inlines env vars at build time. The Dockerfile lets ops override
// these via --build-arg; locally `npm run dev` falls back to the
// uvicorn default port.
export const API_BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? 'http://localhost:8000';
export const WS_BASE = (import.meta.env.VITE_WS_BASE as string | undefined) ?? 'ws://localhost:8000';

/**
 * Typed error from the API. The backend always returns
 * `{ error: { code, message, field? } }` for non-2xx responses.
 * Forms render `field` errors inline; everything else is a toast.
 */
export class ApiError extends Error {
  status: number;
  code: string;
  field?: string;
  constructor(status: number, code: string, message: string, field?: string) {
    super(message);
    this.status = status;
    this.code = code;
    this.field = field;
  }
}

let csrfToken: string | null = null;

async function ensureCsrf(): Promise<string> {
  if (csrfToken) return csrfToken;
  const res = await fetch(`${API_BASE}/auth/csrf`, { credentials: 'include' });
  if (!res.ok) throw new ApiError(res.status, 'csrf_fetch_failed', 'Could not initialise session.');
  const body = (await res.json()) as { csrf_token: string };
  csrfToken = body.csrf_token;
  return csrfToken;
}

/** Reset the cached CSRF token — used after logout to force a re-fetch. */
export function clearCsrfCache(): void {
  csrfToken = null;
}

async function parseError(res: Response): Promise<ApiError> {
  let payload: { error?: { code?: string; message?: string; field?: string } } = {};
  try { payload = await res.json(); } catch { /* body may not be JSON */ }
  const e = payload?.error ?? {};
  return new ApiError(
    res.status,
    e.code ?? 'http_error',
    e.message ?? `${res.status} ${res.statusText}`,
    e.field,
  );
}

export async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, { credentials: 'include' });
  if (!res.ok) throw await parseError(res);
  return res.json() as Promise<T>;
}

export async function postJson<T = unknown>(path: string, body?: unknown): Promise<T> {
  return mutate<T>('POST', path, body);
}

export async function patchJson<T = unknown>(path: string, body?: unknown): Promise<T> {
  return mutate<T>('PATCH', path, body);
}

export async function deleteJson<T = unknown>(path: string, body?: unknown): Promise<T> {
  return mutate<T>('DELETE', path, body);
}

async function mutate<T>(method: string, path: string, body?: unknown): Promise<T> {
  const csrf = await ensureCsrf();
  const init: RequestInit = {
    method,
    credentials: 'include',
    headers: {
      'X-CSRF-Token': csrf,
      ...(body !== undefined ? { 'Content-Type': 'application/json' } : {}),
    },
  };
  if (body !== undefined) init.body = JSON.stringify(body);
  const res = await fetch(`${API_BASE}${path}`, init);
  if (!res.ok) throw await parseError(res);
  try { return (await res.json()) as T; } catch { return undefined as T; }
}

// ---------------------------------------------------------------------------
// Auth + orgs
// ---------------------------------------------------------------------------

export interface AuthUser {
  id: string;
  email: string;
  name: string;
  email_verified: boolean;
}

export interface AuthOrg {
  id: string;
  name: string;
  slug: string;
  role: 'owner' | 'admin' | 'member' | 'viewer';
  plan: string;
}

export interface MeResponse {
  user: AuthUser | null;
  org: AuthOrg | null;
  memberships: AuthOrg[];
}

export const auth = {
  me: () => getJson<MeResponse>('/auth/me'),
  signup: (body: { email: string; name: string; company: string; password: string }) =>
    postJson<MeResponse>('/auth/signup', body),
  login: (body: { email: string; password: string }) =>
    postJson<MeResponse>('/auth/login', body),
  logout: () => postJson<{ status: string }>('/auth/logout').finally(clearCsrfCache),
  forgotPassword: (email: string) =>
    postJson<{ status: string }>('/auth/forgot-password', { email }),
  requestMagicLink: (email: string) =>
    postJson<{ status: string }>('/auth/request-magic-link', { email }),
  loginWithToken: (token: string) =>
    postJson<MeResponse>('/auth/login-with-token', { token }),
  resetPassword: (token: string, password: string) =>
    postJson<MeResponse>('/auth/reset-password', { token, password }),
  verifyEmail: (token: string) =>
    postJson<{ status: string; email: string }>('/auth/verify-email', { token }),
  resendVerification: () => postJson<{ status: string }>('/auth/resend-verification'),
  changePassword: (current: string, password: string) =>
    postJson<{ status: string }>('/auth/change-password', { current, password }),
  deleteAccount: (currentPassword: string) =>
    postJson<{ status: string; orgs_deleted: string[] }>('/auth/delete-account', {
      current_password: currentPassword,
    }).finally(clearCsrfCache),
  listSessions: () => getJson<SessionRow[]>('/auth/sessions'),
  revokeSession: (id: string) => postJson<{ status: string }>(`/auth/sessions/${id}/revoke`),
  revokeAll: () => postJson<{ status: string; revoked: number }>('/auth/sessions/revoke-all'),
};

export interface SessionRow {
  id: string;
  user_agent: string;
  ip: string;
  created_at: string;
  last_seen_at: string;
  expires_at: string;
  current: boolean;
}

export interface MemberRow {
  user_id: string;
  email: string;
  name: string;
  role: 'owner' | 'admin' | 'member' | 'viewer';
  joined_at: string;
}

export interface InviteRow {
  id: string;
  email: string;
  role: string;
  expires_at: string;
  expired: boolean;
}

export interface AuditEvent {
  id: string;
  kind: string;
  actor_user_id: string | null;
  payload: Record<string, unknown>;
  created_at: string;
}

export const orgs = {
  list: () => getJson<AuthOrg[]>('/api/orgs'),
  switch: (orgId: string) => postJson<{ id: string; name: string }>('/api/orgs/switch', { org_id: orgId }),
  members: () => getJson<MemberRow[]>('/api/orgs/current/members'),
  invites: () => getJson<InviteRow[]>('/api/orgs/current/invites'),
  invite: (email: string, role: 'admin' | 'member' | 'viewer') =>
    postJson<InviteRow>('/api/orgs/current/invites', { email, role }),
  acceptInvite: (token: string) =>
    postJson<{ id: string; name: string }>('/api/orgs/accept-invite', { token }),
  changeRole: (userId: string, role: 'owner' | 'admin' | 'member' | 'viewer') =>
    patchJson<{ status: string }>(`/api/orgs/current/members/${userId}`, { role }),
  removeMember: (userId: string) =>
    deleteJson<{ status: string }>(`/api/orgs/current/members/${userId}`),
  leave: () => postJson<{ status: string }>('/api/orgs/current/leave'),
  audit: () => getJson<AuditEvent[]>('/api/orgs/current/audit'),
  /** URL for the audit-log CSV export. Use with an `<a download>` so
   *  the browser handles the file save with cookies attached. */
  auditCsvUrl: (range?: { since?: string; until?: string }): string => {
    const qs = new URLSearchParams();
    if (range?.since) qs.set('since', range.since);
    if (range?.until) qs.set('until', range.until);
    const tail = qs.toString();
    return `${API_BASE}/api/orgs/current/audit.csv${tail ? `?${tail}` : ''}`;
  },
  deleteCurrent: (confirmName: string, currentPassword: string) =>
    deleteJson<{ status: string; org_id: string }>('/api/orgs/current', {
      confirm_name: confirmName,
      current_password: currentPassword,
    }),
};

// ---------------------------------------------------------------------------
// Existing simulation API
// ---------------------------------------------------------------------------

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
  /** Daily waste from the per-project simulation warm-up. May be 0
   *  if the estimator was skipped at startup (tests). */
  estimated_daily_waste?: number;
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
