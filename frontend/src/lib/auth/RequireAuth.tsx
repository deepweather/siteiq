/** Route guard — redirects to /login if not signed in. */
import { Navigate, useLocation } from 'react-router-dom';
import type { ReactNode } from 'react';
import { useAuth } from './AuthProvider';

export function RequireAuth({ children }: { children: ReactNode }) {
  const { status, user } = useAuth();
  const loc = useLocation();
  if (status === 'loading') return <AuthLoading />;
  if (!user) {
    const next = encodeURIComponent(loc.pathname + loc.search);
    return <Navigate to={`/login?next=${next}`} replace />;
  }
  return <>{children}</>;
}

const ROLE_ORDER = { viewer: 0, member: 1, admin: 2, owner: 3 } as const;

export function RequireRole({
  min,
  children,
}: {
  min: keyof typeof ROLE_ORDER;
  children: ReactNode;
}) {
  const { status, user, org } = useAuth();
  if (status === 'loading') return <AuthLoading />;
  if (!user) return <Navigate to="/login" replace />;
  const role = org?.role ?? 'viewer';
  if (ROLE_ORDER[role] < ROLE_ORDER[min]) {
    return (
      <div className="h-screen flex items-center justify-center bg-background">
        <div className="text-center max-w-sm">
          <div className="text-2xl font-semibold mb-2">Access denied</div>
          <p className="text-muted-foreground text-sm">
            This page requires the <strong>{min}</strong> role. Ask your workspace owner for access.
          </p>
        </div>
      </div>
    );
  }
  return <>{children}</>;
}

function AuthLoading() {
  return (
    <div className="h-screen flex items-center justify-center bg-background">
      <div className="text-center">
        <div className="w-10 h-10 bg-primary rounded-lg flex items-center justify-center mx-auto mb-4">
          <span className="text-primary-foreground text-lg font-bold">S</span>
        </div>
        <div className="text-foreground font-semibold text-sm">SiteIQ</div>
        <div className="text-muted-foreground text-xs mt-1">Loading…</div>
      </div>
    </div>
  );
}
