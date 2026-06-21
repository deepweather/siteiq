import asyncio
from collections import defaultdict, deque

from config import (
    SIM_SECONDS_PER_TICK, WORKDAY_START, WORKDAY_END,
    MAX_TRAIL_LENGTH, SIM_TICK_INTERVAL, ANALYTICS_UPDATE_INTERVAL,
)
from models.assets import Asset, WorkerState
from simulation.density import DensityGrid
from simulation.site_factory import create_initial_site, create_site_from_template
from simulation.worker_behavior import update_worker
from simulation.equipment_behavior import update_equipment


# Re-exported for tests / external callers that want the grid resolution
DENSITY_CELL_SIZE = 4


class SimulationEngine:
    # Backwards-compat alias for test_heatmap.py
    DENSITY_CELL_SIZE = DENSITY_CELL_SIZE

    def __init__(self, project_id: str = "westhafen"):
        self.project_id = project_id
        self._init_from_project(project_id)

    def _init_from_project(self, project_id: str):
        self.site, self.assets, self.worker_internals = create_site_from_template(project_id)
        self.sim_time: float = WORKDAY_START + 2 * 3600
        self.sim_day: int = self.site.current_day
        self.speed_multiplier: float = 1.0
        self.paused: bool = False
        self.position_history: dict[str, deque] = {}
        self.activity_log: dict[str, deque] = {}
        self.running: bool = True
        self._density = DensityGrid(cell_size=DENSITY_CELL_SIZE)

        for a in self.assets:
            if a.type == "worker":
                self.position_history[a.id] = deque(maxlen=MAX_TRAIL_LENGTH)
            self.activity_log[a.id] = deque(maxlen=50)

        self._rebuild_indexes()

    def rebuild_indexes(self) -> None:
        """Public re-index entry point. Call after mutating `self.assets`
        directly (e.g. in tests). Project switches call this automatically."""
        self._rebuild_indexes()

    def _rebuild_indexes(self) -> None:
        """O(1) lookup tables. Rebuilt whenever the assets list is replaced
        (project switch, asset added/removed by an applied recommendation)."""
        self._by_id: dict[str, Asset] = {a.id: a for a in self.assets}
        self._by_type: dict[str, list[Asset]] = defaultdict(list)
        self._facilities_by_subtype: dict[str, list[Asset]] = defaultdict(list)
        self._workers_by_zone: dict[str, list[Asset]] = defaultdict(list)
        self._zone_by_id: dict[str, object] = {z.id: z for z in self.site.zones}
        for a in self.assets:
            self._by_type[a.type].append(a)
            if a.type == "facility":
                self._facilities_by_subtype[a.subtype].append(a)
            if a.type == "worker" and a.assigned_zone:
                self._workers_by_zone[a.assigned_zone].append(a)

    def load_project(self, project_id: str):
        self.project_id = project_id
        self._init_from_project(project_id)

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
            self.sim_time = WORKDAY_START
            self.sim_day += 1
            self._reset_daily_counters()

        for asset in self.assets:
            if asset.type == "worker":
                update_worker(asset, dt_sim, self)
            elif asset.type == "equipment":
                update_equipment(asset, dt_sim, self)

        self._record_positions()

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

    def density_snapshot(self) -> dict:
        """Cumulative foot-traffic snapshot for the current sim day."""
        return self._density.snapshot(self.site.width, self.site.height)

    def get_state_snapshot(self) -> dict:
        trails = {}
        for aid, positions in self.position_history.items():
            trails[aid] = list(positions)

        return {
            "sim_time": self.sim_time,
            "sim_day": self.sim_day,
            "assets": [a.to_broadcast_dict() for a in self.assets],
            "trails": trails,
        }

    # ── SiteStateSource Protocol surface (O(1) indexed lookups) ─────────

    def asset_by_id(self, asset_id: str):
        return self._by_id.get(asset_id)

    def zone_by_id(self, zone_id: str):
        return self._zone_by_id.get(zone_id)

    def workers_in_zone(self, zone_id: str) -> list:
        # Defensive copy so callers can mutate without corrupting the index
        return list(self._workers_by_zone.get(zone_id, ()))

    # Internal accessors used by hot paths (worker_behavior._find_nearest).
    def facilities_by_subtype(self, subtype: str) -> list[Asset]:
        return self._facilities_by_subtype.get(subtype, [])

    def materials(self) -> list[Asset]:
        return self._by_type.get("material", [])

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
