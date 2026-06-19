import { useEffect, useState } from 'react';
import { fetchAssetDetail, type AssetDetail as AssetDetailData, type ActivityLogEntry } from '../../services/api';
import { formatCurrency, formatPercent, formatSimTime } from '../../utils/formatting';
import { TRADE_COLORS } from '../../utils/colors';

interface AssetDetailProps {
  assetId: string;
  onClose: () => void;
}

const STATE_LABELS: Record<string, string> = {
  working: 'Working',
  walking_to_toilet: 'Walking to toilet',
  at_toilet: 'At toilet',
  walking_to_break: 'Walking to break',
  at_break: 'On break',
  walking_to_material: 'Fetching material',
  carrying_material: 'Carrying material',
  walking_to_work: 'Returning to work',
  idle: 'Idle',
  operating: 'Operating',
  removed: 'Removed from site',
  active: 'Active',
  staged: 'Staged',
};

const SUBTYPE_LABELS: Record<string, string> = {
  structural: 'Structural',
  mep: 'MEP',
  finishing: 'Finishing',
  general: 'General',
  tower_crane: 'Tower Crane',
  concrete_pump: 'Concrete Pump',
  excavator: 'Excavator',
  toilet: 'Portable Toilet',
  breakroom: 'Break Room',
  office: 'Site Office',
  toolcrib: 'Tool Crib',
  rebar: 'Rebar',
  conduit: 'Conduit',
  drywall: 'Drywall',
  concrete: 'Concrete',
};

