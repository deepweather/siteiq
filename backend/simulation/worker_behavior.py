from collections import deque
from math import sqrt
from typing import Callable, Protocol
import random

from models.assets import Asset, Position, WorkerState
from models.connection import Connection
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
    # Phase 3: live elevator cab state, keyed by Connection.id.
    cabs: dict[str, object]

    def log_activity(self, asset_id: str, event: str) -> None: ...

    # Optional indexed accessors (step 6). Engines that don't implement
    # them fall back to the slow linear scan over `assets`.
    # `level_id` is an optional filter (Phase 2). Engines that ignore
    # it behave exactly as the pre-multilevel implementation did.
    def facilities_by_subtype(
        self, subtype: str, level_id: str | None = None
    ) -> list[Asset]: ...
    def materials(self) -> list[Asset]: ...

    # Connection-graph accessor (Phase 3). Engines without vertical
    # transport return an empty list.
    def connections_from_level(self, level_id: str) -> list[Connection]: ...


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
    """Pick the nearest facility of `subtype` to the worker.

    Multi-level (Phase 2): prefer a same-level facility. Only fall back
    to a cross-level one when no facility exists on the worker's
    current level. The vertical-transport FSM (Phase 3) handles the
    actual stair/elevator routing once a target on another level is
    chosen — for now we still pick the nearest by raw 2D distance.
    """
    same_level = engine.facilities_by_subtype(subtype, worker.position.level_id)
    candidates = same_level or engine.facilities_by_subtype(subtype)
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
            internals.return_position = Position(
                x=worker.position.x, y=worker.position.y,
                level_id=worker.position.level_id,
            )
            internals.next_toilet = _jitter(TOILET_INTERVAL)
            internals.toilet_trips_today += 1
            internals.toilet_trip_start_time = engine.sim_time
            # Multi-level: route through stair/elevator if needed.
            destination = Position(
                x=toilet.position.x, y=toilet.position.y,
                level_id=toilet.position.level_id,
            )
            if _begin_vertical_route(
                worker, internals, engine, final_destination=destination
            ):
                return
            internals.target = destination
            worker.state = WorkerState.WALKING_TO_TOILET
            engine.log_activity(worker.id, f"Walking to {toilet.id}")
            return
        # No toilet exists — defer the check so we don't get pinned here
        internals.next_toilet = _jitter(TOILET_INTERVAL)

    if internals.next_material <= 0:
        mat = _find_material(worker, engine)
        if mat:
            internals.return_position = Position(
                x=worker.position.x, y=worker.position.y,
                level_id=worker.position.level_id,
            )
            internals.next_material = _jitter(MATERIAL_RUN_INTERVAL)
            internals.material_trips_today += 1
            internals.material_trip_start_time = engine.sim_time
            destination = Position(
                x=mat.position.x, y=mat.position.y,
                level_id=mat.position.level_id,
            )
            if _begin_vertical_route(
                worker, internals, engine, final_destination=destination
            ):
                return
            internals.target = destination
            worker.state = WorkerState.WALKING_TO_MATERIAL
            engine.log_activity(worker.id, f"Fetching {mat.subtype}")
            return
        internals.next_material = _jitter(MATERIAL_RUN_INTERVAL)

    if internals.next_break <= 0:
        breakroom = _find_nearest_facility(worker, engine, "breakroom")
        if breakroom:
            internals.return_position = Position(
                x=worker.position.x, y=worker.position.y,
                level_id=worker.position.level_id,
            )
            internals.next_break = _jitter(BREAK_INTERVAL)
            destination = Position(
                x=breakroom.position.x, y=breakroom.position.y,
                level_id=breakroom.position.level_id,
            )
            if _begin_vertical_route(
                worker, internals, engine, final_destination=destination
            ):
                return
            internals.target = destination
            worker.state = WorkerState.WALKING_TO_BREAK
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


# ─── Phase 3: vertical-transport routing ─────────────────────────────


