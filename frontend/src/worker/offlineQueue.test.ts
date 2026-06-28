import 'fake-indexeddb/auto';
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { openDB } from 'idb';
import { clearCsrfCache } from '../services/api';
import { outbox, newClientEventId, type OutboxItem } from './offlineQueue';

const okJson = (body: unknown) =>
  new Response(JSON.stringify(body), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  });

function mockEntry(handler?: () => Response) {
  return vi.spyOn(globalThis, 'fetch').mockImplementation(async (input) => {
    const url = typeof input === 'string' ? input : (input as Request).url;
    if (url.endsWith('/auth/csrf')) return okJson({ csrf_token: 'csrf-q' });
    if (url.endsWith('/api/worker/entry')) return (handler ?? (() => okJson({ id: 'e', status: 'proposed' })))();
    return okJson({});
  });
}

function setOnline(value: boolean) {
  Object.defineProperty(navigator, 'onLine', { value, configurable: true });
}

function item(over: Partial<OutboxItem> = {}): OutboxItem {
  return {
    kind: 'delivery',
    client_event_id: over.client_event_id ?? newClientEventId(),
    payload: { subtype: 'rebar', quantity: 1, unit: 't', zone_id: 'zone-a' },
    occurred_at: new Date().toISOString(),
    created_at: Date.now(),
    ...over,
  };
}

async function clearStore() {
  const d = await openDB('siteiq-worker', 1);
  await d.clear('outbox');
}

describe('offline outbox', () => {
  beforeEach(async () => {
    vi.restoreAllMocks();
    clearCsrfCache();
    setOnline(true);
    await clearStore();
    await outbox.flush(); // settle flushing flag + count
  });

  afterEach(() => setOnline(true));

  it('sends immediately when online and clears the queue', async () => {
    mockEntry();
    const res = await outbox.submitOrQueue(item({ client_event_id: 'cid-online-1' }));
    expect(res).toBe('sent');
    expect((await outbox.list()).length).toBe(0);
  });

  it('queues when offline and keeps the item', async () => {
    mockEntry();
    setOnline(false);
    const res = await outbox.submitOrQueue(item({ client_event_id: 'cid-offline-1' }));
    expect(res).toBe('queued');
    const list = await outbox.list();
    expect(list.map((i) => i.client_event_id)).toContain('cid-offline-1');
  });

  it('dedupes by client_event_id (same key overwrites)', async () => {
    mockEntry();
    setOnline(false);
    await outbox.submitOrQueue(item({ client_event_id: 'cid-dupe' }));
    await outbox.submitOrQueue(item({ client_event_id: 'cid-dupe' }));
    const dupes = (await outbox.list()).filter((i) => i.client_event_id === 'cid-dupe');
    expect(dupes.length).toBe(1);
  });

  it('flush drains queued items once back online', async () => {
    mockEntry();
    setOnline(false);
    await outbox.submitOrQueue(item({ client_event_id: 'cid-flush-1' }));
    await outbox.submitOrQueue(item({ client_event_id: 'cid-flush-2' }));
    expect((await outbox.list()).length).toBe(2);

    setOnline(true);
    const { sent } = await outbox.flush();
    expect(sent).toBe(2);
    expect((await outbox.list()).length).toBe(0);
  });

  it('flush keeps items when the network fails', async () => {
    mockEntry(() => {
      throw new TypeError('network down');
    });
    setOnline(false);
    await outbox.submitOrQueue(item({ client_event_id: 'cid-keep-1' }));
    setOnline(true);
    const { sent, remaining } = await outbox.flush();
    expect(sent).toBe(0);
    expect(remaining).toBeGreaterThanOrEqual(1);
  });
});
