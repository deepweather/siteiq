"""Editor-facing project CRUD + version management.

This router is the only HTTP surface for the editor. The simulation
control endpoints (`/api/projects/{slug}/load`, `/api/simulation/*`)
stay on `api/routes.py` so the simulation surface remains independent.

Authorisation
-------------
- Read endpoints: any org member.
- Write endpoints: admin or higher.

Optimistic-concurrency control
------------------------------
Every save (`PUT /api/projects/{id}`) requires an `If-Match` header
carrying the version id the editor last loaded. The repository raises
`OptimisticLockError` if that no longer matches the project's current
pointer, and the router maps it to a 409 with `code=version_conflict`.

Audit events
------------
- `project.created`     on POST /api/projects
- `project.updated`     on PUT /api/projects/{id}
- `project.deleted`     on DELETE /api/projects/{id}
- `project.activated`   on POST /api/projects/{id}/activate
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_current_org, get_current_user, require_role
from auth.errors import ApiError
from db.models import AuditEvent, Org, ProjectStatus, ProjectVisibility, Role, User
from db.project_repository import (
    OptimisticLockError,
    ProjectRepository,
)
from db.session import get_db
from models.project_document import ProjectDocument, validate_document
from analytics.aggregator import compute_waste_summary
from services.recommendation_service import RecommendationService
from simulation.engine import SimulationEngine


router = APIRouter(prefix="/api/projects", tags=["projects"])


# ── Request/response schemas ─────────────────────────────────────────


class ProjectListItem(BaseModel):
    id: str
    org_id: str | None
    slug: str
    name: str
    description: str
    type: str
    discipline: str
    visibility: str
    status: str
    current_version_id: str | None
    is_owner: bool
    # True iff this project's current version is the one the org's
    # simulation is currently pinned to. The project list page needs
    # this to render an "Active" badge — otherwise the user can't tell
    # which Activate button to NOT click.
    is_active: bool = False


class ProjectDetailResponse(BaseModel):
    id: str
    org_id: str | None
    slug: str
    name: str
    description: str
    type: str
    discipline: str
    visibility: str
    status: str
    current_version_id: str | None
    is_owner: bool
    document: ProjectDocument


class CreateProjectRequest(BaseModel):
    document: ProjectDocument
    visibility: str = Field(default=ProjectVisibility.PRIVATE.value)
    message: str = "Initial version"


class UpdateProjectRequest(BaseModel):
    document: ProjectDocument
    message: str = ""


class ActivateRequest(BaseModel):
    version_id: str | None = None  # if None, activates current_version_id


class ValidationResponse(BaseModel):
    issues: list[dict]


# ── Preview Run schemas ──────────────────────────────────────────────


# Default warm-up matches the portfolio estimator's WARMUP_TICKS (240
# ticks ≈ 2 sim-hours at SIM_SECONDS_PER_TICK=30). The cap protects the
# request loop: at the documented ~30 ms / preview-run we stay well under
# a typical request budget; 1200 ticks ≈ 10 sim-hours and ~150 ms which
# is still acceptable for an explicit user action.
PREVIEW_DEFAULT_TICKS = 240
PREVIEW_MAX_TICKS = 1200


class PreviewRequest(BaseModel):
    document: ProjectDocument
    ticks: int | None = None


class PreviewResponse(BaseModel):
    sim_time: float
    sim_day: int
    site: dict
    assets: list[dict]
    waste: dict
    recommendations: list[dict]


# ── Helpers ──────────────────────────────────────────────────────────


async def _audit(
    db: AsyncSession,
    *,
    kind: str,
    org_id: str | None,
    actor_user_id: str | None,
    payload: dict | None = None,
) -> None:
    db.add(AuditEvent(
        id=str(uuid.uuid4()),
        org_id=org_id,
        actor_user_id=actor_user_id,
        kind=kind,
        payload=payload or {},
    ))


def _can_edit(project_org_id: str | None, current_org_id: str) -> bool:
    return project_org_id == current_org_id


def _to_list_item(
    summary,
    *,
    current_org_id: str,
    active_version_id: str | None,
    active_slug: str | None,
) -> ProjectListItem:
    # A project is "active" if its current version is what the org's
    # engine is currently pinned to. We accept either the version-id
    # match (post-editor activate) or the slug match (legacy seed path
    # where active_project_version_id wasn't set yet).
    is_active = False
    if active_version_id is not None and summary.current_version_id == active_version_id:
        is_active = True
    elif active_version_id is None and active_slug is not None and summary.slug == active_slug:
        is_active = True
    return ProjectListItem(
        id=summary.id,
        org_id=summary.org_id,
        slug=summary.slug,
        name=summary.name,
        description=summary.description,
        type=summary.type,
        discipline=summary.discipline,
        visibility=summary.visibility,
        status=summary.status,
        current_version_id=summary.current_version_id,
        is_owner=summary.org_id == current_org_id,
        is_active=is_active,
    )


# ── Read endpoints ───────────────────────────────────────────────────


@router.get("", response_model=list[ProjectListItem])
async def list_projects(
    org: Org = Depends(get_current_org),
    db: AsyncSession = Depends(get_db),
):
    repo = ProjectRepository(db)
    items = await repo.list_for_org(org.id)
    return [
        _to_list_item(
            s,
            current_org_id=org.id,
            active_version_id=org.active_project_version_id,
            active_slug=org.active_project_id,
        )
        for s in items
    ]


@router.get("/{project_id}", response_model=ProjectDetailResponse)
async def get_project(
    project_id: str,
    org: Org = Depends(get_current_org),
    db: AsyncSession = Depends(get_db),
):
    repo = ProjectRepository(db)
    project = await repo.get_project(project_id)
    if project is None:
        raise ApiError(404, "project_not_found", "Project not found.")
    # Visibility check.
    if project.org_id != org.id and project.visibility != ProjectVisibility.PUBLIC_TEMPLATE.value:
        raise ApiError(403, "forbidden", "You don't have access to this project.")
    doc = await repo.load_document(project_id=project.id)
    if doc is None:
        raise ApiError(500, "missing_version", "Project has no version on file.")
    return ProjectDetailResponse(
        id=project.id,
        org_id=project.org_id,
        slug=project.slug,
        name=project.name,
        description=project.description,
        type=project.type,
        discipline=project.discipline,
        visibility=project.visibility,
        status=project.status,
        current_version_id=project.current_version_id,
        is_owner=project.org_id == org.id,
        document=doc,
    )


# ── Write endpoints ──────────────────────────────────────────────────


@router.post("", response_model=ProjectDetailResponse)
async def create_project(
    req: CreateProjectRequest,
    org: Org = Depends(get_current_org),
    user: User = Depends(get_current_user),
    _ = Depends(require_role(Role.ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    # Block publishing public templates from a regular org account; only
    # the seed importer creates those (org_id=None).
    visibility = ProjectVisibility(req.visibility)
    if visibility == ProjectVisibility.PUBLIC_TEMPLATE:
        raise ApiError(
            403, "forbidden_visibility",
            "Only stock seeds may be public templates.",
            field="visibility",
        )

    # Validate the document before persisting.
    errors = [i for i in validate_document(req.document) if i.severity == "error"]
    if errors:
        first = errors[0]
        raise ApiError(
            400, first.code, first.message, field=first.field or first.asset_id,
        )

    repo = ProjectRepository(db)
    project = await repo.create_project(
        org_id=org.id,
        document=req.document,
        visibility=visibility,
        status=ProjectStatus.DRAFT,
        created_by_user_id=user.id,
        commit_message=req.message,
    )
    await _audit(
        db, kind="project.created",
        org_id=org.id, actor_user_id=user.id,
        payload={
            "project_id": project.id,
            "slug": project.slug,
            "version_id": project.current_version_id,
        },
    )
    await db.commit()
    doc = await repo.load_document(project_id=project.id)
    assert doc is not None  # we just inserted the first version
    return ProjectDetailResponse(
        id=project.id,
        org_id=project.org_id,
        slug=project.slug,
        name=project.name,
        description=project.description,
        type=project.type,
        discipline=project.discipline,
        visibility=project.visibility,
        status=project.status,
        current_version_id=project.current_version_id,
        is_owner=True,
        document=doc,
    )


@router.put("/{project_id}", response_model=ProjectDetailResponse)
async def update_project(
    project_id: str,
    req: UpdateProjectRequest,
    org: Org = Depends(get_current_org),
    user: User = Depends(get_current_user),
    _ = Depends(require_role(Role.ADMIN)),
    db: AsyncSession = Depends(get_db),
    if_match: str | None = Header(default=None, alias="If-Match"),
):
    repo = ProjectRepository(db)
    project = await repo.get_project(project_id)
    if project is None:
        raise ApiError(404, "project_not_found", "Project not found.")
    if not _can_edit(project.org_id, org.id):
        raise ApiError(403, "forbidden", "You don't own this project.")

    errors = [i for i in validate_document(req.document) if i.severity == "error"]
    if errors:
        first = errors[0]
        raise ApiError(
            400, first.code, first.message, field=first.field or first.asset_id,
        )

    # OCC: caller must echo back the version they edited.
    parent = if_match
    if parent is None:
        # Defensive default — allow callers without If-Match (e.g. tests
        # that don't care about concurrency) to overwrite the current
        # pointer rather than 409 by default.
        parent = project.current_version_id

    try:
        new_version_id = await repo.save_version(
            project_id=project.id,
            document=req.document,
            parent_version_id=parent,
            message=req.message,
            created_by_user_id=user.id,
        )
    except OptimisticLockError:
        raise ApiError(
            409, "version_conflict",
            "Project was edited by someone else; reload and try again.",
        )

    await _audit(
        db, kind="project.updated",
        org_id=org.id, actor_user_id=user.id,
        payload={
            "project_id": project.id,
            "from_version": parent,
            "to_version": new_version_id,
        },
    )
    await db.commit()
    doc = await repo.load_document(project_id=project.id)
    assert doc is not None
    return ProjectDetailResponse(
        id=project.id,
        org_id=project.org_id,
        slug=project.slug,
        name=project.name,
        description=project.description,
        type=project.type,
        discipline=project.discipline,
        visibility=project.visibility,
        status=project.status,
        current_version_id=project.current_version_id,
        is_owner=True,
        document=doc,
    )


@router.delete("/{project_id}")
async def delete_project(
    project_id: str,
    org: Org = Depends(get_current_org),
    user: User = Depends(get_current_user),
    _ = Depends(require_role(Role.ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    repo = ProjectRepository(db)
    project = await repo.get_project(project_id)
    if project is None:
        raise ApiError(404, "project_not_found", "Project not found.")
    if not _can_edit(project.org_id, org.id):
        raise ApiError(403, "forbidden", "You don't own this project.")
    payload = {"project_id": project.id, "slug": project.slug}
    await repo.delete_project(project_id)
    await _audit(
        db, kind="project.deleted",
        org_id=org.id, actor_user_id=user.id, payload=payload,
    )
    await db.commit()
    return {"status": "deleted"}


@router.post("/{project_id}/activate")
async def activate_project(
    project_id: str,
    req: ActivateRequest,
    org: Org = Depends(get_current_org),
    user: User = Depends(get_current_user),
    _ = Depends(require_role(Role.ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    """Pin the org's simulation to a specific (project_id, version_id).

    The next `get_source` call will detect the version drift and
    rebuild the engine. This is what the editor's "Activate this
    project" button calls.
    """
    repo = ProjectRepository(db)
    project = await repo.get_project(project_id)
    if project is None:
        raise ApiError(404, "project_not_found", "Project not found.")
    # Activation needs read access — public templates count.
    if project.org_id != org.id and project.visibility != ProjectVisibility.PUBLIC_TEMPLATE.value:
        raise ApiError(403, "forbidden", "You don't have access to this project.")

    version_id = req.version_id or project.current_version_id
    if version_id is None:
        raise ApiError(400, "no_version", "Project has no version to activate.")
    if (await repo.get_version(version_id)) is None:
        raise ApiError(404, "version_not_found", "Version not found.")

    org.active_project_id = project.slug
    org.active_project_version_id = version_id
    await _audit(
        db, kind="project.activated",
        org_id=org.id, actor_user_id=user.id,
        payload={"project_id": project.id, "version_id": version_id},
    )
    await db.commit()
    return {
        "status": "activated",
        "project_id": project.id,
        "version_id": version_id,
    }


@router.post("/{project_id}/validate", response_model=ValidationResponse)
async def validate_project(
    project_id: str,
    req: UpdateProjectRequest,
    org: Org = Depends(get_current_org),
    _ = Depends(require_role(Role.ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    """Dry-run validation. The editor calls this from the autosave loop
    to surface live errors without committing a new version."""
    repo = ProjectRepository(db)
    project = await repo.get_project(project_id)
    if project is None:
        raise ApiError(404, "project_not_found", "Project not found.")
    if not _can_edit(project.org_id, org.id):
        raise ApiError(403, "forbidden", "You don't own this project.")
    issues = [i.model_dump() for i in validate_document(req.document)]
    return ValidationResponse(issues=issues)


@router.post("/{project_id}/preview", response_model=PreviewResponse)
async def preview_project(
    project_id: str,
    req: PreviewRequest,
    org: Org = Depends(get_current_org),
    user: User = Depends(get_current_user),
    _ = Depends(require_role(Role.ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    """Run a transient simulation against an in-memory draft document.

    Builds an engine OUTSIDE the org's per-org registry so the live
    simulation isn't disturbed. After `ticks` engine ticks, computes
    waste + recommendations off the snapshot and returns everything
    in one shot. Nothing is persisted.

    Authorisation matches other write paths (admin+); previewing
    someone else's project would also leak its document content via
    the request body, but the body is the caller's own draft, so the
    same "must be able to write here" rule is the right gate.
    """
    repo = ProjectRepository(db)
    project = await repo.get_project(project_id)
    if project is None:
        raise ApiError(404, "project_not_found", "Project not found.")
    if not _can_edit(project.org_id, org.id):
        raise ApiError(403, "forbidden", "You don't own this project.")

    errors = [i for i in validate_document(req.document) if i.severity == "error"]
    if errors:
        first = errors[0]
        raise ApiError(
            400, first.code, first.message, field=first.field or first.asset_id,
        )

    ticks = req.ticks if req.ticks is not None else PREVIEW_DEFAULT_TICKS
    if ticks < 0:
        ticks = 0
    if ticks > PREVIEW_MAX_TICKS:
        raise ApiError(
            400, "ticks_out_of_range",
            f"ticks must be ≤ {PREVIEW_MAX_TICKS}", field="ticks",
        )

    # Transient engine — never registered with the org's SourceRegistry.
    # The engine is GC'd as soon as this function returns.
    engine = SimulationEngine(document=req.document)
    for _ in range(ticks):
        engine.tick()

    waste = compute_waste_summary(engine)
    rec_service = RecommendationService(engine)
    rec_service.mark_dirty()
    recs = rec_service.get()

    snapshot = engine.get_state_snapshot()
    await _audit(
        db, kind="project.preview",
        org_id=org.id, actor_user_id=user.id,
        payload={
            "project_id": project.id,
            "version_hash": req.document.content_hash(),
            "ticks": ticks,
        },
    )
    await db.commit()
    return PreviewResponse(
        sim_time=snapshot["sim_time"],
        sim_day=snapshot["sim_day"],
        site={
            "id": engine.site.id,
            "name": engine.site.name,
            "width": engine.site.width,
            "height": engine.site.height,
            "zones": [z.model_dump() for z in engine.site.zones],
            "levels": [lv.model_dump() for lv in engine.site.levels],
        },
        assets=snapshot["assets"],
        waste=waste.model_dump(),
        recommendations=[r.model_dump() for r in recs],
    )
