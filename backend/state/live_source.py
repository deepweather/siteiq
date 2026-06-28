"""LiveSource — real device feed as a `SiteStateSource`.

Closes the long-standing coherence gap (debt #33): instead of the
`SimulationEngine` generating motion, a `LiveSource` takes the project's
*static* layout (zones, levels, equipment/material placements, navmesh) and
*folds recent ledger events* (produced by cameras/gateways/sensors via the
ingestion path) over it to reflect current reality. Analytics, optimization,
and the renderer consume it through the identical `SiteStateSource` Protocol,
so nothing downstream changes.

Implementation: it composes a `SimulationEngine` built from the
`ProjectDocument` purely for its layout + indexes + navmesh, but never ticks
it. `apply_events` mutates that state from the ledger. Position fusion across
multiple cameras (worker re-identification) is intentionally out of scope for
now; the v1 fold covers equipment state, material levels, and any explicit
position/zone events a device emits.
"""
from __future__ import annotations

import logging
from typing import Iterable

from models.project_document import ProjectDocument
from simulation.engine import SimulationEngine


logger = logging.getLogger("siteiq.state.live")


class LiveSource:
    """A `SiteStateSource` backed by ledger events rather than simulation.

    Delegates the whole read Protocol to an internal, non-ticking engine
    (built from the document) and overlays dynamic state from events."""

    def __init__(
        self,
        document: ProjectDocument,
        *,
        project_version_id: str | None = None,
    ) -> None:
        self._engine = SimulationEngine(
            project_id=document.slug,
            document=document,
            project_version_id=project_version_id,
        )
        # Never auto-ticked by `run_loops_for_registry` (it skips non-engines),
        # but make doubly sure it stays put.
        self._engine.running = False
        self._engine.paused = True
        self.is_live = True
        # Settable plain attributes (NOT properties) so the registry and the
        # lifespan shutdown can do `source.running = False` uniformly across
        # SimulationEngine and LiveSource.
        self.running = False
        self.paused = True

    # Expose the same identity attributes the registry/analytics read.
    @property
    def project_id(self) -> str:
        return self._engine.project_id

    @property
    def project_version_id(self) -> str | None:
        return self._engine.project_version_id

    def tick(self) -> None:  # no-op: live state changes via apply_events
        return None

    # Everything else on the SiteStateSource Protocol (site, assets,
    # asset_by_id, zone_by_id, workers_in_zone, levels, navmesh_for_level,
    # get_state_snapshot, …) delegates to the inner engine's implementation.
    def __getattr__(self, name: str):
        return getattr(self._engine, name)

    # ── the fold ─────────────────────────────────────────────────────

    def apply_events(self, events: Iterable) -> None:
        """Overlay current state from confirmed ledger events. Best-effort:
        unknown subjects/kinds are ignored. Events should be ordered oldest
        -> newest so the last write wins."""
        engine = self._engine
        by_id = {a.id: a for a in engine.assets}
        changed = False
        for e in events:
            kind = getattr(e, "kind", None)
            subject_id = getattr(e, "subject_id", None)
            payload = getattr(e, "payload", None) or {}
            asset = by_id.get(subject_id) if subject_id else None

            if kind == "equipment.state_changed" and asset is not None:
                state = payload.get("state")
                if state:
                    asset.state = state
                    changed = True
            elif kind in ("worker.position", "worker.moved") and asset is not None:
                x, y = payload.get("x"), payload.get("y")
                if x is not None and y is not None:
                    asset.position.x = float(x)
                    asset.position.y = float(y)
                    if payload.get("level_id"):
                        asset.position.level_id = str(payload["level_id"])
                    changed = True
            elif kind == "equipment.utilization" and asset is not None:
                # Reflect a reported state if present (idle/operating).
                state = payload.get("state")
                if state:
                    asset.state = state
                    changed = True

        if changed:
            engine.rebuild_indexes()
