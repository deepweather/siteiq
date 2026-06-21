/**
 * Surfaces WebSocket connection drops as toasts.
 *
 * - Connected → connected: silent.
 * - Connected → disconnected: after a 2s grace (so transient blips
 *   don't spam the queue), push a sticky "Reconnecting…" toast.
 * - Disconnected → connected: replace the sticky with a 2s "Live
 *   again" success toast.
 *
 * The component-level `connected` pill in `TopBar` stays as the
 * primary indicator; this hook is for the moments when the user has
 * scrolled or is mid-task and needs an active nudge.
 */
import { useEffect, useRef } from 'react';
import { dismissToast, pushToast } from '../utils/toasts';

const DISCONNECT_GRACE_MS = 2000;

export function useConnectionToast(connected: boolean): void {
  const stickyId = useRef<number | null>(null);
  const graceTimer = useRef<number | null>(null);
  const previouslyConnected = useRef(connected);

  useEffect(() => {
    if (connected) {
      // Cancel any pending "show reconnecting" timer.
      if (graceTimer.current) {
        clearTimeout(graceTimer.current);
        graceTimer.current = null;
      }
      // If we were displaying a reconnecting toast, swap to a quick
      // confirmation. Skip on initial mount (avoid a noisy "Live
      // again" on page load).
      if (stickyId.current !== null) {
        dismissToast(stickyId.current);
        stickyId.current = null;
        pushToast({
          title: 'Live again',
          subtitle: 'Reconnected to the simulation stream.',
          tone: 'success',
          ttlMs: 2500,
        });
      }
    } else if (previouslyConnected.current) {
      // Just dropped — start the grace window.
      graceTimer.current = window.setTimeout(() => {
        if (stickyId.current === null) {
          stickyId.current = pushToast({
            title: 'Reconnecting…',
            subtitle: 'Lost the live stream. Trying again.',
            tone: 'warning',
            ttlMs: 0,
          });
        }
      }, DISCONNECT_GRACE_MS);
    }
    previouslyConnected.current = connected;
    return () => {
      if (graceTimer.current) {
        clearTimeout(graceTimer.current);
        graceTimer.current = null;
      }
    };
  }, [connected]);
}
