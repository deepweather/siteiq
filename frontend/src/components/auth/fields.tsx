/** Shared form primitives. Tailwind classes only — keeps bundle small. */
import { forwardRef, useId, type InputHTMLAttributes, type ReactNode } from 'react';

interface FieldProps extends InputHTMLAttributes<HTMLInputElement> {
  label: string;
  error?: string;
  hint?: ReactNode;
}

export const TextField = forwardRef<HTMLInputElement, FieldProps>(function TextField(
  { label, error, hint, className = '', id, ...rest },
  ref,
) {
  const generatedId = useId();
  const inputId = id ?? generatedId;
  return (
    <div className="mb-4">
      <label htmlFor={inputId} className="block text-sm font-medium mb-1">
        {label}
      </label>
      <input
        ref={ref}
        id={inputId}
        className={
          'w-full rounded-md border border-input bg-background px-3 py-2 text-sm ' +
          'placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary ' +
          (error ? 'border-destructive ' : '') +
          className
        }
        aria-invalid={Boolean(error)}
        {...rest}
      />
      {hint && !error && <p className="text-xs text-muted-foreground mt-1">{hint}</p>}
      {error && <p className="text-xs text-destructive mt-1">{error}</p>}
    </div>
  );
});

export function FormError({ children }: { children?: ReactNode }) {
  if (!children) return null;
  return (
    <div className="rounded-md border border-destructive/40 bg-destructive/10 text-destructive text-sm px-3 py-2 mb-4">
      {children}
    </div>
  );
}

export function SubmitButton({
  loading,
  children,
}: {
  loading?: boolean;
  children: ReactNode;
}) {
  return (
    <button
      type="submit"
      disabled={loading}
      className={
        'w-full rounded-md bg-primary text-primary-foreground font-semibold text-sm py-2.5 ' +
        'hover:bg-primary/90 disabled:opacity-60 transition-colors'
      }
    >
      {loading ? 'Working…' : children}
    </button>
  );
}
