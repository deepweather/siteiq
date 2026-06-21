import random
from models.site import Site, Zone, Phase, ScheduleEntry
from models.assets import Asset, Position, WorkerState, EquipmentState
from simulation.worker_internals import WorkerInternals
from config import (
    TOILET_INTERVAL, BREAK_INTERVAL,
    MATERIAL_RUN_INTERVAL, JITTER_FACTOR,
)


def _jitter(base: float) -> float:
    return base * (1.0 + random.uniform(-JITTER_FACTOR, JITTER_FACTOR))


# ── Project Templates ───────────────────────────────────────────────

PROJECT_TEMPLATES = {

    # ── 1. Residential Multi-Family (Mehrfamilienhaus) ──────────────
    # Typical Berlin 5-story MFH, ~60 units, tight urban site
    "westhafen": {
        "id": "site-westhafen",
        "name": "Wohnanlage Westhafen — Berlin",
        "description": "60-unit residential complex, 5 stories, underground parking. Tight urban site with constrained access.",
        "type": "Residential",
        "width": 240,
        "height": 160,
        "start_day": 47,
        "zones": [
            {"id": "zone-a", "label": "Block A", "x": 10, "y": 10, "w": 70, "h": 60, "phase": Phase.FINISHES, "progress": 0.35,
             "workers": [("finishing", 8)]},
            {"id": "zone-b", "label": "Block B", "x": 100, "y": 10, "w": 70, "h": 60, "phase": Phase.MEP_ROUGHIN, "progress": 0.55,
             "workers": [("mep", 12)]},
            {"id": "zone-c", "label": "Block C", "x": 55, "y": 85, "w": 70, "h": 60, "phase": Phase.STRUCTURAL, "progress": 0.65,
             "workers": [("structural", 15)]},
            {"id": "zone-d", "label": "Tiefgarage", "x": 10, "y": 85, "w": 40, "h": 60, "phase": Phase.FOUNDATION, "progress": 0.80,
             "workers": [("general", 8)]},
            {"id": "zone-e", "label": "Außenanlagen", "x": 140, "y": 85, "w": 70, "h": 60, "phase": Phase.EXCAVATION, "progress": 0.40,
             "workers": [("general", 7)]},
        ],
        "facilities": [
            {"id": "toilet-1", "subtype": "toilet", "x": 230, "y": 10},
            {"id": "toilet-2", "subtype": "toilet", "x": 230, "y": 150},
            {"id": "breakroom", "subtype": "breakroom", "x": 5, "y": 80},
            {"id": "office", "subtype": "office", "x": 5, "y": 5},
            {"id": "toolcrib", "subtype": "toolcrib", "x": 5, "y": 150},
        ],
        "equipment": [
            {"id": "crane-1", "subtype": "tower_crane", "x": 100, "y": 80, "state": EquipmentState.OPERATING},
            {"id": "pump-1", "subtype": "concrete_pump", "x": 50, "y": 150, "state": EquipmentState.IDLE},
            {"id": "excavator-1", "subtype": "excavator", "x": 170, "y": 120, "state": EquipmentState.OPERATING},
        ],
        "materials": [
            {"id": "mat-rebar", "subtype": "rebar", "x": 120, "y": 155, "needed_in": "zone-c"},
            {"id": "mat-conduit", "subtype": "conduit", "x": 125, "y": 155, "needed_in": "zone-b"},
            {"id": "mat-drywall", "subtype": "drywall", "x": 115, "y": 155, "needed_in": "zone-a"},
            {"id": "mat-concrete", "subtype": "concrete", "x": 130, "y": 155, "needed_in": "zone-d"},
        ],
        "schedule": [
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
        ],
    },

    # ── 2. Commercial Office (Bürogebäude) ──────────────────────────
    # Modern office campus in Frankfurt, two wings + lobby, larger site
    "europa-quarter": {
        "id": "site-europa",
        "name": "Bürocampus Europaviertel — Frankfurt",
        "description": "12-story office tower with 2 wings, 18,000m² GFA. Open site with good access but poor facility placement.",
        "type": "Commercial",
        "width": 300,
        "height": 200,
        "start_day": 82,
        "zones": [
            {"id": "zone-a", "label": "Turm Ost", "x": 30, "y": 20, "w": 80, "h": 70, "phase": Phase.CLOSEIN, "progress": 0.45,
             "workers": [("general", 10), ("mep", 6)]},
            {"id": "zone-b", "label": "Turm West", "x": 140, "y": 20, "w": 80, "h": 70, "phase": Phase.STRUCTURAL, "progress": 0.70,
             "workers": [("structural", 14)]},
            {"id": "zone-c", "label": "Lobby / Atrium", "x": 110, "y": 95, "w": 60, "h": 45, "phase": Phase.MEP_ROUGHIN, "progress": 0.30,
             "workers": [("mep", 8)]},
            {"id": "zone-d", "label": "Tiefgarage P1", "x": 15, "y": 110, "w": 90, "h": 70, "phase": Phase.FINISHES, "progress": 0.60,
             "workers": [("finishing", 10)]},
            {"id": "zone-e", "label": "Tiefgarage P2", "x": 130, "y": 145, "w": 90, "h": 45, "phase": Phase.FOUNDATION, "progress": 0.85,
             "workers": [("general", 6)]},
            {"id": "zone-f", "label": "Außenanlagen", "x": 230, "y": 20, "w": 55, "h": 120, "phase": Phase.EXCAVATION, "progress": 0.25,
             "workers": [("general", 6)]},
        ],
        "facilities": [
            {"id": "toilet-1", "subtype": "toilet", "x": 290, "y": 10},
            {"id": "toilet-2", "subtype": "toilet", "x": 290, "y": 190},
            {"id": "toilet-3", "subtype": "toilet", "x": 10, "y": 190},
            {"id": "breakroom", "subtype": "breakroom", "x": 10, "y": 100},
            {"id": "office", "subtype": "office", "x": 10, "y": 10},
            {"id": "toolcrib", "subtype": "toolcrib", "x": 150, "y": 195},
        ],
        "equipment": [
            {"id": "crane-1", "subtype": "tower_crane", "x": 120, "y": 55, "state": EquipmentState.OPERATING},
            {"id": "crane-2", "subtype": "tower_crane", "x": 200, "y": 55, "state": EquipmentState.IDLE},
            {"id": "pump-1", "subtype": "concrete_pump", "x": 55, "y": 195, "state": EquipmentState.IDLE},
            {"id": "excavator-1", "subtype": "excavator", "x": 260, "y": 80, "state": EquipmentState.OPERATING},
        ],
        "materials": [
            {"id": "mat-rebar", "subtype": "rebar", "x": 145, "y": 195, "needed_in": "zone-b"},
            {"id": "mat-conduit", "subtype": "conduit", "x": 155, "y": 195, "needed_in": "zone-c"},
            {"id": "mat-drywall", "subtype": "drywall", "x": 135, "y": 195, "needed_in": "zone-d"},
            {"id": "mat-concrete", "subtype": "concrete", "x": 165, "y": 195, "needed_in": "zone-e"},
            {"id": "mat-glass", "subtype": "drywall", "x": 175, "y": 195, "needed_in": "zone-a"},
        ],
        "schedule": [
            ScheduleEntry(zone_id="zone-e", phase=Phase.FOUNDATION, start_day=1, end_day=40, trades_required=["general"]),
            ScheduleEntry(zone_id="zone-e", phase=Phase.STRUCTURAL, start_day=41, end_day=70, trades_required=["structural"]),
            ScheduleEntry(zone_id="zone-d", phase=Phase.STRUCTURAL, start_day=20, end_day=55, trades_required=["structural"]),
            ScheduleEntry(zone_id="zone-d", phase=Phase.FINISHES, start_day=56, end_day=100, trades_required=["finishing"]),
            ScheduleEntry(zone_id="zone-b", phase=Phase.STRUCTURAL, start_day=30, end_day=90, trades_required=["structural"]),
            ScheduleEntry(zone_id="zone-b", phase=Phase.MEP_ROUGHIN, start_day=91, end_day=120, trades_required=["mep"]),
            ScheduleEntry(zone_id="zone-c", phase=Phase.MEP_ROUGHIN, start_day=60, end_day=95, trades_required=["mep"]),
            ScheduleEntry(zone_id="zone-c", phase=Phase.FINISHES, start_day=96, end_day=130, trades_required=["finishing"]),
            ScheduleEntry(zone_id="zone-a", phase=Phase.CLOSEIN, start_day=50, end_day=100, trades_required=["general", "mep"]),
            ScheduleEntry(zone_id="zone-a", phase=Phase.FINISHES, start_day=101, end_day=140, trades_required=["finishing"]),
            ScheduleEntry(zone_id="zone-f", phase=Phase.EXCAVATION, start_day=70, end_day=110, trades_required=["general"]),
            ScheduleEntry(zone_id="zone-f", phase=Phase.FOUNDATION, start_day=111, end_day=140, trades_required=["general"]),
        ],
    },

    # ── 3. Infrastructure / Bridge (Brückenbau / Infrastruktur) ─────
    # Highway bridge replacement near Munich, linear site, heavy civil
    "isar-bridge": {
        "id": "site-isar",
        "name": "Brückenneubau B2 Isarbrücke — München",
        "description": "120m span highway bridge replacement. Linear construction site along the river with phased lane closures.",
        "type": "Infrastructure",
        "width": 350,
        "height": 120,
        "start_day": 135,
        "zones": [
            {"id": "zone-a", "label": "Widerlager West", "x": 10, "y": 25, "w": 60, "h": 70, "phase": Phase.FOUNDATION, "progress": 0.90,
             "workers": [("structural", 10)]},
            {"id": "zone-b", "label": "Pfeiler 1-3", "x": 80, "y": 30, "w": 70, "h": 60, "phase": Phase.STRUCTURAL, "progress": 0.55,
             "workers": [("structural", 12)]},
            {"id": "zone-c", "label": "Überbau Mitte", "x": 160, "y": 25, "w": 80, "h": 70, "phase": Phase.STRUCTURAL, "progress": 0.30,
             "workers": [("structural", 16), ("general", 4)]},
            {"id": "zone-d", "label": "Pfeiler 4-6", "x": 250, "y": 30, "w": 50, "h": 60, "phase": Phase.EXCAVATION, "progress": 0.60,
             "workers": [("general", 8)]},
            {"id": "zone-e", "label": "Widerlager Ost", "x": 310, "y": 25, "w": 35, "h": 70, "phase": Phase.EXCAVATION, "progress": 0.20,
             "workers": [("general", 6)]},
        ],
        "facilities": [
            {"id": "toilet-1", "subtype": "toilet", "x": 5, "y": 5},
            {"id": "toilet-2", "subtype": "toilet", "x": 345, "y": 5},
            {"id": "breakroom", "subtype": "breakroom", "x": 175, "y": 5},
            {"id": "office", "subtype": "office", "x": 5, "y": 110},
            {"id": "toolcrib", "subtype": "toolcrib", "x": 345, "y": 110},
        ],
        "equipment": [
            {"id": "crane-1", "subtype": "tower_crane", "x": 130, "y": 55, "state": EquipmentState.OPERATING},
            {"id": "crane-2", "subtype": "tower_crane", "x": 230, "y": 55, "state": EquipmentState.OPERATING},
            {"id": "pump-1", "subtype": "concrete_pump", "x": 90, "y": 110, "state": EquipmentState.IDLE},
            {"id": "pump-2", "subtype": "concrete_pump", "x": 270, "y": 110, "state": EquipmentState.IDLE},
            {"id": "excavator-1", "subtype": "excavator", "x": 300, "y": 75, "state": EquipmentState.OPERATING},
        ],
        "materials": [
            {"id": "mat-rebar", "subtype": "rebar", "x": 170, "y": 115, "needed_in": "zone-c"},
            {"id": "mat-rebar-2", "subtype": "rebar", "x": 180, "y": 115, "needed_in": "zone-b"},
            {"id": "mat-concrete", "subtype": "concrete", "x": 160, "y": 115, "needed_in": "zone-a"},
            {"id": "mat-concrete-2", "subtype": "concrete", "x": 190, "y": 115, "needed_in": "zone-d"},
        ],
        "schedule": [
            ScheduleEntry(zone_id="zone-a", phase=Phase.FOUNDATION, start_day=1, end_day=50, trades_required=["structural"]),
            ScheduleEntry(zone_id="zone-a", phase=Phase.STRUCTURAL, start_day=51, end_day=110, trades_required=["structural"]),
            ScheduleEntry(zone_id="zone-b", phase=Phase.EXCAVATION, start_day=20, end_day=60, trades_required=["general"]),
            ScheduleEntry(zone_id="zone-b", phase=Phase.STRUCTURAL, start_day=61, end_day=140, trades_required=["structural"]),
            ScheduleEntry(zone_id="zone-c", phase=Phase.STRUCTURAL, start_day=80, end_day=180, trades_required=["structural", "general"]),
            ScheduleEntry(zone_id="zone-d", phase=Phase.EXCAVATION, start_day=100, end_day=150, trades_required=["general"]),
            ScheduleEntry(zone_id="zone-d", phase=Phase.FOUNDATION, start_day=151, end_day=190, trades_required=["structural"]),
            ScheduleEntry(zone_id="zone-e", phase=Phase.EXCAVATION, start_day=120, end_day=170, trades_required=["general"]),
            ScheduleEntry(zone_id="zone-e", phase=Phase.FOUNDATION, start_day=171, end_day=210, trades_required=["structural"]),
        ],
    },
}


