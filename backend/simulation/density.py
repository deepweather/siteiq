"""Foot-traffic density grid used by the heatmap.

Sparse `dict[(col, row), count]` keyed by cell coordinates. Reset at the
day boundary by the engine. Kept in its own module so SimulationEngine
doesn't balloon with heatmap concerns.
"""
from __future__ import annotations

from models.assets import Asset


class DensityGrid:
    def __init__(self, cell_size: int = 4) -> None:
        self.cell_size = cell_size
        self._cells: dict[tuple[int, int], int] = {}

    def record(self, asset: Asset) -> None:
        col = int(asset.position.x // self.cell_size)
        row = int(asset.position.y // self.cell_size)
        key = (col, row)
        self._cells[key] = self._cells.get(key, 0) + 1

    def reset(self) -> None:
        self._cells.clear()

    def snapshot(self, site_width: float, site_height: float) -> dict:
        """Compact JSON-friendly snapshot. See API contract in claude.md."""
        if not self._cells:
            return {
                "cell_size": self.cell_size,
                "site_width": site_width,
                "site_height": site_height,
                "max_count": 0,
                "cells": [],
            }
        max_count = max(self._cells.values())
        cells = [
            [c, r, round(count / max_count, 3)]
            for (c, r), count in self._cells.items()
        ]
        return {
            "cell_size": self.cell_size,
            "site_width": site_width,
            "site_height": site_height,
            "max_count": max_count,
            "cells": cells,
        }
