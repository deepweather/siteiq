import { useEffect, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { AuthShell } from '../components/auth/AuthShell';
import { useAuth } from '../lib/auth/AuthProvider';
import { ApiError, auth } from '../services/api';

export default function VerifyEmailPage() {
  const [params] = useSearchParams();
  const token = params.get('token');
  const { refresh } = useAuth();
  const [state, setState] = useState<'pending' | 'ok' | 'error'>('pending');
  const [error, setError] = useState<string>('');

  useEffect(() => {
    let cancelled = false;
    if (!token) {
      setState('error');
      setError('Missing verification token.');
      return;
    }
    (async () => {
      try {
        await auth.verifyEmail(token);
        if (!cancelled) {
          setState('ok');
          refresh();
        }
      } catch (e) {
        if (!cancelled) {
          setState('error');
          setError(e instanceof ApiError ? e.message : 'Verification failed.');
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [token, refresh]);

  return (
    <AuthShell
      title={
        state === 'pending' ? 'Verifying your email…' : state === 'ok' ? 'Email verified' : 'Verification failed'
      }
      subtitle={
        state === 'ok'
          ? 'Your account is fully activated. You can now invite teammates.'
          : state === 'error'
            ? error
            : ''
      }
      footer={
        <Link to="/app" className="text-foreground hover:underline">
          Continue to dashboard
        </Link>
      }
    >
      <div className="text-sm text-muted-foreground">
        {state === 'pending' && 'Hold tight…'}
      </div>
    </AuthShell>
  );
}
