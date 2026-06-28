/** Small React hooks for the worker shell: outbox state + connectivity. */
import { useEffect, useState, useSyncExternalStore } from 'react';
import { outbox } from './offlineQueue';

export function useOutbox(): { pending: number; flushing: boolean } {
  return useSyncExternalStore(outbox.subscribeBound, outbox.getSnapshot, outbox.getSnapshot);
}

export function useOnline(): boolean {
  const [online, setOnline] = useState<boolean>(
    typeof navigator === 'undefined' ? true : navigator.onLine,
  );
  useEffect(() => {
    const up = () => setOnline(true);
    const down = () => setOnline(false);
    window.addEventListener('online', up);
    window.addEventListener('offline', down);
    return () => {
      window.removeEventListener('online', up);
      window.removeEventListener('offline', down);
    };
  }, []);
  return online;
}
