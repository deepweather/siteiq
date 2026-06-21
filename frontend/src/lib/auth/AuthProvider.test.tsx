/** AuthProvider boots via /auth/me and exposes loading -> ready transition. */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { AuthProvider, useAuth } from './AuthProvider';
import { clearCsrfCache } from '../../services/api';

const okJson = (body: unknown) =>
  new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  });

function Probe() {
  const { status, user, org } = useAuth();
  return (
    <>
      <div data-testid="status">{status}</div>
      <div data-testid="user">{user?.email ?? 'none'}</div>
      <div data-testid="org">{org?.name ?? 'none'}</div>
    </>
  );
}

describe('AuthProvider', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    clearCsrfCache();
  });

  it('starts in loading and resolves to anonymous when /auth/me returns nulls', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      okJson({ user: null, org: null, memberships: [] }),
    );
    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>,
    );
    expect(screen.getByTestId('status').textContent).toBe('loading');
    await waitFor(() => expect(screen.getByTestId('status').textContent).toBe('ready'));
    expect(screen.getByTestId('user').textContent).toBe('none');
  });

  it('exposes the user + active org after /auth/me succeeds', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      okJson({
        user: { id: 'u', email: 'a@b.com', name: 'A', email_verified: true },
        org: { id: 'o', name: 'AcmeCo', slug: 'acmeco', role: 'owner', plan: 'trial' },
        memberships: [],
      }),
    );
    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>,
    );
    await waitFor(() => expect(screen.getByTestId('status').textContent).toBe('ready'));
    expect(screen.getByTestId('user').textContent).toBe('a@b.com');
    expect(screen.getByTestId('org').textContent).toBe('AcmeCo');
  });

  it('treats /auth/me failures as anonymous', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(new Response('{}', { status: 500 }));
    render(
      <AuthProvider>
        <Probe />
      </AuthProvider>,
    );
    await waitFor(() => expect(screen.getByTestId('status').textContent).toBe('ready'));
    expect(screen.getByTestId('user').textContent).toBe('none');
  });
});
