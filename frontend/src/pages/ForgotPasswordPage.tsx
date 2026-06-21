import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { AuthShell } from '../components/auth/AuthShell';
import { TextField, FormError, SubmitButton } from '../components/auth/fields';
import { ApiError, auth } from '../services/api';

const Schema = z.object({ email: z.string().email('Enter a valid email') });
type Form = z.infer<typeof Schema>;

export default function ForgotPasswordPage() {
  const [done, setDone] = useState(false);
  const [serverError, setServerError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<Form>({ resolver: zodResolver(Schema) });

  const onSubmit = async (data: Form) => {
    setServerError(null);
    try {
      await auth.forgotPassword(data.email);
      setDone(true);
    } catch (e) {
      setServerError(e instanceof ApiError ? e.message : 'Something went wrong.');
    }
  };

  return (
    <AuthShell
      title={done ? 'Check your inbox' : 'Reset your password'}
      subtitle={
        done
          ? "If an account exists for that email, we just sent a reset link. The link expires in 30 minutes."
          : "We'll email you a link to set a new password."
      }
      footer={
        <Link to="/login" className="text-foreground hover:underline">
          Back to sign in
        </Link>
      }
    >
      {!done && (
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
          <SubmitButton loading={isSubmitting}>Send reset link</SubmitButton>
        </form>
      )}
    </AuthShell>
  );
}
