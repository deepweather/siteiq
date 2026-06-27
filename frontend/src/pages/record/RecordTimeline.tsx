import { useCallback, useEffect, useState } from 'react';
import { recordApi, type DayRollup, type SiteEventDTO } from '../../services/recordApi';
import { EventRow } from './EventRow';
import { fmtDate } from './format';

/** Flight recorder: pick a day, see everything that happened, grouped by hour. */
export default function RecordTimeline({ refreshKey }: { refreshKey: number }) {
  const [days, setDays] = useState<DayRollup[]>([]);
  const [activeDate, setActiveDate] = useState<string | null>(null);
  const [events, setEvents] = useState<SiteEventDTO[]>([]);
  const [loading, setLoading] = useState(true);

  const loadDays = useCallback(async () => {
    const r = await recordApi.listDays();
    setDays(r.days);
    setActiveDate((cur) => cur ?? (r.days.length ? r.days[r.days.length - 1].date : null));
  }, []);

  useEffect(() => {
    loadDays();
  }, [loadDays, refreshKey]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    recordApi
      .getTimeline(activeDate ?? undefined)
      .then((r) => {
        if (cancelled) return;
        setEvents(r.events);
        if (!activeDate && r.date) setActiveDate(r.date);
      })
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [activeDate, refreshKey]);

  const byHour = groupByHour(events);

  return (
    <div className="flex gap-4 min-h-0">
      <div className="w-44 shrink-0">
        <div className="text-xs uppercase tracking-wide text-muted-foreground mb-2 px-1">
          Days
        </div>
        <div className="space-y-1 max-h-[60vh] overflow-auto pr-1">
          {days.map((d) => (
            <button
              key={d.date}
              onClick={() => setActiveDate(d.date)}
              className={[
                'w-full text-left rounded-md px-2.5 py-1.5 text-sm',
                d.date === activeDate
                  ? 'bg-primary/15 text-primary'
                  : 'hover:bg-secondary text-foreground',
              ].join(' ')}
            >
              <div className="font-medium">{fmtDate(d.date + 'T12:00:00')}</div>
              <div className="text-[11px] text-muted-foreground font-mono">
                {d.event_count} events · {d.workers_active} crew
              </div>
            </button>
          ))}
          {days.length === 0 && (
            <div className="text-sm text-muted-foreground px-1">No history yet.</div>
          )}
        </div>
      </div>

      <div className="flex-1 min-w-0">
        {loading ? (
          <div className="px-4 py-6 text-sm text-muted-foreground">Loading…</div>
        ) : events.length === 0 ? (
          <div className="px-4 py-10 text-center text-sm text-muted-foreground">
            Nothing recorded on this day.
          </div>
        ) : (
          <div className="space-y-4">
            {byHour.map(([hour, evs]) => (
              <div key={hour}>
                <div className="text-xs font-mono text-muted-foreground mb-1 px-1">
                  {hour}
                </div>
                <div className="rounded-xl border border-border bg-card divide-y divide-border">
                  {evs.map((e) => (
                    <EventRow key={e.id} event={e} />
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function groupByHour(events: SiteEventDTO[]): [string, SiteEventDTO[]][] {
  const map = new Map<string, SiteEventDTO[]>();
  for (const e of events) {
    const d = new Date(e.occurred_at);
    const hour = `${String(d.getHours()).padStart(2, '0')}:00`;
    const arr = map.get(hour) ?? [];
    arr.push(e);
    map.set(hour, arr);
  }
  return [...map.entries()].sort((a, b) => a[0].localeCompare(b[0]));
}
