import { useCallback, useEffect, useState } from 'react';
import {
  recordApi,
  type SiteEventDTO,
  type VerifyResult,
} from '../../services/recordApi';
import { EventRow } from './EventRow';

const KIND_OPTIONS = [
  '',
  'worker.timesheet',
  'equipment.utilization',
  'equipment.state_changed',
  'material.delivered',
  'inspection.passed',
  'incident.flagged',
  'optimization.applied',
  'note',
];

/** Raw searchable ledger + tamper-evidence badge. */
export default function RecordLedger({ refreshKey }: { refreshKey: number }) {
  const [events, setEvents] = useState<SiteEventDTO[]>([]);
  const [verify, setVerify] = useState<VerifyResult | null>(null);
  const [kind, setKind] = useState('');
  const [source, setSource] = useState('');
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [evs, v] = await Promise.all([
        recordApi.listEvents({
          kind: kind || undefined,
          source: source || undefined,
          order: 'desc',
          limit: 200,
        }),
        recordApi.verify(),
      ]);
      setEvents(evs.events);
      setVerify(v);
    } finally {
      setLoading(false);
    }
  }, [kind, source]);

  useEffect(() => {
    load();
  }, [load, refreshKey]);

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-3 flex-wrap">
        {verify && (
          <span
            className={[
              'text-xs px-2.5 py-1 rounded-md font-medium',
              verify.ok
                ? 'bg-emerald-100 text-emerald-700'
                : 'bg-red-100 text-red-700',
            ].join(' ')}
            data-testid="verify-badge"
          >
            {verify.ok
              ? `Chain verified · ${verify.count} events`
              : `Chain BROKEN at #${verify.broken_at}`}
          </span>
        )}
        <div className="flex-1" />
        <select
          value={kind}
          onChange={(e) => setKind(e.target.value)}
          className="text-sm rounded-md border border-border bg-card px-2 py-1"
        >
          {KIND_OPTIONS.map((k) => (
            <option key={k} value={k}>
              {k || 'All kinds'}
            </option>
          ))}
        </select>
        <select
          value={source}
          onChange={(e) => setSource(e.target.value)}
          className="text-sm rounded-md border border-border bg-card px-2 py-1"
        >
          {['', 'generator', 'simulation', 'human', 'camera', 'system'].map((s) => (
            <option key={s} value={s}>
              {s || 'All sources'}
            </option>
          ))}
        </select>
      </div>

      {loading ? (
        <div className="px-4 py-6 text-sm text-muted-foreground">Loading ledger…</div>
      ) : (
        <div className="rounded-xl border border-border bg-card divide-y divide-border">
          {events.map((e) => (
            <EventRow key={e.id} event={e} showDate />
          ))}
          {events.length === 0 && (
            <div className="px-4 py-10 text-center text-sm text-muted-foreground">
              No events match.
            </div>
          )}
        </div>
      )}
    </div>
  );
}
