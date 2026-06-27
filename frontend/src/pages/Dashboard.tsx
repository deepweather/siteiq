/**
 * Dashboard — the home of /app.
 *
 * Renders only the body: SiteMap on the left, RightPanel on the right.
 * The persistent chrome (MenuBar at top, Sidebar on left, StatusBar at
 * bottom) is provided by <Chrome/> at the layout-route level.
 *
 * Live streams + analytics + recommendations live in LiveContext one
 * layer above, so the SiteMap mounts exactly once per /app session and
 * survives navigation to Portfolio / ProjectList / Settings.
 */

import { useCallback, useState } from 'react';
import { useLive } from '../shell/useLive';
import { SiteMap } from '../components/SiteMap/SiteMap';
import { RightPanel } from '../components/RightPanel/RightPanel';
import { ToastContainer } from '../components/common/ToastContainer';
import { useConnectionToast } from '../hooks/useConnectionToast';
import type { Recommendation } from '../types/analytics';

export default function Dashboard() {
  const live = useLive();
  useConnectionToast(live.connected);

  const [selectedAssetId, setSelectedAssetId] = useState<string | null>(null);

  const handleAssetSelect = useCallback((id: string | null) => setSelectedAssetId(id), []);

  const handleRecsChange = useCallback(
    (next: Recommendation[]) => live.setRecommendations(next),
    [live],
  );

  const handleApplied = useCallback(
    (rec: Recommendation) => {
      live.setRecentApply({ assetId: rec.target_asset_id, ts: performance.now() });
    },
    [live],
  );

  if (live.siteLoading || !live.site) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <div className="text-center">
          <div className="w-10 h-10 bg-primary rounded-lg flex items-center justify-center mx-auto mb-4">
            <span className="text-primary-foreground text-lg font-bold">S</span>
          </div>
          <div className="text-foreground font-semibold text-sm">SiteIQ</div>
          <div className="text-muted-foreground text-xs mt-1">Connecting to site…</div>
        </div>
      </div>
    );
  }

  return (
    <>
      <div className="flex-1 flex min-h-0 min-w-0">
        <SiteMap
          zones={live.site.zones}
          siteWidth={live.site.width}
          siteHeight={live.site.height}
          assetsRef={live.assetsRef}
          trailsRef={live.trailsRef}
          cabsRef={live.cabsRef}
          recommendations={live.recommendations}
          selectedAssetId={selectedAssetId}
          onAssetSelect={handleAssetSelect}
          recentApply={live.recentApply}
          levels={live.site.levels}
          connections={live.site.connections}
        />
        <RightPanel
          waste={live.currentWaste}
          baseline={live.baselineWaste}
          savings={live.savings}
          zones={live.site.zones}
          recommendations={live.recommendations}
          onRecsChange={handleRecsChange}
          onApplied={handleApplied}
          selectedAssetId={selectedAssetId}
          onAssetDeselect={() => setSelectedAssetId(null)}
        />
      </div>
      <ToastContainer />
    </>
  );
}
