# SiteIQ — Claude Context

## What this is

SiteIQ is an interactive demo of a construction site intelligence product. The thesis: construction sites are catastrophically inefficient — workers are productive only 35% of their time. SiteIQ uses cameras + CV to observe everything on a site, quantify waste in euros, and prescribe specific operational fixes.

For this demo, a **simulation engine** replaces real camera feeds. The simulation generates the same data that real CV would. The demo must make an investor or construction executive viscerally understand the waste and see it fixed in real time — in under 3 minutes, no narration needed.

## Architecture overview

Two disconnected systems exist today:

```
SIMULATION (the demo)                    VISION (disconnected proof-of-concept)
┌──────────────────────┐                 ┌─────────────────────────┐
│ SimulationEngine     │                 │ VideoDetector           │
│ - 50 workers FSM     │                 │ - YOLOv8n on .mp4 files │
│ - equipment duty     │                 │ - base64 JPEG frames    │
│   cycles             │    NO LINK      │ - bounding box coords   │
│ - position trails    │◄──────────────►│ - confidence scores     │
│ - analytics/waste    │                 │                         │
│ - recommendations    │                 │ Serves: /ws/camera/{id} │
│                      │                 └─────────────────────────┘
│ Serves: /ws (10Hz)   │
│         /api/*       │
└──────────────────────┘
         │
         ▼
┌──────────────────────┐
│ Frontend             │
│ - Canvas site map    │
│ - Waste/Optimize/    │
│   Timeline panels    │
│ - Asset detail       │
│ - Portfolio view     │
│ - Camera feeds       │◄── Shows real video with real YOLO boxes,
│                      │    but detections have ZERO relationship
└──────────────────────┘    to the simulation workers
```

**This is the core architectural problem.** The camera feeds and the simulation are not synchronized. A "Worker 34%" detection in the video corresponds to nobody on the 2D map. The product story is "cameras → intelligence → decisions" but the demo shows two unrelated systems side by side.

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
| Backend | Python 3.13, FastAPI, uvicorn, WebSocket, Pydantic v2 |
| Frontend | React 19, Vite 8, TypeScript 6, Tailwind CSS 3, HTML5 Canvas |
| CV | ultralytics (YOLOv8n), opencv-python-headless |
| Package mgmt | uv (backend), npm (frontend) |
| Real-time | WebSocket at 10Hz for sim state, ~5Hz for camera frames |

## Running the app

```bash
# Backend
cd backend
uv sync
uv run uvicorn main:app --host 0.0.0.0 --port 8000

# Frontend
cd frontend
npm install
npm run dev
# → http://localhost:5173
```

Camera feeds require .mp4 files in `backend/vision/videos/`. Two Pexels CC0 videos are downloaded but gitignored. YOLO model weights (`yolov8n.pt`) auto-download on first run.

## Backend modules

### `config.py`
All simulation constants. Key tunables: `TOILET_INTERVAL` (7200s = 2h), `MATERIAL_RUN_INTERVAL` (7200s), equipment hourly rates (€180/120/90 for crane/pump/excavator), `SIM_SECONDS_PER_TICK` (30 — each 100ms real tick = 30s sim time at 1x speed).

### `models/`
Pydantic v2 schemas. `Site` has zones + schedule. `Asset` has position, state, metadata. `WasteSummary` aggregates costs. `Recommendation` has from/to positions and savings.

`Asset.to_broadcast_dict()` produces the compact WebSocket payload — flat dict with id, type, subtype, x, y, state, assigned_zone.

### `simulation/`
- **`site_factory.py`** — `PROJECT_TEMPLATES` dict with 3 German construction projects (residential Berlin, commercial Frankfurt, infrastructure Munich). Each defines zones, facilities, equipment, materials, schedule, and worker counts. `create_site_from_template(project_id)` instantiates a full simulation state.

- **`engine.py`** — `SimulationEngine` runs the tick loop. Manages position_history (deque per worker, max 150), activity_log (deque per asset, max 50). `tick()` updates all workers and equipment per `dt_sim`. `get_state_snapshot()` returns the WebSocket broadcast payload. `get_asset_detail()` returns rich per-asset data for the detail panel. `load_project()` hot-swaps the entire simulation.