def get_project_list() -> list[dict]:
    return [
        {
            "id": key,
            "name": tmpl["name"],
            "description": tmpl["description"],
            "type": tmpl["type"],
        }
        for key, tmpl in PROJECT_TEMPLATES.items()
    ]


def create_site_from_template(
    project_id: str,
) -> tuple[Site, list[Asset], dict[str, WorkerInternals]]:
    tmpl = PROJECT_TEMPLATES.get(project_id)
    if not tmpl:
        raise ValueError(f"Unknown project: {project_id}")

    zones = [
        Zone(id=z["id"], label=z["label"], x=z["x"], y=z["y"],
             width=z["w"], height=z["h"], phase=z["phase"],
             phase_progress=z["progress"])
        for z in tmpl["zones"]
    ]

    site = Site(
        id=tmpl["id"],
        name=tmpl["name"],
        width=tmpl["width"],
        height=tmpl["height"],
        zones=zones,
        current_day=tmpl["start_day"],
        schedule=tmpl["schedule"],
    )

    assets: list[Asset] = []
    worker_internals: dict[str, WorkerInternals] = {}

    worker_num = 1
    for zdef in tmpl["zones"]:
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
                worker_internals[wid] = WorkerInternals(
                    next_toilet=_jitter(TOILET_INTERVAL * random.uniform(0.3, 1.0)),
                    next_break=_jitter(BREAK_INTERVAL * random.uniform(0.5, 1.0)),
                    next_material=_jitter(MATERIAL_RUN_INTERVAL * random.uniform(0.4, 1.0)),
                    return_position=Position(x=px, y=py),
                )
                worker_num += 1

    for fdef in tmpl["facilities"]:
        assets.append(Asset(
            id=fdef["id"], type="facility", subtype=fdef["subtype"],
            position=Position(x=fdef["x"], y=fdef["y"]),
            state="active",
        ))

    for edef in tmpl["equipment"]:
        assets.append(Asset(
            id=edef["id"], type="equipment", subtype=edef["subtype"],
            position=Position(x=edef["x"], y=edef["y"]),
            state=edef["state"],
            metadata={"hours_active": 0.0, "hours_idle": 0.0, "cycle_timer": 0.0},
        ))

    for mdef in tmpl["materials"]:
        assets.append(Asset(
            id=mdef["id"], type="material", subtype=mdef["subtype"],
            position=Position(x=mdef["x"], y=mdef["y"]),
            state="staged",
            metadata={"needed_in_zone": mdef["needed_in"]},
        ))

    return site, assets, worker_internals


def create_initial_site() -> tuple[Site, list[Asset], dict]:
    """Default: first template."""
    return create_site_from_template("westhafen")
