"""Project-asset routes: upload + serve + delete level background images.

Lives in its own router because it talks `multipart/form-data` + raw
bytes — different shape from the JSON-only project CRUD in
`api/projects.py`. The asset table is content-addressed via the SHA-256
hash in `project_assets.content_hash`, so the GET route can cache
aggressively (1-year `immutable`).

Authorisation: admin+ on every route (matches the project-write
contract). The serve route is admin+ too — the assets are part of a
private project, not public templates.

Audit events:
- `project.background.uploaded` on POST
- `project.background.deleted` on DELETE
"""
from __future__ import annotations

import hashlib
import uuid
from typing import Any

from fastapi import APIRouter, Depends, File, Header, Response, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import get_current_org, get_current_user, require_role
from auth.errors import ApiError
from db.models import AuditEvent, Org, ProjectAsset, Role, User
from db.project_repository import OptimisticLockError, ProjectRepository
from db.session import get_db


# Limits live in the router because they're product decisions, not
# storage facts. 2 MB is enough for a high-DPI floor plan PNG; bigger
# than that and we'd want a tile pipeline anyway.
MAX_UPLOAD_BYTES = 2 * 1024 * 1024
ALLOWED_CONTENT_TYPES = {"image/png", "image/jpeg", "image/jpg", "image/webp"}
LEVEL_BACKGROUND_KIND = "level_background"

router = APIRouter(prefix="/api/projects", tags=["project-assets"])


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


def _own_project_or_403(project, org: Org) -> None:
    if project is None:
        raise ApiError(404, "project_not_found", "Project not found.")
    if project.org_id != org.id:
        raise ApiError(403, "forbidden", "You don't own this project.")


def _patch_level_background_url(doc_json: dict[str, Any], level_id: str, url: str | None) -> dict[str, Any]:
    """Return a shallow-copied document JSON with `background_image_url`
    set on the matching level. `url=None` strips it back to None.

    Doing the surgery on the dict (rather than re-validating through
    Pydantic) keeps the route hot-path tiny and survives schema changes
    that add fields to Level.
    """
    levels = doc_json.get("levels") or []
    updated_levels = []
    found = False
    for lv in levels:
        if lv.get("id") == level_id:
            updated_levels.append({**lv, "background_image_url": url})
            found = True
        else:
            updated_levels.append(lv)
    if not found:
        raise ApiError(404, "level_not_found", f"Level {level_id!r} not found in project.")
    return {**doc_json, "levels": updated_levels}


@router.post("/{project_id}/levels/{level_id}/background")
async def upload_level_background(
    project_id: str,
    level_id: str,
    file: UploadFile = File(...),
    org: Org = Depends(get_current_org),
    user: User = Depends(get_current_user),
    _ = Depends(require_role(Role.ADMIN)),
    db: AsyncSession = Depends(get_db),
    if_match: str | None = Header(default=None, alias="If-Match"),
):
    repo = ProjectRepository(db)
    project = await repo.get_project(project_id)
    _own_project_or_403(project, org)

    content_type = (file.content_type or "").lower()
    if content_type not in ALLOWED_CONTENT_TYPES:
        raise ApiError(
            400, "invalid_content_type",
            "Background must be PNG, JPEG, or WebP.",
            field="file",
        )

    # Read the whole body upfront. UploadFile is a SpooledTemporaryFile
    # under the hood, so this is a memory-bound copy that hard-caps at
    # MAX_UPLOAD_BYTES + 1 (we stop early if the limit is exceeded).
    chunk = await file.read(MAX_UPLOAD_BYTES + 1)
    if len(chunk) > MAX_UPLOAD_BYTES:
        raise ApiError(
            413, "file_too_large",
            f"Background image must be ≤ {MAX_UPLOAD_BYTES // 1024} KiB.",
            field="file",
        )
    if not chunk:
        raise ApiError(400, "empty_file", "Empty file body.", field="file")

    content_hash = hashlib.sha256(chunk).hexdigest()
    asset_id = str(uuid.uuid4())
    db.add(ProjectAsset(
        id=asset_id,
        project_id=project.id,
        kind=LEVEL_BACKGROUND_KIND,
        content_type=content_type,
        data=chunk,
        content_hash=content_hash,
    ))
    await db.flush()

    # Patch the project's NEXT version with the new url. OCC via If-Match
    # mirrors the project PUT route — if the caller's If-Match is stale,
    # we 409 and the editor reloads.
    doc = await repo.load_document(project_id=project.id)
    if doc is None:
        raise ApiError(500, "missing_version", "Project has no version on file.")
    new_doc_json = _patch_level_background_url(
        doc.model_dump(mode="json"),
        level_id,
        f"/api/projects/{project.id}/assets/{asset_id}",
    )
    from models.project_document import ProjectDocument
    new_doc = ProjectDocument.model_validate(new_doc_json)

    parent = if_match or project.current_version_id
    try:
        new_version_id = await repo.save_version(
            project_id=project.id,
            document=new_doc,
            parent_version_id=parent,
            message=f"Set background for level {level_id}",
            created_by_user_id=user.id,
        )
    except OptimisticLockError:
        raise ApiError(
            409, "version_conflict",
            "Project was edited by someone else; reload and try again.",
        )

    await _audit(
        db, kind="project.background.uploaded",
        org_id=org.id, actor_user_id=user.id,
        payload={
            "project_id": project.id,
            "level_id": level_id,
            "asset_id": asset_id,
            "content_hash": content_hash,
            "to_version": new_version_id,
        },
    )
    await db.commit()
    return {
        "url": f"/api/projects/{project.id}/assets/{asset_id}",
        "asset_id": asset_id,
        "content_hash": content_hash,
        "current_version_id": new_version_id,
    }


