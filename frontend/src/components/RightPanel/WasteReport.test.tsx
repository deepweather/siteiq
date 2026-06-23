/**
 * Sweeps for the "raw zone ID leaks to users" bug — the bare letter
 * A/B/C/D the user pointed out. The fix injects real zone labels.
 */
import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { WasteReport } from './WasteReport';
import type { WasteSummary } from '../../types/analytics';
import type { Zone } from '../../types/site';

const zones: Zone[] = [
  { id: 'zone-a', label: 'Block A', x: 0, y: 0, width: 10, height: 10, phase: 'structural', phase_progress: 0.5 },
  { id: 'zone-b', label: 'Turm Ost', x: 10, y: 0, width: 10, height: 10, phase: 'mep_roughin', phase_progress: 0.5 },
];

const waste: WasteSummary = {
  toilet_walk_daily: 800,
  toilet_walk_monthly: 17600,
  material_handling_daily: 400,
  material_handling_monthly: 8800,
  equipment_idle_daily: 1800,
  equipment_idle_monthly: 39600,
  total_daily: 3000,
  total_monthly: 66000,
  zone_metrics: [
    { zone_id: 'zone-a', num_workers: 12, avg_toilet_round_trip_min: 8, avg_toilet_trips_per_day: 4,
      daily_toilet_walk_minutes: 120, daily_toilet_walk_cost: 500, avg_material_round_trip_min: 6,
      daily_material_walk_cost: 250, productivity_rate: 0.7 },
    { zone_id: 'zone-b', num_workers: 8, avg_toilet_round_trip_min: 6, avg_toilet_trips_per_day: 4,
      daily_toilet_walk_minutes: 60, daily_toilet_walk_cost: 300, avg_material_round_trip_min: 4,
      daily_material_walk_cost: 150, productivity_rate: 0.8 },
  ],
  equipment_metrics: [
    { asset_id: 'crane-1', subtype: 'tower_crane', utilization_rate: 0.32,
      hours_active: 3, hours_idle: 6, daily_idle_cost: 1200 },
    { asset_id: 'crane-2', subtype: 'tower_crane', utilization_rate: 0.78,
      hours_active: 8, hours_idle: 2, daily_idle_cost: 360 },
  ],
};

describe('WasteReport zone-label fix (UX follow-up)', () => {
  it('renders the "Toilet & break walks" row with friendly label', () => {
    render(
      <WasteReport
        waste={waste}
        baseline={null}
        savings={null}
        pendingSavingsMonthly={0}
        zones={zones}
        onSwitchToOptimize={() => {}}
      />,
    );
    expect(screen.getByText(/Toilet & break walks/i)).toBeInTheDocument();
  });

  it('shows REAL zone labels in the facility-access breakdown (NOT raw letters)', () => {
    render(
      <WasteReport
        waste={waste}
        baseline={null}
        savings={null}
        pendingSavingsMonthly={0}
        zones={zones}
        onSwitchToOptimize={() => {}}
      />,
    );
    fireEvent.click(screen.getByText(/Toilet & break walks/i));

    // Real labels must be rendered
    expect(screen.getByText('Block A')).toBeInTheDocument();
    expect(screen.getByText('Turm Ost')).toBeInTheDocument();

    // And the worker count is shown alongside
    expect(screen.getByText(/12 workers/)).toBeInTheDocument();
    expect(screen.getByText(/8 workers/)).toBeInTheDocument();
  });

  it('shows REAL zone labels in the material-staging breakdown', () => {
    render(
      <WasteReport
        waste={waste}
        baseline={null}
        savings={null}
        pendingSavingsMonthly={0}
        zones={zones}
        onSwitchToOptimize={() => {}}
      />,
    );
    fireEvent.click(screen.getByText(/Material in wrong place/i));
    expect(screen.getByText('Block A')).toBeInTheDocument();
    expect(screen.getByText('Turm Ost')).toBeInTheDocument();
  });

  it('disambiguates equipment by asset number (Crane #1 vs #2)', () => {
    render(
      <WasteReport
        waste={waste}
        baseline={null}
        savings={null}
        pendingSavingsMonthly={0}
        zones={zones}
        onSwitchToOptimize={() => {}}
      />,
    );
    fireEvent.click(screen.getByText(/Equipment idle time/i));
    expect(screen.getByText('Tower Crane #1')).toBeInTheDocument();
    expect(screen.getByText('Tower Crane #2')).toBeInTheDocument();
  });

  it('sorts equipment breakdown by cost descending (biggest offender first)', () => {
    const { container } = render(
      <WasteReport
        waste={waste}
        baseline={null}
        savings={null}
        pendingSavingsMonthly={0}
        zones={zones}
        onSwitchToOptimize={() => {}}
      />,
    );
    fireEvent.click(screen.getByText(/Equipment idle time/i));
    const rows = container.querySelectorAll('.font-medium.truncate');
    const labels = Array.from(rows).map(r => r.textContent);
    // Crane #1 (€1200) should appear before Crane #2 (€360)
    const i1 = labels.indexOf('Tower Crane #1');
    const i2 = labels.indexOf('Tower Crane #2');
    expect(i1).toBeGreaterThanOrEqual(0);
    expect(i2).toBeGreaterThan(i1);
  });

  it('shows empty-state message when there is no waste in a category', () => {
    const emptyWaste: WasteSummary = {
      ...waste,
      zone_metrics: [],
    };
    render(
      <WasteReport
        waste={emptyWaste}
        baseline={null}
        savings={null}
        pendingSavingsMonthly={0}
        zones={zones}
        onSwitchToOptimize={() => {}}
      />,
    );
    fireEvent.click(screen.getByText(/Toilet & break walks/i));
    expect(screen.getByText(/No facility-walk waste/i)).toBeInTheDocument();
  });

  it('falls back gracefully when zones list is empty (unknown zone IDs)', () => {
    render(
      <WasteReport
        waste={waste}
        baseline={null}
        savings={null}
        pendingSavingsMonthly={0}
        zones={[]}
        onSwitchToOptimize={() => {}}
      />,
    );
    fireEvent.click(screen.getByText(/Toilet & break walks/i));
    // Fallback: "zone-a" → "Zone A" (still readable, not raw)
    expect(screen.getByText('Zone A')).toBeInTheDocument();
    expect(screen.getByText('Zone B')).toBeInTheDocument();
  });
});


