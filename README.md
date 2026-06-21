# SiteIQ — Construction Site Intelligence

Real-time construction site monitoring and optimization demo. Uses a simulation engine to generate asset position data, compute waste analytics, and prescribe operational fixes.

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

### Frontend
```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:5173

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

- **Backend**: Python/FastAPI with in-memory simulation engine running at 10Hz, managed by `uv`
- **Frontend**: React/TypeScript/Vite with HTML5 Canvas rendering and Tailwind CSS
- **Communication**: WebSocket for real-time position + analytics streaming, REST for recommendations and controls

## Demo Flow

1. Site loads with 50 workers, 3 equipment pieces, and deliberately suboptimal facility placement
2. Watch workers walk absurd distances to toilets (placed in far corners)
3. Toggle "Trails" to see movement patterns — long diagonal lines are the waste
4. Switch to "Recommendations" tab and click "Apply All"
5. Watch facilities relocate, paths shorten, and waste numbers drop in real time
