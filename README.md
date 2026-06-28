# SiteIQ — Construction Site Intelligence

Real-time construction site monitoring and optimization. A simulation engine
generates asset position data, computes waste analytics, and prescribes
operational fixes — and the same pipeline can be driven by **real devices**
(cameras / gateways / sensors) in **Live Mode**.

Three frontends/clients talk to one backend + one event ledger:
- the **dashboard** (`/`) — the optimization story for managers,
- the **worker PWA** (`/worker/`) — an offline-first field-crew app,
- **edge agents** (`edge/`) — on-device software that posts to `/api/ingest`.

For the full architecture see [`claude.md`](claude.md); for on-device
software see [`edge/README.md`](edge/README.md).

## Quick Start

### Backend
```bash
cd backend
uv sync
# Apply database migrations (creates the SQLite file by default).
uv run alembic upgrade head
uv run uvicorn main:app --host 0.0.0.0 --port 8000
```

Configure via `.env` (see `backend/.env.example`). In dev, transactional
emails are written to `email_outbox` and visible at
`http://localhost:8000/dev/outbox`.

#### Local demo user

For poking around the dashboard without going through signup +
verification email, run the idempotent seed script:

```bash
cd backend
uv run python seed_demo_user.py
# email:    demo@siteiq.dev
# password: DemoPassword123!
# org:      Demo Construction (owner)
```

The script writes directly via the ORM, so the email-verify token is
skipped and the user lands on the dashboard immediately. Re-running it
just resets the password — handy after wiping `siteiq.db`. Override
`SITEIQ_DEMO_EMAIL`, `SITEIQ_DEMO_PASSWORD`, `SITEIQ_DEMO_NAME`, or
`SITEIQ_DEMO_COMPANY` if you want different defaults.

### Frontend (dashboard)
```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173

### Worker app (field-crew PWA)

A separate, same-origin bundle served under `/worker/` — offline-first,
German-first (with an EN toggle), big-button entry capture, and asset/material
lookup. Crew entries land as `proposed` in the supervisor's Record Inbox.

```bash
cd frontend
npm run dev:worker     # dev server, open http://localhost:5174/worker/
npm run build:worker   # production bundle -> dist/worker (served at /worker/)
```

Log in with a magic link (in dev, the link appears at
`http://localhost:8000/dev/outbox`). It installs to a phone home screen and
keeps a local outbox so entries survive dead zones and sync on reconnect.

### Edge devices (cameras / gateways / sensors)

On-site software that authenticates with a one-time **claim code** (minted in
the UI under **Settings → Devices**) and posts events to `/api/ingest`. Flip
the dashboard to **Live Mode** (the `SIM`/`LIVE` toggle in the menu bar) to
drive it from real device data instead of the simulation.

```bash
# 1. Settings -> Devices -> Add device -> copy the claim code.
# 2. Build + run the Go agent on the device:
cd edge/agent && go build -o siteiq-agent .
./siteiq-agent claim --server http://localhost:8000 --code <CODE>
./siteiq-agent run   --server http://localhost:8000
# 3. (camera) run the CV sidecar against a stream or the demo videos:
cd ../sidecar && pip install -r requirements.txt
python sidecar.py --source demo --agent http://127.0.0.1:9099
```

See [`edge/README.md`](edge/README.md) for the gateway/ESP32 tiers, Docker
images, and the full device contract.

### Production stack via Docker Compose

```bash
docker compose up --build
# → frontend:  http://localhost:8080
# → backend:   http://localhost:8000
# → Postgres:  localhost:5432  (user: siteiq, db: siteiq)
```

The compose file mirrors a real prod deployment:
- Backend image (multi-stage `uv` build) runs `alembic upgrade head`
  on start, then `uvicorn`.
- Frontend image bakes the API origin in at build time via Vite env
  args and serves the SPA from nginx.
- Postgres replaces the dev SQLite file. The session-secret + email
  provider come from env vars (`SITEIQ_*`) — review them in
  `docker-compose.yml` before going live.

## Architecture

- **Backend**: Python/FastAPI; per-org `SimulationEngine` at 10 Hz OR a
  device-fed `LiveSource` (both implement one `SiteStateSource` seam); an
  append-only, hash-chained event ledger as the system of record. Managed by `uv`.
- **Frontend**: React/TypeScript/Vite — dashboard (Canvas + Tailwind) and a
  separate worker PWA (`vite-plugin-pwa`, IndexedDB outbox).
- **Edge**: a Go agent (durable SQLite outbox) + Python CV sidecar (YOLO) +
  gateway bridge for low-power sensors.
- **Communication**: WebSocket for live position + analytics streaming; REST
  for recommendations, controls, the record, and device ingestion.

## Demo Flow

1. Site loads with 50 workers, 3 equipment pieces, and deliberately suboptimal facility placement
2. Watch workers walk absurd distances to toilets (placed in far corners)
3. Toggle "Trails" to see movement patterns — long diagonal lines are the waste
4. Switch to "Recommendations" tab and click "Apply All"
5. Watch facilities relocate, paths shorten, and waste numbers drop in real time
