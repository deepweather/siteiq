import { useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { AuthShell } from '../components/auth/AuthShell';
import { FormError, SubmitButton } from '../components/auth/fields';
import { PasswordField } from '../components/auth/PasswordField';
import { useAuth } from '../lib/auth/AuthProvider';
import { ApiError, auth } from '../services/api';

const Schema = z.object({
  password: z.string().min(12, 'Use at least 12 characters'),
});
type Form = z.infer<typeof Schema>;

export default function ResetPasswordPage() {
  const nav = useNavigate();
  const [params] = useSearchParams();
  const token = params.get('token') ?? '';
  const { setMe } = useAuth();
  const [serverError, setServerError] = useState<string | null>(null);

  const {
    register,
    handleSubmit,
    setError,
    watch,
    formState: { errors, isSubmitting },
  } = useForm<Form>({ resolver: zodResolver(Schema) });
  const password = watch('password') ?? '';

  const onSubmit = async (data: Form) => {
    setServerError(null);
    if (!token) {
      setServerError('Reset link is missing or malformed. Request a new one.');
      return;
    }
    try {
      const me = await auth.resetPassword(token, data.password);
      setMe(me);
      nav('/app', { replace: true });
    } catch (e) {
      if (e instanceof ApiError) {
        if (e.field) setError(e.field as keyof Form, { message: e.message });
        else setServerError(e.message);
      } else {
        setServerError('Something went wrong. Try again.');
      }
    }
  };

  return (
    <AuthShell
      title="Choose a new password"
      subtitle="Use a passphrase you can remember — at least 12 characters."
      footer={
        <Link to="/login" className="text-foreground hover:underline">
          Back to sign in
        </Link>
      }
    >
      <form onSubmit={handleSubmit(onSubmit)} noValidate>
        <FormError>{serverError}</FormError>
        <PasswordField
          autoComplete="new-password"
          autoFocus
          passwordValue={password}
          {...register('password')}
          error={errors.password?.message}
        />
        <SubmitButton loading={isSubmitting}>Set new password</SubmitButton>
      </form>
    </AuthShell>
  );
}
