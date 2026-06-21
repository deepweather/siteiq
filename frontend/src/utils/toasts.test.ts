/**
 * Tests for the module-level toast queue.
 */
import { describe, it, expect, beforeEach, vi, afterEach } from 'vitest';
import { pushToast, dismissToast, subscribeToasts, _resetToasts } from './toasts';

describe('toast queue', () => {
  beforeEach(() => {
    vi.useFakeTimers();
    _resetToasts();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it('starts empty', () => {
    const seen: number[] = [];
    const unsub = subscribeToasts((list) => seen.push(list.length));
    expect(seen[0]).toBe(0);
    unsub();
  });

  it('pushToast notifies subscribers immediately', () => {
    let last: number = -1;
    const unsub = subscribeToasts((list) => { last = list.length; });
    pushToast({ tone: 'success', title: 'hello' });
    expect(last).toBe(1);
    unsub();
  });

  it('auto-dismisses after ttlMs', () => {
    let count = -1;
    const unsub = subscribeToasts((list) => { count = list.length; });
    pushToast({ tone: 'success', title: 'gone soon', ttlMs: 1000 });
    expect(count).toBe(1);
    vi.advanceTimersByTime(999);
    expect(count).toBe(1);
    vi.advanceTimersByTime(1);
    expect(count).toBe(0);
    unsub();
  });

  it('ttlMs=0 makes the toast sticky', () => {
    let count = -1;
    const unsub = subscribeToasts((list) => { count = list.length; });
    pushToast({ tone: 'info', title: 'sticky', ttlMs: 0 });
    vi.advanceTimersByTime(60_000);
    expect(count).toBe(1);
    unsub();
  });

  it('dismissToast removes by id', () => {
    let snapshot: ReadonlyArray<{ id: number }> = [];
    const unsub = subscribeToasts((list) => { snapshot = list; });
    const id = pushToast({ tone: 'success', title: 'a' });
    pushToast({ tone: 'success', title: 'b' });
    expect(snapshot.length).toBe(2);
    dismissToast(id);
    expect(snapshot.length).toBe(1);
    expect(snapshot[0].id).not.toBe(id);
    unsub();
  });

  it('multiple toasts queue up FIFO and dismiss independently', () => {
    let snapshot: ReadonlyArray<{ id: number; title: string }> = [];
    const unsub = subscribeToasts((list) => { snapshot = list; });
    pushToast({ tone: 'success', title: 'first', ttlMs: 1000 });
    pushToast({ tone: 'success', title: 'second', ttlMs: 3000 });
    pushToast({ tone: 'success', title: 'third', ttlMs: 5000 });
    expect(snapshot.map(t => t.title)).toEqual(['first', 'second', 'third']);
    vi.advanceTimersByTime(1500);
    expect(snapshot.map(t => t.title)).toEqual(['second', 'third']);
    vi.advanceTimersByTime(2000);
    expect(snapshot.map(t => t.title)).toEqual(['third']);
    unsub();
  });

  it('unsubscribe stops further notifications', () => {
    const seen: number[] = [];
    const unsub = subscribeToasts((list) => seen.push(list.length));
    pushToast({ tone: 'success', title: 'first' });
    unsub();
    pushToast({ tone: 'success', title: 'after-unsub' });
    expect(seen).toEqual([0, 1]); // initial empty + first push only
  });
});
