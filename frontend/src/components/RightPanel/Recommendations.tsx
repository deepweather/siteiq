import { useState, useEffect, useCallback } from 'react';
import type { Recommendation } from '../../types/analytics';
import { fetchRecommendations, applyRecommendation, applyAllRecommendations } from '../../services/api';
import { formatCurrency } from '../../utils/formatting';

interface RecommendationsProps {
  onRecsChange: (recs: Recommendation[]) => void;
}

export function Recommendations({ onRecsChange }: RecommendationsProps) {
  const [recs, setRecs] = useState<Recommendation[]>([]);
  const [loading, setLoading] = useState(true);
  const [applying, setApplying] = useState<string | null>(null);

  const loadRecs = useCallback(async () => {
    try {
      const data = await fetchRecommendations();
      setRecs(data);
      onRecsChange(data);
    } catch {
      /* retry on next call */
    }
    setLoading(false);
  }, [onRecsChange]);

  useEffect(() => {
    loadRecs();
    const interval = setInterval(loadRecs, 5000);
    return () => clearInterval(interval);
  }, [loadRecs]);

  const handleApply = async (id: string) => {
    setApplying(id);
    await applyRecommendation(id);
    setRecs(prev => prev.map(r => r.id === id ? { ...r, applied: true } : r));
    onRecsChange(recs.map(r => r.id === id ? { ...r, applied: true } : r));
    setApplying(null);
    setTimeout(loadRecs, 1000);
  };

  const handleApplyAll = async () => {
    setApplying('all');
    await applyAllRecommendations();
    setRecs(prev => prev.map(r => ({ ...r, applied: true })));
    onRecsChange(recs.map(r => ({ ...r, applied: true })));
    setApplying(null);
    setTimeout(loadRecs, 1000);
  };

  const pending = recs.filter(r => !r.applied);
  const applied = recs.filter(r => r.applied);
  const totalMonthlySavings = recs.reduce((s, r) => s + r.monthly_savings, 0);

  if (loading) {
    return <div className="flex items-center justify-center h-40 text-muted-foreground text-sm">Loading...</div>;
  }

  return (
    <div className="space-y-4">
      {applied.length > 0 && (
        <div className="bg-success/10 border border-success/20 rounded-lg p-4">
          <div className="text-xs text-success font-medium">Projected Annual Savings</div>
          <div className="font-mono text-2xl font-bold text-success tabular-nums mt-1">
            {formatCurrency(totalMonthlySavings * 12)}
          </div>
        </div>
      )}

      {pending.length > 0 && (
        <>
          {pending.length > 1 && (
            <button
              onClick={handleApplyAll}
              disabled={applying === 'all'}
              className="w-full py-2.5 rounded-lg text-sm font-medium bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50 shadow-sm"
            >
              {applying === 'all' ? 'Applying...' : `Apply All ${pending.length} Optimizations`}
            </button>
          )}

          <div className="space-y-3">
            {pending.map((rec) => (
              <div key={rec.id} className="border border-border rounded-lg p-4">
                <div className="flex items-start justify-between gap-3">
                  <h4 className="text-sm font-medium text-foreground">{rec.title}</h4>
                  <span className="shrink-0 inline-flex items-center font-mono text-xs text-success bg-success/10 px-2 py-0.5 rounded-full tabular-nums">
                    {formatCurrency(rec.monthly_savings)}/mo
                  </span>
                </div>
                <p className="text-xs text-muted-foreground mt-1.5 leading-relaxed">{rec.description}</p>
                <button
                  onClick={() => handleApply(rec.id)}
                  disabled={applying === rec.id}
                  className="mt-3 px-4 py-1.5 rounded-md text-xs font-medium text-primary-foreground bg-primary hover:bg-primary/90 disabled:opacity-50"
                >
                  {applying === rec.id ? 'Applying...' : 'Apply'}
                </button>
              </div>
            ))}
          </div>
        </>
      )}

      {applied.length > 0 && pending.length > 0 && (
        <div className="border-t border-border" />
      )}

      {applied.length > 0 && (
        <div>
          <div className="text-xs text-muted-foreground font-medium mb-2">Applied ({applied.length})</div>
          <div className="space-y-2">
            {applied.map((rec) => (
              <div key={rec.id} className="flex items-center justify-between p-3 rounded-lg bg-secondary">
                <div className="flex items-center gap-2">
                  <span className="w-5 h-5 rounded-full bg-success/20 text-success text-[10px] flex items-center justify-center">&#10003;</span>
                  <span className="text-sm text-foreground">{rec.title}</span>
                </div>
                <span className="font-mono text-xs text-muted-foreground tabular-nums">{formatCurrency(rec.monthly_savings)}/mo</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