- **`worker_behavior.py`** — Worker FSM: WORKING → WALKING_TO_TOILET/MATERIAL/BREAK → AT_TOILET/CARRYING_MATERIAL/AT_BREAK → WALKING_TO_WORK → WORKING. Tracks cumulative time_working/walking/at_facilities, trip counts, round-trip times. All counters reset daily in `_reset_daily_counters()`. Logs state transitions via `engine.log_activity()`.

- **`equipment_behavior.py`** — Simpler: alternates OPERATING ↔ IDLE based on duty cycles (crane 40min/30min, pump 10min/40min, excavator 42min/18min). Tracks hours_active/hours_idle.

### `analytics/`
- **`travel.py`** — Per-zone metrics: avg toilet round-trip, trips/day, daily walk cost (trips × RT × hourly_rate), productivity rate. Extrapolates partial-day data via `day_fraction`.
- **`utilization.py`** — Per-equipment: utilization rate, daily idle cost (normalized to 11h workday × idle_fraction × rate).
- **`aggregator.py`** — Combines travel + equipment into `WasteSummary` with daily and monthly totals.

### `optimization/`
- **`facility_placement.py`** — Weighted k-means (k=2) on zone centers to find optimal toilet positions. Computes distance savings → time savings → euro savings.
- **`material_staging.py`** — For each material >20m from target zone, finds nearest zone edge for restaging. Savings = distance_saved × 2 (round trip) / worker_speed × trips × hourly_rate.
- **`equipment_schedule.py`** — Flags equipment <40% utilization for release, <60% for rescheduling. Savings based on idle hours × rate.

### `api/`
- **`routes.py`** — REST: GET /api/site, /api/recommendations, /api/assets/{id}, /api/projects, /api/portfolio. POST: apply recs, set speed, pause, load project.
- **`websocket.py`** — WS /ws streams state_update at 10Hz with assets + trails + analytics (analytics only non-null every ~1s).
- **`camera.py`** — GET /api/cameras lists video feeds. WS /ws/camera/{video_id} streams YOLO-processed frames at ~5Hz.

### `vision/`
- **`detector.py`** — `VideoDetector` wraps YOLOv8n. Loads all .mp4 from vision/videos/, reads frames with OpenCV, runs inference (conf=0.20), returns base64 JPEG + normalized bounding boxes. CLASS_REMAP maps COCO classes to construction labels ("person" → "Worker"). ~18ms inference per frame on Apple Silicon.

## Frontend modules

### State management
- `useWebSocket` — connects to ws://localhost:8000/ws, stores assets + trails in **refs** (not state) for canvas performance. Only analytics, simTime, simDay trigger React re-renders.
- `useSimulation` — fetches /api/site on mount. `reload()` re-fetches after project switch.
- `useAnalytics` — captures first analytics as baseline, computes savings delta. `resetBaseline()` clears on project switch.
- Recommendations fetched in `App.tsx` via useEffect + 5s polling (not inside the Optimize tab component).

### Canvas rendering (`renderer.ts`, 769 lines)
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

### Bugs (verified by reading every route handler and data flow)

1. **Recommendation cache not cleared on project switch.** `routes.py:load_project()` clears `_recommendations_cache` (a dead module-level var in routes.py, line 8) but the real cache is `cached_recommendations` in `main.py`. The `recs_dirty` flag only flips on the next analytics tick (~1s later). Between project load and that tick, stale recs from the old project can be served. Fix: `main.py:get_recommendations()` should check `engine.project_id` matches the cached project, or `load_project` should call a clear function in main.py.

2. **YOLO inference blocks the async event loop.** `camera.py` line 36 calls `_detector.get_next_frame()` synchronously (~18ms of OpenCV + YOLO per frame, per connected camera). During inference, the entire FastAPI event loop stalls — sim WebSocket pushes, REST endpoints, everything. Fix: wrap in `asyncio.to_thread()`.

3. **No fetch error handling in frontend.** Every function in `api.ts` does `fetch(url).then(r => r.json())` without checking `r.ok` or `r.status`. A backend 500 or network error returns `undefined` which propagates silently through the UI. Any transient failure (e.g., during project switch) can put components into broken states.

### Frontend bugs (verified by reading every component)

