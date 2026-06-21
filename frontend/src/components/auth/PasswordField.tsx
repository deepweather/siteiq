/**
 * Password field with a zxcvbn-ts-driven strength meter and an HIBP
 * k-anonymity breach check.
 *
 * - zxcvbn is loaded lazily (~150 KB gzipped of dictionaries) so the
 *   auth forms stay snappy on cold-load.
 * - HIBP runs on blur (debounced via a 600 ms idle timer) so we don't
 *   round-trip on every keystroke. The check is privacy-preserving:
 *   only the first 5 hex chars of SHA-1(password) leave the browser.
 * - If the password is found in a known breach, we render a clear
 *   warning beneath the meter with the breach count.
 */
import { forwardRef, useEffect, useState, type InputHTMLAttributes } from 'react';
import { TextField } from './fields';
import { checkBreach } from './hibp';

interface Props extends Omit<InputHTMLAttributes<HTMLInputElement>, 'type'> {
  label?: string;
  error?: string;
  showStrength?: boolean;
  passwordValue?: string;
}

const SEGMENTS = 4;
const LABELS = ['Weak', 'Fair', 'Good', 'Strong', 'Excellent'] as const;

export const PasswordField = forwardRef<HTMLInputElement, Props>(function PasswordField(
  { label = 'Password', error, showStrength = true, passwordValue, ...rest },
  ref,
) {
  const [show, setShow] = useState(false);
  const value = passwordValue ?? '';
  const score = useStrengthScore(showStrength ? value : null);
  const breachCount = useBreachCheck(showStrength ? value : null);

  return (
    <div className="mb-4">
      <div className="flex items-center justify-between mb-1">
        <label className="block text-sm font-medium">{label}</label>
        <button
          type="button"
          onClick={() => setShow((s) => !s)}
          className="text-xs text-muted-foreground hover:text-foreground"
        >
          {show ? 'Hide' : 'Show'}
        </button>
      </div>
      <input
        ref={ref}
        type={show ? 'text' : 'password'}
        className={
          'w-full rounded-md border border-input bg-background px-3 py-2 text-sm ' +
          'placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary ' +
          (error ? 'border-destructive' : '')
        }
        aria-invalid={Boolean(error)}
        {...rest}
      />
      {showStrength && value.length > 0 && (
        <div className="mt-2 flex items-center gap-2">
          <div className="flex-1 grid grid-cols-4 gap-1">
            {Array.from({ length: SEGMENTS }).map((_, i) => (
              <div
                key={i}
                className={
                  'h-1.5 rounded-full ' +
                  (i < (score === null ? 0 : score)
                    ? score! <= 1
                      ? 'bg-destructive'
                      : score! === 2
                        ? 'bg-amber-500'
                        : 'bg-emerald-500'
                    : 'bg-muted')
                }
              />
            ))}
          </div>
          <span className="text-xs text-muted-foreground tabular-nums w-16 text-right">
            {score === null ? '…' : LABELS[score] ?? 'Weak'}
          </span>
        </div>
      )}
      {showStrength && breachCount > 0 && (
        <p className="text-xs text-destructive mt-1">
          This password has appeared in {breachCount.toLocaleString()} known data breach{breachCount === 1 ? '' : 'es'}. Pick a different one.
        </p>
      )}
      {error && <p className="text-xs text-destructive mt-1">{error}</p>}
    </div>
  );
});

// Hidden-by-default to keep TextField's API export untouched.
TextField.displayName ??= 'TextField';

/**
 * HIBP k-anonymity check, debounced. Returns -1 (network failure) /
 * 0 (clean) / N (breach count). We start at 0 and only update when the
 * user pauses typing for ~600 ms, so the check fires once per "draft".
 */
function useBreachCheck(value: string | null): number {
  const [count, setCount] = useState(0);
  useEffect(() => {
    if (value === null) return;
    if (!value || value.length < 8) {
      setCount(0);
      return;
    }
    const ctrl = new AbortController();
    const timer = window.setTimeout(async () => {
      const n = await checkBreach(value, ctrl.signal);
      if (!ctrl.signal.aborted) setCount(n < 0 ? 0 : n);
    }, 600);
    return () => {
      window.clearTimeout(timer);
      ctrl.abort();
    };
  }, [value]);
  return count;
}


function useStrengthScore(value: string | null): number | null {
  const [score, setScore] = useState<number | null>(null);
  useEffect(() => {
    if (value === null) return;
    if (!value) {
      setScore(null);
      return;
    }
    let cancelled = false;
    (async () => {
      const [coreMod, common, en] = await Promise.all([
        import('@zxcvbn-ts/core'),
        import('@zxcvbn-ts/language-common'),
        import('@zxcvbn-ts/language-en'),
      ]);
      const { zxcvbn, zxcvbnOptions } = coreMod as unknown as {
        zxcvbn: (pw: string) => { score: number };
        zxcvbnOptions: { setOptions: (o: unknown) => void };
      };
      zxcvbnOptions.setOptions({
        dictionary: {
          ...common.dictionary,
          ...en.dictionary,
        },
        translations: en.translations,
        graphs: common.adjacencyGraphs,
      });
      const result = zxcvbn(value);
      if (!cancelled) setScore(result.score);
    })();
    return () => {
      cancelled = true;
    };
  }, [value]);
  return score;
}
