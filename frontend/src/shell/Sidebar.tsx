/**
 * Sidebar — slim left-edge nav rail.
 *
 * 52 px wide, always visible across every chrome'd route. Icon-only by
 * design — labels appear as a tooltip on hover. This keeps the canvas
 * +600 px wide on a 1024 px viewport (sidebar 52 + right rail 320/380 =
 * canvas 624/584).
 *
 * Five nav targets + Cmd+K shortcut at the bottom. Active route gets
 * the primary-coloured background so you always know where you are.
 */

import { NavLink } from 'react-router-dom';
import { openPalette } from './keyboard';

interface IconLink {
  to: string;
  label: string;
  icon: string;
  end?: boolean;
  /** Match additional path prefixes for the active highlight, e.g.
   *  /app/projects/abc/edit should still glow the Projects icon. */
  alsoMatches?: string[];
}

const NAV: IconLink[] = [
  { to: '/app',           label: 'Dashboard',  icon: '⌂', end: true },
  { to: '/app/portfolio', label: 'Portfolio',  icon: '▦' },
  { to: '/app/record',    label: 'Record',     icon: '🗎' },
  { to: '/app/projects',  label: 'Projects',   icon: '✎', alsoMatches: ['/app/projects/'] },
  { to: '/app/settings',  label: 'Settings',   icon: '⚙' },
];

export function Sidebar() {
  return (
    <aside className="w-[52px] shrink-0 border-r border-border bg-card flex flex-col items-stretch py-2 gap-1">
      {NAV.map((item) => (
        <NavLink
          key={item.to}
          to={item.to}
          end={item.end}
          title={item.label}
          aria-label={item.label}
          className={({ isActive }) => {
            // NavLink only matches the exact path for `end`. We extend
            // active state to additional prefixes (e.g. editor under
            // projects) via a custom check on window.location.
            const onPrefix =
              item.alsoMatches?.some((p) => typeof window !== 'undefined' && window.location.pathname.startsWith(p))
              ?? false;
            const active = isActive || onPrefix;
            return [
              'mx-1.5 h-9 rounded-md flex items-center justify-center text-[15px]',
              active
                ? 'bg-primary/15 text-primary'
                : 'text-muted-foreground hover:bg-secondary hover:text-foreground',
            ].join(' ');
          }}
        >
          <span aria-hidden="true">{item.icon}</span>
        </NavLink>
      ))}
      <div className="flex-1" />
      <button
        type="button"
        onClick={() => openPalette()}
        title="Command palette (⌘K)"
        aria-label="Command palette"
        className="mx-1.5 h-9 rounded-md flex items-center justify-center text-[10px] font-mono text-muted-foreground hover:bg-secondary hover:text-foreground border border-border"
      >
        ⌘K
      </button>
    </aside>
  );
}

export default Sidebar;
