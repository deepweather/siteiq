"""Vertical-transport graph edges between levels.

A `Connection` is either a stair or an elevator. Each one anchors to one
(x, y) point per level it serves. Workers BFS over the connection graph
to find a route from their current level to a target level — typically
this is one hop, but a hybrid project (stair UG2..EG, elevator EG..Roof)
might require two.

The cab parameters only apply to elevators; stairs are modelled as
fixed-time-per-level traversal with no queue.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class ConnectionNode(BaseModel):
    """The (x, y) anchor of a connection on one specific level."""

    level_id: str
    x: float
    y: float


class Connection(BaseModel):
    """Vertical transport between two or more levels."""

    id: str
    kind: Literal["stair", "elevator"]
    nodes: list[ConnectionNode]
    # Elevator-only — ignored when kind == "stair".
    cab_capacity: int = 6
    cycle_time_s: float = 60.0
    speed_m_per_s: float = 1.5
    # Stair-only — seconds spent in TRAVERSING_VERTICAL per level
    # difference. Default ~ a fit construction worker on one flight.
    seconds_per_level_climb: float = 20.0

    def levels(self) -> list[str]:
        return [n.level_id for n in self.nodes]

    def node_for_level(self, level_id: str) -> ConnectionNode | None:
        for n in self.nodes:
            if n.level_id == level_id:
                return n
        return None
