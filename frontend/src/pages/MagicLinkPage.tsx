/**
 * /magic-link?token=…
 *
 * Two states:
 *   - With ?token=…  → consume immediately, sign user in, redirect to /app.
 *   - Without ?token → render a "Send me a sign-in link" form (passwordless
 *     login flow). Same idea as Slack / Notion's magic link.
 */
import { useEffect, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { AuthShell } from '../components/auth/AuthShell';
import { TextField, FormError, SubmitButton } from '../components/auth/fields';
import { useAuth } from '../lib/auth/AuthProvider';
import { ApiError, auth } from '../services/api';

const Schema = z.object({ email: z.string().email('Enter a valid email') });
type Form = z.infer<typeof Schema>;

export default function MagicLinkPage() {
  const [params] = useSearchParams();
  const token = params.get('token');
  const nav = useNavigate();
  const { setMe } = useAuth();
  const [state, setState] = useState<'consuming' | 'sent' | 'form' | 'error'>(
    token ? 'consuming' : 'form',
  );
  const [error, setError] = useState('');

  useEffect(() => {
    if (!token) return;
    let cancelled = false;
    (async () => {
      try {
        const me = await auth.loginWithToken(token);
        if (cancelled) return;
        setMe(me);
        nav('/app', { replace: true });
      } catch (e) {
        if (cancelled) return;
        setState('error');
        setError(
          e instanceof ApiError
            ? e.message
            : 'This sign-in link is no longer valid.',
        );
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [token, setMe, nav]);

  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<Form>({ resolver: zodResolver(Schema) });

  const onSubmit = async (data: Form) => {
    setError('');
    try {
      await auth.requestMagicLink(data.email);
      setState('sent');
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Could not send sign-in link.');
    }
  };

  if (state === 'consuming') {
    return (
      <AuthShell title="Signing you in…" subtitle="Hold tight.">
        <div className="text-sm text-muted-foreground">Verifying your link.</div>
      </AuthShell>
    );
  }

  if (state === 'error') {
    return (
      <AuthShell
        title="This link can't be used"
        subtitle={error}
        footer={
          <Link to="/login" className="text-foreground hover:underline">
            Back to sign in
          </Link>
        }
      >
        <Link
          to="/magic-link"
          className="inline-block rounded-md bg-primary text-primary-foreground font-semibold text-sm px-4 py-2 hover:bg-primary/90"
        >
          Send a fresh link
        </Link>
      </AuthShell>
    );
  }

  if (state === 'sent') {
    return (
      <AuthShell
        title="Check your inbox"
        subtitle="If we have an account for that email, you'll get a sign-in link in a minute. It expires in 15 minutes."
        footer={
          <Link to="/login" className="text-foreground hover:underline">
            Back to sign in
          </Link>
        }
      >
        <div className="text-sm text-muted-foreground">
          Tip: in development, the link is at <code className="font-mono">/dev/outbox</code>.
        </div>
      </AuthShell>
    );
  }

  return (
    <AuthShell
      title="Sign in with a link"
      subtitle="No password required. We'll email you a one-time link."
      footer={
        <Link to="/login" className="text-foreground hover:underline">
          Use a password instead
        </Link>
      }
    >
      <form onSubmit={handleSubmit(onSubmit)} noValidate>
        <FormError>{error}</FormError>
        <TextField
          label="Work email"
          type="email"
          autoComplete="email"
          autoFocus
          {...register('email')}
          error={errors.email?.message}
        />
        <SubmitButton loading={isSubmitting}>Email me a sign-in link</SubmitButton>
      </form>
    </AuthShell>
  );
}
