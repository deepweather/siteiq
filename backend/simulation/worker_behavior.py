from math import sqrt
from typing import Callable, Protocol
import random

from models.assets import Asset, Position, WorkerState
from models.site import Site, Zone
from simulation.worker_internals import WorkerInternals
from config import (
    WORKER_SPEED, TOILET_INTERVAL, BREAK_INTERVAL, MATERIAL_RUN_INTERVAL,
    TOILET_DWELL, BREAK_DWELL, MATERIAL_DWELL, JITTER_FACTOR,
)


class _WorkerEngine(Protocol):
    """Minimal engine surface that worker_behavior depends on. Lets mypy
    type-check this module without importing the full SimulationEngine
    (which would cascade type errors from not-yet-refactored modules)."""
    sim_time: float
    assets: list[Asset]
    site: Site
    worker_internals: dict[str, WorkerInternals]

    def log_activity(self, asset_id: str, event: str) -> None: ...

    # Optional indexed accessors (step 6). Engines that don't implement
    # them fall back to the slow linear scan over `assets`.
    def facilities_by_subtype(self, subtype: str) -> list[Asset]: ...
    def materials(self) -> list[Asset]: ...


# State handler signature: (worker, internals, dt, engine) -> None
StateHandler = Callable[[Asset, WorkerInternals, float, _WorkerEngine], None]


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


def _find_nearest_facility(worker: Asset, engine: _WorkerEngine, subtype: str) -> Asset | None:
    candidates = engine.facilities_by_subtype(subtype)
    best = None
    best_dist = float("inf")
    for a in candidates:
        dx = a.position.x - worker.position.x
        dy = a.position.y - worker.position.y
        d = sqrt(dx * dx + dy * dy)
        if d < best_dist:
            best_dist = d
            best = a
    return best


def _find_material(worker: Asset, engine: _WorkerEngine) -> Asset | None:
    best = None
    best_dist = float("inf")
    for a in engine.materials():
        dx = a.position.x - worker.position.x
        dy = a.position.y - worker.position.y
        d = sqrt(dx * dx + dy * dy)
        if d < best_dist:
            best_dist = d
            best = a
    return best


def _random_point_in_zone(zone_id: str | None, zones: list[Zone]) -> Position:
    if zone_id is None:
        return Position(x=120, y=80)
    for z in zones:
        if z.id == zone_id:
            return Position(
                x=z.x + random.uniform(5, z.width - 5),
                y=z.y + random.uniform(5, z.height - 5),
            )
    return Position(x=120, y=80)


# ─── Per-state handlers ──────────────────────────────────────────────────


def _on_working(worker: Asset, internals: WorkerInternals, dt_sim: float, engine: _WorkerEngine) -> None:
    internals.time_working += dt_sim
    internals.next_toilet -= dt_sim
    internals.next_break -= dt_sim
    internals.next_material -= dt_sim

    if internals.next_toilet <= 0:
        toilet = _find_nearest_facility(worker, engine, "toilet")
        if toilet:
            internals.target = Position(x=toilet.position.x, y=toilet.position.y)
            internals.return_position = Position(x=worker.position.x, y=worker.position.y)
            worker.state = WorkerState.WALKING_TO_TOILET
            internals.next_toilet = _jitter(TOILET_INTERVAL)
            internals.toilet_trips_today += 1
            internals.toilet_trip_start_time = engine.sim_time
            engine.log_activity(worker.id, f"Walking to {toilet.id}")
            return
        # No toilet exists — defer the check so we don't get pinned here
        internals.next_toilet = _jitter(TOILET_INTERVAL)

    if internals.next_material <= 0:
        mat = _find_material(worker, engine)
        if mat:
            internals.target = Position(x=mat.position.x, y=mat.position.y)
            internals.return_position = Position(x=worker.position.x, y=worker.position.y)
            worker.state = WorkerState.WALKING_TO_MATERIAL
            internals.next_material = _jitter(MATERIAL_RUN_INTERVAL)
            internals.material_trips_today += 1
            internals.material_trip_start_time = engine.sim_time
            engine.log_activity(worker.id, f"Fetching {mat.subtype}")
            return
        internals.next_material = _jitter(MATERIAL_RUN_INTERVAL)

    if internals.next_break <= 0:
        breakroom = _find_nearest_facility(worker, engine, "breakroom")
        if breakroom:
            internals.target = Position(x=breakroom.position.x, y=breakroom.position.y)
            internals.return_position = Position(x=worker.position.x, y=worker.position.y)
            worker.state = WorkerState.WALKING_TO_BREAK
            internals.next_break = _jitter(BREAK_INTERVAL)
            engine.log_activity(worker.id, "Walking to break room")
            return
        internals.next_break = _jitter(BREAK_INTERVAL)


def _on_walking_to_toilet(worker: Asset, internals: WorkerInternals, dt_sim: float, engine: _WorkerEngine) -> None:
    internals.time_walking += dt_sim
    assert internals.target is not None
    arrived, dist = move_toward(worker, internals.target, dt_sim)
    internals.total_distance += dist
    if arrived:
        worker.state = WorkerState.AT_TOILET
        internals.action_timer = _jitter(TOILET_DWELL)
        engine.log_activity(worker.id, "Arrived at toilet")


