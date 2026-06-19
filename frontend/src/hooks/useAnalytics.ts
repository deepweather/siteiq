import { useState, useEffect, useRef } from 'react';
import type { WasteSummary } from '../types/analytics';

interface AnalyticsState {
  currentWaste: WasteSummary | null;
  baselineWaste: WasteSummary | null;
  savings: {
    toilet: number;
    material: number;
    equipment: number;
    total: number;
  } | null;
}

export function useAnalytics(wsAnalytics: WasteSummary | null): AnalyticsState {
  const [currentWaste, setCurrentWaste] = useState<WasteSummary | null>(null);
  const baselineRef = useRef<WasteSummary | null>(null);
  const [baselineWaste, setBaselineWaste] = useState<WasteSummary | null>(null);

  useEffect(() => {
    if (!wsAnalytics) return;
    setCurrentWaste(wsAnalytics);

    if (!baselineRef.current && wsAnalytics.total_daily > 0) {
      baselineRef.current = { ...wsAnalytics };
      setBaselineWaste({ ...wsAnalytics });
    }
  }, [wsAnalytics]);

  const savings = currentWaste && baselineWaste ? {
    toilet: baselineWaste.toilet_walk_monthly - currentWaste.toilet_walk_monthly,
    material: baselineWaste.material_handling_monthly - currentWaste.material_handling_monthly,
    equipment: baselineWaste.equipment_idle_monthly - currentWaste.equipment_idle_monthly,
    total: baselineWaste.total_monthly - currentWaste.total_monthly,
  } : null;

  return { currentWaste, baselineWaste, savings };
}
