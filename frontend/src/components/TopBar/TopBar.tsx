import { useState, useEffect, useRef } from 'react';
import { formatSimTime } from '../../utils/formatting';
import { setSimSpeed, togglePause, fetchProjects, loadProject, type ProjectSummary } from '../../services/api';

interface TopBarProps {
  simTime: number;
  simDay: number;
  connected: boolean;
  siteName: string;
  onProjectChange: () => void;
  onShowPortfolio: () => void;
}

const SPEEDS = [1, 2, 5, 10];

export function TopBar({ simTime, simDay, connected, siteName, onProjectChange, onShowPortfolio }: TopBarProps) {
  const [activeSpeed, setActiveSpeed] = useState(1);
  const [paused, setPaused] = useState(false);
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [showPicker, setShowPicker] = useState(false);
  const [switching, setSwitching] = useState(false);
  const pickerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    fetchProjects().then(setProjects).catch(() => {});
  }, []);

  useEffect(() => {
    const handleClick = (e: MouseEvent) => {
      if (pickerRef.current && !pickerRef.current.contains(e.target as Node)) {
        setShowPicker(false);
      }
    };
    document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, []);

  const handleSpeed = async (speed: number) => {
    setActiveSpeed(speed);
    await setSimSpeed(speed);
  };

  const handlePause = async () => {
    setPaused(!paused);
    await togglePause();
  };

  const handleProjectSelect = async (id: string) => {
    setSwitching(true);
    setShowPicker(false);
    await loadProject(id);
    onProjectChange();
    setSwitching(false);
  };

  return (
    <div className="h-12 bg-card border-b border-border flex items-center px-4 shrink-0 shadow-sm">
      <div className="flex items-center gap-3 min-w-[200px]">
        <div className="flex items-center gap-2">
          <div className="w-7 h-7 bg-primary rounded-md flex items-center justify-center">
            <span className="text-primary-foreground text-xs font-bold">S</span>
          </div>
          <span className="font-semibold text-sm text-foreground">SiteIQ</span>
        </div>
        <button
          onClick={onShowPortfolio}
          className="text-[11px] text-muted-foreground hover:text-foreground px-2 py-1 rounded-md hover:bg-secondary border border-border transition-colors"
        >
          Portfolio
        </button>
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

      <div className="flex items-center gap-2 min-w-[280px] justify-end">
        <div className="flex items-center gap-1.5 px-2 py-1 rounded-md bg-secondary">
          <span className={`w-2 h-2 rounded-full ${connected ? 'bg-success' : 'bg-destructive'}`} />
          <span className="text-xs text-muted-foreground">{connected ? 'Live' : 'Offline'}</span>
        </div>

        <div className="relative" ref={pickerRef}>
          <button
            onClick={() => setShowPicker(!showPicker)}
            disabled={switching}
            className="text-sm text-foreground font-medium truncate max-w-[200px] hover:text-primary transition-colors flex items-center gap-1"
          >
            {switching ? 'Loading...' : siteName}
            <svg className="w-3 h-3 text-muted-foreground shrink-0" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M3 5l3 3 3-3" />
            </svg>
          </button>

          {showPicker && projects.length > 0 && (
            <div className="absolute right-0 top-full mt-1 w-80 border border-border rounded-lg shadow-xl z-50 overflow-hidden" style={{ backgroundColor: 'hsl(var(--card))', boxShadow: '0 10px 40px rgba(0,0,0,0.15)' }}>
              <div className="px-3 py-2 border-b border-border">
                <span className="text-xs text-muted-foreground font-medium">Switch Project</span>
              </div>
              {projects.map((p) => (
                <button
                  key={p.id}
                  onClick={() => handleProjectSelect(p.id)}
                  className="w-full px-3 py-2.5 text-left hover:bg-secondary transition-colors border-b border-border last:border-0"
                  style={{ backgroundColor: 'hsl(var(--card))' }}
                >
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-medium text-foreground">{p.name}</span>
                    <span className="text-[10px] text-muted-foreground bg-secondary px-1.5 py-0.5 rounded">{p.type}</span>
                  </div>
                  <div className="text-xs text-muted-foreground mt-0.5">{p.description}</div>
                </button>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
