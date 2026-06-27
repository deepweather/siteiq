/**
 * WasteReport — the cost story.
 *
 * The single most important pixels in the product. Visual order:
 *   1. Hero red number (monthly recoverable waste, animated).
 *   2. "EUR X lost every day this layout stays unchanged" subtext.
 *   3. Compact ROI strip (cost / payback / annual net).
 *   4. Big green APPLY ALL CTA with the recovered amount baked in.
 *   5. Inline expander: N optimisations, with per-rec Apply buttons.
 *   6. "What's bleeding" rows (Toilet / Equipment / Materials / vertical /
 *      shoring-compliance).
 *   7. "Included at no extra cost" — vendor-replacement framing, small.
 *
 * No tabs. One mode. Optimised for a 3-minute demo viewer: their eye
 * lands on the number, jumps to the CTA, presses it.
 */

import { useState, useMemo } from 'react';
import type { Recommendation, WasteSummary } from '../../types/analytics';
import type { Zone } from '../../types/site';
import { useAnimatedNumber } from '../../hooks/useAnimatedNumber';
import { formatCurrency, formatPercent } from '../../utils/formatting';
import { Recommendations } from './Recommendations';

interface WasteReportProps {
  waste: WasteSummary | null;
  baseline: WasteSummary | null;
  savings: { toilet: number; material: number; equipment: number; total: number } | null;
  zones: Zone[];
  /** Recommendations + handlers are optional because some test harnesses
   *  render the report in isolation, without the live engine. The Apply
   *  CTA simply hides when there are no recs to apply. */
  recommendations?: Recommendation[];
  onRecsChange?: (recs: Recommendation[]) => void;
  onApplied?: (rec: Recommendation) => void;
}

const EQUIPMENT_TYPE_LABELS: Record<string, string> = {
  tower_crane: 'Tower Crane',
  concrete_pump: 'Concrete Pump',
  excavator: 'Excavator',
};

function formatEquipmentLabel(asset_id: string, subtype: string): string {
  const base = EQUIPMENT_TYPE_LABELS[subtype] || subtype.replace(/_/g, ' ');
  const numMatch = asset_id.match(/-(\d+)$/);
  return numMatch ? `${base} #${numMatch[1]}` : base;
}

