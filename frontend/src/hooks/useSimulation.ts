import { useState, useEffect, useCallback } from 'react';
import type { Site } from '../types/site';
import { fetchSite } from '../services/api';

export function useSimulation() {
  const [site, setSite] = useState<Site | null>(null);
  const [loading, setLoading] = useState(true);
  const [version, setVersion] = useState(0);

  useEffect(() => {
    setLoading(true);
    fetchSite()
      .then(setSite)
      .catch(console.error)
      .finally(() => setLoading(false));
  }, [version]);

  const reload = useCallback(() => {
    setVersion(v => v + 1);
  }, []);

  return { site, loading, reload };
}
