import { useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { AuthShell } from '../components/auth/AuthShell';
import { TextField, FormError, SubmitButton } from '../components/auth/fields';
import { PasswordField } from '../components/auth/PasswordField';
import { useAuth } from '../lib/auth/AuthProvider';
import { ApiError, auth } from '../services/api';

const Schema = z.object({
  email: z.string().email('Enter a valid email'),
  password: z.string().min(1, 'Password required'),
});

type Form = z.infer<typeof Schema>;

export default function LoginPage() {
  const nav = useNavigate();
  const [params] = useSearchParams();
  const { setMe } = useAuth();
  const [serverError, setServerError] = useState<string | null>(null);

  const {
    register,
    handleSubmit,
    setError,
    watch,
    formState: { errors, isSubmitting },
  } = useForm<Form>({ resolver: zodResolver(Schema) });

  const password = watch('password');

  const onSubmit = async (data: Form) => {
    setServerError(null);
    try {
      const me = await auth.login(data);
      setMe(me);
      const next = params.get('next') ?? '/app';
      nav(decodeURIComponent(next), { replace: true });
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
      title="Welcome back"
      subtitle="Sign in to your SiteIQ workspace."
      footer={
        <>
          New to SiteIQ?{' '}
          <Link to="/signup" className="font-medium text-foreground hover:underline">
            Create an account
          </Link>
        </>
      }
    >
      <form onSubmit={handleSubmit(onSubmit)} noValidate>
        <FormError>{serverError}</FormError>
        <TextField
          label="Work email"
          type="email"
          autoComplete="email"
          autoFocus
          {...register('email')}
          error={errors.email?.message}
        />
        <PasswordField
          autoComplete="current-password"
          showStrength={false}
          passwordValue={password}
          {...register('password')}
          error={errors.password?.message}
        />
        <div className="flex items-center justify-between mb-4">
          <Link
            to="/magic-link"
            className="text-xs text-muted-foreground hover:text-foreground"
          >
            Email me a sign-in link
          </Link>
          <Link
            to="/forgot-password"
            className="text-xs text-muted-foreground hover:text-foreground"
          >
            Forgot password?
          </Link>
        </div>
        <SubmitButton loading={isSubmitting}>Sign in</SubmitButton>
      </form>
    </AuthShell>
  );
}
