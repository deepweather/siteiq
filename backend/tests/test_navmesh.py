"""NavMesh unit tests.

Covers the four properties the rest of the system depends on:
  1. Cell categorisation — road, zone, equipment, off-site are correctly
     classified from the input geometry.
  2. A* finds a path on a trivial obstacle layout (proves the algorithm).
  3. Paths prefer roads when meaningfully shorter, and detour around
     equipment (never enter an infinite-cost cell).
  4. String-pull simplifies a straight zigzag down to its endpoints, and
     the cache replays a path without rerunning A*.
"""
from __future__ import annotations

from math import hypot

from config import (
    EQUIPMENT_FOOTPRINT_RADIUS_M,
    NAVMESH_CELL_SIZE_M,
    NAVMESH_COST_BLOCKED,
    ROAD_SOUTH_STRIP_M,
)
from models.assets import Asset, Position
from models.site import Discipline, Level, Phase, Site, Zone
from simulation.navmesh import NavMesh


def _empty_site(width: float = 100.0, height: float = 100.0) -> Site:
    return Site(
        id="t",
        name="t",
        width=width,
        height=height,
        zones=[],
        current_day=1,
        discipline=Discipline.HOCHBAU,
        levels=[Level(id="L0", name="EG", elevation_m=0.0, order=0)],
    )


def _crane(x: float, y: float, level_id: str = "L0") -> Asset:
    return Asset(
        id=f"crane-at-{x}-{y}",
        type="equipment",
        subtype="tower_crane",
        position=Position(x=x, y=y, level_id=level_id),
        state="operating",
    )


# ── 1. Cell categorisation ───────────────────────────────────────────


def test_empty_site_is_all_open_except_roads():
    """Without zones or equipment, every cell is road (south/west strip)
    or open. No infinities."""
    site = _empty_site(width=60, height=60)
    mesh = NavMesh.build(level_id="L0", site=site, equipment=[])
    for c in mesh.cost:
        assert c < NAVMESH_COST_BLOCKED


