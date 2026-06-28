/**
 * Device fleet API client. Mirrors backend/api/devices.py (cookie + admin).
 * Ingestion (`/api/ingest/*`) is device-token only and not called from the
 * browser — this client is purely the operator-facing fleet surface.
 */
import { deleteJson, getJson, patchJson, postJson, putJson } from './api';

export type DeviceKind = 'camera' | 'gateway' | 'sensor';
export type DeviceHealth = 'online' | 'offline' | 'never_seen';

export interface DeviceRow {
  id: string;
  name: string;
  kind: DeviceKind | string;
  project_id: string;
  status: 'active' | 'revoked' | string;
  health: DeviceHealth;
  agent_version: string | null;
  queue_depth: number;
  last_seen_at: string | null;
  created_at: string | null;
  capabilities: Record<string, unknown>;
  has_calibration: boolean;
  events_total: number;
  last_event_at: string | null;
}

export interface ClaimResult {
  claim_id: string;
  code: string;
  kind: string;
  name: string;
  project_id: string;
  expires_at: string;
  qr: { code: string; project_id: string; kind: string };
}

export const devicesApi = {
  list: () => getJson<DeviceRow[]>('/api/devices'),
  get: (id: string) => getJson<DeviceRow & { calibration: Record<string, unknown> }>(`/api/devices/${id}`),
  createClaim: (body: { name: string; kind: DeviceKind; project_id?: string }) =>
    postJson<ClaimResult>('/api/devices/claims', body),
  rename: (id: string, name: string) => patchJson<DeviceRow>(`/api/devices/${id}`, { name }),
  revoke: (id: string) => deleteJson<{ status: string }>(`/api/devices/${id}`),
  rotate: (id: string) => postJson<{ status: string; token: string }>(`/api/devices/${id}/rotate`),
  setCalibration: (id: string, calibration: Record<string, unknown>) =>
    putJson<{ status: string }>(`/api/devices/${id}/calibration`, { calibration }),
};
