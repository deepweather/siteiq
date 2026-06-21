import { useState, useCallback, useEffect, useRef } from 'react';
import type { Recommendation } from '../../types/analytics';
import type { Zone } from '../../types/site';
import { applyRecommendation, applyAllRecommendations } from '../../services/api';
import { formatCurrency } from '../../utils/formatting';
import { pushToast } from '../../utils/toasts';

interface RecommendationsProps {
  recommendations: Recommendation[];
  onRecsChange: (recs: Recommendation[]) => void;
  /** Called after each successful apply with the rec that was applied —
   *  used by the parent to drive the "recently moved" glow on the map. */
  onApplied?: (rec: Recommendation) => void;
  /** Zones for translating zone_id → human label in receipt subtitles. */
  zones?: Zone[];
}

const CELEBRATION_MS = 8000;

/** Compute the "what physically changed" subtitle shown in toasts + applied
 *  cards. Different rec types deserve different framings:
 *   - move_facility / restage_material: "moved Nm closer"
 *   - reschedule_equipment: "released — N idle h/day reclaimed"
 */
function describeChange(rec: Recommendation): string {
  if ((rec.type === 'move_facility' || rec.type === 'restage_material') && rec.to_position) {
    const dx = rec.to_position.x - rec.from_position.x;
    const dy = rec.to_position.y - rec.from_position.y;
    const moved = Math.hypot(dx, dy);
    return `Moved ${moved.toFixed(0)}m to a better location`;
  }
  if (rec.type === 'reschedule_equipment') {
    // Description already says "X% utilization. Return to rental pool ..."
    return rec.description.split(' ').slice(0, 12).join(' ');
  }
  return rec.description;
}

