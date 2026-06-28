import { describe, it, expect, beforeEach, vi } from 'vitest';
import { API_BASE, clearCsrfCache } from './api';
import { devicesApi } from './devicesApi';

const okJson = (body: unknown) =>
  new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  });

function mockFetch(handler: (url: string, init?: RequestInit) => Response) {
  return vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const url = typeof input === 'string' ? input : (input as Request).url;
    if (url.endsWith('/auth/csrf')) return okJson({ csrf_token: 'csrf-d' });
    return handler(url, init as RequestInit | undefined);
  });
}

describe('devicesApi', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    clearCsrfCache();
  });

  it('list GETs the fleet', async () => {
    const spy = mockFetch(() => okJson([]));
    await devicesApi.list();
    expect(spy.mock.calls.at(-1)![0]).toBe(`${API_BASE}/api/devices`);
  });

  it('createClaim POSTs name + kind with CSRF', async () => {
    const spy = mockFetch(() => okJson({ claim_id: 'c', code: 'XYZ', project_id: 'p', kind: 'camera', name: 'Cam', expires_at: '', qr: {} }));
    const res = await devicesApi.createClaim({ name: 'Cam', kind: 'camera' });
    expect(res.code).toBe('XYZ');
    const post = spy.mock.calls.find((c) => (c[1] as RequestInit | undefined)?.method === 'POST')!;
    expect(post[0]).toBe(`${API_BASE}/api/devices/claims`);
    expect((post[1] as RequestInit).headers as Record<string, string>).toMatchObject({ 'X-CSRF-Token': 'csrf-d' });
    expect(JSON.parse((post[1] as RequestInit).body as string)).toMatchObject({ name: 'Cam', kind: 'camera' });
  });

  it('revoke DELETEs the device', async () => {
    const spy = mockFetch(() => okJson({ status: 'revoked' }));
    await devicesApi.revoke('dev-1');
    const del = spy.mock.calls.find((c) => (c[1] as RequestInit | undefined)?.method === 'DELETE')!;
    expect(del[0]).toBe(`${API_BASE}/api/devices/dev-1`);
  });

  it('rotate POSTs to the rotate endpoint', async () => {
    const spy = mockFetch(() => okJson({ status: 'rotated', token: 'new' }));
    const res = await devicesApi.rotate('dev-1');
    expect(res.token).toBe('new');
    const post = spy.mock.calls.find((c) => (c[1] as RequestInit | undefined)?.method === 'POST')!;
    expect(post[0]).toBe(`${API_BASE}/api/devices/dev-1/rotate`);
  });
});
