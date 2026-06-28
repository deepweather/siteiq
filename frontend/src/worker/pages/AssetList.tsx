/** Assets tab + lookup: searchable material / equipment / zone status. */
import { useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useI18n } from '../i18n';
import { workerApi, type WorkerAsset } from '../workerApi';
import { Screen, Spinner, ChipGroup } from '../components/ui';

const TYPE_EMOJI: Record<string, string> = { material: '🧱', equipment: '🏗️', zone: '📍' };

export default function AssetList() {
  const { t } = useI18n();
  const navigate = useNavigate();
  const [type, setType] = useState<string>('');
  const [q, setQ] = useState('');
  const [assets, setAssets] = useState<WorkerAsset[] | null>(null);

  // Debounced fetch on type/query change.
  useEffect(() => {
    let alive = true;
    const handle = setTimeout(() => {
      workerApi
        .assets(type || undefined, q || undefined)
        .then((r) => alive && setAssets(r.assets))
        .catch(() => alive && setAssets([]));
    }, 200);
    return () => {
      alive = false;
      clearTimeout(handle);
    };
  }, [type, q]);

  const typeChoices = useMemo(
    () => [
      { id: '', label: t('assets.all') },
      { id: 'material', label: t('assets.material') },
      { id: 'equipment', label: t('assets.equipment') },
      { id: 'zone', label: t('assets.zone') },
    ],
    [t],
  );

  return (
    <Screen>
      <input
        type="search"
        inputMode="search"
        placeholder={t('assets.search')}
        value={q}
        onChange={(e) => setQ(e.target.value)}
        className="w-full min-h-[60px] rounded-2xl border-2 border-border bg-card px-5 text-lg text-foreground outline-none focus:border-primary"
      />
      <ChipGroup choices={typeChoices} value={type} onSelect={setType} />

      {assets === null ? (
        <Spinner label={t('common.loading')} />
      ) : assets.length === 0 ? (
        <p className="text-center text-muted-foreground py-12 text-lg">{t('asset.empty')}</p>
      ) : (
        <div className="space-y-3">
          {assets.map((a) => (
            <button
              key={`${a.subject_type}/${a.subject_id}`}
              onClick={() => navigate(`/assets/${a.subject_type}/${encodeURIComponent(a.subject_id)}`)}
              className="w-full rounded-2xl border border-border bg-card p-4 flex items-center gap-4 text-left active:scale-[0.99] transition-transform"
            >
              <span className="text-3xl" aria-hidden>{TYPE_EMOJI[a.subject_type] ?? '•'}</span>
              <span className="flex-1 min-w-0">
                <span className="block text-lg font-semibold text-foreground truncate">
                  {a.descriptor || a.subject_id}
                </span>
                <span className="block text-sm text-muted-foreground">{statusLine(a, t)}</span>
              </span>
              <span className="text-muted-foreground text-2xl" aria-hidden>›</span>
            </button>
          ))}
        </div>
      )}
    </Screen>
  );
}

function statusLine(a: WorkerAsset, t: (k: string) => string): string {
  if (a.subject_type === 'material' && 'on_hand_qty' in a.metrics) {
    const unit = typeof a.state.unit === 'string' ? ` ${a.state.unit}` : '';
    return `${a.metrics.on_hand_qty}${unit} ${t('asset.onHand')}`;
  }
  if (a.subject_type === 'equipment' && 'utilization' in a.metrics) {
    return `${t('asset.utilization')} ${Math.round((a.metrics.utilization ?? 0) * 100)}%`;
  }
  if (a.last_state) return a.last_state;
  return a.subject_id;
}
