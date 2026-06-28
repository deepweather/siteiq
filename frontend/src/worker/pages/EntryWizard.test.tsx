import 'fake-indexeddb/auto';
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { openDB } from 'idb';
import { clearCsrfCache } from '../../services/api';
import { I18nProvider } from '../I18nProvider';
import EntryWizard from './EntryWizard';

const okJson = (body: unknown) =>
  new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  });

function mockFetch() {
  return vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
    const url = typeof input === 'string' ? input : (input as Request).url;
    if (url.endsWith('/auth/csrf')) return okJson({ csrf_token: 'csrf-e' });
    if (url.includes('/api/worker/zones')) {
      return okJson({ zones: [{ id: 'zone-a', label: 'Zone A' }], project_id: 'p' });
    }
    if (url.includes('/api/worker/assets')) {
      return okJson({
        assets: [
          { subject_type: 'zone', subject_id: 'zone-a', descriptor: 'Zone A', last_state: null, event_count: 1, last_seen: null, pending: 0, metrics: {}, state: {} },
        ],
        counts: { zone: 1 },
        project_id: 'p',
      });
    }
    if (url.endsWith('/api/worker/entry')) return okJson({ id: 'e1', status: 'proposed' });
    return okJson({});
  });
}

function setOnline(value: boolean) {
  Object.defineProperty(navigator, 'onLine', { value, configurable: true });
}

async function clearStore() {
  const d = await openDB('siteiq-worker', 1);
  await d.clear('outbox');
}

function renderWizard() {
  return render(
    <I18nProvider>
      <MemoryRouter initialEntries={['/new/delivery']}>
        <Routes>
          <Route path="/new/:kind" element={<EntryWizard />} />
          <Route path="/" element={<div>HOME</div>} />
        </Routes>
      </MemoryRouter>
    </I18nProvider>,
  );
}

async function walkDeliveryToReview() {
  fireEvent.click(await screen.findByRole('button', { name: 'Rebar' }));
  fireEvent.click(screen.getByRole('button', { name: 'Next' })); // -> quantity
  fireEvent.click(screen.getByRole('button', { name: 'Next' })); // -> where (qty defaults to 1)
  fireEvent.click(await screen.findByRole('button', { name: 'Zone A' }));
  fireEvent.click(screen.getByRole('button', { name: 'Next' })); // -> review
}

describe('EntryWizard', () => {
  beforeEach(async () => {
    vi.restoreAllMocks();
    clearCsrfCache();
    localStorage.setItem('siteiq.worker.lang', 'en');
    setOnline(true);
    mockFetch();
    await clearStore();
  });

  afterEach(() => setOnline(true));

  it('submits a delivery online and shows the Sent screen', async () => {
    renderWizard();
    await walkDeliveryToReview();
    fireEvent.click(screen.getByRole('button', { name: 'Send' }));
    expect(await screen.findByText('Sent')).toBeInTheDocument();
  });

  it('queues the delivery offline and shows the Saved screen', async () => {
    renderWizard();
    await walkDeliveryToReview();
    setOnline(false);
    fireEvent.click(screen.getByRole('button', { name: 'Send' }));
    expect(await screen.findByText('Saved')).toBeInTheDocument();
  });
});
