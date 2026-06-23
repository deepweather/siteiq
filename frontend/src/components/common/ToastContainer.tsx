import { useEffect, useState } from 'react';
import { dismissToast, subscribeToasts, type Toast } from '../../utils/toasts';

// Tone styling. The earlier `bg-X/5` overlay actually clobbered the
// card background (Tailwind applies the later `bg-*` class), leaving
// the toast looking transparent / "unstyled" because 5% alpha let the
// canvas behind show through. We now keep `bg-card` as the substrate
// and rely on the border + icon chip to convey the tone.
const TONE_STYLES: Record<Toast['tone'], { ring: string; text: string; icon: string; iconBg: string }> = {
  success: {
    ring: 'border-success/40',
    text: 'text-success',
    iconBg: 'bg-success/15',
    icon: '\u2713',
  },
  info: {
    ring: 'border-primary/40',
    text: 'text-primary',
    iconBg: 'bg-primary/15',
    icon: 'i',
  },
  warning: {
    ring: 'border-warning/40',
    text: 'text-warning',
    iconBg: 'bg-warning/15',
    icon: '!',
  },
};

export function ToastContainer() {
  const [toasts, setToasts] = useState<Toast[]>([]);
  useEffect(() => subscribeToasts(setToasts), []);

  return (
    <div
      className="pointer-events-none fixed bottom-4 right-4 z-50 flex w-[340px] max-w-[calc(100vw-2rem)] flex-col-reverse gap-2"
      aria-live="polite"
      aria-atomic="false"
    >
      {toasts.map((t) => (
        <ToastCard key={t.id} toast={t} />
      ))}
    </div>
  );
}

function ToastCard({ toast }: { toast: Toast }) {
  const style = TONE_STYLES[toast.tone];
  return (
    <div
      role="status"
      className={`pointer-events-auto flex items-start gap-3 rounded-lg border bg-card p-3 shadow-lg animate-toast-in ${style.ring}`}
    >
      <span
        className={`mt-0.5 inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-full font-bold ${style.iconBg} ${style.text}`}
        aria-hidden="true"
      >
        {style.icon}
      </span>
      <div className="min-w-0 flex-1">
        <div className="text-sm font-semibold text-foreground">{toast.title}</div>
        {toast.subtitle && (
          <div className="mt-0.5 text-xs text-muted-foreground leading-snug">{toast.subtitle}</div>
        )}
      </div>
      <button
        type="button"
        onClick={() => dismissToast(toast.id)}
        className="-mr-1 -mt-1 ml-1 inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-md text-muted-foreground hover:bg-secondary hover:text-foreground"
        aria-label="Dismiss notification"
      >
        &times;
      </button>
    </div>
  );
}
