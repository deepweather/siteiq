# SiteIQ — Claude Context

## What this is

SiteIQ is an interactive demo of a construction site intelligence product. The thesis: construction sites are catastrophically inefficient — workers are productive only 35% of their time. SiteIQ uses cameras + CV to observe everything on a site, quantify waste in euros, and prescribe specific operational fixes.

For this demo, a **simulation engine** replaces real camera feeds. The simulation generates the same data that real CV would. The demo must make an investor or construction executive viscerally understand the waste and see it fixed in real time — in under 3 minutes, no narration needed.

## Architecture overview

Two disconnected systems exist today, gated by a self-hosted auth layer:

```
                              ┌────────── Frontend (React Router) ──────────┐
                              │  Public:                                    │
                              │   / LandingPage                             │
                              │   /login /signup /forgot-password           │
                              │   /reset-password /verify-email             │
                              │   /accept-invite                            │
                              │  Gated /app/*  (RequireAuth):               │
                              │   Dashboard + Settings (Account / Team /    │
                              │   Workspaces / Sessions)                    │
                              └────────────────┬────────────────────────────┘
                                               │ cookie + CSRF
                                               ▼
SIMULATION (the demo)                    VISION (disconnected proof-of-concept)
┌──────────────────────┐                 ┌─────────────────────────┐
│ SimulationEngine     │                 │ VideoDetector           │
│ - 50–60 workers FSM  │                 │ - YOLOv8n on .mp4 files │
│ - equipment duty     │                 │ - base64 JPEG frames    │
│   cycles             │    NO LINK      │ - bounding box coords   │
│ - position trails    │◄──────────────►│ - confidence scores     │
│ - analytics/waste    │                 │                         │
│ - recommendations    │                 │ Serves: /ws/camera/{id} │
│                      │                 └─────────────────────────┘
│ Serves: /ws (10Hz)   │                            ▲
│         /api/*       │                            │ all gated by
└──────────┬───────────┘                            │ Depends(get_current_org)
           │ all gated by Depends(get_current_org)  │
           └────────────────┬───────────────────────┘
                            │
                            ▼
                ┌──────────────────────────────────┐
                │ FastAPI app                      │
                │  /auth/*  /api/*  /api/orgs/*    │
                │  CSRF middleware + Origin check  │
                │  CORS  Error envelope handler    │
                │  app.state: db engine, email     │
                │  sender, limiter, source, recs   │
                └──────────────┬───────────────────┘
                               │
                               ▼
                ┌──────────────────────────────────┐
                │ SQLAlchemy async (SQLite|Postgres)│
                │ users, orgs, memberships, invites│
                │ sessions, tokens, outbox, audits │
                └──────────────────────────────────┘
```

The camera feeds and the simulation are still not synchronized — see the
"Architectural debt" section. The product story is "cameras → intelligence
→ decisions" but the demo shows two unrelated systems side by side.

### What "Live Mode" should eventually look like

```
Real cameras → YOLO inference → Camera calibration → 2D site map
                                (pixel → meter transform)
                                        │
                                        ▼
                              Same analytics/optimization
                              pipeline as simulation mode
```

The simulation engine would be replaced by real detection data projected onto the site plan.

## Tech stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.13, FastAPI, uvicorn, WebSocket, Pydantic v2, pydantic-settings |
| Persistence | SQLAlchemy 2.0 async, Alembic, aiosqlite (dev/test) / asyncpg (prod) |
| Auth | argon2-cffi (passwords), opaque server-side sessions, slowapi (rate limit), httpx (Resend) |
| Frontend | React 19, Vite 8, TypeScript 6, Tailwind CSS 3, HTML5 Canvas |
| Frontend libs | react-router-dom v6, react-hook-form, zod, @zxcvbn-ts (lazy), sonner |
| CV | ultralytics (YOLOv8n), opencv-python-headless |
| Package mgmt | uv (backend), npm (frontend) |
| Real-time | WebSocket at 10Hz for sim state, ~5Hz for camera frames |

## Running the app

```bash
# Backend
cd backend
uv sync
uv run alembic upgrade head           # creates ./siteiq.db on first run
uv run uvicorn main:app --host 0.0.0.0 --port 8000

# Frontend
cd frontend
npm install
npm run dev
# → http://localhost:5173
```

Settings are read from `backend/.env` (see `backend/.env.example` for every
`SITEIQ_*` knob). In dev mode the verification + reset emails are persisted
to the `email_outbox` table and visible at `http://localhost:8000/dev/outbox`
— no SMTP setup needed.

Camera feeds require .mp4 files in `backend/vision/videos/`. Two Pexels CC0
videos are downloaded but gitignored. YOLO model weights (`yolov8n.pt`)
auto-download on first run.

## Auth, orgs, and persistence

A self-hosted auth stack sits in front of every `/api/*` and WebSocket
route. SQLite drives dev/test (zero setup), Postgres drives prod — both
behind one async SQLAlchemy 2.0 engine selected via `SITEIQ_DATABASE_URL`.

```mermaid
flowchart LR
    Browser["Browser (cookie + CSRF)"] --> Routes
    subgraph backend [FastAPI app]
        Routes["/auth/* and /api/* routers"]
        Routes --> Deps["api/deps.py: get_current_user, get_current_org, require_role"]
        Deps --> DB[("SQLAlchemy async DB<br/>SQLite dev / Postgres prod")]
        Deps --> Source["SiteStateSource (existing)"]
        Routes --> Email["EmailSender Protocol"]
        Email --> Console["ConsoleSender (dev)"]
        Email --> Resend["ResendSender (prod)"]
    end
    DB --> Tables["users, orgs, org_memberships, org_invites,<br/>auth_sessions, verification_tokens, email_outbox, audit_events"]
```

### Rate limiting + abuse controls
slowapi limiter as a module-level singleton in `auth/rate_limit.py`
(required because `@limiter.limit("…")` captures it at decoration
time). Wired on:

- `POST /auth/signup` — 5 / hour / IP (signup-spam guard)
- `POST /auth/login` — 10 / minute / IP (brute-force guard)
- `POST /auth/forgot-password` — 5 / hour / IP (email-cost guard)

Storage is in-memory by default; `SITEIQ_RATE_LIMIT_REDIS_URL` swaps to
Redis at lifespan start so multi-worker deployments share counters.
The 429 response goes through the standard `{error: {code, message}}`
envelope (`code: "rate_limited"`).

### Security headers
`api/security_headers.py` is a pure ASGI middleware (deliberately not
`BaseHTTPMiddleware` — the latter deadlocks `TestClient` when stacked
≥3 deep). On every HTTP response it adds:

- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: DENY`
- `Referrer-Policy: strict-origin-when-cross-origin`
- `Permissions-Policy: geolocation=(), microphone=(), camera=(), payment=()`
- `Content-Security-Policy` — `default-src 'self'`, frame-ancestors
  blocked, object-src blocked, `connect-src` whitelist includes
  `api.pwnedpasswords.com` for the HIBP breach check
- `Strict-Transport-Security: max-age=31536000; includeSubDomains` —
  **only when `env=prod`** (would lock localhost into HTTPS-upgrades)

### Email outbox retention
`auth/outbox_cleanup.py` is a periodic background task spawned in the
lifespan. Deletes `email_outbox` rows older than
`SITEIQ_EMAIL_OUTBOX_RETENTION_DAYS` (default 90) every
`SITEIQ_EMAIL_OUTBOX_CLEANUP_INTERVAL_SECONDS` (default 3600). Set
retention to `0` to disable. The lifespan teardown awaits the
cancelled task before disposing the DB engine — without that drain,
an in-flight cleanup can race the engine shutdown and the lifespan
never returns.

### Health, readiness, and version
- `GET /healthz` — liveness, returns 200 + `{"status": "ok"}` while the
  process is up. Used by the Dockerfile + docker-compose healthchecks.
- `GET /readyz` — readiness, returns 200 only when the DB is reachable
  AND the simulation registry is initialised. 503 otherwise so traffic
  is held off briefly during startup.
- `GET /api/version` — returns `{commit, built_at, short}`. Reads
  `SITEIQ_COMMIT_SHA` + `SITEIQ_BUILT_AT` env first; falls back to a
  `version.txt` file the Dockerfile stamps at build time. Surfaced in
  the SettingsLayout footer for support tickets.

All three are unauthenticated and GET-only (so they sail past CSRF).

### Request-id middleware
`api/request_id.py` — pure ASGI middleware, outermost layer. Reads
incoming `X-Request-Id` (e.g. from a load balancer) or generates a UUID
hex, binds it to a `contextvars.ContextVar`, echoes it on the response
header. `logging_config.RequestIdFilter` reads from the ContextVar and
stamps every log record with `request_id=…`. The standard error
envelope includes `request_id` so the frontend's `ApiError.requestId`
is set for every server-rejected request — users can paste it into
support tickets.

### Auth GC
`auth/auth_cleanup.py` — periodic background task that drops fully
revoked / expired `auth_sessions` and consumed / expired
`verification_tokens` after the configured retention windows
(`SITEIQ_AUTH_SESSION_RETENTION_DAYS`, `SITEIQ_AUTH_TOKEN_RETENTION_DAYS`).
Mirrors `outbox_cleanup.py`; the lifespan teardown drains both before
disposing the DB engine.

### Active project per org
`orgs.active_project_id` (added in migration `0002_orgs_active_project`)
persists each org's chosen `PROJECT_TEMPLATES` key. The
`SourceRegistry`'s `for_org` accepts an optional `project_id` argument;
`get_source` passes `org.active_project_id` so a backend restart
rebuilds engines on the right project. `POST /api/projects/{id}/load`
writes the choice back to the row.

### Magic-link login
Passwordless alternative auth path. `POST /auth/request-magic-link`
(rate-limited, silent on unknown emails) drops a 15-minute single-use
token in the user's email. `POST /auth/login-with-token` consumes the
token, sets a session cookie, and returns the same `MeResponse` as a
password login. UI lives at `/magic-link` (form + token-consumer in
the same page) and is reachable from `LoginPage` ("Email me a sign-in
link"). Replays are rejected as `token_used`.

### Audit log CSV export
`GET /api/orgs/current/audit.csv?since=…&until=…` streams up to 10k
rows of audit events as RFC 4180 CSV. Owner-only. The frontend Team
settings page links via `<a download href={orgs.auditCsvUrl()}>` so
the browser handles the file save with the auth cookie attached. Bad
timestamps return the standard `{error: {code: "invalid_timestamp",
field}}` envelope.

### Frontend resilience
- `src/lib/ErrorBoundary.tsx` wraps the entire router. Anything thrown
  during render or in a lifecycle phase becomes a clean recovery card
  with the stack trace + a Reload button (no blank page).
- `src/hooks/useConnectionToast.ts` watches the WS `connected` flag.
  After a 2s grace, drops a sticky "Reconnecting…" toast; on reconnect
  it auto-replaces with a 2.5s "Live again" success.
- All routes are split via `React.lazy` + `Suspense`. Initial bundle
  is ~243 KB (was 434 KB pre-split). Each settings page is ~1–8 KB
  on its own.

### Per-org simulation engines

`backend/state/registry.py` is the registry for `SimulationEngine` +
`RecommendationService` instances, keyed by `org_id`. The `Depends(get_source)`
dependency now resolves the active org first and looks up (or
lazily creates) that org's engine. The simulation tick loop iterates
every live engine. Side effects:

- Two orgs viewing the dashboard see different sites.
- WebSocket auth (`api/ws_auth.py`) returns the session's
  `current_org_id`, and the WS handler uses it to look up the right
  engine.
- Account / workspace deletion calls `registry.discard(org_id)` so the
  engine + analytics + recs are reclaimed immediately.

The `SiteStateSource` Protocol seam still gates everything, so a
future `LiveSource` (camera-fed) implementation drops in by changing
only the registry's `EngineFactory`.

### Account + workspace deletion

- `POST /auth/delete-account` — re-supplies the password, then deletes
  the user. For each org the user owned: if there's another owner,
  the org survives (only the membership goes); if they were the last
  owner, the org is deleted entirely (cascade drops memberships,
  invites, audit_events, and the registry's engine).
- `DELETE /api/orgs/current` — owner-only. Two confirmations:
  type the workspace name + re-supply the password. Sessions whose
  `current_org_id` pointed at the deleted org get nulled — they fall
  back to another membership next request rather than logging out.
- Both record `org.deleted` / `user.deleted` audit events before the
  cascade so an admin can later forensically reconstruct what happened.

### Portfolio waste estimator

`services/portfolio_estimator.py` warms a transient `SimulationEngine`
per project template at app startup (240 ticks ≈ 2 sim-hours), runs
`compute_waste_summary` once, caches the result on
`app.state.portfolio_estimates`. Each `/api/portfolio` card now shows
real per-project daily/monthly numbers instead of the legacy fixed
formula. Tests turn the warm-up off via
`SITEIQ_COMPUTE_PORTFOLIO_AT_STARTUP=false` to keep TestClient
lifespans fast (this means tests fall back to the legacy formula —
acceptable for unit tests; integration smoke covers the live path).

### Sessions, not JWTs
Opaque tokens live in `auth_sessions`; the cookie holds the plaintext,
the DB holds `sha256(token)`. Revocation, sliding expiry, and "sign out
everywhere" are all single SQL updates. Cookie name uses the `__Host-`
prefix when `SITEIQ_COOKIE_SECURE=true` so browsers enforce Path=/, Secure,
no Domain.

### CSRF
Double-submit cookie pattern (`siteiq_csrf` cookie + `X-CSRF-Token` header)
plus an `Origin` allow-list checked on every state-changing request.
WebSockets share the same Origin allow-list and re-verify the session
cookie at upgrade.

### Email
`EmailSender` Protocol mirrors the `SiteStateSource` seam. `ConsoleSender`
persists to `email_outbox`; the same rows are visible at `/dev/outbox`
when `SITEIQ_ENV=dev`. `ResendSender` posts to api.resend.com via httpx
and updates the same row's status. Tests assert against the outbox.

### Orgs + roles
Signup auto-creates an Org named after the company; the user is its
owner. Roles (owner > admin > member > viewer) are checked via
`Depends(require_role(Role.ADMIN))`. Invites are 7-day single-use tokens
keyed to the invitee's email. Every membership change writes an
`audit_events` row (visible to owners on Settings → Team).

### New backend modules
- `db/` — async engine factory + ORM models + `get_db` dependency.
- `auth/` — `passwords.py` (argon2id), `tokens.py`, `sessions.py`,
  `csrf.py`, `rate_limit.py`, `email_sender.py`, `email_templates.py`,
  `service.py`, `routes.py`, `errors.py`, `timeutil.py`.
- `orgs/` — invite/membership service + routes.
- `api/dev.py` — `/dev/outbox` (mounted only when env=dev).
- `api/ws_auth.py` — origin + cookie check shared by `/ws` and `/ws/camera/*`.
- `alembic/` — migrations; one revision (`0001_init_auth`) creates every auth table.

Every existing protected route is wrapped with `Depends(get_current_org)`,
so unauthenticated requests get the canonical `{error: {code, message}}`
401 envelope. The simulation itself stays a single global engine for
v1; per-org engines are a future move and the `SiteStateSource` Protocol
already supports it.

### Frontend auth
- Top-level `BrowserRouter` in `App.tsx` with public routes (`/`,
  `/login`, `/signup`, `/forgot-password`, `/reset-password`,
  `/verify-email`, `/accept-invite`) and gated `/app/*`.
- `lib/auth/AuthProvider.tsx` boots via `GET /auth/me`, exposes
  `useAuth()` everywhere. `RequireAuth` redirects to `/login?next=…`,
  `RequireRole` shows an "Access denied" panel.
- `services/api.ts` extends `getJson`/`postJson` with `credentials:
  'include'` and an `X-CSRF-Token` header sourced from `/auth/csrf`.
  All errors throw `ApiError` so forms can render `error.field`.
- `pages/LandingPage.tsx` uses the same orange + JetBrains Mono tokens
  as the dashboard, with a `LiveWasteCounter` that ticks up while the
  user reads — same metric the dashboard surfaces, so the funnel feels
  coherent.
- `pages/settings/*` covers Account (change password, resend
  verification), Team (members, invites, audit log for owners),
  Workspaces (org switcher), and Sessions (per-device revoke + sign
  out everywhere).

## Backend architecture (post-refactor)

The backend follows a **state-source seam** so the simulation and (future) live-CV mode share the entire analytics + optimization + API surface. Every consumer depends only on the `SiteStateSource` Protocol, not on `SimulationEngine`. Long-lived objects live on `app.state` and are injected via FastAPI `Depends` — no module-level globals.

```mermaid
flowchart LR
    subgraph sources [State sources]
        Sim[SimulationEngine]
        Live[LiveSource - future]
    end
    Source[SiteStateSource Protocol]
    Sim --> Source
    Live -.-> Source

    Source --> Analytics
    Source --> Optimization
    Source --> Detail[asset_detail.py]
    Source --> WS[/ws/]
    Source --> REST[REST routes]
```

## Backend modules

### `config.py`
Domain constants only (rates, intervals, sim-clock parameters). Operational knobs live in `settings.py` instead.
Key tunables: `TOILET_INTERVAL` (7200s = 2h), `MATERIAL_RUN_INTERVAL` (7200s), equipment hourly rates (€180/120/90 for crane/pump/excavator), `SIM_SECONDS_PER_TICK` (30 — each 100ms real tick = 30s sim time at 1× speed).

### `settings.py`
`Settings` (pydantic-settings `BaseSettings`) with `SITEIQ_*` env-var overrides. Beyond CORS / log / YOLO knobs the auth-era fields are: `env` (`dev|prod|test`), `database_url`, `frontend_origin`, `session_secret`, `session_cookie_name`, `session_lifetime_days`, `session_idle_days`, `cookie_domain`, `cookie_secure`, `email_provider` (`console|resend`), `resend_api_key`, `email_from`, `rate_limit_redis_url`. Convenience properties: `is_prod`, `is_dev`, `effective_cookie_secure` (defaults to `True` in prod, `False` in dev). Documented in `backend/.env.example`.

### `logging_config.py`
`configure(level, fmt)` installs one stream handler on the root logger. `fmt="json"` swaps in `python-json-logger`'s `JsonFormatter`. Idempotent — safe to call repeatedly. Every backend module uses `logging.getLogger(__name__)`. Zero `print(...)` calls; zero bare `except Exception: pass` (guardrail tests in `test_logging.py`).

### `state/`
- **`source.py`** — `SiteStateSource` Protocol (`@runtime_checkable`). Surface: `project_id`, `sim_time`, `sim_day`, `site`, `assets`, `asset_by_id`, `zone_by_id`, `workers_in_zone`, `worker_internals_for`, `activity_log_for`, `position_history_for`. Both `SimulationEngine` and (future) `LiveSource` implement this.

### `models/`
Pydantic v2 schemas. `Site` has zones + schedule. `Asset` has position, state, metadata. `WasteSummary` aggregates costs. `Recommendation.from_position` / `to_position` use the typed `PositionXY` model.

`Asset.to_broadcast_dict()` produces the compact WebSocket payload — flat dict with id, type, subtype, x, y, state, assigned_zone.

### `simulation/`
- **`site_factory.py`** — `PROJECT_TEMPLATES` dict with 3 German construction projects (residential Berlin, commercial Frankfurt, infrastructure Munich). Each defines zones, facilities, equipment, materials, schedule, and worker counts. `create_site_from_template(project_id)` instantiates a full simulation state. Returns `(Site, list[Asset], dict[str, WorkerInternals])`.

- **`engine.py`** (~140 LOC, down from 243) — `SimulationEngine` implements `SiteStateSource`. Owns `assets`, `site`, `worker_internals`, `position_history`, `activity_log`, plus three O(1) indexes (`_by_id`, `_facilities_by_subtype`, `_workers_by_zone`) rebuilt on every project switch via `rebuild_indexes()`. `tick()` advances the FSM; `get_state_snapshot()` produces the WS broadcast payload. `load_project()` hot-swaps + re-indexes.

- **`worker_internals.py`** — `@dataclass WorkerInternals` typed state per worker (FSM timers, dwell counters, daily-reset stats). Replaces the old `dict[str, Any]` access. `reset_daily()` clears day-level counters.

- **`worker_behavior.py`** — Worker FSM with dispatch table: `STATE_HANDLERS: dict[WorkerState, StateHandler]` maps each state to a single-purpose `_on_*` handler (`_on_working`, `_on_walking_to_toilet`, `_on_at_toilet`, `_on_walking_to_material`, `_on_carrying_material`, `_on_walking_to_break`, `_on_at_break`, `_on_walking_to_work`). Adding a state means: write a handler + add one line. Uses engine's indexed lookups via the local `_WorkerEngine` Protocol (`facilities_by_subtype`, `materials`). Strict-mypy clean.

- **`equipment_behavior.py`** — Alternates OPERATING ↔ IDLE on duty cycles (crane 40/30min, pump 10/40min, excavator 42/18min). Tracks hours_active/hours_idle.

- **`asset_detail.py`** — `asset_detail(source, asset_id)` builds the rich per-asset detail view. Dispatch table `DETAIL_BUILDERS` routes by `asset.type` to `_worker_detail` / `_equipment_detail` / `_facility_detail` / `_material_detail`. Per-type radius + state tables for facility occupancy. Replaces the old 130-LOC `engine.get_asset_detail()` god-method.

### `analytics/`
All take `source: SiteStateSource`, not the engine.
- **`travel.py`** — `compute_travel_metrics(source)`. Per-zone metrics: avg toilet round-trip, trips/day, daily walk cost (trips × RT × hourly_rate), productivity rate. Extrapolates partial-day data via `day_fraction`.
- **`utilization.py`** — `compute_equipment_utilization(source)`. Per-equipment: utilization rate, daily idle cost (normalized to 11h workday × idle_fraction × rate).
- **`aggregator.py`** — `compute_waste_summary(source)`. Combines travel + equipment into `WasteSummary` with daily and monthly totals.

### `optimization/`
All take `source: SiteStateSource`.
- **`facility_placement.py`** — Weighted k-means (k=2) on zone centers; greedy-nearest pairing assigns toilets to centroids.
- **`material_staging.py`** — Picks the zone edge closest to the material's current position to preserve gate-side logistics flow.
- **`equipment_schedule.py`** — Flags equipment <40% utilization for release, <60% for rescheduling. Daily idle hours = `(1 - utilization) × 11h` — stable from t=0.

### `services/`
- **`recommendation_service.py`** — `RecommendationService(source, optimizers=…)`. Owns the recommendation cache; tracks the project id of the cached set and auto-invalidates on mismatch. `get()`, `clear()`, `mark_dirty()`, `by_id()`. Constructed once per app at lifespan startup, injected via `Depends(get_rec_service)`.

### `api/`
- **`deps.py`** — FastAPI dependency providers. Domain: `get_source`, `get_rec_service`, `get_detector`, `get_analytics`, `get_settings`, `get_email_sender` (all 503 if `app.state` isn't ready). Auth: `get_optional_session`, `get_current_session`, `get_current_user`, `get_current_org`, `get_current_membership`, `require_role(min: Role)` (closure-style Depends, returns 403 below threshold).
- **`routes.py`** — REST routes, all wrapped in `Depends(get_current_org)`. GET `/api/projects`, `/api/portfolio`, `/api/site`, `/api/recommendations`, `/api/assets/{id}`, `/api/simulation/state`, `/api/simulation/heatmap`. POST `/api/projects/{id}/load`, `/api/recommendations/{id}/apply`, `/api/recommendations/apply-all`, `/api/simulation/speed`, `/api/simulation/pause`. Sim-only controls return 501 if the source isn't a `SimulationEngine`.
- **`websocket.py`** — WS `/ws` streams `state_update` at 10Hz (assets + trails + latest analytics). Auth: cookie + origin checked at upgrade via `api/ws_auth.py`.
- **`camera.py`** — GET `/api/cameras` lists video feeds. WS `/ws/camera/{video_id}` streams YOLO-processed frames at ~5Hz via `asyncio.to_thread()` so inference doesn't stall the event loop. Same cookie + origin check as `/ws`.
- **`ws_auth.py`** — `authenticate_ws(websocket)`: rejects unknown Origins with close code 4403, missing/invalid session with 4401. Shared by both WebSocket endpoints.
- **`dev.py`** — `/dev/outbox` (mounted only when `env=dev`). Lists the most recent 100 emails for inspection during development; matching `/dev/outbox/{id}/html` serves the rendered email body.

### `vision/`
- **`detector.py`** — `VideoDetector` wraps YOLOv8n. Loads all .mp4 from `vision/videos/`, reads frames with OpenCV, runs inference (conf=0.20), returns base64 JPEG + normalized bounding boxes. CLASS_REMAP maps COCO classes to construction labels ("person" → "Worker"). ~18ms inference per frame on Apple Silicon.

### `main.py`
Thin composition root. `create_app(settings=None)` builds an isolated FastAPI app (tests can pass custom settings). Lifespan handler constructs the async DB engine + session factory, the `EmailSender` (Console or Resend), the slowapi limiter, the `SimulationEngine`, the `RecommendationService` and the `VideoDetector` — all attached to `app.state`. Then spawns `run_simulation_loop` + `_run_analytics_loop`. Middleware order: CORS → CSRF (double-submit cookie + Origin allow-list, exempts `/auth/csrf` + `/ws/*`) → routers (`/auth`, `/api/orgs`, `/api`, `/ws`, `/ws/camera`, plus `/dev/*` only in dev). A custom exception handler converts `HTTPException` and `RequestValidationError` into the standard `{error: {code, message, field?}}` envelope. No module-level globals.

## Test suite

| Suite | File | Count | Covers |
|---|---|---|---|
| Bug regressions | `tests/test_bug_fixes.py` | 19 | Bugs #1, #11, #12, #16-#28 |
| HTTP API | `tests/test_api.py` | 9 | All REST endpoints via TestClient (with auth fixture) |
| Async / YOLO offload | `tests/test_event_loop.py` | 2 | Bug #2 |
| Edge cases | `tests/test_edge_cases.py` | 14 | Long sim, project flipping, etc. |
| `SiteStateSource` Protocol | `tests/test_state_source.py` | 9 | Consumers depend only on Protocol |
| DI | `tests/test_di.py` | 5 | No module globals, `app.state` isolated per app |
| `WorkerInternals` dataclass | `tests/test_worker_internals.py` | 7 | Typed state contract |
| `asset_detail` builders | `tests/test_asset_detail.py` | 16 | Per-builder behavior + engine LOC budget |
| Worker FSM dispatch | `tests/test_worker_fsm.py` | 15 | Each state handler in isolation |
| Engine index perf | `tests/test_engine_perf.py` | 6 | O(1) lookups, project-switch invalidation |
| `Settings` | `tests/test_settings.py` | 8 | Env overrides, validation |
| Logging | `tests/test_logging.py` | 7 | No prints, no bare excepts, structured fields |
| Heatmap | `tests/test_heatmap.py` | 7 | Density grid + sparse encoding |
| DB engine + migrations | `tests/test_db.py` | 3 | URL switching, Alembic upgrade clean on SQLite |
| argon2 passwords | `tests/test_auth_passwords.py` | 4 | Round-trip, bad-password rejection, salt uniqueness |
| `/auth/*` routes | `tests/test_auth_routes.py` | 11 | Signup/login/logout, CSRF, verify, reset, sessions |
| `/api/orgs/*` routes | `tests/test_orgs.py` | 7 | Auto-org-on-signup, invites, role gating, audit |
| `EmailSender` | `tests/test_email_sender.py` | 4 | Console outbox + Resend httpx_mock + 5xx |
| AuthZ | `tests/test_authz.py` | 3 | 401 without cookie, role gates 403 |
| Rate limits | `tests/test_rate_limit.py` | 3 | 429 after burst on /auth/login, signup, forgot-password |
| Security headers | `tests/test_security_headers.py` | 3 | Baseline headers + dev-no-HSTS + prod-HSTS |
| Outbox cleanup | `tests/test_outbox_cleanup.py` | 2 | Old rows deleted, retention=0 disables |
| Account + org deletion | `tests/test_deletion.py` | 6 | Password gate, last-owner cascade, name-mismatch confirm |
| Per-org simulation | `tests/test_per_org_engine.py` | 2 | Two orgs see independent sites; deletion discards engine |
| Health + version | `tests/test_health.py` | 5 | /healthz; /readyz green/red on DB; /api/version shape + env override |
| Magic-link login | `tests/test_magic_link.py` | 4 | Silent-on-unknown, single-use, replay rejected, round-trip |
| Audit CSV export | `tests/test_audit_export.py` | 3 | Owner can download, admin gated, bad timestamp 400 |
| Auth GC | `tests/test_auth_cleanup.py` | 3 | Old revoked sessions + consumed tokens dropped; live ones kept |
| Active project persistence | `tests/test_active_project_persistence.py` | 1 | orgs.active_project_id survives a registry reset |
| Request-Id middleware | `tests/test_request_id.py` | 4 | Echoed, generated when absent, distinct per request, in error envelope |
| **Total backend** | | **192** | |
| Frontend | `frontend/src/**/*.test.{ts,tsx}` | 52 | Sim canvas + auth (AuthProvider, RequireAuth), api.ts |
| **Total** | | **244** | |

Mypy strict scoped to `simulation/worker_internals.py`, `simulation/worker_behavior.py`, `state/source.py` — clean.

`tests/conftest.py` exposes:
- `engine` / `frankfurt_engine` / `munich_engine` — fresh `SimulationEngine` instances.
- `app_settings` — `Settings` pointing at a per-test SQLite file with `env=dev`.
- `app_factory` / `client` — applies migrations, swaps in the no-op detector + `cheap_hasher` for argon2, builds a `TestClient`.
- `auth_client` — `client` with a real signed-up user + session cookie + CSRF header preset; the standard fixture for auth-gated routes.
- `authenticate(client)` / `setup_test_db(url)` — helpers for tests that build their own app variants (e.g. `test_di`, `test_settings`).

## Frontend modules

### State management
- `App.tsx` is now a `BrowserRouter`. The simulation app body lives in `pages/Dashboard.tsx`, mounted at `/app` behind `<RequireAuth>`.
- `lib/auth/AuthProvider` — context that boots via `GET /auth/me`, exposes `useAuth()` (`status`, `user`, `org`, `memberships`, `refresh`, `setMe`) everywhere. `RequireAuth` redirects to `/login?next=…`; `RequireRole` shows an "Access denied" panel if below threshold.
- `useWebSocket` — connects to `${WS_BASE}/ws`, stores assets + trails in **refs** (not state) for canvas performance. Only analytics, simTime, simDay trigger React re-renders.
- `useSimulation` — fetches `/api/site` on mount. `reload()` re-fetches after project switch.
- `useAnalytics` — captures first analytics as baseline, computes savings delta. `resetBaseline()` clears on project switch.
- Recommendations fetched in `Dashboard.tsx` via useEffect + 5s polling (not inside the Optimize tab component). The dashboard also resets selection / recs / baseline whenever the active org id changes.

### Canvas rendering (`renderer.ts`, 768 lines)
Module-level coordinate helpers `px()`, `py()`, `ps()` set from scale/offset each frame. Draws in order: ground → roads → fence → zone structures (phase-specific: excavation contours, foundation grids, structural columns, MEP conduit routes, finishes partitions) → heatmap → trails → materials → facilities → equipment → workers → recommendation arrows → selection highlight → scale bar → legend.

Workers rendered as emoji (👷) with trade-colored dot underneath. Equipment as emoji (🏗️🚛🚜) with status ring and ACTIVE/IDLE label. Facilities as emoji (🚻☕🏢🔧) on background plates. Materials as emoji (🪨🔌🧱🪣).

Selection: pulsing orange ring + tooltip with asset ID. Selected worker's trail at full opacity, others dimmed to 4%.

### `CameraFeed.tsx`
Connects to `ws://localhost:8000/ws/camera/{videoId}`. Receives base64 JPEG + detection data. Renders video frame on canvas, overlays bounding boxes with corner brackets, class labels, confidence %, inference time, detection count HUD. Shows "● REC" indicator and "YOLOv8 · SiteIQ Vision" badge.

