# Changelog

Historical bug fixes, refactors, and closed debt. Preserved here so the
agent-facing `claude.md` can focus on the live architecture. Each entry
keeps its original bug description so the fix has context — if you find
yourself tempted to undo any of these, read the entry first.

For the actual diffs, use `git log -p`. This file is a curated index, not
a substitute for git.

---

## 2026-06 — Project list audit fixes (second handoff round)

Six bugs surfaced by a second walkthrough; all went through the React
click path, not the fetch fixture, which is why the unit tests missed
them. Fixed in `eb6947f`.

- **`pages/projects/ProjectListPage.tsx`** — `+ New project` and the
  `Duplicate` button used `window.prompt()`, which silently no-ops in
  embedded browsers / the Cursor MCP webview and is 1998-grade UX
  everywhere else. Replaced with an inline `ProjectModal` (slug + name
  inputs, client-side validation mirroring the server's
  `/^[a-z][a-z0-9-]*$/` slug rule + collision check, auto-disabled
  Create button, backdrop blur, click-outside cancel). The duplicate
  flow auto-fills `{source.slug}-copy-{N}` so the user never lands on
  a 409.
- **`api/projects.py`** — added `is_active: bool` to every
  `ProjectListItem`. True when the project's `current_version_id`
  matches `org.active_project_version_id`, OR (legacy path) the
  project's slug matches `org.active_project_id` when the version
  pointer isn't set. Without this the project-list UI couldn't tell
  the user which Activate button is the destructive one.
- **`pages/projects/ProjectListPage.tsx`** — renders a green `● Active`
  pill on the active card, swaps its border for `border-primary/60
  ring-1 ring-primary/20`, and the Activate button becomes a disabled
  "Activated". Clicking the disabled button just navs back to `/app`
  instead of hitting the activate endpoint.
- **`state/registry.py`** — `for_org_at_version` previously rebuilt the
  engine whenever `engine.project_version_id != version_id`. But legacy
  seed-loaded engines (`for_org('munich-sewer')`) carry
  `project_version_id = None`, so any subsequent activate-call
  mis-detected them as stale and tore the engine down — wiping applied
  recommendations, the sim day, every per-worker timer. Registry now
  tags the engine in place when its slug + null version match the
  document being activated, instead of rebuilding. The seed importer is
  idempotent on content hash, so a slug-equal engine is, by
  construction, running the same document.
- **`api/routes.py`** — `POST /api/site/load-seed` had the same
  destructive behaviour (called `engine.load_project` unconditionally
  even when the slug was already active). Now skipped when
  `source.project_id == req.slug`.
- **`components/editor/EditorCanvas.tsx`** — extended the
  collision-avoidance pattern from `renderer.ts` into the editor
  canvas, where Munich's linear Kanalsanierung otherwise mashed
  half-a-dozen subtype labels into one strip. Selected markers' labels
  are always painted so the cursor target never disappears.
- **`pages/settings/TeamSettings.tsx`** — audit-log payload column was
  printing raw JSON (`{"project_id":"9b681...","version_id":"..."}`)
  that scrolled off the card. Added `formatAuditPayload` that folds
  SHA-256 + UUID values to their first 8 chars and joins keys with
  `·`, e.g. `project_id=9b681a37 · version_id=a3999e92`.

Regression tests added: `test_project_list_marks_active_project`,
`test_reactivate_same_version_preserves_engine_state`,
`test_reactivate_seed_after_slug_load_preserves_engine`.

---

## 2026-06 — Dashboard UX polish (post-handoff fixes)

Layout + readability bugs the unit tests didn't catch.

- **`TopBar.tsx`** — the three-column flexbox previously let the left
  cluster (logo / Portfolio / Projects / Settings) grow into the
  centred sim clock, wrapping "7:24 AM" to two lines and visually
  stacking the Settings button on top of it. Each cluster now uses
  `shrink-0` + `whitespace-nowrap`, the centre group has `min-w-0` +
  nowrap, and the right cluster's project-name button truncates rather
  than pushing the clock out.
- **`SiteMap/LevelSwitcher.tsx`** — moved from `top-2 right-2` to
  `top-2 left-2`. Renderer paints its trade / Active / Idle legend in
  the top-right corner, so a right-aligned switcher visibly overlapped
  that legend.
