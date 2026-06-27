import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import RecordTimeline from './RecordTimeline';

const okJson = (body: unknown) =>
  new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  });

const day = {
  date: '2026-01-10',
  deliveries: 1,
  timesheets: 2,
  incidents: 0,
  inspections: 0,
  equipment_summaries: 1,
  workers_active: 2,
  event_count: 3,
};

const ev = {
  id: 'e1',
  seq: 1,
  occurred_at: '2026-01-10T09:30:00+00:00',
  recorded_at: '2026-01-10T09:30:00+00:00',
  subject_type: 'material',
  subject_id: 'm1',
  kind: 'material.delivered',
  payload: { subtype: 'rebar', quantity: 2, unit: 't', zone_id: 'zone-a' },
  source: 'generator',
  confidence: 1,
  evidence_ref: null,
  status: 'confirmed',
  supersedes_event_id: null,
  actor_user_id: null,
};

describe('RecordTimeline', () => {
  beforeEach(() => vi.restoreAllMocks());

  it('renders the day list and the selected day events grouped by hour', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      const url = typeof input === 'string' ? input : (input as Request).url;
      if (url.includes('/api/record/days')) return okJson({ days: [day], project_id: 'p' });
      if (url.includes('/api/record/timeline')) return okJson({ date: '2026-01-10', events: [ev] });
      return okJson(null);
    });

    render(<RecordTimeline refreshKey={0} />);
    // The event renders once loaded.
    expect(await screen.findByText('Delivery')).toBeInTheDocument();
    // Day selector present.
    expect(screen.getByText(/2 crew/)).toBeInTheDocument();
  });

  it('shows an empty state when no history', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      const url = typeof input === 'string' ? input : (input as Request).url;
      if (url.includes('/api/record/days')) return okJson({ days: [], project_id: 'p' });
      if (url.includes('/api/record/timeline')) return okJson({ date: null, events: [] });
      return okJson(null);
    });
    render(<RecordTimeline refreshKey={0} />);
    expect(await screen.findByText(/No history yet|Nothing recorded/i)).toBeInTheDocument();
  });
});
