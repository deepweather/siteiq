/** Home: greeting + today's site activity + the four big action tiles. */
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../../lib/auth/AuthProvider';
import { useI18n } from '../i18n';
import { workerApi, type WorkerOverview } from '../workerApi';
import { Screen, Tile } from '../components/ui';

const ACTIONS: { kind: string; emoji: string; tint: string; key: string }[] = [
  { kind: 'delivery', emoji: '📦', tint: 'hsl(212 80% 92%)', key: 'action.delivery' },
  { kind: 'incident', emoji: '⚠️', tint: 'hsl(0 80% 93%)', key: 'action.incident' },
  { kind: 'inspection', emoji: '✅', tint: 'hsl(152 50% 88%)', key: 'action.inspection' },
  { kind: 'note', emoji: '📝', tint: 'hsl(220 13% 91%)', key: 'action.note' },
];

export default function WorkerHome() {
  const { t } = useI18n();
  const { user } = useAuth();
  const navigate = useNavigate();
  const [ov, setOv] = useState<WorkerOverview | null>(null);

  useEffect(() => {
    let alive = true;
    workerApi
      .overview()
      .then((o) => alive && setOv(o))
      .catch(() => {/* offline — show cached SW response or nothing */});
    return () => {
      alive = false;
    };
  }, []);

  const firstName = user?.name?.split(' ')[0] ?? '';

  return (
    <Screen>
      <div>
        <h1 className="text-2xl font-bold text-foreground">
          {t('greeting')}{firstName ? `, ${firstName}` : ''}
        </h1>
        {ov ? (
          <p className="text-muted-foreground text-lg">{ov.site_name}</p>
        ) : null}
      </div>

      {ov ? (
        <div className="grid grid-cols-3 gap-2">
          <Stat label={t('action.delivery')} value={ov.today.deliveries} />
          <Stat label={t('action.incident')} value={ov.today.incidents} />
          <Stat label={t('action.inspection')} value={ov.today.inspections} />
        </div>
      ) : null}

      <div className="grid grid-cols-2 gap-3">
        {ACTIONS.map((a) => (
          <Tile
            key={a.kind}
            emoji={a.emoji}
            tint={a.tint}
            label={t(a.key)}
            onClick={() => navigate(`/new/${a.kind}`)}
          />
        ))}
      </div>
    </Screen>
  );
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-2xl bg-card border border-border p-3 text-center">
      <div className="font-mono text-3xl font-bold text-foreground tabular-nums">{value}</div>
      <div className="text-xs text-muted-foreground truncate">{label}</div>
    </div>
  );
}