export function Recommendations({ recommendations: recs, onRecsChange, onApplied, zones }: RecommendationsProps) {
  const [applying, setApplying] = useState<string | null>(null);
  // Celebration card is visible only while the recommendation signature
  // matches the one we captured when Apply-All ran. Any project switch /
  // new rec set therefore auto-hides it without an explicit timer.
  const [celebrationSig, setCelebrationSig] = useState<string | null>(null);
  const celebrationTimer = useRef<number | null>(null);

  const recsSignature = recs.map(r => r.id).sort().join('|');
  const justAppliedAll = celebrationSig !== null && celebrationSig === recsSignature;

  useEffect(() => {
    return () => {
      if (celebrationTimer.current) clearTimeout(celebrationTimer.current);
    };
  }, []);

  const handleApply = useCallback(async (id: string) => {
    setApplying(id);
    const rec = recs.find(r => r.id === id);
    try {
      await applyRecommendation(id);
      onRecsChange(recs.map(r => r.id === id ? { ...r, applied: true } : r));
      if (rec) {
        onApplied?.(rec);
        pushToast({
          tone: 'success',
          title: `Saved ${formatCurrency(rec.monthly_savings)}/mo`,
          subtitle: `${rec.title} \u00b7 ${describeChange(rec)}`,
        });
      }
    } catch (err) {
      pushToast({
        tone: 'warning',
        title: 'Could not apply optimization',
        subtitle: err instanceof Error ? err.message : 'Please try again.',
      });
    } finally {
      setApplying(null);
    }
  }, [recs, onRecsChange, onApplied]);

  const handleApplyAll = useCallback(async () => {
    setApplying('all');
    const pendingBefore = recs.filter(r => !r.applied);
    try {
      await applyAllRecommendations();
      const nextRecs = recs.map(r => ({ ...r, applied: true }));
      onRecsChange(nextRecs);
      const totalSavings = pendingBefore.reduce((s, r) => s + r.monthly_savings, 0);
      pushToast({
        tone: 'success',
        title: `Applied ${pendingBefore.length} optimizations`,
        subtitle: `Recovering ${formatCurrency(totalSavings)}/mo \u00b7 ${formatCurrency(totalSavings * 12)} per year`,
        ttlMs: 6000,
      });
      if (onApplied) {
        for (const r of pendingBefore) onApplied(r);
      }
      const nextSig = nextRecs.map(r => r.id).sort().join('|');
      setCelebrationSig(nextSig);
      if (celebrationTimer.current) clearTimeout(celebrationTimer.current);
      celebrationTimer.current = window.setTimeout(() => setCelebrationSig(null), CELEBRATION_MS);
    } catch (err) {
      pushToast({
        tone: 'warning',
        title: 'Apply-all failed',
        subtitle: err instanceof Error ? err.message : 'Please try again.',
      });
    } finally {
      setApplying(null);
    }
  }, [recs, onRecsChange, onApplied]);

  const pending = recs.filter(r => !r.applied);
  const applied = recs.filter(r => r.applied);
  const totalMonthlySavings = recs.reduce((s, r) => s + r.monthly_savings, 0);
  const pendingMonthlySavings = pending.reduce((s, r) => s + r.monthly_savings, 0);

  // Group pending recs by category — easier to scan visually
  const grouped: Record<string, Recommendation[]> = {};
  for (const r of pending) {
    const cat = REC_CATEGORY[r.type] || { key: 'other', label: 'Other' };
    if (!grouped[cat.key]) grouped[cat.key] = [];
    grouped[cat.key].push(r);
  }
  // Sort categories by total savings desc
  const orderedCats = Object.keys(grouped).sort(
    (a, b) =>
      grouped[b].reduce((s, r) => s + r.monthly_savings, 0) -
      grouped[a].reduce((s, r) => s + r.monthly_savings, 0),
  );

  if (recs.length === 0) {
    return <div className="flex items-center justify-center h-40 text-muted-foreground text-sm">Looking for optimizations…</div>;
  }

  return (
    <div className="space-y-4">
      {/* Post-apply celebration */}
      {justAppliedAll && applied.length > 0 && (
        <div className="bg-success/10 border-2 border-success/30 rounded-lg p-5 text-center">
          <div className="text-success text-2xl mb-2">&#10003;</div>
          <div className="text-xs text-success font-semibold uppercase tracking-wider">All Optimizations Applied</div>
          <div className="font-mono text-3xl font-bold text-success tabular-nums mt-2">
            {formatCurrency(totalMonthlySavings * 12)}
          </div>
          <div className="text-xs text-success/70 mt-1">projected annual savings</div>
          <div className="font-mono text-sm text-muted-foreground mt-2 tabular-nums">
            {formatCurrency(totalMonthlySavings)}/month
          </div>
        </div>
      )}

      {/* Pre-apply: show what's available */}
      {pending.length > 0 && (
        <>
          {!justAppliedAll && (
            <div className="bg-warning/8 border border-warning/20 rounded-lg p-4">
              <div className="text-xs text-warning font-semibold uppercase tracking-wider">Available Savings</div>
              <div className="font-mono text-2xl font-bold text-foreground tabular-nums mt-1">
                {formatCurrency(pendingMonthlySavings)}
                <span className="text-sm text-muted-foreground font-medium">/mo</span>
              </div>
              <div className="text-xs text-muted-foreground mt-1">
                {formatCurrency(pendingMonthlySavings * 12)}/year across {pending.length} {pending.length === 1 ? 'improvement' : 'improvements'}
              </div>
            </div>
          )}

          <button
            onClick={handleApplyAll}
            disabled={applying === 'all'}
            className="w-full py-3 rounded-lg text-sm font-semibold bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50 shadow-sm transition-all active:scale-[0.98]"
          >
            {applying === 'all' ? (
              <span className="flex items-center justify-center gap-2">
                <span className="w-4 h-4 border-2 border-primary-foreground/30 border-t-primary-foreground rounded-full animate-spin" />
                Optimizing site layout…
              </span>
            ) : (
              <span className="flex items-center justify-center gap-2">
                <span>Apply all — save</span>
                <span className="font-mono tabular-nums">{formatCurrency(pendingMonthlySavings)}/mo</span>
              </span>
            )}
          </button>

          <div className="space-y-3">
            {orderedCats.map(catKey => {
              const catRecs = grouped[catKey];
              const catLabel = REC_CATEGORY[catRecs[0].type]?.label || 'Other';
              const catIcon = REC_CATEGORY[catRecs[0].type]?.icon || '•';
              const catTotal = catRecs.reduce((s, r) => s + r.monthly_savings, 0);
              return (
                <div key={catKey} className="space-y-1.5">
                  <div className="flex items-center justify-between text-[10px] uppercase tracking-wider font-semibold">
                    <span className="text-muted-foreground flex items-center gap-1.5">
                      <span className="text-sm" aria-hidden="true">{catIcon}</span>
                      {catLabel} ({catRecs.length})
                    </span>
                    <span className="font-mono text-muted-foreground tabular-nums">{formatCurrency(catTotal)}/mo</span>
                  </div>
                  {catRecs.map(rec => (
                    <div key={rec.id} className="border border-border rounded-lg p-3">
                      <div className="flex items-start justify-between gap-2">
                        <div className="min-w-0">
                          <h4 className="text-sm font-medium text-foreground">{rec.title}</h4>
                          <p className="text-[11px] text-muted-foreground mt-1 leading-relaxed">{rec.description}</p>
                        </div>
                        <span className="shrink-0 inline-flex items-center font-mono text-xs text-success bg-success/10 px-2 py-0.5 rounded-full tabular-nums whitespace-nowrap">
                          {formatCurrency(rec.monthly_savings)}/mo
                        </span>
                      </div>
                      <button
                        onClick={() => handleApply(rec.id)}
                        disabled={applying === rec.id}
                        className="mt-2.5 px-3 py-1 rounded-md text-xs font-medium text-primary border border-primary/30 hover:bg-primary hover:text-primary-foreground disabled:opacity-50 transition-colors"
                      >
                        {applying === rec.id ? 'Applying…' : 'Apply'}
                      </button>
                    </div>
                  ))}
                </div>
              );
            })}
          </div>
        </>
      )}

      {/* Applied list */}
      {applied.length > 0 && pending.length > 0 && (
        <div className="border-t border-border" />
      )}

      {applied.length > 0 && (
        <div>
          <div className="text-xs text-muted-foreground font-medium mb-2">
            Applied ({applied.length}) \u00b7 saving{' '}
            <span className="font-mono text-success tabular-nums">
              {formatCurrency(applied.reduce((s, r) => s + r.monthly_savings, 0))}/mo
            </span>
          </div>
          <div className="space-y-1.5">
            {applied.map((rec) => (
              <AppliedCard key={rec.id} rec={rec} zones={zones} />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}


function AppliedCard({ rec, zones }: { rec: Recommendation; zones?: Zone[] }) {
  const change = describeChange(rec);
  const zoneLabel = (() => {
    if (!zones) return null;
    // Pull a zone label out of titles like "Restage Concrete near Block C"
    const m = rec.title.match(/near\s+(.+)$/i);
    if (m) return m[1].trim();
    return null;
  })();

  return (
    <div className="rounded-lg border border-success/25 bg-success/5 p-2.5">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2 mb-1">
            <span
              className="w-5 h-5 rounded-full bg-success/20 text-success text-[10px] flex items-center justify-center shrink-0"
              aria-hidden="true"
            >
              &#10003;
            </span>
            <span className="text-sm font-medium text-foreground truncate">{rec.title}</span>
          </div>
          <div className="text-[11px] text-muted-foreground leading-snug ml-7">
            {change}
            {zoneLabel ? ` \u00b7 affects ${zoneLabel}` : ''}
          </div>
        </div>
        <div className="text-right shrink-0">
          <div className="font-mono text-sm font-semibold text-success tabular-nums">
            {formatCurrency(rec.monthly_savings)}
            <span className="text-[10px] text-muted-foreground font-medium">/mo</span>
          </div>
          <div className="text-[10px] text-muted-foreground font-mono tabular-nums">
            {formatCurrency(rec.daily_savings)}/day
          </div>
        </div>
      </div>
    </div>
  );
}

// Maps backend rec types to a user-friendly category + icon. Keep this near
// the component so adding a new rec type fails-soft (falls through to 'Other').
const REC_CATEGORY: Record<string, { key: string; label: string; icon: string }> = {
  move_facility: { key: 'facility', label: 'Facility placement', icon: '🚻' },
  restage_material: { key: 'material', label: 'Material staging', icon: '📦' },
  reschedule_equipment: { key: 'equipment', label: 'Equipment scheduling', icon: '🏗️' },
};
