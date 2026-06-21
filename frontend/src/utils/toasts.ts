/**
 * Tiny module-level toast queue.
 *
 * Why module-level instead of React Context? Toasts cross-cut the entire
 * app — every async handler in any component might want to push one. A
 * Context provider would force everything to be wrapped + threaded
 * through. A subscribe-based singleton is simpler and friction-free.
 */
export type ToastTone = 'success' | 'info' | 'warning';

export interface Toast {
  id: number;
  title: string;
  subtitle?: string;
  tone: ToastTone;
  /** Auto-dismiss after this many ms. 0 = sticky. Default 4500. */
  ttlMs: number;
}

type Listener = (toasts: Toast[]) => void;

let nextId = 1;
let current: Toast[] = [];
const listeners = new Set<Listener>();
const dismissTimers = new Map<number, ReturnType<typeof setTimeout>>();

function emit(): void {
  for (const l of listeners) l(current);
}

export function pushToast(input: Omit<Toast, 'id' | 'ttlMs'> & { ttlMs?: number }): number {
  const id = nextId++;
  const ttlMs = input.ttlMs ?? 4500;
  const toast: Toast = { ...input, id, ttlMs };
  current = [...current, toast];
  emit();
  if (ttlMs > 0) {
    dismissTimers.set(id, setTimeout(() => dismissToast(id), ttlMs));
  }
  return id;
}

export function dismissToast(id: number): void {
  current = current.filter((t) => t.id !== id);
  const timer = dismissTimers.get(id);
  if (timer) {
    clearTimeout(timer);
    dismissTimers.delete(id);
  }
  emit();
}

export function subscribeToasts(fn: Listener): () => void {
  listeners.add(fn);
  fn(current); // emit initial
  return () => {
    listeners.delete(fn);
  };
}

/** Test helper — wipe queue + cancel timers. */
export function _resetToasts(): void {
  for (const t of dismissTimers.values()) clearTimeout(t);
  dismissTimers.clear();
  current = [];
  nextId = 1;
  emit();
}