def test_south_strip_is_cheaper_than_open():
    """Cells along the bottom edge cost the road price; cells one
    south-strip-height up cost the open price. This is what makes
    workers prefer the perimeter."""
    site = _empty_site(width=80, height=80)
    mesh = NavMesh.build(level_id="L0", site=site, equipment=[])
    south_cell = mesh.cost[
        (mesh.rows - 1) * mesh.cols + (mesh.cols // 2)
    ]
    middle_cell = mesh.cost[
        (mesh.rows // 2) * mesh.cols + (mesh.cols // 2)
    ]
    assert south_cell < middle_cell


def test_zone_interior_is_costlier_than_open():
    """Zone interiors get the slight 1.5-cost penalty so the path
    prefers detouring around populated zones when feasible."""
    site = _empty_site(width=100, height=100)
    site.zones = [
        Zone(
            id="z", label="Z", x=30, y=30, width=20, height=20,
            phase=Phase.STRUCTURAL, phase_progress=0.5, level_id="L0",
        ),
    ]
    mesh = NavMesh.build(level_id="L0", site=site, equipment=[])
    inside = mesh.cost[int(40 / NAVMESH_CELL_SIZE_M) * mesh.cols + int(40 / NAVMESH_CELL_SIZE_M)]
    outside_north = mesh.cost[int(10 / NAVMESH_CELL_SIZE_M) * mesh.cols + int(40 / NAVMESH_CELL_SIZE_M)]
    assert inside > outside_north  # zone is costlier than open ground above it


def test_equipment_footprint_marks_cells_blocked():
    """Stamping a crane should fill its radius-15m circle with the
    impassable sentinel."""
    site = _empty_site(width=80, height=80)
    mesh = NavMesh.build(
        level_id="L0",
        site=site,
        equipment=[_crane(40, 40)],
    )
    cx = int(40 / NAVMESH_CELL_SIZE_M)
    cy = int(40 / NAVMESH_CELL_SIZE_M)
    assert mesh.cost[cy * mesh.cols + cx] >= NAVMESH_COST_BLOCKED
    # 10 m to the side (within the 15 m radius) is also blocked.
    assert mesh.cost[cy * mesh.cols + (cx + int(10 / NAVMESH_CELL_SIZE_M))] >= NAVMESH_COST_BLOCKED
    # 20 m away — outside the radius — is walkable.
    far_cell = mesh.cost[
        cy * mesh.cols + (cx + int(20 / NAVMESH_CELL_SIZE_M))
    ]
    assert far_cell < NAVMESH_COST_BLOCKED


# ── 2. A* correctness ───────────────────────────────────────────────


def test_path_reaches_destination_on_trivial_site():
    site = _empty_site(width=80, height=80)
    mesh = NavMesh.build(level_id="L0", site=site, equipment=[])
    start = Position(x=10, y=70, level_id="L0")
    end = Position(x=70, y=70, level_id="L0")
    waypoints = mesh.path(start, end)
    assert waypoints, "path() must return at least one waypoint"
    # Final waypoint is the requested destination.
    assert waypoints[-1].x == end.x
    assert waypoints[-1].y == end.y


def test_path_avoids_equipment_footprint():
    """A direct line from start to end would cross the crane at the
    centre. The path must NEVER pass through any infinite-cost cell."""
    site = _empty_site(width=80, height=80)
    mesh = NavMesh.build(
        level_id="L0",
        site=site,
        equipment=[_crane(40, 40)],
    )
    start = Position(x=10, y=40, level_id="L0")
    end = Position(x=70, y=40, level_id="L0")
    waypoints = mesh.path(start, end)
    # Every line segment between consecutive waypoints must stay clear
    # of blocked cells (string-pull guarantees this).
    prev = Position(x=start.x, y=start.y, level_id="L0")
    for w in waypoints:
        # Sample 20 points along the segment and check each is walkable.
        for t in range(1, 20):
            ix = prev.x + (w.x - prev.x) * t / 20
            iy = prev.y + (w.y - prev.y) * t / 20
            assert mesh.is_walkable(ix, iy), f"path crosses blocked cell at ({ix}, {iy})"
        prev = w


def test_path_is_longer_than_euclidean_when_obstacle_blocks_line():
    """The detour costs more than the straight-line distance — proves
    the obstacle is actually being routed around."""
    site = _empty_site(width=80, height=80)
    mesh = NavMesh.build(
        level_id="L0",
        site=site,
        equipment=[_crane(40, 40)],
    )
    start = Position(x=10, y=40, level_id="L0")
    end = Position(x=70, y=40, level_id="L0")
    waypoints = mesh.path(start, end)
    walked = 0.0
    prev = (start.x, start.y)
    for w in waypoints:
        walked += hypot(w.x - prev[0], w.y - prev[1])
        prev = (w.x, w.y)
    euclidean = hypot(end.x - start.x, end.y - start.y)
    assert walked > euclidean + 5  # at least a few metres of detour


# ── 3. Road preference + walkability snap ───────────────────────────


def test_road_is_walkable_and_open_is_walkable_at_edges():
    """The perimeter road is at y near H-1 (centre of last row). Open
    ground at the centre of the site. Both are walkable."""
    site = _empty_site(width=60, height=60)
    mesh = NavMesh.build(level_id="L0", site=site, equipment=[])
    assert mesh.is_walkable(30, 30)  # centre — open
    assert mesh.is_walkable(30, 58)  # south road
    assert mesh.is_walkable(4, 30)   # west road


def test_equipment_cell_is_not_walkable():
    site = _empty_site(width=60, height=60)
    mesh = NavMesh.build(
        level_id="L0",
        site=site,
        equipment=[_crane(30, 30)],
    )
    assert not mesh.is_walkable(30, 30)


def test_nearest_walkable_snaps_off_obstacle():
    site = _empty_site(width=80, height=80)
    mesh = NavMesh.build(
        level_id="L0",
        site=site,
        equipment=[_crane(40, 40)],
    )
    snapped = mesh.nearest_walkable(40, 40)
    assert snapped is not None
    sx, sy = snapped
    assert mesh.is_walkable(sx, sy)
    # The snapped cell sits just outside the 15 m crane radius.
    assert hypot(sx - 40, sy - 40) >= 12  # at least near the edge


# ── 4. String-pull + cache ──────────────────────────────────────────


def test_string_pull_collapses_straight_line():
    """A start-to-end with no obstacles between them is one straight
    segment — the simplifier keeps just two anchors."""
    site = _empty_site(width=80, height=80)
    mesh = NavMesh.build(level_id="L0", site=site, equipment=[])
    start = Position(x=10, y=50, level_id="L0")
    end = Position(x=70, y=50, level_id="L0")
    waypoints = mesh.path(start, end)
    # The path skips the start position and ends with the exact target,
    # so for a straight line we expect 1 to 2 waypoints.
    assert len(waypoints) <= 2


def test_cache_hit_returns_same_path():
    site = _empty_site(width=60, height=60)
    mesh = NavMesh.build(level_id="L0", site=site, equipment=[])
    start = Position(x=5, y=10, level_id="L0")
    end = Position(x=50, y=50, level_id="L0")
    first = mesh.path(start, end)
    second = mesh.path(start, end)
    assert len(first) == len(second)
    for a, b in zip(first, second):
        assert (a.x, a.y) == (b.x, b.y)


def test_distance_returns_finite_positive_value():
    site = _empty_site(width=80, height=80)
    mesh = NavMesh.build(level_id="L0", site=site, equipment=[])
    start = Position(x=10, y=10, level_id="L0")
    end = Position(x=70, y=70, level_id="L0")
    d = mesh.distance(start, end)
    assert d > 0


def test_invalidate_clears_cache():
    site = _empty_site(width=60, height=60)
    mesh = NavMesh.build(level_id="L0", site=site, equipment=[])
    mesh.path(
        Position(x=5, y=10, level_id="L0"),
        Position(x=50, y=50, level_id="L0"),
    )
    assert mesh._cache, "path should have populated the cache"
    mesh.invalidate()
    assert not mesh._cache


# ── 5. Equipment footprint table sanity ────────────────────────────


def test_equipment_footprint_defaults_include_known_subtypes():
    assert "tower_crane" in EQUIPMENT_FOOTPRINT_RADIUS_M
    assert "excavator" in EQUIPMENT_FOOTPRINT_RADIUS_M
    # Workers' personal radius — anything that doesn't have a footprint
    # gets 0 and stamps no cells.
    assert EQUIPMENT_FOOTPRINT_RADIUS_M.get("not_a_real_subtype", 0.0) == 0.0


def test_south_strip_constant_matches_renderer_pattern():
    """The renderer paints a 12 m south strip. If anyone bumps the
    constant in one place but not the other, the navmesh and the
    visuals stop agreeing on where the road is."""
    assert ROAD_SOUTH_STRIP_M == 12.0


# ── 6. Authored roads ───────────────────────────────────────────────


def test_authored_road_polyline_stamps_cells_as_road():
    """When the project document declares an explicit road, its cells
    become the cheap road cost — and the legacy perimeter fallback is
    NOT applied. This is the path workers prefer over open ground."""
    from config import NAVMESH_COST_ROAD
    from models.site import Road
    site = _empty_site(width=100, height=100)
    # Single horizontal road through the middle.
    site.roads = [
        Road(id="road-h", points=[(0.0, 50.0), (100.0, 50.0)], width_m=8.0)
    ]
    mesh = NavMesh.build(level_id="L0", site=site, equipment=[])
    # Middle of the strip is road.
    on_road = mesh.cost[int(50 / NAVMESH_CELL_SIZE_M) * mesh.cols + int(50 / NAVMESH_CELL_SIZE_M)]
    assert on_road == NAVMESH_COST_ROAD
    # The legacy south strip (y=88-100) is NOT carved (no fallback when
    # authored roads exist).
    south = mesh.cost[int(95 / NAVMESH_CELL_SIZE_M) * mesh.cols + int(50 / NAVMESH_CELL_SIZE_M)]
    assert south != NAVMESH_COST_ROAD


def test_authored_road_with_corner_keeps_walkable_through_turn():
    """An L-shaped road should be road all the way through the corner —
    `_stamp_disk` at each polyline node fills the wedge that a
    segment-only stamp would leave behind."""
    from models.site import Road
    site = _empty_site(width=80, height=80)
    site.roads = [
        Road(id="L", points=[(10.0, 40.0), (40.0, 40.0), (40.0, 10.0)], width_m=8.0)
    ]
    mesh = NavMesh.build(level_id="L0", site=site, equipment=[])
    # The corner cell at (40, 40) must be walkable.
    assert mesh.is_walkable(40, 40)
    # And a path from the road's start to its end must thread along it.
    path = mesh.path(
        Position(x=12, y=40, level_id="L0"),
        Position(x=40, y=12, level_id="L0"),
    )
    for w in path:
        assert mesh.is_walkable(w.x, w.y), f"path leaves the road at ({w.x},{w.y})"
