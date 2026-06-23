/**
 * Editor-facing project CRUD.
 *
 * The shape mirrors `backend/api/projects.py`. Saves carry an `If-Match`
 * header so two concurrent editors get a clean 409 (mapped to
 * `ApiError.code === "version_conflict"`).
 */
import { API_BASE, ApiError, deleteJson, getJson, postJson, putJson } from './api';

export interface ProjectListItem {
  id: string;
  org_id: string | null;
  slug: string;
  name: string;
  description: string;
  type: string;
  discipline: string;
  visibility: string;
  status: string;
  current_version_id: string | null;
  is_owner: boolean;
  /** True iff this project's current version is the one the org's
   *  simulation is currently pinned to. Drives the "Active" badge
   *  + Activate-button-disabled treatment on the project list. */
  is_active?: boolean;
}

// Pydantic-mirrored canonical document. Re-using the model directly
// avoids transformation pipelines (Jeff-Dean principle #1).
export interface ProjectLevel {
  id: string;
  name: string;
  elevation_m: number;
  order: number;
  background_image_url?: string | null;
}

export interface ProjectConnectionNode {
  level_id: string;
  x: number;
  y: number;
}

export interface ProjectConnection {
  id: string;
  kind: 'stair' | 'elevator';
  nodes: ProjectConnectionNode[];
  cab_capacity?: number;
  cycle_time_s?: number;
  speed_m_per_s?: number;
  seconds_per_level_climb?: number;
}

export interface ProjectZone {
  id: string;
  label: string;
  x: number;
  y: number;
  width: number;
  height: number;
  phase: string;
  phase_progress: number;
  level_id?: string;
}

export interface ProjectFacility {
  id: string;
  subtype: string;
  x: number;
  y: number;
  level_id?: string;
}

export interface ProjectEquipment {
  id: string;
  subtype: string;
  x: number;
  y: number;
  state?: string;
  level_id?: string;
}

export interface ProjectMaterial {
  id: string;
  subtype: string;
  x: number;
  y: number;
  needed_in: string;
  level_id?: string;
}

export interface ProjectScheduleEntry {
  zone_id: string;
  phase: string;
  start_day: number;
  end_day: number;
  trades_required: string[];
}

export interface ProjectWorkerSeed {
  zone_id: string;
  trade: string;
  count: number;
}

export interface ProjectDocument {
  schema_version: number;
  slug: string;
  name: string;
  description: string;
  type: string;
  discipline: string;
  width: number;
  height: number;
  start_day: number;
  levels: ProjectLevel[];
  zones: ProjectZone[];
  facilities: ProjectFacility[];
  equipment: ProjectEquipment[];
  materials: ProjectMaterial[];
  connections: ProjectConnection[];
  schedule: ProjectScheduleEntry[];
  worker_seeds: ProjectWorkerSeed[];
}

export interface ProjectDetail extends ProjectListItem {
  document: ProjectDocument;
}

export interface ValidationIssue {
  code: string;
  severity: 'error' | 'warning';
  message: string;
  field?: string | null;
  asset_id?: string | null;
}

export function listProjects(): Promise<ProjectListItem[]> {
  return getJson<ProjectListItem[]>('/api/projects');
}

export function getProject(id: string): Promise<ProjectDetail> {
  return getJson<ProjectDetail>(`/api/projects/${id}`);
}

export function createProject(
  document: ProjectDocument,
  options: { visibility?: string; message?: string } = {},
): Promise<ProjectDetail> {
  return postJson<ProjectDetail>('/api/projects', {
    document,
    visibility: options.visibility ?? 'private',
    message: options.message ?? 'Initial version',
  });
}

export function saveProject(
  id: string,
  document: ProjectDocument,
  parentVersionId: string | null,
  message: string = '',
): Promise<ProjectDetail> {
  return putJson<ProjectDetail>(
    `/api/projects/${id}`,
    { document, message },
    parentVersionId ? { 'If-Match': parentVersionId } : undefined,
  );
}

export function deleteProject(id: string): Promise<{ status: string }> {
  return deleteJson<{ status: string }>(`/api/projects/${id}`);
}

export function activateProject(
  id: string,
  versionId?: string,
): Promise<{ status: string; project_id: string; version_id: string }> {
  return postJson<{ status: string; project_id: string; version_id: string }>(
    `/api/projects/${id}/activate`,
    versionId ? { version_id: versionId } : {},
  );
}

