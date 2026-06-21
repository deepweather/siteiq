/** Shared shell for /app/settings/* pages — left nav + content area. */
import { NavLink, Outlet, useNavigate } from 'react-router-dom';
import { useAuth } from '../../lib/auth/AuthProvider';
import { auth, clearCsrfCache } from '../../services/api';

const NAV = [
  { to: '/app/settings/account', label: 'Account' },
  { to: '/app/settings/team', label: 'Team', adminOnly: true },
  { to: '/app/settings/orgs', label: 'Workspaces' },
  { to: '/app/settings/sessions', label: 'Sessions' },
];

export default function SettingsLayout() {
  const { user, org, refresh } = useAuth();
  const nav = useNavigate();
  const isAdmin = org?.role === 'owner' || org?.role === 'admin';

  const onSignOut = async () => {
    await auth.logout();
    clearCsrfCache();
    await refresh();
    nav('/login', { replace: true });
  };

  return (
    <div className="h-screen flex flex-col bg-background">
      <header className="px-6 py-4 border-b border-border flex items-center justify-between">
        <div className="flex items-center gap-3">
          <NavLink to="/app" className="flex items-center gap-2">
            <span className="w-7 h-7 bg-primary rounded-md flex items-center justify-center">
              <span className="text-primary-foreground text-sm font-bold">S</span>
            </span>
            <span className="font-semibold text-sm">SiteIQ</span>
          </NavLink>
          <span className="text-muted-foreground">/</span>
          <span className="text-sm font-medium">Settings</span>
        </div>
        <div className="text-xs text-muted-foreground flex items-center gap-3">
          <span>{user?.email}</span>
          <button onClick={onSignOut} className="hover:text-foreground">
            Sign out
          </button>
        </div>
      </header>
      <div className="flex-1 grid grid-cols-[220px_1fr] min-h-0">
        <aside className="border-r border-border p-4 space-y-1">
          {NAV.filter((item) => !item.adminOnly || isAdmin).map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) =>
                'block rounded-md px-3 py-2 text-sm ' +
                (isActive
                  ? 'bg-muted text-foreground font-medium'
                  : 'text-muted-foreground hover:text-foreground hover:bg-muted/60')
              }
            >
              {item.label}
            </NavLink>
          ))}
        </aside>
        <main className="overflow-y-auto p-8">
          <div className="max-w-3xl mx-auto">
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  );
}
