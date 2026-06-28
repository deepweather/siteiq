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

from models.project_document import ProjectDocument
from services.recommendation_service import RecommendationService
from simulation.engine import SimulationEngine
from state.live_source import LiveSource


logger = logging.getLogger("siteiq.state.registry")


EngineFactory = Callable[[str], SimulationEngine]


def _default_factory(default_project_id: str) -> EngineFactory:
    """Initial-engine factory used when the registry has no other
    knowledge about the org. The route layer's `get_source` overrides
    this with a per-org factory that reads `Org.active_project_id`."""
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

    def for_org(self, org_id: str, *, project_id: str | None = None) -> SimulationEngine:
        """Return (or lazily create) the org's engine. Pass `project_id`
        on first creation to seed it from a persisted org choice; later
        calls ignore it."""
        eng = self._engines.get(org_id)
        # Rebuild when missing OR when the cached source is a LiveSource (the
        # org just switched back to simulation mode).
        if eng is None or isinstance(eng, LiveSource):
            if project_id:
                eng = SimulationEngine(project_id=project_id)
            else:
                eng = self._factory(org_id)
            self._engines[org_id] = eng
            self._rec_services[org_id] = RecommendationService(eng)
            logger.info(
                "source_engine_created",
                extra={"org_id": org_id, "project": eng.project_id},
            )
        return eng

    def for_org_at_version(
        self,
        org_id: str,
        *,
        document: ProjectDocument,
        version_id: str,
    ) -> SimulationEngine:
        """Return the engine for the org, ensuring it's running on the
        document at `version_id`. If the engine is missing or pinned to
        a different version, it's torn down and rebuilt.

        Used by the editor / activate-version flow. The legacy
        `for_org(org_id, project_id=...)` path stays in place for the
        seed-slug-based load_project endpoint.
        """
        eng = self._engines.get(org_id)
        if isinstance(eng, SimulationEngine) and eng.project_version_id == version_id:
            return eng
        # Engines created via the legacy slug seed path (`for_org`) don't
        # tag themselves with the seed's content-hash version, so a
        # subsequent "activate this seed" call would mis-detect them as
        # stale and tear down a perfectly good engine — wiping simulation
        # day + every applied recommendation. The seed importer is
        # idempotent on content hash, so an engine that's already loaded
        # the same slug + has no version tag is, by construction, running
        # the same document this method is about to load. Tag it instead
        # of rebuilding.
        if (
            isinstance(eng, SimulationEngine)
            and eng.project_version_id is None
            and eng.project_id == document.slug
        ):
            eng.project_version_id = version_id
            logger.info(
                "source_engine_tagged",
                extra={"org_id": org_id, "slug": document.slug, "version": version_id[:8]},
            )
            return eng
        # Discard and rebuild on a version mismatch.
        if eng is not None:
            eng.running = False
        new_eng = SimulationEngine(
            project_id=document.slug,
            document=document,
            project_version_id=version_id,
        )
        self._engines[org_id] = new_eng
        self._rec_services[org_id] = RecommendationService(new_eng)
        # Latest analytics for the old version is stale; clear it so
        # the next analytics tick fills it in fresh for the new doc.
        self._latest_analytics.pop(org_id, None)
        logger.info(
            "source_engine_versioned",
            extra={"org_id": org_id, "slug": document.slug, "version": version_id[:8]},
        )
        return new_eng

    def for_org_live(
        self,
        org_id: str,
        *,
        document: ProjectDocument,
        version_id: str | None,
    ) -> LiveSource:
        """Return (or build) the org's LiveSource for `document`. Replaces a
        SimulationEngine or a stale LiveSource. Caller refreshes it from the
        ledger via `LiveSource.apply_events`."""
        existing = self._engines.get(org_id)
        if (
            isinstance(existing, LiveSource)
            and existing.project_id == document.slug
            and existing.project_version_id == version_id
        ):
            return existing
        if isinstance(existing, SimulationEngine):
            existing.running = False
        src = LiveSource(document, project_version_id=version_id)
        self._engines[org_id] = src
        self._rec_services[org_id] = RecommendationService(src)
        self._latest_analytics.pop(org_id, None)
        logger.info(
            "live_source_created",
            extra={"org_id": org_id, "slug": document.slug},
        )
        return src

    def set(self, org_id: str, source) -> None:
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
            # LiveSource (and any non-simulation source) is never ticked —
            # its state changes via `apply_events`, not a clock.
            if isinstance(engine, SimulationEngine) and engine.running and not engine.paused:
                try:
                    engine.tick()
                except Exception:
                    logger.exception(
                        "engine_tick_failed",
                        extra={"project_id": engine.project_id},
                    )
        await asyncio.sleep(tick_interval)
