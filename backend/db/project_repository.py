"""Async repository for projects + their immutable content-addressed
version history.

The repository is the only place that knows how `ProjectDocument`
instances get to / from the database. Callers (the API router, the
seed importer, the registry) work in terms of `ProjectDocument` and
opaque version-id strings.

Concurrency: `save_version` enforces optimistic concurrency control via
the `parent_version_id` argument. If `parent_version_id` no longer
matches the project's current pointer, the call raises
`OptimisticLockError` and the caller surfaces a 409 to the editor.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import (
    Project,
    ProjectStatus,
    ProjectVersion,
    ProjectVisibility,
)
from models.project_document import ProjectDocument


class OptimisticLockError(Exception):
    """Raised when a save expects parent_version_id X but the project's
    current pointer no longer matches."""


@dataclass(frozen=True)
class ProjectSummary:
    """The lightweight shape returned by `list_projects` for the editor's
    project picker."""

    id: str
    org_id: Optional[str]
    slug: str
    name: str
    description: str
    type: str
    discipline: str
    visibility: str
    status: str
    current_version_id: Optional[str]
    created_at: datetime
    updated_at: datetime


def _now() -> datetime:
    return datetime.now(timezone.utc)


class ProjectRepository:
    """SQLAlchemy-backed repository. Stateless — pass a session in."""

    def __init__(self, session: AsyncSession) -> None:
        self.db = session

    # ── Listing / fetching ─────────────────────────────────────────

    async def list_for_org(self, org_id: str) -> list[ProjectSummary]:
        """Returns every project the org can see: its own private
        projects + every public template."""
        result = await self.db.execute(
            select(Project)
            .where(
                (Project.org_id == org_id)
                | (Project.visibility == ProjectVisibility.PUBLIC_TEMPLATE.value)
            )
            .order_by(Project.created_at.asc())
        )
        return [self._summarise(p) for p in result.scalars().all()]

    async def get_project(self, project_id: str) -> Project | None:
        return await self.db.get(Project, project_id)

    async def get_project_by_slug(
        self, *, org_id: str | None, slug: str
    ) -> Project | None:
        """Lookup precedence: org-owned project with this slug, then
        public-template fallback. Used by the boot seed importer."""
        if org_id is not None:
            r = await self.db.execute(
                select(Project).where(
                    Project.org_id == org_id, Project.slug == slug
                )
            )
            p = r.scalar_one_or_none()
            if p is not None:
                return p
        r = await self.db.execute(
            select(Project).where(
                Project.org_id.is_(None),
                Project.slug == slug,
                Project.visibility == ProjectVisibility.PUBLIC_TEMPLATE.value,
            )
        )
        return r.scalar_one_or_none()

    async def get_version(self, version_id: str) -> ProjectVersion | None:
        return await self.db.get(ProjectVersion, version_id)

    async def load_document(
        self, *, project_id: str, version_id: str | None = None
    ) -> ProjectDocument | None:
        """Returns the document for `version_id`, or the project's
        current version when `version_id` is None."""
        target_version = version_id
        if target_version is None:
            project = await self.get_project(project_id)
            if project is None or project.current_version_id is None:
                return None
            target_version = project.current_version_id
        version = await self.get_version(target_version)
        if version is None:
            return None
        return ProjectDocument.model_validate(version.document)

    # ── Mutations ─────────────────────────────────────────────────

    async def create_project(
        self,
        *,
        org_id: str | None,
        document: ProjectDocument,
        visibility: ProjectVisibility = ProjectVisibility.PRIVATE,
        status: ProjectStatus = ProjectStatus.DRAFT,
        created_by_user_id: str | None,
        commit_message: str = "Initial version",
    ) -> Project:
        """Creates the project + its first version in one go.

        The first version's `parent_version_id` is NULL. This is the
        only path that creates a project — every subsequent edit calls
        `save_version`."""
        now = _now()
        project = Project(
            id=str(uuid.uuid4()),
            org_id=org_id,
            slug=document.slug,
            name=document.name,
            description=document.description,
            type=document.type,
            discipline=document.discipline.value if hasattr(document.discipline, "value") else document.discipline,
            visibility=visibility.value,
            status=status.value,
            current_version_id=None,
            created_by_user_id=created_by_user_id,
            created_at=now,
            updated_at=now,
        )
        self.db.add(project)
        await self.db.flush()
        version_id = await self._insert_version(
            project=project,
            document=document,
            parent_version_id=None,
            message=commit_message,
            created_by_user_id=created_by_user_id,
        )
        project.current_version_id = version_id
        await self.db.flush()
        return project

    async def save_version(
        self,
        *,
        project_id: str,
        document: ProjectDocument,
        parent_version_id: str | None,
        message: str = "",
        created_by_user_id: str | None,
    ) -> str:
        """Persist a new version and atomically swap the project's
        `current_version_id` pointer. Raises `OptimisticLockError` if
        `parent_version_id` no longer matches the live pointer."""
        project = await self.get_project(project_id)
        if project is None:
            raise LookupError(f"Project {project_id} not found.")
        if project.current_version_id != parent_version_id:
            raise OptimisticLockError(
                f"Expected current version {parent_version_id!r}, "
                f"got {project.current_version_id!r}"
            )
        # Sync the project's outer metadata to whatever the new doc says.
        project.slug = document.slug
        project.name = document.name
        project.description = document.description
        project.type = document.type
        project.discipline = (
            document.discipline.value
            if hasattr(document.discipline, "value")
            else document.discipline
        )
        project.updated_at = _now()

        new_version_id = await self._insert_version(
            project=project,
            document=document,
            parent_version_id=parent_version_id,
            message=message,
            created_by_user_id=created_by_user_id,
        )
        project.current_version_id = new_version_id
        await self.db.flush()
        return new_version_id

    async def delete_project(self, project_id: str) -> None:
        project = await self.get_project(project_id)
        if project is None:
            return
        await self.db.delete(project)
        await self.db.flush()

    # ── Internals ─────────────────────────────────────────────────

    async def _insert_version(
        self,
        *,
        project: Project,
        document: ProjectDocument,
        parent_version_id: str | None,
        message: str,
        created_by_user_id: str | None,
    ) -> str:
        """Compute the content hash, dedupe against an existing version
        if any, otherwise insert a new row."""
        version_id = document.content_hash()
        existing = await self.get_version(version_id)
        if existing is None:
            self.db.add(ProjectVersion(
                id=version_id,
                project_id=project.id,
                parent_version_id=parent_version_id,
                document=document.model_dump(mode="json"),
                message=message,
                created_by_user_id=created_by_user_id,
                created_at=_now(),
            ))
            await self.db.flush()
        return version_id

    def _summarise(self, p: Project) -> ProjectSummary:
        return ProjectSummary(
            id=p.id,
            org_id=p.org_id,
            slug=p.slug,
            name=p.name,
            description=p.description,
            type=p.type,
            discipline=p.discipline,
            visibility=p.visibility,
            status=p.status,
            current_version_id=p.current_version_id,
            created_at=p.created_at,
            updated_at=p.updated_at,
        )
