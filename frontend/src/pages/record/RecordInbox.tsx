import { useCallback, useEffect, useState } from 'react';
import { recordApi, type SiteEventDTO } from '../../services/recordApi';
import { EventRow } from './EventRow';

interface Props {
  canWrite: boolean;
  onChanged?: () => void;
}

/** Confirmation inbox: low-confidence proposed events awaiting a human.
 *  "Confirm, don't create" — the system proposes, the user approves. */
export default function RecordInbox({ canWrite, onChanged }: Props) {
  const [events, setEvents] = useState<SiteEventDTO[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const r = await recordApi.getInbox();
      setEvents(r.events);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const act = async (id: string, action: 'confirm' | 'reject') => {
    setBusy(id);
    try {
      if (action === 'confirm') await recordApi.confirmEvent(id);
      else await recordApi.rejectEvent(id);
      setEvents((prev) => prev.filter((e) => e.id !== id));
      onChanged?.();
    } finally {
      setBusy(null);
    }
  };

  if (loading) {
    return <div className="px-4 py-6 text-sm text-muted-foreground">Loading inbox…</div>;
  }

  if (events.length === 0) {
    return (
      <div className="px-4 py-10 text-center text-sm text-muted-foreground">
        <div className="text-2xl mb-2">✓</div>
        Inbox zero. Every observation has been confirmed.
      </div>
    );
  }

  return (
    <div>
      <p className="text-sm text-muted-foreground mb-3">
        {events.length} observation{events.length === 1 ? '' : 's'} need review. Confirm to
        promote to ground truth, or reject to dismiss.
      </p>
      <div className="rounded-xl border border-border bg-card divide-y divide-border">
        {events.map((e) => (
          <EventRow key={e.id} event={e} showDate>
            {canWrite ? (
              <>
                <button
                  disabled={busy === e.id}
                  onClick={() => act(e.id, 'confirm')}
                  className="text-xs rounded-md bg-emerald-600 text-white px-2.5 py-1 hover:bg-emerald-700 disabled:opacity-50"
                >
                  Confirm
                </button>
                <button
                  disabled={busy === e.id}
                  onClick={() => act(e.id, 'reject')}
                  className="text-xs rounded-md border border-border px-2.5 py-1 text-muted-foreground hover:bg-secondary disabled:opacity-50"
                >
                  Reject
                </button>
              </>
            ) : (
              <span className="text-xs text-muted-foreground">read-only</span>
            )}
          </EventRow>
        ))}
      </div>
    </div>
  );
}
