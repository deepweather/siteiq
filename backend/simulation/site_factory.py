import random
from models.site import Site, Zone, Phase, ScheduleEntry
from models.assets import Asset, Position, WorkerState, EquipmentState
from config import (
    SITE_WIDTH, SITE_HEIGHT, TOILET_INTERVAL, BREAK_INTERVAL,
    MATERIAL_RUN_INTERVAL, JITTER_FACTOR,
)


def _jitter(base: float) -> float:
    return base * (1.0 + random.uniform(-JITTER_FACTOR, JITTER_FACTOR))


ZONE_DEFS = [
    {"id": "zone-a", "label": "Zone A", "x": 10, "y": 10, "w": 70, "h": 60, "phase": Phase.FINISHES, "progress": 0.35,
     "workers": [("finishing", 8)]},
    {"id": "zone-b", "label": "Zone B", "x": 100, "y": 10, "w": 70, "h": 60, "phase": Phase.MEP_ROUGHIN, "progress": 0.55,
     "workers": [("mep", 12)]},
    {"id": "zone-c", "label": "Zone C", "x": 55, "y": 85, "w": 70, "h": 60, "phase": Phase.STRUCTURAL, "progress": 0.65,
     "workers": [("structural", 15)]},
    {"id": "zone-d", "label": "Zone D", "x": 10, "y": 85, "w": 40, "h": 60, "phase": Phase.FOUNDATION, "progress": 0.80,
     "workers": [("general", 8)]},
    {"id": "zone-e", "label": "Zone E", "x": 140, "y": 85, "w": 70, "h": 60, "phase": Phase.EXCAVATION, "progress": 0.40,
     "workers": [("general", 7)]},
]

FACILITY_DEFS = [
    {"id": "toilet-1", "subtype": "toilet", "x": 230, "y": 10},
    {"id": "toilet-2", "subtype": "toilet", "x": 230, "y": 150},
    {"id": "breakroom", "subtype": "breakroom", "x": 5, "y": 80},
    {"id": "office", "subtype": "office", "x": 5, "y": 5},
    {"id": "toolcrib", "subtype": "toolcrib", "x": 5, "y": 150},
]

EQUIPMENT_DEFS = [
    {"id": "crane-1", "subtype": "tower_crane", "x": 100, "y": 80, "state": EquipmentState.OPERATING},
    {"id": "pump-1", "subtype": "concrete_pump", "x": 50, "y": 150, "state": EquipmentState.IDLE},
    {"id": "excavator-1", "subtype": "excavator", "x": 170, "y": 120, "state": EquipmentState.OPERATING},
]

MATERIAL_DEFS = [
    {"id": "mat-rebar", "subtype": "rebar", "x": 120, "y": 155, "needed_in": "zone-c"},
    {"id": "mat-conduit", "subtype": "conduit", "x": 125, "y": 155, "needed_in": "zone-b"},
    {"id": "mat-drywall", "subtype": "drywall", "x": 115, "y": 155, "needed_in": "zone-a"},
    {"id": "mat-concrete", "subtype": "concrete", "x": 130, "y": 155, "needed_in": "zone-d"},
]

