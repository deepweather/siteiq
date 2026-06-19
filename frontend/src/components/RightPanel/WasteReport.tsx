import { useState } from 'react';
import type { WasteSummary } from '../../types/analytics';
import { formatCurrency, formatPercent } from '../../utils/formatting';

interface WasteReportProps {
  waste: WasteSummary | null;
  baseline: WasteSummary | null;
  savings: { toilet: number; material: number; equipment: number; total: number } | null;
}

export function WasteReport({ waste, baseline, savings }: WasteReportProps) {
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
      <div className="bg-secondary rounded-lg p-4">
        <div className="text-xs text-muted-foreground font-medium">Total Monthly Waste</div>
        <div className="font-mono text-3xl font-bold text-foreground tabular-nums mt-1">
          {formatCurrency(waste.total_monthly)}
        </div>
        {hasSavings ? (
          <div className="flex items-center gap-2 mt-1.5">
            <span className="inline-flex items-center gap-1 font-mono text-xs text-success bg-success/10 px-2 py-0.5 rounded-full tabular-nums">
              {formatCurrency(savings.total)} saved
            </span>
            <span className="text-muted-foreground text-xs">
              from {formatCurrency(baselineTotal)}
            </span>
          </div>
        ) : (
          <div className="text-xs text-muted-foreground mt-1.5">
            {formatCurrency(waste.total_daily)}/day across all categories
          </div>
        )}
      </div>

      <div className="space-y-1">
        <CostRow
          label="Unproductive Movement"
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
          daily={waste.material_handling_daily}
          monthly={waste.material_handling_monthly}
        />
      </div>
    </div>
  );
}

function CostRow({ label, daily, monthly, detail }: {
  label: string;
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
        <div className="flex items-center gap-2 mb-1">
          {hasDetail && (
            <span className={`text-[10px] text-muted-foreground transition-transform ${open ? 'rotate-90' : ''}`}>
              &#9654;
            </span>
          )}
          <span className="text-sm font-medium text-foreground">{label}</span>
        </div>
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
