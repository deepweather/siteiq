"""Backwards-compat shim around the canonical ProjectDocument seeds.

This module used to own the in-Python PROJECT_TEMPLATES dict. The
canonical project format is now `ProjectDocument` (see
`models/project_document.py`), persisted on disk as JSON under
`seeds/projects/` and (Phase 1) in the `project_versions` DB table.

The exports below preserve the old call signatures so the engine,
portfolio estimator, and tests can keep working without churn. Phase 1
re-points the engine to load directly from the `ProjectRepository`,
and this module's surface shrinks to just `get_project_list` for the
listing endpoint.
"""
from __future__ import annotations

from typing import Any

from models.assets import Asset
from models.connection import Connection
from models.site import Site
from seeds.loader import load_all_seed_documents, load_seed_document
from simulation.project_loader import build_engine_state
from simulation.worker_internals import WorkerInternals


def _seed_summary(slug: str, doc) -> dict[str, Any]:
    """Best-effort summary used by the portfolio-estimator fallback and
    tests that historically poked at PROJECT_TEMPLATES['zones'] etc."""
    return {
        "id": f"site-{slug}",
        "name": doc.name,
        "description": doc.description,
        "type": doc.type,
        "width": doc.width,
        "height": doc.height,
        "start_day": doc.start_day,
        "zones": [
            {
                "id": z.id,
                "label": z.label,
                "x": z.x,
                "y": z.y,
                "w": z.width,
                "h": z.height,
                "phase": z.phase,
                "progress": z.phase_progress,
                "workers": [
                    (s.trade, s.count)
                    for s in doc.worker_seeds
                    if s.zone_id == z.id
                ],
            }
            for z in doc.zones
        ],
        "facilities": [{"id": f.id, "subtype": f.subtype, "x": f.x, "y": f.y} for f in doc.facilities],
        "equipment": [
            {"id": e.id, "subtype": e.subtype, "x": e.x, "y": e.y, "state": e.state}
            for e in doc.equipment
        ],
        "materials": [
            {"id": m.id, "subtype": m.subtype, "x": m.x, "y": m.y, "needed_in": m.needed_in}
            for m in doc.materials
        ],
        "schedule": list(doc.schedule),
    }


class _ProjectTemplatesView:
    """Lazy, dict-like view over the seeded documents.

    Only the keys actually exercised by the existing code paths are
    supported: `__getitem__`, `__contains__`, `.keys()`, `.items()`,
    `.values()`. Each lookup goes through `seeds.loader` (cached after
    first call). This will be replaced by a direct repository lookup
    in Phase 1, at which point this view collapses to a passthrough.
    """

    def __getitem__(self, slug: str) -> dict[str, Any]:
        doc = load_seed_document(slug)
        if doc is None:
            raise KeyError(slug)
        return _seed_summary(slug, doc)

    def __contains__(self, slug: object) -> bool:
        return isinstance(slug, str) and load_seed_document(slug) is not None

    def keys(self):  # type: ignore[no-untyped-def]
        return load_all_seed_documents().keys()

    def items(self):  # type: ignore[no-untyped-def]
        for slug, doc in load_all_seed_documents().items():
            yield slug, _seed_summary(slug, doc)

    def values(self):  # type: ignore[no-untyped-def]
        for slug, doc in load_all_seed_documents().items():
            yield _seed_summary(slug, doc)


PROJECT_TEMPLATES = _ProjectTemplatesView()


def get_project_list() -> list[dict[str, Any]]:
    return [
        {
            "id": slug,
            "name": doc.name,
            "description": doc.description,
            "type": doc.type,
        }
        for slug, doc in load_all_seed_documents().items()
    ]


def create_site_from_template(
    project_id: str,
) -> tuple[Site, list[Asset], dict[str, WorkerInternals]]:
    """Legacy signature retained for the engine + portfolio estimator.

    Loads the canonical document from the seed bundle and materialises
    it. The 4-tuple form (with connections) is exposed separately as
    `create_site_from_template_with_connections` so the engine can pick
    up the connection list when it's ready in Phase 2.
    """
    site, assets, internals, _ = create_site_from_template_with_connections(project_id)
    return site, assets, internals


def create_site_from_template_with_connections(
    project_id: str,
) -> tuple[Site, list[Asset], dict[str, WorkerInternals], list[Connection]]:
    doc = load_seed_document(project_id)
    if doc is None:
        raise ValueError(f"Unknown project: {project_id}")
    return build_engine_state(doc)


def create_initial_site() -> tuple[Site, list[Asset], dict[str, WorkerInternals]]:
    """Default: first seed in alphabetical order, preserving the historic
    "westhafen" pick."""
    seeds = load_all_seed_documents()
    if "westhafen" in seeds:
        return create_site_from_template("westhafen")
    return create_site_from_template(next(iter(seeds.keys())))