describe('WasteReport — Phase 5 shoring compliance row', () => {
  it('renders an "Unshored excavation" warning when any zone has compliance < 1.0', () => {
    const wasteWithShoring: WasteSummary = {
      ...waste,
      shoring_compliance: [
        { zone_id: 'zone-b', zone_label: 'Abschnitt B', compliance: 1.0, nearest_distance_m: 7.1 },
        { zone_id: 'zone-d', zone_label: 'Pfeiler 4-6', compliance: 0.0, nearest_distance_m: 42.3 },
        { zone_id: 'zone-e', zone_label: 'Widerlager Ost', compliance: 0.0, nearest_distance_m: null },
      ],
    };
    render(
      <WasteReport
        waste={wasteWithShoring}
        baseline={null}
        savings={null}
        pendingSavingsMonthly={0}
        zones={zones}
        onSwitchToOptimize={() => {}}
      />,
    );
    expect(screen.getByText(/Unshored excavation/i)).toBeInTheDocument();
    // Header summary: 2 of 3 zones flagged.
    expect(screen.getByText(/2 of 3 excavation zones/i)).toBeInTheDocument();
  });

  it('expanding the row reveals the offending zone labels + distances', () => {
    const wasteWithShoring: WasteSummary = {
      ...waste,
      shoring_compliance: [
        { zone_id: 'zone-d', zone_label: 'Pfeiler 4-6', compliance: 0.0, nearest_distance_m: 42.3 },
        { zone_id: 'zone-e', zone_label: 'Widerlager Ost', compliance: 0.0, nearest_distance_m: null },
      ],
    };
    render(
      <WasteReport
        waste={wasteWithShoring}
        baseline={null}
        savings={null}
        pendingSavingsMonthly={0}
        zones={zones}
        onSwitchToOptimize={() => {}}
      />,
    );
    fireEvent.click(screen.getByText(/Unshored excavation/i));
    expect(screen.getByText('Pfeiler 4-6')).toBeInTheDocument();
    expect(screen.getByText(/nearest pile 42 m/i)).toBeInTheDocument();
    expect(screen.getByText('Widerlager Ost')).toBeInTheDocument();
    expect(screen.getByText(/no sheet pile on this level/i)).toBeInTheDocument();
  });

  it('does NOT render the shoring row when every zone is compliant', () => {
    const wasteAllCompliant: WasteSummary = {
      ...waste,
      shoring_compliance: [
        { zone_id: 'zone-b', zone_label: 'Abschnitt B', compliance: 1.0, nearest_distance_m: 7.1 },
        { zone_id: 'zone-c', zone_label: 'Abschnitt C', compliance: 1.0, nearest_distance_m: 5.0 },
      ],
    };
    render(
      <WasteReport
        waste={wasteAllCompliant}
        baseline={null}
        savings={null}
        pendingSavingsMonthly={0}
        zones={zones}
        onSwitchToOptimize={() => {}}
      />,
    );
    expect(screen.queryByText(/Unshored excavation/i)).toBeNull();
  });

  it('does NOT render the shoring row on Hochbau projects (empty list)', () => {
    render(
      <WasteReport
        waste={waste}
        baseline={null}
        savings={null}
        pendingSavingsMonthly={0}
        zones={zones}
        onSwitchToOptimize={() => {}}
      />,
    );
    expect(screen.queryByText(/Unshored excavation/i)).toBeNull();
  });
});
