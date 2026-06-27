/**
 * Global shell shortcuts.
 *
 * Bound once at the AppLayout mount, deliberately narrow so the editor /
 * form fields keep ownership of every other key:
 *
 *   Cmd/Ctrl+K — open the command palette
 *   Cmd/Ctrl+, — go to Settings
 *
 * That's it. No tabs to switch, no panels to toggle.
 */

import { useEffect } from 'react';
import { useNavigate } from 'react-router-dom';

let openPaletteImpl: (() => void) | null = null;
let closePaletteImpl: (() => void) | null = null;

/** The CommandPalette registers its open/close callbacks here so the
 *  keyboard hook (which doesn't know which palette instance is active)
 *  can flip it from anywhere in the tree. */
export function registerPaletteControls(open: () => void, close: () => void): () => void {
  openPaletteImpl = open;
  closePaletteImpl = close;
  return () => {
    if (openPaletteImpl === open) openPaletteImpl = null;
    if (closePaletteImpl === close) closePaletteImpl = null;
  };
}

/** Public open/close hooks for any UI affordance (MenuBar's ⌘K
 *  button, View menu's "Command Palette…", a sidebar button, etc.). */
export function openPalette(): void {
  openPaletteImpl?.();
}
export function closePalette(): void {
  closePaletteImpl?.();
}

export function useShellShortcuts(): void {
  const nav = useNavigate();
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const mod = e.metaKey || e.ctrlKey;
      if (!mod) return;

      if (e.key === 'k' || e.key === 'K') {
        e.preventDefault();
        if (openPaletteImpl) openPaletteImpl();
        return;
      }

      if (e.key === ',') {
        e.preventDefault();
        nav('/app/settings');
      }
    };
    const onEsc = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && closePaletteImpl) closePaletteImpl();
    };
    document.addEventListener('keydown', onKey);
    document.addEventListener('keydown', onEsc);
    return () => {
      document.removeEventListener('keydown', onKey);
      document.removeEventListener('keydown', onEsc);
    };
  }, [nav]);
}