SCHEDULE = [
    ScheduleEntry(zone_id="zone-e", phase=Phase.EXCAVATION, start_day=1, end_day=30, trades_required=["general"]),
    ScheduleEntry(zone_id="zone-e", phase=Phase.FOUNDATION, start_day=31, end_day=55, trades_required=["general"]),
    ScheduleEntry(zone_id="zone-d", phase=Phase.FOUNDATION, start_day=15, end_day=50, trades_required=["general"]),
    ScheduleEntry(zone_id="zone-d", phase=Phase.STRUCTURAL, start_day=51, end_day=80, trades_required=["structural"]),
    ScheduleEntry(zone_id="zone-c", phase=Phase.STRUCTURAL, start_day=25, end_day=65, trades_required=["structural"]),
    ScheduleEntry(zone_id="zone-c", phase=Phase.MEP_ROUGHIN, start_day=66, end_day=90, trades_required=["mep"]),
    ScheduleEntry(zone_id="zone-b", phase=Phase.MEP_ROUGHIN, start_day=35, end_day=70, trades_required=["mep"]),
    ScheduleEntry(zone_id="zone-b", phase=Phase.CLOSEIN, start_day=71, end_day=95, trades_required=["general"]),
    ScheduleEntry(zone_id="zone-a", phase=Phase.FINISHES, start_day=40, end_day=85, trades_required=["finishing"]),
    ScheduleEntry(zone_id="zone-a", phase=Phase.COMPLETE, start_day=86, end_day=120, trades_required=[]),
]


def create_initial_site() -> tuple[Site, list[Asset], dict]:
    """Returns (site, assets, worker_internals) with deliberately suboptimal layout."""
    zones = [
        Zone(id=z["id"], label=z["label"], x=z["x"], y=z["y"],
             width=z["w"], height=z["h"], phase=z["phase"],
             phase_progress=z["progress"])
        for z in ZONE_DEFS
    ]

    site = Site(
        id="site-westhafen",
        name="Bauprojekt Westhafen — Berlin",
        width=SITE_WIDTH,
        height=SITE_HEIGHT,
        zones=zones,
        current_day=47,
        schedule=SCHEDULE,
    )

    assets: list[Asset] = []
    worker_internals: dict = {}

    worker_num = 1
    for zdef in ZONE_DEFS:
        for trade, count in zdef["workers"]:
            for _ in range(count):
                wid = f"worker-{worker_num:03d}"
                px = zdef["x"] + random.uniform(5, zdef["w"] - 5)
                py = zdef["y"] + random.uniform(5, zdef["h"] - 5)
                assets.append(Asset(
                    id=wid, type="worker", subtype=trade,
                    position=Position(x=px, y=py),
                    state=WorkerState.WORKING,
                    assigned_zone=zdef["id"],
                ))
                worker_internals[wid] = {
                    "next_toilet": _jitter(TOILET_INTERVAL * random.uniform(0.3, 1.0)),
                    "next_break": _jitter(BREAK_INTERVAL * random.uniform(0.5, 1.0)),
                    "next_material": _jitter(MATERIAL_RUN_INTERVAL * random.uniform(0.4, 1.0)),
                    "action_timer": 0.0,
                    "target": None,
                    "return_position": Position(x=px, y=py),
                    "total_distance": 0.0,
                    "time_working": 0.0,
                    "time_walking": 0.0,
                    "time_at_facilities": 0.0,
                    "toilet_trips_today": 0,
                    "toilet_trip_start_time": 0.0,
                    "toilet_total_round_trip": 0.0,
                    "material_trips_today": 0,
                    "material_trip_start_time": 0.0,
                    "material_total_round_trip": 0.0,
                }
                worker_num += 1

    for fdef in FACILITY_DEFS:
        assets.append(Asset(
            id=fdef["id"], type="facility", subtype=fdef["subtype"],
            position=Position(x=fdef["x"], y=fdef["y"]),
            state="active",
        ))

    for edef in EQUIPMENT_DEFS:
        assets.append(Asset(
            id=edef["id"], type="equipment", subtype=edef["subtype"],
            position=Position(x=edef["x"], y=edef["y"]),
            state=edef["state"],
            metadata={"hours_active": 0.0, "hours_idle": 0.0, "cycle_timer": 0.0},
        ))

    for mdef in MATERIAL_DEFS:
        assets.append(Asset(
            id=mdef["id"], type="material", subtype=mdef["subtype"],
            position=Position(x=mdef["x"], y=mdef["y"]),
            state="staged",
            metadata={"needed_in_zone": mdef["needed_in"]},
        ))

    return site, assets, worker_internals
