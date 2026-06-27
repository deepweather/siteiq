/**
 * MenuBar — the single top row of the app shell.
 *
 * Replaces the previous AppHeader. Real desktop apps put their menus,
 * persistent identity (project / clock / speed) and a global search
 * affordance in one row, in that order. We do the same:
 *
 *   [S]  Site  View  Account  Help        Wohnanlage… ▾  Day 47  11:01  ⏸ 1× 2× 5× 10×  ● Live   ⌘K
 *
 * The menus are short and verb-shaped, not theatre. Project switcher /
 * clock / speed live in this row even on non-dashboard routes because
 * the simulation is always running in the background.
 */

import { useEffect, useRef, useState, type ReactNode } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../lib/auth/AuthProvider';
import { useLive } from './useLive';
import { auth, clearCsrfCache, fetchProjects, type ProjectSummary } from '../services/api';
import { formatSimTime } from '../utils/formatting';
import { openPalette } from './keyboard';

export function MenuBar() {
  const live = useLive();
  const nav = useNavigate();
  const { user, org, refresh } = useAuth();
  const [openIdx, setOpenIdx] = useState<number | null>(null);
  const [projectMenuAnchor, setProjectMenuAnchor] = useState<DOMRect | null>(null);
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const projectRef = useRef<HTMLButtonElement>(null);
  const menuRootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    fetchProjects().then(setProjects).catch(() => {});
  }, []);

  // Close menu dropdowns on outside click / Esc.
  useEffect(() => {
    if (openIdx === null) return;
    const onMouseDown = (e: MouseEvent) => {
      if (!menuRootRef.current?.contains(e.target as Node)) setOpenIdx(null);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpenIdx(null);
    };
    document.addEventListener('mousedown', onMouseDown);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onMouseDown);
      document.removeEventListener('keydown', onKey);
    };
  }, [openIdx]);

  const handleSignOut = async () => {
    await auth.logout();
    clearCsrfCache();
    await refresh();
    nav('/login', { replace: true });
  };

  const goto = (path: string) => nav(path);

  const menus: { label: string; items: MenuItem[] }[] = [
    {
      label: 'Site',
      items: [
        { label: live.paused ? 'Resume simulation' : 'Pause simulation', onClick: () => void live.togglePaused(), shortcut: 'Space' },
        { separator: true },
        { label: 'Speed 1×', checked: live.speed === 1, onClick: () => void live.setSpeed(1) },
        { label: 'Speed 2×', checked: live.speed === 2, onClick: () => void live.setSpeed(2) },
        { label: 'Speed 5×', checked: live.speed === 5, onClick: () => void live.setSpeed(5) },
        { label: 'Speed 10×', checked: live.speed === 10, onClick: () => void live.setSpeed(10) },
      ],
    },
    {
      label: 'View',
      items: [
        { label: 'Dashboard', onClick: () => goto('/app') },
        { label: 'Portfolio', onClick: () => goto('/app/portfolio') },
        { label: 'All projects', onClick: () => goto('/app/projects') },
        { separator: true },
        { label: 'Command Palette…', onClick: () => openPalette(), shortcut: '⌘K' },
      ],
    },
    {
      label: 'Account',
      items: [
        { label: 'Settings', onClick: () => goto('/app/settings'), shortcut: '⌘,' },
        { label: 'Workspaces', onClick: () => goto('/app/settings/orgs') },
        { separator: true },
        { label: user?.email ?? 'Signed in', disabled: true },
        { label: 'Sign out', onClick: handleSignOut },
      ],
    },
    {
      label: 'Help',
      items: [
        { label: 'Documentation', onClick: () => window.open('https://github.com', '_blank', 'noopener,noreferrer') },
        { label: `About SiteIQ — ${org?.name ?? ''}`, disabled: true },
      ],
    },
  ];

  return (
    <header className="h-9 bg-card border-b border-border flex items-center px-2 shrink-0 shadow-sm select-none gap-1">
      <div className="flex items-center gap-2 pr-2 mr-1 shrink-0">
        <div className="w-5 h-5 bg-primary rounded flex items-center justify-center">
          <span className="text-primary-foreground text-[10px] font-bold">S</span>
        </div>
      </div>

      {/* Menus */}
      <div ref={menuRootRef} className="relative flex items-center gap-0.5 shrink-0">
        {menus.map((m, i) => (
          <div key={m.label} className="relative">
            <button
              type="button"
              onMouseEnter={() => { if (openIdx !== null) setOpenIdx(i); }}
              onClick={() => setOpenIdx(openIdx === i ? null : i)}
              className={`px-2.5 h-6 text-[12px] rounded ${
                openIdx === i
                  ? 'bg-secondary text-foreground'
                  : 'text-muted-foreground hover:bg-secondary hover:text-foreground'
              }`}
            >
              {m.label}
            </button>
            {openIdx === i && (
              <MenuDropdown items={m.items} onPick={() => setOpenIdx(null)} />
            )}
          </div>
        ))}
      </div>

      <div className="flex-1" />

      {/* Project switcher (the only menu that opens a wide popover with
       *  a project list). Click opens WorkspaceMenu from a separate
       *  popover anchor — keeps the project list separate from the
       *  short menu dropdowns. */}
      <button
        ref={projectRef}
        type="button"
        onClick={() => {
          const r = projectRef.current?.getBoundingClientRect();
          if (r) setProjectMenuAnchor(r);
        }}
        aria-haspopup="menu"
        className="flex items-center gap-1.5 text-[13px] font-semibold text-foreground hover:text-primary px-2 h-7 rounded hover:bg-secondary shrink-0 min-w-0"
        title="Switch project"
      >
        <span className="truncate max-w-[220px]">{live.site?.name ?? 'No project'}</span>
        <svg className="w-3 h-3 text-muted-foreground shrink-0" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M3 5l3 3 3-3" />
        </svg>
      </button>

      <div className="flex items-center gap-2 text-[11px] whitespace-nowrap shrink-0 px-1">
        <span className="text-muted-foreground">Day {live.simDay}</span>
        <span className="font-mono tabular-nums text-foreground">{formatSimTime(live.simTime)}</span>
      </div>

      <div className="flex items-center gap-1 shrink-0">
        <button
          type="button"
          onClick={() => void live.togglePaused()}
          className="w-6 h-6 flex items-center justify-center rounded text-[11px] border border-border hover:bg-secondary text-muted-foreground"
          title={live.paused ? 'Resume' : 'Pause'}
          aria-label={live.paused ? 'Resume simulation' : 'Pause simulation'}
        >
          {live.paused ? '▶' : '⏸'}
        </button>
        {[1, 2, 5, 10].map((s) => (
          <button
            key={s}
            type="button"
            onClick={() => void live.setSpeed(s)}
            className={`px-1.5 h-6 rounded text-[11px] font-mono shrink-0 ${
              live.speed === s
                ? 'bg-primary text-primary-foreground'
                : 'border border-border text-muted-foreground hover:bg-secondary'
            }`}
            aria-label={`Set speed ${s}x`}
            aria-pressed={live.speed === s}
          >
            {s}×
          </button>
        ))}
      </div>

      <div className="flex items-center gap-1.5 px-2 py-0.5 rounded bg-secondary shrink-0">
        <span className={`w-1.5 h-1.5 rounded-full ${live.connected ? 'bg-success' : 'bg-destructive'}`} />
        <span className="text-[11px] text-muted-foreground">{live.connected ? 'Live' : 'Offline'}</span>
      </div>

      <button
        type="button"
        onClick={() => openPalette()}
        className="ml-1 text-[11px] text-muted-foreground hover:text-foreground hover:bg-secondary rounded px-2 h-6 flex items-center gap-1.5 border border-border shrink-0"
        title="Command palette"
      >
        <span className="font-mono">⌘K</span>
      </button>

      {projectMenuAnchor && (
        <ProjectSwitcherPopover
          anchor={projectMenuAnchor}
          projects={projects}
          currentSlug={live.site?.id ?? null}
          currentName={live.site?.name ?? null}
          onClose={() => setProjectMenuAnchor(null)}
          onPick={async (slug) => {
            setProjectMenuAnchor(null);
            await live.switchProject(slug);
          }}
        />
      )}
    </header>
  );
}

