"""FastAPI dependency providers.

These pull objects off `request.app.state` so route handlers get them
via `Depends(...)` and tests can override them with `app.dependency_overrides`.
No module-level globals here.
"""
from __future__ import annotations

from typing import Optional

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from auth.email_sender import EmailSender
from auth.errors import ApiError
from auth.sessions import (
    cookie_name,
    get_session as load_session,
    touch_session,
)
from db.models import AuthSession, Device, Org, OrgMembership, Role, User
from db.session import get_db
from services.device_service import authenticate_device, touch_device
from services.recommendation_service import RecommendationService
from state.source import SiteStateSource
from vision.detector import VideoDetector


def _get_registry(request: Request):
    reg = getattr(request.app.state, "registry", None)
    if reg is None:
        raise HTTPException(status_code=503, detail="State source not ready")
    return reg


def get_detector(request: Request) -> VideoDetector:
    det = getattr(request.app.state, "detector", None)
    if det is None:
        raise HTTPException(status_code=503, detail="Detector not ready")
    return det


# `get_source` etc. are now per-org. Each is a Depends that resolves the
# active org first via `_org_for_source` (a private alias of
# `get_current_org` to avoid the import cycle below since `Org` is a
# DB model defined later in this file's import chain).


def get_settings(request: Request):
    cfg = getattr(request.app.state, "settings", None)
    if cfg is None:
        raise HTTPException(status_code=503, detail="Settings not ready")
    return cfg


def get_email_sender(request: Request) -> EmailSender:
    sender = getattr(request.app.state, "email_sender", None)
    if sender is None:
        raise HTTPException(status_code=503, detail="Email sender not ready")
    return sender


def get_capture_parser(request: Request):
    parser = getattr(request.app.state, "capture_parser", None)
    if parser is None:
        raise HTTPException(status_code=503, detail="Capture parser not ready")
    return parser


def get_query_responder(request: Request):
    responder = getattr(request.app.state, "query_responder", None)
    if responder is None:
        raise HTTPException(status_code=503, detail="Query responder not ready")
    return responder


def get_rate_card(request: Request):
    """Active cost rate card. Falls back to the config default when the
    lifespan hasn't attached one (e.g. some unit-test app variants)."""
    rc = getattr(request.app.state, "rate_card", None)
    if rc is None:
        from models.cost import default_rate_card

        return default_rate_card()
    return rc


# ---------------------------------------------------------------------------
# Session + user dependencies
# ---------------------------------------------------------------------------


