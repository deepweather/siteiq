import { useEffect, useState } from 'react';
import { fetchPortfolio, loadProject, type PortfolioSite } from '../../services/api';
import { formatCurrency } from '../../utils/formatting';

interface PortfolioProps {
  onSelectSite: (projectId: string) => void;
  onClose: () => void;
}

const TYPE_COLORS: Record<string, string> = {
  Residential: 'bg-blue-100 text-blue-700',
  Commercial: 'bg-purple-100 text-purple-700',
  Infrastructure: 'bg-amber-100 text-amber-700',
};

export function Portfolio({ onSelectSite, onClose }: PortfolioProps) {
  const [sites, setSites] = useState<PortfolioSite[]>([]);
  const [loading, setLoading] = useState(true);
  const [switching, setSwitching] = useState<string | null>(null);

  useEffect(() => {
    fetchPortfolio().then(setSites).catch(() => {}).finally(() => setLoading(false));
  }, []);

  const handleSelect = async (id: string) => {
    setSwitching(id);
    await loadProject(id);
    onSelectSite(id);
  };

  const totalWorkers = sites.reduce((s, p) => s + p.workers, 0);
  const totalEquipment = sites.reduce((s, p) => s + p.equipment, 0);
  const totalWaste = sites.reduce((s, p) => s + p.estimated_monthly_waste, 0);
  const systemCostTotal = sites.length * 2000;

  if (loading) {
    return (
      <div className="h-screen flex items-center justify-center bg-background">
        <div className="text-muted-foreground text-sm">Loading portfolio...</div>
      </div>
    );
  }

  return (
    <div className="h-screen flex flex-col bg-background">
      <div className="h-12 bg-card border-b border-border flex items-center px-4 shrink-0 shadow-sm">
        <div className="flex items-center gap-2">
          <div className="w-7 h-7 bg-primary rounded-md flex items-center justify-center">
            <span className="text-primary-foreground text-xs font-bold">S</span>
          </div>
          <span className="font-semibold text-sm text-foreground">SiteIQ</span>
        </div>
        <div className="flex-1 text-center">
          <span className="text-sm font-medium text-foreground">Portfolio Overview</span>
        </div>
        <button
          onClick={onClose}
          className="text-xs text-muted-foreground hover:text-foreground px-3 py-1.5 rounded-md hover:bg-secondary border border-border"
        >
          Back to site
        </button>
      </div>

      <div className="flex-1 overflow-y-auto p-6">
        <div className="max-w-5xl mx-auto">
          {/* Portfolio summary */}
          <div className="grid grid-cols-4 gap-4 mb-8">
            <SummaryCard label="Active Sites" value={String(sites.length)} />
            <SummaryCard label="Total Workers" value={String(totalWorkers)} />
            <SummaryCard label="Equipment Tracked" value={String(totalEquipment)} />
            <SummaryCard
              label="Portfolio Waste"
              value={formatCurrency(totalWaste)}
              sublabel="/month"
              destructive
            />
          </div>

          {/* ROI banner */}
          <div className="bg-primary/5 border border-primary/20 rounded-lg p-4 mb-8 flex items-center justify-between">
            <div>
              <div className="text-xs text-primary font-semibold uppercase tracking-wider">Portfolio ROI</div>
              <div className="text-sm text-muted-foreground mt-1">
                SiteIQ cost: {formatCurrency(systemCostTotal)}/mo across {sites.length} sites
              </div>
            </div>
            <div className="text-right">
              <div className="font-mono text-2xl font-bold text-primary tabular-nums">
                {Math.round(totalWaste * 0.65 / systemCostTotal)}x
              </div>
              <div className="text-xs text-muted-foreground">payback ratio</div>
            </div>
          </div>

          {/* Site cards */}
          <div className="space-y-3">
            {sites.map(site => (
              <div
                key={site.id}
                className="bg-card border border-border rounded-lg p-4 hover:shadow-md transition-shadow"
              >
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
                    onClick={() => handleSelect(site.id)}
                    disabled={switching === site.id}
                    className="shrink-0 px-4 py-2 rounded-md text-xs font-medium bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50 transition-colors"
                  >
                    {switching === site.id ? 'Loading...' : 'Open Site'}
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
