/**
 * RightPanel — the dashboard's secondary surface.
 *
 * Two modes, no tabs:
 *   - default: WasteReport (the cost story + Apply CTA).
 *   - selected asset: AssetDetail (worker / equipment / facility / material).
 *
 * The right rail is narrow on small viewports so the canvas keeps as
 * much horizontal real estate as possible: 320 px below 1280 px, 380 px
 * above. Apply CTA stays prominent at either width.
 */

import { useEffect, useState } from 'react';
import type { WasteSummary, Recommendation } from '../../types/analytics';
import type { ScheduleEntry, Zone } from '../../types/site';
import { WasteReport } from './WasteReport';
import { AssetDetail } from './AssetDetail';

interface RightPanelProps {
  waste: WasteSummary | null;
  baseline: WasteSummary | null;
  savings: { toilet: number; material: number; equipment: number; total: number } | null;
  /** Kept for prop compatibility with Dashboard. Timeline content now
   *  lives in the editor's Schedule tab; the dashboard rail does not
   *  surface it. The dashboard wires through `[]` to be explicit. */
  schedule?: ScheduleEntry[];
  zones: Zone[];
  currentDay?: number;
  recommendations: Recommendation[];
  onRecsChange: (recs: Recommendation[]) => void;
  onApplied?: (rec: Recommendation) => void;
  selectedAssetId: string | null;
  onAssetDeselect: () => void;
}

export function RightPanel({
  waste, baseline, savings, zones, recommendations,
  onRecsChange, onApplied, selectedAssetId, onAssetDeselect,
}: RightPanelProps) {
  const [narrow, setNarrow] = useState(
    typeof window === 'undefined' ? false : window.innerWidth < 1280,
  );
  useEffect(() => {
    const onResize = () => setNarrow(window.innerWidth < 1280);
    window.addEventListener('resize', onResize);
    return () => window.removeEventListener('resize', onResize);
  }, []);

  // Esc deselects whatever's selected — keeps the keyboard story
  // consistent with the rest of the app.
  useEffect(() => {
    if (!selectedAssetId) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onAssetDeselect();
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [selectedAssetId, onAssetDeselect]);

  return (
    <div
      className="shrink-0 bg-card border-l border-border flex flex-col h-full shadow-sm"
      style={{ width: narrow ? 320 : 380 }}
    >
      {selectedAssetId ? (
        <>
          <div className="flex items-center justify-between border-b border-border shrink-0 px-3 py-2.5">
            <span className="text-xs font-medium text-foreground">Asset Detail</span>
            <button
              onClick={onAssetDeselect}
              className="text-xs text-muted-foreground hover:text-foreground px-2 py-1 rounded-md hover:bg-secondary"
            >
              Back
            </button>
          </div>
          <div className="flex-1 overflow-y-auto p-3">
            <AssetDetail assetId={selectedAssetId} onClose={onAssetDeselect} />
          </div>
        </>
      ) : (
        <div className="flex-1 overflow-y-auto p-3">
          <WasteReport
            waste={waste}
            baseline={baseline}
            savings={savings}
            zones={zones}
            recommendations={recommendations}
            onRecsChange={onRecsChange}
            onApplied={onApplied}
          />
        </div>
      )}
    </div>
  );
}
