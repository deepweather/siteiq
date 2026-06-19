import asyncio
from collections import deque

from config import (
    SIM_SECONDS_PER_TICK, WORKDAY_START, WORKDAY_END,
    MAX_TRAIL_LENGTH, SIM_TICK_INTERVAL, ANALYTICS_UPDATE_INTERVAL,
)
from models.assets import WorkerState
from simulation.site_factory import create_initial_site, create_site_from_template
from simulation.worker_behavior import update_worker
from simulation.equipment_behavior import update_equipment


class SimulationEngine:
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

        for a in self.assets:
            if a.type == "worker":
                self.position_history[a.id] = deque(maxlen=MAX_TRAIL_LENGTH)
            self.activity_log[a.id] = deque(maxlen=50)

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
        for wid, internals in self.worker_internals.items():
            internals["toilet_trips_today"] = 0
            internals["material_trips_today"] = 0
            internals["toilet_total_round_trip"] = 0.0
            internals["material_total_round_trip"] = 0.0
            internals["time_working"] = 0.0
            internals["time_walking"] = 0.0
            internals["time_at_facilities"] = 0.0

    def _record_positions(self):
        for asset in self.assets:
            if asset.type == "worker" and asset.id in self.position_history:
                self.position_history[asset.id].append(
                    (round(asset.position.x, 1), round(asset.position.y, 1))
                )

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

    def get_asset_by_id(self, asset_id: str):
        for a in self.assets:
            if a.id == asset_id:
                return a
        return None

    def get_zone_by_id(self, zone_id: str):
        for z in self.site.zones:
            if z.id == zone_id:
                return z
        return None

    def get_workers_in_zone(self, zone_id: str) -> list:
        return [a for a in self.assets if a.type == "worker" and a.assigned_zone == zone_id]

    def get_asset_detail(self, asset_id: str) -> dict | None:
        asset = self.get_asset_by_id(asset_id)
        if not asset:
            return None

        from math import sqrt
        from simulation.equipment_behavior import EQUIPMENT_DUTY_CYCLES
        from config import WORKDAY_START, WORKDAY_END

        base = {
            "id": asset.id,
            "type": asset.type,
            "subtype": asset.subtype,
            "x": round(asset.position.x, 1),
            "y": round(asset.position.y, 1),
            "state": asset.state,
            "assigned_zone": asset.assigned_zone,
        }

        if asset.type == "worker":
            internals = self.worker_internals.get(asset.id, {})
            t_work = internals.get("time_working", 0)
            t_walk = internals.get("time_walking", 0)
            t_fac = internals.get("time_at_facilities", 0)
            total_t = t_work + t_walk + t_fac
            productivity = t_work / total_t if total_t > 0 else 0

            toilet_trips = internals.get("toilet_trips_today", 0)
            toilet_rt = internals.get("toilet_total_round_trip", 0)
            avg_toilet_rt = (toilet_rt / toilet_trips / 60) if toilet_trips > 0 else 0

            mat_trips = internals.get("material_trips_today", 0)
            mat_rt = internals.get("material_total_round_trip", 0)
            avg_mat_rt = (mat_rt / mat_trips / 60) if mat_trips > 0 else 0

            base["detail"] = {
                "productivity": round(productivity, 3),
                "total_distance_m": round(internals.get("total_distance", 0), 1),
                "toilet_trips_today": toilet_trips,
                "avg_toilet_round_trip_min": round(avg_toilet_rt, 1),
                "material_trips_today": mat_trips,
                "avg_material_round_trip_min": round(avg_mat_rt, 1),
                "time_working_s": round(t_work, 0),
                "time_walking_s": round(t_walk, 0),
                "time_at_facilities_s": round(t_fac, 0),
            }
            trail = list(self.position_history.get(asset.id, []))
            base["trail"] = trail

        elif asset.type == "equipment":
            hours_active = asset.metadata.get("hours_active", 0)
            hours_idle = asset.metadata.get("hours_idle", 0)
            total = hours_active + hours_idle
            utilization = hours_active / total if total > 0.01 else 0.5
            cycle = EQUIPMENT_DUTY_CYCLES.get(asset.subtype, {})
            workday_h = (WORKDAY_END - WORKDAY_START) / 3600
            from config import CRANE_HOURLY_RATE, PUMP_HOURLY_RATE, EXCAVATOR_HOURLY_RATE
            rates = {"tower_crane": CRANE_HOURLY_RATE, "concrete_pump": PUMP_HOURLY_RATE, "excavator": EXCAVATOR_HOURLY_RATE}
            rate = rates.get(asset.subtype, 200)
            daily_idle_cost = (1 - utilization) * workday_h * rate

            base["detail"] = {
                "utilization": round(utilization, 3),
                "hours_active": round(hours_active, 2),
                "hours_idle": round(hours_idle, 2),
                "daily_idle_cost": round(daily_idle_cost, 2),
                "cycle_timer_s": round(asset.metadata.get("cycle_timer", 0), 0),
                "operate_duration_s": cycle.get("operate_duration", 0),
                "idle_duration_s": cycle.get("idle_duration", 0),
            }

        elif asset.type == "facility":
            workers_here = []
            for a in self.assets:
                if a.type != "worker":
                    continue
                if asset.subtype == "toilet" and a.state == "at_toilet":
                    d = sqrt((a.position.x - asset.position.x)**2 + (a.position.y - asset.position.y)**2)
                    if d < 5:
                        workers_here.append({"id": a.id, "subtype": a.subtype})
                elif asset.subtype == "breakroom" and a.state == "at_break":
                    d = sqrt((a.position.x - asset.position.x)**2 + (a.position.y - asset.position.y)**2)
                    if d < 10:
                        workers_here.append({"id": a.id, "subtype": a.subtype})
            base["detail"] = {
                "workers_present": workers_here,
            }

        elif asset.type == "material":
            target_zone_id = asset.metadata.get("needed_in_zone")
            dist = None
            if target_zone_id:
                zone = self.get_zone_by_id(target_zone_id)
                if zone:
                    dx = asset.position.x - (zone.x + zone.width / 2)
                    dy = asset.position.y - (zone.y + zone.height / 2)
                    dist = round(sqrt(dx*dx + dy*dy), 1)
            base["detail"] = {
                "needed_in_zone": target_zone_id,
                "distance_to_zone_m": dist,
            }

        base["activity_log"] = list(self.activity_log.get(asset_id, []))
        return base


async def run_simulation_loop(engine: SimulationEngine):
    while engine.running:
        engine.tick()
        await asyncio.sleep(SIM_TICK_INTERVAL)
