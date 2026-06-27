/**
 * CommandPalette — ⌘K overlay.
 *
 * Single-purpose: speed up power-user navigation. The 3-minute demo
 * viewer never sees this; the daily operator hits it without thinking.
 *
 * Verbs:
 *   - Switch project (live engine swap)
 *   - Apply recommendation (by title)
 *   - Go to portfolio / editor / settings / project list
 *   - Set speed / pause-resume
 *   - Sign out
 *
 * Esc closes. ↑↓ navigates. Enter runs. Mouse always works too.
 */

import { useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useLive } from './useLive';
import {
  applyRecommendation,
  auth,
  clearCsrfCache,
  fetchProjects,
  type ProjectSummary,
} from '../services/api';
import { listProjects, type ProjectListItem } from '../services/projectsApi';
import { registerPaletteControls } from './keyboard';

interface Command {
  id: string;
  label: string;
  hint?: string;
  group: 'Projects' | 'Recommendations' | 'Go to' | 'Site' | 'Account';
  run: () => void | Promise<void>;
}

export function CommandPalette() {
  const live = useLive();
  const nav = useNavigate();
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState('');
  const [highlight, setHighlight] = useState(0);
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [orgProjects, setOrgProjects] = useState<ProjectListItem[]>([]);
  const inputRef = useRef<HTMLInputElement>(null);

  // Register open/close with the keyboard hook.
  useEffect(() => {
    return registerPaletteControls(() => setOpen(true), () => setOpen(false));
  }, []);

  // Load lists when the palette opens.
  useEffect(() => {
    if (!open) return;
    fetchProjects().then(setProjects).catch(() => {});
    listProjects().then(setOrgProjects).catch(() => {});
    setQuery('');
    setHighlight(0);
    setTimeout(() => inputRef.current?.focus(), 0);
  }, [open]);

  const onSignOut = async () => {
    await auth.logout();
    clearCsrfCache();
    nav('/login', { replace: true });
  };

  const activeOrgProject = orgProjects.find((p) => p.is_active);
  const activeEditTarget = activeOrgProject
    ? `/app/projects/${activeOrgProject.id}/edit`
    : '/app/projects';

  const commands: Command[] = useMemo(() => {
    if (!open) return [];
    const list: Command[] = [];

    for (const p of projects) {
      list.push({
        id: `project.${p.slug}`,
        group: 'Projects',
        label: `Switch to: ${p.name}`,
        hint: p.type,
        run: () => live.switchProject(p.slug),
      });
    }

    for (const r of live.recommendations) {
      if (r.applied) continue;
      list.push({
        id: `rec.${r.id}`,
        group: 'Recommendations',
        label: `Apply: ${r.title}`,
        hint: `+€${Math.round(r.monthly_savings)}/mo`,
        run: async () => {
          await applyRecommendation(r.id);
          await live.refreshRecommendations();
        },
      });
    }

    list.push(
      { id: 'go.dashboard', group: 'Go to', label: 'Dashboard', run: () => nav('/app') },
      { id: 'go.portfolio', group: 'Go to', label: 'Portfolio', run: () => nav('/app/portfolio') },
      { id: 'go.projects', group: 'Go to', label: 'All projects', run: () => nav('/app/projects') },
      { id: 'go.edit', group: 'Go to', label: 'Edit current project', run: () => nav(activeEditTarget) },
      { id: 'go.settings', group: 'Go to', label: 'Settings', hint: '⌘,', run: () => nav('/app/settings') },
    );

    list.push(
      { id: 'site.pause', group: 'Site', label: live.paused ? 'Resume simulation' : 'Pause simulation', run: () => { void live.togglePaused(); } },
      { id: 'site.speed.1', group: 'Site', label: 'Set speed 1×', run: () => { void live.setSpeed(1); } },
      { id: 'site.speed.2', group: 'Site', label: 'Set speed 2×', run: () => { void live.setSpeed(2); } },
      { id: 'site.speed.5', group: 'Site', label: 'Set speed 5×', run: () => { void live.setSpeed(5); } },
      { id: 'site.speed.10', group: 'Site', label: 'Set speed 10×', run: () => { void live.setSpeed(10); } },
    );

    list.push({ id: 'account.signout', group: 'Account', label: 'Sign out', run: onSignOut });
    return list;
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, projects, live.recommendations, live.paused, activeEditTarget]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return commands;
    return commands.filter(
      (c) => c.label.toLowerCase().includes(q) || c.group.toLowerCase().includes(q),
    );
  }, [commands, query]);

  const grouped = useMemo(() => {
    const m: Record<string, Command[]> = {};
    for (const c of filtered) {
      if (!m[c.group]) m[c.group] = [];
      m[c.group].push(c);
    }
    return m;
  }, [filtered]);

  useEffect(() => {
    if (highlight >= filtered.length) setHighlight(0);
  }, [filtered.length, highlight]);

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Escape') { setOpen(false); return; }
    if (e.key === 'ArrowDown') { e.preventDefault(); setHighlight((h) => Math.min(filtered.length - 1, h + 1)); return; }
    if (e.key === 'ArrowUp') { e.preventDefault(); setHighlight((h) => Math.max(0, h - 1)); return; }
    if (e.key === 'Enter') {
      e.preventDefault();
      const c = filtered[highlight];
      if (c) {
        void c.run();
        setOpen(false);
      }
    }
  };

  if (!open) return null;

  let cursor = -1;

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center pt-24 px-4 bg-black/30 backdrop-blur-sm"
      onMouseDown={(e) => { if (e.target === e.currentTarget) setOpen(false); }}
    >
      <div className="w-full max-w-xl bg-card border border-border rounded-lg shadow-2xl overflow-hidden">
        <input
          ref={inputRef}
          value={query}
          onChange={(e) => { setQuery(e.target.value); setHighlight(0); }}
          onKeyDown={onKeyDown}
          placeholder="Search projects, recommendations, actions…"
          className="w-full px-4 py-3 text-sm bg-transparent border-b border-border focus:outline-none"
        />
        <div className="max-h-[60vh] overflow-y-auto">
          {filtered.length === 0 && (
            <div className="p-4 text-sm text-muted-foreground">No matches.</div>
          )}
          {Object.entries(grouped).map(([group, items]) => (
            <div key={group}>
              <div className="px-4 pt-3 pb-1 text-[10px] uppercase tracking-wider text-muted-foreground font-semibold">
                {group}
              </div>
              {items.map((c) => {
                cursor += 1;
                const idx = cursor;
                const active = idx === highlight;
                return (
                  <button
                    type="button"
                    key={c.id}
                    onMouseEnter={() => setHighlight(idx)}
                    onClick={() => { void c.run(); setOpen(false); }}
                    className={`w-full px-4 py-2 text-left flex items-center justify-between gap-4 text-[13px] ${
                      active ? 'bg-primary/10 text-foreground' : 'text-foreground hover:bg-secondary'
                    }`}
                  >
                    <span className="truncate">{c.label}</span>
                    {c.hint && <span className="text-[10px] text-muted-foreground font-mono shrink-0">{c.hint}</span>}
                  </button>
                );
              })}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

export default CommandPalette;
