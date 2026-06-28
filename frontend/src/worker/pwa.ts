/// <reference types="vite-plugin-pwa/client" />

/**
 * Service-worker registration for the worker PWA. Auto-updates in the
 * background; we keep it best-effort so a registration failure never blocks
 * the app (it still works as a plain SPA).
 */
import { registerSW } from 'virtual:pwa-register';

export function registerWorkerSW(): void {
  try {
    registerSW({ immediate: true });
  } catch {
    /* SW unsupported / blocked — app degrades to online-only. */
  }
}
