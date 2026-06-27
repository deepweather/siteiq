"""Weighted-grid pathfinder for a single level.

The simulation prior to this module walked every worker in a straight
line via `worker_behavior.move_toward`. That made workers cut through
zones, the fence, and equipment cabs — diagrammatically realistic,
operationally false.

`NavMesh` overlays a 2 m grid on the level, colours each cell by what
it's standing on (road / zone / open ground / equipment / off-site),
and pathfinds with A* + an octile heuristic. The grid is built once
per level from existing geometry — `Site.zones`, the equipment list,
and the hardcoded road pattern that `renderer.ts` already draws. No
new editor schema, no per-project authoring.

A path is a sequence of `Position` waypoints. `WorkerInternals.path`
holds the active sequence, and `worker_behavior.follow_path` walks one
waypoint at a time. The optimizer asks `navmesh.distance(a, b)` so
"move toilet 30 m closer" reflects what workers actually walk, not the
crow flies.

Rebuild on:
- project switch (engine `_rebuild_indexes`)
- recommendation apply (engine `apply_recommendation` invalidates)

Caching: `path(start, end)` is keyed by `(start_cell_idx, end_cell_idx)`.
The same trip from the same starting zone to the same toilet recomputes
A* once, then serves from cache. Demo loads have ~10 distinct
destinations, so the cache fills quickly.
"""

from __future__ import annotations

import heapq
import math
from typing import Iterable

from config import (
    EQUIPMENT_FOOTPRINT_RADIUS_M,
    NAVMESH_CELL_SIZE_M,
    NAVMESH_COST_BLOCKED,
    NAVMESH_COST_OPEN,
    NAVMESH_COST_ROAD,
    NAVMESH_COST_ZONE,
    ROAD_SOUTH_STRIP_M,
    ROAD_WEST_STRIP_M,
)
from models.assets import Asset, Position
from models.site import Road, Site, Zone

SQRT2 = math.sqrt(2)


