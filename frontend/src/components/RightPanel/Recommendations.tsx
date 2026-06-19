import { useState, useCallback } from 'react';
import type { Recommendation } from '../../types/analytics';
import { applyRecommendation, applyAllRecommendations } from '../../services/api';
import { formatCurrency } from '../../utils/formatting';

interface RecommendationsProps {
  recommendations: Recommendation[];
  onRecsChange: (recs: Recommendation[]) => void;
}

export function Recommendations({ recommendations: recs, onRecsChange }: RecommendationsProps) {
  const [applying, setApplying] = useState<string | null>(null);
  const [justAppliedAll, setJustAppliedAll] = useState(false);

  const handleApply = useCallback(async (id: string) => {
    setApplying(id);
    await applyRecommendation(id);
    onRecsChange(recs.map(r => r.id === id ? { ...r, applied: true } : r));
    setApplying(null);
  }, [recs, onRecsChange]);

  const handleApplyAll = useCallback(async () => {
    setApplying('all');
    await applyAllRecommendations();
    onRecsChange(recs.map(r => ({ ...r, applied: true })));
    setApplying(null);
    setJustAppliedAll(true);
  }, [recs, onRecsChange]);

  const pending = recs.filter(r => !r.applied);
  const applied = recs.filter(r => r.applied);
  const totalMonthlySavings = recs.reduce((s, r) => s + r.monthly_savings, 0);
  const pendingMonthlySavings = pending.reduce((s, r) => s + r.monthly_savings, 0);

  if (recs.length === 0) {
    return <div className="flex items-center justify-center h-40 text-muted-foreground text-sm">Loading recommendations...</div>;
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
                {formatCurrency(pendingMonthlySavings * 12)}/year across {pending.length} optimizations
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
                Optimizing site layout...
              </span>
            ) : (
              `Apply All ${pending.length} Optimizations`
            )}
          </button>

          <div className="space-y-2">
            {pending.map((rec) => (
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
                  {applying === rec.id ? 'Applying...' : 'Apply'}
                </button>
              </div>
            ))}
          </div>
        </>
      )}

      {/* Applied list */}
      {applied.length > 0 && pending.length > 0 && (
        <div className="border-t border-border" />
      )}

      {applied.length > 0 && (
        <div>
          <div className="text-xs text-muted-foreground font-medium mb-2">Applied ({applied.length})</div>
          <div className="space-y-1.5">
            {applied.map((rec) => (
              <div key={rec.id} className="flex items-center justify-between p-2.5 rounded-lg bg-secondary">
                <div className="flex items-center gap-2 min-w-0">
                  <span className="w-5 h-5 rounded-full bg-success/20 text-success text-[10px] flex items-center justify-center shrink-0">&#10003;</span>
                  <span className="text-sm text-foreground truncate">{rec.title}</span>
                </div>
                <span className="font-mono text-xs text-muted-foreground tabular-nums shrink-0 ml-2">{formatCurrency(rec.monthly_savings)}/mo</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
