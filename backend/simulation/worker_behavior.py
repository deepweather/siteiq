from math import sqrt
import random

from models.assets import Asset, Position, WorkerState
from config import (
    WORKER_SPEED, TOILET_INTERVAL, BREAK_INTERVAL, MATERIAL_RUN_INTERVAL,
    TOILET_DWELL, BREAK_DWELL, MATERIAL_DWELL, JITTER_FACTOR,
)


def _jitter(base: float) -> float:
    return base * (1.0 + random.uniform(-JITTER_FACTOR, JITTER_FACTOR))


def move_toward(worker: Asset, target: Position, dt_sim: float) -> tuple[bool, float]:
    """Move worker toward target. Returns (arrived, distance_moved)."""
    dx = target.x - worker.position.x
    dy = target.y - worker.position.y
    dist = sqrt(dx * dx + dy * dy)
    if dist < 1.0:
        worker.position.x = target.x
        worker.position.y = target.y
        return True, dist
    move_dist = WORKER_SPEED * dt_sim
    if move_dist >= dist:
        worker.position.x = target.x
        worker.position.y = target.y
        return True, dist
    ratio = move_dist / dist
    worker.position.x += dx * ratio
    worker.position.y += dy * ratio
    return False, move_dist


def _find_nearest(worker: Asset, assets: list[Asset], subtype: str) -> Asset | None:
    best = None
    best_dist = float("inf")
    for a in assets:
        if a.type == "facility" and a.subtype == subtype:
            dx = a.position.x - worker.position.x
            dy = a.position.y - worker.position.y
            d = sqrt(dx * dx + dy * dy)
            if d < best_dist:
                best_dist = d
                best = a
    return best


def _find_material_for_zone(worker: Asset, assets: list[Asset]) -> Asset | None:
    best = None
    best_dist = float("inf")
    for a in assets:
        if a.type == "material":
            dx = a.position.x - worker.position.x
            dy = a.position.y - worker.position.y
            d = sqrt(dx * dx + dy * dy)
            if d < best_dist:
                best_dist = d
                best = a
    return best


def _random_point_in_zone(zone_id: str, zones) -> Position:
    for z in zones:
        if z.id == zone_id:
            return Position(
                x=z.x + random.uniform(5, z.width - 5),
                y=z.y + random.uniform(5, z.height - 5),
            )
    return Position(x=120, y=80)


