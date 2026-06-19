import { useState, useEffect } from 'react';
import type { Site } from '../types/site';
import { fetchSite } from '../services/api';

export function useSimulation() {
  const [site, setSite] = useState<Site | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchSite()
      .then(setSite)
      .catch(console.error)
      .finally(() => setLoading(false));
  }, []);

  return { site, loading };
}