4. **`justAppliedAll` never resets in `Recommendations.tsx`.** Set to `true` on Apply All (line 27), never set back to `false`. The celebration card stays visible forever — survives rec refreshes and project switches. Only clears on full page reload.

5. **Three hardcoded `localhost:8000` URLs outside `api.ts`.** `useWebSocket.ts` line 28 (`ws://localhost:8000/ws`), `CameraFeed.tsx` (`ws://localhost:8000/ws/camera/...`), `SiteMap.tsx` line 32 (`http://localhost:8000/api/cameras`). The `API_BASE` constant in `api.ts` is not shared with these.

6. **WebSocket reconnect can create duplicate connections.** `useWebSocket.ts` line 26 checks `readyState === OPEN` but a WS in `CONNECTING` state (0) passes the guard, allowing a second `new WebSocket()` before the first resolves.

7. **`handlePortfolioSelect` in `App.tsx` ignores its `projectId` parameter.** Line 50-53: receives `projectId` but only calls `handleProjectChange()` which doesn't use it. The project was already loaded in `Portfolio.tsx` via `loadProject(id)`, so it works, but the parameter is dead.

8. **Portfolio ROI uses hardcoded 0.65 recovery factor.** `Portfolio.tsx` line 89: `totalWaste * 0.65 / systemCostTotal`. This magic number is disconnected from actual optimization savings.

### Renderer bugs (`renderer.ts`)

9. **`ctx.measureText` before `ctx.font` in zone labels.** Line 150 measures text with the font from the previous draw call, not the zone label font set on line 154. Zone label backgrounds may be wrong width.

10. **Module-level mutable state (`S`, `OX`, `OY`).** Lines 12-14 — global variables stomped on every `renderFrame` call. Would break if two canvases rendered simultaneously.

### Simulation logic bugs

11. **Worker gets permanently stuck if no facility exists.** `worker_behavior.py` lines 84-116: if `_find_nearest` returns `None`, the timer check passes but the `return` still executes. The timer stays negative forever, so the worker can never reach the material or break checks below. Every tick hits the same failing toilet check and returns.

12. **k-means toilet assignment is order-based, not distance-based.** `facility_placement.py` line 69: toilet-1 always gets cluster 0, toilet-2 gets cluster 1, regardless of which toilet is closer to which cluster centroid. Can recommend longer moves than necessary.

### Timeline bugs

13. **Timeline hardcodes zone IDs and TOTAL_DAYS=120.** `Timeline.tsx` lines 9-16: zone IDs are `['zone-a'...'zone-e']` — misses `zone-f` in Frankfurt. Labels show "Zone A" instead of actual zone names ("Turm Ost"). TOTAL_DAYS=120 overflows for the Munich bridge project (runs to day 210, current day 135 is off-screen).

### Additional frontend issues

14. **CameraFeed RAF loop restarts 5x/sec.** `useEffect` deps include `detectionCount` and `inferenceMs` (state), which update on every WS message. The effect tears down and recreates the RAF loop each time, causing flicker. Should use refs.

15. **CameraFeed has no WebSocket reconnection.** If the WS closes, the feed dies permanently. No retry logic.

16. **AssetDetail zone name is reformatted ID, not actual label.** `zone-a` becomes "ZONE A" instead of the zone's real label.

17. **MaterialDetail zone name regex doesn't capitalize zone letter.** `'zone-c'.replace('zone-', 'Zone ').replace(/^\w/, ...)` produces "Zone c" — the regex only matches the start of string ("Z"), not the zone letter.

18. **EquipmentDetail duty cycle progress bar is wrong during idle.** `cycle_timer_s / operate_duration_s` — during idle phase the timer counts toward `idle_duration_s` but divides by `operate_duration_s`. Exceeds 100% for equipment with idle > operate duration.

19. **`onMouseUp` doesn't restore cursor to `grab`.** Cursor stays `grabbing` after mouseup until the next mousemove triggers hover check.

20. **`onMouseMove` registered on both canvas AND window.** Double hit-test on every mouse move when over canvas (iterates 62 assets twice at 60fps).

21. **`AssetUpdate` type missing `assigned_zone`.** Backend sends it, frontend type doesn't declare it.

22. **`formatCurrencyCompact` exported but never used.**