def _find_connection_to(engine: _WorkerEngine, from_level: str, to_level: str) -> Connection | None:
    """BFS over the connection graph for a direct or transit route from
    `from_level` to `to_level`. Returns the *first hop* connection — the
    FSM rides it and re-routes from the destination if more hops are
    needed. Most projects have one-hop connectivity.
    """
    if from_level == to_level:
        return None
    visited: set[str] = {from_level}
    queue: deque[tuple[str, Connection | None]] = deque([(from_level, None)])
    parents: dict[str, tuple[str, Connection]] = {}
    while queue:
        lv, _ = queue.popleft()
        for c in engine.connections_from_level(lv):
            for n in c.nodes:
                if n.level_id == lv or n.level_id in visited:
                    continue
                visited.add(n.level_id)
                parents[n.level_id] = (lv, c)
                if n.level_id == to_level:
                    # Walk back to find the first-hop connection.
                    cur = n.level_id
                    while parents.get(cur, ("", None))[0] != from_level:
                        cur = parents[cur][0]
                    return parents[cur][1]
                queue.append((n.level_id, c))
    return None


def _begin_vertical_route(
    worker: Asset,
    internals: WorkerInternals,
    engine: _WorkerEngine,
    *,
    final_destination: Position,
) -> bool:
    """If the worker is on a different level than the destination, set
    up the WALKING_TO_VERTICAL state and return True. Otherwise leave
    the FSM in its current state and return False."""
    if worker.position.level_id == final_destination.level_id:
        return False
    conn = _find_connection_to(
        engine, worker.position.level_id, final_destination.level_id
    )
    if conn is None:
        # Disconnected graph — give up gracefully.
        return False
    node = conn.node_for_level(worker.position.level_id)
    if node is None:
        return False
    internals.target = Position(x=node.x, y=node.y, level_id=worker.position.level_id)
    internals.target_level_id = final_destination.level_id
    internals.cross_level_destination = final_destination
    internals.vertical_connection_id = conn.id
    worker.state = WorkerState.WALKING_TO_VERTICAL
    engine.log_activity(worker.id, f"Heading to {conn.kind} {conn.id}")
    return True


def _on_walking_to_vertical(
    worker: Asset,
    internals: WorkerInternals,
    dt_sim: float,
    engine: _WorkerEngine,
) -> None:
    """Walk to the stair / elevator anchor on the worker's current
    level. On arrival, hand off to the right vertical-transport flow."""
    internals.time_walking += dt_sim
    assert internals.target is not None
    arrived, dist = move_toward(worker, internals.target, dt_sim)
    internals.total_distance += dist
    if not arrived:
        return

    conn = _resolve_connection(engine, internals.vertical_connection_id)
    if conn is None:
        # Connection vanished (project edited mid-simulation) — bail
        # to working state so the worker doesn't lock up.
        _clear_vertical_state(internals)
        worker.state = WorkerState.WORKING
        return

    if conn.kind == "stair":
        # Stair traversal: spend a flat time per level difference.
        levels_apart = _levels_apart(engine, conn, worker.position.level_id, internals.target_level_id or "")
        internals.action_timer = conn.seconds_per_level_climb * max(levels_apart, 1)
        worker.state = WorkerState.TRAVERSING_VERTICAL
        internals.vertical_queue_enter_time = engine.sim_time
        engine.log_activity(worker.id, f"Climbing {conn.id}")
        return

    # Elevator: join the cab's queue on this level.
    cab = engine.cabs.get(conn.id) if hasattr(engine, "cabs") else None
    if cab is None:
        # Engine has no cabs configured — treat as stair fallback.
        worker.state = WorkerState.TRAVERSING_VERTICAL
        internals.action_timer = conn.cycle_time_s / 2.0
        internals.vertical_queue_enter_time = engine.sim_time
        return
    cab.queue_per_level.setdefault(worker.position.level_id, deque()).append(worker.id)
    cab.queue_enter_time[worker.id] = engine.sim_time
    internals.vertical_queue_enter_time = engine.sim_time
    worker.state = WorkerState.TRAVERSING_VERTICAL
    # Park target position at the cab anchor; cab.on_alight will
    # move the worker to the destination level when the ride ends.
    engine.log_activity(worker.id, f"Queueing for {conn.id}")


def _on_traversing_vertical(
    worker: Asset,
    internals: WorkerInternals,
    dt_sim: float,
    engine: _WorkerEngine,
) -> None:
    """For stairs, count down the climb timer; on expiry, teleport to
    the destination level. Elevator passengers wait here while the cab
    moves them; the cab's `on_alight` callback transitions them out."""
    internals.time_in_vertical_transport += dt_sim
    conn = _resolve_connection(engine, internals.vertical_connection_id)
    if conn is None or conn.kind == "elevator":
        # Elevator: the cab's `on_alight` advances state. No-op here.
        return
    internals.action_timer -= dt_sim
    if internals.action_timer > 0:
        return
    # Stair traversal finished — land on the destination level.
    target_level = internals.target_level_id or worker.position.level_id
    dest = internals.cross_level_destination
    node = conn.node_for_level(target_level)
    if node is None or dest is None:
        _clear_vertical_state(internals)
        worker.state = WorkerState.WORKING
        return
    worker.position.level_id = target_level
    worker.position.x = node.x
    worker.position.y = node.y
    _continue_after_vertical(worker, internals, engine, dest)


