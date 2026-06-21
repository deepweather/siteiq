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
from db.models import AuthSession, Org, OrgMembership, Role, User
from db.session import get_db
from services.recommendation_service import RecommendationService
from state.source import SiteStateSource
from vision.detector import VideoDetector


def get_source(request: Request) -> SiteStateSource:
    source = getattr(request.app.state, "source", None)
    if source is None:
        raise HTTPException(status_code=503, detail="State source not ready")
    return source


def get_rec_service(request: Request) -> RecommendationService:
    svc = getattr(request.app.state, "rec_service", None)
    if svc is None:
        raise HTTPException(status_code=503, detail="Recommendation service not ready")
    return svc


def get_detector(request: Request) -> VideoDetector:
    det = getattr(request.app.state, "detector", None)
    if det is None:
        raise HTTPException(status_code=503, detail="Detector not ready")
    return det


def get_analytics(request: Request):
    """Latest WasteSummary or None. The analytics loop writes to app.state.latest_analytics."""
    return getattr(request.app.state, "latest_analytics", None)


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