### `SiteMap.tsx`
Canvas container with pan (drag), zoom (scroll wheel), reset (double-click). Click detection: converts screen coords → site meters via scale/offset/zoom/pan back-projection, finds nearest asset within hit radius, sets selectedAssetId. Cursor changes to pointer on hover over assets. Toggle bar: Trails, Heatmap, Show Fixes, Cameras.

### Right panel
Tabbed: Waste / Optimize / Timeline. Asset detail replaces tabs when an asset is selected.

- **WasteReport** — Red "RECOVERABLE WASTE" hero with monthly + daily framing. ROI card (system cost €2K/mo vs savings, payback ratio). "Included at no extra cost" card showing BauWatch/PPE/Buildots replacements. Three expandable cost rows with zone/equipment breakdowns. Green CTA "Apply optimizations — recover €X/mo" links to Optimize tab.

- **Recommendations** — "Available Savings" banner with monthly + annual total. "Apply All N Optimizations" button with spinner state. Individual recommendation cards with Apply buttons. Post-apply celebration card with annual savings. Applied list at bottom.

- **Timeline** — Gantt chart from schedule data. Hardcoded lookahead text (not driven by simulation — known limitation).

- **AssetDetail** — Worker: productivity bar (work/walk/facility split), distance, trips, round-trip times. Equipment: utilization gauge, duty cycle progress. Facility: workers present list. Material: target zone + distance. Activity log with sim-clock timestamps.