async def get_optional_session(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> Optional[AuthSession]:
    """Returns the live session row or None. Touches last_seen + sliding
    expiry whenever a valid session is found."""
    settings = request.app.state.settings
    token = request.cookies.get(cookie_name(settings))
    if not token:
        return None
    session = await load_session(db, token)
    if session is None:
        return None
    await touch_session(db, session, idle_days=settings.session_idle_days)
    return session


async def get_current_session(
    session: Optional[AuthSession] = Depends(get_optional_session),
) -> AuthSession:
    if session is None:
        raise ApiError(401, "not_authenticated", "Sign in to continue.")
    return session


async def get_current_user(
    db: AsyncSession = Depends(get_db),
    session: AuthSession = Depends(get_current_session),
) -> User:
    user = await db.get(User, session.user_id)
    if user is None:
        raise ApiError(401, "not_authenticated", "Sign in to continue.")
    return user


async def get_current_org(
    db: AsyncSession = Depends(get_db),
    session: AuthSession = Depends(get_current_session),
) -> Org:
    """Active org for the session. If `current_org_id` is missing, picks
    the user's most-recent membership and persists it as the active org."""
    if session.current_org_id is not None:
        org = await db.get(Org, session.current_org_id)
        if org is not None:
            return org

    result = await db.execute(
        select(Org)
        .join(OrgMembership, OrgMembership.org_id == Org.id)
        .where(OrgMembership.user_id == session.user_id)
        .order_by(OrgMembership.created_at.desc())
        .limit(1)
    )
    org = result.scalar_one_or_none()
    if org is None:
        raise ApiError(403, "no_org_membership", "Your account has no workspace yet.")
    session.current_org_id = org.id
    return org


async def get_current_membership(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    org: Org = Depends(get_current_org),
) -> OrgMembership:
    result = await db.execute(
        select(OrgMembership).where(
            OrgMembership.user_id == user.id, OrgMembership.org_id == org.id
        )
    )
    m = result.scalar_one_or_none()
    if m is None:
        raise ApiError(403, "not_a_member", "You don't have access to this workspace.")
    return m


# ---------------------------------------------------------------------------
# Device (bearer-token) authentication — for `/api/ingest/*`
# ---------------------------------------------------------------------------


async def get_current_device(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> Device:
    """Resolve the calling device from `Authorization: Bearer <token>`.

    Devices are NOT browser sessions: bearer auth (no cookie), so these
    routes are CSRF-exempt by construction. The returned device carries its
    fixed `(org_id, project_id)` scope — ingestion ignores any client-
    supplied org/project."""
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise ApiError(401, "device_not_authenticated", "Device token required.")
    device = await authenticate_device(db, token.strip())
    if device is None:
        raise ApiError(401, "device_not_authenticated", "Invalid or revoked device token.")
    await touch_device(db, device)
    return device


def require_role(min_role: Role):
    """Returns a Depends-able function that raises 403 if the current
    membership is below `min_role`."""

    async def _dep(membership: OrgMembership = Depends(get_current_membership)) -> OrgMembership:
        if Role.rank(membership.role) < Role.rank(min_role):
            raise ApiError(
                403,
                "insufficient_role",
                f"This action requires {min_role.value} or higher.",
            )
        return membership

    return _dep


# ---------------------------------------------------------------------------
# Per-org simulation source (resolved through the registry)
# ---------------------------------------------------------------------------


async def get_source(
    request: Request,
    org: Org = Depends(get_current_org),
    db: AsyncSession = Depends(get_db),
) -> SiteStateSource:
    """Return the org's engine.

    Resolution order:
      1. If `org.active_project_version_id` is set, load the corresponding
         immutable `ProjectDocument` from the DB and ensure the engine
         is pinned to it (re-keying the registry if the version drifted).
      2. Otherwise fall back to the legacy slug-based seed path
         (`org.active_project_id`).

    This is the only place the editor / activate-version flow and the
    legacy seed flow meet.
    """
    registry = _get_registry(request)

    # Live mode: build/refresh a LiveSource folded from the device-fed ledger
    # over the project's static layout (closes debt #33). Falls back to the
    # simulation path if no document can be resolved.
    if getattr(org, "live_mode", False):
        live = await _build_live_source(request, org, db, registry)
        if live is not None:
            return live

    version_id = org.active_project_version_id
    if version_id is not None:
        from db.project_repository import ProjectRepository

        repo = ProjectRepository(db)
        version_row = await repo.get_version(version_id)
        if version_row is not None:
            from models.project_document import ProjectDocument

            doc = ProjectDocument.model_validate(version_row.document)
            return registry.for_org_at_version(
                org.id, document=doc, version_id=version_id
            )
        # Stale pointer (e.g. version was deleted): fall through to seed.

    return registry.for_org(org.id, project_id=org.active_project_id)


async def _build_live_source(request, org, db, registry):
    """Resolve the active ProjectDocument (pinned version or seed slug),
    build/return the org's LiveSource, and fold confirmed ledger events over
    it. Returns None if no document can be resolved (caller uses sim)."""
    from models.project_document import ProjectDocument
    from seeds.loader import load_seed_document
    from services.event_ledger import EventLedger, EventStatusValue

    doc = None
    version_id = org.active_project_version_id
    if version_id is not None:
        from db.project_repository import ProjectRepository

        repo = ProjectRepository(db)
        version_row = await repo.get_version(version_id)
        if version_row is not None:
            doc = ProjectDocument.model_validate(version_row.document)
    if doc is None:
        slug = org.active_project_id or request.app.state.settings.default_project_id
        doc = load_seed_document(slug)
        version_id = None
    if doc is None:
        return None

    live = registry.for_org_live(org.id, document=doc, version_id=version_id)
    rows = await EventLedger(db).query(
        org.id, live.project_id,
        statuses=[EventStatusValue.CONFIRMED], order="asc", limit=5000,
    )
    live.apply_events(rows)
    return live


async def get_rec_service(
    request: Request,
    org: Org = Depends(get_current_org),
    source: SiteStateSource = Depends(get_source),
) -> RecommendationService:
    """Resolve the rec service for the org's *currently active* engine.

    Critical: `Depends(get_source)` runs first so the registry has had
    a chance to rebuild the engine on a version change. Otherwise the
    rec service could end up pointing at the previous engine for an
    instant after a version swap.
    """
    return _get_registry(request).rec_service_for(org.id)


def get_analytics(
    request: Request,
    org: Org = Depends(get_current_org),
):
    """Latest WasteSummary for the active org (or None until the
    analytics loop has computed at least once)."""
    return _get_registry(request).latest_analytics_for(org.id)
