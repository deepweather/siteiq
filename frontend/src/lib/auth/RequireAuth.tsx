/** Route guard — redirects to /login if not signed in. */
import { Navigate, useLocation, useSearchParams } from 'react-router-dom';
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

/**
 * Inverse of RequireAuth — keeps already-signed-in users out of the public
 * marketing / auth pages (landing, login, signup). Without this the app is
 * one-directional: anonymous users get bounced *into* /login, but a logged-in
 * user revisiting `/` or `/login` would see the stranger experience.
 *
 * Honours a `?next=` hint (set by RequireAuth) so a logged-in user who lands
 * on `/login?next=/app/portfolio` is forwarded to their intended destination
 * rather than the dashboard root.
 */
export function RedirectIfAuthed({ children }: { children: ReactNode }) {
  const { status, user } = useAuth();
  const [params] = useSearchParams();
  if (status === 'loading') return <AuthLoading />;
  if (user) {
    const next = params.get('next');
    return <Navigate to={next ? decodeURIComponent(next) : '/app'} replace />;
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
