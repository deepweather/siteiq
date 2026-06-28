/** Gate for the worker app — redirects to /worker/login when signed out. */
import type { ReactNode } from 'react';
import { Navigate } from 'react-router-dom';
import { useAuth } from '../lib/auth/AuthProvider';
import { useI18n } from './i18n';
import { Spinner } from './components/ui';

export function RequireWorkerAuth({ children }: { children: ReactNode }) {
  const { status, user } = useAuth();
  const { t } = useI18n();
  if (status === 'loading') return <Spinner label={t('common.loading')} />;
  if (!user) return <Navigate to="/login" replace />;
  return <>{children}</>;
}
