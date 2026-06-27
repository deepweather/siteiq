# SiteIQ — Claude Context

Live architecture reference for AI coding agents. Describes the system as
it stands today.

Sibling docs:
- [`VISION.md`](VISION.md) — why this product exists, the wedge, the
  endgame. Read first if you need product context.
- [`CHANGELOG.md`](CHANGELOG.md) — historical bug fixes, completed
  refactors, closed debt. Don't drag any of that back into this file.
- [`README.md`](README.md) — how to run it locally + via Docker.

## What this is

SiteIQ is an interactive demo of a construction site intelligence product.
The thesis: construction sites are catastrophically inefficient — workers
are productive only 35% of their time. SiteIQ uses cameras + CV to observe
everything on a site, quantify waste in euros, and prescribe specific
operational fixes.

For this demo a **simulation engine** replaces real camera feeds. The
simulation generates the same data that real CV would. The demo must make
an investor or construction executive viscerally understand the waste and
see it fixed in real time — in under 3 minutes, no narration needed.

## Architecture

Two intentionally-disconnected systems behind a self-hosted auth layer:

```
                              ┌────────── Frontend (React Router) ──────────┐
                              │  Public:  / /login /signup /forgot-password │
                              │           /reset-password /verify-email     │
                              │           /accept-invite                    │
                              │  Gated /app/* (RequireAuth → AppLayout):    │
                              │   Chrome (MenuBar + Sidebar + StatusBar)    │
                              │     ↳ Dashboard / Portfolio / Projects /    │
                              │       Settings                              │
                              │   Editor (full-viewport, outside Chrome)    │
                              └────────────────┬────────────────────────────┘
                                               │ cookie + CSRF
                                               ▼
SIMULATION (the demo)                    VISION (proof-of-concept)
┌──────────────────────┐                 ┌─────────────────────────┐
│ SimulationEngine     │                 │ VideoDetector           │
│ - 50–60 workers FSM  │                 │ - YOLOv8n on .mp4 files │
│ - equipment duty     │                 │ - base64 JPEG frames    │
│   cycles             │    NO LINK      │ - bounding box coords   │
│ - position trails    │◄──────────────►│ - confidence scores     │
│ - analytics/waste    │                 │                         │
│ - recommendations    │                 │ Serves: /ws/camera/{id} │
│ Serves: /ws (10Hz)   │                 └─────────────────────────┘
│         /api/*       │                            ▲
└──────────┬───────────┘                            │ all gated by
           │ all gated by Depends(get_current_org)  │ Depends(get_current_org)
           └────────────────┬───────────────────────┘
                            ▼
                ┌──────────────────────────────────┐
                │ FastAPI app                      │
                │  /auth/*  /api/*  /api/orgs/*    │
                │  CSRF middleware + Origin check  │
                │  CORS  Error envelope handler    │
                │  app.state: db engine, email     │
                │  sender, limiter, source, recs   │
                └──────────────┬───────────────────┘
                               ▼
                ┌──────────────────────────────────┐
                │ SQLAlchemy async (SQLite|Postgres)│
                │ users, orgs, memberships, invites│
                │ sessions, tokens, outbox, audits │
                │ projects, project_versions,      │
                │ project_assets, site_events      │
                └──────────────────────────────────┘
```

The camera feeds and the simulation are still not synchronized — see the
"Open architectural debt" section. The product story is "cameras →
intelligence → decisions" but today's demo shows two unrelated systems
side by side.

### What "Live Mode" should eventually look like

```
Real cameras → YOLO inference → Camera calibration → 2D site map
                                (pixel → meter transform)
                                        │
                                        ▼
                              Same analytics/optimization
                              pipeline as simulation mode
```

The simulation engine would be replaced by real detection data projected
onto the site plan. The `SiteStateSource` Protocol seam already supports
this — a future `LiveSource` drops in by changing only the registry's
`EngineFactory`.

## Tech stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.13, FastAPI, uvicorn, WebSocket, Pydantic v2, pydantic-settings |
| Persistence | SQLAlchemy 2.0 async, Alembic, aiosqlite (dev/test) / asyncpg (prod) |
| Auth | argon2-cffi (passwords), opaque server-side sessions, slowapi (rate limit), httpx (Resend) |
| Frontend | React 19, Vite 8, TypeScript 6, Tailwind CSS 3, HTML5 Canvas |
| Frontend libs | react-router-dom v7, react-hook-form, zod, @zxcvbn-ts (lazy), sonner |
| CV | ultralytics (YOLOv8n), opencv-python-headless |
| Package mgmt | uv (backend), npm (frontend) |
| Real-time | WebSocket at 10 Hz for sim state, ~5 Hz for camera frames |

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

Settings are read from `backend/.env` (see `backend/.env.example` for
every `SITEIQ_*` knob). In dev mode the verification + reset emails are
persisted to the `email_outbox` table and visible at
`http://localhost:8000/dev/outbox` — no SMTP setup needed.

Camera feeds require .mp4 files in `backend/vision/videos/`. Three Pexels
CC0 construction-site videos are downloaded but gitignored. YOLO weights
(`yolov8n.pt`) auto-download on first run.

## Design principles (do not violate)

1. **One canonical document.** `backend/models/project_document.py`
   defines `ProjectDocument`. It is the storage format, the API
   payload, the editor's state, and the simulation engine's input. The
   only transformation is `simulation.project_loader.build_engine_state(doc)`.
2. **Content-addressed immutable versions.** Every save writes a new
   `project_versions` row whose PK is `sha256(canonical_json(document))`.
   `projects.current_version_id` is a single mutable FK — atomic swap,
   no draft/publish state machine.
3. **The seam is sacred.** `SiteStateSource` Protocol is the contract
   between state producers (simulation, future LiveSource) and consumers
   (analytics, optimization, API, renderer). Don't bypass it.
4. **No module-level globals.** Long-lived objects live on `app.state`
   and are injected via FastAPI `Depends`. The one documented exception
   is `renderer.ts`'s `S/OX/OY` — see comment at the declaration site.
5. **Editor = thin reducer over the same Pydantic schema.** OCC via
   `If-Match: <version_id>`, no CRDTs.
6. **Multi-level via discrete `level_id` + a connection graph.** Vertical
   transport is BFS on a small graph, not 3D pathfinding.
7. **The system of record is an append-only event ledger.** `site_events`
   is the operational source of truth. Current state and costs are
   projections (folds) over it — never separately maintained. The only
   write path is `services.event_ledger.EventLedger`; the simulation, the
   demo generator, manual capture, and a future camera `LiveSource` all
   append through it. Rows are immutable (the `status` cache aside, whose
   every change is itself a companion event), hash-chained per stream, and
   bitemporal (`occurred_at` vs `recorded_at`).

## Auth, orgs, persistence

Self-hosted auth in front of every `/api/*` and WebSocket route. SQLite
for dev/test, Postgres for prod — one async SQLAlchemy 2.0 engine
selected via `SITEIQ_DATABASE_URL`.

```mermaid
flowchart LR
    Browser["Browser (cookie + CSRF)"] --> Routes
    subgraph backend [FastAPI app]
        Routes["/auth/* and /api/* routers"]
        Routes --> Deps["api/deps.py: get_current_user, get_current_org, require_role"]
        Deps --> DB[("SQLAlchemy async DB<br/>SQLite dev / Postgres prod")]
        Deps --> Source["SiteStateSource (per-org engine)"]
        Routes --> Email["EmailSender Protocol"]
        Email --> Console["ConsoleSender (dev)"]
        Email --> Resend["ResendSender (prod)"]
    end
    DB --> Tables["users, orgs, org_memberships, org_invites,<br/>auth_sessions, verification_tokens, email_outbox, audit_events,<br/>projects, project_versions, project_assets, site_events"]
```

