/**
 * Offline outbox for worker entries.
 *
 * Construction sites have dead zones, so submitting an entry must never
 * block on the network. Every entry is written to an IndexedDB store first;
 * we then try to flush it. The backend dedupes on `client_event_id`, so
 * replaying the queue on reconnect is safe (exactly-once from the user's
 * point of view).
 *
 * Flush rules:
 *  - success            -> remove from outbox
 *  - 4xx (bad entry)    -> remove + surface (it will never succeed)
 *  - network / 5xx      -> keep, retry on next reconnect
 */
import { openDB, type IDBPDatabase } from 'idb';
import { ApiError } from '../services/api';
import { workerApi, type EntryRequest } from './workerApi';

export interface OutboxItem extends EntryRequest {
  client_event_id: string;
  created_at: number;
}

const DB_NAME = 'siteiq-worker';
const STORE = 'outbox';

let _dbp: Promise<IDBPDatabase> | null = null;
function db(): Promise<IDBPDatabase> {
  if (!_dbp) {
    _dbp = openDB(DB_NAME, 1, {
      upgrade(database) {
        if (!database.objectStoreNames.contains(STORE)) {
          database.createObjectStore(STORE, { keyPath: 'client_event_id' });
        }
      },
    });
  }
  return _dbp;
}

function toRequest(item: OutboxItem): EntryRequest {
  return {
    kind: item.kind,
    client_event_id: item.client_event_id,
    subject_id: item.subject_id ?? null,
    payload: item.payload,
    occurred_at: item.occurred_at,
  };
}

type Listener = () => void;

class OutboxManager {
  private listeners = new Set<Listener>();
  pending = 0;
  flushing = false;
  // Immutable snapshot for React's useSyncExternalStore (new identity on change).
  snapshot: { pending: number; flushing: boolean } = { pending: 0, flushing: false };

  constructor() {
    if (typeof window !== 'undefined') {
      window.addEventListener('online', () => void this.flush());
      // Prime the count once IndexedDB is reachable.
      void this.refreshCount();
    }
  }

  subscribe(fn: Listener): () => void {
    this.listeners.add(fn);
    return () => {
      this.listeners.delete(fn);
    };
  }

  private emit() {
    this.snapshot = { pending: this.pending, flushing: this.flushing };
    for (const fn of this.listeners) fn();
  }

  getSnapshot = () => this.snapshot;
  subscribeBound = (fn: Listener) => this.subscribe(fn);

  async list(): Promise<OutboxItem[]> {
    const all = (await (await db()).getAll(STORE)) as OutboxItem[];
    return all.sort((a, b) => a.created_at - b.created_at);
  }

  private async refreshCount() {
    this.pending = await (await db()).count(STORE);
    this.emit();
  }

  private async remove(cid: string) {
    await (await db()).delete(STORE, cid);
  }

  /** Persist + attempt immediate send. Returns 'sent' if it went through
   *  right now, 'queued' if it was stored for later. Throws on a 4xx
   *  (the entry is malformed and will never succeed). */
  async submitOrQueue(item: OutboxItem): Promise<'sent' | 'queued'> {
    await (await db()).put(STORE, item);
    await this.refreshCount();

    if (typeof navigator !== 'undefined' && !navigator.onLine) {
      return 'queued';
    }
    try {
      await workerApi.submitEntry(toRequest(item));
      await this.remove(item.client_event_id);
      await this.refreshCount();
      return 'sent';
    } catch (e) {
      if (e instanceof ApiError && e.status >= 400 && e.status < 500) {
        await this.remove(item.client_event_id);
        await this.refreshCount();
        throw e;
      }
      // Network or server hiccup — leave it queued for the next flush.
      return 'queued';
    }
  }

  /** Drain the outbox. Stops at the first item that can't be delivered
   *  (network down), so order is preserved and we don't hammer a dead link. */
  async flush(): Promise<{ sent: number; remaining: number }> {
    if (this.flushing) return { sent: 0, remaining: this.pending };
    this.flushing = true;
    this.emit();
    let sent = 0;
    try {
      const items = await this.list();
      for (const item of items) {
        try {
          await workerApi.submitEntry(toRequest(item));
          await this.remove(item.client_event_id);
          sent += 1;
        } catch (e) {
          if (e instanceof ApiError && e.status >= 400 && e.status < 500) {
            // Permanently bad — drop it so it can't wedge the queue.
            await this.remove(item.client_event_id);
            continue;
          }
          break; // network/5xx — try again next reconnect
        }
      }
    } finally {
      this.flushing = false;
      await this.refreshCount();
    }
    return { sent, remaining: this.pending };
  }
}

export const outbox = new OutboxManager();

export function newClientEventId(): string {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) {
    return crypto.randomUUID();
  }
  return `cid-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}