interface MenuItem {
  label?: string;
  shortcut?: string;
  checked?: boolean;
  disabled?: boolean;
  separator?: boolean;
  onClick?: () => void;
}

function MenuDropdown({ items, onPick }: { items: MenuItem[]; onPick: () => void }) {
  return (
    <div className="absolute top-full left-0 mt-0.5 min-w-[200px] bg-card border border-border rounded-md shadow-lg z-50 py-1">
      {items.map((it, i) => {
        if (it.separator) return <div key={i} className="my-1 border-t border-border" />;
        return (
          <button
            key={i}
            type="button"
            disabled={it.disabled}
            onClick={() => {
              if (it.disabled) return;
              it.onClick?.();
              onPick();
            }}
            className={`w-full px-3 py-1.5 text-left text-[12px] flex items-center justify-between gap-4 ${
              it.disabled ? 'text-muted-foreground/60 cursor-default' : 'text-foreground hover:bg-secondary'
            }`}
          >
            <span className="flex items-center gap-2">
              {it.checked !== undefined && (
                <span className="w-3 inline-block text-primary text-center">{it.checked ? '✓' : ''}</span>
              )}
              {it.label}
            </span>
            {it.shortcut && <span className="text-[10px] text-muted-foreground font-mono">{it.shortcut}</span>}
          </button>
        );
      })}
    </div>
  );
}

