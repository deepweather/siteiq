import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import RecordDirectory from './RecordDirectory';
import { EntityNavContext } from './entityNav';

const okJson = (body: unknown) =>
  new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  });

const subjects = {
  subjects: [
    {
      subject_type: 'worker',
      subject_id: 'worker-001',
      descriptor: 'carpenter',
      last_state: null,
      event_count: 5,
      last_seen: '2026-02-10T17:00:00+00:00',
      pending: 0,
    },
    {
      subject_type: 'equipment',
      subject_id: 'crane-1',
      descriptor: 'tower_crane',
      last_state: 'idle',
      event_count: 12,
      last_seen: '2026-02-10T17:00:00+00:00',
      pending: 0,
    },
  ],
  counts: { worker: 1, equipment: 1 },
  project_id: 'westhafen',
};

function renderWithNav(open = vi.fn()) {
  return {
    open,
    ...render(
      <EntityNavContext.Provider value={open}>
        <RecordDirectory refreshKey={0} />
      </EntityNavContext.Provider>,
    ),
  };
}

describe('RecordDirectory', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(globalThis, 'fetch').mockResolvedValue(okJson(subjects));
  });

  it('lists subjects with category chips and descriptors', async () => {
    renderWithNav();
    expect(await screen.findByText('worker-001')).toBeInTheDocument();
    expect(screen.getByText('crane-1')).toBeInTheDocument();
    expect(screen.getByText('Equipment')).toBeInTheDocument();
  });

  it('filters by search text', async () => {
    renderWithNav();
    await screen.findByText('worker-001');
    fireEvent.change(screen.getByPlaceholderText(/Search workers/i), {
      target: { value: 'crane' },
    });
    expect(screen.getByText('crane-1')).toBeInTheDocument();
    expect(screen.queryByText('worker-001')).toBeNull();
  });

  it('opens the entity drawer (via nav context) when a card is clicked', async () => {
    const open = vi.fn();
    renderWithNav(open);
    const card = await screen.findByText('crane-1');
    await act(async () => {
      fireEvent.click(card);
    });
    expect(open).toHaveBeenCalledWith('equipment', 'crane-1');
  });
});
