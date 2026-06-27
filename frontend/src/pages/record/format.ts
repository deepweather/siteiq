/** Shared display helpers for the Record UI. */

export function eur(amount: number): string {
  return new Intl.NumberFormat('en-IE', {
    style: 'currency',
    currency: 'EUR',
    maximumFractionDigits: 0,
  }).format(amount || 0);
}

export function eurExact(amount: number): string {
  return new Intl.NumberFormat('en-IE', {
    style: 'currency',
    currency: 'EUR',
    maximumFractionDigits: 2,
  }).format(amount || 0);
}

const KIND_LABELS: Record<string, string> = {
  'worker.timesheet': 'Timesheet',
  'worker.clocked_in': 'Clock in',
  'worker.clocked_out': 'Clock out',
  'equipment.state_changed': 'Equipment state',
  'equipment.utilization': 'Equipment utilization',
  'equipment.released': 'Equipment released',
  'material.delivered': 'Delivery',
  'material.staged': 'Material staged',
  'material.consumed': 'Material used',
  'inspection.passed': 'Inspection passed',
  'inspection.failed': 'Inspection failed',
  'incident.flagged': 'Incident',
  'optimization.applied': 'Optimisation applied',
  note: 'Note',
};

export function kindLabel(kind: string): string {
  return KIND_LABELS[kind] ?? kind;
}

export function kindIcon(kind: string): string {
  if (kind.startsWith('worker')) return '👷';
  if (kind.startsWith('equipment')) return '🏗️';
  if (kind.startsWith('material')) return '📦';
  if (kind.startsWith('inspection')) return '✅';
  if (kind.startsWith('incident')) return '⚠️';
  if (kind.startsWith('optimization')) return '💡';
  return '📝';
}

/** Tailwind classes for a source provenance badge. */
export function sourceClasses(source: string): string {
  switch (source) {
    case 'human':
      return 'bg-primary/10 text-primary';
    case 'camera':
      return 'bg-sky-100 text-sky-700';
    case 'simulation':
    case 'generator':
      return 'bg-secondary text-muted-foreground';
    default:
      return 'bg-secondary text-muted-foreground';
  }
}

export function statusClasses(status: string): string {
  switch (status) {
    case 'confirmed':
      return 'bg-emerald-100 text-emerald-700';
    case 'proposed':
      return 'bg-amber-100 text-amber-700';
    case 'rejected':
      return 'bg-red-100 text-red-700';
    case 'superseded':
      return 'bg-secondary text-muted-foreground line-through';
    default:
      return 'bg-secondary text-muted-foreground';
  }
}

export function fmtTime(iso: string): string {
  try {
    return new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  } catch {
    return iso;
  }
}

export function fmtDate(iso: string): string {
  try {
    return new Date(iso).toLocaleDateString([], {
      weekday: 'short',
      month: 'short',
      day: 'numeric',
    });
  } catch {
    return iso;
  }
}

/** A short human summary of an event payload for list rows. */
export function summarizeEvent(kind: string, payload: Record<string, unknown>): string {
  // Coerce an unknown payload value to a display string ('' when missing).
  const g = (key: string): string => {
    const v = payload[key];
    return v === undefined || v === null ? '' : String(v);
  };
  switch (kind) {
    case 'worker.timesheet':
      return `${g('trade') || 'worker'} · ${g('hours_total') || '0'}h (${g('hours_walking') || '0'}h walking)`;
    case 'equipment.utilization':
      return `${g('subtype') || 'equipment'} · ${g('hours_idle') || '0'}h idle / ${g('hours_active') || '0'}h active`;
    case 'equipment.state_changed':
      return `${g('subtype') || 'equipment'} → ${g('state')}`;
    case 'material.delivered': {
      const zone = g('zone_id');
      return `${g('quantity')}${g('unit')} ${g('subtype') || 'material'}${zone ? ` → ${zone}` : ''}`;
    }
    case 'incident.flagged':
      return `${g('severity')} ${g('note') || 'incident'}`.trim();
    case 'inspection.passed':
    case 'inspection.failed':
      return `${g('zone_id')} ${g('result')}`.trim();
    case 'optimization.applied':
      return g('title') || g('rec_type') || 'optimisation';
    case 'note':
      return g('note');
    default:
      return Object.keys(payload).length ? JSON.stringify(payload) : '';
  }
}
