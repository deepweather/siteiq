"""LiveSource: SiteStateSource conformance, event folding, and the live-mode
HTTP toggle."""
from __future__ import annotations

from seeds.loader import load_seed_document
from state.live_source import LiveSource


class _Event:
    def __init__(self, kind, subject_id, payload):
        self.kind = kind
        self.subject_id = subject_id
        self.payload = payload


def test_live_source_conforms_and_folds_equipment_state():
    doc = load_seed_document("westhafen")
    assert doc is not None
    live = LiveSource(doc)
    # Duck-types the whole read Protocol via delegation to a non-ticking engine.
    assert live.site.zones
    assert callable(live.asset_by_id) and callable(live.workers_in_zone)
    assert live.levels is not None
    assert live.running is False  # never auto-ticked

    equipment = [a for a in live.assets if a.type == "equipment"]
    assert equipment
    target = equipment[0]

    live.apply_events([
        _Event("equipment.state_changed", target.id, {"state": "idle"})
    ])
    assert str(live.asset_by_id(target.id).state) in ("idle", "EquipmentState.IDLE")


def test_live_source_folds_worker_position():
    doc = load_seed_document("westhafen")
    live = LiveSource(doc)
    workers = [a for a in live.assets if a.type == "worker"]
    assert workers
    w = workers[0]
    live.apply_events([
        _Event("worker.position", w.id, {"x": 12.5, "y": 34.0})
    ])
    moved = live.asset_by_id(w.id)
    assert moved.position.x == 12.5 and moved.position.y == 34.0


def test_live_mode_toggle_swaps_source(auth_client):
    on = auth_client.post("/api/simulation/mode", json={"live": True})
    assert on.status_code == 200 and on.json()["live"] is True

    # The dashboard still works (site comes from the project layout).
    site = auth_client.get("/api/site")
    assert site.status_code == 200
    assert site.json()["zones"]

    # Sim-only controls now report 501 (live source isn't a SimulationEngine).
    assert auth_client.post("/api/simulation/pause").status_code == 501

    off = auth_client.post("/api/simulation/mode", json={"live": False})
    assert off.json()["live"] is False
    # Pause works again on the simulation source.
    assert auth_client.post("/api/simulation/pause").status_code == 200
