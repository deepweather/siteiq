/**
 * AuthProvider — global auth context for the app.
 *
 * Boots by calling /auth/me. While booting the app shows a quiet
 * splash; after, every page knows whether the user is signed in and
 * which org is active. Updates flow through `refresh()` (no manual
 * cache plumbing).
 */
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react';
import { auth, type AuthOrg, type AuthUser, type MeResponse } from '../../services/api';

interface AuthContextShape {
  status: 'loading' | 'ready';
  user: AuthUser | null;
  org: AuthOrg | null;
  memberships: AuthOrg[];
  refresh: () => Promise<void>;
  setMe: (m: MeResponse) => void;
}

const AuthContext = createContext<AuthContextShape | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<'loading' | 'ready'>('loading');
  const [me, setMe] = useState<MeResponse>({ user: null, org: null, memberships: [] });

  const refresh = useCallback(async () => {
    try {
      const data = await auth.me();
      setMe(data);
    } catch {
      setMe({ user: null, org: null, memberships: [] });
    } finally {
      setStatus('ready');
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const value = useMemo<AuthContextShape>(
    () => ({
      status,
      user: me.user,
      org: me.org,
      memberships: me.memberships,
      refresh,
      setMe,
    }),
    [status, me, refresh],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextShape {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used inside <AuthProvider>');
  return ctx;
}
