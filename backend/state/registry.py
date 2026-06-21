"""Per-org simulation registry.

Until this module the backend ran a single global `SimulationEngine`,
so two orgs viewing the dashboard saw the same workers. Now each org
gets its own engine + recommendation service, lazily created on first
access and cached for the app's lifetime. The simulation/analytics loop
iterates every live engine.

The registry is the natural home for a future `LiveSource` (real
camera-fed) implementation: same lookup signature, different
constructor.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Callable

from services.recommendation_service import RecommendationService
from simulation.engine import SimulationEngine
from state.source import SiteStateSource


logger = logging.getLogger("siteiq.state.registry")


EngineFactory = Callable[[str], SimulationEngine]


def _default_factory(default_project_id: str) -> EngineFactory:
    def make(_org_id: str) -> SimulationEngine:
        return SimulationEngine(project_id=default_project_id)

    return make


class SourceRegistry:
    """Owns one `SimulationEngine` (and its `RecommendationService`) per
    org id. Thread-safe-enough for a single-process FastAPI worker
    (the app.state pattern guarantees no cross-app sharing).

    Tests can pre-seed an entry to inject a stub source via
    `registry.set(org_id, source)`.
    """

    def __init__(self, factory: EngineFactory) -> None:
        self._factory = factory
        self._engines: dict[str, SimulationEngine] = {}
        self._rec_services: dict[str, RecommendationService] = {}
        self._latest_analytics: dict[str, object | None] = {}

    # ---- engines ----------------------------------------------------

    def for_org(self, org_id: str) -> SimulationEngine:
        eng = self._engines.get(org_id)
        if eng is None:
            eng = self._factory(org_id)
            self._engines[org_id] = eng
            self._rec_services[org_id] = RecommendationService(eng)
            logger.info("source_engine_created", extra={"org_id": org_id, "project": eng.project_id})
        return eng

    def set(self, org_id: str, source: SimulationEngine) -> None:
        """Test hook: replace (or pre-seed) a source for an org."""
        self._engines[org_id] = source
        self._rec_services[org_id] = RecommendationService(source)

    def all_engines(self) -> list[SimulationEngine]:
        return list(self._engines.values())

    def items(self) -> list[tuple[str, SimulationEngine]]:
        return list(self._engines.items())

    def discard(self, org_id: str) -> None:
        """Drop an org's engine + rec service (called when an org is deleted)."""
        eng = self._engines.pop(org_id, None)
        if eng is not None:
            eng.running = False
        self._rec_services.pop(org_id, None)
        self._latest_analytics.pop(org_id, None)
        logger.info("source_engine_discarded", extra={"org_id": org_id})

    # ---- ancillary state -------------------------------------------

    def rec_service_for(self, org_id: str) -> RecommendationService:
        # Ensure the engine exists first so the rec service is bound.
        self.for_org(org_id)
        return self._rec_services[org_id]

    def latest_analytics_for(self, org_id: str):
        return self._latest_analytics.get(org_id)

    def set_latest_analytics(self, org_id: str, value) -> None:
        self._latest_analytics[org_id] = value


def make_registry(default_project_id: str) -> SourceRegistry:
    return SourceRegistry(_default_factory(default_project_id))


async def run_loops_for_registry(
    registry: SourceRegistry,
    *,
    tick_interval: float,
) -> None:
    """Single asyncio task that ticks every known engine.

    A tick rate of 100 ms is tight enough that adding more orgs in dev
    is fine; in prod with many orgs, this scales to a worker pool with
    minimal change (one task per engine instead of round-robin).
    """
    while True:
        for engine in registry.all_engines():
            if engine.running and not engine.paused:
                try:
                    engine.tick()
                except Exception:
                    logger.exception(
                        "engine_tick_failed",
                        extra={"project_id": engine.project_id},
                    )
        await asyncio.sleep(tick_interval)