function ProjectSwitcherPopover({
  anchor, projects, currentName, onClose, onPick,
}: {
  anchor: DOMRect;
  projects: ProjectSummary[];
  currentSlug: string | null;
  currentName: string | null;
  onClose: () => void;
  onPick: (slug: string) => void;
}) {
  const rootRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const onDown = (e: MouseEvent) => {
      if (!rootRef.current?.contains(e.target as Node)) onClose();
    };
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    document.addEventListener('mousedown', onDown);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDown);
      document.removeEventListener('keydown', onKey);
    };
  }, [onClose]);

  return (
    <div
      ref={rootRef}
      className="fixed z-50 w-[320px] bg-card border border-border rounded-lg shadow-xl overflow-hidden"
      style={{ top: anchor.bottom + 4, left: anchor.left }}
      role="menu"
    >
      <div className="px-4 pt-3 pb-1 text-[10px] uppercase tracking-wider text-muted-foreground font-semibold">
        Switch project
      </div>
      <div className="max-h-[320px] overflow-y-auto py-1">
        {projects.map((p) => {
          const isActive = currentName === p.name;
          return (
            <button
              key={p.id}
              type="button"
              onClick={() => onPick(p.slug)}
              className={`w-full px-4 py-1.5 text-left text-sm flex items-center gap-2 hover:bg-secondary ${
                isActive ? 'text-foreground' : 'text-muted-foreground'
              }`}
            >
              <span className={`w-1.5 h-1.5 rounded-full ${isActive ? 'bg-success' : 'bg-transparent border border-border'}`} />
              <span className="flex-1 truncate">{p.name}</span>
              <span className="text-[9px] uppercase tracking-wider opacity-50">{p.type}</span>
            </button>
          );
        })}
      </div>
    </div>
  );
}

export default MenuBar;

// Re-export so tests can pass a custom set of items if needed in the future.
export type { MenuItem };

export function MenuSpacer({ children }: { children?: ReactNode }) {
  return <>{children}</>;
}
