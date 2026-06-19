import { useState } from 'react';
import type { WasteSummary, Recommendation } from '../../types/analytics';
import type { ScheduleEntry } from '../../types/site';
import { WasteReport } from './WasteReport';
import { Recommendations } from './Recommendations';
import { Timeline } from './Timeline';
import { AssetDetail } from './AssetDetail';

interface RightPanelProps {
  waste: WasteSummary | null;
  baseline: WasteSummary | null;
  savings: { toilet: number; material: number; equipment: number; total: number } | null;
  schedule: ScheduleEntry[];
  currentDay: number;
  onRecsChange: (recs: Recommendation[]) => void;
  selectedAssetId: string | null;
  onAssetDeselect: () => void;
}

type Tab = 'waste' | 'recs' | 'timeline';

export function RightPanel({ waste, baseline, savings, schedule, currentDay, onRecsChange, selectedAssetId, onAssetDeselect }: RightPanelProps) {
  const [activeTab, setActiveTab] = useState<Tab>('waste');

  const tabs: { id: Tab; label: string }[] = [
    { id: 'waste', label: 'Waste' },
    { id: 'recs', label: 'Optimize' },
    { id: 'timeline', label: 'Timeline' },
  ];

  return (
    <div className="w-[380px] shrink-0 bg-card border-l border-border flex flex-col h-full shadow-sm">
      {selectedAssetId ? (
        <>
          <div className="flex items-center justify-between border-b border-border shrink-0 px-3 py-2.5">
            <span className="text-xs font-medium text-foreground">Asset Detail</span>
            <button
              onClick={onAssetDeselect}
              className="text-xs text-muted-foreground hover:text-foreground px-2 py-1 rounded-md hover:bg-secondary"
            >
              Back
            </button>
          </div>
          <div className="flex-1 overflow-y-auto p-3">
            <AssetDetail assetId={selectedAssetId} onClose={onAssetDeselect} />
          </div>
        </>
      ) : (
        <>
          <div className="flex border-b border-border shrink-0">
            {tabs.map((tab) => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`flex-1 py-3 text-xs font-medium border-b-2 ${
                  activeTab === tab.id
                    ? 'text-primary border-primary'
                    : 'text-muted-foreground border-transparent hover:text-foreground'
                }`}
              >
                {tab.label}
              </button>
            ))}
          </div>
          <div className="flex-1 overflow-y-auto p-3">
            {activeTab === 'waste' && (
              <WasteReport waste={waste} baseline={baseline} savings={savings} />
            )}
            {activeTab === 'recs' && (
              <Recommendations onRecsChange={onRecsChange} />
            )}
            {activeTab === 'timeline' && (
              <Timeline schedule={schedule} currentDay={currentDay} />
            )}
          </div>
        </>
      )}
    </div>
  );
}
