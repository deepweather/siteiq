from pydantic import BaseModel
from enum import Enum


class Phase(str, Enum):
    EXCAVATION = "excavation"
    FOUNDATION = "foundation"
    STRUCTURAL = "structural"
    MEP_ROUGHIN = "mep_roughin"
    CLOSEIN = "closein"
    FINISHES = "finishes"
    COMPLETE = "complete"


class Zone(BaseModel):
    id: str
    label: str
    x: float
    y: float
    width: float
    height: float
    phase: Phase
    phase_progress: float


class ScheduleEntry(BaseModel):
    zone_id: str
    phase: Phase
    start_day: int
    end_day: int
    trades_required: list[str]


class Site(BaseModel):
    id: str
    name: str
    width: float
    height: float
    zones: list[Zone]
    current_day: int
    schedule: list[ScheduleEntry] = []
