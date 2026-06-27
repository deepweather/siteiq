/**
 * Live data context provider.
 *
 * The backend exposes a single sim engine per org; the WS + analytics +
 * recommendations + the active site descriptor are therefore a single
 * shared resource. We lift them here so every chrome component
 * (MenuBar, Sidebar, StatusBar) reads from the same WebSocket instead
 * of opening their own.
 *
 * The context object + the `useLive` hook live in [./useLive.ts] so
 * this `.tsx` file exports only a component (Fast Refresh constraint).
 */

import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react';
import { useAuth } from '../lib/auth/AuthProvider';
import { useAnalytics } from '../hooks/useAnalytics';
import { useSimulation } from '../hooks/useSimulation';
import { useWebSocket } from '../hooks/useWebSocket';
import { fetchRecommendations, loadProject, setSimSpeed, togglePause } from '../services/api';
import type { Recommendation } from '../types/analytics';
import { LiveContext, type LiveContextShape } from './useLive';

export function LiveProvider({ children }: { children: ReactNode }) {
  const { org } = useAuth();
  const { assetsRef, trailsRef, cabsRef, analytics, simTime, simDay, connected } = useWebSocket();
  const { site, loading: siteLoading, reload } = useSimulation();
  const { currentWaste, baselineWaste, savings, resetBaseline } = useAnalytics(analytics);
  const [recommendations, setRecommendations] = useState<Recommendation[]>([]);
  const [speed, setSpeedState] = useState(1);
  const [paused, setPaused] = useState(false);
  const [recentApply, setRecentApply] = useState<{ assetId: string; ts: number } | null>(null);
  const recsIntervalRef = useRef<number | null>(null);

  const refreshRecommendations = useCallback(async () => {
    try {
      const data = await fetchRecommendations();
      setRecommendations(data);
    } catch {
      /* retry next interval */
    }
  }, []);

  // Poll recs at 5 s like the legacy Dashboard.
  useEffect(() => {
    refreshRecommendations();
    recsIntervalRef.current = window.setInterval(refreshRecommendations, 5000);
    return () => {
      if (recsIntervalRef.current) clearInterval(recsIntervalRef.current);
    };
  }, [refreshRecommendations]);

  // Reset everything when the active org changes (engine swap).
  useEffect(() => {
    setRecommendations([]);
    resetBaseline();
    reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [org?.id]);

  const switchProject = useCallback(
    async (slug: string) => {
      await loadProject(slug);
      setRecommendations([]);
      resetBaseline();
      reload();
      // The recs endpoint is keyed on the active project — refresh
      // after a beat so the backend has finished swapping engines.
      setTimeout(refreshRecommendations, 1000);
    },
    [reload, resetBaseline, refreshRecommendations],
  );

  const setSpeed = useCallback(async (s: number) => {
    setSpeedState(s);
    await setSimSpeed(s);
  }, []);

  const togglePaused = useCallback(async () => {
    setPaused((p) => !p);
    await togglePause();
  }, []);

  const value = useMemo<LiveContextShape>(
    () => ({
      assetsRef,
      trailsRef,
      cabsRef,
      analytics,
      currentWaste,
      baselineWaste,
      savings,
      simTime,
      simDay,
      connected,
      site,
      siteLoading,
      recommendations,
      setRecommendations,
      speed,
      paused,
      setSpeed,
      togglePaused,
      switchProject,
      reload,
      recentApply,
      setRecentApply,
      refreshRecommendations,
    }),
    [
      assetsRef,
      trailsRef,
      cabsRef,
      analytics,
      currentWaste,
      baselineWaste,
      savings,
      simTime,
      simDay,
      connected,
      site,
      siteLoading,
      recommendations,
      speed,
      paused,
      setSpeed,
      togglePaused,
      switchProject,
      reload,
      recentApply,
      refreshRecommendations,
    ],
  );

  return <LiveContext.Provider value={value}>{children}</LiveContext.Provider>;
}
