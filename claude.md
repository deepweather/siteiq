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

1. **Camera feeds are disconnected from simulation** — the core coherence problem. See architecture section.
2. **Timeline lookahead is hardcoded** — static text, not driven by simulation state. Damages trust if questioned.
3. **`_find_nearest_facility` in travel.py** — defined but never called.
4. **`MetricCard.tsx`** — defined but never imported (dead code).
5. **`vision/__init__.py`** exists but backend exploration noted it may be missing — verify if import issues arise.
6. **No tests** — `tests/__init__.py` exists but is empty.
7. **Portfolio waste estimates are rough** — uses `workers * 50 * 0.12 * 22 + equipment * 150 * 0.4 * 11 * 22`, not actual simulation data.
8. **CORS hardcoded** to localhost:5173 and :5174 only.
9. **Single-threaded YOLO inference** in the async event loop — blocks the sim tick while processing video frames. Should run in a thread pool.
10. **No auth, no persistence, no database** — demo only. All state is in-memory and resets on restart.

## Target waste metrics (tuned and verified)

| Category | Daily | Monthly | Target range |
|----------|-------|---------|-------------|
| Toilet walks | ~€875 | ~€19K | €800-1,200/day |
| Material handling | ~€600 | ~€13K | €400-700/day |
| Equipment idle | ~€2,200 | ~€48K | €1,200-2,200/day |
| **Total** | **~€3,700** | **~€81K** | **€2,400-4,100/day** |

After applying all optimizations: waste drops ~40-65% depending on project.