### Backend logic issues found on full read

23. **`equipment_schedule.py` `daily_idle_hours` formula is unstable.** `hours_idle * (11.0 / total)` — when `total` is small (early sim), this inflates massively. Should use `(1 - utilization) * 11.0`.

24. **`equipment_schedule.py` hardcodes fallback zone "D".** `asset.assigned_zone or 'D'` — equipment never has `assigned_zone` set, so every equipment description says "Zone D".

25. **`material_staging.py` picks zone edge nearest to center, not to material.** The "optimal" position is always the edge with the shortest distance to the zone's own center, which is always the shorter dimension. Should minimize distance from material's current position or from workers.

26. **Facility detail only checks toilet/breakroom.** `get_asset_detail` office and toolcrib subtypes never match any condition, so `workers_present` is always empty for them.

27. **`EquipmentState.REPOSITIONING` defined but never used.** Dead enum value.

28. **`Recommendation.from_position` and `to_position` are untyped `dict`.** Should be `dict[str, float]` or a proper model.

### Dead code

16. **`CONSTRUCTION_CLASSES` dict in `detector.py`** (lines 11-22) — defined but never referenced.
17. **`_recommendations_cache` in `routes.py`** (line 8) — declared and cleared in `load_project` but never read.
18. **`_find_nearest_facility` in `travel.py`** — defined but never called.
19. **`MetricCard.tsx`** — component defined but never imported.

### Architectural debt

8. **Camera feeds are disconnected from simulation** — the core coherence problem. See architecture section above.
9. **Timeline lookahead is hardcoded** — static text in `Timeline.tsx`, not driven by simulation state. Damages trust if questioned.
10. **Portfolio waste estimates are rough** — uses a fixed formula (`workers * 50 * 0.12 * 22 + equipment * 150 * 0.4 * 11 * 22`), not actual simulation data per project.
11. **CORS hardcoded** to localhost:5173 and :5174 only.
12. **No tests** — `tests/__init__.py` exists but is empty.
13. **No auth, no persistence, no database** — demo only. All state is in-memory and resets on restart.

### API route → frontend mapping (verified)

| Backend route | Method | Frontend caller | Notes |
|--------------|--------|----------------|-------|
| `/api/projects` | GET | `TopBar.tsx` via `fetchProjects()` | On mount |
| `/api/projects/{id}/load` | POST | `TopBar.tsx` via `loadProject()` | On project switch |
| `/api/portfolio` | GET | `Portfolio.tsx` via `fetchPortfolio()` | On mount |
| `/api/site` | GET | `useSimulation.ts` via `fetchSite()` | On mount + reload |
| `/api/recommendations` | GET | `App.tsx` via `fetchRecommendations()` | 5s polling |
| `/api/recommendations/{id}/apply` | POST | `Recommendations.tsx` via `applyRecommendation()` | On click |
| `/api/recommendations/apply-all` | POST | `Recommendations.tsx` via `applyAllRecommendations()` | On click |
| `/api/assets/{id}` | GET | `AssetDetail.tsx` via `fetchAssetDetail()` | 1.5s polling when selected |
| `/api/simulation/speed` | POST | `TopBar.tsx` via `setSimSpeed()` | On speed button click |
| `/api/simulation/pause` | POST | `TopBar.tsx` via `togglePause()` | On pause button click |
| `/api/simulation/state` | GET | *unused by frontend* | Exists as fallback, never called |
| `/api/cameras` | GET | `SiteMap.tsx` inline fetch | When cameras toggle enabled |
| `/ws` | WS | `useWebSocket.ts` | 10Hz sim state stream |
| `/ws/camera/{id}` | WS | `CameraFeed.tsx` | ~5Hz YOLO frame stream |

## Target waste metrics (tuned and verified)

| Category | Daily | Monthly | Target range |
|----------|-------|---------|-------------|
| Toilet walks | ~€875 | ~€19K | €800-1,200/day |
| Material handling | ~€600 | ~€13K | €400-700/day |
| Equipment idle | ~€2,200 | ~€48K | €1,200-2,200/day |
| **Total** | **~€3,700** | **~€81K** | **€2,400-4,100/day** |

After applying all optimizations: waste drops ~40-65% depending on project.