def _continue_after_vertical(
    worker: Asset,
    internals: WorkerInternals,
    engine: _WorkerEngine,
    final_destination: Position,
) -> None:
    """Once the worker is on the right level, head to the final target
    by walking. Reuses the WALKING_TO_TOILET / WALKING_TO_WORK shape."""
    if worker.position.level_id != final_destination.level_id:
        # Multi-hop journey: route through the next connection too.
        if _begin_vertical_route(
            worker, internals, engine, final_destination=final_destination
        ):
            return
    internals.target = Position(
        x=final_destination.x,
        y=final_destination.y,
        level_id=final_destination.level_id,
    )
    internals.target_level_id = None
    internals.cross_level_destination = None
    internals.vertical_connection_id = ""
    # Default to walking-to-work so the rest of the FSM picks it up; if
    # the worker was originally heading to a facility, the
    # WALKING_TO_WORK handler will route them correctly via the next
    # tick's `_on_working` re-evaluation.
    worker.state = WorkerState.WALKING_TO_WORK
    engine.log_activity(worker.id, "Arrived on destination floor")


def _clear_vertical_state(internals: WorkerInternals) -> None:
    internals.target_level_id = None
    internals.cross_level_destination = None
    internals.vertical_connection_id = ""
    internals.vertical_queue_enter_time = 0.0


def _resolve_connection(engine: _WorkerEngine, conn_id: str) -> Connection | None:
    if not conn_id:
        return None
    # Engines have `connections` either as an attribute or a property.
    conns = getattr(engine, "connections", None)
    if not conns:
        return None
    for c in conns:
        if c.id == conn_id:
            return c
    return None


def _levels_apart(
    engine: _WorkerEngine, conn: Connection, from_level: str, to_level: str
) -> int:
    """How many adjacent stops on this connection's level list separate
    the two levels."""
    ids = [n.level_id for n in conn.nodes]
    if from_level not in ids or to_level not in ids:
        return 1
    return abs(ids.index(from_level) - ids.index(to_level))


def on_worker_boarded(engine: _WorkerEngine, worker_id: str, level_id: str) -> str | None:
    """Cab callback: returns the worker's target level so the cab knows
    where to drop them. Called when the worker actually enters the cab."""
    internals = engine.worker_internals.get(worker_id)
    if internals is None:
        return None
    return internals.target_level_id


def on_worker_alighted(engine: _WorkerEngine, worker_id: str, level_id: str) -> None:
    """Cab callback: cab arrived at the worker's target level. Move the
    worker's position to the cab anchor on that level and resume the
    walking flow."""
    internals = engine.worker_internals.get(worker_id)
    worker = next((a for a in engine.assets if a.id == worker_id), None)
    if internals is None or worker is None:
        return
    conn = _resolve_connection(engine, internals.vertical_connection_id)
    dest = internals.cross_level_destination
    if conn is None or dest is None:
        _clear_vertical_state(internals)
        worker.state = WorkerState.WORKING
        return
    node = conn.node_for_level(level_id)
    if node is not None:
        worker.position.level_id = level_id
        worker.position.x = node.x
        worker.position.y = node.y
    _continue_after_vertical(worker, internals, engine, dest)


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
    WorkerState.WALKING_TO_VERTICAL: _on_walking_to_vertical,
    WorkerState.TRAVERSING_VERTICAL: _on_traversing_vertical,
}


def update_worker(worker: Asset, dt_sim: float, engine: _WorkerEngine) -> None:
    """Advance a worker by `dt_sim` simulated seconds. Dispatches to the
    handler registered for the worker's current state. Unknown states are
    a no-op (defensive — should never happen in practice)."""
    internals = engine.worker_internals[worker.id]
    handler = STATE_HANDLERS.get(worker.state)
    if handler is not None:
        handler(worker, internals, dt_sim, engine)
