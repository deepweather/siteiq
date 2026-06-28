import asyncio
from collections import defaultdict, deque

from config import (
    SIM_SECONDS_PER_TICK, WORKDAY_START, WORKDAY_END,
    MAX_TRAIL_LENGTH, SIM_TICK_INTERVAL,
)
from models.assets import Asset
from models.connection import Connection
from models.project_document import ProjectDocument
from simulation.density import DensityGrid
from simulation.event_emit import emit_end_of_day
from simulation.navmesh import NavMesh
from simulation.project_loader import build_engine_state
from simulation.site_factory import (
    create_site_from_template_with_connections,
)
from simulation.tiefbau_behavior import update_tiefbau_equipment
from simulation.vertical_transport import CabState, build_cabs, tick_cab
from simulation.worker_behavior import update_worker
from simulation.equipment_behavior import update_equipment


# Re-exported for tests / external callers that want the grid resolution
DENSITY_CELL_SIZE = 4


class SimulationEngine:
    # Backwards-compat alias for test_heatmap.py
    DENSITY_CELL_SIZE = DENSITY_CELL_SIZE

    def __init__(
        self,
        project_id: str = "westhafen",
        *,
        document: ProjectDocument | None = None,
        project_version_id: str | None = None,
    ):
        """Build an engine from either:
          - a slug (legacy: loaded from the seed bundle), or
          - a fully-formed `ProjectDocument` (new: loaded from the DB,
            optionally tagged with its content-addressed version id).
        """
        self.project_id = project_id
        # The content-addressed version id of the document the engine is
        # currently running, when known. Editor / activate flows set
        # this so the registry can detect "engine is on a stale version"
        # on the next access.
        self.project_version_id: str | None = project_version_id
        if document is not None:
            self._init_from_document(document)
        else:
            self._init_from_project(project_id)

    def _shared_init(self) -> None:
        self.sim_time: float = WORKDAY_START + 2 * 3600
        self.sim_day: int = self.site.current_day
        self.speed_multiplier: float = 1.0
        self.paused: bool = False
        self.position_history: dict[str, deque] = {}
        self.activity_log: dict[str, deque] = {}
        self.running: bool = True
        # System-of-record: discrete operational events emitted on state
        # transitions (NOT every tick). The drain loop in main.py flushes
        # this buffer into the ledger. Bounded so a stalled drain can't
        # grow it unboundedly. Transient/preview engines simply never get
        # drained and are GC'd with their buffer.
        self.pending_events: deque = deque(maxlen=50000)
        self._density = DensityGrid(cell_size=DENSITY_CELL_SIZE)
        # Live cab state for every elevator connection. Stairs have no
        # cab — workers traverse them with a flat time penalty.
        self.cabs: dict[str, CabState] = build_cabs(self.connections, self.site.levels)

        for a in self.assets:
            if a.type == "worker":
                self.position_history[a.id] = deque(maxlen=MAX_TRAIL_LENGTH)
            self.activity_log[a.id] = deque(maxlen=50)

        self._rebuild_indexes()

    def _init_from_project(self, project_id: str):
        self.site, self.assets, self.worker_internals, self.connections = (
            create_site_from_template_with_connections(project_id)
        )
        self._shared_init()

    def _init_from_document(self, document: ProjectDocument) -> None:
        self.site, self.assets, self.worker_internals, self.connections = (
            build_engine_state(document)
        )
        self._shared_init()

    def rebuild_indexes(self) -> None:
        """Public re-index entry point. Call after mutating `self.assets`
        directly (e.g. in tests). Project switches call this automatically."""
        self._rebuild_indexes()

    def _rebuild_indexes(self) -> None:
        """O(1) lookup tables. Rebuilt whenever the assets list is replaced
        (project switch, asset added/removed by an applied recommendation).

        Multi-level (Phase 2): facilities are pinned to their level at
        document-load time and never move, so we can also index them by
        `(subtype, level_id)`. Workers move between levels via
        `WALKING_TO_VERTICAL`/`TRAVERSING_VERTICAL`, so anything
        per-worker-per-level is computed on demand instead of cached.
        """
        self._by_id: dict[str, Asset] = {a.id: a for a in self.assets}
        self._by_type: dict[str, list[Asset]] = defaultdict(list)
        self._facilities_by_subtype: dict[str, list[Asset]] = defaultdict(list)
        self._facilities_by_subtype_level: dict[
            tuple[str, str], list[Asset]
        ] = defaultdict(list)
        self._workers_by_zone: dict[str, list[Asset]] = defaultdict(list)
        self._zone_by_id: dict[str, object] = {z.id: z for z in self.site.zones}
        self._level_by_id: dict[str, object] = {lv.id: lv for lv in self.site.levels}
        for a in self.assets:
            self._by_type[a.type].append(a)
            if a.type == "facility":
                self._facilities_by_subtype[a.subtype].append(a)
                self._facilities_by_subtype_level[(a.subtype, a.position.level_id)].append(a)
            if a.type == "worker" and a.assigned_zone:
                self._workers_by_zone[a.assigned_zone].append(a)
        # Connection-graph index (level_id -> list[Connection]).
        self._connections_by_level: dict[str, list[Connection]] = defaultdict(list)
        for c in self.connections:
            for n in c.nodes:
                self._connections_by_level[n.level_id].append(c)

        # Navmesh per level — workers route around equipment + along
        # roads instead of walking straight lines through cranes. Built
        # once here and invalidated on rec apply / project switch (both
        # paths funnel back through this method, so we don't need a
        # separate refresh hook).
        equipment = self._by_type.get("equipment", [])
        levels = self.site.levels if self.site.levels else [
            type("_L0", (), {"id": "L0"})()
        ]
        self.navmeshes: dict[str, NavMesh] = {
            lv.id: NavMesh.build(level_id=lv.id, site=self.site, equipment=equipment)
            for lv in levels
        }

    def load_project(self, project_id: str):
        self.project_id = project_id
        self.project_version_id = None
        self._init_from_project(project_id)

    def load_document(
        self,
        document: ProjectDocument,
        *,
        project_version_id: str | None = None,
    ) -> None:
        """Hot-swap the engine to a new `ProjectDocument`. Used when the
        editor activates a new version for the org, or when boot-time
        seed importer publishes an updated seed."""
        self.project_id = document.slug
        self.project_version_id = project_version_id
        self._init_from_document(document)

    def log_activity(self, asset_id: str, event: str):
        self.activity_log.setdefault(asset_id, deque(maxlen=50)).append({
            "time": self.sim_time,
            "day": self.sim_day,
            "event": event,
        })

    def tick(self):
        if self.paused:
            return
        dt_sim = SIM_SECONDS_PER_TICK * self.speed_multiplier

        self.sim_time += dt_sim
        if self.sim_time >= WORKDAY_END:
            # Emit end-of-day ledger events for the day that just finished
            # (current self.sim_day) BEFORE the counters reset.
            emit_end_of_day(self)
            self.sim_time = WORKDAY_START
            self.sim_day += 1
            self._reset_daily_counters()

        for asset in self.assets:
            if asset.type == "worker":
                update_worker(asset, dt_sim, self)
            elif asset.type == "equipment":
                # Tiefbau-only subtypes (dewatering_pump, sheet_pile)
                # have their own cycle table; the legacy equipment
                # update handles cranes / pumps / excavators only.
                if asset.subtype in ("dewatering_pump", "sheet_pile"):
                    update_tiefbau_equipment(asset, dt_sim, self)
                else:
                    update_equipment(asset, dt_sim, self)

        # Advance every elevator cab (no-op for single-floor projects).
        if self.cabs:
            self._tick_cabs(dt_sim)

        self._record_positions()

    def _tick_cabs(self, dt_sim: float) -> None:
        """Ride every cab forward, dispatching on_alight / on_board to
        the worker FSM. Keeps the vertical_transport module free of
        WorkerInternals knowledge."""
        from simulation.worker_behavior import (
            on_worker_alighted,
            on_worker_boarded,
        )
        for cab in self.cabs.values():
            tick_cab(
                cab,
                dt_sim=dt_sim,
                sim_time=self.sim_time,
                on_alight=lambda wid, lvl: on_worker_alighted(self, wid, lvl),
                on_board=lambda wid, lvl: on_worker_boarded(self, wid, lvl),
            )

    def _reset_daily_counters(self):
        for internals in self.worker_internals.values():
            internals.reset_daily()
        self._density.reset()  # heatmap is a per-day view

    def _record_positions(self):
        for asset in self.assets:
            if asset.type != "worker":
                continue
            if asset.id in self.position_history:
                self.position_history[asset.id].append(
                    (round(asset.position.x, 1), round(asset.position.y, 1))
                )
            self._density.record(asset)

    def density_snapshot(self, *, level_id: str | None = None) -> dict:
        """Cumulative foot-traffic snapshot for the current sim day.

        `level_id=None` collapses every level into one map (legacy /
        single-floor behaviour). Pass a level id to filter — used by
        the multi-level dashboard to show only the visible floor's
        heatmap.
        """
        return self._density.snapshot(
            self.site.width, self.site.height, level_id=level_id,
        )

    def get_state_snapshot(self) -> dict:
        trails = {}
        for aid, positions in self.position_history.items():
            trails[aid] = list(positions)

        # Live cab snapshot for the renderer's cross-level activity
        # indicators on stair/elevator anchors. Cheap — at most a
        # handful of cabs per project, each summarised by floor.
        cabs: list[dict] = []
        for conn_id, cab in self.cabs.items():
            queue_by_level = {
                lv: len(q) for lv, q in cab.queue_per_level.items() if q
            }
            cabs.append({
                "id": conn_id,
                "current_level": cab.current_level_id,
                "passengers": len(cab.passengers),
                "capacity": cab.capacity,
                "queue_by_level": queue_by_level,
            })

        return {
            "sim_time": self.sim_time,
            "sim_day": self.sim_day,
            "assets": [a.to_broadcast_dict() for a in self.assets],
            "trails": trails,
            "cabs": cabs,
        }

    # ── SiteStateSource Protocol surface (O(1) indexed lookups) ─────────

    def asset_by_id(self, asset_id: str):
        return self._by_id.get(asset_id)

    def zone_by_id(self, zone_id: str):
        return self._zone_by_id.get(zone_id)

    def workers_in_zone(self, zone_id: str) -> list:
        # Defensive copy so callers can mutate without corrupting the index
        return list(self._workers_by_zone.get(zone_id, ()))

    def workers_in_level(self, level_id: str) -> list[Asset]:
        """All workers currently on `level_id`. Computed on demand
        because workers move between levels via vertical transport.
        O(N_workers); fine at the project scales we ship."""
        return [
            w for w in self._by_type.get("worker", [])
            if w.position.level_id == level_id
        ]

    # Internal accessors used by hot paths (worker_behavior._find_nearest).
    def facilities_by_subtype(
        self, subtype: str, level_id: str | None = None
    ) -> list[Asset]:
        """All facilities of the given subtype.

        Passing `level_id` returns only those on that specific level —
        used by the vertical-aware FSM to find a same-floor toilet
        first. Without `level_id`, returns the pooled list across
        every level (legacy behaviour for single-floor projects).
        """
        if level_id is None:
            return self._facilities_by_subtype.get(subtype, [])
        return self._facilities_by_subtype_level.get((subtype, level_id), [])

    def materials(self) -> list[Asset]:
        return self._by_type.get("material", [])

    # ── Multi-level Protocol surface ─────────────────────────────────

    @property
    def levels(self) -> list:
        return sorted(self.site.levels, key=lambda lv: lv.order)

    def level_by_id(self, level_id: str):
        return self._level_by_id.get(level_id)

    @property
    def connections(self) -> list[Connection]:
        return list(getattr(self, "_connections", []))

    @connections.setter
    def connections(self, value: list[Connection]) -> None:
        # Stored under a private attribute so the public property is the
        # only read path and we can swap implementations later.
        self._connections = list(value)

    def connections_from_level(self, level_id: str) -> list[Connection]:
        return list(self._connections_by_level.get(level_id, ()))

    def navmesh_for_level(self, level_id: str) -> NavMesh | None:
        """Per-level pathfinder (worker FSM + optimizer). None if the
        level has no navmesh built (shouldn't happen after _rebuild_indexes)."""
        return self.navmeshes.get(level_id)

    def worker_internals_for(self, worker_id: str):
        """Protocol method — typed dataclass in step 3."""
        return self.worker_internals.get(worker_id)

    def activity_log_for(self, asset_id: str):
        return list(self.activity_log.get(asset_id, []))

    def position_history_for(self, worker_id: str) -> list:
        deque_ = self.position_history.get(worker_id)
        return list(deque_) if deque_ is not None else []

    # NB: `get_asset_detail()` lived here pre-step-4 (130 LOC of per-type
    # branching). It has been extracted to `simulation.asset_detail.asset_detail`,
    # which takes a SiteStateSource directly. The route in api/routes.py
    # now calls that service instead.


async def run_simulation_loop(engine: SimulationEngine):
    while engine.running:
        engine.tick()
        await asyncio.sleep(SIM_TICK_INTERVAL)
