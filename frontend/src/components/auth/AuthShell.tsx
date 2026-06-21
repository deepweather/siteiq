/**
 * AuthShell — split layout used by every auth screen.
 *
 * Left: form card (handed in via children).
 * Right (hidden on mobile): a quiet, kinetic visual — the SiteIQ wordmark,
 * a subtle pulsing waste counter that ticks up while the page is open,
 * and a one-line value prop. Same orange primary + JetBrains Mono digits
 * as the product so the funnel feels coherent.
 */
import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';
import { LiveWasteCounter } from '../landing/LiveWasteCounter';

export function AuthShell({
  title,
  subtitle,
  children,
  footer,
}: {
  title: string;
  subtitle?: string;
  children: ReactNode;
  footer?: ReactNode;
}) {
  return (
    <div className="min-h-screen bg-background grid lg:grid-cols-2">
      <div className="flex flex-col justify-between p-8 lg:p-12">
        <Link to="/" className="flex items-center gap-2 group">
          <span className="w-8 h-8 bg-primary rounded-lg flex items-center justify-center">
            <span className="text-primary-foreground text-base font-bold">S</span>
          </span>
          <span className="font-semibold text-foreground tracking-tight">SiteIQ</span>
        </Link>

        <div className="w-full max-w-sm mx-auto">
          <h1 className="text-2xl font-semibold tracking-tight mb-1">{title}</h1>
          {subtitle && <p className="text-muted-foreground text-sm mb-6">{subtitle}</p>}
          {children}
        </div>

        <div className="text-xs text-muted-foreground">{footer}</div>
      </div>

      <div className="hidden lg:flex flex-col justify-between bg-muted/40 border-l border-border p-12">
        <div>
          <div className="text-xs uppercase tracking-widest text-muted-foreground font-semibold">
            Recoverable waste, live
          </div>
          <div className="mt-3 font-mono text-5xl font-semibold tabular-nums tracking-tight">
            <LiveWasteCounter perDayEUR={3700} />
          </div>
          <div className="text-sm text-muted-foreground mt-2">
            being burnt across simulated SiteIQ sites since you opened this page.
          </div>
        </div>

        <blockquote className="border-l-2 border-primary pl-4 text-sm text-foreground/80">
          “35% productive time is the construction industry's open secret.
          We make it visible — and recoverable.”
        </blockquote>
      </div>
    </div>
  );
}
