/**
 * Bug #3 — api.ts must throw on non-2xx responses instead of silently
 * returning undefined. Bug #5 — API_BASE/WS_BASE constants must be the
 * single source of truth for URL bases.
 */
import { describe, it, expect, beforeEach, vi } from 'vitest';
import {
  API_BASE, WS_BASE,
  fetchProjects, fetchSite, fetchRecommendations, fetchAssetDetail,
  fetchCameras, loadProject, applyRecommendation, applyAllRecommendations,
  setSimSpeed, togglePause,
} from './api';

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
  });

  it.each([
    ['fetchProjects', () => fetchProjects()],
    ['fetchSite', () => fetchSite()],
    ['fetchRecommendations', () => fetchRecommendations()],
    ['fetchCameras', () => fetchCameras()],
    ['fetchAssetDetail', () => fetchAssetDetail('foo')],
  ])('%s rejects on 500', async (_name, fn) => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response('boom', { status: 500, statusText: 'Server Error' }),
    );
    await expect(fn()).rejects.toThrow(/500/);
  });

  it.each([
    ['loadProject', () => loadProject('x')],
    ['applyRecommendation', () => applyRecommendation('x')],
    ['applyAllRecommendations', () => applyAllRecommendations()],
    ['setSimSpeed', () => setSimSpeed(5)],
    ['togglePause', () => togglePause()],
  ])('%s rejects on 500', async (_name, fn) => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response('boom', { status: 500, statusText: 'Server Error' }),
    );
    await expect(fn()).rejects.toThrow(/500/);
  });

  it('happy path: parses JSON body successfully', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify([{ id: 'p', name: 'P', description: 'd', type: 'Residential' }]), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      }),
    );
    const projects = await fetchProjects();
    expect(projects).toHaveLength(1);
    expect(projects[0].id).toBe('p');
  });

  it('happy path: 404 still rejects (no silent undefined)', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response('not found', { status: 404, statusText: 'Not Found' }),
    );
    await expect(fetchAssetDetail('ghost')).rejects.toThrow(/404/);
  });

  it('POST without body sends no Content-Type header', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response('null', { status: 200, headers: { 'Content-Type': 'application/json' } }),
    );
    await togglePause();
    const call = fetchSpy.mock.calls[0];
    const init = call[1] as RequestInit;
    expect(init.method).toBe('POST');
    expect(init.headers).toBeUndefined();
  });

  it('POST with body sends Content-Type and serialized JSON', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response('null', { status: 200, headers: { 'Content-Type': 'application/json' } }),
    );
    await setSimSpeed(5);
    const init = fetchSpy.mock.calls[0][1] as RequestInit;
    expect((init.headers as Record<string, string>)['Content-Type']).toBe('application/json');
    expect(init.body).toBe(JSON.stringify({ speed: 5 }));
  });

  it('correct paths used for each endpoint (bug #5)', async () => {
    const fetchSpy = vi.spyOn(globalThis, 'fetch').mockImplementation(
      async () => new Response('[]', { status: 200, headers: { 'Content-Type': 'application/json' } }),
    );
    await fetchProjects();
    await fetchCameras();
    await loadProject('westhafen');
    const urls = fetchSpy.mock.calls.map(c => c[0]);
    expect(urls).toContain(`${API_BASE}/api/projects`);
    expect(urls).toContain(`${API_BASE}/api/cameras`);
    expect(urls).toContain(`${API_BASE}/api/projects/westhafen/load`);
  });
});
