export interface Zone {
  id: string;
  label: string;
  x: number;
  y: number;
  width: number;
  height: number;
  phase: string;
  phase_progress: number;
}

export interface ScheduleEntry {
  zone_id: string;
  phase: string;
  start_day: number;
  end_day: number;
  trades_required: string[];
}

export interface Site {
  id: string;
  name: string;
  width: number;
  height: number;
  zones: Zone[];
  current_day: number;
  schedule: ScheduleEntry[];
}
