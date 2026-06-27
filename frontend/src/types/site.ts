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

export interface Road {
  /** Author-stable id; not used by the renderer beyond debug labels. */
  id: string;
  /** Polyline points in site metres. The renderer stamps a strip of
   *  `width_m` along every segment + a half-width disk at every node. */
  points: [number, number][];
  /** Width of the stamped strip in metres. */
  width_m: number;
  /** Which level the road lives on. Defaults to "L0" for legacy
   *  single-floor projects. */
  level_id?: string;
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
  /** Authored walkable corridors (polylines). When empty the renderer
   *  falls back to a default south + west perimeter strip so legacy
   *  documents still draw something sensible. */
  roads?: Road[];
}
