import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import RecordCosts from './RecordCosts';

const okJson = (body: unknown) =>
  new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  });

const breakdown = {
  since: null,
  until: null,
  labor_cost: 5000,
  labor_waste_cost: 1200,
  equipment_idle_cost: 3000,
  material_cost: 2000,
  total_cost: 10000,
  by_category: [
    { key: 'labor', label: 'Labour', amount: 5000 },
    { key: 'equipment_idle', label: 'Equipment idle', amount: 3000 },
    { key: 'material', label: 'Materials', amount: 2000 },
  ],
  by_day: [{ key: '2026-01-09', label: '2026-01-09', amount: 4000 }],
  by_zone: [{ key: 'zone-a', label: 'zone-a', amount: 7000 }],
  lines: [
    {
      category: 'labor',
      label: 'carpenter — 8h',
      amount: 440,
      occurred_on: '2026-01-09',
      zone_id: 'zone-a',
      subject_type: 'worker',
      subject_id: 'worker-001',
      supporting_event_ids: ['e1'],
    },
  ],
};

describe('RecordCosts', () => {
  beforeEach(() => vi.restoreAllMocks());

  it('renders totals and the recoverable-waste figure', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(okJson(breakdown));
    render(<RecordCosts refreshKey={0} />);
    expect(await screen.findByText('Total recorded')).toBeInTheDocument();
    // €10,000 total rendered somewhere.
    expect(screen.getAllByText(/€10,000/).length).toBeGreaterThan(0);
    expect(screen.getByText(/non-productive labour/i)).toBeInTheDocument();
  });

  it('shows an empty state when there are no costs', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      okJson({ ...breakdown, total_cost: 0, lines: [] }),
    );
    render(<RecordCosts refreshKey={0} />);
    expect(await screen.findByText(/No costs recorded yet/i)).toBeInTheDocument();
  });
});
