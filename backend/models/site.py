from pydantic import BaseModel
from enum import Enum

from models.assets import DEFAULT_LEVEL_ID


class Phase(str, Enum):
    EXCAVATION = "excavation"
    # Tiefbau-specific phases (Phase 5 wires the renderer + behaviour).
    SHORING = "shoring"
    PILING = "piling"
    DRAINAGE = "drainage"
    FOUNDATION = "foundation"
    STRUCTURAL = "structural"
    MEP_ROUGHIN = "mep_roughin"
    CLOSEIN = "closein"
    FINISHES = "finishes"
    PAVING = "paving"
    COMPLETE = "complete"


class Discipline(str, Enum):
    """Construction discipline tag on a project. Drives default level
    structure, palette of available phases, and renderer hints."""

    HOCHBAU = "hochbau"
    TIEFBAU = "tiefbau"
    HYBRID = "hybrid"


class Level(BaseModel):
    """A named vertical slice of the site. Workers move within a level
    continuously; cross-level travel goes through a `Connection` (stair
    or elevator). `elevation_m` is the floor's height above grade; can
    be negative for Tiefgarage / UG levels."""

    id: str
    name: str
    elevation_m: float
    order: int
    background_image_url: str | None = None


class Zone(BaseModel):
    id: str
    label: str
    x: float
    y: float
    width: float
    height: float
    phase: Phase
    phase_progress: float
    level_id: str = DEFAULT_LEVEL_ID


class ScheduleEntry(BaseModel):
    zone_id: str
    phase: Phase
    start_day: int
    end_day: int
    trades_required: list[str]


class Road(BaseModel):
    """Authored walkable corridor. A polyline of `(x, y)` points; the
    navmesh + renderer stamp a strip of `width_m` along each segment.

    Roads are the cheapest cells on the navmesh — workers prefer them
    over open ground and over zone interiors. Drawing them is the
    canvas equivalent: a darker strip with a dashed centre line.
    """

    id: str
    points: list[tuple[float, float]]
    width_m: float = 6.0
    level_id: str = "L0"


class Site(BaseModel):
    id: str
    name: str
    width: float
    height: float
    zones: list[Zone]
    current_day: int
    schedule: list[ScheduleEntry] = []
    discipline: Discipline = Discipline.HOCHBAU
    levels: list[Level] = []
    # Authored road / pedestrian-corridor network. When empty the navmesh
    # and renderer fall back to the legacy hardcoded perimeter pattern
    # (south + west strips). Polyline-based so authors can curve roads
    # around obstacles rather than be limited to grid-aligned strips.
    roads: list[Road] = []
