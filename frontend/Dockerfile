# SiteIQ frontend — Vite build → nginx static.
#
# At build time, the API base must be baked in (Vite inlines env vars
# at build, not runtime). Override via:
#   docker build --build-arg VITE_API_BASE=https://api.example.com \
#                --build-arg VITE_WS_BASE=wss://api.example.com .
#
FROM node:22-alpine AS builder

WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund

COPY . .
ARG VITE_API_BASE=http://localhost:8000
ARG VITE_WS_BASE=ws://localhost:8000
ENV VITE_API_BASE=$VITE_API_BASE \
    VITE_WS_BASE=$VITE_WS_BASE
# Main dashboard SPA + the separate same-origin worker PWA (-> dist/worker).
RUN npm run build && npm run build:worker


FROM nginx:1.27-alpine AS runtime

# A tiny nginx config that serves the SPA + falls back to index.html
# for client-side routes (so /app/settings/team works on a hard
# refresh).
COPY <<'EOF' /etc/nginx/conf.d/default.conf
server {
    listen 80;
    server_name _;
    root /usr/share/nginx/html;
    index index.html;

    # Long cache for hashed assets, no-cache for the entry HTML.
    location /assets/ {
        expires 1y;
        add_header Cache-Control "public, immutable";
    }

    # Worker PWA — separate same-origin bundle. SPA fallback to its own
    # entry so deep links like /worker/assets survive a hard refresh.
    location /worker/assets/ {
        expires 1y;
        add_header Cache-Control "public, immutable";
    }
    location /worker/ {
        try_files $uri $uri/ /worker/worker.html;
        add_header Cache-Control "no-store" always;
    }

    location / {
        try_files $uri $uri/ /index.html;
        add_header Cache-Control "no-store" always;
    }
}
EOF

COPY --from=builder /app/dist /usr/share/nginx/html

EXPOSE 80
HEALTHCHECK --interval=30s --timeout=3s --retries=3 \
    CMD wget -qO- http://localhost/ >/dev/null || exit 1