export function WasteReport({ waste, baseline, savings, zones, recommendations = [], onRecsChange, onApplied }: WasteReportProps) {
  const zoneLabel = useMemo(() => {
    const map = new Map(zones.map((z) => [z.id, z.label]));
    return (id: string) => {
      const found = map.get(id);
      if (found) return found;
      const parts = id.split('-');
      if (parts.length === 2 && parts[0] === 'zone') return `Zone ${parts[1].toUpperCase()}`;
      return id;
    };
  }, [zones]);

  const hasSavings = !!savings && savings.total > 100;
  const animatedMonthly = useAnimatedNumber(waste?.total_monthly ?? 0, 800);
  const animatedSavings = useAnimatedNumber(hasSavings ? savings!.total : 0, 800);

  const [recsOpen, setRecsOpen] = useState(false);

  if (!waste) {
    return (
      <div className="flex items-center justify-center h-40 text-muted-foreground text-sm">
        Waiting for data…
      </div>
    );
  }

  const baselineTotal = baseline?.total_monthly || waste.total_monthly;
  const pendingRecs = recommendations.filter((r) => !r.applied);
  const pendingMonthly = pendingRecs.reduce((s, r) => s + r.monthly_savings, 0);
  const recoveredMonthly = hasSavings ? savings!.total : pendingMonthly;
  const systemCost = 2000;
  const paybackRatio = recoveredMonthly > 0 ? Math.round(recoveredMonthly / systemCost) : 0;
  const annualNet = (recoveredMonthly - systemCost) * 12;

  return (
    <div className="space-y-4">
      {/* Hero: the number */}
      <div className="rounded-lg border border-destructive/20 bg-destructive/8 p-4">
        {hasSavings ? (
          <>
            <div className="text-[10px] uppercase tracking-wider text-muted-foreground font-semibold">
              Monthly waste — optimised
            </div>
            <div className="mt-1 font-mono text-4xl font-bold text-foreground tabular-nums">
              {formatCurrency(animatedMonthly)}
              <span className="text-base text-muted-foreground font-medium">/mo</span>
            </div>
            <div className="mt-2 flex items-center gap-2 flex-wrap">
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
            <div className="text-[10px] uppercase tracking-wider text-destructive font-semibold">
              Recoverable waste
            </div>
            <div className="mt-1 font-mono text-4xl font-bold text-destructive tabular-nums leading-tight">
              {formatCurrency(animatedMonthly)}
              <span className="text-base text-destructive/60 font-medium">/mo</span>
            </div>
            <div className="text-xs text-muted-foreground mt-1.5">
              {formatCurrency(waste.total_daily)} lost every day this layout stays unchanged
            </div>
          </>
        )}
      </div>

      {/* ROI strip — small, sets the why for the CTA */}
      <div className="grid grid-cols-3 gap-2 text-center">
        <RoiCell label="Cost" value={formatCurrency(systemCost) + '/mo'} />
        <RoiCell label="Payback" value={paybackRatio > 0 ? `${paybackRatio}×` : '—'} primary />
        <RoiCell label="Annual net" value={annualNet > 0 ? formatCurrency(annualNet) : '—'} success={annualNet > 0} />
      </div>

      {/* The big CTA + inline rec expander.
       *  We embed the full Recommendations component but hide it behind
       *  an expander so the dashboard's hero ordering stays clean. The
       *  component's own Apply All button is the primary CTA — it sits
       *  above the per-rec list inside the expander. */}
      {onRecsChange && (pendingRecs.length > 0 || recommendations.some((r) => r.applied)) ? (
        <div className="rounded-lg border border-border overflow-hidden">
          <button
            type="button"
            onClick={() => setRecsOpen((o) => !o)}
            aria-expanded={recsOpen}
            className={`w-full px-3 py-3 text-left flex items-center justify-between gap-3 ${
              pendingRecs.length > 0
                ? 'bg-success text-white hover:bg-success/90'
                : 'bg-secondary text-foreground hover:bg-secondary/80'
            }`}
          >
            <div className="flex items-baseline gap-2">
              <span className="text-sm font-semibold">
                {pendingRecs.length > 0
                  ? `Apply optimisations — recover`
                  : 'All optimisations applied'}
              </span>
              {pendingRecs.length > 0 && (
                <span className="font-mono text-sm font-bold tabular-nums">
                  {formatCurrency(pendingMonthly)}/mo
                </span>
              )}
            </div>
            <div className="flex items-center gap-2 text-[11px] opacity-90">
              <span>{pendingRecs.length > 0 ? `${pendingRecs.length} ↓` : `${recommendations.length} ✓`}</span>
            </div>
          </button>
          {recsOpen && (
            <div className="p-3 border-t border-border bg-card">
              <Recommendations
                recommendations={recommendations}
                onRecsChange={onRecsChange}
                onApplied={onApplied}
                zones={zones}
              />
            </div>
          )}
        </div>
      ) : null}

      {/* What's bleeding — the story behind the number */}
      <div className="space-y-1">
        <div className="text-[10px] uppercase tracking-wider text-muted-foreground font-semibold pl-1">
          What's bleeding
        </div>
        <CostRow
          label="Toilet & break walks"
          sublabel="Time workers spend walking to facilities instead of working"
          daily={waste.toilet_walk_daily}
          monthly={waste.toilet_walk_monthly}
          detail={
            <ZoneCostBreakdown
              items={[...waste.zone_metrics]
                .filter((z) => z.daily_toilet_walk_cost > 1)
                .sort((a, b) => b.daily_toilet_walk_cost - a.daily_toilet_walk_cost)
                .map((z) => ({
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
                .map((e) => (
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
                .filter((z) => z.daily_material_walk_cost > 1)
                .sort((a, b) => b.daily_material_walk_cost - a.daily_material_walk_cost)
                .map((z) => ({
                  label: zoneLabel(z.zone_id),
                  workers: z.num_workers,
                  cost: z.daily_material_walk_cost,
                  detail: `${z.avg_material_round_trip_min.toFixed(1)} min per material run`,
                }))}
              emptyMessage="Materials are well-staged today."
            />
          }
        />
        {(waste.vertical_transport_daily ?? 0) > 0 && (
          <CostRow
            label="Vertical transport queues"
            sublabel="Time workers spend waiting for or riding elevators"
            daily={waste.vertical_transport_daily ?? 0}
            monthly={waste.vertical_transport_monthly ?? 0}
          />
        )}
        {(() => {
          const sc = waste.shoring_compliance ?? [];
          const bad = sc.filter((z) => z.compliance < 1.0);
          if (sc.length === 0 || bad.length === 0) return null;
          return <ShoringComplianceRow issues={bad} totalZones={sc.length} />;
        })()}
      </div>

      {/* Vendor-consolidation framing, small at the bottom */}
      <IncludedServices />
    </div>
  );
}

function RoiCell({ label, value, primary, success }: { label: string; value: string; primary?: boolean; success?: boolean }) {
  return (
    <div className="rounded-md border border-border bg-card px-2 py-1.5">
      <div className="text-[9px] uppercase tracking-wider text-muted-foreground font-semibold">{label}</div>
      <div className={`mt-0.5 font-mono text-sm font-bold tabular-nums ${
        primary ? 'text-primary' : success ? 'text-success' : 'text-foreground'
      }`}>{value}</div>
    </div>
  );
}

function ShoringComplianceRow({ issues, totalZones }: {
  issues: { zone_id: string; zone_label: string; nearest_distance_m?: number | null }[];
  totalZones: number;
}) {
  const [open, setOpen] = useState(false);
  return (
    <div className="border border-destructive/30 bg-destructive/5 rounded-lg overflow-hidden">
      <button
        type="button"
        aria-expanded={open}
        onClick={() => setOpen(!open)}
        className="w-full p-3 text-left hover:bg-destructive/10 transition-colors"
      >
        <div className="flex items-center justify-between gap-3">
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-1.5 mb-0.5">
              <span className="text-sm font-semibold text-destructive">Unshored excavation</span>
              <span className="text-[10px] text-muted-foreground/70 font-normal">
                {open ? 'hide zones' : 'view zones'}
              </span>
            </div>
            <div className="text-[11px] text-muted-foreground leading-snug">
              {issues.length} of {totalZones} excavation zones aren't backed by a sheet pile within 25 m. Safety + EU-DIN compliance risk.
            </div>
          </div>
          <span className={`text-muted-foreground transition-transform shrink-0 ${open ? 'rotate-180' : ''}`} aria-hidden="true">
            <svg width="10" height="10" viewBox="0 0 10 10" fill="none">
              <path d="M2 3.5L5 6.5L8 3.5" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </span>
        </div>
      </button>
      {open && (
        <div className="px-3 pb-3 pt-2 border-t border-destructive/30 bg-destructive/[0.03] space-y-1.5">
          {issues.map((z) => (
            <div key={z.zone_id} className="flex items-baseline justify-between gap-2 text-xs">
              <span className="text-foreground font-medium truncate">{z.zone_label}</span>
              <span className="font-mono text-destructive text-[11px] tabular-nums shrink-0">
                {z.nearest_distance_m != null
                  ? `nearest pile ${z.nearest_distance_m.toFixed(0)} m`
                  : 'no sheet pile on this level'}
              </span>
            </div>
          ))}
        </div>
      )}
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
            <span className={`text-muted-foreground transition-transform shrink-0 ${open ? 'rotate-180' : ''}`} aria-hidden="true">
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
  const maxCost = Math.max(...items.map((i) => i.cost), 1);
  return (
    <div className="space-y-2.5">
      {items.map((item) => (
        <div key={item.label} className="space-y-1">
          <div className="flex items-baseline justify-between gap-2 text-xs">
            <div className="flex items-baseline gap-1.5 min-w-0">
              <span className="text-foreground font-medium truncate">{item.label}</span>
              <span className="text-[10px] text-muted-foreground shrink-0">{item.workers} {item.workers === 1 ? 'worker' : 'workers'}</span>
            </div>
            <span className="font-mono text-destructive font-semibold tabular-nums shrink-0">{formatCurrency(item.cost)}/d</span>
          </div>
          <div className="h-1.5 bg-secondary rounded-full overflow-hidden">
            <div className="h-full bg-destructive/50 rounded-full transition-all" style={{ width: `${(item.cost / maxCost) * 100}%` }} />
          </div>
          {item.detail && <div className="text-[10px] text-muted-foreground">{item.detail}</div>}
        </div>
      ))}
    </div>
  );
}
