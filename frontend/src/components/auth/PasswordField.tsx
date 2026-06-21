/**
 * Password field with a zxcvbn-ts-driven strength meter.
 *
 * zxcvbn is loaded lazily (~150 KB gzipped of dictionaries) so the auth
 * forms stay snappy on cold-load. Below the input we show a 4-segment
 * meter with the matching label (Weak / Fair / Good / Strong / Excellent)
 * and an estimated crack-time hint.
 */
import { forwardRef, useEffect, useState, type InputHTMLAttributes } from 'react';
import { TextField } from './fields';

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
      {error && <p className="text-xs text-destructive mt-1">{error}</p>}
    </div>
  );
});

// Hidden-by-default to keep TextField's API export untouched.
TextField.displayName ??= 'TextField';

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
