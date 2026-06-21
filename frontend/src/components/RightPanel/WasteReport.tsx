import { useState, useMemo } from 'react';
import type { WasteSummary } from '../../types/analytics';
import type { Zone } from '../../types/site';
import { useAnimatedNumber } from '../../hooks/useAnimatedNumber';
import { formatCurrency, formatPercent } from '../../utils/formatting';

interface WasteReportProps {
  waste: WasteSummary | null;
  baseline: WasteSummary | null;
  savings: { toilet: number; material: number; equipment: number; total: number } | null;
  pendingSavingsMonthly: number;
  zones: Zone[];
  onSwitchToOptimize: () => void;
}

// Pretty asset labels — "crane-1" → "Tower Crane #1", etc.
const EQUIPMENT_TYPE_LABELS: Record<string, string> = {
  tower_crane: 'Tower Crane',
  concrete_pump: 'Concrete Pump',
  excavator: 'Excavator',
};

function formatEquipmentLabel(asset_id: string, subtype: string): string {
  const base = EQUIPMENT_TYPE_LABELS[subtype] || subtype.replace(/_/g, ' ');
  // "crane-1" → "#1"
  const numMatch = asset_id.match(/-(\d+)$/);
  return numMatch ? `${base} #${numMatch[1]}` : base;
}

export function WasteReport({ waste, baseline, savings, pendingSavingsMonthly, zones, onSwitchToOptimize }: WasteReportProps) {
  // ── Hooks: must run unconditionally on every render (Rules of Hooks).
  //    Computed values that depend on data flow into the JSX below the
  //    early-return guard.

  // zone_id → real human label ("zone-a" → "Block A"). Fallback to a
  // capitalised version of the ID if the zone list isn't loaded yet.
  const zoneLabel = useMemo(() => {
    const map = new Map(zones.map(z => [z.id, z.label]));
    return (id: string) => {
      const found = map.get(id);
      if (found) return found;
      // Fallback: "zone-a" → "Zone A" (capitalise the suffix too)
      const parts = id.split('-');
      if (parts.length === 2 && parts[0] === 'zone') {
        return `Zone ${parts[1].toUpperCase()}`;
      }
      return id;
    };
  }, [zones]);

  // Animate the hero waste number so apply-events visibly tick down
  // instead of snapping. Falls back to 0 when waste isn't loaded yet.
  const hasSavings = savings && savings.total > 100;
  const animatedMonthly = useAnimatedNumber(waste?.total_monthly ?? 0, 800);
  const animatedSavings = useAnimatedNumber(hasSavings ? savings.total : 0, 800);

  if (!waste) {
    return (
      <div className="flex items-center justify-center h-40 text-muted-foreground text-sm">
        Waiting for data...
      </div>
    );
  }

  const baselineTotal = baseline?.total_monthly || waste.total_monthly;

  return (
    <div className="space-y-4">
      {/* Hero waste number */}
      <div className="bg-destructive/8 border border-destructive/20 rounded-lg p-4">
        {hasSavings ? (
          <>
            <div className="text-xs text-muted-foreground font-medium">Monthly Waste — Optimized</div>
            <div className="font-mono text-3xl font-bold text-foreground tabular-nums mt-1">
              {formatCurrency(animatedMonthly)}
            </div>
            <div className="flex items-center gap-2 mt-2">
              <span className="inline-flex items-center gap-1 font-mono text-xs font-semibold text-success bg-success/10 px-2 py-1 rounded-full tabular-nums">
                {formatCurrency(animatedSavings)} saved/mo
              </span>
              <span className="text-muted-foreground text-xs line-through font-mono tabular-nums">
                {formatCurrency(baselineTotal)}
              </span>
            </div>
          </>
        ) : (
          <>
            <div className="text-xs text-destructive font-semibold uppercase tracking-wider">Recoverable Waste</div>
            <div className="font-mono text-4xl font-bold text-destructive tabular-nums mt-1">
              {formatCurrency(animatedMonthly)}
              <span className="text-lg text-destructive/60 font-medium">/mo</span>
            </div>
            <div className="text-xs text-muted-foreground mt-1.5">
              {formatCurrency(waste.total_daily)} lost every day this layout stays unchanged
            </div>
          </>
        )}
      </div>

      {/* ROI frame */}
      <ROICard
        wasteMonthly={waste.total_monthly}
        savingsMonthly={hasSavings ? savings.total : 0}
        pendingSavingsMonthly={pendingSavingsMonthly}
        hasSavings={!!hasSavings}
        onSwitchToOptimize={onSwitchToOptimize}
      />

      {/* Included services — vendor consolidation */}
      <IncludedServices />

      {/* Category rows */}
      <div className="space-y-1">
        <CostRow
          label="Toilet & break walks"
          sublabel="Time workers spend walking to facilities instead of working"
          daily={waste.toilet_walk_daily}
          monthly={waste.toilet_walk_monthly}
          detail={
            <ZoneCostBreakdown
              items={[...waste.zone_metrics]
                .filter(z => z.daily_toilet_walk_cost > 1)
                .sort((a, b) => b.daily_toilet_walk_cost - a.daily_toilet_walk_cost)
                .map(z => ({
                  label: zoneLabel(z.zone_id),
                  workers: z.num_workers,
                  cost: z.daily_toilet_walk_cost,
                  detail: `${z.daily_toilet_walk_minutes.toFixed(0)} min/day · ${z.avg_toilet_round_trip_min.toFixed(1)} min per trip`,
                }))}
              emptyMessage="No facility-walk waste detected this day."
            />
          }
        />
        <CostRow
          label="Equipment idle time"
          sublabel="Rental cost while equipment isn't operating"
          daily={waste.equipment_idle_daily}
          monthly={waste.equipment_idle_monthly}
          detail={
            <div className="space-y-2.5">
              {[...waste.equipment_metrics]
                .sort((a, b) => b.daily_idle_cost - a.daily_idle_cost)
                .map(e => (
                  <div key={e.asset_id} className="flex items-center gap-2 text-xs">
                    <div className="w-28 min-w-0">
                      <div className="text-foreground font-medium truncate">{formatEquipmentLabel(e.asset_id, e.subtype)}</div>
                      <div className="text-[10px] text-muted-foreground">{formatPercent(e.utilization_rate)} utilization</div>
                    </div>
                    <div className="flex-1 h-2 bg-secondary rounded-full overflow-hidden flex" title={`Active ${formatPercent(e.utilization_rate)} / Idle ${formatPercent(1 - e.utilization_rate)}`}>
                      <div className="h-full bg-success" style={{ width: `${e.utilization_rate * 100}%` }} />
                      <div className="h-full bg-destructive/40" style={{ width: `${(1 - e.utilization_rate) * 100}%` }} />
                    </div>
                    <span className="font-mono text-destructive w-16 text-right tabular-nums">{formatCurrency(e.daily_idle_cost)}/d</span>
                  </div>
                ))}
            </div>
          }
        />
        <CostRow
          label="Material in wrong place"
          sublabel="Workers walking further than necessary to fetch materials"
          daily={waste.material_handling_daily}
          monthly={waste.material_handling_monthly}
          detail={
            <ZoneCostBreakdown
              items={[...waste.zone_metrics]
                .filter(z => z.daily_material_walk_cost > 1)
                .sort((a, b) => b.daily_material_walk_cost - a.daily_material_walk_cost)
                .map(z => ({
                  label: zoneLabel(z.zone_id),
                  workers: z.num_workers,
                  cost: z.daily_material_walk_cost,
                  detail: `${z.avg_material_round_trip_min.toFixed(1)} min per material run`,
                }))}
              emptyMessage="Materials are well-staged today."
            />
          }
        />
      </div>
    </div>
  );
}

