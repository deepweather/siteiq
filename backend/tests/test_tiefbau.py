"""Phase 5 — Tiefbau discipline tests.

Covers the new dewatering-pump duty cycle, the shoring-compliance KPI,
and the new Munich sewer seed end-to-end."""
from __future__ import annotations

from models.assets import EquipmentState
from models.project_document import (
    EquipmentSpec,
    ProjectDocument,
    WorkerSeed,
)
from models.site import Discipline, Level, Phase, Zone
from simulation.engine import SimulationEngine
from simulation.tiefbau_behavior import compute_shoring_compliance


def test_munich_sewer_seed_loads_and_ticks():
    eng = SimulationEngine(project_id="munich-sewer")
    assert eng.site.discipline == Discipline.TIEFBAU
    assert any(a.subtype == "sheet_pile" for a in eng.assets)
    assert any(a.subtype == "dewatering_pump" for a in eng.assets)
    # Spin a hundred ticks; nothing should crash.
    for _ in range(100):
        eng.tick()
    # Dewatering pump should have accumulated hours_active.
    pump = next(a for a in eng.assets if a.subtype == "dewatering_pump")
    assert pump.metadata.get("hours_active", 0.0) > 0.0


def test_sheet_pile_keeps_operating_state():
    """Sheet piles don't cycle — once placed, they're permanent. The
    Tiefbau update must not flip them to IDLE."""
    eng = SimulationEngine(project_id="munich-sewer")
    sps = [a for a in eng.assets if a.subtype == "sheet_pile"]
    assert sps  # munich-sewer has 5 sheet piles
    for _ in range(200):
        eng.tick()
    assert all(a.state == EquipmentState.OPERATING for a in sps)


def test_dewatering_pump_eventually_cycles_to_idle():
    """Default cycle: 2h operating, 30min idle. Sim runs 30s per tick,
    so after ~240 ticks (2h sim) the pump should hit IDLE."""
    eng = SimulationEngine(project_id="munich-sewer")
    pumps = [a for a in eng.assets if a.subtype == "dewatering_pump"]
    assert pumps
    flipped = False
    for _ in range(400):
        eng.tick()
        if any(p.state == EquipmentState.IDLE for p in pumps):
            flipped = True
            break
    assert flipped, "no dewatering pump ever flipped to IDLE within 400 ticks"


# ── Shoring compliance KPI ───────────────────────────────────────────


def _tiefbau_compliance_doc(*, sheet_pile_at: tuple[float, float] | None) -> ProjectDocument:
    """A single excavation zone with optional sheet pile nearby."""
    equipment = []
    if sheet_pile_at is not None:
        equipment.append(EquipmentSpec(
            id="sheet-1", subtype="sheet_pile",
            x=sheet_pile_at[0], y=sheet_pile_at[1], state="operating",
        ))
    return ProjectDocument(
        slug="comp-test",
        name="Shoring Compliance Test",
        description="",
        discipline=Discipline.TIEFBAU,
        width=100.0, height=80.0,
        levels=[Level(id="L0", name="EG", elevation_m=0.0, order=0)],
        zones=[Zone(
            id="z1", label="Z1", x=20, y=20, width=40, height=40,
            phase=Phase.EXCAVATION, phase_progress=0.5, level_id="L0",
        )],
        equipment=equipment,
        worker_seeds=[WorkerSeed(zone_id="z1", trade="general", count=2)],
    )


def test_shoring_compliance_one_for_well_backed_zone():
    """Sheet pile inside the influence radius (25m) of the zone centre
    (40, 40) — compliance should be 1.0."""
    eng = SimulationEngine(document=_tiefbau_compliance_doc(sheet_pile_at=(45, 45)))
    res = compute_shoring_compliance(eng)
    assert len(res) == 1
    assert res[0].zone_id == "z1"
    assert res[0].compliance == 1.0
    assert res[0].nearest_sheet_pile_id == "sheet-1"
    assert res[0].nearest_distance_m is not None
    assert res[0].nearest_distance_m < 25.0


def test_shoring_compliance_zero_when_no_sheet_pile():
    """No sheet pile anywhere → compliance = 0.0."""
    eng = SimulationEngine(document=_tiefbau_compliance_doc(sheet_pile_at=None))
    res = compute_shoring_compliance(eng)
    assert len(res) == 1
    assert res[0].compliance == 0.0
    assert res[0].nearest_sheet_pile_id is None


def test_shoring_compliance_zero_when_sheet_pile_too_far():
    """Sheet pile 60m away — well outside the 25m radius."""
    eng = SimulationEngine(document=_tiefbau_compliance_doc(sheet_pile_at=(95, 70)))
    res = compute_shoring_compliance(eng)
    assert len(res) == 1
    assert res[0].compliance == 0.0
    assert res[0].nearest_sheet_pile_id == "sheet-1"
    assert res[0].nearest_distance_m is not None
    assert res[0].nearest_distance_m > 25.0


def test_shoring_compliance_skips_non_excavation_zones():
    eng = SimulationEngine(project_id="westhafen")  # no EXCAVATION zones currently
    # Westhafen has zone-e in EXCAVATION phase (progress 0.4), so it
    # is included. But no sheet piles exist there → compliance 0.0.
    res = compute_shoring_compliance(eng)
    assert all(r.compliance == 0.0 for r in res)


def test_munich_sewer_compliance_is_partial():
    """Munich-sewer has sheet piles along the line — some zones should
    be covered, others not depending on their distance."""
    eng = SimulationEngine(project_id="munich-sewer")
    res = compute_shoring_compliance(eng)
    # zone-b and zone-c are EXCAVATION; sheet-pile-b is at (80, 35),
    # zone-b centre is (85, 40) — well within 25m.
    by_zone = {r.zone_id: r for r in res}
    assert "zone-b" in by_zone
    assert by_zone["zone-b"].compliance == 1.0


def test_seed_includes_tiefbau_phases():
    eng = SimulationEngine(project_id="munich-sewer")
    phases = {e.phase for e in eng.site.schedule}
    assert Phase.SHORING in phases
    assert Phase.DRAINAGE in phases
    assert Phase.PAVING in phases
