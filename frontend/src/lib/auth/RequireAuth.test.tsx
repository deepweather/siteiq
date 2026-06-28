/** RequireAuth redirects unauthenticated users to /login?next=... */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { AuthProvider } from './AuthProvider';
import { RequireAuth, RequireRole, RedirectIfAuthed } from './RequireAuth';
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

const meUser = {
  user: { id: 'u', email: 'a@b.com', name: 'A', email_verified: true },
  org: { id: 'o', name: 'AcmeCo', slug: 'acmeco', role: 'owner', plan: 'trial' },
  memberships: [],
};

function PublicTree({ children, initial }: { children: React.ReactNode; initial: string }) {
  return (
    <MemoryRouter initialEntries={[initial]}>
      <AuthProvider>
        <Routes>
          <Route path="/login" element={children} />
          <Route path="/app" element={<div>dashboard</div>} />
          <Route path="/app/portfolio" element={<div>portfolio page</div>} />
        </Routes>
      </AuthProvider>
    </MemoryRouter>
  );
}

describe('RedirectIfAuthed', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    clearCsrfCache();
  });

  it('renders the public page when signed out', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      okJson({ user: null, org: null, memberships: [] }),
    );
    render(
      <PublicTree initial="/login">
        <RedirectIfAuthed>
          <div>login screen</div>
        </RedirectIfAuthed>
      </PublicTree>,
    );
    await waitFor(() => screen.getByText('login screen'));
  });

  it('bounces a signed-in user to /app', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(okJson(meUser));
    render(
      <PublicTree initial="/login">
        <RedirectIfAuthed>
          <div>login screen</div>
        </RedirectIfAuthed>
      </PublicTree>,
    );
    await waitFor(() => screen.getByText('dashboard'));
    expect(screen.queryByText('login screen')).toBeNull();
  });

  it('honours the ?next= hint when signed in', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(okJson(meUser));
    render(
      <PublicTree initial="/login?next=%2Fapp%2Fportfolio">
        <RedirectIfAuthed>
          <div>login screen</div>
        </RedirectIfAuthed>
      </PublicTree>,
    );
    await waitFor(() => screen.getByText('portfolio page'));
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
