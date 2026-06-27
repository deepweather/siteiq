import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, fireEvent, act } from '@testing-library/react';
import RecordAsk from './RecordAsk';

const okJson = (body: unknown) =>
  new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  });

describe('RecordAsk', () => {
  beforeEach(async () => {
    vi.restoreAllMocks();
    const { clearCsrfCache } = await import('../../services/api');
    clearCsrfCache();
  });

  it('asks a question and renders the answer + evidence count', async () => {
    vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
      const url = typeof input === 'string' ? input : (input as Request).url;
      if (url.endsWith('/auth/csrf')) return okJson({ csrf_token: 't' });
      return okJson({
        intent: 'equipment_idle',
        answer: 'Equipment sat idle for 120 hours, costing €18,000.',
        data: { idle_hours: 120 },
        supporting_event_ids: ['a', 'b', 'c'],
      });
    });

    render(<RecordAsk />);
    fireEvent.change(screen.getByPlaceholderText(/Ask about idle equipment/i), {
      target: { value: 'idle equipment cost?' },
    });
    await act(async () => {
      fireEvent.click(screen.getByRole('button', { name: /^Ask$/i }));
    });

    expect(await screen.findByTestId('ask-answer')).toBeInTheDocument();
    expect(screen.getByText(/Equipment sat idle for 120 hours/)).toBeInTheDocument();
    expect(screen.getByText(/Backed by 3 events/)).toBeInTheDocument();
  });
});