@router.get("/{project_id}/assets/{asset_id}")
async def serve_project_asset(
    project_id: str,
    asset_id: str,
    org: Org = Depends(get_current_org),
    _ = Depends(require_role(Role.ADMIN)),
    db: AsyncSession = Depends(get_db),
):
    repo = ProjectRepository(db)
    project = await repo.get_project(project_id)
    _own_project_or_403(project, org)
    row = await db.get(ProjectAsset, asset_id)
    if row is None or row.project_id != project.id:
        raise ApiError(404, "asset_not_found", "Asset not found.")
    # Content-addressed via the hash on the row — once a URL points at
    # an asset_id, the body never changes. Long, immutable cache lets
    # the browser skip re-fetching across page navigations.
    return Response(
        content=row.data,
        media_type=row.content_type,
        headers={
            "Cache-Control": "public, max-age=31536000, immutable",
            "ETag": f'"{row.content_hash}"',
        },
    )


@router.delete("/{project_id}/levels/{level_id}/background")
async def delete_level_background(
    project_id: str,
    level_id: str,
    org: Org = Depends(get_current_org),
    user: User = Depends(get_current_user),
    _ = Depends(require_role(Role.ADMIN)),
    db: AsyncSession = Depends(get_db),
    if_match: str | None = Header(default=None, alias="If-Match"),
):
    repo = ProjectRepository(db)
    project = await repo.get_project(project_id)
    _own_project_or_403(project, org)
    doc = await repo.load_document(project_id=project.id)
    if doc is None:
        raise ApiError(500, "missing_version", "Project has no version on file.")
    doc_json = doc.model_dump(mode="json")
    level = next((lv for lv in doc_json.get("levels", []) if lv.get("id") == level_id), None)
    if level is None:
        raise ApiError(404, "level_not_found", f"Level {level_id!r} not found in project.")
    current_url: str | None = level.get("background_image_url")

    # Strip the URL from the level + drop any matching asset row.
    new_doc_json = _patch_level_background_url(doc_json, level_id, None)
    from models.project_document import ProjectDocument
    new_doc = ProjectDocument.model_validate(new_doc_json)
    parent = if_match or project.current_version_id
    try:
        await repo.save_version(
            project_id=project.id,
            document=new_doc,
            parent_version_id=parent,
            message=f"Clear background for level {level_id}",
            created_by_user_id=user.id,
        )
    except OptimisticLockError:
        raise ApiError(
            409, "version_conflict",
            "Project was edited by someone else; reload and try again.",
        )

    asset_id: str | None = None
    if current_url is not None and current_url.startswith(f"/api/projects/{project.id}/assets/"):
        asset_id = current_url.rsplit("/", 1)[-1]
        # Only delete rows actually owned by this project — guards against
        # a malformed URL that happens to look like an asset id from a
        # different project.
        row = await db.get(ProjectAsset, asset_id)
        if row is not None and row.project_id == project.id:
            await db.delete(row)
            await db.flush()

    await _audit(
        db, kind="project.background.deleted",
        org_id=org.id, actor_user_id=user.id,
        payload={
            "project_id": project.id,
            "level_id": level_id,
            "asset_id": asset_id,
        },
    )
    await db.commit()
    return {"status": "deleted", "asset_id": asset_id}
