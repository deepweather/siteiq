import { useState, useCallback, useEffect, useRef } from 'react';
import { useWebSocket } from './hooks/useWebSocket';
import { useSimulation } from './hooks/useSimulation';
import { useAnalytics } from './hooks/useAnalytics';
import { TopBar } from './components/TopBar/TopBar';
import { SiteMap } from './components/SiteMap/SiteMap';
import { RightPanel } from './components/RightPanel/RightPanel';
import { Portfolio } from './components/Portfolio/Portfolio';
import { ToastContainer } from './components/common/ToastContainer';
import { fetchRecommendations } from './services/api';
import type { Recommendation } from './types/analytics';

export default function App() {
  const { assetsRef, trailsRef, analytics, simTime, simDay, connected } = useWebSocket();
  const { site, loading, reload } = useSimulation();
  const { currentWaste, baselineWaste, savings, resetBaseline } = useAnalytics(analytics);
  const [recommendations, setRecommendations] = useState<Recommendation[]>([]);
  const [selectedAssetId, setSelectedAssetId] = useState<string | null>(null);
  const [showPortfolio, setShowPortfolio] = useState(false);
  /** Last asset modified by an Apply action (drives the "pulsing glow" on
   *  the map and the smooth-move animation lookup). */
  const [recentApply, setRecentApply] = useState<{ assetId: string; ts: number } | null>(null);
  const recsInterval = useRef<number | null>(null);

  const loadRecs = useCallback(async () => {
    try {
      const data = await fetchRecommendations();
      setRecommendations(data);
    } catch { /* retry next interval */ }
  }, []);

  useEffect(() => {
    loadRecs();
    recsInterval.current = window.setInterval(loadRecs, 5000);
    return () => { if (recsInterval.current) clearInterval(recsInterval.current); };
  }, [loadRecs]);

  const handleRecsChange = useCallback((recs: Recommendation[]) => {
    setRecommendations(recs);
  }, []);

  const handleApplied = useCallback((rec: Recommendation) => {
    setRecentApply({ assetId: rec.target_asset_id, ts: performance.now() });
  }, []);

  const handleAssetSelect = useCallback((id: string | null) => {
    setSelectedAssetId(id);
  }, []);

  const handleProjectChange = useCallback(() => {
    setSelectedAssetId(null);
    setRecommendations([]);
    resetBaseline();
    reload();
    setTimeout(loadRecs, 1000);
  }, [reload, resetBaseline, loadRecs]);

  const handlePortfolioSelect = useCallback(() => {
    // Portfolio.tsx already calls loadProject(id) before invoking this
    // callback, so we just need to refresh local state. The projectId
    // argument declared on the prop is intentionally unused here.
    handleProjectChange();
    setShowPortfolio(false);
  }, [handleProjectChange]);

  if (showPortfolio) {
    return (
      <Portfolio
        onSelectSite={handlePortfolioSelect}
        onClose={() => setShowPortfolio(false)}
      />
    );
  }

  if (loading || !site) {
    return (
      <div className="h-screen flex items-center justify-center bg-background">
        <div className="text-center">
          <div className="w-10 h-10 bg-primary rounded-lg flex items-center justify-center mx-auto mb-4">
            <span className="text-primary-foreground text-lg font-bold">S</span>
          </div>
          <div className="text-foreground font-semibold text-sm">SiteIQ</div>
          <div className="text-muted-foreground text-xs mt-1">Connecting to site...</div>
        </div>
      </div>
    );
  }

  const pendingRecs = recommendations.filter(r => !r.applied);
  const pendingSavingsMonthly = pendingRecs.reduce((s, r) => s + r.monthly_savings, 0);

  return (
    <div className="h-screen flex flex-col bg-background">
      <TopBar
        simTime={simTime}
        simDay={simDay}
        connected={connected}
        siteName={site.name}
        onProjectChange={handleProjectChange}
        onShowPortfolio={() => setShowPortfolio(true)}
      />
      <div className="flex-1 flex min-h-0">
        <SiteMap
          zones={site.zones}
          siteWidth={site.width}
          siteHeight={site.height}
          assetsRef={assetsRef}
          trailsRef={trailsRef}
          recommendations={recommendations}
          selectedAssetId={selectedAssetId}
          onAssetSelect={handleAssetSelect}
          recentApply={recentApply}
        />
        <RightPanel
          waste={currentWaste}
          baseline={baselineWaste}
          savings={savings}
          pendingSavingsMonthly={pendingSavingsMonthly}
          schedule={site.schedule}
          zones={site.zones}
          currentDay={simDay}
          recommendations={recommendations}
          onRecsChange={handleRecsChange}
          onApplied={handleApplied}
          selectedAssetId={selectedAssetId}
          onAssetDeselect={() => setSelectedAssetId(null)}
        />
      </div>
      <ToastContainer />
    </div>
  );
}
