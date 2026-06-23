"""Cab-tracked vertical-transport simulation.

For every `Connection(kind="elevator")` the engine keeps a `Cab` which
tracks position, direction, passengers, and per-level queues. Workers
board on arrival and alight at their target level. Stairs are handled
out-of-band (a flat per-level-climb traversal time, no queue) so this
module focuses on the elevator model.

Routing is BFS over the connection graph. With typical building sizes
(< 20 cabs, < 20 levels) this is cheap; the microbench in
`tests/test_engine_perf.py` enforces the budget.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Iterable

from models.connection import Connection


@dataclass
class CabState:
    """Live state of one elevator cab. Owned by the engine and ticked
    each simulation step."""

    connection_id: str
    capacity: int
    speed_m_per_s: float
    door_dwell_s: float

    # Per-level (x, y, elevation) anchor lookup, populated at engine boot.
    level_y_by_id: dict[str, float] = field(default_factory=dict)

    # Live state.
    current_level_id: str = ""
    direction: int = 0  # +1 up, -1 down, 0 idle
    door_open_remaining_s: float = 0.0
    # Passengers ride together; each entry is (worker_id, target_level_id).
    passengers: list[tuple[str, str]] = field(default_factory=list)
    # Per-level FIFO queue. Workers join here in WALKING_TO_VERTICAL once
    # they reach the cab anchor on their current level.
    queue_per_level: dict[str, deque[str]] = field(default_factory=dict)
    # Worker id -> sim_time they joined a queue. Lets the engine remove
    # them O(1) from the queue when they reach the cab, and lets
    # analytics compute time-in-queue.
    queue_enter_time: dict[str, float] = field(default_factory=dict)
    # Number of times the operator applied an `add_equipment` rec on
    # this cab. Each application doubles capacity, but the optimizer
    # consults this counter so applying once is enough — a transient
    # rec disappearance + reappearance can't drive runaway compounding.
    extra_cab_count: int = 0

    def ordered_level_ids(self) -> list[str]:
        """Levels this cab serves, ordered low → high by elevation."""
        return sorted(self.level_y_by_id.keys(), key=lambda lv: self.level_y_by_id[lv])


def build_cabs(connections: Iterable[Connection], levels) -> dict[str, CabState]:
    """Build a Cab for every elevator connection. Stairs do not get a
    Cab (they have no queue).

    `levels` is iterable of `Level` with `elevation_m`.
    """
    level_elev = {lv.id: lv.elevation_m for lv in levels}
    cabs: dict[str, CabState] = {}
    for c in connections:
        if c.kind != "elevator":
            continue
        cab = CabState(
            connection_id=c.id,
            capacity=c.cab_capacity,
            speed_m_per_s=c.speed_m_per_s,
            door_dwell_s=max(c.cycle_time_s * 0.05, 2.0),
            level_y_by_id={n.level_id: level_elev.get(n.level_id, 0.0) for n in c.nodes},
        )
        # Idle on the lowest served level.
        ordered = cab.ordered_level_ids()
        cab.current_level_id = ordered[0] if ordered else ""
        cab.queue_per_level = {lv: deque() for lv in ordered}
        cabs[c.id] = cab
    return cabs


def _adjacent_level(cab: CabState, level_id: str, direction: int) -> str | None:
    """The next level in `direction` (+1 / -1) along the cab's stops."""
    ordered = cab.ordered_level_ids()
    if level_id not in ordered:
        return None
    idx = ordered.index(level_id)
    nxt = idx + (1 if direction > 0 else -1)
    if 0 <= nxt < len(ordered):
        return ordered[nxt]
    return None


def _pick_direction(cab: CabState) -> int:
    """When idle, choose the direction with the closest queued caller.

    Ties go to "up". Returns 0 if no queues are non-empty.
    """
    if not any(cab.queue_per_level.values()) and not cab.passengers:
        return 0
    ordered = cab.ordered_level_ids()
    here = ordered.index(cab.current_level_id) if cab.current_level_id in ordered else 0
    nearest_up = float("inf")
    nearest_down = float("inf")
    for idx, lv in enumerate(ordered):
        if cab.queue_per_level.get(lv):
            distance = abs(idx - here)
            if idx >= here and distance < nearest_up:
                nearest_up = distance
            if idx <= here and distance < nearest_down:
                nearest_down = distance
    if nearest_up == float("inf") and nearest_down == float("inf"):
        # Only passengers riding; pick whichever direction has the nearest target.
        for _, target in cab.passengers:
            if target in ordered:
                t = ordered.index(target)
                if t > here:
                    return 1
                if t < here:
                    return -1
        return 0
    if nearest_up <= nearest_down:
        return 1
    return -1


def tick_cab(
    cab: CabState,
    *,
    dt_sim: float,
    sim_time: float,
    on_alight: "OnAlight" = None,
    on_board: "OnBoard" = None,
) -> None:
    """Advance one cab by `dt_sim` simulated seconds.

    Long tick budgets (the sim runs at up to 20x real-time) can fit
    multiple floor stops; we resolve them all in one call so cab
    position stays consistent with worker movement.

    `on_alight(worker_id, level_id)` is called every time a passenger
    leaves the cab. `on_board(worker_id, level_id)` is called every
    time a worker boards.
    """
    budget = dt_sim
    # Door dwell first — sit still while passengers board/alight.
    if cab.door_open_remaining_s > 0:
        consume = min(budget, cab.door_open_remaining_s)
        cab.door_open_remaining_s -= consume
        budget -= consume
        if cab.door_open_remaining_s == 0:
            # Doors close; if no continuing demand, idle and stop.
            if not cab.passengers and not any(cab.queue_per_level.values()):
                cab.direction = 0
                return

    while budget > 0:
        if cab.direction == 0:
            cab.direction = _pick_direction(cab)
            if cab.direction == 0:
                return

        next_level = _adjacent_level(cab, cab.current_level_id, cab.direction)
        if next_level is None:
            # End of shaft — reverse and try again on the next pass.
            cab.direction = -cab.direction
            continue

        dy = abs(cab.level_y_by_id[next_level] - cab.level_y_by_id[cab.current_level_id])
        travel_time = dy / max(cab.speed_m_per_s, 0.1)
        if budget < travel_time:
            return
        budget -= travel_time
        cab.current_level_id = next_level

        # Doors open: alight passengers heading here, board queued workers.
        arriving = [
            (wid, target) for wid, target in cab.passengers if target == next_level
        ]
        for wid, _ in arriving:
            cab.passengers.remove((wid, next_level))
            if on_alight is not None:
                on_alight(wid, next_level)
        queue = cab.queue_per_level.get(next_level)
        if queue:
            free_seats = cab.capacity - len(cab.passengers)
            while free_seats > 0 and queue:
                wid = queue.popleft()
                cab.queue_enter_time.pop(wid, None)
                target = on_board(wid, next_level) if on_board is not None else None
                if target is None:
                    continue
                cab.passengers.append((wid, target))
                free_seats -= 1
        # Open the doors for the dwell window before continuing.
        cab.door_open_remaining_s = cab.door_dwell_s
        consume = min(budget, cab.door_open_remaining_s)
        cab.door_open_remaining_s -= consume
        budget -= consume
        if cab.door_open_remaining_s == 0 and not cab.passengers and not any(
            cab.queue_per_level.values()
        ):
            cab.direction = 0
            return


# Convenience type aliases for the callbacks above.
OnAlight = "callable[[str, str], None] | None"
OnBoard = "callable[[str, str], str | None] | None"
