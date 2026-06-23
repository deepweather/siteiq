"""Foot-traffic density grid used by the heatmap.

Sparse `dict[(level_id, col, row), count]` keyed by cell coordinates +
the worker's level. Reset at the day boundary by the engine. Kept in
its own module so SimulationEngine doesn't balloon with heatmap
concerns.

Multi-level (Phase 5 audit fix): the grid now indexes per level so a
two-floor project doesn't pile its underground traffic on top of its
ground-floor traffic. `snapshot(level_id=...)` filters to a single
level; `snapshot()` (level_id=None) pools all levels — handy for
single-floor projects and aggregate views.
"""
from __future__ import annotations

from models.assets import Asset


class DensityGrid:
    def __init__(self, cell_size: int = 4) -> None:
        self.cell_size = cell_size
        self._cells: dict[tuple[str, int, int], int] = {}

    def record(self, asset: Asset) -> None:
        col = int(asset.position.x // self.cell_size)
        row = int(asset.position.y // self.cell_size)
        key = (asset.position.level_id, col, row)
        self._cells[key] = self._cells.get(key, 0) + 1

    def reset(self) -> None:
        self._cells.clear()

    def snapshot(
        self,
        site_width: float,
        site_height: float,
        *,
        level_id: str | None = None,
    ) -> dict:
        """Compact JSON-friendly snapshot. Filter to one level via
        `level_id`; pass None to pool every level into one map."""
        filtered = (
            {(c, r): n for (lid, c, r), n in self._cells.items() if lid == level_id}
            if level_id is not None
            else self._collapse_levels()
        )
        if not filtered:
            return {
                "cell_size": self.cell_size,
                "site_width": site_width,
                "site_height": site_height,
                "max_count": 0,
                "cells": [],
                "level_id": level_id,
            }
        max_count = max(filtered.values())
        cells = [
            [c, r, round(count / max_count, 3)]
            for (c, r), count in filtered.items()
        ]
        return {
            "cell_size": self.cell_size,
            "site_width": site_width,
            "site_height": site_height,
            "max_count": max_count,
            "cells": cells,
            "level_id": level_id,
        }

    def _collapse_levels(self) -> dict[tuple[int, int], int]:
        out: dict[tuple[int, int], int] = {}
        for (_, c, r), n in self._cells.items():
            key = (c, r)
            out[key] = out.get(key, 0) + n
        return out
