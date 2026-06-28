import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  optimizeDeps: {
    // Scope dependency pre-bundling to the main app's entry. Without this,
    // Vite also scans `worker.html` (the separate PWA bundle, built via
    // `vite.worker.config.ts`), which imports `virtual:pwa-register` — a
    // module only the worker config's vite-plugin-pwa provides. The main
    // config can't resolve it, the dep scan fails, pre-bundling is skipped,
    // and lazy route imports start failing ("Failed to fetch dynamically
    // imported module"). Pinning entries to index.html ignores worker.html.
    entries: ['index.html'],
  },
})
