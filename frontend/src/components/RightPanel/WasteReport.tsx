import { useState } from 'react';
import type { WasteSummary } from '../../types/analytics';
import { formatCurrency, formatPercent } from '../../utils/formatting';

interface WasteReportProps {
  waste: WasteSummary | null;
  baseline: WasteSummary | null;
  savings: { toilet: number; material: number; equipment: number; total: number } | null;
  pendingSavingsMonthly: number;
  onSwitchToOptimize: () => void;
}

export function WasteReport({ waste, baseline, savings, pendingSavingsMonthly, onSwitchToOptimize }: WasteReportProps) {
  if (!waste) {
    return (
      <div className="flex items-center justify-center h-40 text-muted-foreground text-sm">
        Waiting for data...
      </div>
    );
  }

  const hasSavings = savings && savings.total > 100;
  const baselineTotal = baseline?.total_monthly || waste.total_monthly;

  return (
    <div className="space-y-4">
      {/* Hero waste number */}
      <div className="bg-destructive/8 border border-destructive/20 rounded-lg p-4">
        {hasSavings ? (
          <>
            <div className="text-xs text-muted-foreground font-medium">Monthly Waste — Optimized</div>
            <div className="font-mono text-3xl font-bold text-foreground tabular-nums mt-1">
              {formatCurrency(waste.total_monthly)}
            </div>
            <div className="flex items-center gap-2 mt-2">
              <span className="inline-flex items-center gap-1 font-mono text-xs font-semibold text-success bg-success/10 px-2 py-1 rounded-full tabular-nums">
                {formatCurrency(savings.total)} saved/mo
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
              {formatCurrency(waste.total_monthly)}
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
          label="Facility Access Loss"
          sublabel="Toilet & break travel time"
          daily={waste.toilet_walk_daily}
          monthly={waste.toilet_walk_monthly}
          detail={
            <ZoneBreakdown
              items={waste.zone_metrics.map(z => ({
                label: z.zone_id.replace('zone-', '').toUpperCase(),
                value: z.daily_toilet_walk_minutes,
                max: 200,
                suffix: ' min',
              }))}
            />
          }
        />
        <CostRow
          label="Equipment Idle"
          sublabel="Rental cost during downtime"
          daily={waste.equipment_idle_daily}
          monthly={waste.equipment_idle_monthly}
          detail={
            <div className="space-y-2">
              {waste.equipment_metrics.map(e => (
                <div key={e.asset_id} className="flex items-center gap-2 text-xs">
                  <span className="w-20 text-muted-foreground capitalize">{e.subtype.replace('_', ' ')}</span>
                  <div className="flex-1 h-2 bg-secondary rounded-full overflow-hidden flex">
                    <div className="h-full bg-success rounded-l-full" style={{ width: `${e.utilization_rate * 100}%` }} />
                    <div className="h-full bg-destructive/40 rounded-r-full" style={{ width: `${(1 - e.utilization_rate) * 100}%` }} />
                  </div>
                  <span className="font-mono text-foreground w-10 text-right tabular-nums">{formatPercent(e.utilization_rate)}</span>
                </div>
              ))}
            </div>
          }
        />
        <CostRow
          label="Material Staging"
          sublabel="Walk distance to misplaced materials"
          daily={waste.material_handling_daily}
          monthly={waste.material_handling_monthly}
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
        className={`w-full p-3 text-left hover:bg-secondary/50 ${hasDetail ? 'cursor-pointer' : 'cursor-default'}`}
        onClick={() => hasDetail && setOpen(!open)}
      >
        <div className="flex items-center gap-2 mb-0.5">
          {hasDetail && (
            <span className={`text-[10px] text-muted-foreground transition-transform ${open ? 'rotate-90' : ''}`}>
              &#9654;
            </span>
          )}
          <span className="text-sm font-medium text-foreground">{label}</span>
        </div>
        {sublabel && <div className="text-[10px] text-muted-foreground ml-4 mb-1">{sublabel}</div>}
        <div className="flex items-baseline gap-3 ml-4">
          <span className="font-mono text-sm font-semibold text-destructive tabular-nums">{formatCurrency(daily)}/day</span>
          <span className="font-mono text-xs text-muted-foreground tabular-nums">{formatCurrency(monthly)}/mo</span>
        </div>
      </button>
      {open && detail && (
        <div className="px-3 pb-3 pt-1 border-t border-border bg-secondary/30">
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

function ROICard({ wasteMonthly, savingsMonthly, pendingSavingsMonthly, hasSavings, onSwitchToOptimize }: {
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

function ZoneBreakdown({ items }: { items: { label: string; value: number; max: number; suffix: string }[] }) {
  return (
    <div className="space-y-2">
      {items.map(item => (
        <div key={item.label} className="flex items-center gap-2 text-xs">
          <span className="w-6 text-muted-foreground font-medium text-right">{item.label}</span>
          <div className="flex-1 h-2 bg-secondary rounded-full overflow-hidden">
            <div className="h-full bg-destructive/50 rounded-full" style={{ width: `${Math.min(100, (item.value / item.max) * 100)}%` }} />
          </div>
          <span className="font-mono text-foreground w-14 text-right tabular-nums">{item.value.toFixed(0)}{item.suffix}</span>
        </div>
      ))}
    </div>
  );
}
