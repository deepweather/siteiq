export const TRADE_COLORS: Record<string, string> = {
  structural: '#ef4444',
  mep: '#a78bfa',
  finishing: '#4ade80',
  general: '#a1a1aa',
};

export const PHASE_LABELS: Record<string, string> = {
  excavation: 'Excavation',
  shoring: 'Shoring',
  piling: 'Piling',
  drainage: 'Drainage',
  foundation: 'Foundation',
  structural: 'Structural',
  mep_roughin: 'MEP Rough-in',
  closein: 'Close-in',
  finishes: 'Finishes',
  paving: 'Paving',
  complete: 'Complete',
};

export const PHASE_COLORS: Record<string, string> = {
  excavation: '#eab308',
  // Tiefbau-specific phases live in the warm-earth → cool-water family
  // so the Gantt visually separates the underground prep work from
  // the Hochbau column above it.
  shoring: '#a16207',
  piling: '#854d0e',
  drainage: '#06b6d4',
  foundation: '#f97316',
  structural: '#ef4444',
  mep_roughin: '#a78bfa',
  closein: '#60a5fa',
  finishes: '#4ade80',
  paving: '#475569',
  complete: '#71717a',
};
