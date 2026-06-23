from pydantic import BaseModel


DEFAULT_LEVEL_ID = "L0"


class Position(BaseModel):
    x: float
    y: float
    # Multi-level support. Existing single-floor data implicitly belongs
    # to level "L0" (ground floor), so the default keeps every legacy
    # consumer working unchanged.
    level_id: str = DEFAULT_LEVEL_ID


class Asset(BaseModel):
    id: str
    type: str
    subtype: str
    position: Position
    state: str
    assigned_zone: str | None = None
    metadata: dict = {}

    def to_broadcast_dict(self) -> dict:
        d = {
            "id": self.id,
            "type": self.type,
            "subtype": self.subtype,
            "x": round(self.position.x, 1),
            "y": round(self.position.y, 1),
            "state": self.state,
        }
        # Always include level_id so multi-level clients can filter even
        # when the asset happens to live on the default ground floor.
        d["lvl"] = self.position.level_id
        if self.assigned_zone:
            d["assigned_zone"] = self.assigned_zone
        return d


class WorkerState:
    WORKING = "working"
    WALKING_TO_TOILET = "walking_to_toilet"
    AT_TOILET = "at_toilet"
    WALKING_TO_BREAK = "walking_to_break"
    AT_BREAK = "at_break"
    WALKING_TO_MATERIAL = "walking_to_material"
    CARRYING_MATERIAL = "carrying_material"
    WALKING_TO_WORK = "walking_to_work"
    # Multi-level / vertical-transport states (Phase 3 wires the FSM).
    WALKING_TO_VERTICAL = "walking_to_vertical"
    TRAVERSING_VERTICAL = "traversing_vertical"
    IDLE = "idle"


class EquipmentState:
    OPERATING = "operating"
    IDLE = "idle"
    REMOVED = "removed"