def update_worker(worker: Asset, dt_sim: float, engine) -> None:
    internals = engine.worker_internals[worker.id]
    assets = engine.assets
    zones = engine.site.zones

    if worker.state == WorkerState.WORKING:
        internals["time_working"] += dt_sim
        internals["next_toilet"] -= dt_sim
        internals["next_break"] -= dt_sim
        internals["next_material"] -= dt_sim

        if internals["next_toilet"] <= 0:
            toilet = _find_nearest(worker, assets, "toilet")
            if toilet:
                internals["target"] = Position(x=toilet.position.x, y=toilet.position.y)
                internals["return_position"] = Position(x=worker.position.x, y=worker.position.y)
                worker.state = WorkerState.WALKING_TO_TOILET
                internals["next_toilet"] = _jitter(TOILET_INTERVAL)
                internals["toilet_trips_today"] += 1
                internals["toilet_trip_start_time"] = engine.sim_time
                engine.log_activity(worker.id, f"Walking to {toilet.id}")
            return

        if internals["next_material"] <= 0:
            mat = _find_material_for_zone(worker, assets)
            if mat:
                internals["target"] = Position(x=mat.position.x, y=mat.position.y)
                internals["return_position"] = Position(x=worker.position.x, y=worker.position.y)
                worker.state = WorkerState.WALKING_TO_MATERIAL
                internals["next_material"] = _jitter(MATERIAL_RUN_INTERVAL)
                internals["material_trips_today"] += 1
                internals["material_trip_start_time"] = engine.sim_time
                engine.log_activity(worker.id, f"Fetching {mat.subtype}")
            return

        if internals["next_break"] <= 0:
            breakroom = _find_nearest(worker, assets, "breakroom")
            if breakroom:
                internals["target"] = Position(x=breakroom.position.x, y=breakroom.position.y)
                internals["return_position"] = Position(x=worker.position.x, y=worker.position.y)
                worker.state = WorkerState.WALKING_TO_BREAK
                internals["next_break"] = _jitter(BREAK_INTERVAL)
                engine.log_activity(worker.id, "Walking to break room")
            return

    elif worker.state == WorkerState.WALKING_TO_TOILET:
        internals["time_walking"] += dt_sim
        arrived, dist = move_toward(worker, internals["target"], dt_sim)
        internals["total_distance"] += dist
        if arrived:
            worker.state = WorkerState.AT_TOILET
            internals["action_timer"] = _jitter(TOILET_DWELL)
            engine.log_activity(worker.id, "Arrived at toilet")

    elif worker.state == WorkerState.AT_TOILET:
        internals["time_at_facilities"] += dt_sim
        internals["action_timer"] -= dt_sim
        if internals["action_timer"] <= 0:
            worker.state = WorkerState.WALKING_TO_WORK
            internals["target"] = _random_point_in_zone(worker.assigned_zone, zones)
            internals["returning_from"] = "toilet"
            engine.log_activity(worker.id, "Leaving toilet, returning to work")

    elif worker.state == WorkerState.WALKING_TO_MATERIAL:
        internals["time_walking"] += dt_sim
        arrived, dist = move_toward(worker, internals["target"], dt_sim)
        internals["total_distance"] += dist
        if arrived:
            worker.state = WorkerState.CARRYING_MATERIAL
            internals["action_timer"] = _jitter(MATERIAL_DWELL)
            internals["carrying_target"] = _random_point_in_zone(worker.assigned_zone, zones)
            engine.log_activity(worker.id, "Picking up material")

    elif worker.state == WorkerState.CARRYING_MATERIAL:
        if internals["action_timer"] > 0:
            internals["time_at_facilities"] += dt_sim
            internals["action_timer"] -= dt_sim
        else:
            internals["time_walking"] += dt_sim
            target = internals.get("carrying_target")
            if target is None:
                target = _random_point_in_zone(worker.assigned_zone, zones)
                internals["carrying_target"] = target
            arrived, dist = move_toward(worker, target, dt_sim)
            internals["total_distance"] += dist
            if arrived:
                trip_time = engine.sim_time - internals["material_trip_start_time"]
                if 0 < trip_time < 7200:
                    internals["material_total_round_trip"] += trip_time
                worker.state = WorkerState.WORKING
                engine.log_activity(worker.id, "Material delivered, resumed work")

    elif worker.state == WorkerState.WALKING_TO_BREAK:
        internals["time_walking"] += dt_sim
        arrived, dist = move_toward(worker, internals["target"], dt_sim)
        internals["total_distance"] += dist
        if arrived:
            worker.state = WorkerState.AT_BREAK
            internals["action_timer"] = _jitter(BREAK_DWELL)
            engine.log_activity(worker.id, "On break")

    elif worker.state == WorkerState.AT_BREAK:
        internals["time_at_facilities"] += dt_sim
        internals["action_timer"] -= dt_sim
        if internals["action_timer"] <= 0:
            worker.state = WorkerState.WALKING_TO_WORK
            internals["target"] = _random_point_in_zone(worker.assigned_zone, zones)
            internals["returning_from"] = "break"
            engine.log_activity(worker.id, "Break over, returning to work")

    elif worker.state == WorkerState.WALKING_TO_WORK:
        internals["time_walking"] += dt_sim
        arrived, dist = move_toward(worker, internals["target"], dt_sim)
        internals["total_distance"] += dist
        if arrived:
            returning_from = internals.get("returning_from", "")
            if returning_from == "toilet":
                trip_time = engine.sim_time - internals.get("toilet_trip_start_time", 0)
                if 0 < trip_time < 7200:
                    internals["toilet_total_round_trip"] += trip_time
            internals["returning_from"] = ""
            internals["toilet_trip_start_time"] = 0
            worker.state = WorkerState.WORKING
            engine.log_activity(worker.id, "Resumed work")
