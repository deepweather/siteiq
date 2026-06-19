import { useState, useCallback } from 'react';
import { useWebSocket } from './hooks/useWebSocket';
import { useSimulation } from './hooks/useSimulation';
import { useAnalytics } from './hooks/useAnalytics';
import { TopBar } from './components/TopBar/TopBar';
import { SiteMap } from './components/SiteMap/SiteMap';
import { RightPanel } from './components/RightPanel/RightPanel';
import type { Recommendation } from './types/analytics';

export default function App() {
  const { assetsRef, trailsRef, analytics, simTime, simDay, connected } = useWebSocket();
  const { site, loading } = useSimulation();
  const { currentWaste, baselineWaste, savings } = useAnalytics(analytics);
  const [recommendations, setRecommendations] = useState<Recommendation[]>([]);
  const [selectedAssetId, setSelectedAssetId] = useState<string | null>(null);

  const handleRecsChange = useCallback((recs: Recommendation[]) => {
    setRecommendations(recs);
  }, []);

  const handleAssetSelect = useCallback((id: string | null) => {
    setSelectedAssetId(id);
  }, []);

  if (loading || !site) {
    return (
      <div className="h-screen flex items-center justify-center bg-background">
        <div className="text-muted-foreground text-sm">Connecting to site...</div>
      </div>
    );
  }

  return (
    <div className="h-screen flex flex-col bg-background">
      <TopBar
        simTime={simTime}
        simDay={simDay}
        connected={connected}
        siteName={site.name}
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
        />
        <RightPanel
          waste={currentWaste}
          baseline={baselineWaste}
          savings={savings}
          schedule={site.schedule}
          currentDay={simDay}
          onRecsChange={handleRecsChange}
          selectedAssetId={selectedAssetId}
          onAssetDeselect={() => setSelectedAssetId(null)}
        />
      </div>
    </div>
  );
}
