import { useState } from 'react';
import { formatSimTime } from '../../utils/formatting';
import { setSimSpeed, togglePause } from '../../services/api';

interface TopBarProps {
  simTime: number;
  simDay: number;
  connected: boolean;
  siteName: string;
}

const SPEEDS = [1, 2, 5, 10];

export function TopBar({ simTime, simDay, connected, siteName }: TopBarProps) {
  const [activeSpeed, setActiveSpeed] = useState(1);
  const [paused, setPaused] = useState(false);

  const handleSpeed = async (speed: number) => {
    setActiveSpeed(speed);
    await setSimSpeed(speed);
  };

  const handlePause = async () => {
    setPaused(!paused);
    await togglePause();
  };

  return (
    <div className="h-12 bg-card border-b border-border flex items-center px-4 shrink-0 shadow-sm">
      <div className="flex items-center gap-2 min-w-[160px]">
        <div className="w-7 h-7 bg-primary rounded-md flex items-center justify-center">
          <span className="text-primary-foreground text-xs font-bold">S</span>
        </div>
        <span className="font-semibold text-sm text-foreground">SiteIQ</span>
      </div>

      <div className="flex-1 flex items-center justify-center gap-4">
        <span className="font-mono text-sm tabular-nums text-foreground">
          {formatSimTime(simTime)}
        </span>
        <span className="text-muted-foreground text-sm">Day {simDay}</span>

        <div className="flex items-center gap-1 ml-2">
          <button
            onClick={handlePause}
            className="w-7 h-7 flex items-center justify-center rounded-md text-xs border border-border hover:bg-secondary text-muted-foreground"
          >
            {paused ? '\u25B6' : '\u23F8'}
          </button>
          {SPEEDS.map((s) => (
            <button
              key={s}
              onClick={() => handleSpeed(s)}
              className={`px-2 h-7 rounded-md text-xs font-mono ${
                activeSpeed === s
                  ? 'bg-primary text-primary-foreground'
                  : 'border border-border text-muted-foreground hover:bg-secondary'
              }`}
            >
              {s}x
            </button>
          ))}
        </div>
      </div>

      <div className="flex items-center gap-2 min-w-[240px] justify-end">
        <div className="flex items-center gap-1.5 px-2 py-1 rounded-md bg-secondary">
          <span className={`w-2 h-2 rounded-full ${connected ? 'bg-success' : 'bg-destructive'}`} />
          <span className="text-xs text-muted-foreground">{connected ? 'Live' : 'Offline'}</span>
        </div>
        <span className="text-sm text-foreground font-medium truncate">{siteName}</span>
      </div>
    </div>
  );
}
