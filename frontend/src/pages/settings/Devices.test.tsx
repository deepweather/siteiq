import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { clearCsrfCache } from '../../services/api';
import Devices from './Devices';

const okJson = (body: unknown) =>
  new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } });

const DEVICE = {
  id: 'dev-1',
  name: 'Tower Cam',
  kind: 'camera',
  project_id: 'westhafen',
  status: 'active',
  health: 'online',
  agent_version: '0.1.0',
  queue_depth: 0,
  last_seen_at: new Date().toISOString(),
  created_at: new Date().toISOString(),
  capabilities: {},
  has_calibration: false,
  events_total: 12,
  last_event_at: null,
};

describe('Devices fleet page', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    clearCsrfCache();
  });

  it('lists devices with health and events', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      const url = typeof input === 'string' ? input : (input as Request).url;
      if (url.endsWith('/auth/csrf')) return okJson({ csrf_token: 'c' });
      if (url.endsWith('/api/devices')) return okJson([DEVICE]);
      return okJson({});
    });
    render(<Devices />);
    expect(await screen.findByText('Tower Cam')).toBeInTheDocument();
    expect(screen.getByText(/12 events/)).toBeInTheDocument();
  });

  it('add-device flow surfaces a one-time claim code', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
      const url = typeof input === 'string' ? input : (input as Request).url;
      if (url.endsWith('/auth/csrf')) return okJson({ csrf_token: 'c' });
      if (url.endsWith('/api/devices') && (!init || init.method !== 'POST')) return okJson([]);
      if (url.endsWith('/api/devices/claims')) {
        return okJson({ claim_id: 'c1', code: 'CLAIM-CODE-123', project_id: 'westhafen', kind: 'camera', name: 'Cam', expires_at: new Date().toISOString(), qr: {} });
      }
      return okJson({});
    });
    render(<Devices />);
    fireEvent.click(await screen.findByRole('button', { name: 'Add device' }));
    fireEvent.click(screen.getByRole('button', { name: 'Create claim code' }));
    await waitFor(() => expect(screen.getByText(/CLAIM-CODE-123/)).toBeInTheDocument());
  });
});