- **`components/common/ToastContainer.tsx`** — each tone used to apply
  `bg-card` + `bg-X/5`, and because Tailwind orders the later class
  last, the 5%-alpha tint clobbered the card background, leaving the
  toast looking transparent / "unstyled" against the canvas. We now
  keep `bg-card` as the substrate (solid white in light mode) and
  convey the tone via the border (`border-X/40`) and the icon chip
  (`bg-X/15`) only.
- **`SiteMap/renderer.ts`** — three additions:
  1. Zone labels were drawn during `drawZoneStructures` (early in the
     pipeline), so equipment markers placed near a zone's top-left
     corner painted on top of the label pill. Extracted to
     `drawZoneLabels`, called as the very last asset-layer step so the
     pill always sits on top, and the pill background is now fully
     opaque (was 85%-alpha so equipment bled through).
  2. `drawEquipmentTopDown` previously drew every label without overlap
     detection — Munich's 4 sheet piles + 2 dewatering pumps + crane
     (~200 m strip) all stacked their `sheet_pile ACTIVE` labels. Added
     a per-call painted-rectangle list; new labels are skipped if they
     would overlap an existing one. Same dodge for `drawMaterialStacks`
     and the recommendation cost chips inside `drawRecommendationArrows`.
  3. Extended the `LABELS` table with friendly names for `sheet_pile`
     ("SHORING") and `dewatering_pump` ("PUMP") instead of falling back
     to the raw subtype string.

These changes raise `renderer.ts` from ~768 LOC to ~970 LOC; the
Phase-6 lock-in rule that kept it untouched during the editor build is
now relaxed for documented bug fixes.

---

## 2026-06-21 — Resolved during the auth + ops sweep

- ~~**CORS hardcoded** to localhost:5173/5174~~ — `SITEIQ_CORS_ORIGINS`
  (comma-separated env var) drives the allow-list.
- ~~**No tests** — empty `tests/__init__.py`~~ — backend at 192+ tests
  across 22 suites, frontend at 52.
- ~~**No auth, no persistence, no database**~~ — full self-hosted auth
  + SQLAlchemy / Alembic / SQLite-or-Postgres + audit log.
- ~~**Per-org engines deferred**~~ — `state/registry.py` keys engines
  by `org_id`, lazy creation, `Depends(get_source)` resolves through
  the active org.
- ~~**No account / workspace deletion UI**~~ — `POST /auth/delete-account`
  + `DELETE /api/orgs/current`, both with password confirmation; UI
  under Settings → Account / Team danger zones.
- ~~**Timeline lookahead hardcoded**~~ — `Timeline.tsx` now derives the
  next 30 days of phase transitions from the schedule + currentDay.
- ~~**Portfolio waste from a fixed formula**~~ — `services/portfolio_estimator.py`
  warms each project template at startup and caches the real
  `compute_waste_summary` output.
- ~~**No prod deployment story**~~ — `backend/Dockerfile` (multi-stage
  uv), `frontend/Dockerfile` (Vite → nginx), `docker-compose.yml` with
  Postgres.
- ~~**No security headers**~~ — `api/security_headers.py` adds CSP,
  X-Frame, Referrer-Policy, Permissions-Policy, X-CTO; HSTS in prod.
- ~~**No rate limits**~~ — slowapi on `/auth/login` (10/min),
  `/auth/signup` + `/auth/forgot-password` (5/hr), Redis-ready storage.
- ~~**No password breach check**~~ — HIBP k-anonymity in `PasswordField`
  (only first 5 hex of SHA-1 leaves the browser).
- ~~**Email outbox grew forever**~~ — periodic cleanup task with
  configurable TTL.
- ~~**No health endpoints**~~ — `/healthz` + `/readyz` (DB ping +
  registry check); Dockerfile healthcheck switched to `/readyz`.
- ~~**Frontend was a single 434 KB bundle**~~ — `React.lazy` route
  splits; entry chunk down to 243 KB, individual pages 1–8 KB.
- ~~**Silent UI errors took down the whole app**~~ — top-level
  `ErrorBoundary` shows a recovery card with the stack and a Reload
  button.
- ~~**WS drops were silently shown as a colored pill**~~ —
  `useConnectionToast` shows "Reconnecting…" / "Live again" after a
  grace window.
- ~~**Password-only login**~~ — magic-link via `/auth/request-magic-link`
  + `/auth/login-with-token`, 15-min single-use tokens.
- ~~**No audit log export**~~ — `GET /api/orgs/current/audit.csv` with
  `since` / `until` query params (RFC 4180, owner-only).
