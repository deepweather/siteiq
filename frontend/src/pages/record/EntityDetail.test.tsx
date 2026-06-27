import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import EntityDetail from './EntityDetail';
import { EntityNavContext } from './entityNav';

const okJson = (body: unknown) =>
  new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  });

const craneEntity = {
  subject_type: 'equipment',
  subject_id: 'crane-1',
  event_count: 12,
  first_seen: '2026-02-01T08:00:00+00:00',
  last_seen: '2026-02-10T17:00:00+00:00',
  kinds: { 'equipment.utilization': 6 },
  state: { subtype: 'tower_crane', hours_idle: 3 },
  metrics: { idle_hours: 30, active_hours: 40, utilization: 0.57 },
  events: [
    {
      id: 'e1', seq: 1, occurred_at: '2026-02-10T09:00:00+00:00',
      recorded_at: '2026-02-10T09:00:00+00:00', subject_type: 'worker',
      subject_id: 'worker-007', kind: 'worker.timesheet',
      payload: { trade: 'carpenter', hours_total: 8 },
      source: 'generator', confidence: 1, evidence_ref: null,
      status: 'confirmed', supersedes_event_id: null, actor_user_id: null,
    },
  ],
};

describe('EntityDetail', () => {
  beforeEach(() => vi.restoreAllMocks());

  it('renders metrics, current state and history', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(okJson(craneEntity));
    render(<EntityDetail subjectType="equipment" subjectId="crane-1" />);
    expect(await screen.findByText('Utilization')).toBeInTheDocument();
    expect(screen.getByText('57%')).toBeInTheDocument();
    expect(screen.getByText('Current state')).toBeInTheDocument();
    expect(screen.getByText(/History/)).toBeInTheDocument();
  });

  it('history rows link to their subject via the nav context', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(okJson(craneEntity));
    const open = vi.fn();
    render(
      <EntityNavContext.Provider value={open}>
        <EntityDetail subjectType="equipment" subjectId="crane-1" />
      </EntityNavContext.Provider>,
    );
    const link = await screen.findByText('worker:worker-007');
    await act(async () => {
      fireEvent.click(link);
    });
    expect(open).toHaveBeenCalledWith('worker', 'worker-007');
  });

  it('shows a friendly message when the entity has no record', async () => {
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ error: { code: 'entity_not_found', message: 'x' } }), {
        status: 404,
        headers: { 'Content-Type': 'application/json' },
      }),
    );
    render(<EntityDetail subjectType="zone" subjectId="zone-x" />);
    expect(await screen.findByText(/No record for zone:zone-x/i)).toBeInTheDocument();
  });
});
