import { PHASE_COLORS, PHASE_LABELS } from '../../utils/colors';
import type { ScheduleEntry } from '../../types/site';

interface TimelineProps {
  schedule: ScheduleEntry[];
  currentDay: number;
}

const TOTAL_DAYS = 120;

export function Timeline({ schedule, currentDay }: TimelineProps) {
  const zoneIds = ['zone-a', 'zone-b', 'zone-c', 'zone-d', 'zone-e'];
  const zoneLabels: Record<string, string> = {
    'zone-a': 'Zone A', 'zone-b': 'Zone B', 'zone-c': 'Zone C',
    'zone-d': 'Zone D', 'zone-e': 'Zone E',
  };

  const dayMarkers = [0, 30, 60, 90, 120];

  return (
    <div className="space-y-4">
      <div className="border border-border rounded-lg p-4">
        <div className="text-xs text-muted-foreground font-medium mb-4">Project Schedule</div>

        <div className="relative">
          <div className="flex text-[10px] text-muted-foreground mb-2 ml-16">
            {dayMarkers.map(d => (
              <span
                key={d}
                className="absolute font-mono tabular-nums"
                style={{ left: `calc(64px + ${(d / TOTAL_DAYS) * 100}% * (1 - 64px / 100%))` }}
              >
                {d}
              </span>
            ))}
          </div>

          <div className="mt-6 space-y-1.5">
            {zoneIds.map(zoneId => {
              const entries = schedule.filter(s => s.zone_id === zoneId);
              return (
                <div key={zoneId} className="flex items-center h-6">
                  <span className="w-16 text-xs text-muted-foreground shrink-0">{zoneLabels[zoneId]}</span>
                  <div className="flex-1 relative h-5 bg-secondary rounded">
                    {entries.map((entry, i) => {
                      const left = (entry.start_day / TOTAL_DAYS) * 100;
                      const width = ((entry.end_day - entry.start_day) / TOTAL_DAYS) * 100;
                      const isCurrent = currentDay >= entry.start_day && currentDay <= entry.end_day;
                      return (
                        <div
                          key={i}
                          className={`absolute top-0 h-full rounded text-[8px] flex items-center justify-center text-white font-medium overflow-hidden ${
                            isCurrent ? 'ring-2 ring-primary/50' : ''
                          }`}
                          style={{
                            left: `${left}%`,
                            width: `${width}%`,
                            backgroundColor: PHASE_COLORS[entry.phase] || '#71717a',
                            opacity: currentDay > entry.end_day ? 0.4 : 0.85,
                          }}
                          title={`${PHASE_LABELS[entry.phase] || entry.phase}: Day ${entry.start_day}-${entry.end_day}`}
                        >
                          {width > 8 ? (PHASE_LABELS[entry.phase] || entry.phase).slice(0, 6) : ''}
                        </div>
                      );
                    })}
                    <div
                      className="absolute top-0 w-0.5 h-full bg-foreground z-10 rounded-full"
                      style={{ left: `${(currentDay / TOTAL_DAYS) * 100}%` }}
                    />
                  </div>
                </div>
              );
            })}
          </div>

          <div className="flex items-center gap-1.5 mt-3 text-xs text-muted-foreground ml-16">
            <span className="w-2 h-2 bg-foreground rounded-full" />
            <span className="font-mono tabular-nums">Day {currentDay}</span>
          </div>
        </div>
      </div>

      <div className="border border-border rounded-lg p-4">
        <div className="text-xs text-muted-foreground font-medium mb-3">Lookahead</div>
        <div className="space-y-3">
          <LookaheadItem
            zone="Zone B"
            color={PHASE_COLORS.mep_roughin}
            text="MEP rough-in est. complete in ~18 days. Begin staging close-in materials."
          />
          <LookaheadItem
            zone="Zone C"
            color={PHASE_COLORS.structural}
            text="Structural 65% complete. Rebar demand peaks in 8 days."
          />
          <LookaheadItem
            zone="Zone D"
            color={PHASE_COLORS.foundation}
            text="Foundation pour starts in 5 days. Schedule concrete pump return."
          />
        </div>
      </div>
    </div>
  );
}

function LookaheadItem({ zone, color, text }: { zone: string; color: string; text: string }) {
  return (
    <div className="flex gap-2 text-xs">
      <span
        className="w-1 shrink-0 rounded-full"
        style={{ backgroundColor: color, minHeight: '100%' }}
      />
      <div>
        <span className="font-medium text-foreground">{zone}:</span>{' '}
        <span className="text-muted-foreground">{text}</span>
      </div>
    </div>
  );
}
