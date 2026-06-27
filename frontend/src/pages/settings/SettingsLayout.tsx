/** Shared shell for /app/settings/* — left nav + content area. Full-screen
 *  takeover, reached from the dashboard's WorkspaceMenu. */
import { useEffect, useState } from 'react';
import { NavLink, Outlet, useNavigate } from 'react-router-dom';
import { useAuth } from '../../lib/auth/AuthProvider';
import { auth, clearCsrfCache, fetchVersion, type VersionInfo } from '../../services/api';

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
  const [version, setVersion] = useState<VersionInfo | null>(null);
  useEffect(() => {
    fetchVersion().then(setVersion).catch(() => {});
  }, []);

  const onSignOut = async () => {
    await auth.logout();
    clearCsrfCache();
    await refresh();
    nav('/login', { replace: true });
  };

  return (
    <div className="flex-1 grid grid-cols-[200px_1fr] min-h-0 bg-background">
      <aside className="border-r border-border p-3 space-y-1 overflow-y-auto">
        <div className="px-3 mb-2">
          <div className="text-[10px] uppercase tracking-wider text-muted-foreground font-semibold">Settings</div>
          <div className="text-[11px] text-foreground truncate">{user?.email}</div>
        </div>
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
        <div className="pt-2 mt-2 border-t border-border">
          <button
            onClick={onSignOut}
            className="w-full text-left rounded-md px-3 py-2 text-sm text-muted-foreground hover:text-foreground hover:bg-muted/60"
          >
            Sign out
          </button>
        </div>
      </aside>
      <main className="overflow-y-auto p-8">
        <div className="max-w-3xl mx-auto">
          <Outlet />
          {version && (
            <p className="mt-12 text-[11px] text-muted-foreground tabular-nums">
              Build {version.short}
              {version.built_at && ` · ${version.built_at}`}
            </p>
          )}
        </div>
      </main>
    </div>
  );
}
