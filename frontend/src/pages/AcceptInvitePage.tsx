import { useEffect, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { AuthShell } from '../components/auth/AuthShell';
import { useAuth } from '../lib/auth/AuthProvider';
import { ApiError, auth, orgs } from '../services/api';

/**
 * Accepting an invite has two paths:
 *  - Already signed-in: try to accept; if the email mismatches, show
 *    the "wrong email" error and a link to sign out.
 *  - Anonymous: redirect to /login with `next` set so the user signs in
 *    and lands back here, where the token is then redeemed.
 */
export default function AcceptInvitePage() {
  const [params] = useSearchParams();
  const token = params.get('token');
  const nav = useNavigate();
  const { user, refresh } = useAuth();
  const [state, setState] = useState<'pending' | 'ok' | 'error' | 'needs_login'>('pending');
  const [error, setError] = useState('');

  useEffect(() => {
    if (!token) {
      setState('error');
      setError('Missing invite token.');
      return;
    }
    if (!user) {
      setState('needs_login');
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        const result = await orgs.acceptInvite(token);
        if (!cancelled) {
          // Switch into the new org so the dashboard immediately shows it.
          await orgs.switch(result.id);
          await refresh();
          setState('ok');
          setTimeout(() => nav('/app', { replace: true }), 800);
        }
      } catch (e) {
        if (cancelled) return;
        setState('error');
        setError(e instanceof ApiError ? e.message : 'Could not accept invite.');
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [token, user, refresh, nav]);

  if (state === 'needs_login') {
    return (
      <AuthShell
        title="Sign in to accept your invite"
        subtitle="The invite is tied to a specific email address — sign in or create that account first."
      >
        <Link
          to={`/login?next=${encodeURIComponent('/accept-invite?token=' + (token ?? ''))}`}
          className="block w-full rounded-md bg-primary text-primary-foreground font-semibold text-sm py-2.5 text-center hover:bg-primary/90"
        >
          Sign in
        </Link>
        <Link
          to={`/signup`}
          className="block w-full mt-3 text-center text-sm text-muted-foreground hover:text-foreground"
        >
          Don't have an account? Create one
        </Link>
      </AuthShell>
    );
  }

  return (
    <AuthShell
      title={
        state === 'pending'
          ? 'Joining workspace…'
          : state === 'ok'
            ? "You're in!"
            : 'Could not accept invite'
      }
      subtitle={state === 'error' ? error : state === 'ok' ? 'Redirecting to your dashboard…' : ''}
      footer={
        state === 'error' && (
          <button
            onClick={async () => {
              await auth.logout();
              nav('/login', { replace: true });
            }}
            className="text-foreground hover:underline"
          >
            Sign out and try a different account
          </button>
        )
      }
    >
      <div className="text-sm text-muted-foreground">
        {state === 'pending' && 'Hold tight…'}
      </div>
    </AuthShell>
  );
}