export function AssetDetail({ assetId, onClose }: AssetDetailProps) {
  const [data, setData] = useState<AssetDetailData | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const d = await fetchAssetDetail(assetId);
        if (!cancelled) setData(d);
      } catch {
        if (!cancelled) setError(true);
      }
    };
    load();
    const interval = setInterval(load, 1500);
    return () => { cancelled = true; clearInterval(interval); };
  }, [assetId]);

  if (error) {
    return (
      <div className="p-4 text-sm text-destructive">
        Asset not found. <button onClick={onClose} className="underline">Close</button>
      </div>
    );
  }

  if (!data) {
    return <div className="p-4 text-sm text-muted-foreground">Loading...</div>;
  }

  return (
    <div className="space-y-4">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            {data.type === 'worker' && (
              <span
                className="inline-block w-3 h-3 rounded-full shrink-0"
                style={{ backgroundColor: TRADE_COLORS[data.subtype] || '#a1a1aa' }}
              />
            )}
            <div className="text-lg font-semibold text-foreground truncate">
              {data.type === 'worker'
                ? `${SUBTYPE_LABELS[data.subtype] || data.subtype} Worker`
                : SUBTYPE_LABELS[data.subtype] || data.subtype}
            </div>
          </div>
          <div className="flex items-center gap-2 mt-1">
            {data.assigned_zone && (
              <span className="text-xs text-muted-foreground">
                {data.assigned_zone.replace('zone-', 'Zone ').toUpperCase()}
              </span>
            )}
            <span className="text-xs text-muted-foreground font-mono">{data.id}</span>
          </div>
        </div>
        <button
          onClick={onClose}
          className="w-7 h-7 rounded-md border border-border flex items-center justify-center text-muted-foreground hover:bg-secondary text-sm shrink-0"
        >
          &times;
        </button>
      </div>

      <div className="flex items-center gap-2">
        <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${
          data.state === 'working' || data.state === 'operating' || data.state === 'active'
            ? 'bg-success/10 text-success'
            : data.state === 'removed'
            ? 'bg-destructive/10 text-destructive'
            : 'bg-warning/10 text-warning'
        }`}>
          {STATE_LABELS[data.state] || data.state}
        </span>
      </div>

      {data.type === 'worker' && data.detail && <WorkerDetail detail={data.detail} />}
      {data.type === 'equipment' && data.detail && <EquipmentDetail detail={data.detail} />}
      {data.type === 'facility' && data.detail && <FacilityDetail detail={data.detail} />}
      {data.type === 'material' && data.detail && <MaterialDetail detail={data.detail} />}

      {data.activity_log && data.activity_log.length > 0 && (
        <ActivityLog entries={data.activity_log} />
      )}
    </div>
  );
}

function WorkerDetail({ detail }: { detail: NonNullable<AssetDetailData['detail']> }) {
  const tw = detail.time_working_s || 0;
  const twk = detail.time_walking_s || 0;
  const tf = detail.time_at_facilities_s || 0;
  const total = tw + twk + tf;
  const pctWork = total > 0 ? (tw / total) * 100 : 0;
  const pctWalk = total > 0 ? (twk / total) * 100 : 0;
  const pctFac = total > 0 ? (tf / total) * 100 : 0;

  return (
    <div className="space-y-3">
      <div className="border border-border rounded-lg p-3">
        <div className="text-xs text-muted-foreground font-medium mb-2">Productivity</div>
        <div className="flex items-center gap-3">
          <div className="font-mono text-2xl font-bold text-foreground tabular-nums">
            {formatPercent(detail.productivity || 0)}
          </div>
          <div className="flex-1 h-3 bg-secondary rounded-full overflow-hidden flex">
            <div className="h-full bg-success" style={{ width: `${pctWork}%` }} title={`Working: ${pctWork.toFixed(0)}%`} />
            <div className="h-full bg-warning" style={{ width: `${pctWalk}%` }} title={`Walking: ${pctWalk.toFixed(0)}%`} />
            <div className="h-full bg-muted-foreground/30" style={{ width: `${pctFac}%` }} title={`At facility: ${pctFac.toFixed(0)}%`} />
          </div>
        </div>
        <div className="flex gap-3 mt-2 text-[10px] text-muted-foreground">
          <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-sm bg-success" /> Working {pctWork.toFixed(0)}%</span>
          <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-sm bg-warning" /> Walking {pctWalk.toFixed(0)}%</span>
          <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-sm bg-muted-foreground/30" /> Facility {pctFac.toFixed(0)}%</span>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-2">
        <StatBox label="Distance today" value={`${(detail.total_distance_m || 0).toFixed(0)}m`} />
        <StatBox label="Toilet trips" value={String(detail.toilet_trips_today || 0)} />
        <StatBox label="Avg toilet RT" value={`${(detail.avg_toilet_round_trip_min || 0).toFixed(1)} min`} />
        <StatBox label="Material trips" value={String(detail.material_trips_today || 0)} />
        <StatBox label="Avg material RT" value={`${(detail.avg_material_round_trip_min || 0).toFixed(1)} min`} />
      </div>
    </div>
  );
}

function EquipmentDetail({ detail }: { detail: NonNullable<AssetDetailData['detail']> }) {
  const util = detail.utilization || 0;
  const cyclePct = (detail.operate_duration_s && detail.cycle_timer_s != null)
    ? (detail.cycle_timer_s / (detail.operate_duration_s || 1)) * 100
    : 0;

  return (
    <div className="space-y-3">
      <div className="border border-border rounded-lg p-3">
        <div className="text-xs text-muted-foreground font-medium mb-2">Utilization</div>
        <div className="flex items-center gap-3">
          <div className="font-mono text-2xl font-bold text-foreground tabular-nums">
            {formatPercent(util)}
          </div>
          <div className="flex-1 h-3 bg-secondary rounded-full overflow-hidden flex">
            <div className="h-full bg-success rounded-l-full" style={{ width: `${util * 100}%` }} />
            <div className="h-full bg-destructive/40 rounded-r-full" style={{ width: `${(1 - util) * 100}%` }} />
          </div>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-2">
        <StatBox label="Hours active" value={`${(detail.hours_active || 0).toFixed(1)}h`} />
        <StatBox label="Hours idle" value={`${(detail.hours_idle || 0).toFixed(1)}h`} />
        <StatBox label="Daily idle cost" value={formatCurrency(detail.daily_idle_cost || 0)} />
      </div>

      {detail.operate_duration_s != null && detail.idle_duration_s != null && (
        <div className="border border-border rounded-lg p-3">
          <div className="text-xs text-muted-foreground font-medium mb-2">Duty Cycle</div>
          <div className="text-xs text-muted-foreground">
            {Math.round((detail.operate_duration_s || 0) / 60)} min on / {Math.round((detail.idle_duration_s || 0) / 60)} min off
          </div>
          <div className="mt-2 h-2 bg-secondary rounded-full overflow-hidden">
            <div
              className="h-full bg-primary/50 rounded-full transition-all"
              style={{ width: `${Math.min(100, cyclePct)}%` }}
            />
          </div>
          <div className="text-[10px] text-muted-foreground mt-1 font-mono tabular-nums">
            Cycle: {Math.round(detail.cycle_timer_s || 0)}s elapsed
          </div>
        </div>
      )}
    </div>
  );
}

function FacilityDetail({ detail }: { detail: NonNullable<AssetDetailData['detail']> }) {
  const workers = detail.workers_present || [];
  return (
    <div className="space-y-3">
      <div className="border border-border rounded-lg p-3">
        <div className="text-xs text-muted-foreground font-medium mb-2">
          Workers Present ({workers.length})
        </div>
        {workers.length === 0 ? (
          <div className="text-xs text-muted-foreground">No workers currently here</div>
        ) : (
          <div className="space-y-1">
            {workers.map(w => (
              <div key={w.id} className="flex items-center gap-2 text-xs">
                <span
                  className="w-2.5 h-2.5 rounded-full"
                  style={{ backgroundColor: TRADE_COLORS[w.subtype] || '#a1a1aa' }}
                />
                <span className="font-mono text-foreground">{w.id}</span>
                <span className="text-muted-foreground capitalize">{w.subtype}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function MaterialDetail({ detail }: { detail: NonNullable<AssetDetailData['detail']> }) {
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 gap-2">
        {detail.needed_in_zone && (
          <StatBox
            label="Target zone"
            value={detail.needed_in_zone.replace('zone-', 'Zone ').replace(/^\w/, c => c.toUpperCase())}
          />
        )}
        {detail.distance_to_zone_m != null && (
          <StatBox label="Distance" value={`${detail.distance_to_zone_m}m`} />
        )}
      </div>
    </div>
  );
}

function ActivityLog({ entries }: { entries: ActivityLogEntry[] }) {
  const reversed = [...entries].reverse();
  return (
    <div className="border border-border rounded-lg p-3">
      <div className="text-xs text-muted-foreground font-medium mb-2">Activity Log</div>
      <div className="space-y-1 max-h-48 overflow-y-auto">
        {reversed.map((entry, i) => (
          <div key={i} className="flex items-start gap-2 text-xs">
            <span className="font-mono text-muted-foreground tabular-nums shrink-0 w-16 text-right">
              {formatSimTime(entry.time)}
            </span>
            <span className="text-foreground">{entry.event}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function StatBox({ label, value }: { label: string; value: string }) {
  return (
    <div className="border border-border rounded-lg p-2.5">
      <div className="text-[10px] text-muted-foreground">{label}</div>
      <div className="font-mono text-sm font-semibold text-foreground tabular-nums mt-0.5">{value}</div>
    </div>
  );
}
