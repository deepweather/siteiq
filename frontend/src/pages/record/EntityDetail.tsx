import { useEffect, useState } from 'react';
import { recordApi, type EntityProjection } from '../../services/recordApi';
import { EventRow } from './EventRow';
import { fmtDate, metricLabel, metricValue, subjectIcon, subjectTypeLabel } from './format';

const HIDDEN_STATE_KEYS = ['worker_id', 'equipment_id', 'material_id', 'note', 'day'];

/** Full record for one subject: header, metrics, current state, and the
 *  clickable event history. Shared by the entity drawer. */
export default function EntityDetail({
  subjectType,
  subjectId,
}: {
  subjectType: string;
  subjectId: string;
}) {
  const [proj, setProj] = useState<EntityProjection | null>(null);
  const [loading, setLoading] = useState(true);
  const [notFound, setNotFound] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setNotFound(false);
    recordApi
      .getEntity(subjectType, subjectId)
      .then((p) => !cancelled && setProj(p))
      .catch(() => !cancelled && setNotFound(true))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [subjectType, subjectId]);

  if (loading) {
    return <div className="px-1 py-6 text-sm text-muted-foreground">Loading…</div>;
  }
  if (notFound || !proj) {
    return (
      <div className="px-1 py-6 text-sm text-muted-foreground">
        No record for {subjectType}:{subjectId} yet.
      </div>
    );
  }

  const metricEntries = Object.entries(proj.metrics ?? {});
  const stateEntries = Object.entries(proj.state ?? {}).filter(
    ([k]) => !HIDDEN_STATE_KEYS.includes(k),
  );
  const recentEvents = [...proj.events].reverse().slice(0, 50);

  return (
    <div className="space-y-5">
      <div className="flex items-center gap-3">
        <span className="text-2xl" aria-hidden="true">
          {subjectIcon(proj.subject_type)}
        </span>
        <div className="min-w-0">
          <h2 className="text-xl font-semibold truncate">{proj.subject_id}</h2>
          <div className="text-xs text-muted-foreground">
            {subjectTypeLabel(proj.subject_type)} · {proj.event_count} events
            {proj.last_seen ? ` · last seen ${fmtDate(proj.last_seen)}` : ''}
          </div>
        </div>
      </div>

      {metricEntries.length > 0 && (
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
          {metricEntries.map(([k, v]) => (
            <div key={k} className="rounded-xl border border-border bg-card p-3">
              <div className="text-xs text-muted-foreground mb-1">{metricLabel(k)}</div>
              <div className="text-lg font-mono tabular-nums">{metricValue(k, v)}</div>
            </div>
          ))}
        </div>
      )}

      {stateEntries.length > 0 && (
        <div className="rounded-xl border border-border bg-card p-4">
          <div className="text-sm font-medium mb-2">Current state</div>
          <dl className="grid grid-cols-2 gap-x-6 gap-y-1 text-sm">
            {stateEntries.map(([k, v]) => (
              <div key={k} className="flex justify-between gap-2">
                <dt className="text-muted-foreground">{metricLabel(k)}</dt>
                <dd className="font-mono truncate">{String(v)}</dd>
              </div>
            ))}
          </dl>
        </div>
      )}

      <div className="rounded-xl border border-border bg-card overflow-hidden">
        <div className="px-4 py-3 text-sm font-medium border-b border-border">
          History ({recentEvents.length} most recent)
        </div>
        <div className="divide-y divide-border">
          {recentEvents.map((e) => (
            <EventRow key={e.id} event={e} showDate />
          ))}
        </div>
      </div>
    </div>
  );
}
