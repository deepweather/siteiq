"""Turn a `ProjectDocument` into the engine's initial state.

This is the only place in the codebase that translates the canonical
document format into Pydantic `Site` / `Asset` / `WorkerInternals`
values. Every other layer reads or writes the document as-is.
"""
from __future__ import annotations

import random

from config import (
    BREAK_INTERVAL,
    JITTER_FACTOR,
    MATERIAL_RUN_INTERVAL,
    TOILET_INTERVAL,
)
from models.assets import Asset, EquipmentState, Position, WorkerState
from models.connection import Connection
from models.project_document import ProjectDocument
from models.site import Site
from simulation.worker_internals import WorkerInternals


def _jitter(base: float) -> float:
    return base * (1.0 + random.uniform(-JITTER_FACTOR, JITTER_FACTOR))


def build_engine_state(
    doc: ProjectDocument,
) -> tuple[Site, list[Asset], dict[str, WorkerInternals], list[Connection]]:
    """Materialise a project document into the tuple the engine expects.

    The connections list is returned alongside the assets so the engine
    can stash them on a per-instance attribute without having to dig
    them out of the document later.
    """
    site = Site(
        id=f"site-{doc.slug}",
        name=doc.name,
        width=doc.width,
        height=doc.height,
        zones=list(doc.zones),
        current_day=doc.start_day,
        schedule=list(doc.schedule),
        discipline=doc.discipline,
        levels=list(doc.levels),
    )

    assets: list[Asset] = []
    worker_internals: dict[str, WorkerInternals] = {}

    # Build a per-zone position sampler so worker_seeds can place workers
    # randomly inside the zone they were assigned to.
    zone_by_id = {z.id: z for z in doc.zones}

    worker_num = 1
    for seed in doc.worker_seeds:
        zone = zone_by_id.get(seed.zone_id)
        if zone is None or seed.count <= 0:
            continue
        for _ in range(seed.count):
            wid = f"worker-{worker_num:03d}"
            px = zone.x + random.uniform(5, max(zone.width - 5, 6))
            py = zone.y + random.uniform(5, max(zone.height - 5, 6))
            assets.append(Asset(
                id=wid,
                type="worker",
                subtype=seed.trade,
                position=Position(x=px, y=py, level_id=zone.level_id),
                state=WorkerState.WORKING,
                assigned_zone=zone.id,
            ))
            worker_internals[wid] = WorkerInternals(
                next_toilet=_jitter(TOILET_INTERVAL * random.uniform(0.3, 1.0)),
                next_break=_jitter(BREAK_INTERVAL * random.uniform(0.5, 1.0)),
                next_material=_jitter(MATERIAL_RUN_INTERVAL * random.uniform(0.4, 1.0)),
                return_position=Position(x=px, y=py, level_id=zone.level_id),
            )
            worker_num += 1

    for f in doc.facilities:
        assets.append(Asset(
            id=f.id,
            type="facility",
            subtype=f.subtype,
            position=Position(x=f.x, y=f.y, level_id=f.level_id),
            state="active",
        ))

    for e in doc.equipment:
        assets.append(Asset(
            id=e.id,
            type="equipment",
            subtype=e.subtype,
            position=Position(x=e.x, y=e.y, level_id=e.level_id),
            state=e.state if e.state in (EquipmentState.OPERATING, EquipmentState.IDLE) else EquipmentState.OPERATING,
            metadata={"hours_active": 0.0, "hours_idle": 0.0, "cycle_timer": 0.0},
        ))

    for m in doc.materials:
        assets.append(Asset(
            id=m.id,
            type="material",
            subtype=m.subtype,
            position=Position(x=m.x, y=m.y, level_id=m.level_id),
            state="staged",
            metadata={"needed_in_zone": m.needed_in},
        ))

    return site, assets, worker_internals, list(doc.connections)
