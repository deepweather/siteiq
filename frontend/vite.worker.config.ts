import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { VitePWA } from 'vite-plugin-pwa'

// Separate build for the field-crew PWA. Served same-origin under
// `/worker/` by the same nginx as the main SPA, so the session cookie +
// CSRF flow work unchanged. Its own service worker is scoped to `/worker/`
// so the heavy dashboard bundle is never cached onto a worker's phone.
//
//   npm run dev:worker     # dev server (different port, proxies nothing —
//                          # API_BASE points straight at the backend)
//   npm run build:worker   # -> dist/worker
export default defineConfig({
  base: '/worker/',
  build: {
    outDir: 'dist/worker',
    emptyOutDir: true,
    rollupOptions: {
      input: 'worker.html',
    },
  },
  server: {
    port: 5174,
  },
  plugins: [
    react(),
    VitePWA({
      registerType: 'autoUpdate',
      scope: '/worker/',
      base: '/worker/',
      filename: 'sw.js',
      manifestFilename: 'manifest.webmanifest',
      includeAssets: ['icon.svg'],
      workbox: {
        navigateFallback: '/worker/worker.html',
        // Don't precache giant chunks; the app is intentionally small.
        globPatterns: ['**/*.{js,css,html,svg,woff2}'],
        runtimeCaching: [
          {
            // Read endpoints: serve last-known data in a dead zone.
            urlPattern: ({ url }) => url.pathname.startsWith('/api/worker/'),
            handler: 'NetworkFirst',
            options: {
              cacheName: 'worker-api',
              networkTimeoutSeconds: 4,
              expiration: { maxEntries: 64, maxAgeSeconds: 60 * 60 * 24 },
            },
          },
        ],
      },
      manifest: {
        name: 'SiteIQ Crew',
        short_name: 'SiteIQ',
        description: 'Field-crew app for logging deliveries, issues, and inspections.',
        start_url: '/worker/',
        scope: '/worker/',
        display: 'standalone',
        orientation: 'portrait',
        background_color: '#fafafa',
        theme_color: '#ea580c',
        icons: [
          { src: 'icon.svg', sizes: 'any', type: 'image/svg+xml', purpose: 'any maskable' },
        ],
      },
      devOptions: {
        enabled: false,
      },
    }),
  ],
})
