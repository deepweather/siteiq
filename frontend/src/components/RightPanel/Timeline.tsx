import { PHASE_COLORS, PHASE_LABELS } from '../../utils/colors';
import type { ScheduleEntry, Zone } from '../../types/site';

interface TimelineProps {
  schedule: ScheduleEntry[];
  currentDay: number;
  zones: Zone[];
}

function buildDayMarkers(totalDays: number): number[] {
  // ~5 evenly-spaced markers rounded to the nearest 10 days for legibility.
  const step = Math.max(10, Math.round(totalDays / 4 / 10) * 10);
  const markers: number[] = [];
  for (let d = 0; d <= totalDays; d += step) markers.push(d);
  if (markers[markers.length - 1] !== totalDays) markers.push(totalDays);
  return markers;
}

export function Timeline({ schedule, currentDay, zones }: TimelineProps) {
  // Zones from the actual project — preserves real labels (e.g. "Turm Ost")
  // and includes any zone count (the Frankfurt project has zone-f).
  const zoneIds = zones.map(z => z.id);
  const zoneLabels: Record<string, string> = Object.fromEntries(
    zones.map(z => [z.id, z.label]),
  );

  // Project duration derived from the schedule, with headroom for the
  // current-day marker (Munich's bridge runs to day 210, current day 135).
  const scheduleMax = schedule.reduce((m, s) => Math.max(m, s.end_day), 0);
  const TOTAL_DAYS = Math.max(120, scheduleMax, currentDay + 5);
  const dayMarkers = buildDayMarkers(TOTAL_DAYS);

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
        <div className="text-xs text-muted-foreground font-medium mb-3">
          Lookahead — next 30 days
        </div>
        <Lookahead schedule={schedule} currentDay={currentDay} zones={zones} />
      </div>
    </div>
  );
}

const LOOKAHEAD_HORIZON_DAYS = 30;
const LOOKAHEAD_MAX_ITEMS = 4;

interface LookaheadEvent {
  zoneLabel: string;
  phase: string;
  daysAway: number;
  kind: 'starts' | 'finishes';
}

function buildLookahead(
  schedule: ScheduleEntry[],
  currentDay: number,
  zones: Zone[],
): LookaheadEvent[] {
  const labelById: Record<string, string> = Object.fromEntries(
    zones.map((z) => [z.id, z.label]),
  );
  const events: LookaheadEvent[] = [];
  for (const e of schedule) {
    const startsIn = e.start_day - currentDay;
    if (startsIn > 0 && startsIn <= LOOKAHEAD_HORIZON_DAYS) {
      events.push({
        zoneLabel: labelById[e.zone_id] ?? e.zone_id,
        phase: e.phase,
        daysAway: startsIn,
        kind: 'starts',
      });
    }
    const endsIn = e.end_day - currentDay;
    if (endsIn > 0 && endsIn <= LOOKAHEAD_HORIZON_DAYS && currentDay >= e.start_day) {
      events.push({
        zoneLabel: labelById[e.zone_id] ?? e.zone_id,
        phase: e.phase,
        daysAway: endsIn,
        kind: 'finishes',
      });
    }
  }
  return events
    .sort((a, b) => a.daysAway - b.daysAway)
    .slice(0, LOOKAHEAD_MAX_ITEMS);
}

function Lookahead({
  schedule,
  currentDay,
  zones,
}: {
  schedule: ScheduleEntry[];
  currentDay: number;
  zones: Zone[];
}) {
  const events = buildLookahead(schedule, currentDay, zones);
  if (events.length === 0) {
    return (
      <p className="text-xs text-muted-foreground">
        No phase transitions in the next {LOOKAHEAD_HORIZON_DAYS} days.
      </p>
    );
  }
  return (
    <ul className="space-y-3">
      {events.map((e, i) => (
        <li key={`${e.zoneLabel}-${e.phase}-${e.kind}-${i}`} className="flex gap-2 text-xs">
          <span
            className="w-1 shrink-0 rounded-full"
            style={{ backgroundColor: PHASE_COLORS[e.phase] || '#71717a', minHeight: '100%' }}
          />
          <div>
            <span className="font-medium text-foreground">{e.zoneLabel}:</span>{' '}
            <span className="text-muted-foreground">
              {PHASE_LABELS[e.phase] || e.phase} {e.kind} in{' '}
              <span className="font-mono tabular-nums">{e.daysAway}</span>{' '}
              {e.daysAway === 1 ? 'day' : 'days'}.
            </span>
          </div>
        </li>
      ))}
    </ul>
  );
}
