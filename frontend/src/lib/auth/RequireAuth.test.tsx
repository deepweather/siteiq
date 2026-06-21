/** RequireAuth redirects unauthenticated users to /login?next=... */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { AuthProvider } from './AuthProvider';
import { RequireAuth, RequireRole } from './RequireAuth';
import { clearCsrfCache } from '../../services/api';

const okJson = (body: unknown) =>
  new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  });

function Tree({ children, initial }: { children: React.ReactNode; initial: string }) {
  return (
    <MemoryRouter initialEntries={[initial]}>
      <AuthProvider>
        <Routes>
          <Route path="/login" element={<div>login screen</div>} />
          <Route path="/app" element={children} />
        </Routes>
      </AuthProvider>
    </MemoryRouter>
  );
}

describe('RequireAuth', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    clearCsrfCache();
  });

  it('redirects to /login when there is no session', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      okJson({ user: null, org: null, memberships: [] }),
    );
    render(
      <Tree initial="/app">
        <RequireAuth>
          <div>secret dashboard</div>
        </RequireAuth>
      </Tree>,
    );
    await waitFor(() => screen.getByText('login screen'));
    expect(screen.queryByText('secret dashboard')).toBeNull();
  });

  it('renders children when /auth/me returns a user', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      okJson({
        user: { id: 'u', email: 'a@b.com', name: 'A', email_verified: true },
        org: { id: 'o', name: 'AcmeCo', slug: 'acmeco', role: 'owner', plan: 'trial' },
        memberships: [],
      }),
    );
    render(
      <Tree initial="/app">
        <RequireAuth>
          <div>secret dashboard</div>
        </RequireAuth>
      </Tree>,
    );
    await waitFor(() => screen.getByText('secret dashboard'));
  });
});

describe('RequireRole', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    clearCsrfCache();
  });

  it('blocks members from admin-only content', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      okJson({
        user: { id: 'u', email: 'a@b.com', name: 'A', email_verified: true },
        org: { id: 'o', name: 'AcmeCo', slug: 'acmeco', role: 'member', plan: 'trial' },
        memberships: [],
      }),
    );
    render(
      <MemoryRouter initialEntries={['/']}>
        <AuthProvider>
          <RequireRole min="admin">
            <div>admin content</div>
          </RequireRole>
        </AuthProvider>
      </MemoryRouter>,
    );
    await waitFor(() => screen.getByText(/access denied/i));
    expect(screen.queryByText('admin content')).toBeNull();
  });

  it('lets owners through', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      okJson({
        user: { id: 'u', email: 'a@b.com', name: 'A', email_verified: true },
        org: { id: 'o', name: 'AcmeCo', slug: 'acmeco', role: 'owner', plan: 'trial' },
        memberships: [],
      }),
    );
    render(
      <MemoryRouter initialEntries={['/']}>
        <AuthProvider>
          <RequireRole min="admin">
            <div>admin content</div>
          </RequireRole>
        </AuthProvider>
      </MemoryRouter>,
    );
    await waitFor(() => screen.getByText('admin content'));
  });
});
