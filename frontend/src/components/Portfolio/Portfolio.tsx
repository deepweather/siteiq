/**
 * Portfolio — full-screen takeover showing every project the workspace
 * can activate, with simulated waste totals and the same ROI framing as
 * the dashboard's right rail. Reached from the WorkspaceMenu (or
 * /app/portfolio deep link). "Back to dashboard" returns to /app.
 */
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { fetchPortfolio, type PortfolioSite } from '../../services/api';
import { formatCurrency } from '../../utils/formatting';
import { useLive } from '../../shell/useLive';

const RECOVERABLE_WASTE_FRACTION = 0.55;
const SYSTEM_COST_PER_SITE = 2000;

const TYPE_COLORS: Record<string, string> = {
  Residential: 'bg-blue-100 text-blue-700',
  Commercial: 'bg-purple-100 text-purple-700',
  Infrastructure: 'bg-amber-100 text-amber-700',
};

export function Portfolio() {
  const nav = useNavigate();
  const live = useLive();
  const [sites, setSites] = useState<PortfolioSite[]>([]);
  const [loading, setLoading] = useState(true);
  const [switching, setSwitching] = useState<string | null>(null);

  useEffect(() => {
    fetchPortfolio().then(setSites).catch(() => {}).finally(() => setLoading(false));
  }, []);

  const onOpen = async (id: string) => {
    setSwitching(id);
    try {
      await live.switchProject(id);
      nav('/app');
    } finally {
      setSwitching(null);
    }
  };

  if (loading) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <div className="text-muted-foreground text-sm">Loading portfolio…</div>
      </div>
    );
  }

  const totalWorkers = sites.reduce((s, p) => s + p.workers, 0);
  const totalEquipment = sites.reduce((s, p) => s + p.equipment, 0);
  const totalWaste = sites.reduce((s, p) => s + p.estimated_monthly_waste, 0);
  const systemCostTotal = sites.length * SYSTEM_COST_PER_SITE;
  const recoverableMonthly = totalWaste * RECOVERABLE_WASTE_FRACTION;
  const paybackRatio = systemCostTotal > 0 ? Math.round(recoverableMonthly / systemCostTotal) : 0;

  return (
    <div className="flex-1 overflow-y-auto p-8 bg-background">
      <div className="max-w-5xl mx-auto">
        <header className="mb-6">
          <h1 className="text-lg font-semibold text-foreground">Portfolio</h1>
          <p className="text-xs text-muted-foreground mt-0.5">Every project this workspace can activate.</p>
        </header>
        <div>
          <div className="grid grid-cols-4 gap-4 mb-8">
            <SummaryCard label="Active Sites" value={String(sites.length)} />
            <SummaryCard label="Total Workers" value={String(totalWorkers)} />
            <SummaryCard label="Equipment Tracked" value={String(totalEquipment)} />
            <SummaryCard label="Portfolio Waste" value={formatCurrency(totalWaste)} sublabel="/month" destructive />
          </div>

          <div className="bg-primary/5 border border-primary/20 rounded-lg p-4 mb-8 flex items-center justify-between">
            <div>
              <div className="text-xs text-primary font-semibold uppercase tracking-wider">Portfolio ROI</div>
              <div className="text-sm text-muted-foreground mt-1">
                SiteIQ cost: {formatCurrency(systemCostTotal)}/mo across {sites.length} sites
              </div>
            </div>
            <div className="text-right">
              <div className="font-mono text-2xl font-bold text-primary tabular-nums">{paybackRatio}x</div>
              <div className="text-xs text-muted-foreground">payback ratio</div>
            </div>
          </div>

          <div className="space-y-3">
            {sites.map((site) => (
              <div key={site.id} className="bg-card border border-border rounded-lg p-4 hover:shadow-md transition-shadow">
                <div className="flex items-start justify-between gap-4">
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1">
                      <h3 className="text-sm font-semibold text-foreground truncate">{site.name}</h3>
                      <span className={`text-[10px] font-medium px-1.5 py-0.5 rounded ${TYPE_COLORS[site.type] || 'bg-secondary text-muted-foreground'}`}>
                        {site.type}
                      </span>
                      {site.active && (
                        <span className="text-[10px] font-medium px-1.5 py-0.5 rounded bg-success/10 text-success">Active</span>
                      )}
                    </div>
                    <p className="text-xs text-muted-foreground">{site.description}</p>
                    <div className="flex items-center gap-6 mt-3">
                      <Stat label="Workers" value={String(site.workers)} />
                      <Stat label="Equipment" value={`${site.equipment} (${site.idle_equipment} idle)`} />
                      <Stat label="Zones" value={String(site.zones)} />
                      <Stat label="Day" value={String(site.day)} />
                      <Stat label="Est. Waste" value={`${formatCurrency(site.estimated_monthly_waste)}/mo`} destructive />
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={() => onOpen(site.id)}
                    disabled={switching === site.id}
                    className="shrink-0 px-4 py-2 rounded-md text-xs font-medium bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50 transition-colors"
                  >
                    {switching === site.id ? 'Loading…' : 'Open Site'}
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

function SummaryCard({ label, value, sublabel, destructive }: { label: string; value: string; sublabel?: string; destructive?: boolean }) {
  return (
    <div className="bg-card border border-border rounded-lg p-4">
      <div className="text-[10px] text-muted-foreground font-medium uppercase tracking-wider">{label}</div>
      <div className={`font-mono text-xl font-bold tabular-nums mt-1 ${destructive ? 'text-destructive' : 'text-foreground'}`}>
        {value}
        {sublabel && <span className="text-xs text-muted-foreground font-normal">{sublabel}</span>}
      </div>
    </div>
  );
}

function Stat({ label, value, destructive }: { label: string; value: string; destructive?: boolean }) {
  return (
    <div>
      <div className="text-[10px] text-muted-foreground">{label}</div>
      <div className={`text-xs font-medium font-mono tabular-nums ${destructive ? 'text-destructive' : 'text-foreground'}`}>{value}</div>
    </div>
  );
}

export default Portfolio;