### `Portfolio.tsx`
Full-screen view showing all 3 project templates. Summary cards (sites, workers, equipment, waste). Portfolio ROI banner. Per-site cards with Open Site button that triggers project switch.

## Design system
Light theme using HSL CSS custom properties (shadcn-style tokens). Primary = orange (24 80% 50%), destructive = red, success = green, warning = amber. Inter for UI, JetBrains Mono for numbers. All monetary values use `tabular-nums` for stable width.

## Known issues and debt

Bugs 1–32 below were all identified during the original audit and have been
fixed in the working tree. Each entry retains its original description and now
ends with a `→ Fix:` note describing what was actually changed. Architectural
debt items 33–38 remain open.

### Bugs (verified by reading every route handler and data flow)

1. **Recommendation cache not cleared on project switch.** `routes.py:load_project()` clears `_recommendations_cache` (a dead module-level var in routes.py, line 8) but the real cache is `cached_recommendations` in `main.py`. The `recs_dirty` flag only flips on the next analytics tick (~1s later). Between project load and that tick, stale recs from the old project can be served.
   → Fix: `main.py` exposes `clear_recommendations_cache()`, passed into `init_routes`. `routes.load_project` calls it on switch. `get_recommendations()` also re-checks `engine.project_id` against a cached `cached_project_id` and forces a refresh on mismatch. The dead `_recommendations_cache` var in `routes.py` is removed.

2. **YOLO inference blocks the async event loop.** `camera.py` line 36 calls `_detector.get_next_frame()` synchronously (~18ms of OpenCV + YOLO per frame, per connected camera). During inference, the entire FastAPI event loop stalls — sim WebSocket pushes, REST endpoints, everything.
   → Fix: `camera.py` now runs `_detector.get_next_frame` via `asyncio.to_thread()`, freeing the event loop during OpenCV/YOLO work.

3. **No fetch error handling in frontend.** Every function in `api.ts` does `fetch(url).then(r => r.json())` without checking `r.ok` or `r.status`. A backend 500 or network error returns `undefined` which propagates silently through the UI. Any transient failure (e.g., during project switch) can put components into broken states.
   → Fix: introduced shared `getJson<T>()` / `postJson()` helpers in `api.ts` that throw on non-2xx. All API functions go through them. Existing call sites already use `.catch()` so errors no longer silently produce `undefined`.

### Frontend bugs (verified by reading every component)

4. **`justAppliedAll` never resets in `Recommendations.tsx`.** Set to `true` on Apply All (line 27), never set back to `false`. The celebration card stays visible forever — survives rec refreshes and project switches. Only clears on full page reload.
   → Fix: replaced boolean state with a `celebrationSig` (the recommendation-set signature captured when Apply-All ran). The card is visible only while the current recsSignature still matches, so a project switch or new rec set auto-hides it. A timer also auto-clears it after 8 s.

5. **Three hardcoded `localhost:8000` URLs outside `api.ts`.** `useWebSocket.ts` line 28, `CameraFeed.tsx`, `SiteMap.tsx` line 32.
   → Fix: `api.ts` exports `API_BASE` and `WS_BASE`. `useWebSocket.ts`, `CameraFeed.tsx`, and `SiteMap.tsx` (now via a new `fetchCameras()` helper) all import them. Single source of truth.

6. **WebSocket reconnect can create duplicate connections.** `useWebSocket.ts` line 26 checks `readyState === OPEN` but a WS in `CONNECTING` state (0) passes the guard.
   → Fix: guard now skips when an existing socket is OPEN *or* CONNECTING.

7. **`handlePortfolioSelect` in `App.tsx` ignores its `projectId` parameter.**
   → Fix: parameter removed from the implementation (TypeScript allows fewer params than the prop signature). A comment explains why: `Portfolio.tsx` calls `loadProject(id)` before invoking the callback.

