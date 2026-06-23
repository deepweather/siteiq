import type { Level } from '../../types/site';

interface LevelSwitcherProps {
  levels: Level[];
  activeLevel: string;
  onLevelChange: (levelId: string) => void;
}

/**
 * Vertical strip on the right of the site map. Top item = highest level
 * (Dach), bottom = deepest UG. Single-floor projects render nothing.
 */
export function LevelSwitcher({ levels, activeLevel, onLevelChange }: LevelSwitcherProps) {
  if (!levels || levels.length <= 1) return null;
  // Sort descending by `order` so Dach is at the top.
  const sorted = [...levels].sort((a, b) => b.order - a.order);
  return (
    // Top-LEFT, not top-right: renderer.ts paints its trade / status
    // legend in the top-right corner of the canvas, so a right-aligned
    // switcher visibly overlapped that legend. Left side is otherwise
    // empty until the user pans the map.
    <div className="absolute top-2 left-2 flex flex-col gap-0.5 bg-card/95 border border-border rounded-md p-1 shadow-sm backdrop-blur z-10">
      {sorted.map((lv) => {
        const isActive = lv.id === activeLevel;
        return (
          <button
            key={lv.id}
            type="button"
            onClick={() => onLevelChange(lv.id)}
            className={
              `px-2.5 py-1 text-xs font-medium tabular-nums rounded transition-colors text-left min-w-[80px] ` +
              (isActive
                ? 'bg-primary text-primary-foreground'
                : 'text-muted-foreground hover:bg-secondary')
            }
            title={`Elevation: ${lv.elevation_m}m`}
          >
            <span className="font-mono mr-1.5 opacity-70">{lv.order >= 0 ? '+' : ''}{lv.order}</span>
            {lv.name}
          </button>
        );
      })}
    </div>
  );
}
