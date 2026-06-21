"""RecommendationService — owns the recommendation cache.

Extracted from main.py to remove module-level globals. The service caches
per-project so a project switch invalidates automatically. Marking
recommendations as dirty (via `mark_dirty()`) forces a recompute on the
next call — typically driven by the analytics loop after fresh metrics
have been computed.
"""
from __future__ import annotations

from typing import Callable

from models.analytics import Recommendation
from optimization.equipment_schedule import optimize_equipment
from optimization.facility_placement import optimize_toilet_placement
from optimization.material_staging import optimize_material_staging
from state.source import SiteStateSource


# Default optimizer set — exposed as a constructor argument so tests can
# swap in stubs and we can later add/remove optimizers without touching
# this file's logic.
DEFAULT_OPTIMIZERS: tuple[Callable[[SiteStateSource], list[Recommendation]], ...] = (
    optimize_toilet_placement,
    optimize_material_staging,
    optimize_equipment,
)


class RecommendationService:
    def __init__(
        self,
        source: SiteStateSource,
        optimizers: tuple[Callable[[SiteStateSource], list[Recommendation]], ...] = DEFAULT_OPTIMIZERS,
    ) -> None:
        self._source = source
        self._optimizers = optimizers
        self._cache: list[Recommendation] = []
        self._cached_project_id: str | None = None
        self._dirty = True

    def mark_dirty(self) -> None:
        """Force recompute on the next get() call. Called by the analytics
        loop whenever fresh metrics land."""
        self._dirty = True

    def clear(self) -> None:
        """Drop the entire cache (used on project switch when we want zero
        carry-over applied state)."""
        self._cache = []
        self._cached_project_id = None
        self._dirty = True

    def get(self) -> list[Recommendation]:
        current_project = self._source.project_id

        # Cache from a previous project — drop it entirely. Without this,
        # applied carry-over from project A could surface in project B.
        if self._cached_project_id != current_project:
            self._cache = []
            self._cached_project_id = current_project
            self._dirty = True

        if self._dirty or not self._cache:
            recs: list[Recommendation] = []
            for optimizer in self._optimizers:
                recs.extend(optimizer(self._source))

            # Preserve applied-state for recs whose IDs survive across recompute
            applied_ids = {r.id for r in self._cache if r.applied}
            for r in recs:
                if r.id in applied_ids:
                    r.applied = True

            self._cache = recs
            self._dirty = False
        return self._cache

    def by_id(self, rec_id: str) -> Recommendation | None:
        return next((r for r in self.get() if r.id == rec_id), None)
