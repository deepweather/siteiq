import { useEffect, useState } from 'react';
import { recordApi, type CostBreakdown } from '../../services/recordApi';
import { isNavigableSubject, useEntityNav } from './entityNav';
import { eur } from './format';

/** Costs as a projection over the ledger. Every figure traces to events. */
export default function RecordCosts({ refreshKey }: { refreshKey: number }) {
  const openEntity = useEntityNav();
  const [costs, setCosts] = useState<CostBreakdown | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    recordApi
      .getCosts()
      .then((c) => !cancelled && setCosts(c))
      .finally(() => !cancelled && setLoading(false));
    return () => {
      cancelled = true;
    };
  }, [refreshKey]);

  if (loading && !costs) {
    return <div className="px-4 py-6 text-sm text-muted-foreground">Loading costs…</div>;
  }
  if (!costs || costs.total_cost === 0) {
    return (
      <div className="px-4 py-10 text-center text-sm text-muted-foreground">
        No costs recorded yet. Generate demo data or let the simulation run.
      </div>
    );
  }

  const cards = [
    { label: 'Total recorded', value: costs.total_cost, accent: 'text-foreground' },
    { label: 'Labour', value: costs.labor_cost, accent: 'text-foreground' },
    { label: 'Equipment idle', value: costs.equipment_idle_cost, accent: 'text-foreground' },
    { label: 'Materials', value: costs.material_cost, accent: 'text-foreground' },
  ];

  const maxDay = Math.max(...costs.by_day.map((d) => d.amount), 1);

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {cards.map((c) => (
          <div key={c.label} className="rounded-xl border border-border bg-card p-4">
            <div className="text-xs text-muted-foreground mb-1">{c.label}</div>
            <div className={`text-2xl font-mono tabular-nums ${c.accent}`}>{eur(c.value)}</div>
          </div>
        ))}
      </div>

      <div className="rounded-xl border border-border bg-card p-4">
        <div className="text-sm font-medium mb-1">Recoverable: non-productive labour</div>
        <div className="text-xl font-mono tabular-nums text-primary">
          {eur(costs.labor_waste_cost)}
        </div>
        <p className="text-xs text-muted-foreground mt-1">
          Time workers spent walking and in vertical transport — the wedge SiteIQ targets.
        </p>
      </div>

      <div className="grid md:grid-cols-2 gap-4">
        <div className="rounded-xl border border-border bg-card p-4">
          <div className="text-sm font-medium mb-3">Daily spend</div>
          <div className="space-y-1.5">
            {costs.by_day.map((d) => (
              <div key={d.key} className="flex items-center gap-2 text-xs">
                <div className="w-20 shrink-0 font-mono text-muted-foreground">{d.key}</div>
                <div className="flex-1 bg-secondary rounded h-3 overflow-hidden">
                  <div
                    className="h-full bg-primary/70"
                    style={{ width: `${(d.amount / maxDay) * 100}%` }}
                  />
                </div>
                <div className="w-16 text-right font-mono tabular-nums">{eur(d.amount)}</div>
              </div>
            ))}
          </div>
        </div>

        <div className="rounded-xl border border-border bg-card p-4">
          <div className="text-sm font-medium mb-3">By zone</div>
          <div className="space-y-1.5">
            {costs.by_zone.slice(0, 10).map((z) => (
              <div key={z.key} className="flex items-center justify-between text-sm">
                <span className="text-muted-foreground">{z.label}</span>
                <span className="font-mono tabular-nums">{eur(z.amount)}</span>
              </div>
            ))}
            {costs.by_zone.length === 0 && (
              <div className="text-xs text-muted-foreground">No zone-attributed costs.</div>
            )}
          </div>
        </div>
      </div>

      <div className="rounded-xl border border-border bg-card overflow-hidden">
        <div className="px-4 py-3 text-sm font-medium border-b border-border">
          Cost lines (each traces to its supporting events)
        </div>
        <div className="divide-y divide-border max-h-80 overflow-auto">
          {costs.lines
            .filter((l) => l.category !== 'labor_waste')
            .slice(0, 200)
            .map((l, i) => {
              const navigable =
                !!l.subject_type && !!l.subject_id && isNavigableSubject(l.subject_type);
              return (
                <div key={i} className="px-4 py-2 flex items-center gap-3 text-sm">
                  <div className="flex-1 min-w-0">
                    {navigable ? (
                      <button
                        type="button"
                        onClick={() => openEntity(l.subject_type!, l.subject_id!)}
                        className="truncate text-left hover:text-primary hover:underline block w-full"
                      >
                        {l.label}
                      </button>
                    ) : (
                      <div className="truncate">{l.label}</div>
                    )}
                    <div className="text-[11px] font-mono text-muted-foreground/70">
                      {l.category}
                      {l.occurred_on ? ` · ${l.occurred_on}` : ''}
                      {l.zone_id ? ` · ${l.zone_id}` : ''} ·{' '}
                      {l.supporting_event_ids.length} evt
                    </div>
                  </div>
                  <div className="font-mono tabular-nums shrink-0">{eur(l.amount)}</div>
                </div>
              );
            })}
        </div>
      </div>
    </div>
  );
}