### Sessions, not JWTs
Opaque tokens live in `auth_sessions`; the cookie holds the plaintext,
the DB holds `sha256(token)`. Revocation, sliding expiry, and "sign out
everywhere" are all single SQL updates. Cookie name uses the `__Host-`
prefix when `SITEIQ_COOKIE_SECURE=true` so browsers enforce Path=/, Secure,
no Domain.

### CSRF
Double-submit cookie (`siteiq_csrf` cookie + `X-CSRF-Token` header) plus
an `Origin` allow-list checked on every state-changing request. WebSockets
share the same Origin allow-list and re-verify the session cookie at
upgrade.

### Email
`EmailSender` Protocol mirrors the `SiteStateSource` seam. `ConsoleSender`
persists to `email_outbox`; the same rows are visible at `/dev/outbox`
when `SITEIQ_ENV=dev`. `ResendSender` posts to api.resend.com via httpx
and updates the same row's status. Tests assert against the outbox.

### Orgs + roles
Signup auto-creates an Org named after the company; the user is its
owner. Roles (`owner > admin > member > viewer`) are checked via
`Depends(require_role(Role.ADMIN))`. Invites are 7-day single-use tokens
keyed to the invitee's email. Every membership change writes an
`audit_events` row (visible to owners on Settings → Team).

### Magic-link login
Passwordless alternative path. `POST /auth/request-magic-link`
(rate-limited, silent on unknown emails) drops a 15-minute single-use
token in the user's email. `POST /auth/login-with-token` consumes the
token. Replays return `token_used`. UI at `/magic-link`, reachable from
`LoginPage`.

### Rate limiting
slowapi limiter as a module-level singleton in `auth/rate_limit.py`
(required because `@limiter.limit("…")` captures it at decoration time).
Wired on:
- `POST /auth/signup` — 5 / hour / IP (signup-spam guard)
- `POST /auth/login` — 10 / minute / IP (brute-force guard)
- `POST /auth/forgot-password` — 5 / hour / IP (email-cost guard)

Storage is in-memory; `SITEIQ_RATE_LIMIT_REDIS_URL` swaps to Redis at
lifespan start for multi-worker deployments. 429s go through the standard
`{error: {code: "rate_limited", message}}` envelope.

### Security headers
`api/security_headers.py` is a **pure ASGI middleware** (not
`BaseHTTPMiddleware` — the latter deadlocks `TestClient` when stacked
≥3 deep). Adds on every response:

- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: DENY`
- `Referrer-Policy: strict-origin-when-cross-origin`
- `Permissions-Policy: geolocation=(), microphone=(), camera=(), payment=()`
- `Content-Security-Policy` — `default-src 'self'`, frame-ancestors
  blocked, object-src blocked, `connect-src` whitelist includes
  `api.pwnedpasswords.com` for the HIBP breach check
- `Strict-Transport-Security: max-age=31536000; includeSubDomains` —
  **only when `env=prod`** (would lock localhost into HTTPS upgrades)

### Request-id middleware
`api/request_id.py` — pure ASGI middleware, **outermost layer**. Reads
incoming `X-Request-Id` or generates a UUID hex, binds it to a
`contextvars.ContextVar`, echoes it on the response. `logging_config.RequestIdFilter`
reads the ContextVar and stamps every log record with `request_id=…`. The
error envelope includes `request_id` so users can paste it into support
tickets.

### Health, readiness, version
- `GET /healthz` — liveness, returns 200 + `{"status": "ok"}` while the
  process is up. Used by Dockerfile + docker-compose healthchecks.
- `GET /readyz` — readiness, returns 200 only when the DB is reachable
  AND the simulation registry is initialised. 503 otherwise.
- `GET /api/version` — returns `{commit, built_at, short}`. Reads
  `SITEIQ_COMMIT_SHA` + `SITEIQ_BUILT_AT` env first; falls back to a
  `version.txt` file the Dockerfile stamps at build time. Surfaced in
  the SettingsLayout footer.

All three are unauthenticated GETs (sail past CSRF).

### Background cleanup tasks
Both lifecycle tasks drain on shutdown — without that, an in-flight
cleanup can race the engine shutdown and the lifespan never returns.

- `auth/outbox_cleanup.py` — deletes `email_outbox` rows older than
  `SITEIQ_EMAIL_OUTBOX_RETENTION_DAYS` (default 90) every
  `SITEIQ_EMAIL_OUTBOX_CLEANUP_INTERVAL_SECONDS` (default 3600).
  Retention `0` disables.
- `auth/auth_cleanup.py` — drops fully-revoked / expired `auth_sessions`
  and consumed / expired `verification_tokens` past their retention
  windows (`SITEIQ_AUTH_SESSION_RETENTION_DAYS`, `SITEIQ_AUTH_TOKEN_RETENTION_DAYS`).

### Per-org simulation engines
`backend/state/registry.py` is the registry for `SimulationEngine` +
`RecommendationService` instances, keyed by `org_id`. `Depends(get_source)`
resolves the active org first and looks up (or lazily creates) that org's
engine. The simulation tick loop iterates every live engine. Side effects:

- Two orgs viewing the dashboard see different sites.
- WebSocket auth (`api/ws_auth.py`) returns the session's
  `current_org_id`; the WS handler uses it to look up the right engine.
- Account / workspace deletion calls `registry.discard(org_id)` so the
  engine + analytics + recs are reclaimed immediately.

`orgs.active_project_id` (migration `0002_orgs_active_project`) persists
each org's chosen `PROJECT_TEMPLATES` key. `orgs.active_project_version_id`
(migration `0003_projects`) pins the project version for the
content-addressed editor flow.

### Account + workspace deletion
- `POST /auth/delete-account` — re-supplies the password, then deletes
  the user. For each org the user owned: if there's another owner, only
  the membership goes; if they were the last owner, the org is deleted
  entirely (cascade drops memberships, invites, audit_events, and the
  registry's engine).
- `DELETE /api/orgs/current` — owner-only. Two confirmations: type the
  workspace name + re-supply the password. Sessions whose `current_org_id`
  pointed at the deleted org get nulled — they fall back to another
  membership next request rather than logging out.
- Both record `org.deleted` / `user.deleted` audit events before the
  cascade so an admin can forensically reconstruct what happened.

### Audit log CSV export
`GET /api/orgs/current/audit.csv?since=…&until=…` streams up to 10k rows
of audit events as RFC 4180 CSV. Owner-only. Frontend Team settings
links via `<a download href={orgs.auditCsvUrl()}>` so the browser
handles the file save with the auth cookie attached. Bad timestamps
return `{error: {code: "invalid_timestamp", field}}`.

### Portfolio waste estimator
`services/portfolio_estimator.py` warms a transient `SimulationEngine`
per project template at app startup (240 ticks ≈ 2 sim-hours), runs
`compute_waste_summary` once, caches on `app.state.portfolio_estimates`.
Each `/api/portfolio` card shows real per-project numbers. Tests turn
the warm-up off via `SITEIQ_COMPUTE_PORTFOLIO_AT_STARTUP=false` to keep
TestClient lifespans fast — they fall back to the legacy formula
(acceptable for unit tests; integration smoke covers the live path).

### Frontend resilience
- `src/lib/ErrorBoundary.tsx` wraps the entire router. Anything thrown
  during render becomes a clean recovery card with stack trace + Reload.
- `src/hooks/useConnectionToast.ts` watches the WS `connected` flag.
  After a 2 s grace, drops a sticky "Reconnecting…" toast; on reconnect
  it auto-replaces with a 2.5 s "Live again" success.
- All routes are split via `React.lazy` + `Suspense`. Initial bundle
  ~245 KB (gzip ~78 KB); each settings page is 1–8 KB on its own.

## Backend modules

### `config.py`
Domain constants only (rates, intervals, sim-clock parameters).
Operational knobs live in `settings.py` instead. Key tunables:
`TOILET_INTERVAL` (7200 s = 2 h), `MATERIAL_RUN_INTERVAL` (7200 s),
equipment hourly rates (€180/120/90 for crane/pump/excavator),
`SIM_SECONDS_PER_TICK` (30 — each 100 ms real tick = 30 s sim time at
1× speed).

### `settings.py`
`Settings` (pydantic-settings `BaseSettings`) with `SITEIQ_*` env
overrides. Beyond CORS / log / YOLO knobs, the auth-era fields:
`env` (`dev|prod|test`), `database_url`, `frontend_origin`,
`session_secret`, `session_cookie_name`, `session_lifetime_days`,
`session_idle_days`, `cookie_domain`, `cookie_secure`, `email_provider`
(`console|resend`), `resend_api_key`, `email_from`, `rate_limit_redis_url`.
Convenience properties: `is_prod`, `is_dev`, `effective_cookie_secure`
(defaults `True` in prod, `False` in dev). System-of-record seams:
`capture_provider` (`rule|llm`), `query_provider` (`deterministic|llm`),
`record_llm_api_key` (the `llm` providers degrade to the deterministic
defaults until a key is set). Documented in `.env.example`.

### `logging_config.py`
`configure(level, fmt)` installs one stream handler on the root logger.
`fmt="json"` swaps in `python-json-logger`'s `JsonFormatter`. Idempotent.
Every module uses `logging.getLogger(__name__)`. **Zero `print(...)`
calls; zero bare `except Exception: pass`** (guarded by `test_logging.py`).

### `state/`
- **`source.py`** — `SiteStateSource` Protocol (`@runtime_checkable`).
  Surface: `project_id`, `sim_time`, `sim_day`, `site`, `assets`,
  `asset_by_id`, `zone_by_id`, `workers_in_zone`, `worker_internals_for`,
  `activity_log_for`, `position_history_for`. Multi-level additions:
  `levels`, `level_by_id`, `workers_in_level`, `connections`,
  `connections_from_level`.
- **`registry.py`** — `SourceRegistry` keyed by `org_id`. `for_org(slug)`
  for seed-slug loads, `for_org_at_version(org_id, doc, version_id)` for
  content-addressed activation. Tags engine-in-place when slug + null
  version match the activating document (avoids tearing down legacy
  seed-loaded engines).

### `models/`
Pydantic v2 schemas. `Site` has zones + schedule. `Asset` has position,
state, metadata. `WasteSummary` aggregates costs. `Recommendation.from_position`
/ `to_position` use the typed `PositionXY` model.
`Asset.to_broadcast_dict()` produces the compact WebSocket payload —
flat dict with id, type, subtype, x, y, state, assigned_zone, lvl.

### `models/project_document.py` — canonical schema

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
    background_image_url: str | None

class Position(BaseModel):
    x: float; y: float
    level_id: str = "L0"   # default keeps legacy data compatible

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

### `simulation/`
- **`site_factory.py`** — `PROJECT_TEMPLATES` is a thin lazy view that
  loads from `backend/seeds/projects/*.json`. Four seeds today:
  residential Berlin, commercial Frankfurt, infrastructure Munich,
  Munich sewer (Tiefbau).

- **`project_loader.py`** — `build_engine_state(doc)` materialises
  `(Site, list[Asset], dict[worker_id, WorkerInternals], list[Connection])`
  from a `ProjectDocument`. The only doc→engine translation.

- **`navmesh.py`** — `NavMesh` per level: 2 m weighted grid (road
  1.0, open ground 1.5, zone interior 2.0, equipment footprint and
  off-site = infinity) with A* + octile heuristic + Bresenham
  string-pull simplification + path cache. `build(level_id, site,
  equipment)` overlays roads (matching renderer's south + west strips),
  zone rectangles, and per-subtype equipment circles
  (`EQUIPMENT_FOOTPRINT_RADIUS_M` in [config.py](backend/config.py)).
  `path(start, end)` returns the worker-facing waypoint list;
  `distance(start, end)` is used by the optimizer to score
  recommendations by what workers actually walk;
  `nearest_walkable(x, y)` snaps a candidate placement off impassable
  cells; `invalidate()` wipes the cache on rec apply / project switch.

- **`engine.py`** (~140 LOC, down from 243) — `SimulationEngine`
  implements `SiteStateSource`. Owns `assets`, `site`, `worker_internals`,
  `position_history`, `activity_log`, plus O(1) indexes (`_by_id`,
  `_facilities_by_subtype`, `_facilities_by_subtype_level`,
  `_workers_by_zone`, `_connections_by_level`) rebuilt on every project
  switch via `rebuild_indexes()`. `tick()` advances the FSM;
  `get_state_snapshot()` produces the WS broadcast payload.

- **`worker_internals.py`** — `@dataclass WorkerInternals` typed state
  per worker (FSM timers, dwell counters, daily-reset stats,
  `target_level_id`, `cross_level_destination`, `vertical_connection_id`,
  `vertical_queue_enter_time`, `time_in_vertical_transport`).
  `reset_daily()` clears day-level counters.

- **`worker_behavior.py`** — Worker FSM with dispatch table:
  `STATE_HANDLERS: dict[WorkerState, StateHandler]` maps each state to a
  single-purpose `_on_*` handler. Adding a state = write a handler + add
  one line. Uses engine's indexed lookups via the local `_WorkerEngine`
  Protocol. **Strict-mypy clean.** `_find_nearest_facility` prefers a
  same-level facility, falls back cross-level only when none exists on
  the worker's current floor. `_begin_vertical_route` BFSes the
  connection graph and sets `WALKING_TO_VERTICAL` if the destination is
  on a different level. Movement primitives:
  - `move_toward(worker, target, dt_sim)` — single-segment walk.
  - `set_path(worker, internals, engine, dest)` — queries the per-level
    navmesh and stashes the waypoint list on `WorkerInternals.path` /
    `.path_index`. Falls back to single-target on sources without a navmesh.
  - `follow_path(worker, internals, dt_sim)` — walks one tick along
    `internals.path`, advancing the index on arrival. Every "walking"
    state handler calls this instead of `move_toward` so workers route
    around equipment + along roads instead of cutting through cranes.

- **`vertical_transport.py`** — one `CabState` per elevator
  `Connection`: `current_level_id`, `direction (+1/-1/0)`,
  `passengers: list[(worker_id, target_level_id)]`,
  `queue_per_level: dict[level_id, deque[worker_id]]`, `door_open_remaining_s`.
  `tick_cab(cab, dt_sim, on_alight, on_board)` advances the cab and
  dispatches callbacks. Long sim ticks (sim runs up to 20× real-time)
  loop through multiple floor stops so cab position stays consistent
  with worker movement. **Microbench gate**: 6 cabs × 250 workers × 6
  levels averages < 5 ms/tick. Locked in
  `tests/test_vertical_transport.py::test_tick_under_5ms_with_six_cabs_and_workers`.

- **`equipment_behavior.py`** — Alternates OPERATING ↔ IDLE on duty
  cycles (crane 40/30 min, pump 10/40 min, excavator 42/18 min). Tracks
  `hours_active` / `hours_idle`.

- **`tiefbau_behavior.py`** — `update_tiefbau_equipment`: dewatering
  pumps run 80% / 20% duty cycle; sheet piles stay permanently
  OPERATING. `compute_shoring_compliance` returns a per-EXCAVATION-zone
  score: 1.0 if a sheet pile is within `SHORING_INFLUENCE_RADIUS_M = 25`
  of the zone's centre, 0.0 otherwise. New subtypes: `sheet_pile`,
  `dewatering_pump`. Engine dispatch in `_tick()` routes these subtypes
  to `update_tiefbau_equipment` instead of `update_equipment`.

- **`asset_detail.py`** — `asset_detail(source, asset_id)` builds the
  rich per-asset detail view. Dispatch table `DETAIL_BUILDERS` routes by
  `asset.type` to `_worker_detail` / `_equipment_detail` /
  `_facility_detail` / `_material_detail`. Per-type radius + state
  tables for facility occupancy.

### `analytics/` (all take `source: SiteStateSource`)
- **`travel.py`** — `compute_travel_metrics(source)`. Per-zone metrics:
  avg toilet round-trip, trips/day, daily walk cost (trips × RT ×
  hourly_rate), productivity rate. Extrapolates partial-day data via
  `day_fraction`.
- **`utilization.py`** — `compute_equipment_utilization(source)`. Per-equipment:
  utilization rate, daily idle cost (normalized to 11h workday ×
  idle_fraction × rate).
- **`vertical_metrics.py`** — `compute_vertical_metrics(source)`. Per-worker
  `time_in_vertical_transport` extrapolated to a full day → `waste_daily`
  in €. Per-cab snapshot: `queued_now`, `riding_now`, `saturation`,
  `longest_wait_s`.
- **`aggregator.py`** — `compute_waste_summary(source)`. Combines travel
  + equipment + vertical into `WasteSummary` with daily and monthly
  totals. WasteSummary's `vertical_transport_daily` / `_monthly` is
  rendered only when > 0 (single-floor sites stay clean).

### `optimization/` (all take `source: SiteStateSource`)
- **`facility_placement.py`** — Weighted k-means (k=2) **per level** —
  toilets can't move across floors. Greedy-nearest pairing assigns
  toilets to centroids. Centroids snap to the nearest walkable navmesh
  cell so the optimizer never suggests "move the toilet onto the crane".
  Savings use `navmesh.distance(...)` (path-distance, not euclidean) so
  the cost number reflects what workers actually walk; falls back to
  euclidean on sources without a navmesh.
- **`material_staging.py`** — Picks the zone edge closest to the
  material's current position (preserves gate-side logistics flow).
  Candidate positions are snapped to walkable cells via
  `navmesh.nearest_walkable`; scoring uses `navmesh.distance`.
- **`equipment_schedule.py`** — Flags equipment < 40% utilization for
  release, < 60% for rescheduling. `daily_idle_hours = (1 - utilization)
  × 11h` (stable from t=0).
- **`vertical_transport_optimizer.py`** — Fires on instantaneous
  saturation ≥ 60% or longest queue wait ≥ 60 s, OR cumulative daily
  waste per cab ≥ €5/day. Recommendation: "Add a second cab next to
  {connection_id}", estimated savings = `avg_daily_per_cab / 2`.

### `services/`
- **`recommendation_service.py`** — `RecommendationService(source,
  optimizers=…)`. Owns the recommendation cache; tracks the project id
  of the cached set and auto-invalidates on mismatch. `get()`, `clear()`,
  `mark_dirty()`, `by_id()`. Constructed once per app at lifespan
  startup, injected via `Depends(get_rec_service)`.
- **`portfolio_estimator.py`** — see "Auth, orgs, persistence" above.
- **`event_ledger.py`** — `EventLedger(session)`: the single write path
  into the system of record. `append`/`append_many` assign a per-stream
  gap-free `seq` and chained `hash`; `set_status` records confirm/reject/
  supersede as companion events AND updates the cached `status`; `query`
  filters (subject/kind/source/status/time, excludes companion events by
  default); `verify_chain` recomputes the chain to detect tampering.
- **`cost_engine.py`** — `compute_costs(events, rate_card)` folds confirmed
  `worker.timesheet` / `equipment.utilization` / `material.delivered`
  events into a `CostBreakdown`. Every `CostLine` carries its supporting
  event ids. Default `RateCard` in `models/cost.py` (config-sourced).
- **`record_projections.py`** — pure folds: `entity_projection` (current
  state + per-type metrics + history for one subject), `daily_rollup`,
  `event_to_dict`.
- **`demo_record_generator.py`** — deterministic backfill from the active
  `ProjectDocument` for the days BEFORE `start_day` (timesheets, equipment
  utilization + state changes, deliveries incl. a few low-confidence camera
  detections for the inbox, inspections, incidents). One continuous timeline
  with live emission. CLI: `seed_demo_record.py`.
- **`capture.py`** — `CaptureParser` Protocol + `RuleBasedCaptureParser`
  default (keyword/regex → `proposed` events) + `LLMCaptureParser` stub.
- **`record_query.py`** — `QueryResponder` Protocol + `DeterministicQueryResponder`
  default (intent-matched ledger aggregations with supporting events) +
  `LLMQueryResponder` stub. Both built from `settings.{capture,query}_provider`.
- **`sim_calendar.py`** — `sim_to_datetime(sim_day, sim_time)` maps the sim
  clock to ledger `occurred_at` via `RECORD_EPOCH_DATE`.

`simulation/event_emit.py` keeps the engine lean: `record_event` buffers an
event on `engine.pending_events`, `drain` empties it, `emit_end_of_day`
writes the daily timesheets + equipment utilization. `main._run_event_drain_loop`
flushes every live engine into the ledger every `EVENT_DRAIN_INTERVAL`
(drains on shutdown like the other lifecycle tasks).

### `api/`
- **`deps.py`** — FastAPI dependency providers. Domain: `get_source`,
  `get_rec_service`, `get_detector`, `get_analytics`, `get_settings`,
  `get_email_sender` (all 503 if `app.state` isn't ready). Auth:
  `get_optional_session`, `get_current_session`, `get_current_user`,
  `get_current_org`, `get_current_membership`, `require_role(min: Role)`
  (closure-style Depends, returns 403 below threshold).
- **`routes.py`** — REST routes, all wrapped in `Depends(get_current_org)`.
  GET `/api/projects`, `/api/portfolio`, `/api/site`,
  `/api/recommendations`, `/api/assets/{id}`, `/api/simulation/state`,
  `/api/simulation/heatmap`. POST `/api/site/load-seed`,
  `/api/recommendations/{id}/apply`, `/api/recommendations/apply-all`,
  `/api/simulation/speed`, `/api/simulation/pause`. Sim-only controls
  return 501 if the source isn't a `SimulationEngine`.
- **`projects.py`** — content-addressed project CRUD (see
  "Editor + multi-level" below).
- **`record.py`** — system-of-record surface (`/api/record/*`): `events`,
  `days`, `timeline`, `subjects`, `entities/{type}/{id}`, `inbox`,
  `events/{id}/confirm`, `events/{id}/reject`, `events` (manual), `costs`,
  `verify`, `capture`, `query`, `demo/generate`. Writes = member+; demo regen =
  admin+. The active stream is `(org.id, source.project_id)`. Every mutation
  writes an `audit_events` row. Reads are filtered through the tiered
  visibility policy (`Depends(get_record_access)`, see below).

### Record visibility policy — `services/record_access.py`
Tiered data privacy over the ledger (auth is solved; this is authorization).
Principle: aggregate + asset data is open, individual worker behavioural data
is privileged (a GDPR / works-council requirement). `RecordAccess(role)`
maps the role ladder to three tiers and redacts server-side:
- **crew** (viewer) — operational only (equipment / materials / zones /
  inspections / incidents + aggregate costs & headcounts). Worker subjects
  and `worker.*` events are filtered out; `GET /entities/worker/*` → 403.
- **supervisor** (member) — the above + individual worker timesheets /
  presence, but behavioural fields (`hours_facilities/walking/vertical`,
  the `walking_hours` metric) and per-worker cost lines are stripped.
- **manager** (admin/owner) — everything.
Applied in `events`, `timeline`, `inbox`, `subjects`, `entities`, `costs`.
The frontend mirrors it for affordance (worker links simply don't appear for
crew; the entity drawer shows a "restricted" card on a 403).
- **`project_assets.py`** — background image upload + serve. Multipart
  parser via `python-multipart`.
- **`websocket.py`** — WS `/ws` streams `state_update` at 10 Hz (assets
  + trails + latest analytics). Auth: cookie + origin checked at upgrade
  via `api/ws_auth.py`.
- **`camera.py`** — GET `/api/cameras` lists video feeds. WS
  `/ws/camera/{video_id}` streams YOLO-processed frames at ~5 Hz via
  `asyncio.to_thread()` so inference doesn't stall the event loop.
- **`ws_auth.py`** — `authenticate_ws(websocket)`: rejects unknown
  Origins with close code 4403, missing/invalid session with 4401.
  Shared by both WebSocket endpoints.
- **`dev.py`** — `/dev/outbox` (mounted only when `env=dev`). Lists
  recent 100 emails; `/dev/outbox/{id}/html` serves the rendered body.

### `vision/`
- **`detector.py`** — `VideoDetector` wraps YOLOv8n. Loads all .mp4
  from `vision/videos/`, reads frames with OpenCV, runs inference
  (conf=0.20), returns base64 JPEG + normalized bounding boxes.
  CLASS_REMAP maps COCO classes to construction labels ("person" →
  "Worker"). ~18 ms inference per frame on Apple Silicon.

### `db/`
- **`project_repository.py`** — only place that translates between
  `ProjectDocument` and DB rows. `save_version(project_id, doc,
  parent_version_id, …)` raises `OptimisticLockError` if
  `parent_version_id` no longer matches the project's current pointer,
  which the router surfaces as a 409 `version_conflict`.

### `seeds/`
- **`importer.py`** — imports every bundled JSON seed as a public-template
  row at app startup. Idempotent via content hash: identical seeds
  dedupe; edited seeds bump the version.

### `main.py`
Thin composition root. `create_app(settings=None)` builds an isolated
FastAPI app (tests can pass custom settings). Lifespan handler
constructs the async DB engine + session factory, the `EmailSender`
(Console or Resend), the slowapi limiter, the `SimulationEngine`, the
`RecommendationService` and the `VideoDetector` — all attached to
`app.state`. Spawns `run_simulation_loop` + `_run_analytics_loop`.

Middleware order: request-id (outermost) → CORS → CSRF (double-submit
cookie + Origin allow-list, exempts `/auth/csrf` + `/ws/*`) →
security-headers → routers (`/auth`, `/api/orgs`, `/api`, `/ws`,
`/ws/camera`, plus `/dev/*` only in dev). A custom exception handler
converts `HTTPException` and `RequestValidationError` into the standard
`{error: {code, message, field?}}` envelope.

## Editor + multi-level (live architecture)

### Persistence

Alembic migration `0003_projects` adds:

- `projects(id, org_id, slug, name, description, type, discipline,
  visibility, status, current_version_id, …)` — top-level row, `org_id=NULL`
  for public templates.
- `project_versions(id, project_id, parent_version_id, document JSONB,
  message, created_by_user_id, created_at)` — immutable. `id` is the
  SHA-256 content hash.
- `orgs.active_project_version_id` — pointer at the version the org's
  simulation runs on.

Migration `0004_project_assets` adds `project_assets(id, project_id FK
cascade, kind, content_type, data LargeBinary, content_hash)` for
background floor-plan blobs.

### Project router

All routes wrapped in `Depends(get_current_org)` + `require_role(Role.ADMIN)`
for writes.

| Route | Method | Purpose |
|-------|--------|---------|
| `/api/projects` | GET | List org-owned + public-template projects (incl. `is_active` flag) |
| `/api/projects` | POST | Create new draft (returns full document) |
| `/api/projects/{id}` | GET | Full document, version id, visibility, ownership |
| `/api/projects/{id}` | PUT | Save new version. `If-Match: <version_id>` required for OCC. Validation errors as `400 {code, message, field}`. |
| `/api/projects/{id}` | DELETE | Soft via cascade |
| `/api/projects/{id}/activate` | POST | Pin org's simulation to this project/version |
| `/api/projects/{id}/validate` | POST | Dry-run validation; live editor feedback |
| `/api/projects/{id}/preview` | POST | Transient engine, `ticks` (default 240, max 1200), returns snapshot + waste + recs. Rejects docs with `severity="error"` validation issues. |
| `/api/projects/{id}/levels/{level_id}/background` | POST | Multipart upload. `image/{png\|jpeg\|webp}`, ≤ 2 MiB. Inserts blob + writes new version with `Level.background_image_url`. `If-Match` honoured. |
| `/api/projects/{id}/levels/{level_id}/background` | DELETE | Strips url + drops asset row in one transaction. |
| `/api/projects/{id}/assets/{asset_id}` | GET | Serves bytes with `Cache-Control: public, max-age=31536000, immutable` and content hash as `ETag`. |

Every mutating endpoint writes an `audit_events` row: `project.created`,
`project.updated`, `project.deleted`, `project.activated`,
`project.preview`, `project.background.uploaded`,
`project.background.deleted`.

`/api/site/load-seed {slug}` is kept for the dashboard's stock-project
switcher; it's a no-op when `source.project_id == req.slug`.

### Editor GUI

Routes:
- `/app/projects` — list of org-owned + public-template projects with
  Edit / Activate / Duplicate actions. Active project shown with green
  `● Active` pill and disabled "Activated" button.
- `/app/projects/:id/edit` — the editor.

Components in `frontend/src/components/editor/`:
- **`ToolPalette.tsx`** — categorised tool buttons (Zone / Facility /
  Vertical / Equipment / Tiefbau).
- **`LevelManager.tsx`** — add/rename/remove levels (L0 protected); per-row
  "📐" uploads a background image.
- **`PropertiesPanel.tsx`** — context-sensitive editor for the currently
  selected zone / facility / equipment / material / connection. Worker
  seeds edited inside the zone view.
- **`EditorCanvas.tsx`** — focused 2D drawing for editor mode (separate
  from the runtime renderer). Click-to-select in select mode;
  click-to-place when a placement tool is active. Snap-to-grid pills
  (0/1/5/10 m, default 1 m, persisted to
  `localStorage.siteiq.editor.grid_size`). Grid dots auto-step up
  (1m → 2m → 4m → 8m) until ≥ 6 CSS pixels of separation. 3 px
  click→drag threshold; coarse-grain undo (one patch per drag). Label
  collision detection mirrors `renderer.ts`.
- **`ScheduleEditor.tsx`** — right-column "Schedule" tab. One row per
  zone, ordered like `LevelManager`. Drag a `ProjectScheduleEntry` block
  horizontally → shifts `start_day` and `end_day` together; drag left
  handle → only `start_day`; drag right handle → only `end_day`. Snap
  to 1-day grid. "+ Phase" opens an inline picker. One coarse-grain
  `patch` per drag on mouseup.
- **`PreviewRunPanel.tsx`** — non-modal sidebar with daily/monthly waste
  + top 5 recommendations. Auto-dismisses when the draft mutates.
- **`ValidationOverlay.tsx`** — surfaces errors / warnings from
  `POST /api/projects/{id}/validate`.

State management via `frontend/src/hooks/useProjectDraft.ts`:
- `useReducer` over `{ current, past, future, savedVersionId }` for
  instant undo/redo.
- Autosave every 5 s if dirty, posting `PUT /api/projects/{id}` with
  `If-Match: <savedVersionId>`. Conflict → sets `conflict=true` (UI
  shows "⚠ conflict — reload").
- Debounced live validation (800 ms) → `setIssues`.
- `applyServerUpdate(detail)` callback clears undo/redo (the new version
  IS the new ground truth).

Activate from the editor header → `POST /api/projects/{id}/activate` →
navigate back to the dashboard. The next `get_source` call detects the
version drift and rebuilds the engine on the new document.

## Frontend modules

### Desktop shell (`src/shell/`)

Every `/app/*` route is nested under a two-layer shell:

```
<RequireAuth>
  <AppLayout>                      // shell/AppLayout.tsx
    <LiveProvider>                 // shell/LiveContext.tsx — single WS+sim
                                   //   shared across every /app/* route
      <CommandPalette/>            // shell/CommandPalette.tsx — ⌘K overlay
      <Outlet/>                    // route children below
    </LiveProvider>
  </AppLayout>
</RequireAuth>

  <Chrome>                         // shell/Chrome.tsx — persistent chrome
    <MenuBar/>                     //   shell/MenuBar.tsx — top row
    <Sidebar/>                     //   shell/Sidebar.tsx — 52 px icon rail
    <main><Outlet/></main>         //   page body (Dashboard / Portfolio / …)
    <StatusBar/>                   //   shell/StatusBar.tsx — bottom strip
  </Chrome>
```

- **`AppLayout.tsx`** — outermost wrapper for `/app/*`. Mounts the
  `LiveProvider` (one WebSocket + one `/api/site` fetch + one
  recommendations poll per session, survives navigation between Dashboard
  / Portfolio / Editor / Settings). Wipes the legacy
  `localStorage.siteiq.shell.v1` key from the abandoned tab-shell on
  mount, registers `Cmd+K` / `Cmd+,` shortcuts.
- **`Chrome.tsx`** — visual shell. Renders `MenuBar` at top, `Sidebar`
  on the left, page `<Outlet/>` in the middle, `StatusBar` at bottom.
  Used for Dashboard / Portfolio / ProjectListPage / Settings. The
  editor opts out (full viewport for its own three-panel layout).
- **`LiveContext.tsx` + `useLive.ts`** — the live-data context.
  Provider lives in the `.tsx` for hot-reload friendliness; the hook +
  context object live in the `.ts` so the `.tsx` exports only a
  component. Exposes `assetsRef`, `trailsRef`, `cabsRef`, `analytics`,
  `currentWaste`, `baselineWaste`, `savings`, `recommendations`,
  `setRecommendations`, `speed`, `paused`, `setSpeed`, `togglePaused`,
  `switchProject(slug)`, `reload()`, `recentApply`, `setRecentApply`,
  `refreshRecommendations()`.
- **`MenuBar.tsx`** — single top row, ~36 px. Brand badge ·
  `Site` / `View` / `Account` / `Help` dropdowns · project switcher
  popover (clickable project name, lists projects with an active dot) ·
  sim clock (`Day N · HH:MM`) · pause toggle · 1×/2×/5×/10× speed pills ·
  connection dot · `⌘K` button.
- **`Sidebar.tsx`** — 52 px icon rail, always visible. Six targets:
  Dashboard / Portfolio / Record / Projects / Settings + a bottom `⌘K` button.
  Icon-only by design so the canvas keeps maximum horizontal real estate.
  Active route gets the primary-coloured highlight.
- **`StatusBar.tsx`** — 24 px bottom strip. Workspace cell · pending recs
  + monthly recoverable € · current monthly waste · build version. Cells
  are clickable jump-points (workspace → `/app/settings/orgs`, pending
  → opens palette).
- **`CommandPalette.tsx`** — `Cmd+K` overlay. Verbs: switch project,
  apply recommendation by name, set speed, pause/resume, go to
  Dashboard / Portfolio / Projects / Editor / Settings, Sign out.
  Arrow keys + Enter navigate, Esc closes. Registers itself via
  `keyboard.registerPaletteControls` so the top bar's `⌘K` button +
  the shortcut fire the same handler.
- **`keyboard.ts`** — global shortcut binding. Just `Cmd+K` (palette)
  and `Cmd+,` (settings). Exposes `openPalette()` / `closePalette()`
  for the menu bar and sidebar to call.

### Routes (`App.tsx`)

```
/                         landing
/login /signup /forgot-password /reset-password /verify-email
/accept-invite /magic-link   public auth flow

/app                      → <AppLayout> wraps everything below
  projects/:id/edit       → <ProjectEditorPage>  (no Chrome — full viewport)
  (otherwise)             → <Chrome> wraps:
      index               → <Dashboard>
      portfolio           → <Portfolio>
      record              → <RecordPage>     (system of record)
      projects            → <ProjectListPage>
      settings/*          → <SettingsLayout>  (nested NavLink + Outlet)
```

### State

- **`useWebSocket`** — connects to `${WS_BASE}/ws`, stores assets + trails
  in **refs** (not state) for canvas performance. Only analytics, simTime,
  simDay trigger React re-renders. Reconnect guard skips OPEN *or*
  CONNECTING sockets.
- **`useSimulation`** — fetches `/api/site` on mount. `reload()` re-fetches
  after project switch.
- **`useAnalytics`** — captures first analytics as baseline, computes
  savings delta. `resetBaseline()` clears on project switch.
- **`lib/auth/AuthProvider`** — context that boots via `GET /auth/me`,
  exposes `useAuth()` (`status`, `user`, `org`, `memberships`, `refresh`,
  `setMe`). `RequireAuth` redirects to `/login?next=…`; `RequireRole`
  shows an "Access denied" panel below threshold.

### `services/api.ts`
Extends `getJson` / `postJson` with `credentials: 'include'` and an
`X-CSRF-Token` header sourced from `/auth/csrf`. All errors throw
`ApiError` so forms can render `error.field`. Exports `API_BASE` and
`WS_BASE` — the single source of truth for URLs.

### Canvas rendering (`renderer.ts`, ~970 LOC)
Module-level coordinate helpers `px()`, `py()`, `ps()` set from
scale/offset each frame. The `S/OX/OY` globals are the one documented
exception to the no-globals rule — see comment at the top of the file.

Draw order: ground → roads → fence → zone structures (phase-specific:
excavation contours, foundation grids, structural columns, MEP conduit
routes, finishes partitions) → heatmap → trails → materials → facilities
→ equipment → workers → recommendation arrows → selection highlight →
zone labels → scale bar → legend.

Workers rendered as emoji (👷) with trade-colored dot underneath.
Equipment as emoji (🏗️🚛🚜) with status ring and ACTIVE/IDLE label.
Facilities as emoji (🚻☕🏢🔧) on background plates. Materials as emoji
(🪨🔌🧱🪣). Selection: pulsing orange ring + tooltip; selected worker's
trail at full opacity, others dimmed to 4%.

Label collision detection: every label-draw helper
(`drawEquipmentTopDown`, `drawMaterialStacks`, `drawZoneLabels`,
`drawRecommendationArrows` cost chips) keeps a per-call painted-rectangle
list and skips new labels that would overlap. Friendly subtype labels
in the `LABELS` table (`sheet_pile` → "SHORING", `dewatering_pump` →
"PUMP").

### `CameraFeed.tsx`
Connects to `${WS_BASE}/ws/camera/{videoId}` with exponential-backoff
reconnect (1 s → 10 s cap). Receives base64 JPEG + detection data.
Renders video frame on canvas, overlays bounding boxes with corner
brackets, class labels, confidence %, inference time, detection count
HUD. Shows "● REC" indicator and "YOLOv8 · SiteIQ Vision" badge. Stats
in refs so the RAF loop mounts once.

### `SiteMap.tsx`
Canvas container with pan (drag), zoom (scroll wheel), reset
(double-click). Click detection: converts screen coords → site meters
via scale/offset/zoom/pan back-projection, finds nearest asset within
hit radius, sets `selectedAssetId`. Cursor changes to pointer on hover
over assets; restores to `grab` on mouseUp. Toggle bar: Trails, Heatmap,
Show Fixes, Cameras, Iso View (multi-level only).

Per-mount image cache keyed by absolute URL for level backgrounds. When
the active level has a `background_image_url`, the canvas paints it
once before the dashed site bounds. `renderer.ts` stays untouched; the
runtime SiteMap path temporarily intercepts the two specific
`ctx.fillRect` calls inside `drawSiteGround` (`fillStyle === '#f0ede8'
|| '#d4c9a8'`) so the floor plan survives underneath. Intercept is
restored before the cab overlay runs.

### `SiteMap/LevelSwitcher.tsx`
Vertical strip on the **left** of the canvas (renderer's legend lives
top-right), top-to-bottom by `order` descending. Renders nothing on
single-floor projects. `SiteMap.tsx` manages `activeLevel` state,
filters zones (`zone.level_id === activeLevel`) and assets
(`a.lvl === activeLevel`) before passing to the renderer.

### `SiteMap/IsoRenderer.ts`
2.5D iso compositor. Renders each level to an `OffscreenCanvas` via the
existing `renderFrame`, then stacks them at a ~30° iso angle on the
parent canvas. One `LevelSlab` per level, cached with a dirty-hash
(per-level asset positions + render flags). Only redraws slabs that
changed since the last frame. Single-floor sites short-circuit to
regular `renderFrame` — zero cost when iso is off. `resetIsoSlabs()`
clears the cache on project switch.

### Right panel
Two modes, no tabs:
  - default → `WasteReport` (the cost story).
  - selected asset → `AssetDetail`.

`WasteReport` ordering (top → bottom): hero red number (monthly recoverable
waste, JetBrains Mono, animated) → "EUR X lost every day this layout
stays unchanged" subtext → compact ROI strip (cost / payback / annual
net) → **big green Apply optimisations CTA** with the recovered euros
inside it + inline expander revealing the per-rec list →
"What's bleeding" rows (toilet walks / equipment idle / materials /
vertical transport / shoring compliance) → "Included at no extra cost"
vendor-replacement panel at the bottom.

The previous Waste/Optimize/Timeline tab framing is gone — Timeline
content lives in the editor's Schedule tab where it semantically
belongs, and Recommendations are folded into the Apply CTA's inline
expander so the cost story stays the dominant rail.

Component breakdown (all under `components/RightPanel/`):
- **`WasteReport.tsx`** — owns the cost story + Apply CTA. Renders the
  hero animated number, ROI strip, Apply button (with the recovered
  euros in-button), an inline "N optimisations" expander that mounts
  `<Recommendations/>`, and the "what's bleeding" rows.
- **`Recommendations.tsx`** — embedded inside the expander. "Apply All"
  button with spinner, per-rec cards with Apply buttons, post-apply
  celebration card keyed off `celebrationSig` (auto-hides on project
  switch or new rec set; 8 s timer fallback), applied list at bottom.
- **`Timeline.tsx`** — Gantt chart from schedule data. Used by the
  editor's Schedule tab; not rendered in the runtime right rail.
- **`AssetDetail.tsx`** — Worker: productivity bar (work/walk/facility
  split), distance, trips, round-trip times. Equipment: utilization
  gauge, duty cycle progress (denominator switches between
  `operate_duration_s` / `idle_duration_s` based on state). Facility:
  workers present list. Material: target zone (uses
  `needed_in_zone_label` from backend) + distance. Activity log with
  sim-clock timestamps.

### `Portfolio.tsx`
Routed page (`/app/portfolio`) rendered inside `<Chrome>`. Summary cards
(sites, workers, equipment, waste). Portfolio ROI banner using
`RECOVERABLE_WASTE_FRACTION = 0.55` + `SYSTEM_COST_PER_SITE = 2000`.
Per-site cards with Open Site button that calls
`useLive().switchProject(slug)` and navigates back to `/app`.

### `pages/record/*`
The system-of-record UI under `/app/record` (`RecordPage` tabs, no extra
routing). `recordApi.ts` is the typed client. Tabs:
- **Timeline** (`RecordTimeline`) — flight recorder: day selector +
  events grouped by hour.
- **Inbox** (`RecordInbox`) — proposed (low-confidence) events; one-tap
  Confirm / Reject. "Confirm, don't create".
- **Costs** (`RecordCosts`) — labour / equipment-idle / material totals,
  recoverable non-productive labour, by-day + by-zone, and cost lines that
  trace to supporting events.
- **Ledger** (`RecordLedger`) — searchable raw log + a tamper-evidence
  "chain verified" badge from `GET /api/record/verify`.
- **Ask** (`RecordAsk`) — conversational query over the ledger.
A quick "+ Capture" bar (member+) and a "Generate demo data" button
(admin) sit above the tabs. `EventRow` + `format.ts` are shared.

### `pages/settings/*`
Account (change password, resend verification, delete account), Team
(members, invites, audit log for owners — payload values folded to
first-8 chars by `formatAuditPayload`), Workspaces (org switcher),
Sessions (per-device revoke + sign out everywhere).

### `pages/LandingPage.tsx`
Same orange + JetBrains Mono tokens as the dashboard, with a
`LiveWasteCounter` that ticks up while the user reads.

## Design system
Light theme using HSL CSS custom properties (shadcn-style tokens).
Primary = orange (24 80% 50%), destructive = red, success = green,
warning = amber. Inter for UI, JetBrains Mono for numbers. All monetary
values use `tabular-nums` for stable width.

## Test suite

| Suite | Count | Covers |
|---|---|---|
| Backend | **348** | API, auth, orgs, sim FSM, vertical transport, Tiefbau, editor, preview, background upload, project list, navmesh + path-following + optimizer walkable-clamp, microbench gates, **system of record (ledger hash/verify/bitemporal, cost engine, demo generator, capture, query, `/api/record` flow)** |
| Frontend | **117** | Sim canvas, auth (AuthProvider, RequireAuth), api.ts, editor (ToolPalette, LevelManager, EditorCanvas, ScheduleEditor, PreviewRunPanel), MenuBar, **record (recordApi, Inbox, Costs, Ask, Timeline)** |

Mypy strict scoped to `simulation/worker_internals.py`,
`simulation/worker_behavior.py`, `simulation/navmesh.py`,
`state/source.py` — clean.

Microbench gates locked in:
- `test_tick_under_5ms_at_full_load` — 50 ticks of `isar-bridge` average < 5 ms.
- `test_tick_under_5ms_with_six_cabs_and_workers` — 6 cabs × 250 workers
  same budget.

`tests/conftest.py` exposes:
- `engine` / `frankfurt_engine` / `munich_engine` — fresh `SimulationEngine`
  instances.
- `app_settings` — `Settings` pointing at a per-test SQLite file with
  `env=dev`.
- `app_factory` / `client` — applies migrations, swaps in the no-op
  detector + `cheap_hasher` for argon2, builds a `TestClient`.
- `auth_client` — `client` with a real signed-up user + session cookie
  + CSRF header preset; the standard fixture for auth-gated routes.
- `authenticate(client)` / `setup_test_db(url)` — helpers for tests
  that build their own app variants.

## Open architectural debt

- **#33 — Camera feeds are disconnected from simulation.** The core
  coherence problem. The `SiteStateSource` Protocol seam already supports
  a future `LiveSource` that would replace the simulation engine with
  calibrated YOLO detections projected onto the 2D map.
- **#35 — No 2FA UI yet.** The `users.totp_secret` column exists; the
  UI is intentionally hidden behind a future feature flag.
- **#36 — No billing.** `orgs.plan` exists (`trial|pro|enterprise`) but
  Stripe integration is a separate plan.

## API route → frontend mapping

Every `/api/*` route is wrapped in `Depends(get_current_org)` and returns
the standard `{error: {code, message, field?}}` envelope on failure.
Mutating requests carry `credentials: 'include'` + `X-CSRF-Token`.

### Auth

| Backend route | Method | Frontend caller | Notes |
|--------------|--------|----------------|-------|
| `/auth/csrf` | GET | `services/api.ts` (auto) | Sets `siteiq_csrf` cookie + returns body token; cached client-side |
| `/auth/me` | GET | `AuthProvider` boot | `{user, org, memberships}` — `null`s when anonymous |
| `/auth/signup` | POST | `SignupPage` | Creates user + org (owner) + session; sends verification email |
| `/auth/login` | POST | `LoginPage` | Returns `MeResponse` and sets session cookie |
| `/auth/logout` | POST | `MenuBar` (Account menu), `SettingsLayout`, `CommandPalette` | Revokes active session, clears cookie + CSRF cache |
| `/auth/forgot-password` | POST | `ForgotPasswordPage` | Always 200 — never reveals whether the email exists |
| `/auth/reset-password` | POST | `ResetPasswordPage` | Single-use token, revokes all sessions, issues fresh |
| `/auth/verify-email` | POST | `VerifyEmailPage` | Single-use token, 24h TTL |
| `/auth/resend-verification` | POST | `AccountSettings` | No-op if already verified |
| `/auth/change-password` | POST | `AccountSettings` | Revokes every other session |
| `/auth/sessions` | GET | `Sessions` | Live (non-revoked, non-expired) sessions |
| `/auth/sessions/{id}/revoke` | POST | `Sessions` | Per-device revoke |
| `/auth/sessions/revoke-all` | POST | `Sessions` | Sign out everywhere; reissues current cookie |
| `/auth/request-magic-link` | POST | `MagicLinkPage` | Silent on unknown emails |
| `/auth/login-with-token` | POST | `MagicLinkPage` | 15-min single-use |
| `/auth/delete-account` | POST | `AccountSettings` | Password re-supplied; cascade |

### Orgs

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
| `/api/orgs/current/leave` | POST | _future_ | Last-owner protection |
| `/api/orgs/current/audit` | GET | `TeamSettings` | owner only |
| `/api/orgs/current/audit.csv` | GET | `TeamSettings` (download link) | owner only; RFC 4180 |
| `/api/orgs/current` | DELETE | `TeamSettings` danger zone | owner only; name + password confirm |

### Simulation (gated by current org)

| Backend route | Method | Frontend caller | Notes |
|--------------|--------|----------------|-------|
| `/api/portfolio` | GET | `Portfolio.tsx` via `fetchPortfolio()` | On mount |
| `/api/site` | GET | `useSimulation.ts` via `fetchSite()` | On mount + reload |
| `/api/site/load-seed` | POST | `LiveContext.switchProject` (called by `MenuBar` project popover, `Portfolio.tsx`, `CommandPalette`) | Stock-project switcher; no-op when slug already active |
| `/api/recommendations` | GET | `LiveContext.tsx` | 5s polling, exposed to consumers via `useLive().recommendations` |
| `/api/recommendations/{id}/apply` | POST | `Recommendations.tsx`, `CommandPalette` | On click |
| `/api/recommendations/apply-all` | POST | `Recommendations.tsx` | On click |
| `/api/assets/{id}` | GET | `AssetDetail.tsx` | 1.5s polling when selected |
| `/api/simulation/speed` | POST | `LiveContext.setSpeed` (called by `MenuBar` + `CommandPalette`) | On speed button click |
| `/api/simulation/pause` | POST | `LiveContext.togglePaused` (called by `MenuBar` + `CommandPalette`) | On pause button click |
| `/api/simulation/state` | GET | *unused by frontend* | Exists as fallback |
| `/api/simulation/heatmap` | GET | `SiteMap.tsx` (when toggled) | Sparse density grid, daily reset |
| `/api/cameras` | GET | `SiteMap.tsx` inline fetch | When cameras toggle enabled |
| `/ws` | WS | `useWebSocket.ts` | 10 Hz sim state stream; cookie + Origin checked at upgrade |
| `/ws/camera/{id}` | WS | `CameraFeed.tsx` | ~5 Hz YOLO frame stream; same auth |

### Projects (editor)

| Backend route | Method | Frontend caller |
|--------------|--------|-----------------|
| `/api/projects` | GET | `ProjectListPage`, `MenuBar` (project switcher popover), `CommandPalette` |
| `/api/projects` | POST | `ProjectListPage` (Create / Duplicate) |
| `/api/projects/{id}` | GET | `useProjectDraft` |
| `/api/projects/{id}` | PUT | `useProjectDraft` (autosave, `If-Match`) |
| `/api/projects/{id}` | DELETE | _no UI yet, exposed for completeness_ |
| `/api/projects/{id}/activate` | POST | `ProjectListPage`, `ProjectEditorPage` (header) |
| `/api/projects/{id}/validate` | POST | `useProjectDraft` (debounced) |
| `/api/projects/{id}/preview` | POST | `PreviewRunPanel` |
| `/api/projects/{id}/levels/{level_id}/background` | POST | `LevelManager` (📐 button) |
| `/api/projects/{id}/levels/{level_id}/background` | DELETE | `LevelManager` (clr) |
| `/api/projects/{id}/assets/{asset_id}` | GET | `EditorCanvas` + `SiteMap` background draw |

### System of record (gated by current org)

| Backend route | Method | Frontend caller | Notes |
|--------------|--------|----------------|-------|
| `/api/record/events` | GET | `RecordLedger` via `recordApi.listEvents` | Filters: subject/kind/source/status/time |
| `/api/record/days` | GET | `RecordTimeline` | Per-day rollup for the day selector |
| `/api/record/timeline` | GET | `RecordTimeline` | `?date=YYYY-MM-DD`; one day's events |
| `/api/record/entities/{type}/{id}` | GET | (entity drill-in) | Projection + per-type metrics |
| `/api/record/inbox` | GET | `RecordInbox` | Proposed events awaiting confirmation |
| `/api/record/events/{id}/confirm` | POST | `RecordInbox` | member+ |
| `/api/record/events/{id}/reject` | POST | `RecordInbox` | member+ |
| `/api/record/events` | POST | (manual entry) | member+; high-trust path |
| `/api/record/costs` | GET | `RecordCosts` | `CostBreakdown` projection |
| `/api/record/verify` | GET | `RecordLedger` | Hash-chain integrity badge |
| `/api/record/capture` | POST | `RecordPage` capture bar | member+; text → proposed events |
| `/api/record/query` | POST | `RecordAsk` | Conversational, read-only |
| `/api/record/demo/generate` | POST | `RecordPage` (admin) | Regenerate demo history |

### Dev only (`SITEIQ_ENV=dev`)

| Backend route | Method | Purpose |
|--------------|--------|---------|
| `/dev/outbox` | GET | Lists last 100 emails |
| `/dev/outbox/{id}/html` | GET | Renders HTML body |

## Target waste metrics (tuned and verified)

| Category | Daily | Monthly | Target range |
|----------|-------|---------|-------------|
| Toilet walks | ~€875 | ~€19K | €800–1,200/day |
| Material handling | ~€600 | ~€13K | €400–700/day |
| Equipment idle | ~€2,200 | ~€48K | €1,200–2,200/day |
| **Total** | **~€3,700** | **~€81K** | **€2,400–4,100/day** |

After applying all optimizations: waste drops ~40–65% depending on
project.
