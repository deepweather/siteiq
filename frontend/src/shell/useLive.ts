/**
 * useLive — consume the live-data context.
 *
 * Kept in its own file (separate from `LiveContext.tsx`) so the .tsx
 * file exports only a component and Fast Refresh stays happy.
 */

import { createContext, useContext } from 'react';
import type { CabSnapshot } from '../hooks/useWebSocket';
import type { AssetUpdate, Trail } from '../types/assets';
import type { Recommendation, WasteSummary } from '../types/analytics';
import type { Site } from '../types/site';

export interface LiveContextShape {
  // Live stream refs (refs so canvases can poll without re-renders).
  assetsRef: React.MutableRefObject<AssetUpdate[]>;
  trailsRef: React.MutableRefObject<Trail>;
  cabsRef: React.MutableRefObject<CabSnapshot[]>;

  // Reactive state.
  analytics: WasteSummary | null;
  currentWaste: WasteSummary | null;
  baselineWaste: WasteSummary | null;
  savings: { toilet: number; material: number; equipment: number; total: number } | null;
  simTime: number;
  simDay: number;
  connected: boolean;
  site: Site | null;
  siteLoading: boolean;
  recommendations: Recommendation[];
  setRecommendations: (next: Recommendation[]) => void;

  // Controls.
  speed: number;
  paused: boolean;
  setSpeed: (s: number) => Promise<void>;
  togglePaused: () => Promise<void>;

  switchProject: (slug: string) => Promise<void>;
  reload: () => void;

  recentApply: { assetId: string; ts: number } | null;
  setRecentApply: (apply: { assetId: string; ts: number } | null) => void;

  refreshRecommendations: () => Promise<void>;
}

export const LiveContext = createContext<LiveContextShape | null>(null);

export function useLive(): LiveContextShape {
  const ctx = useContext(LiveContext);
  if (!ctx) throw new Error('useLive must be used inside <LiveProvider>');
  return ctx;
}
