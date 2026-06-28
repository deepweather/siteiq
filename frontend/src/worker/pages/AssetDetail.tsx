/** One asset's status, folded from the ledger. Headline number + recent
 *  activity. Worker subjects are blocked server-side (crew tier) -> 403,
 *  which we render as a friendly "restricted" card. */
import { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { ApiError } from '../../services/api';
import { useI18n } from '../i18n';
import { workerApi, type EntityDetail } from '../workerApi';
import { Screen, Spinner } from '../components/ui';

export default function AssetDetail() {
  const { t } = useI18n();
  const navigate = useNavigate();
  const { type = '', id = '' } = useParams<{ type: string; id: string }>();
  const [detail, setDetail] = useState<EntityDetail | null>(null);
  const [error, setError] = useState<'restricted' | 'missing' | null>(null);

  useEffect(() => {
    let alive = true;
    workerApi
      .asset(type, id)
      .then((d) => alive && setDetail(d))
      .catch((e) => {
        if (!alive) return;
        if (e instanceof ApiError && e.status === 403) setError('restricted');
        else setError('missing');
      });
    return () => {
      alive = false;
    };
  }, [type, id]);

  if (error) {
    return (
      <Screen>
        <Header onBack={() => navigate(-1)} title={decodeURIComponent(id)} />
        <div className="rounded-2xl border-2 border-border bg-card p-6 text-center text-muted-foreground">
          {error === 'restricted'
            ? '🔒'
            : '∅'}
          <p className="mt-2 text-lg">{error === 'restricted' ? '—' : t('asset.empty')}</p>
        </div>
      </Screen>
    );
  }

  if (!detail) return <Spinner label={t('common.loading')} />;

  const headline = headlineMetric(detail, t);

  return (
    <Screen>
      <Header onBack={() => navigate(-1)} title={decodeURIComponent(id)} />

      {headline ? (
        <div className="rounded-2xl bg-card border border-border p-5 text-center">
          <div className="font-mono text-5xl font-bold text-foreground tabular-nums">{headline.value}</div>
          <div className="text-muted-foreground mt-1">{headline.label}</div>
        </div>
      ) : null}

      <div>
        <h2 className="text-lg font-semibold text-foreground mb-2">{t('asset.events')}</h2>
        <div className="space-y-2">
          {detail.events.slice(-12).reverse().map((e) => (
            <div key={e.id} className="rounded-xl border border-border bg-card px-4 py-3">
              <div className="flex justify-between text-sm">
                <span className="font-medium text-foreground">{e.kind}</span>
                <span className="text-muted-foreground">{new Date(e.occurred_at).toLocaleDateString()}</span>
              </div>
              {e.status !== 'confirmed' ? (
                <span className="text-xs text-warning">{e.status}</span>
              ) : null}
            </div>
          ))}
        </div>
      </div>
    </Screen>
  );
}

function Header({ onBack, title }: { onBack: () => void; title: string }) {
  return (
    <div className="flex items-center gap-3">
      <button onClick={onBack} className="w-12 h-12 rounded-full bg-secondary text-2xl active:scale-95" aria-label="back">
        ‹
      </button>
      <h1 className="text-xl font-bold text-foreground truncate">{title}</h1>
    </div>
  );
}

function headlineMetric(
  d: EntityDetail,
  t: (k: string) => string,
): { value: string; label: string } | null {
  if (d.subject_type === 'material' && 'on_hand_qty' in d.metrics) {
    const unit = typeof d.state.unit === 'string' ? ` ${d.state.unit}` : '';
    return { value: `${d.metrics.on_hand_qty}${unit}`, label: t('asset.onHand') };
  }
  if (d.subject_type === 'equipment' && 'utilization' in d.metrics) {
    return {
      value: `${Math.round((d.metrics.utilization ?? 0) * 100)}%`,
      label: t('asset.utilization'),
    };
  }
  return null;
}