def _on_at_toilet(worker: Asset, internals: WorkerInternals, dt_sim: float, engine: _WorkerEngine) -> None:
    internals.time_at_facilities += dt_sim
    internals.action_timer -= dt_sim
    if internals.action_timer <= 0:
        worker.state = WorkerState.WALKING_TO_WORK
        internals.target = _random_point_in_zone(worker.assigned_zone, engine.site.zones)
        internals.returning_from = "toilet"
        engine.log_activity(worker.id, "Leaving toilet, returning to work")


def _on_walking_to_material(worker: Asset, internals: WorkerInternals, dt_sim: float, engine: _WorkerEngine) -> None:
    internals.time_walking += dt_sim
    assert internals.target is not None
    arrived, dist = move_toward(worker, internals.target, dt_sim)
    internals.total_distance += dist
    if arrived:
        worker.state = WorkerState.CARRYING_MATERIAL
        internals.action_timer = _jitter(MATERIAL_DWELL)
        internals.carrying_target = _random_point_in_zone(worker.assigned_zone, engine.site.zones)
        engine.log_activity(worker.id, "Picking up material")


def _on_carrying_material(worker: Asset, internals: WorkerInternals, dt_sim: float, engine: _WorkerEngine) -> None:
    if internals.action_timer > 0:
        internals.time_at_facilities += dt_sim
        internals.action_timer -= dt_sim
        return
    internals.time_walking += dt_sim
    target = internals.carrying_target
    if target is None:
        target = _random_point_in_zone(worker.assigned_zone, engine.site.zones)
        internals.carrying_target = target
    arrived, dist = move_toward(worker, target, dt_sim)
    internals.total_distance += dist
    if arrived:
        trip_time = engine.sim_time - internals.material_trip_start_time
        if 0 < trip_time < 7200:
            internals.material_total_round_trip += trip_time
        worker.state = WorkerState.WORKING
        engine.log_activity(worker.id, "Material delivered, resumed work")


def _on_walking_to_break(worker: Asset, internals: WorkerInternals, dt_sim: float, engine: _WorkerEngine) -> None:
    internals.time_walking += dt_sim
    assert internals.target is not None
    arrived, dist = move_toward(worker, internals.target, dt_sim)
    internals.total_distance += dist
    if arrived:
        worker.state = WorkerState.AT_BREAK
        internals.action_timer = _jitter(BREAK_DWELL)
        engine.log_activity(worker.id, "On break")


def _on_at_break(worker: Asset, internals: WorkerInternals, dt_sim: float, engine: _WorkerEngine) -> None:
    internals.time_at_facilities += dt_sim
    internals.action_timer -= dt_sim
    if internals.action_timer <= 0:
        worker.state = WorkerState.WALKING_TO_WORK
        internals.target = _random_point_in_zone(worker.assigned_zone, engine.site.zones)
        internals.returning_from = "break"
        engine.log_activity(worker.id, "Break over, returning to work")


def _on_walking_to_work(worker: Asset, internals: WorkerInternals, dt_sim: float, engine: _WorkerEngine) -> None:
    internals.time_walking += dt_sim
    assert internals.target is not None
    arrived, dist = move_toward(worker, internals.target, dt_sim)
    internals.total_distance += dist
    if arrived:
        if internals.returning_from == "toilet":
            trip_time = engine.sim_time - internals.toilet_trip_start_time
            if 0 < trip_time < 7200:
                internals.toilet_total_round_trip += trip_time
        internals.returning_from = ""
        internals.toilet_trip_start_time = 0.0
        worker.state = WorkerState.WORKING
        engine.log_activity(worker.id, "Resumed work")


# Dispatch table — adding a new WorkerState means: write a handler + add one line.
STATE_HANDLERS: dict[str, StateHandler] = {
    WorkerState.WORKING: _on_working,
    WorkerState.WALKING_TO_TOILET: _on_walking_to_toilet,
    WorkerState.AT_TOILET: _on_at_toilet,
    WorkerState.WALKING_TO_MATERIAL: _on_walking_to_material,
    WorkerState.CARRYING_MATERIAL: _on_carrying_material,
    WorkerState.WALKING_TO_BREAK: _on_walking_to_break,
    WorkerState.AT_BREAK: _on_at_break,
    WorkerState.WALKING_TO_WORK: _on_walking_to_work,
}


def update_worker(worker: Asset, dt_sim: float, engine: _WorkerEngine) -> None:
    """Advance a worker by `dt_sim` simulated seconds. Dispatches to the
    handler registered for the worker's current state. Unknown states are
    a no-op (defensive — should never happen in practice)."""
    internals = engine.worker_internals[worker.id]
    handler = STATE_HANDLERS.get(worker.state)
    if handler is not None:
        handler(worker, internals, dt_sim, engine)
