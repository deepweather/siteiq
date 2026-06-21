from pydantic import BaseModel


class Position(BaseModel):
    x: float
    y: float


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
    IDLE = "idle"


class EquipmentState:
    OPERATING = "operating"
    IDLE = "idle"
    REMOVED = "removed"
