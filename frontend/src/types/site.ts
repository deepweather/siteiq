export interface Zone {
  id: string;
  label: string;
  x: number;
  y: number;
  width: number;
  height: number;
  phase: string;
  phase_progress: number;
  /** Multi-level: which level this zone lives on. Defaults to "L0"
   *  (ground floor) for legacy single-floor projects. */
  level_id?: string;
}

export interface ScheduleEntry {
  zone_id: string;
  phase: string;
  start_day: number;
  end_day: number;
  trades_required: string[];
}

export interface Level {
  id: string;
  name: string;
  elevation_m: number;
  order: number;
  background_image_url?: string | null;
}

export interface ConnectionNode {
  level_id: string;
  x: number;
  y: number;
}

export interface SiteConnection {
  id: string;
  kind: "stair" | "elevator";
  nodes: ConnectionNode[];
}

export interface Site {
  id: string;
  name: string;
  width: number;
  height: number;
  zones: Zone[];
  current_day: number;
  schedule: ScheduleEntry[];
  /** Phase 2: levels are always present. Single-floor projects expose
   *  exactly one level (L0). */
  levels?: Level[];
  /** Phase 3: vertical-transport graph. Empty for single-floor projects. */
  connections?: SiteConnection[];
  discipline?: string;
}
