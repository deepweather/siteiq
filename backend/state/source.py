"""SiteStateSource — the abstraction every consumer depends on.

The simulation engine implements this Protocol today. A future LiveSource
(real cameras + tracker + projector) would implement the same Protocol and
slot in without changes to analytics, optimization, or API code.

Keep this surface MINIMAL. Every method here is something analytics or
optimization actually needs. Don't expose anything simulation-specific
(e.g. tick(), pause()) — those belong on the concrete implementation.
"""
from __future__ import annotations

from typing import Any, Iterable, Protocol, runtime_checkable

from models.assets import Asset
from models.connection import Connection
from models.site import Level, Site, Zone
from simulation.navmesh import NavMesh


@runtime_checkable
class SiteStateSource(Protocol):
    """Read-only view of the construction site's current state.

    Analytics, optimization, and HTTP/WS handlers depend on this Protocol
    so they can run against simulated OR live data without modification.
    """

    project_id: str
    sim_time: float
    sim_day: int

    @property
    def site(self) -> Site: ...

    @property
    def assets(self) -> list[Asset]: ...

    def asset_by_id(self, asset_id: str) -> Asset | None: ...

    def zone_by_id(self, zone_id: str) -> Zone | None: ...

    def workers_in_zone(self, zone_id: str) -> list[Asset]: ...

    def worker_internals_for(self, worker_id: str) -> "WorkerInternalsView | None":
        """Per-worker FSM/analytics state. Source-defined struct (currently
        a dict, will become a typed dataclass in step 3)."""
        ...

    def activity_log_for(self, asset_id: str) -> Iterable[dict[str, Any]]:
        """Recent activity events for an asset, newest-last."""
        ...

    def position_history_for(self, worker_id: str) -> list[tuple[float, float]]:
        """Recent (x,y) trail for a worker, oldest-first."""
        ...

    # ── Multi-level surface (Phase 2) ───────────────────────────────
    #
    # All consumers that don't care about levels see "L0" everywhere and
    # behave exactly as before. Multi-level consumers (renderer, vertical
    # transport, per-level optimizers) filter on `level_id`.

    @property
    def levels(self) -> list[Level]:
        """The site's levels, ordered by `order` ascending (lowest UG
        first, highest OG last)."""
        ...

    def level_by_id(self, level_id: str) -> Level | None: ...

    def workers_in_level(self, level_id: str) -> list[Asset]: ...

    @property
    def connections(self) -> list[Connection]:
        """Vertical-transport graph. Empty for single-floor projects."""
        ...

    def connections_from_level(self, level_id: str) -> list[Connection]:
        """Every connection that touches `level_id` as one of its nodes.
        Used by the FSM to find candidate stairs/elevators."""
        ...

    # ── Pathfinding (navmesh) ───────────────────────────────────────
    #
    # The simulation engine builds one `NavMesh` per level so the worker
    # FSM can route around equipment + the fence + (softly) other zones.
    # The optimizer reads `navmesh.distance(a, b)` so recommendation
    # savings reflect the path workers actually walk.

    def navmesh_for_level(self, level_id: str) -> NavMesh | None:
        """The navmesh for `level_id`, or None if the source doesn't
        model walkability for this level."""
        ...


# Step 3 replaced the dict-based access with the WorkerInternals dataclass.
# This alias is kept for documentation purposes — the actual return type of
# `worker_internals_for` is `WorkerInternals | None`.
WorkerInternalsView = dict[str, Any]
