/** Magic-link login. Email -> link in inbox -> tap on this device -> in.
 *  The email link lands at /worker/login?token=… (allow-listed server-side). */
import { useEffect, useRef, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { auth, ApiError } from '../../services/api';
import { useAuth } from '../../lib/auth/AuthProvider';
import { useI18n } from '../i18n';
import { Screen, WorkerButton, Spinner, FieldLabel } from '../components/ui';

export default function WorkerLogin() {
  const { t } = useI18n();
  const { user, status, setMe } = useAuth();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const token = params.get('token');

  const [email, setEmail] = useState('');
  const [phase, setPhase] = useState<'idle' | 'sent' | 'signingIn' | 'error'>(
    token ? 'signingIn' : 'idle',
  );
  const consumed = useRef(false);

  // Already signed in -> straight to home.
  useEffect(() => {
    if (status === 'ready' && user) navigate('/', { replace: true });
  }, [status, user, navigate]);

  // Consume a magic-link token if present.
  useEffect(() => {
    if (!token || consumed.current) return;
    consumed.current = true;
    (async () => {
      try {
        const me = await auth.loginWithToken(token);
        setMe(me);
        navigate('/', { replace: true });
      } catch {
        setPhase('error');
      }
    })();
  }, [token, setMe, navigate]);

  const send = async () => {
    try {
      await auth.requestMagicLink(email.trim(), '/worker/login');
      setPhase('sent');
    } catch (e) {
      // Endpoint is silent on unknown emails; only a transport error lands here.
      if (e instanceof ApiError) setPhase('error');
      else setPhase('sent');
    }
  };

  if (phase === 'signingIn') return <Spinner label={t('login.signingIn')} />;

  return (
    <div className="min-h-screen flex flex-col justify-center">
      <Screen className="max-w-md w-full mx-auto">
        <div className="flex flex-col items-center mb-4">
          <div className="w-16 h-16 rounded-2xl bg-primary flex items-center justify-center text-primary-foreground text-3xl font-bold">
            S
          </div>
          <div className="mt-3 text-xl font-bold text-foreground">{t('appName')}</div>
        </div>

        {phase === 'sent' ? (
          <div className="text-center space-y-2 py-6">
            <div className="text-5xl" aria-hidden>📩</div>
            <h1 className="text-2xl font-bold text-foreground">{t('login.sent.title')}</h1>
            <p className="text-muted-foreground text-lg">{t('login.sent.sub')}</p>
          </div>
        ) : (
          <>
            <FieldLabel>{t('login.title')}</FieldLabel>
            <p className="text-muted-foreground text-lg mb-4">{t('login.lead')}</p>
            <input
              type="email"
              inputMode="email"
              autoComplete="email"
              placeholder={t('login.email')}
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full min-h-[64px] rounded-2xl border-2 border-border bg-card px-5 text-xl text-foreground outline-none focus:border-primary mb-4"
            />
            {phase === 'error' ? (
              <p className="text-destructive text-base mb-3">{t('login.failed')}</p>
            ) : null}
            <WorkerButton onClick={send} disabled={!email.includes('@')}>
              {t('login.send')}
            </WorkerButton>
          </>
        )}
      </Screen>
    </div>
  );
}
