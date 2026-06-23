/**
 * useWebSocket — audit-fix tests that the new `cabsRef` channel
 * actually propagates the cabs array from the WS state_update payload.
 */
import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { act, renderHook } from '@testing-library/react';
import { useWebSocket, type CabSnapshot } from './useWebSocket';

// In-process MockWebSocket so the hook's `new WebSocket(...)` resolves
// against our handler instead of hitting a real socket.
class MockWebSocket {
  static last: MockWebSocket | null = null;
  url: string;
  readyState: number = 0;
  onopen: ((ev: Event) => void) | null = null;
  onmessage: ((ev: MessageEvent) => void) | null = null;
  onclose: ((ev: CloseEvent) => void) | null = null;
  onerror: ((ev: Event) => void) | null = null;

  static readonly CONNECTING = 0;
  static readonly OPEN = 1;
  static readonly CLOSING = 2;
  static readonly CLOSED = 3;

  constructor(url: string) {
    this.url = url;
    MockWebSocket.last = this;
    // Open in a microtask so the hook can attach handlers first.
    queueMicrotask(() => {
      this.readyState = 1;
      this.onopen?.(new Event('open'));
    });
  }
  send(): void { /* no-op */ }
  close(): void {
    this.readyState = 3;
    this.onclose?.(new CloseEvent('close'));
  }
  emit(payload: unknown): void {
    this.onmessage?.(new MessageEvent('message', { data: JSON.stringify(payload) }));
  }
}


describe('useWebSocket — cabs channel', () => {
  const RealWS = globalThis.WebSocket;
  beforeEach(() => {
    MockWebSocket.last = null;
    (globalThis as unknown as { WebSocket: typeof MockWebSocket }).WebSocket = MockWebSocket;
  });
  afterEach(() => {
    (globalThis as unknown as { WebSocket: typeof WebSocket }).WebSocket = RealWS;
  });

  it('exposes a stable cabsRef ref', () => {
    const { result } = renderHook(() => useWebSocket());
    expect(result.current.cabsRef).toBeDefined();
    expect(result.current.cabsRef.current).toEqual([]);
  });

  it('populates cabsRef from the state_update payload', async () => {
    const { result } = renderHook(() => useWebSocket());
    // Let MockWebSocket's microtask open the connection.
    await new Promise((r) => setTimeout(r, 5));
    const cabs: CabSnapshot[] = [
      {
        id: 'lift-1',
        current_level: 'L0',
        passengers: 2,
        capacity: 4,
        queue_by_level: { L1: 3 },
      },
    ];
    act(() => {
      MockWebSocket.last!.emit({
        type: 'state_update',
        sim_time: 100,
        sim_day: 1,
        assets: [],
        trails: {},
        cabs,
        analytics: null,
      });
    });
    expect(result.current.cabsRef.current).toEqual(cabs);
  });

  it('defaults cabs to [] when the WS payload omits the field', async () => {
    const { result } = renderHook(() => useWebSocket());
    await new Promise((r) => setTimeout(r, 5));
    act(() => {
      MockWebSocket.last!.emit({
        type: 'state_update',
        sim_time: 100,
        sim_day: 1,
        assets: [],
        trails: {},
        analytics: null,
        // intentionally no `cabs`
      });
    });
    expect(result.current.cabsRef.current).toEqual([]);
  });
});
