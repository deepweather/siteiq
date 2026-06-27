/**
 * AppLayout — the single layout route for /app/*.
 *
 * Owns the LiveProvider (one WebSocket + one /api/site fetch per session,
 * survives navigation between Dashboard / Portfolio / Editor / Settings)
 * and the Cmd+K palette overlay. The page-level routes render below it
 * via <Outlet/>.
 *
 * Each child route paints its own full chrome — the dashboard uses
 * AppHeader, the editor / portfolio / project list / settings use their
 * own task-shaped headers. None of them know about each other.
 */

import { useEffect } from 'react';
import { Outlet } from 'react-router-dom';
import { LiveProvider } from './LiveContext';
import { CommandPalette } from './CommandPalette';
import { useShellShortcuts } from './keyboard';

const LEGACY_STORE_KEY = 'siteiq.shell.v1';

export default function AppLayout() {
  // One-time cleanup of the abandoned tab-shell's localStorage state.
  // Without this, an earlier-build user opens the app and sees ghost
  // chrome trying to restore from a now-removed store schema.
  useEffect(() => {
    try {
      window.localStorage.removeItem(LEGACY_STORE_KEY);
    } catch {
      /* private mode / quota — ignore */
    }
  }, []);

  useShellShortcuts();

  return (
    <LiveProvider>
      <Outlet />
      <CommandPalette />
    </LiveProvider>
  );
}
