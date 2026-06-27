/**
 * MenuBar — the only chrome users see all the time. Tests:
 *  - renders the active project name + speed/pause/connection cluster
 *  - clicking the project name opens the switcher popover
 *  - clicking Site opens a dropdown with pause + speed verbs
 *  - clicking Settings inside the Account menu routes to /app/settings
 *  - Sign out clears the session and redirects to /login
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { AuthProvider } from '../lib/auth/AuthProvider';
import { LiveProvider } from './LiveContext';
import { MenuBar } from './MenuBar';

const setupFetchMock = () => {
  vi.spyOn(window, 'fetch').mockImplementation(async (input: RequestInfo | URL) => {
    const url = typeof input === 'string' ? input : input instanceof URL ? input.toString() : input.url;
    if (url.endsWith('/auth/me')) {
      return new Response(
        JSON.stringify({
          user: { id: 'u', email: 'a@b.io', name: 'Marvin', email_verified: true },
          org: { id: 'o', name: 'Demo Workspace', slug: 'demo', role: 'owner', plan: 'trial' },
          memberships: [],
        }),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      );
    }
    if (url.endsWith('/auth/csrf')) {
      return new Response(JSON.stringify({ csrf_token: 't' }), { status: 200, headers: { 'Content-Type': 'application/json' } });
    }
    if (url.endsWith('/auth/logout')) {
      return new Response(JSON.stringify({ status: 'ok' }), { status: 200, headers: { 'Content-Type': 'application/json' } });
    }
    if (url.endsWith('/api/projects')) {
      return new Response(
        JSON.stringify([
          { id: 'p1', slug: 'berlin', name: 'Berlin Site', description: '', type: 'Residential' },
          { id: 'p2', slug: 'frankfurt', name: 'Frankfurt Site', description: '', type: 'Commercial' },
        ]),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      );
    }
    if (url.endsWith('/api/site')) {
      return new Response(
        JSON.stringify({ id: 'berlin', name: 'Berlin Site', slug: 'berlin', width: 100, height: 80, zones: [], levels: [], connections: [], schedule: [] }),
        { status: 200, headers: { 'Content-Type': 'application/json' } },
      );
    }
    if (url.endsWith('/api/recommendations')) {
      return new Response('[]', { status: 200, headers: { 'Content-Type': 'application/json' } });
    }
    return new Response('{}', { status: 200, headers: { 'Content-Type': 'application/json' } });
  });
};

beforeEach(() => {
  setupFetchMock();
});

function renderMenu() {
  return render(
    <MemoryRouter initialEntries={['/app']}>
      <AuthProvider>
        <LiveProvider>
          <Routes>
            <Route path="/app" element={<MenuBar />} />
            <Route path="/app/settings" element={<div data-testid="settings-route">settings</div>} />
            <Route path="/login" element={<div data-testid="login-route">login</div>} />
          </Routes>
        </LiveProvider>
      </AuthProvider>
    </MemoryRouter>,
  );
}

describe('<MenuBar />', () => {
  it('renders the project name + speed/pause/connection cluster', async () => {
    renderMenu();
    await waitFor(() => expect(screen.getByText('Berlin Site')).toBeInTheDocument());
    expect(screen.getByText(/Live|Offline/)).toBeInTheDocument();
    // Speed pills.
    expect(screen.getByRole('button', { name: 'Set speed 1x' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Set speed 10x' })).toBeInTheDocument();
  });

  it('opens the project switcher popover when the project name is clicked', async () => {
    renderMenu();
    fireEvent.click(await screen.findByRole('button', { name: /Berlin Site/ }));
    expect(await screen.findByText('Frankfurt Site')).toBeInTheDocument();
    expect(screen.getByText(/SWITCH PROJECT/i)).toBeInTheDocument();
  });

  it('Site menu reveals pause + speed verbs', async () => {
    renderMenu();
    // The "Site" menu label.
    fireEvent.click(await screen.findByRole('button', { name: 'Site' }));
    expect(await screen.findByText(/Pause simulation/)).toBeInTheDocument();
    expect(screen.getByText('Speed 5×')).toBeInTheDocument();
  });

  it('Account menu → Settings navigates to /app/settings', async () => {
    renderMenu();
    fireEvent.click(await screen.findByRole('button', { name: 'Account' }));
    fireEvent.click(await screen.findByText('Settings'));
    await waitFor(() => expect(screen.getByTestId('settings-route')).toBeInTheDocument());
  });

  it('Account menu → Sign out logs out and routes to /login', async () => {
    renderMenu();
    fireEvent.click(await screen.findByRole('button', { name: 'Account' }));
    fireEvent.click(await screen.findByText('Sign out'));
    await waitFor(() => expect(screen.getByTestId('login-route')).toBeInTheDocument());
  });
});
