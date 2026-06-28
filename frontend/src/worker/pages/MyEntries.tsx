/** My submissions, newest-first, plus anything still waiting in the offline
 *  outbox. Closes the loop: the worker sees their entry land and get
 *  confirmed/rejected by a supervisor. */
import { useCallback, useEffect, useState } from 'react';
import { useI18n } from '../i18n';
import { workerApi, type WorkerEvent } from '../workerApi';
import { outbox, type OutboxItem } from '../offlineQueue';
import { useOutbox } from '../hooks';
import { Screen, Spinner } from '../components/ui';

const STATUS_TINT: Record<string, string> = {
  proposed: 'text-warning',
  confirmed: 'text-success',
  rejected: 'text-destructive',
};

export default function MyEntries() {
  const { t } = useI18n();
  const { pending } = useOutbox();
  const [entries, setEntries] = useState<WorkerEvent[] | null>(null);
  const [queued, setQueued] = useState<OutboxItem[]>([]);

  const load = useCallback(() => {
    workerApi
      .myEntries()
      .then((r) => setEntries(r.entries))
      .catch(() => setEntries([]));
    outbox.list().then(setQueued);
  }, []);

  useEffect(() => {
    load();
    const onFocus = () => load();
    window.addEventListener('focus', onFocus);
    const handle = window.setInterval(load, 10000);
    return () => {
      window.removeEventListener('focus', onFocus);
      window.clearInterval(handle);
    };
  }, [load, pending]);

  return (
    <Screen>
      <h1 className="text-2xl font-bold text-foreground">{t('entries.title')}</h1>

      {queued.map((q) => (
        <div key={q.client_event_id} className="rounded-2xl border-2 border-warning/40 bg-warning/5 px-4 py-3">
          <div className="flex justify-between">
            <span className="font-semibold text-foreground">{t(`action.${q.kind}`)}</span>
            <span className="text-sm text-warning">⏳ {t('entries.pendingSync')}</span>
          </div>
        </div>
      ))}

      {entries === null ? (
        <Spinner label={t('common.loading')} />
      ) : entries.length === 0 && queued.length === 0 ? (
        <p className="text-center text-muted-foreground py-12 text-lg">{t('entries.empty')}</p>
      ) : (
        <div className="space-y-3">
          {entries.map((e) => (
            <div key={e.id} className="rounded-2xl border border-border bg-card px-4 py-3">
              <div className="flex justify-between">
                <span className="font-semibold text-foreground">{e.kind}</span>
                <span className="text-sm text-muted-foreground">
                  {new Date(e.occurred_at).toLocaleDateString()}
                </span>
              </div>
              <span className={`text-sm ${STATUS_TINT[e.status] ?? 'text-muted-foreground'}`}>
                {t(`entries.status.${e.status}`)}
              </span>
            </div>
          ))}
        </div>
      )}
    </Screen>
  );
}
