import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { AuthShell } from '../components/auth/AuthShell';
import { TextField, FormError, SubmitButton } from '../components/auth/fields';
import { PasswordField } from '../components/auth/PasswordField';
import { useAuth } from '../lib/auth/AuthProvider';
import { ApiError, auth } from '../services/api';

const Schema = z.object({
  name: z.string().min(1, 'Tell us your name'),
  company: z.string().min(1, 'Workspace name required'),
  email: z.string().email('Enter a valid work email'),
  password: z
    .string()
    .min(12, 'Use at least 12 characters — a passphrase works great'),
});

type Form = z.infer<typeof Schema>;

export default function SignupPage() {
  const nav = useNavigate();
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
    try {
      const me = await auth.signup(data);
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
      title="Start a workspace"
      subtitle="14-day free trial. No credit card. Your simulated jobsite is live in under a minute."
      footer={
        <>
          Already have an account?{' '}
          <Link to="/login" className="font-medium text-foreground hover:underline">
            Sign in
          </Link>
        </>
      }
    >
      <form onSubmit={handleSubmit(onSubmit)} noValidate>
        <FormError>{serverError}</FormError>
        <TextField
          label="Your name"
          autoComplete="name"
          autoFocus
          {...register('name')}
          error={errors.name?.message}
        />
        <TextField
          label="Workspace / company name"
          {...register('company')}
          error={errors.company?.message}
          hint="You can rename this later from Settings."
        />
        <TextField
          label="Work email"
          type="email"
          autoComplete="email"
          {...register('email')}
          error={errors.email?.message}
        />
        <PasswordField
          autoComplete="new-password"
          passwordValue={password}
          {...register('password')}
          error={errors.password?.message}
        />
        <SubmitButton loading={isSubmitting}>Create workspace</SubmitButton>
        <p className="text-[11px] text-muted-foreground mt-3 leading-relaxed">
          By signing up you agree to be a sane person on someone else's
          construction site dashboard. You can delete the workspace from
          settings any time.
        </p>
      </form>
    </AuthShell>
  );
}
