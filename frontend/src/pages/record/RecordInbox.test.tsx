import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent, act, waitFor } from '@testing-library/react';
import RecordInbox from './RecordInbox';

const okJson = (body: unknown) =>
  new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  });

const proposed = {
  id: 'ev1',
  seq: 5,
  occurred_at: '2026-01-10T09:00:00+00:00',
  recorded_at: '2026-01-10T09:00:00+00:00',
  subject_type: 'material',
  subject_id: 'capture-rebar',
  kind: 'material.delivered',
  payload: { subtype: 'rebar', quantity: 3, unit: 't', zone_id: 'zone-a' },
  source: 'human',
  confidence: 0.65,
  evidence_ref: null,
  status: 'proposed',
  supersedes_event_id: null,
  actor_user_id: 'u1',
};

describe('RecordInbox', () => {
  beforeEach(async () => {
    vi.restoreAllMocks();
    const { clearCsrfCache } = await import('../../services/api');
    clearCsrfCache();
  });

  it('lists proposed events and confirms one', async () => {
    let confirmed = false;
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      const url = typeof input === 'string' ? input : (input as Request).url;
      if (url.endsWith('/auth/csrf')) return okJson({ csrf_token: 't' });
      if (url.endsWith('/api/record/inbox')) {
        return okJson({ events: confirmed ? [] : [proposed] });
      }
      if (url.endsWith('/api/record/events/ev1/confirm')) {
        confirmed = true;
        return okJson({ ...proposed, status: 'confirmed' });
      }
      return okJson(null);
    });

    const onChanged = vi.fn();
    render(<RecordInbox canWrite onChanged={onChanged} />);

    expect(await screen.findByText('Delivery')).toBeInTheDocument();
    const btn = screen.getByText('Confirm');
    await act(async () => {
      fireEvent.click(btn);
    });
    await waitFor(() => expect(onChanged).toHaveBeenCalled());
    expect(screen.queryByText('Delivery')).toBeNull();
  });

  it('shows inbox-zero state when empty', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      const url = typeof input === 'string' ? input : (input as Request).url;
      if (url.endsWith('/auth/csrf')) return okJson({ csrf_token: 't' });
      return okJson({ events: [] });
    });
    render(<RecordInbox canWrite />);
    expect(await screen.findByText(/Inbox zero/i)).toBeInTheDocument();
  });

  it('hides action buttons for read-only users', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      const url = typeof input === 'string' ? input : (input as Request).url;
      if (url.endsWith('/auth/csrf')) return okJson({ csrf_token: 't' });
      return okJson({ events: [proposed] });
    });
    render(<RecordInbox canWrite={false} />);
    expect(await screen.findByText('Delivery')).toBeInTheDocument();
    expect(screen.queryByText('Confirm')).toBeNull();
    expect(screen.getByText('read-only')).toBeInTheDocument();
  });
});