- ~~**Auth tables grew forever**~~ — `auth/auth_cleanup.py` periodic
  task drops fully-revoked sessions + consumed tokens past their
  retention window.
- ~~**Backend restart reset every org's project to default**~~ —
  `orgs.active_project_id` (migration 0002) persists each org's choice.
- ~~**No request tracing**~~ — request-id middleware + structured
  logging filter; envelope carries `request_id` for support.
- ~~**Password meter chunk was 1.2 MB**~~ — direct-import only
  `commonWords + firstnames + wordSequences + adjacencyGraphs`. Net
  ~750 KB saved on the password-field lazy load.
- ~~**No version endpoint**~~ — `/api/version` returns commit + build
  time; surfaced in the SettingsLayout footer.

---

## 2026-06 — Editor & Multi-Level rebuild closed debt

- ~~**Per-org custom projects (debt #34)**~~ — `org_projects` is now
  `projects` + immutable `project_versions`. Editor lets owners +
  admins build their own sites end-to-end.
- ~~**Tiefbau wasn't a first-class discipline**~~ — `Discipline` enum,
  expanded `Phase`, sheet-pile + dewatering-pump subtypes,
  slope-stability KPI, Munich seed.
- ~~**Single-floor assumption baked into every layer**~~ — `Level` +
  `Position.level_id` + per-level indexes + vertical-transport FSM +
  per-level optimizers + level-switching renderer + iso exploded view.
- ~~**Promised editor features that don't exist (#8–#11)**~~ —
  Preview Run, Gantt schedule editor, background floor-plan upload,
  snap-to-grid. See `claude.md` "Editor v2" for the live design.

---

## Original audit — bugs 1–32 (all fixed)

The original prose for each bug is preserved so the `→ Fix:` note has
context.

### Backend / API

1. **Recommendation cache not cleared on project switch.**
   `routes.py:load_project()` cleared `_recommendations_cache` (a dead
   module-level var) but the real cache was `cached_recommendations` in
   `main.py`. The `recs_dirty` flag only flipped on the next analytics
   tick (~1 s later), so stale recs from the old project leaked.
   → Fix: `main.py` exposes `clear_recommendations_cache()`, passed
   into `init_routes`. `routes.load_project` calls it on switch.
   `get_recommendations()` also re-checks `engine.project_id` against a
   cached `cached_project_id` and forces a refresh on mismatch. Dead
   `_recommendations_cache` var removed.

2. **YOLO inference blocks the async event loop.** `camera.py` called
   `_detector.get_next_frame()` synchronously (~18 ms of OpenCV + YOLO
   per frame, per connected camera). During inference the entire
   FastAPI event loop stalled — sim WebSocket pushes, REST endpoints,
   everything.
   → Fix: `camera.py` now runs `_detector.get_next_frame` via
   `asyncio.to_thread()`. Guarded by `tests/test_event_loop.py`.

3. **No fetch error handling in frontend.** Every `api.ts` function did
   `fetch(url).then(r => r.json())` without checking `r.ok`. A backend
   500 or network error returned `undefined` and propagated silently.
   → Fix: shared `getJson<T>()` / `postJson()` helpers in `api.ts`
   throw on non-2xx. All call sites already used `.catch()`.

### Frontend

4. **`justAppliedAll` never resets in `Recommendations.tsx`.** Set to
   `true` on Apply All, never set back. The celebration card stayed
   visible forever, surviving rec refreshes and project switches.
   → Fix: replaced boolean with a `celebrationSig` (the recommendation-set
   signature captured when Apply-All ran). Visible only while the
   current recsSignature still matches; auto-clear timer at 8 s.

5. **Three hardcoded `localhost:8000` URLs outside `api.ts`.**
   `useWebSocket.ts`, `CameraFeed.tsx`, `SiteMap.tsx`.
   → Fix: `api.ts` exports `API_BASE` and `WS_BASE`; all three
   consumers import them. Single source of truth.

6. **WebSocket reconnect can create duplicate connections.**
   `useWebSocket.ts` checked `readyState === OPEN` but a WS in
   `CONNECTING` state (0) passed the guard.
   → Fix: guard now skips when an existing socket is OPEN *or*
   CONNECTING.

7. **`handlePortfolioSelect` in `App.tsx` ignores its `projectId`
   parameter.**
   → Fix: parameter removed from the implementation (TS allows fewer
   params than the prop signature). Comment explains that `Portfolio.tsx`
   calls `loadProject(id)` before invoking the callback.

8. **Portfolio ROI uses hardcoded 0.65 recovery factor.**
   → Fix: extracted to `RECOVERABLE_WASTE_FRACTION = 0.55` (centered on
   the doc'd 40–65% post-apply reduction range) + `SYSTEM_COST_PER_SITE
   = 2000`.

### Renderer

9. **`ctx.measureText` before `ctx.font` in zone labels.**
   → Fix: reordered — `ctx.font` set first, then `measureText`. Label
   backgrounds now size correctly.

10. **Module-level mutable state (`S`, `OX`, `OY`) in `renderer.ts`.**
    Would break if two canvases rendered simultaneously.
    → Mitigated, not fixed: full refactor would touch 68 call sites.
    The invariant is documented in `renderer.ts` itself at the
    declaration site (synchronous render, single-threaded JS, reset at
    the top of every `renderFrame`). If a second renderer instance is
    ever added, pass `{S, OX, OY}` explicitly through the draw helpers.

### Simulation

11. **Worker gets permanently stuck if no facility exists.** Timer
    stayed negative forever.
    → Fix: when `_find_nearest` returns `None`, the timer is re-jittered
    to a fresh positive value before returning.

12. **k-means toilet assignment is order-based, not distance-based.**
    → Fix: toilets are greedily paired to their *nearest* cluster
    centroid; sort+nearest-pair pass replaces `enumerate(toilets)`.

### Timeline

13. **Timeline hardcodes zone IDs and TOTAL_DAYS=120.**
    → Fix: `Timeline.tsx` takes `zones` as a prop and derives the zone
    list. `TOTAL_DAYS = max(schedule.end_day, currentDay + 5, 120)`, so
    the Munich bridge (day 210) renders correctly.

### Additional frontend

14. **CameraFeed RAF loop restarts 5×/sec.** `useEffect` deps included
    `detectionCount` and `inferenceMs`.
    → Fix: stats moved into refs; deps reduced to `[connected, label]`.

15. **CameraFeed has no WebSocket reconnection.**
    → Fix: same exponential-backoff reconnect loop as `useWebSocket`
    (1 s → 10 s cap), cancelled on unmount.

16. **AssetDetail zone name is reformatted ID, not actual label.**
    → Fix: backend `engine.get_asset_detail()` emits
    `assigned_zone_label` + `needed_in_zone_label`. Frontend prefers the
    label, falls back to the ID.

17. **MaterialDetail zone name regex doesn't capitalize zone letter.**
    → Fix: superseded by #16.

18. **EquipmentDetail duty cycle progress bar is wrong during idle.**
    → Fix: cycle denominator now switches between `operate_duration_s`
    / `idle_duration_s` based on `data.state`.

19. **`onMouseUp` doesn't restore cursor to `grab`.**
    → Fix: `onMouseUp` resets `canvas.style.cursor = 'grab'`.

20. **`onMouseMove` registered on both canvas AND window.**
    → Fix: dropped the canvas-level listener.

21. **`AssetUpdate` type missing `assigned_zone`.**
    → Fix: added `assigned_zone?: string` to the interface.

22. **`formatCurrencyCompact` exported but never used.**
    → Fix: removed.

### Backend logic

23. **`equipment_schedule.py` `daily_idle_hours` formula is unstable.**
    → Fix: replaced `hours_idle * (11.0 / max(total, 0.1))` with
    `(1.0 - utilization) * WORKDAY_HOURS`. Stable from t=0.

24. **`equipment_schedule.py` hardcodes fallback zone "D".**
    → Fix: resolves the actual zone label via `engine.get_zone_by_id`,
    falling back to "its current zone" when none is assigned.

25. **`material_staging.py` picks zone edge nearest to center, not to
    material.**
    → Fix: candidates scored by distance from the material's current
    position.

26. **Facility detail only checks toilet/breakroom.**
    → Fix: per-subtype radius + required-state tables. `office` and
    `toolcrib` report any nearby worker.

27. **`EquipmentState.REPOSITIONING` defined but never used.**
    → Fix: removed.

28. **`Recommendation.from_position` and `to_position` are untyped
    `dict`.**
    → Fix: introduced `PositionXY` Pydantic model; route handler
    updated from `rec.to_position["x"]` → `rec.to_position.x`.

### Dead code removed

29. `CONSTRUCTION_CLASSES` dict in `detector.py`.
30. `_recommendations_cache` in `routes.py` (see #1).
31. `_find_nearest_facility` in `travel.py`.
32. `MetricCard.tsx`.
