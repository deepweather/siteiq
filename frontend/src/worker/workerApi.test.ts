import { describe, it, expect, beforeEach, vi } from 'vitest';
import { API_BASE, clearCsrfCache } from '../services/api';
import { workerApi } from './workerApi';

const okJson = (body: unknown) =>
  new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  });

function mockFetch(handler: (url: string, init?: RequestInit) => Response) {
  return vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const url = typeof input === 'string' ? input : (input as Request).url;
    if (url.endsWith('/auth/csrf')) return okJson({ csrf_token: 'csrf-w' });
    return handler(url, init as RequestInit | undefined);
  });
}

describe('workerApi', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    clearCsrfCache();
  });

  it('assets() forwards type + q query params', async () => {
    const spy = mockFetch(() => okJson({ assets: [], counts: {}, project_id: 'p' }));
    await workerApi.assets('material', 'reb');
    const url = spy.mock.calls.at(-1)![0] as string;
    expect(url.startsWith(`${API_BASE}/api/worker/assets?`)).toBe(true);
    expect(url).toContain('type=material');
    expect(url).toContain('q=reb');
  });

  it('asset() encodes the subject path segments', async () => {
    const spy = mockFetch(() => okJson({ subject_type: 'material', subject_id: 'capture-rebar' }));
    await workerApi.asset('material', 'capture-rebar');
    const url = spy.mock.calls.at(-1)![0] as string;
    expect(url).toBe(`${API_BASE}/api/worker/assets/material/capture-rebar`);
  });

  it('submitEntry POSTs with CSRF + JSON body', async () => {
    const spy = mockFetch(() => okJson({ id: 'e1', status: 'proposed' }));
    await workerApi.submitEntry({
      kind: 'delivery',
      client_event_id: 'cid-12345678',
      payload: { subtype: 'rebar', quantity: 5, unit: 't', zone_id: 'zone-a' },
    });
    const post = spy.mock.calls.find(
      (c) => (c[1] as RequestInit | undefined)?.method === 'POST',
    )!;
    expect(post[0]).toBe(`${API_BASE}/api/worker/entry`);
    const init = post[1] as RequestInit;
    const headers = init.headers as Record<string, string>;
    expect(headers['X-CSRF-Token']).toBe('csrf-w');
    expect(JSON.parse(init.body as string).client_event_id).toBe('cid-12345678');
  });
});
