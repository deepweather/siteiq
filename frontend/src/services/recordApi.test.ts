import { describe, it, expect, beforeEach, vi } from 'vitest';
import { API_BASE, clearCsrfCache } from './api';
import { recordApi } from './recordApi';

const okJson = (body: unknown) =>
  new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  });

function mockFetch(handler: (url: string, init?: RequestInit) => Response) {
  return vi.spyOn(globalThis, 'fetch').mockImplementation(async (input, init) => {
    const url = typeof input === 'string' ? input : (input as Request).url;
    if (url.endsWith('/auth/csrf')) return okJson({ csrf_token: 'csrf-rec' });
    return handler(url, init as RequestInit | undefined);
  });
}

describe('recordApi', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    clearCsrfCache();
  });

  it('listEvents maps source -> source_filter and forwards filters', async () => {
    const spy = mockFetch(() => okJson({ events: [], project_id: 'p' }));
    await recordApi.listEvents({ kind: 'material.delivered', source: 'camera', limit: 50 });
    const url = spy.mock.calls.at(-1)![0] as string;
    expect(url.startsWith(`${API_BASE}/api/record/events?`)).toBe(true);
    expect(url).toContain('kind=material.delivered');
    expect(url).toContain('source_filter=camera');
    expect(url).toContain('limit=50');
    expect(url).not.toContain('source=camera'); // renamed param
  });

  it('getTimeline passes the date query when provided', async () => {
    const spy = mockFetch(() => okJson({ date: '2026-01-10', events: [] }));
    await recordApi.getTimeline('2026-01-10');
    const url = spy.mock.calls.at(-1)![0] as string;
    expect(url).toBe(`${API_BASE}/api/record/timeline?date=2026-01-10`);
  });

  it('confirmEvent POSTs to the confirm endpoint with CSRF', async () => {
    const spy = mockFetch(() => okJson({ id: 'e1', status: 'confirmed' }));
    await recordApi.confirmEvent('e1', 'looks right');
    const post = spy.mock.calls.find(
      (c) => (c[1] as RequestInit | undefined)?.method === 'POST',
    )!;
    expect(post[0]).toBe(`${API_BASE}/api/record/events/e1/confirm`);
    const headers = (post[1] as RequestInit).headers as Record<string, string>;
    expect(headers['X-CSRF-Token']).toBe('csrf-rec');
  });

  it('generateDemo POSTs to the demo endpoint', async () => {
    const spy = mockFetch(() => okJson({ project_id: 'p', days: 21, event_count: 100, proposed_count: 1, kinds: {} }));
    const r = await recordApi.generateDemo(21);
    expect(r.event_count).toBe(100);
    const post = spy.mock.calls.find(
      (c) => (c[1] as RequestInit | undefined)?.method === 'POST',
    )!;
    expect(post[0]).toBe(`${API_BASE}/api/record/demo/generate`);
  });

  it('query returns the structured answer', async () => {
    mockFetch(() => okJson({ intent: 'cost', answer: 'Total is €100', data: {}, supporting_event_ids: ['a'] }));
    const a = await recordApi.query('what is the total cost?');
    expect(a.intent).toBe('cost');
    expect(a.answer).toContain('Total');
  });
});