8. **Portfolio ROI uses hardcoded 0.65 recovery factor.**
   → Fix: extracted to a named constant `RECOVERABLE_WASTE_FRACTION = 0.55` (centered on the doc'd 40–65% post-apply reduction range) plus `SYSTEM_COST_PER_SITE = 2000`. Computation flows from those.

### Renderer bugs (`renderer.ts`)

9. **`ctx.measureText` before `ctx.font` in zone labels.**
   → Fix: reordered — `ctx.font` set first, then `measureText`. Label backgrounds now size correctly.

10. **Module-level mutable state (`S`, `OX`, `OY`).** Would break if two canvases rendered simultaneously.
    → Mitigated: full refactor would touch 68 call sites; instead documented the invariant (synchronous render, single-threaded JS, reset at the top of every `renderFrame`). Listed in code comments with the explicit instruction to pass transform state explicitly if a second renderer instance is ever added. The bug is dormant in current architecture.

### Simulation logic bugs

11. **Worker gets permanently stuck if no facility exists.** Timer stays negative forever.
    → Fix: when `_find_nearest` returns `None`, the timer is now re-jittered to a fresh positive value before returning. The worker no longer pins on an unresolvable check every tick.

12. **k-means toilet assignment is order-based, not distance-based.**
    → Fix: toilets are now greedily paired to their *nearest* cluster centroid; sort+nearest-pair pass replaces `enumerate(toilets)`.

### Timeline bugs

13. **Timeline hardcodes zone IDs and TOTAL_DAYS=120.**
    → Fix: `Timeline.tsx` now takes `zones` as a prop and derives the zone list (preserves real labels like "Turm Ost"). `TOTAL_DAYS` is computed from `max(schedule.end_day, currentDay + 5, 120)`, so the Munich bridge (day 210) and any future longer schedule render correctly. Day markers are rebuilt for the actual span. `App.tsx`/`RightPanel.tsx` plumb zones through.

### Additional frontend issues

14. **CameraFeed RAF loop restarts 5x/sec.** `useEffect` deps include `detectionCount` and `inferenceMs`.
    → Fix: stats moved into refs (`detectionCountRef`, `inferenceMsRef`); deps reduced to `[connected, label]`. The RAF loop now mounts once.

15. **CameraFeed has no WebSocket reconnection.**
    → Fix: added the same exponential-backoff reconnect loop used in `useWebSocket` (1 s → 10 s cap), with cancellation on unmount.

16. **AssetDetail zone name is reformatted ID, not actual label.**
    → Fix: backend `engine.get_asset_detail()` now emits `assigned_zone_label` and `needed_in_zone_label`. Frontend prefers the label, falls back to the ID.

17. **MaterialDetail zone name regex doesn't capitalize zone letter.**
    → Fix: superseded by #16 — uses real `needed_in_zone_label` from the backend instead of regex-mangling the ID.

18. **EquipmentDetail duty cycle progress bar is wrong during idle.**
    → Fix: cycle denominator now switches between `operate_duration_s` / `idle_duration_s` based on `data.state` (`operating` vs `idle`).

19. **`onMouseUp` doesn't restore cursor to `grab`.**
    → Fix: `onMouseUp` now resets `canvas.style.cursor = 'grab'` before handling the click.

20. **`onMouseMove` registered on both canvas AND window.**
    → Fix: dropped the canvas-level listener; kept only the window-level one (which already handles both hover and drag-while-outside-canvas).

21. **`AssetUpdate` type missing `assigned_zone`.**
    → Fix: added `assigned_zone?: string` to the interface.

22. **`formatCurrencyCompact` exported but never used.**
    → Fix: removed.

### Backend logic issues found on full read

23. **`equipment_schedule.py` `daily_idle_hours` formula is unstable.**
    → Fix: replaced `hours_idle * (11.0 / max(total, 0.1))` with `(1.0 - utilization) * WORKDAY_HOURS`. Stable from t=0.

24. **`equipment_schedule.py` hardcodes fallback zone "D".**
    → Fix: now resolves the actual zone label via `engine.get_zone_by_id`, falling back to "its current zone" when none is assigned.

25. **`material_staging.py` picks zone edge nearest to center, not to material.**
    → Fix: candidates are now scored by distance from the material's current position (the staging side closest to the existing logistics path), not by distance from the zone center.

26. **Facility detail only checks toilet/breakroom.**
    → Fix: per-subtype radius table + per-subtype required-state table. `office` and `toolcrib` now report any nearby worker (no required state).

27. **`EquipmentState.REPOSITIONING` defined but never used.**
    → Fix: removed.

28. **`Recommendation.from_position` and `to_position` are untyped `dict`.**
    → Fix: introduced `PositionXY` Pydantic model; both fields now use it. Route handler updated from `rec.to_position["x"]` → `rec.to_position.x`.

### Dead code (all removed)

29. ~~`CONSTRUCTION_CLASSES` dict in `detector.py`~~ — removed.
30. ~~`_recommendations_cache` in `routes.py`~~ — removed (see #1).
31. ~~`_find_nearest_facility` in `travel.py`~~ — removed.
32. ~~`MetricCard.tsx`~~ — file deleted.

### Architectural debt (still open)

33. **Camera feeds are disconnected from simulation** — the core coherence problem. See architecture section above. The `SiteStateSource` Protocol seam already supports a future `LiveSource` that would replace the simulation engine with calibrated YOLO detections projected onto the 2D map.
34. ~~**Per-org custom projects.**~~ Closed in the Editor + Multi-Level rebuild. See "Project editor + multi-level + Tiefbau" below.
35. **No 2FA UI yet.** The `users.totp_secret` column exists; the UI is intentionally hidden behind a future feature flag.
36. **No billing.** `orgs.plan` exists (`trial|pro|enterprise`) but Stripe integration is a separate plan.

## Project editor + multi-level + Tiefbau (Editor & Multi-Level rebuild)

Rebuild that introduces a canonical, content-addressed `ProjectDocument`,
first-class multi-level support, the Tiefbau discipline, an iso "exploded
floors" view, and a customer-facing drag-and-place project editor. Shipped
in ten phases (Phase 0–Phase 9); the architecture below is the post-rebuild
end state.

### Design principles

1. **One canonical document.** [backend/models/project_document.py](backend/models/project_document.py) defines a single `ProjectDocument` Pydantic model. It is the storage format, the API payload, the editor's state, and the simulation engine's input. The only transformation is `simulation.project_loader.build_engine_state(doc)` which materialises `(Site, list[Asset], dict[worker_id, WorkerInternals], list[Connection])`.
2. **Content-addressed immutable versions.** Every save writes a new `project_versions` row whose PK is `sha256(canonical_json(document))`. `projects.current_version_id` is a single mutable FK — atomic swap, no draft/publish state machine.
3. **Levels via discrete `level_id` + a connection graph.** Vertical transport is BFS on a tiny graph, not pathfinding in 3D space.
4. **The seam is sacred.** `SiteStateSource` Protocol stays the contract. Multi-level methods (`levels`, `level_by_id`, `workers_in_level`, `connections`, `connections_from_level`) are additive; single-level consumers see L0 everywhere and behave unchanged.
5. **Editor = thin reducer over the same Pydantic schema.** OCC via `If-Match: <version_id>`, no CRDTs.

### Canonical schema (Phase 0)

```python
class Discipline(str, Enum):
    HOCHBAU = "hochbau"      # above-ground building
    TIEFBAU = "tiefbau"      # civil / underground
    HYBRID  = "hybrid"

class Phase(str, Enum):
    EXCAVATION; SHORING; PILING; DRAINAGE      # Tiefbau additions
    FOUNDATION; STRUCTURAL; MEP_ROUGHIN
    CLOSEIN; FINISHES; PAVING; COMPLETE        # PAVING added

class Level(BaseModel):
    id: str           # "L0", "L-1", "L1"
    name: str         # "EG", "UG1", "1. OG"
    elevation_m: float
    order: int

class Position(BaseModel):
    x: float
    y: float
    level_id: str = "L0"   # default keeps existing data compatible

class Connection(BaseModel):
    id: str
    kind: Literal["stair", "elevator"]
    nodes: list[ConnectionNode]   # (level_id, x, y)
    cab_capacity: int = 6
    cycle_time_s: float = 60.0
    speed_m_per_s: float = 1.5
    seconds_per_level_climb: float = 20.0  # stairs only

class ProjectDocument(BaseModel):
    schema_version: int = 1
    slug, name, description, type, discipline
    width, height, start_day
    levels: list[Level]
    zones: list[Zone]              # carries level_id
    facilities: list[FacilitySpec] # carries level_id
    equipment: list[EquipmentSpec] # carries level_id
    materials: list[MaterialSpec]  # carries level_id
    connections: list[Connection]
    schedule: list[ScheduleEntry]
    worker_seeds: list[WorkerSeed] # per (zone_id, trade) → count

    def content_hash(self) -> str:
        return sha256(canonical_json(self)).hexdigest()
```

The 3 hardcoded templates were converted to JSON seed files under
`backend/seeds/projects/*.json` (Phase 0); the in-Python
`PROJECT_TEMPLATES` dict is now a thin lazy view that loads from disk.

### Persistence (Phase 1)

Alembic migration `0003_projects` adds:

- `projects(id, org_id, slug, name, description, type, discipline, visibility, status, current_version_id, ...)` — top-level row, `org_id=NULL` for public templates.
- `project_versions(id, project_id, parent_version_id, document JSONB, message, created_by_user_id, created_at)` — immutable. `id` is the SHA-256 content hash.
- `orgs.active_project_version_id` — pointer at the version the org's simulation runs on.

[backend/db/project_repository.py](backend/db/project_repository.py) is the only place that translates between `ProjectDocument` and DB rows. `save_version(project_id, doc, parent_version_id, ...)` raises `OptimisticLockError` if `parent_version_id` no longer matches the project's current pointer, which the router surfaces as a 409 `version_conflict`.

[backend/seeds/importer.py](backend/seeds/importer.py) imports every bundled seed as a public-template row at app startup. Idempotent via content hash: identical seeds dedupe; edited seeds bump the version.

[backend/state/registry.py](backend/state/registry.py)'s `for_org_at_version(org_id, document, version_id)` rebuilds an org's engine on version drift. The seed-slug path (`for_org`) still works for the dashboard's stock-project switcher.

### Project router (Phase 1)

All routes wrapped in `Depends(get_current_org)` + `require_role(Role.ADMIN)` for writes.

| Route | Method | Purpose |
|-------|--------|---------|
| `/api/projects` | GET | List org-owned + public-template projects |
| `/api/projects` | POST | Create new draft (returns full document) |
| `/api/projects/{id}` | GET | Full document, version id, visibility, ownership |
| `/api/projects/{id}` | PUT | Save new version. `If-Match: <version_id>` required for OCC. Validation errors surface as `400 {code, message, field}`. |
| `/api/projects/{id}` | DELETE | Soft via cascade |
| `/api/projects/{id}/activate` | POST | Pin org's simulation to this project/version |
| `/api/projects/{id}/validate` | POST | Dry-run validation; live editor feedback |

[backend/api/routes.py](backend/api/routes.py) also gained `/api/site/load-seed {slug}` (Phase 1) — the legacy slug-based load endpoint, kept for the dashboard's stock-project switcher.

Every mutating endpoint writes an `audit_events` row:
`project.created`, `project.updated`, `project.deleted`, `project.activated`.

### Multi-level simulation core (Phase 2)

[backend/simulation/engine.py](backend/simulation/engine.py) gained:

- `_facilities_by_subtype_level: dict[(subtype, level_id), list[Asset]]` — same-level toilet lookup is O(1).
- `_connections_by_level: dict[level_id, list[Connection]]` — fast BFS frontier.
- `_level_by_id` — Protocol-required lookup.
- `workers_in_level(level_id)` — computed on demand (workers move between levels mid-sim).

[backend/simulation/worker_behavior.py](backend/simulation/worker_behavior.py)'s `_find_nearest_facility` now takes an implicit `worker.position.level_id` filter: prefers a same-level facility, falls back to a cross-level one only when none exists on the worker's current floor.

### Cab-tracked vertical transport (Phase 3)

[backend/simulation/vertical_transport.py](backend/simulation/vertical_transport.py) implements one `CabState` per elevator `Connection`:

- `current_level_id`, `direction (+1/-1/0)`, `passengers: list[(worker_id, target_level_id)]`, `queue_per_level: dict[level_id, deque[worker_id]]`, `door_open_remaining_s`.
- `tick_cab(cab, dt_sim, on_alight, on_board)` advances the cab, dispatching:
  - `on_alight(worker_id, level_id)` when a passenger reaches their target.
  - `on_board(worker_id, level_id) -> target_level_id` when a queued worker enters.

Long sim ticks (the sim runs at up to 20× real-time, so a single tick can span seconds-of-elevator-time) loop through multiple floor stops so cab position stays consistent with worker movement.

Worker FSM additions:

- `WorkerState.WALKING_TO_VERTICAL` — walk to the stair/elevator anchor on the current level.
- `WorkerState.TRAVERSING_VERTICAL` — for stairs, count down `seconds_per_level_climb`; for elevators, sit in the queue / on the cab until the callback lands the worker on the destination level.
- `_begin_vertical_route(worker, internals, engine, final_destination)` — BFS over the connection graph; if the destination is on a different level, sets the FSM to WALKING_TO_VERTICAL and stashes the cross-level target on `WorkerInternals.cross_level_destination`.

`WorkerInternals` gained `target_level_id`, `cross_level_destination`, `vertical_connection_id`, `vertical_queue_enter_time`, `time_in_vertical_transport` (reset daily).

**Phase 3 microbench gate**: 6 cabs × 250 workers × 6 levels averages well under 5 ms/tick. Locked in [backend/tests/test_vertical_transport.py](backend/tests/test_vertical_transport.py)::`test_tick_under_5ms_with_six_cabs_and_workers`.

### Per-level analytics + vertical-transport optimizer (Phase 4)

[backend/analytics/vertical_metrics.py](backend/analytics/vertical_metrics.py)'s `compute_vertical_metrics(source)` returns:

- Per-worker accumulated `time_in_vertical_transport` extrapolated to a full day → `waste_daily` (in €).
- Per-cab snapshot: `queued_now`, `riding_now`, `saturation`, `longest_wait_s`.

`WasteSummary` gained `vertical_transport_daily` + `_monthly`. The WasteReport UI only renders the row when the value is > 0 (single-floor sites stay clean).

[backend/optimization/vertical_transport_optimizer.py](backend/optimization/vertical_transport_optimizer.py) fires on either:
- instantaneous saturation ≥ 60% or longest queue wait ≥ 60 s, **or**
- cumulative daily waste per cab ≥ €5/day.

Recommendation: "Add a second cab next to {connection_id}", estimated savings = avg_daily_per_cab / 2.

[backend/optimization/facility_placement.py](backend/optimization/facility_placement.py) now runs k-means **per level** — toilets can't physically move across floors, so each level's toilets cluster on that level's worker centroids only.

### Tiefbau as first-class (Phase 5)

[backend/simulation/tiefbau_behavior.py](backend/simulation/tiefbau_behavior.py):

- `update_tiefbau_equipment(asset, dt_sim, engine)` — dewatering pumps run 80% / 20% duty cycle; sheet piles stay permanently OPERATING.
- `compute_shoring_compliance(source)` — per-EXCAVATION-zone score: 1.0 if a sheet pile is within `SHORING_INFLUENCE_RADIUS_M = 25` of the zone's centre, 0.0 otherwise. Surfaces the "uncovered cut" moment for the demo.

New asset subtypes: `sheet_pile`, `dewatering_pump`. Engine dispatch in `_tick()` routes these subtypes to `update_tiefbau_equipment` instead of the standard `update_equipment`.

New seed: `backend/seeds/projects/munich-sewer.json` (Kanalsanierung Lindwurmstraße). 5 linear excavation segments, 5 sheet piles, 2 dewatering pumps, the new Tiefbau phases (`SHORING`, `EXCAVATION`, `DRAINAGE`, `PAVING`).

### Renderer multi-level (Phase 6)

[frontend/src/components/SiteMap/LevelSwitcher.tsx](frontend/src/components/SiteMap/LevelSwitcher.tsx) — vertical strip on the right of the canvas, top-to-bottom by `order` descending. Renders nothing on single-floor projects.

`SiteMap.tsx` now manages `activeLevel` state, filters zones (`zone.level_id === activeLevel`) and assets (`a.lvl === activeLevel`) before passing to `renderer.ts`. The runtime renderer itself is untouched — adding 768 LOC of branching to `renderer.ts` would have violated the "boring refactor" rule.

WebSocket payload: every asset broadcast dict carries `lvl` (the asset's current `position.level_id`). `/api/site` includes `levels`, `connections`, `discipline`.

### 2.5D iso exploded compositor (Phase 7)

[frontend/src/components/SiteMap/IsoRenderer.ts](frontend/src/components/SiteMap/IsoRenderer.ts) — separate compositor that renders each level to an `OffscreenCanvas` via the existing `renderFrame`, then stacks them at a 30°-ish isometric angle on the parent canvas.

- One `LevelSlab` per level, cached with a dirty-hash (per-level asset positions + render flags). Only redraws slabs that changed since the last frame.
- Single-floor sites short-circuit to the regular `renderFrame` — zero cost when iso is off.
- New "Iso View" toggle in the SiteMap toolbar, only visible on multi-level projects.
- `resetIsoSlabs()` clears the cache on project switch.

### Editor GUI (Phase 8)

Routes:

- `/app/projects` — list of org-owned + public-template projects, with "Edit / Activate / Duplicate" actions.
- `/app/projects/:id/edit` — the editor.

Components in `frontend/src/components/editor/`:

- `ToolPalette.tsx` — categorised tool buttons (Zone / Facility / Vertical / Equipment / Tiefbau).
- `LevelManager.tsx` — add/rename/remove levels; L0 is protected.
- `PropertiesPanel.tsx` — context-sensitive editor for the currently-selected zone / facility / equipment / material / connection. Worker seeds are edited inside the zone view.
- `EditorCanvas.tsx` — focused 2D drawing for the editor mode (separate from the runtime renderer). Click-to-select in select mode; click-to-place when a placement tool is active.
- `ValidationOverlay.tsx` — surfaces errors / warnings from `POST /api/projects/{id}/validate`.

State management via [frontend/src/hooks/useProjectDraft.ts](frontend/src/hooks/useProjectDraft.ts):

- `useReducer` over `{ current, past, future, savedVersionId }` for instant undo/redo.
- Autosave every 5 s if dirty, posting `PUT /api/projects/{id}` with `If-Match: <savedVersionId>`. Conflict → sets `conflict=true` (UI shows "⚠ conflict — reload").
- Debounced live validation (800 ms) → `setIssues`.

Activate from the editor header → `POST /api/projects/{id}/activate` → navigate back to the dashboard. The next `get_source` call detects the version drift and rebuilds the engine on the new document.

### Editor v2 (preview / Gantt / floorplan / grid)

Four post-Phase-8 features that were promised in the original 10-phase
plan and are now in. None mutate the existing seam — every change lives
in additive routes, new tables, or new components.

**Preview Run.** `POST /api/projects/{id}/preview` runs a transient
`SimulationEngine` against a draft document, ticks `ticks` times
(default 240 ≈ 2 sim-hours, max 1200), then returns the snapshot,
`compute_waste_summary` output, and the recommendation list — all in
one synchronous response. The transient engine is built outside
`SourceRegistry`, so the org's live simulation is never touched. Reject
documents whose `validate_document` returns any `severity="error"`
issue. Implementation in [backend/api/projects.py](backend/api/projects.py)
(`preview_project` handler, ~70 LOC) + [frontend/src/components/editor/PreviewRunPanel.tsx](frontend/src/components/editor/PreviewRunPanel.tsx)
(non-modal sidebar with daily/monthly waste + top 5 recommendations,
auto-dismisses when the draft document mutates).

**Snap-to-grid in the editor canvas.** [frontend/src/components/editor/EditorCanvas.tsx](frontend/src/components/editor/EditorCanvas.tsx)
gained a `gridSize` state (`0 | 1 | 5 | 10` meters; default 1 m,
persisted to `localStorage` under `siteiq.editor.grid_size`), a 4-pill
toolbar above the canvas, a dot-grid render at `gridSize`-meter spacing
(α=0.15, drawn under everything), and snap rounding on the
final committed position of every drag + every click-to-place. The 3 px
click→drag threshold and coarse-grain undo (one `patch` per drag) are
unchanged. `snapToGrid(value, gridSize)` is exported for tests.

**Gantt schedule editor.** Right-column tabs in the editor toggle
between "Properties" (default) and "Schedule". The schedule tab is
[frontend/src/components/editor/ScheduleEditor.tsx](frontend/src/components/editor/ScheduleEditor.tsx)
— one row per zone, ordered like `LevelManager`. Each row's track holds
`ProjectScheduleEntry` blocks coloured via `PHASE_COLORS`. Drag a block
horizontally → shifts `start_day` and `end_day` together; drag the left
handle → only `start_day`; drag the right handle → only `end_day`. Snap
is the 1-day grid (everything's rounded via `daysPerPx`). A "+ Phase"
button per row opens an inline picker (`start_day = currentMax + 1`,
`end_day = +30`). "×" / right-click deletes a block. One coarse-grain
`patch` per drag, on mouseup, so undo/redo + autosave keep working.
`PHASE_COLORS` + `PHASE_LABELS` in [frontend/src/utils/colors.ts](frontend/src/utils/colors.ts)
were extended with the four missing Tiefbau values (`SHORING`,
`PILING`, `DRAINAGE`, `PAVING`).

**Background floor-plan upload.** A new `project_assets` table (Alembic
`0004_project_assets`) stores binary blobs (`id`, `project_id` FK
cascade, `kind="level_background"`, `content_type`, `data` LargeBinary,
`content_hash` SHA-256). Routes live in
[backend/api/project_assets.py](backend/api/project_assets.py):
- `POST /api/projects/{id}/levels/{level_id}/background` — multipart
  upload. Accepts `image/png|jpeg|webp` only, capped at 2 MiB. Inserts
  the blob row + writes a NEW project version with `Level.background_image_url`
  set on the matching level. `If-Match` is honoured so OCC still works.
- `GET /api/projects/{id}/assets/{asset_id}` — serves the bytes with
  `Cache-Control: public, max-age=31536000, immutable` and the content
  hash as `ETag` (the body never changes for a given asset_id).
- `DELETE /api/projects/{id}/levels/{level_id}/background` — strips
  the url + drops the asset row in one transaction.

Frontend: [LevelManager.tsx](frontend/src/components/editor/LevelManager.tsx)
gained a per-row "📐" button → hidden `<input type="file" accept="image/*">`.
On select, the file uploads, the editor refetches the project, and the
draft applies the fresh detail via the new
`useProjectDraft.applyServerUpdate(detail)` callback (which clears
undo/redo because the new version is the new ground truth).

Render — `EditorCanvas.tsx` and `SiteMap.tsx` both grew a per-mount
image cache keyed by absolute URL. When the active level has a
`background_image_url`, the canvas calls `ctx.drawImage` once before
the dashed site bounds (editor) or before `renderFrame` (runtime).
`renderer.ts` stays untouched (Phase-6 lock-in rule); since it begins
its draw with an opaque `#f0ede8` full-canvas `fillRect` and a
`#d4c9a8` site-area `fillRect` inside `drawSiteGround`, the runtime
SiteMap path temporarily intercepts those two specific `ctx.fillRect`
calls (`fillStyle === '#f0ede8' || '#d4c9a8'`) so the floor plan
survives underneath the zones / workers / trails. The intercept is
restored before the cab overlay runs. The editor canvas hits the same
`ctx.drawImage` path but doesn't need the intercept (it owns its full
paint pipeline). On the editor side the grid dots also auto-step up
(1m → 2m → 4m → 8m) until they reach ≥ 6 CSS pixels of separation,
keeping the visual grid readable at small scales; the snap step
remains whatever the user picked.

Audit events emitted:
- `project.preview` — `{project_id, version_hash, ticks}`
- `project.background.uploaded` — `{project_id, level_id, asset_id, content_hash, to_version}`
- `project.background.deleted` — `{project_id, level_id, asset_id}`

New dependency: `python-multipart` (FastAPI's required parser for any
`multipart/form-data` route — there's no in-tree alternative without
writing a custom parser).

Closes audit items #8–#11 (Preview run, Gantt editor, background
upload, snap-to-grid) — the four "Promised editor features that don't
exist" subsection entries from the prior revision.

### API route → frontend mapping (post-rebuild additions)

| Backend route | Method | Frontend caller |
|--------------|--------|-----------------|
| `/api/projects` | GET | `ProjectListPage`, `TopBar` |
| `/api/projects` | POST | `ProjectListPage` (Create / Duplicate) |
| `/api/projects/{id}` | GET | `useProjectDraft` |
| `/api/projects/{id}` | PUT | `useProjectDraft` (autosave, `If-Match`) |
| `/api/projects/{id}` | DELETE | _no UI yet, exposed for completeness_ |
| `/api/projects/{id}/activate` | POST | `ProjectListPage`, `ProjectEditorPage` (header) |
| `/api/projects/{id}/validate` | POST | `useProjectDraft` (debounced) |
| `/api/projects/{id}/preview` | POST | `PreviewRunPanel` (Editor v2) |
| `/api/projects/{id}/levels/{level_id}/background` | POST | `LevelManager` (📐 button) |
| `/api/projects/{id}/levels/{level_id}/background` | DELETE | `LevelManager` (clr) |
| `/api/projects/{id}/assets/{asset_id}` | GET | `EditorCanvas` + `SiteMap` background draw |
| `/api/site/load-seed` | POST | `TopBar.handleProjectSelect` (legacy stock-project switcher) |

### Test budget (post-rebuild)

| Phase | Backend new tests | Frontend new tests |
|-------|---|---|
| Phase 0 schema | 13 | — |
| Phase 1 persistence | 10 | — |
| Phase 2 multi-level core | 9 | — |
| Phase 3 vertical transport | 7 | — |
| Phase 4 analytics + optimizer | 9 | — |
| Phase 5 Tiefbau | 9 | — |
| Phase 6 renderer levels | — | 5 (LevelSwitcher) |
| Phase 7 iso view | — | covered by Phase-8 editor tests |
| Phase 8 editor | — | 6 (ToolPalette, LevelManager) |
| Editor v2 preview | 8 | 5 (PreviewRunPanel) |
| Editor v2 snap-to-grid | — | 8 (EditorCanvas) |
| Editor v2 Gantt | — | 8 (ScheduleEditor) |
| Editor v2 floorplan | 9 | 3 (LevelManager) |
| **Totals before / after** | **192 → 284** | **52 → 99** |

End-to-end smoke verified via the browser MCP (auth → editor → preview
panel → snap pills → schedule drag → background upload → activate →
dashboard SiteMap renders the floor plan under the simulation overlay).

### Dashboard UX polish (post-handoff fixes)

A round of fixes after the first live walkthrough surfaced layout +
readability bugs that the unit tests didn't catch:

- `TopBar.tsx` — the three-column flexbox previously let the left
  cluster (logo / Portfolio / Projects / Settings) grow into the
  centred sim clock, wrapping "7:24 AM" to two lines and visually
  stacking the Settings button on top of it. Each cluster now uses
  `shrink-0` + `whitespace-nowrap`, the centre group has `min-w-0`
  + nowrap, and the right cluster's project-name button truncates
  rather than pushing the clock out.
- `SiteMap/LevelSwitcher.tsx` — moved from `top-2 right-2` to
  `top-2 left-2`. Renderer paints its trade / Active / Idle legend
  in the top-right corner, so a right-aligned switcher visibly
  overlapped that legend.
- `components/common/ToastContainer.tsx` — each tone used to apply
  `bg-card` + `bg-X/5`, and because Tailwind orders the later class
  last, the 5%-alpha tint clobbered the card background, leaving the
  toast looking transparent / "unstyled" against the canvas. We now
  keep `bg-card` as the substrate (solid white in light mode) and
  convey the tone via the border (`border-X/40`) and the icon chip
  (`bg-X/15`) only.
- `SiteMap/renderer.ts` — three targeted additions:
  1. Zone labels were drawn during `drawZoneStructures` (early in the
     pipeline), so equipment markers placed near a zone's top-left
     corner painted on top of the label pill. Extracted to
     `drawZoneLabels`, called as the very last asset-layer step so
     the pill always sits on top, and the pill background is now
     fully opaque (was 85%-alpha so equipment bled through).
  2. `drawEquipmentTopDown` previously drew every label without
     overlap detection — Munich's 4 sheet piles + 2 dewatering pumps
     + crane (~200 m strip) all stacked their `sheet_pile ACTIVE`
     labels. Added a per-call painted-rectangle list; new labels are
     skipped if they would overlap an existing one. Same dodge for
     `drawMaterialStacks` and the recommendation cost chips inside
     `drawRecommendationArrows`. Also extended the `LABELS` table
     with friendly names for `sheet_pile` ("SHORING") and
     `dewatering_pump` ("PUMP") instead of falling back to the raw
     subtype string.

These changes raise `renderer.ts` from ~768 LOC to ~970 LOC; the
Phase-6 lock-in rule that kept it untouched during the editor build
is now relaxed for documented bug fixes (label overlap is a real UX
defect, not a feature addition).

Microbench gates locked in:

- `test_tick_under_5ms_at_full_load` (Phase 0) — 50 ticks of `isar-bridge` average < 5 ms.
- `test_tick_under_5ms_with_six_cabs_and_workers` (Phase 3) — 6 cabs × 250 workers stays in the same budget.

### Closed debt (Editor & Multi-Level rebuild)

- ~~Per-org custom projects (debt #34)~~ — `org_projects` is now `projects` + immutable `project_versions`. Editor lets owners + admins build their own sites end-to-end.
- ~~Tiefbau wasn't a first-class discipline~~ — `Discipline` enum, expanded `Phase`, sheet-pile + dewatering-pump subtypes, slope-stability KPI, Munich seed.
- ~~Single-floor assumption baked into every layer~~ — `Level` + `Position.level_id` + per-level indexes + vertical-transport FSM + per-level optimizers + level-switching renderer + iso exploded view.
- ~~Promised editor features that don't exist (#8–#11)~~ — Preview Run, Gantt schedule editor, background floor-plan upload, snap-to-grid. See "Editor v2" subsection above.

### Resolved in 2026-06-21

- ~~**CORS hardcoded** to localhost:5173/5174~~ — `SITEIQ_CORS_ORIGINS` (comma-separated env var) drives the allow-list.
- ~~**No tests** — empty `tests/__init__.py`~~ — backend is at 172 tests across 22 suites, frontend at 52.
- ~~**No auth, no persistence, no database**~~ — full self-hosted auth + SQLAlchemy/Alembic/SQLite-or-Postgres + audit log. See "Auth, orgs, and persistence" above.
- ~~**Per-org engines deferred**~~ — `state/registry.py` keys engines by org_id, lazy creation, `Depends(get_source)` resolves through the active org.
- ~~**No account / workspace deletion UI**~~ — `POST /auth/delete-account` + `DELETE /api/orgs/current`, both with password confirmation; UI under Settings → Account / Team danger zones.
- ~~**Timeline lookahead hardcoded**~~ — `Timeline.tsx` now derives the next 30 days of phase transitions from the schedule + currentDay.
- ~~**Portfolio waste from a fixed formula**~~ — `services/portfolio_estimator.py` warms each project template at startup and caches the real `compute_waste_summary` output.
- ~~**No prod deployment story**~~ — `backend/Dockerfile` (multi-stage uv), `frontend/Dockerfile` (Vite → nginx), `docker-compose.yml` with Postgres. `docker compose up --build` is now the prod-shaped local stack.
- ~~**No security headers**~~ — `api/security_headers.py` adds CSP, X-Frame, Referrer-Policy, Permissions-Policy, X-CTO; HSTS in prod.
- ~~**No rate limits**~~ — slowapi on `/auth/login` (10/min), `/auth/signup` + `/auth/forgot-password` (5/hr), Redis-ready storage.
- ~~**No password breach check**~~ — HIBP k-anonymity in `PasswordField` (only first 5 hex of SHA-1 leaves the browser).
- ~~**Email outbox grew forever**~~ — periodic cleanup task with configurable TTL.
- ~~**No health endpoints**~~ — `/healthz` + `/readyz` (DB ping + registry check); Dockerfile healthcheck switched to `/readyz`.
- ~~**Frontend was a single 434 KB bundle**~~ — `React.lazy` route splits; entry chunk down to 243 KB, individual pages 1–8 KB.
- ~~**Silent UI errors took down the whole app**~~ — top-level `ErrorBoundary` shows a recovery card with the stack and a Reload button.
- ~~**WS drops were silently shown as a colored pill**~~ — `useConnectionToast` shows "Reconnecting…" / "Live again" after a grace window.
- ~~**Password-only login**~~ — magic-link via `/auth/request-magic-link` + `/auth/login-with-token`, 15-min single-use tokens.
- ~~**No audit log export**~~ — `GET /api/orgs/current/audit.csv` with `since` / `until` query params (RFC 4180, owner-only).
- ~~**Auth tables grew forever**~~ — `auth/auth_cleanup.py` periodic task drops fully-revoked sessions + consumed tokens past their retention window.
- ~~**Backend restart reset every org's project to default**~~ — `orgs.active_project_id` (migration 0002) persists each org's choice.
- ~~**No request tracing**~~ — request-id middleware + structured logging filter; envelope carries `request_id` for support.
- ~~**Password meter chunk was 1.2 MB**~~ — direct-import only `commonWords + firstnames + wordSequences + adjacencyGraphs`. Net ~750 KB saved on the password-field lazy load.
- ~~**No version endpoint**~~ — `/api/version` returns commit + build time; surfaced in the SettingsLayout footer.

### API route → frontend mapping (verified)

Every `/api/*` route below is wrapped in `Depends(get_current_org)` and
returns the standard `{error: {code, message, field?}}` envelope on failure.
Mutating requests carry `credentials: 'include'` + `X-CSRF-Token`.

**Auth**

| Backend route | Method | Frontend caller | Notes |
|--------------|--------|----------------|-------|
| `/auth/csrf` | GET | `services/api.ts` (auto) | Sets `siteiq_csrf` cookie + returns body token; cached client-side |
| `/auth/me` | GET | `AuthProvider` boot | Returns `{user, org, memberships}` — `null`s when anonymous |
| `/auth/signup` | POST | `SignupPage` | Creates user + org (owner) + session; sends verification email |
| `/auth/login` | POST | `LoginPage` | Returns `MeResponse` and sets session cookie |
| `/auth/logout` | POST | `SettingsLayout` | Revokes the active session, clears cookie + CSRF cache |
| `/auth/forgot-password` | POST | `ForgotPasswordPage` | Always 200 — never reveals whether the email exists |
| `/auth/reset-password` | POST | `ResetPasswordPage` | Consumes single-use token, revokes all sessions, issues a fresh one |
| `/auth/verify-email` | POST | `VerifyEmailPage` | Single-use token, 24h TTL |
| `/auth/resend-verification` | POST | `AccountSettings` | No-op if already verified |
| `/auth/change-password` | POST | `AccountSettings` | Revokes every other session for the user |
| `/auth/sessions` | GET | `Sessions` | Live (non-revoked, non-expired) sessions for the current user |
| `/auth/sessions/{id}/revoke` | POST | `Sessions` | Per-device revoke |
| `/auth/sessions/revoke-all` | POST | `Sessions` | Sign out everywhere; reissues current cookie |

**Orgs**

| Backend route | Method | Frontend caller | Notes |
|--------------|--------|----------------|-------|
| `/api/orgs` | GET | `OrgSwitcher` | All memberships for current user |
| `/api/orgs/switch` | POST | `OrgSwitcher`, `AcceptInvitePage` | Sets `auth_sessions.current_org_id` |
| `/api/orgs/current/members` | GET | `TeamSettings` | member+ |
| `/api/orgs/current/invites` | GET | `TeamSettings` | admin+ |
| `/api/orgs/current/invites` | POST | `TeamSettings` | admin+; sends invite email |
| `/api/orgs/accept-invite` | POST | `AcceptInvitePage` | Token + email-match check |
| `/api/orgs/current/members/{user_id}` | PATCH | `TeamSettings` | admin+; only owners can touch owner roles |
| `/api/orgs/current/members/{user_id}` | DELETE | `TeamSettings` | admin+ |
| `/api/orgs/current/leave` | POST | `Settings` (future) | Last-owner protection |
| `/api/orgs/current/audit` | GET | `TeamSettings` | owner only |

**Simulation (gated by current org)**

| Backend route | Method | Frontend caller | Notes |
|--------------|--------|----------------|-------|
| `/api/projects` | GET | `TopBar.tsx` via `fetchProjects()` | On mount |
| `/api/projects/{id}/load` | POST | `TopBar.tsx` via `loadProject()` | On project switch |
| `/api/portfolio` | GET | `Portfolio.tsx` via `fetchPortfolio()` | On mount |
| `/api/site` | GET | `useSimulation.ts` via `fetchSite()` | On mount + reload |
| `/api/recommendations` | GET | `Dashboard.tsx` via `fetchRecommendations()` | 5s polling |
| `/api/recommendations/{id}/apply` | POST | `Recommendations.tsx` via `applyRecommendation()` | On click |
| `/api/recommendations/apply-all` | POST | `Recommendations.tsx` via `applyAllRecommendations()` | On click |
| `/api/assets/{id}` | GET | `AssetDetail.tsx` via `fetchAssetDetail()` | 1.5s polling when selected |
| `/api/simulation/speed` | POST | `TopBar.tsx` via `setSimSpeed()` | On speed button click |
| `/api/simulation/pause` | POST | `TopBar.tsx` via `togglePause()` | On pause button click |
| `/api/simulation/state` | GET | *unused by frontend* | Exists as fallback, never called |
| `/api/simulation/heatmap` | GET | `SiteMap.tsx` (when toggled) | Sparse density grid, daily reset |
| `/api/cameras` | GET | `SiteMap.tsx` inline fetch | When cameras toggle enabled |
| `/ws` | WS | `useWebSocket.ts` | 10Hz sim state stream; cookie + Origin checked at upgrade |
| `/ws/camera/{id}` | WS | `CameraFeed.tsx` | ~5Hz YOLO frame stream; same cookie + Origin check |

**Dev only (`SITEIQ_ENV=dev`)**

| Backend route | Method | Purpose |
|--------------|--------|---------|
| `/dev/outbox` | GET | Lists last 100 emails (verification links, reset tokens, invites) |
| `/dev/outbox/{id}/html` | GET | Renders the HTML body for inspection |

## Target waste metrics (tuned and verified)

| Category | Daily | Monthly | Target range |
|----------|-------|---------|-------------|
| Toilet walks | ~€875 | ~€19K | €800-1,200/day |
| Material handling | ~€600 | ~€13K | €400-700/day |
| Equipment idle | ~€2,200 | ~€48K | €1,200-2,200/day |
| **Total** | **~€3,700** | **~€81K** | **€2,400-4,100/day** |

After applying all optimizations: waste drops ~40-65% depending on project.
