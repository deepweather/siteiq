/**
 * Chrome — the persistent desktop-app shell.
 *
 * Wraps a route's <Outlet/> with:
 *   - MenuBar at top (h-9)
 *   - Sidebar on left (52 px)
 *   - StatusBar at bottom (h-6)
 *
 * Mounted by App.tsx as a layout route around every /app/* route that
 * is part of the operational surface. The editor opts out and renders
 * full-screen because its own three-panel layout needs the whole
 * viewport.
 *
 * The LiveProvider + CommandPalette live one layer up in AppLayout so
 * the editor still has them.
 */

import { Outlet } from 'react-router-dom';
import { MenuBar } from './MenuBar';
import { Sidebar } from './Sidebar';
import { StatusBar } from './StatusBar';

export default function Chrome() {
  return (
    <div className="h-screen flex flex-col overflow-hidden bg-background text-foreground">
      <MenuBar />
      <div className="flex-1 flex min-h-0">
        <Sidebar />
        <main className="flex-1 flex flex-col min-w-0 min-h-0">
          <Outlet />
        </main>
      </div>
      <StatusBar />
    </div>
  );
}