class NavMesh:
    """Per-level weighted-grid pathfinder. See module docstring."""

    def __init__(
        self,
        *,
        site_width: float,
        site_height: float,
        cell_size: float = NAVMESH_CELL_SIZE_M,
    ):
        self.site_width = site_width
        self.site_height = site_height
        self.cell_size = cell_size
        self.cols = max(1, int(math.ceil(site_width / cell_size)))
        self.rows = max(1, int(math.ceil(site_height / cell_size)))
        # Flat 1-D cost array indexed by y*cols + x. NAVMESH_COST_BLOCKED
        # is the sentinel for impassable cells (compared with >=).
        self.cost: list[float] = [NAVMESH_COST_OPEN] * (self.cols * self.rows)
        # path cache: (start_cell_idx, end_cell_idx) -> (cells, total_cost)
        self._cache: dict[
            tuple[int, int], tuple[list[tuple[int, int]], float]
        ] = {}

    # ── Build ────────────────────────────────────────────────────────

    @classmethod
    def build(
        cls,
        *,
        level_id: str,
        site: Site,
        equipment: list[Asset],
        cell_size: float = NAVMESH_CELL_SIZE_M,
    ) -> "NavMesh":
        """Lay out the cost grid by overlaying road → zones → equipment."""
        mesh = cls(
            site_width=site.width,
            site_height=site.height,
            cell_size=cell_size,
        )
        # Roads are authored data per project. When a project's site
        # ships no `roads`, fall back to the legacy perimeter pattern
        # (south + west strips + gate) so older seeds and the
        # hardcoded-roads era keep working.
        level_roads = [r for r in site.roads if r.level_id == level_id]
        if level_roads:
            mesh._stamp_roads(level_roads)
        else:
            mesh._stamp_perimeter_fallback(ROAD_SOUTH_STRIP_M, ROAD_WEST_STRIP_M)
        mesh._stamp_zones([z for z in site.zones if z.level_id == level_id])
        mesh._stamp_equipment(
            [e for e in equipment if e.position.level_id == level_id]
        )
        return mesh

    def _stamp_perimeter_fallback(
        self, south_strip_m: float, west_strip_m: float
    ) -> None:
        """Legacy "south + west perimeter strip" road pattern. Used only
        when the project document doesn't author its own road network."""
        for cy in range(self.rows):
            yc = cy * self.cell_size + self.cell_size / 2
            for cx in range(self.cols):
                xc = cx * self.cell_size + self.cell_size / 2
                if yc >= self.site_height - south_strip_m:
                    self.cost[cy * self.cols + cx] = NAVMESH_COST_ROAD
                elif xc < west_strip_m:
                    self.cost[cy * self.cols + cx] = NAVMESH_COST_ROAD

    def _stamp_roads(self, roads: Iterable[Road]) -> None:
        """Carve each authored road polyline into the cost grid. Every
        cell whose centre is within `width_m / 2` of any road segment
        gets the road cost. Endpoints + corners are rounded with the
        same half-width disk so consecutive segments meeting at an
        angle don't leave a missing wedge."""
        for road in roads:
            if len(road.points) < 1:
                continue
            half_w = road.width_m / 2.0
            r2 = half_w * half_w
            # Stamp each segment as a thick line + a disk at every node
            # so corners stay clean.
            for i, (x, y) in enumerate(road.points):
                self._stamp_disk(x, y, half_w, r2)
                if i + 1 < len(road.points):
                    self._stamp_segment(x, y, road.points[i + 1][0], road.points[i + 1][1], half_w, r2)

    def _stamp_disk(self, cx_m: float, cy_m: float, radius: float, r2: float) -> None:
        cx0 = max(0, int((cx_m - radius) / self.cell_size))
        cy0 = max(0, int((cy_m - radius) / self.cell_size))
        cx1 = min(self.cols, int(math.ceil((cx_m + radius) / self.cell_size)))
        cy1 = min(self.rows, int(math.ceil((cy_m + radius) / self.cell_size)))
        for cy in range(cy0, cy1):
            ym = cy * self.cell_size + self.cell_size / 2
            for cx in range(cx0, cx1):
                xm = cx * self.cell_size + self.cell_size / 2
                dx = xm - cx_m
                dy = ym - cy_m
                if dx * dx + dy * dy <= r2:
                    self.cost[cy * self.cols + cx] = NAVMESH_COST_ROAD

    def _stamp_segment(
        self, ax: float, ay: float, bx: float, by: float, half_w: float, r2: float,
    ) -> None:
        """Stamp every cell whose centre is within `half_w` of the
        segment a->b. Cell-by-cell scan over the segment's bbox + a
        point-to-segment distance test — cheap enough at our grid size."""
        x_lo = min(ax, bx) - half_w
        x_hi = max(ax, bx) + half_w
        y_lo = min(ay, by) - half_w
        y_hi = max(ay, by) + half_w
        cx0 = max(0, int(x_lo / self.cell_size))
        cy0 = max(0, int(y_lo / self.cell_size))
        cx1 = min(self.cols, int(math.ceil(x_hi / self.cell_size)))
        cy1 = min(self.rows, int(math.ceil(y_hi / self.cell_size)))
        seg_dx = bx - ax
        seg_dy = by - ay
        seg_len2 = seg_dx * seg_dx + seg_dy * seg_dy or 1.0
        for cy in range(cy0, cy1):
            ym = cy * self.cell_size + self.cell_size / 2
            for cx in range(cx0, cx1):
                xm = cx * self.cell_size + self.cell_size / 2
                # Project (xm, ym) onto the segment, clamp to [0, 1].
                t = ((xm - ax) * seg_dx + (ym - ay) * seg_dy) / seg_len2
                if t < 0:
                    t = 0.0
                elif t > 1:
                    t = 1.0
                px = ax + t * seg_dx
                py = ay + t * seg_dy
                dx = xm - px
                dy = ym - py
                if dx * dx + dy * dy <= r2:
                    self.cost[cy * self.cols + cx] = NAVMESH_COST_ROAD

    def _stamp_zones(self, zones: Iterable[Zone]) -> None:
        """Zones get the highest non-blocked cost: workers route around
        other crews' zones when feasible. We skip cells that have
        already been stamped as road (road is cheaper, and keeping the
        road through a zone boundary keeps the perimeter as the
        backbone)."""
        for z in zones:
            cx0 = max(0, int(z.x / self.cell_size))
            cy0 = max(0, int(z.y / self.cell_size))
            cx1 = min(self.cols, int(math.ceil((z.x + z.width) / self.cell_size)))
            cy1 = min(self.rows, int(math.ceil((z.y + z.height) / self.cell_size)))
            for cy in range(cy0, cy1):
                for cx in range(cx0, cx1):
                    idx = cy * self.cols + cx
                    # Don't overwrite cheaper road cells; everything else
                    # (open ground) gets the zone-interior penalty.
                    if self.cost[idx] > NAVMESH_COST_ROAD:
                        self.cost[idx] = NAVMESH_COST_ZONE

    def _stamp_equipment(self, equipment: Iterable[Asset]) -> None:
        for e in equipment:
            radius = EQUIPMENT_FOOTPRINT_RADIUS_M.get(e.subtype, 0.0)
            if radius <= 0:
                continue
            ex, ey = e.position.x, e.position.y
            r2 = radius * radius
            cx0 = max(0, int((ex - radius) / self.cell_size))
            cy0 = max(0, int((ey - radius) / self.cell_size))
            cx1 = min(self.cols, int(math.ceil((ex + radius) / self.cell_size)))
            cy1 = min(self.rows, int(math.ceil((ey + radius) / self.cell_size)))
            for cy in range(cy0, cy1):
                ym = cy * self.cell_size + self.cell_size / 2
                for cx in range(cx0, cx1):
                    xm = cx * self.cell_size + self.cell_size / 2
                    dx = xm - ex
                    dy = ym - ey
                    if dx * dx + dy * dy <= r2:
                        self.cost[cy * self.cols + cx] = NAVMESH_COST_BLOCKED

    # ── World <-> cell coordinate helpers ───────────────────────────

    def _world_to_cell(self, x: float, y: float) -> tuple[int, int]:
        cx = max(0, min(self.cols - 1, int(x / self.cell_size)))
        cy = max(0, min(self.rows - 1, int(y / self.cell_size)))
        return cx, cy

    def _cell_to_world(self, cx: int, cy: int) -> tuple[float, float]:
        return (cx + 0.5) * self.cell_size, (cy + 0.5) * self.cell_size

    # ── Public queries ──────────────────────────────────────────────

    def is_walkable(self, x: float, y: float) -> bool:
        cx, cy = self._world_to_cell(x, y)
        return self.cost[cy * self.cols + cx] < NAVMESH_COST_BLOCKED

    def nearest_walkable(
        self, x: float, y: float, *, max_radius_m: float = 50.0
    ) -> tuple[float, float] | None:
        """If (x, y) sits on an impassable cell, return the nearest
        walkable cell's world centre. Used by the optimizer to clamp
        candidate facility positions away from equipment / off-site
        cells. Returns None when no walkable cell is within
        `max_radius_m` (should never happen on a sane site)."""
        if self.is_walkable(x, y):
            return x, y
        cx0, cy0 = self._world_to_cell(x, y)
        max_steps = max(1, int(math.ceil(max_radius_m / self.cell_size)))
        for r in range(1, max_steps + 1):
            for dy in range(-r, r + 1):
                for dx in range(-r, r + 1):
                    if max(abs(dx), abs(dy)) != r:
                        continue
                    cx, cy = cx0 + dx, cy0 + dy
                    if not (0 <= cx < self.cols and 0 <= cy < self.rows):
                        continue
                    if self.cost[cy * self.cols + cx] < NAVMESH_COST_BLOCKED:
                        return self._cell_to_world(cx, cy)
        return None

    def path(self, start: Position, end: Position) -> list[Position]:
        """Compute a list of waypoints from start to end. The list does
        NOT include the start position (the worker is already there) and
        DOES include the exact end position as its last entry.

        On unreachable / degenerate input, returns `[end]` so the worker
        keeps moving (straight-line fallback rather than locking up)."""
        start_cell = self._world_to_cell(start.x, start.y)
        end_cell = self._world_to_cell(end.x, end.y)
        # Same cell — just walk to the target directly.
        if start_cell == end_cell:
            return [Position(x=end.x, y=end.y, level_id=end.level_id)]
        cells = self._cached_cells(start_cell, end_cell)
        if cells is None:
            return [Position(x=end.x, y=end.y, level_id=end.level_id)]
        # Build waypoints from cell centres, then append the exact end
        # so the worker actually arrives at the facility, not its cell
        # centre. `cells` begins with the start cell which we skip.
        waypoints: list[Position] = []
        for cx, cy in cells[1:]:
            wx, wy = self._cell_to_world(cx, cy)
            waypoints.append(Position(x=wx, y=wy, level_id=end.level_id))
        waypoints.append(Position(x=end.x, y=end.y, level_id=end.level_id))
        return waypoints

    def distance(self, start: Position, end: Position) -> float:
        """Total weighted path distance from start to end. Falls back to
        euclidean when no path exists or both points are in the same
        cell. Used by the optimizer to score recommendations."""
        start_cell = self._world_to_cell(start.x, start.y)
        end_cell = self._world_to_cell(end.x, end.y)
        if start_cell == end_cell:
            return math.hypot(end.x - start.x, end.y - start.y)
        key = (
            start_cell[1] * self.cols + start_cell[0],
            end_cell[1] * self.cols + end_cell[0],
        )
        cached = self._cache.get(key)
        if cached is not None:
            _, cost = cached
            return cost
        cells = self._astar(start_cell, end_cell)
        if cells is None:
            return math.hypot(end.x - start.x, end.y - start.y)
        simplified = self._string_pull(cells)
        cost = self._path_cost(cells)
        self._cache[key] = (simplified, cost)
        return cost

    def invalidate(self) -> None:
        self._cache.clear()

    # ── Internal: cached A* + simplification ───────────────────────

    def _cached_cells(
        self,
        start_cell: tuple[int, int],
        end_cell: tuple[int, int],
    ) -> list[tuple[int, int]] | None:
        key = (
            start_cell[1] * self.cols + start_cell[0],
            end_cell[1] * self.cols + end_cell[0],
        )
        cached = self._cache.get(key)
        if cached is not None:
            cells, _ = cached
            return cells
        raw = self._astar(start_cell, end_cell)
        if raw is None:
            return None
        simplified = self._string_pull(raw)
        cost = self._path_cost(raw)
        self._cache[key] = (simplified, cost)
        return simplified

    def _astar(
        self,
        start: tuple[int, int],
        end: tuple[int, int],
    ) -> list[tuple[int, int]] | None:
        # Snap start/end to nearest walkable if they're blocked.
        if self.cost[start[1] * self.cols + start[0]] >= NAVMESH_COST_BLOCKED:
            world = self.nearest_walkable(*self._cell_to_world(*start))
            if world is None:
                return None
            start = self._world_to_cell(*world)
        if self.cost[end[1] * self.cols + end[0]] >= NAVMESH_COST_BLOCKED:
            world = self.nearest_walkable(*self._cell_to_world(*end))
            if world is None:
                return None
            end = self._world_to_cell(*world)

        open_heap: list[tuple[float, int, tuple[int, int]]] = []
        counter = 0  # tie-breaker for stable ordering when f-scores tie
        heapq.heappush(open_heap, (0.0, counter, start))
        came_from: dict[tuple[int, int], tuple[int, int]] = {}
        g_score: dict[tuple[int, int], float] = {start: 0.0}

        while open_heap:
            _, _, current = heapq.heappop(open_heap)
            if current == end:
                cells = [current]
                while current in came_from:
                    current = came_from[current]
                    cells.append(current)
                cells.reverse()
                return cells

            cx, cy = current
            current_g = g_score[current]
            for dx, dy in (
                (1, 0), (-1, 0), (0, 1), (0, -1),
                (1, 1), (1, -1), (-1, 1), (-1, -1),
            ):
                nx, ny = cx + dx, cy + dy
                if not (0 <= nx < self.cols and 0 <= ny < self.rows):
                    continue
                ncost = self.cost[ny * self.cols + nx]
                if ncost >= NAVMESH_COST_BLOCKED:
                    continue
                step = SQRT2 if dx != 0 and dy != 0 else 1.0
                tentative = current_g + step * ncost
                neighbor = (nx, ny)
                if tentative < g_score.get(neighbor, float("inf")):
                    came_from[neighbor] = current
                    g_score[neighbor] = tentative
                    h = self._heuristic(neighbor, end)
                    counter += 1
                    heapq.heappush(open_heap, (tentative + h, counter, neighbor))
        return None

    @staticmethod
    def _heuristic(a: tuple[int, int], b: tuple[int, int]) -> float:
        dx = abs(a[0] - b[0])
        dy = abs(a[1] - b[1])
        # Octile distance times the cheapest cell cost (road). Admissible.
        return (max(dx, dy) + (SQRT2 - 1) * min(dx, dy)) * NAVMESH_COST_ROAD

    def _path_cost(self, cells: list[tuple[int, int]]) -> float:
        if not cells:
            return 0.0
        total = 0.0
        for (ax, ay), (bx, by) in zip(cells, cells[1:]):
            step = SQRT2 if ax != bx and ay != by else 1.0
            total += step * self.cost[by * self.cols + bx]
        return total

    # ── String-pull simplification ─────────────────────────────────

    def _string_pull(
        self, cells: list[tuple[int, int]]
    ) -> list[tuple[int, int]]:
        """Drop cells with line-of-sight to the next kept anchor. Turns a
        30-cell zigzag into the few corner cells. Looks natural and lets
        the FSM walk straight from waypoint to waypoint."""
        if len(cells) <= 2:
            return cells
        out = [cells[0]]
        i = 0
        while i < len(cells) - 1:
            j = len(cells) - 1
            while j > i + 1 and not self._line_of_sight(cells[i], cells[j]):
                j -= 1
            out.append(cells[j])
            i = j
        return out

    def _line_of_sight(
        self, a: tuple[int, int], b: tuple[int, int]
    ) -> bool:
        """Bresenham line: every cell along the segment must be walkable
        for the straight hop to be valid."""
        x0, y0 = a
        x1, y1 = b
        dx = abs(x1 - x0)
        dy = -abs(y1 - y0)
        sx = 1 if x0 < x1 else -1
        sy = 1 if y0 < y1 else -1
        err = dx + dy
        x, y = x0, y0
        while True:
            if self.cost[y * self.cols + x] >= NAVMESH_COST_BLOCKED:
                return False
            if x == x1 and y == y1:
                return True
            e2 = 2 * err
            if e2 >= dy:
                err += dy
                x += sx
            if e2 <= dx:
                err += dx
                y += sy