export function validateProject(
  id: string,
  document: ProjectDocument,
): Promise<{ issues: ValidationIssue[] }> {
  return postJson<{ issues: ValidationIssue[] }>(
    `/api/projects/${id}/validate`,
    { document },
  );
}

// ── Preview Run ──────────────────────────────────────────────────────

export interface PreviewWasteSummary {
  toilet_walk_daily: number;
  toilet_walk_monthly: number;
  material_handling_daily: number;
  material_handling_monthly: number;
  equipment_idle_daily: number;
  equipment_idle_monthly: number;
  vertical_transport_daily: number;
  vertical_transport_monthly: number;
  total_daily: number;
  total_monthly: number;
}

export interface PreviewRecommendation {
  id: string;
  type: string;
  title: string;
  description: string;
  target_asset_id: string;
  daily_savings: number;
  monthly_savings: number;
}

export interface PreviewResponse {
  sim_time: number;
  sim_day: number;
  site: {
    id: string;
    name: string;
    width: number;
    height: number;
    zones: unknown[];
    levels: unknown[];
  };
  assets: { id: string; type: string; subtype: string; x: number; y: number; lvl?: string }[];
  waste: PreviewWasteSummary;
  recommendations: PreviewRecommendation[];
}

export function previewProject(
  id: string,
  document: ProjectDocument,
  ticks?: number,
): Promise<PreviewResponse> {
  const body: { document: ProjectDocument; ticks?: number } = { document };
  if (ticks !== undefined) body.ticks = ticks;
  return postJson<PreviewResponse>(`/api/projects/${id}/preview`, body);
}

// ── Level background image ──────────────────────────────────────────

export interface UploadBackgroundResponse {
  url: string;
  asset_id: string;
  content_hash: string;
  current_version_id: string;
}

/** Upload a level background image. Multipart so it skips the JSON
 *  helpers above. We still re-use the CSRF + cookie machinery from
 *  `services/api.ts` via a one-off fetch. */
export async function uploadLevelBackground(
  projectId: string,
  levelId: string,
  file: File,
  parentVersionId: string | null,
): Promise<UploadBackgroundResponse> {
  // Re-use the same CSRF-fetch flow as mutate(). We call the GET
  // endpoint directly because the helpers don't expose multipart.
  const csrfRes = await fetch(`${API_BASE}/auth/csrf`, { credentials: 'include' });
  if (!csrfRes.ok) throw new ApiError(csrfRes.status, 'csrf_fetch_failed', 'Could not initialise session.');
  const csrfBody = (await csrfRes.json()) as { csrf_token: string };
  const form = new FormData();
  form.append('file', file);
  const headers: Record<string, string> = { 'X-CSRF-Token': csrfBody.csrf_token };
  if (parentVersionId) headers['If-Match'] = parentVersionId;
  const res = await fetch(
    `${API_BASE}/api/projects/${projectId}/levels/${levelId}/background`,
    { method: 'POST', credentials: 'include', body: form, headers },
  );
  if (!res.ok) {
    let payload: { error?: { code?: string; message?: string; field?: string } } = {};
    try { payload = await res.json(); } catch { /* body may not be JSON */ }
    const e = payload?.error ?? {};
    throw new ApiError(res.status, e.code ?? 'http_error', e.message ?? res.statusText, e.field);
  }
  return res.json() as Promise<UploadBackgroundResponse>;
}

export function deleteLevelBackground(
  projectId: string,
  levelId: string,
): Promise<{ status: string; asset_id: string | null }> {
  return deleteJson<{ status: string; asset_id: string | null }>(
    `/api/projects/${projectId}/levels/${levelId}/background`,
  );
}

/** Build a fresh empty project the editor can start from. */
export function blankProjectDocument(slug: string, name: string): ProjectDocument {
  return {
    schema_version: 1,
    slug,
    name,
    description: '',
    type: 'Residential',
    discipline: 'hochbau',
    width: 100,
    height: 80,
    start_day: 1,
    levels: [{ id: 'L0', name: 'EG', elevation_m: 0, order: 0 }],
    zones: [],
    facilities: [],
    equipment: [],
    materials: [],
    connections: [],
    schedule: [],
    worker_seeds: [],
  };
}
