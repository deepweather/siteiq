import { useEffect, useRef, useState } from 'react';

/**
 * Tween a numeric value over `durationMs` whenever the input changes.
 *
 * Cancels and restarts on every change so rapid updates don't queue up.
 * Returns the current animated value. Eases out (decelerates near the end)
 * so number changes feel weighty rather than linear.
 */
export function useAnimatedNumber(value: number, durationMs: number = 700): number {
  const [display, setDisplay] = useState(value);
  const fromRef = useRef(value);
  const toRef = useRef(value);
  const startedAtRef = useRef<number>(0);
  const rafRef = useRef<number | null>(null);

  useEffect(() => {
    if (value === toRef.current) return;
    fromRef.current = display;
    toRef.current = value;
    startedAtRef.current = performance.now();

    const tick = () => {
      const t = (performance.now() - startedAtRef.current) / durationMs;
      if (t >= 1) {
        setDisplay(toRef.current);
        rafRef.current = null;
        return;
      }
      // easeOutCubic
      const eased = 1 - Math.pow(1 - t, 3);
      const next = fromRef.current + (toRef.current - fromRef.current) * eased;
      setDisplay(next);
      rafRef.current = requestAnimationFrame(tick);
    };

    if (rafRef.current !== null) cancelAnimationFrame(rafRef.current);
    rafRef.current = requestAnimationFrame(tick);

    return () => {
      if (rafRef.current !== null) cancelAnimationFrame(rafRef.current);
      rafRef.current = null;
    };
    // We intentionally exclude `display` from deps — it changes every
    // frame during the animation and would re-trigger the effect.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value, durationMs]);

  return display;
}
