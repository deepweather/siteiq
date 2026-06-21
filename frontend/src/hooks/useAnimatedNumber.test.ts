/**
 * useAnimatedNumber — verify it tweens between values and lands exactly
 * on the target.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useAnimatedNumber } from './useAnimatedNumber';

describe('useAnimatedNumber', () => {
  let rafCallbacks: Array<(t: number) => void> = [];
  let now = 0;

  beforeEach(() => {
    rafCallbacks = [];
    now = 0;
    vi.spyOn(performance, 'now').mockImplementation(() => now);
    vi.spyOn(window, 'requestAnimationFrame').mockImplementation((cb) => {
      rafCallbacks.push(cb);
      return rafCallbacks.length;
    });
    vi.spyOn(window, 'cancelAnimationFrame').mockImplementation(() => {});
  });
  afterEach(() => {
    vi.restoreAllMocks();
  });

  function flushFrame(deltaMs: number) {
    now += deltaMs;
    const cbs = rafCallbacks;
    rafCallbacks = [];
    act(() => {
      for (const cb of cbs) cb(now);
    });
  }

  it('returns the initial value before any animation', () => {
    const { result } = renderHook(() => useAnimatedNumber(100, 500));
    expect(result.current).toBe(100);
  });

  it('animates toward a new target and lands on it', () => {
    const { result, rerender } = renderHook(({ v }) => useAnimatedNumber(v, 500), {
      initialProps: { v: 0 },
    });
    expect(result.current).toBe(0);
    rerender({ v: 100 });
    // Halfway through, value should be partway (easeOut → past midpoint)
    flushFrame(250);
    expect(result.current).toBeGreaterThan(50);
    expect(result.current).toBeLessThan(100);
    // After the full duration it lands exactly on target
    flushFrame(300);
    expect(result.current).toBe(100);
  });

  it('handles successive changes mid-animation', () => {
    const { result, rerender } = renderHook(({ v }) => useAnimatedNumber(v, 500), {
      initialProps: { v: 0 },
    });
    rerender({ v: 100 });
    flushFrame(100);
    const intermediate = result.current;
    expect(intermediate).toBeGreaterThan(0);
    expect(intermediate).toBeLessThan(100);
    // New target while still animating — should still land on the latest
    rerender({ v: 50 });
    flushFrame(600);
    expect(result.current).toBe(50);
  });

  it('no-op when value equals current target', () => {
    const { result, rerender } = renderHook(({ v }) => useAnimatedNumber(v, 500), {
      initialProps: { v: 42 },
    });
    rerender({ v: 42 });
    // No frame requested
    expect(rafCallbacks.length).toBe(0);
    expect(result.current).toBe(42);
  });
});
