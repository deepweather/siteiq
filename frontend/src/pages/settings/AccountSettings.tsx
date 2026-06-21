import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { TextField, FormError, SubmitButton } from '../../components/auth/fields';
import { PasswordField } from '../../components/auth/PasswordField';
import { useAuth } from '../../lib/auth/AuthProvider';
import { ApiError, auth } from '../../services/api';

const Schema = z
  .object({
    current: z.string().min(1, 'Current password required'),
    password: z.string().min(12, 'Use at least 12 characters'),
    confirm: z.string(),
  })
  .refine((d) => d.password === d.confirm, {
    message: "Passwords don't match",
    path: ['confirm'],
  });

type Form = z.infer<typeof Schema>;

export default function AccountSettings() {
  const { user, refresh } = useAuth();
  const nav = useNavigate();
  const [serverError, setServerError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);
  const [verifying, setVerifying] = useState(false);

  const {
    register,
    handleSubmit,
    setError,
    watch,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<Form>({ resolver: zodResolver(Schema) });
  const password = watch('password') ?? '';

  const onSubmit = async (data: Form) => {
    setServerError(null);
    setSuccess(false);
    try {
      await auth.changePassword(data.current, data.password);
      setSuccess(true);
      reset();
    } catch (e) {
      if (e instanceof ApiError) {
        if (e.field) setError(e.field as keyof Form, { message: e.message });
        else setServerError(e.message);
      } else {
        setServerError('Something went wrong.');
      }
    }
  };

  const onResendVerification = async () => {
    setVerifying(true);
    try {
      await auth.resendVerification();
    } finally {
      setVerifying(false);
    }
  };

  return (
    <div className="space-y-10">
      <section>
        <h1 className="text-2xl font-semibold tracking-tight mb-1">Account</h1>
        <p className="text-sm text-muted-foreground mb-6">Profile + sign-in.</p>
        <div className="rounded-xl border border-border bg-card p-6">
          <Row label="Name" value={user?.name ?? '—'} />
          <Row label="Email" value={user?.email ?? '—'} />
          <Row
            label="Email verified"
            value={
              user?.email_verified ? (
                <span className="text-emerald-600 font-medium">Verified</span>
              ) : (
                <button
                  onClick={onResendVerification}
                  disabled={verifying}
                  className="text-sm font-medium text-primary hover:underline disabled:opacity-60"
                >
                  {verifying ? 'Sending…' : 'Resend verification email'}
                </button>
              )
            }
          />
        </div>
      </section>

      <section>
        <h2 className="text-xl font-semibold tracking-tight mb-1">Change password</h2>
        <p className="text-sm text-muted-foreground mb-6">
          Other sessions will be signed out as a precaution.
        </p>
        <form
          onSubmit={handleSubmit(onSubmit)}
          className="rounded-xl border border-border bg-card p-6"
          noValidate
        >
          <FormError>{serverError}</FormError>
          {success && (
            <div className="rounded-md border border-emerald-500/40 bg-emerald-500/10 text-emerald-700 text-sm px-3 py-2 mb-4">
              Password updated.
            </div>
          )}
          <PasswordField
            label="Current password"
            autoComplete="current-password"
            showStrength={false}
            {...register('current')}
            error={errors.current?.message}
          />
          <PasswordField
            label="New password"
            autoComplete="new-password"
            passwordValue={password}
            {...register('password')}
            error={errors.password?.message}
          />
          <TextField
            label="Confirm new password"
            type="password"
            autoComplete="new-password"
            {...register('confirm')}
            error={errors.confirm?.message}
          />
          <SubmitButton loading={isSubmitting}>Update password</SubmitButton>
        </form>
      </section>

      <DangerZone
        onDeleted={async () => {
          await refresh();
          nav('/', { replace: true });
        }}
      />
    </div>
  );
}

function DangerZone({ onDeleted }: { onDeleted: () => Promise<void> }) {
  const [confirming, setConfirming] = useState(false);
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const onDelete = async () => {
    setError(null);
    setBusy(true);
    try {
      await auth.deleteAccount(password);
      await onDeleted();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'Could not delete account.');
      setBusy(false);
    }
  };

  return (
    <section>
      <h2 className="text-xl font-semibold tracking-tight mb-1 text-destructive">
        Delete account
      </h2>
      <p className="text-sm text-muted-foreground mb-6">
        Permanently delete your account. Workspaces where you're the only owner
        will also be deleted.
      </p>
      <div className="rounded-xl border border-destructive/40 bg-destructive/5 p-6">
        {!confirming ? (
          <button
            onClick={() => setConfirming(true)}
            className="rounded-md border border-destructive text-destructive font-semibold text-sm px-4 py-2 hover:bg-destructive/10"
          >
            Delete my account
          </button>
        ) : (
          <div className="space-y-4">
            <p className="text-sm">
              This is irreversible. Re-enter your password to confirm.
            </p>
            {error && <FormError>{error}</FormError>}
            <input
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="Current password"
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm"
            />
            <div className="flex items-center gap-3">
              <button
                onClick={onDelete}
                disabled={busy || !password}
                className="rounded-md bg-destructive text-destructive-foreground font-semibold text-sm px-4 py-2 disabled:opacity-50"
              >
                {busy ? 'Deleting…' : 'Permanently delete'}
              </button>
              <button
                onClick={() => {
                  setConfirming(false);
                  setPassword('');
                  setError(null);
                }}
                className="text-sm text-muted-foreground hover:text-foreground"
              >
                Cancel
              </button>
            </div>
          </div>
        )}
      </div>
    </section>
  );
}

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between py-3 border-b border-border last:border-b-0">
      <div className="text-sm text-muted-foreground">{label}</div>
      <div className="text-sm font-medium">{value}</div>
    </div>
  );
}
