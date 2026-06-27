/**
 * StatusBar — slim bottom row, real desktop-app finish.
 *
 * Cells, left to right:
 *   • Workspace name (clickable → /app/settings/orgs)
 *   • Pending recs count + monthly recoverable € (clickable → opens palette)
 *   • Current monthly waste (cosmetic, mirrors the right rail's hero)
 *   • Build version
 *
 * Designed to be informative-not-intrusive. ~24 px tall.
 */

import { useEffect, useState } from 'react';
import { useAuth } from '../lib/auth/AuthProvider';
import { useLive } from './useLive';
import { fetchVersion, type VersionInfo } from '../services/api';
import { formatCurrency } from '../utils/formatting';
import { openPalette } from './keyboard';
import { useNavigate } from 'react-router-dom';

export function StatusBar() {
  const { org } = useAuth();
  const live = useLive();
  const nav = useNavigate();
  const [version, setVersion] = useState<VersionInfo | null>(null);

  useEffect(() => {
    fetchVersion().then(setVersion).catch(() => {});
  }, []);

  const pending = live.recommendations.filter((r) => !r.applied);
  const pendingMonthly = pending.reduce((s, r) => s + r.monthly_savings, 0);

  return (
    <div className="h-6 bg-card border-t border-border flex items-center text-[10px] font-mono tabular-nums shrink-0 px-2 gap-1">
      <Cell title="Workspace" onClick={() => nav('/app/settings/orgs')}>
        <span className="text-muted-foreground">●</span>
        <span className="text-foreground truncate max-w-[140px]">{org?.name ?? '—'}</span>
      </Cell>
      <Sep />
      {pendingMonthly > 0 ? (
        <>
          <Cell title="Pending recommendations" onClick={() => openPalette()}>
            <span className="text-primary">⚡</span>
            <span className="text-foreground">{pending.length}</span>
            <span className="text-muted-foreground">·</span>
            <span className="text-foreground">+{formatCurrency(pendingMonthly)}/mo</span>
          </Cell>
          <Sep />
        </>
      ) : null}
      <div className="flex-1" />
      {live.currentWaste && (
        <>
          <Cell title="Recoverable waste this month">
            <span className="text-destructive">€</span>
            <span className="text-foreground">{formatCurrency(live.currentWaste.total_monthly)}/mo</span>
          </Cell>
          <Sep />
        </>
      )}
      {version && (
        <Cell title={`Build ${version.commit}${version.built_at ? ` · ${version.built_at}` : ''}`}>
          <span className="text-muted-foreground">v</span>
          <span className="text-muted-foreground">{version.short}</span>
        </Cell>
      )}
    </div>
  );
}

function Cell({ title, children, onClick }: { title: string; children: React.ReactNode; onClick?: () => void }) {
  const className = 'flex items-center gap-1.5 px-1.5 h-5 rounded';
  if (onClick) {
    return (
      <button type="button" title={title} onClick={onClick} className={`${className} hover:bg-secondary`}>
        {children}
      </button>
    );
  }
  return <div title={title} className={className}>{children}</div>;
}

function Sep() {
  return <span className="w-px h-3 bg-border mx-0.5" />;
}

export default StatusBar;
