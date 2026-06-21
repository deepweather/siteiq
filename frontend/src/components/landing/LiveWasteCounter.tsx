/**
 * Live waste counter — a number that ticks up in euros while the user
 * looks at it. The same metric the product surfaces on the dashboard,
 * so the funnel feels coherent.
 *
 * The increment per second is `perDayEUR / 86400`. We render in monospace
 * tabular-nums so the digits don't shimmer.
 */
import { useEffect, useRef, useState } from 'react';

export function LiveWasteCounter({ perDayEUR }: { perDayEUR: number }) {
  const [value, setValue] = useState(0);
  const start = useRef<number | null>(null);

  useEffect(() => {
    let raf = 0;
    const tick = (now: number) => {
      if (start.current === null) start.current = now;
      const elapsedSec = (now - start.current) / 1000;
      setValue((perDayEUR * elapsedSec) / 86400);
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [perDayEUR]);

  return (
    <span aria-live="polite">
      €{value.toFixed(2).replace(/\B(?=(\d{3})+(?!\d))/g, ',')}
    </span>
  );
}
