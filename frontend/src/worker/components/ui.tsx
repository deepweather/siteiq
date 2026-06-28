/**
 * Worker UI primitives — tuned for gloves + sun + glances.
 * Everything is large (>=64px touch targets), high-contrast, icon-led.
 */
import type { ButtonHTMLAttributes, ReactNode } from 'react';

export function Screen({ children, className = '' }: { children: ReactNode; className?: string }) {
  return <div className={`px-4 py-4 space-y-4 ${className}`}>{children}</div>;
}

export function Spinner({ label }: { label?: string }) {
  return (
    <div className="flex flex-col items-center justify-center py-16 text-muted-foreground">
      <div className="w-10 h-10 border-4 border-muted border-t-primary rounded-full animate-spin" />
      {label ? <div className="mt-3 text-base">{label}</div> : null}
    </div>
  );
}

type Variant = 'primary' | 'secondary' | 'destructive' | 'success';

const VARIANTS: Record<Variant, string> = {
  primary: 'bg-primary text-primary-foreground',
  secondary: 'bg-secondary text-secondary-foreground',
  destructive: 'bg-destructive text-white',
  success: 'bg-success text-white',
};

export function WorkerButton({
  variant = 'primary',
  children,
  className = '',
  ...rest
}: { variant?: Variant; children: ReactNode } & ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      className={`w-full min-h-[68px] rounded-2xl px-5 text-xl font-semibold
        active:scale-[0.98] transition-transform disabled:opacity-50
        disabled:active:scale-100 ${VARIANTS[variant]} ${className}`}
      {...rest}
    >
      {children}
    </button>
  );
}

/** Big square action tile for the home grid. */
export function Tile({
  emoji,
  label,
  tint,
  onClick,
}: {
  emoji: string;
  label: string;
  tint: string;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className="aspect-square rounded-3xl bg-card border border-border shadow-sm
        flex flex-col items-center justify-center gap-2 active:scale-[0.97]
        transition-transform"
    >
      <span
        className="w-16 h-16 rounded-2xl flex items-center justify-center text-4xl"
        style={{ background: tint }}
        aria-hidden
      >
        {emoji}
      </span>
      <span className="text-lg font-semibold text-foreground">{label}</span>
    </button>
  );
}

export interface Choice {
  id: string;
  label: string;
  emoji?: string;
  hint?: string;
}

/** Vertical stack of large single-select rows. */
export function BigChoice({
  choices,
  value,
  onSelect,
}: {
  choices: Choice[];
  value: string | null;
  onSelect: (id: string) => void;
}) {
  return (
    <div className="space-y-3">
      {choices.map((c) => {
        const active = c.id === value;
        return (
          <button
            key={c.id}
            onClick={() => onSelect(c.id)}
            className={`w-full min-h-[68px] rounded-2xl px-5 flex items-center gap-4
              border-2 text-left active:scale-[0.98] transition-transform
              ${active ? 'border-primary bg-primary/10' : 'border-border bg-card'}`}
          >
            {c.emoji ? <span className="text-3xl" aria-hidden>{c.emoji}</span> : null}
            <span className="flex-1">
              <span className="block text-xl font-semibold text-foreground">{c.label}</span>
              {c.hint ? <span className="block text-sm text-muted-foreground">{c.hint}</span> : null}
            </span>
            {active ? <span className="text-primary text-2xl" aria-hidden>✓</span> : null}
          </button>
        );
      })}
    </div>
  );
}

/** Inline wrap-chips, single-select. */
export function ChipGroup({
  choices,
  value,
  onSelect,
}: {
  choices: Choice[];
  value: string | null;
  onSelect: (id: string) => void;
}) {
  return (
    <div className="flex flex-wrap gap-2">
      {choices.map((c) => {
        const active = c.id === value;
        return (
          <button
            key={c.id}
            onClick={() => onSelect(c.id)}
            className={`min-h-[52px] px-5 rounded-full text-lg font-medium border-2
              active:scale-[0.97] transition-transform
              ${active ? 'border-primary bg-primary text-primary-foreground' : 'border-border bg-card text-foreground'}`}
          >
            {c.label}
          </button>
        );
      })}
    </div>
  );
}

/** Big numeric stepper with an optional unit and a tap-to-type fallback. */
export function Stepper({
  value,
  unit,
  step = 1,
  min = 0,
  onChange,
}: {
  value: number;
  unit?: string;
  step?: number;
  min?: number;
  onChange: (n: number) => void;
}) {
  const clamp = (n: number) => Math.max(min, Math.round(n * 10) / 10);
  return (
    <div className="flex items-center justify-between gap-3">
      <button
        onClick={() => onChange(clamp(value - step))}
        className="w-16 h-16 rounded-2xl bg-secondary text-3xl font-bold active:scale-95"
        aria-label="minus"
      >
        −
      </button>
      <div className="flex-1 flex items-baseline justify-center gap-2">
        <input
          inputMode="decimal"
          value={String(value)}
          onChange={(e) => {
            const n = parseFloat(e.target.value);
            onChange(Number.isFinite(n) ? clamp(n) : 0);
          }}
          className="w-24 text-center bg-transparent font-mono text-5xl font-bold text-foreground outline-none"
        />
        {unit ? <span className="text-2xl text-muted-foreground">{unit}</span> : null}
      </div>
      <button
        onClick={() => onChange(clamp(value + step))}
        className="w-16 h-16 rounded-2xl bg-secondary text-3xl font-bold active:scale-95"
        aria-label="plus"
      >
        +
      </button>
    </div>
  );
}

export function FieldLabel({ children }: { children: ReactNode }) {
  return <h2 className="text-2xl font-bold text-foreground mb-4">{children}</h2>;
}
