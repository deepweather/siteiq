/**
 * Bug #3 — api.ts must throw on non-2xx responses instead of silently
 * returning undefined. Bug #5 — API_BASE/WS_BASE constants must be the
 * single source of truth for URL bases. Plus new auth-era checks: every
 * mutating request must include credentials + the X-CSRF-Token header.
 */
import { describe, it, expect, beforeEach, vi } from 'vitest';
import {
  API_BASE,
  WS_BASE,
  ApiError,
  clearCsrfCache,
  fetchProjects,
  fetchSite,
  fetchRecommendations,
  fetchAssetDetail,
  fetchCameras,
  fetchHeatmap,
  loadProject,
  applyRecommendation,
  applyAllRecommendations,
  setSimSpeed,
  togglePause,
} from './api';

const okJson = (body: unknown) =>
  new Response(JSON.stringify(body), { status: 200, headers: { 'Content-Type': 'application/json' } });

const errEnvelope = (status: number, code = 'http_error', message = 'boom') =>
  new Response(JSON.stringify({ error: { code, message } }), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });

function mockCsrfThen(handler: (req: Request) => Response) {
  const responses: Response[] = [];
  vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
    const url = typeof input === 'string' ? input : (input as Request).url;
    if (url.endsWith('/auth/csrf')) {
      return okJson({ csrf_token: 'test-csrf-123' });
    }
    const req = input instanceof Request ? input : new Request(String(input));
    const r = handler(req);
    responses.push(r);
    return r;
  });
}

describe('api.ts URL constants (bug #5)', () => {
  it('exports API_BASE pointing at backend default port', () => {
    expect(API_BASE).toBe('http://localhost:8000');
  });
  it('exports WS_BASE matching API_BASE host', () => {
    expect(WS_BASE).toBe('ws://localhost:8000');
  });
});

describe('api.ts error handling (bug #3)', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    clearCsrfCache();
  });

  it.each([
    ['fetchProjects', () => fetchProjects()],
    ['fetchSite', () => fetchSite()],
    ['fetchRecommendations', () => fetchRecommendations()],
    ['fetchCameras', () => fetchCameras()],
    ['fetchAssetDetail', () => fetchAssetDetail('foo')],
  ])('%s rejects with ApiError on 500', async (_name, fn) => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(errEnvelope(500));
    await expect(fn()).rejects.toBeInstanceOf(ApiError);
  });

  it.each([
    ['loadProject', () => loadProject('x')],
    ['applyRecommendation', () => applyRecommendation('x')],
    ['applyAllRecommendations', () => applyAllRecommendations()],
    ['setSimSpeed', () => setSimSpeed(5)],
    ['togglePause', () => togglePause()],
  ])('%s rejects with ApiError on 500', async (_name, fn) => {
    mockCsrfThen(() => errEnvelope(500));
    await expect(fn()).rejects.toBeInstanceOf(ApiError);
  });

  it('happy path: parses JSON body successfully', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      okJson([{ id: 'p', name: 'P', description: 'd', type: 'Residential' }]),
    );
    const projects = await fetchProjects();
    expect(projects).toHaveLength(1);
    expect(projects[0].id).toBe('p');
  });

  it('happy path: 404 still rejects with ApiError (no silent undefined)', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(errEnvelope(404, 'not_found', 'Asset not found'));
    await expect(fetchAssetDetail('ghost')).rejects.toMatchObject({
      status: 404,
      code: 'not_found',
    });
  });

  it('GET requests include credentials for cookie auth', async () => {
    const spy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(okJson([]));
    await fetchProjects();
    const init = spy.mock.calls[0][1] as RequestInit;
    expect(init.credentials).toBe('include');
  });

  it('POST without body sends X-CSRF-Token header but no Content-Type', async () => {
    const spy = vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      const url = typeof input === 'string' ? input : (input as Request).url;
      if (url.endsWith('/auth/csrf')) return okJson({ csrf_token: 'csrf-abc' });
      return okJson(null);
    });
    await togglePause();
    // Find the POST call (not the CSRF GET).
    const postCall = spy.mock.calls.find(
      (c) => (c[1] as RequestInit | undefined)?.method === 'POST',
    );
    expect(postCall).toBeDefined();
    const init = postCall![1] as RequestInit;
    expect(init.method).toBe('POST');
    expect(init.credentials).toBe('include');
    const headers = init.headers as Record<string, string>;
    expect(headers['X-CSRF-Token']).toBe('csrf-abc');
    expect(headers['Content-Type']).toBeUndefined();
  });

  it('POST with body sends Content-Type and serialized JSON + CSRF', async () => {
    const spy = vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      const url = typeof input === 'string' ? input : (input as Request).url;
      if (url.endsWith('/auth/csrf')) return okJson({ csrf_token: 'csrf-xyz' });
      return okJson(null);
    });
    await setSimSpeed(5);
    const postCall = spy.mock.calls.find(
      (c) => (c[1] as RequestInit | undefined)?.method === 'POST',
    );
    const init = postCall![1] as RequestInit;
    const headers = init.headers as Record<string, string>;
    expect(headers['Content-Type']).toBe('application/json');
    expect(headers['X-CSRF-Token']).toBe('csrf-xyz');
    expect(init.body).toBe(JSON.stringify({ speed: 5 }));
  });

  it('correct paths used for each endpoint (bug #5)', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      const url = typeof input === 'string' ? input : (input as Request).url;
      if (url.endsWith('/auth/csrf')) return okJson({ csrf_token: 't' });
      return okJson([]);
    });
    await fetchProjects();
    await fetchCameras();
    await loadProject('westhafen');
    const urls = fetchSpy.mock.calls.map((c) => c[0]);
    expect(urls).toContain(`${API_BASE}/api/projects`);
    expect(urls).toContain(`${API_BASE}/api/cameras`);
    // Phase 1 renamed the legacy slug-based load endpoint.
    expect(urls).toContain(`${API_BASE}/api/site/load-seed`);
  });

  it('fetchHeatmap with no arg hits the pooled endpoint', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockImplementation(async () =>
      okJson({ cell_size: 4, site_width: 100, site_height: 80, max_count: 0, cells: [], level_id: null }),
    );
    await fetchHeatmap();
    const urls = fetchSpy.mock.calls.map((c) => c[0]);
    expect(urls).toEqual([`${API_BASE}/api/simulation/heatmap`]);
  });

  it('fetchHeatmap(levelId) passes the level_id query param', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockImplementation(async () =>
      okJson({ cell_size: 4, site_width: 100, site_height: 80, max_count: 0, cells: [], level_id: 'L1' }),
    );
    await fetchHeatmap('L1');
    const urls = fetchSpy.mock.calls.map((c) => c[0]);
    expect(urls).toEqual([`${API_BASE}/api/simulation/heatmap?level_id=L1`]);
  });

  it('fetchHeatmap URL-encodes the level_id', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockImplementation(async () =>
      okJson({ cell_size: 4, site_width: 100, site_height: 80, max_count: 0, cells: [] }),
    );
    await fetchHeatmap('L-1');
    const urls = fetchSpy.mock.calls.map((c) => c[0]);
    expect(urls[0]).toBe(`${API_BASE}/api/simulation/heatmap?level_id=L-1`);
  });
});
