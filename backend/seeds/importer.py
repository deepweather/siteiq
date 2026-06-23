"""Import the bundled seeds into the `projects` + `project_versions`
tables on app startup.

The seeds are stored on disk under `seeds/projects/*.json`. On every
boot we ensure each seed is represented as a single public-template row
in the DB. Idempotent: if the project already exists and its
content_hash matches its `current_version_id`, we do nothing. If the
seed file changed, a new version row is created and `current_version_id`
is bumped.
"""
from __future__ import annotations

import logging
from typing import Iterable

from sqlalchemy.ext.asyncio import async_sessionmaker

from db.models import ProjectStatus, ProjectVisibility
from db.project_repository import ProjectRepository
from seeds.loader import load_all_seed_documents


logger = logging.getLogger("siteiq.seeds.importer")


async def import_seed_projects(
    session_factory: async_sessionmaker,
    *,
    slugs: Iterable[str] | None = None,
) -> dict[str, str]:
    """Ensure every bundled seed has a public-template row + a version
    matching its current content_hash. Returns `{slug: version_id}`."""
    docs = load_all_seed_documents()
    if slugs is not None:
        wanted = set(slugs)
        docs = {k: v for k, v in docs.items() if k in wanted}

    out: dict[str, str] = {}
    async with session_factory() as session:
        repo = ProjectRepository(session)
        for slug, doc in docs.items():
            existing = await repo.get_project_by_slug(org_id=None, slug=slug)
            target_hash = doc.content_hash()
            if existing is None:
                project = await repo.create_project(
                    org_id=None,
                    document=doc,
                    visibility=ProjectVisibility.PUBLIC_TEMPLATE,
                    status=ProjectStatus.DRAFT,
                    created_by_user_id=None,
                    commit_message="Imported seed",
                )
                out[slug] = project.current_version_id or target_hash
                logger.info(
                    "seed_project_created",
                    extra={"slug": slug, "version_id": out[slug][:8]},
                )
            elif existing.current_version_id != target_hash:
                new_version = await repo.save_version(
                    project_id=existing.id,
                    document=doc,
                    parent_version_id=existing.current_version_id,
                    message="Updated seed",
                    created_by_user_id=None,
                )
                out[slug] = new_version
                logger.info(
                    "seed_project_updated",
                    extra={
                        "slug": slug,
                        "old": (existing.current_version_id or "")[:8],
                        "new": new_version[:8],
                    },
                )
            else:
                out[slug] = existing.current_version_id
        await session.commit()
    return out