function CostRow({ label, sublabel, daily, monthly, detail }: {
  label: string;
  sublabel?: string;
  daily: number;
  monthly: number;
  detail?: React.ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const hasDetail = !!detail;

  return (
    <div className="border border-border rounded-lg overflow-hidden">
      <button
        type="button"
        aria-expanded={hasDetail ? open : undefined}
        className={`w-full p-3 text-left hover:bg-secondary/50 transition-colors ${hasDetail ? 'cursor-pointer' : 'cursor-default'}`}
        onClick={() => hasDetail && setOpen(!open)}
      >
        <div className="flex items-center justify-between gap-3">
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-1.5 mb-0.5">
              <span className="text-sm font-medium text-foreground">{label}</span>
              {hasDetail && (
                <span className="text-[10px] text-muted-foreground/70 font-normal">
                  {open ? 'hide breakdown' : 'view breakdown'}
                </span>
              )}
            </div>
            {sublabel && <div className="text-[11px] text-muted-foreground leading-snug">{sublabel}</div>}
          </div>
          {hasDetail && (
            <span
              className={`text-muted-foreground transition-transform shrink-0 ${open ? 'rotate-180' : ''}`}
              aria-hidden="true"
            >
              <svg width="10" height="10" viewBox="0 0 10 10" fill="none">
                <path d="M2 3.5L5 6.5L8 3.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
            </span>
          )}
        </div>
        <div className="flex items-baseline gap-3 mt-2">
          <span className="font-mono text-sm font-semibold text-destructive tabular-nums">{formatCurrency(daily)}/day</span>
          <span className="font-mono text-xs text-muted-foreground tabular-nums">{formatCurrency(monthly)}/mo</span>
        </div>
      </button>
      {open && detail && (
        <div className="px-3 pb-3 pt-2 border-t border-border bg-secondary/30">
          {detail}
        </div>
      )}
    </div>
  );
}

function IncludedServices() {
  return (
    <div className="border border-border rounded-lg overflow-hidden">
      <div className="px-3 py-2 bg-secondary/50 border-b border-border flex items-center justify-between">
        <span className="text-[10px] text-muted-foreground font-semibold uppercase tracking-wider">Included at no extra cost</span>
        <span className="text-[10px] text-success font-mono font-semibold">€0/mo</span>
      </div>
      <div className="p-2.5 space-y-1.5">
        <ServiceRow icon="🔒" label="24/7 Site Security" vendor="replaces BauWatch" vendorCost="€1.200/mo" />
        <ServiceRow icon="🦺" label="PPE Compliance" vendor="replaces manual audits" vendorCost="€400/mo" />
        <ServiceRow icon="📊" label="Progress Tracking" vendor="replaces Buildots" vendorCost="€2.500/mo" />
      </div>
    </div>
  );
}

function ServiceRow({ icon, label, vendor, vendorCost }: { icon: string; label: string; vendor: string; vendorCost: string }) {
  return (
    <div className="flex items-center gap-2 text-xs">
      <span className="text-sm w-5 text-center">{icon}</span>
      <span className="text-foreground font-medium flex-1">{label}</span>
      <span className="text-muted-foreground text-[10px]">{vendor}</span>
      <span className="text-muted-foreground text-[10px] line-through font-mono tabular-nums">{vendorCost}</span>
    </div>
  );
}

function ROICard({ savingsMonthly, pendingSavingsMonthly, hasSavings, onSwitchToOptimize }: {
  wasteMonthly: number;
  savingsMonthly: number;
  pendingSavingsMonthly: number;
  hasSavings: boolean;
  onSwitchToOptimize: () => void;
}) {
  const systemCost = 2000;
  const recoveredMonthly = hasSavings ? savingsMonthly : pendingSavingsMonthly;
  const paybackRatio = recoveredMonthly > 0 ? Math.round(recoveredMonthly / systemCost) : 0;
  const annualNet = (recoveredMonthly - systemCost) * 12;

  return (
    <div className="border border-border rounded-lg overflow-hidden">
      <div className="px-3 py-2.5 bg-secondary/50 border-b border-border">
        <div className="text-[10px] text-muted-foreground font-semibold uppercase tracking-wider">SiteIQ ROI</div>
      </div>
      <div className="p-3 space-y-2">
        <div className="flex items-center justify-between text-xs">
          <span className="text-muted-foreground">System cost</span>
          <span className="font-mono text-foreground tabular-nums">{formatCurrency(systemCost)}/mo</span>
        </div>
        <div className="flex items-center justify-between text-xs">
          <span className="text-muted-foreground">{hasSavings ? 'Recovered' : 'Recoverable'}</span>
          <span className="font-mono text-success font-semibold tabular-nums">{formatCurrency(recoveredMonthly)}/mo</span>
        </div>
        <div className="border-t border-border pt-2 flex items-center justify-between">
          <span className="text-xs font-medium text-foreground">Payback</span>
          <span className="font-mono text-sm font-bold text-primary tabular-nums">{paybackRatio}x</span>
        </div>
        {annualNet > 0 && (
          <div className="flex items-center justify-between text-xs">
            <span className="text-muted-foreground">Net annual value</span>
            <span className="font-mono text-success font-semibold tabular-nums">{formatCurrency(annualNet)}</span>
          </div>
        )}
      </div>
      {!hasSavings && pendingSavingsMonthly > 0 && (
        <button
          onClick={onSwitchToOptimize}
          className="w-full py-2.5 text-xs font-semibold bg-success text-white hover:bg-success/90 transition-colors"
        >
          Apply optimizations — recover {formatCurrency(pendingSavingsMonthly)}/mo
        </button>
      )}
    </div>
  );
}

function ZoneCostBreakdown({ items, emptyMessage }: {
  items: { label: string; workers: number; cost: number; detail?: string }[];
  emptyMessage?: string;
}) {
  if (items.length === 0) {
    return (
      <div className="text-xs text-muted-foreground italic py-1">
        {emptyMessage || 'No data yet.'}
      </div>
    );
  }
  const maxCost = Math.max(...items.map(i => i.cost), 1);
  return (
    <div className="space-y-2.5">
      {items.map(item => (
        <div key={item.label} className="space-y-1">
          <div className="flex items-baseline justify-between gap-2 text-xs">
            <div className="flex items-baseline gap-1.5 min-w-0">
              <span className="text-foreground font-medium truncate">{item.label}</span>
              <span className="text-[10px] text-muted-foreground shrink-0">{item.workers} {item.workers === 1 ? 'worker' : 'workers'}</span>
            </div>
            <span className="font-mono text-destructive font-semibold tabular-nums shrink-0">{formatCurrency(item.cost)}/d</span>
          </div>
          <div className="h-1.5 bg-secondary rounded-full overflow-hidden">
            <div
              className="h-full bg-destructive/50 rounded-full transition-all"
              style={{ width: `${(item.cost / maxCost) * 100}%` }}
            />
          </div>
          {item.detail && (
            <div className="text-[10px] text-muted-foreground">{item.detail}</div>
          )}
        </div>
      ))}
    </div>
  );
}
