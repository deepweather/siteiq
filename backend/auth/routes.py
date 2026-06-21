"""Auth REST routes.

Mounted under `/auth/*`. The route layer is intentionally thin: every
substantive operation delegates to `auth.service`. Routes own:
- Cookie set/clear
- CSRF token issuance
- Request-scope concerns (IP, UA, response shape)

Errors flow through `ApiError` (typed envelope).
"""
from __future__ import annotations

import logging
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import (
    get_current_session,
    get_current_user,
    get_email_sender,
    get_optional_session,
    get_settings,
)
from auth import service as svc
from auth.csrf import CSRF_COOKIE, generate_csrf_token
from auth.email_sender import EmailSender
from auth.errors import ApiError
from auth.rate_limit import limiter
from auth.sessions import (
    clear_session_cookie,
    create_session,
    revoke_all_for_user,
    revoke_session,
    set_session_cookie,
)
from db.models import AuthSession, OrgMembership, Role, User
from db.session import get_db


router = APIRouter(prefix="/auth", tags=["auth"])
logger = logging.getLogger("siteiq.auth.routes")


def _client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    if request.client is not None:
        return request.client.host or ""
    return ""


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class SignupRequest(BaseModel):
    email: EmailStr
    name: str = Field(min_length=1, max_length=255)
    company: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=1, max_length=255)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class ForgotPasswordRequest(BaseModel):
    email: EmailStr


class MagicLinkRequest(BaseModel):
    email: EmailStr


class LoginWithTokenRequest(BaseModel):
    token: str


class ResetPasswordRequest(BaseModel):
    token: str
    password: str


class VerifyEmailRequest(BaseModel):
    token: str


class ChangePasswordRequest(BaseModel):
    current: str
    password: str


class DeleteAccountRequest(BaseModel):
    current_password: str


class UserOut(BaseModel):
    id: str
    email: str
    name: str
    email_verified: bool


class OrgOut(BaseModel):
    id: str
    name: str
    slug: str
    role: str
    plan: str


class MeResponse(BaseModel):
    user: UserOut
    org: Optional[OrgOut] = None
    memberships: list[OrgOut] = []


def _user_out(user: User) -> UserOut:
    return UserOut(
        id=user.id,
        email=user.email_display,
        name=user.name,
        email_verified=user.email_verified_at is not None,
    )


async def _build_me(db: AsyncSession, user: User, current_org_id: Optional[str]) -> MeResponse:
    result = await db.execute(
        select(OrgMembership).where(OrgMembership.user_id == user.id)
    )
    memberships = result.scalars().all()
    org_ids = [m.org_id for m in memberships]
    org_rows = {}
    if org_ids:
        from db.models import Org
        rows = await db.execute(select(Org).where(Org.id.in_(org_ids)))
        org_rows = {o.id: o for o in rows.scalars().all()}

    org_outs = [
        OrgOut(
            id=m.org_id,
            name=org_rows[m.org_id].name if m.org_id in org_rows else "",
            slug=org_rows[m.org_id].slug if m.org_id in org_rows else "",
            role=m.role,
            plan=org_rows[m.org_id].plan if m.org_id in org_rows else "trial",
        )
        for m in memberships
        if m.org_id in org_rows
    ]
    active = next((o for o in org_outs if o.id == current_org_id), None) or (org_outs[0] if org_outs else None)
    return MeResponse(user=_user_out(user), org=active, memberships=org_outs)


# ---------------------------------------------------------------------------
# CSRF
# ---------------------------------------------------------------------------


@router.get("/csrf")
async def issue_csrf(request: Request, response: Response):
    """Issue a CSRF token via cookie + body. The frontend echoes the body
    value via the `X-CSRF-Token` header on subsequent state-changing
    requests."""
    settings = request.app.state.settings
    token = request.cookies.get(CSRF_COOKIE) or generate_csrf_token()
    response.set_cookie(
        key=CSRF_COOKIE,
        value=token,
        max_age=60 * 60 * 24 * 7,
        httponly=False,
        secure=settings.effective_cookie_secure,
        samesite="lax",
        path="/",
        domain=settings.cookie_domain,
    )
    return {"csrf_token": token}


# ---------------------------------------------------------------------------
# Signup / login / logout
# ---------------------------------------------------------------------------


@router.post("/signup")
@limiter.limit("5/hour")
async def signup(
    request: Request,
    body: SignupRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
    sender: EmailSender = Depends(get_email_sender),
):
    settings = request.app.state.settings
    user, org = await svc.signup_user(
        db,
        email=body.email,
        name=body.name,
        password=body.password,
        company=body.company,
        sender=sender,
        frontend_origin=settings.frontend_origin,
    )
    _, token = await create_session(
        db,
        user_id=user.id,
        org_id=org.id,
        user_agent=request.headers.get("user-agent", ""),
        ip=_client_ip(request),
        lifetime_days=settings.session_lifetime_days,
    )
    set_session_cookie(response, settings, token, settings.session_lifetime_days)
    return await _build_me(db, user, org.id)


@router.post("/login")
@limiter.limit("10/minute")
async def login(
    request: Request,
    body: LoginRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    settings = request.app.state.settings
    user = await svc.authenticate(db, email=body.email, password=body.password)
    org = await svc.primary_org_for(db, user.id)
    _, token = await create_session(
        db,
        user_id=user.id,
        org_id=org.id if org else None,
        user_agent=request.headers.get("user-agent", ""),
        ip=_client_ip(request),
        lifetime_days=settings.session_lifetime_days,
    )
    set_session_cookie(response, settings, token, settings.session_lifetime_days)
    return await _build_me(db, user, org.id if org else None)


@router.post("/logout")
async def logout(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
    session: Optional[AuthSession] = Depends(get_optional_session),
):
    settings = request.app.state.settings
    if session is not None:
        await revoke_session(db, session.id)
    clear_session_cookie(response, settings)
    return {"status": "ok"}


@router.get("/me")
async def me(
    db: AsyncSession = Depends(get_db),
    session: Optional[AuthSession] = Depends(get_optional_session),
):
    if session is None:
        return {"user": None, "org": None, "memberships": []}
    user = await db.get(User, session.user_id)
    if user is None:
        return {"user": None, "org": None, "memberships": []}
    return (await _build_me(db, user, session.current_org_id)).model_dump()


# ---------------------------------------------------------------------------
# Email verification
# ---------------------------------------------------------------------------


@router.post("/verify-email")
async def verify_email(
    body: VerifyEmailRequest,
    db: AsyncSession = Depends(get_db),
):
    user = await svc.verify_email(db, token=body.token)
    return {"status": "verified", "email": user.email_display}


@router.post("/resend-verification")
async def resend_verification(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    sender: EmailSender = Depends(get_email_sender),
):
    settings = request.app.state.settings
    await svc.resend_verification_email(
        db, user=user, sender=sender, frontend_origin=settings.frontend_origin
    )
    return {"status": "sent"}


# ---------------------------------------------------------------------------
# Password reset
# ---------------------------------------------------------------------------


@router.post("/request-magic-link")
@limiter.limit("5/hour")
async def request_magic_link(
    request: Request,
    body: MagicLinkRequest,
    db: AsyncSession = Depends(get_db),
    sender: EmailSender = Depends(get_email_sender),
):
    """Email a one-time sign-in link. Always returns 200 — we don't
    reveal whether the email is registered."""
    settings = request.app.state.settings
    await svc.request_magic_link(
        db, email=body.email, sender=sender, frontend_origin=settings.frontend_origin
    )
    return {"status": "ok"}


@router.post("/login-with-token")
async def login_with_token(
    body: LoginWithTokenRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    """Consume a magic-link token and issue a fresh session cookie."""
    settings = request.app.state.settings
    user = await svc.login_with_magic_link(db, token=body.token)
    org = await svc.primary_org_for(db, user.id)
    _, token = await create_session(
        db,
        user_id=user.id,
        org_id=org.id if org else None,
        user_agent=request.headers.get("user-agent", ""),
        ip=_client_ip(request),
        lifetime_days=settings.session_lifetime_days,
    )
    set_session_cookie(response, settings, token, settings.session_lifetime_days)
    return await _build_me(db, user, org.id if org else None)


@router.post("/forgot-password")
@limiter.limit("5/hour")
async def forgot_password(
    request: Request,
    body: ForgotPasswordRequest,
    db: AsyncSession = Depends(get_db),
    sender: EmailSender = Depends(get_email_sender),
):
    settings = request.app.state.settings
    await svc.request_password_reset(
        db, email=body.email, sender=sender, frontend_origin=settings.frontend_origin
    )
    # Always return ok — we don't reveal account existence.
    return {"status": "ok"}


@router.post("/reset-password")
async def reset_password(
    body: ResetPasswordRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    settings = request.app.state.settings
    user = await svc.reset_password(db, token=body.token, new_password=body.password)
    org = await svc.primary_org_for(db, user.id)
    _, token = await create_session(
        db,
        user_id=user.id,
        org_id=org.id if org else None,
        user_agent=request.headers.get("user-agent", ""),
        ip=_client_ip(request),
        lifetime_days=settings.session_lifetime_days,
    )
    set_session_cookie(response, settings, token, settings.session_lifetime_days)
    return await _build_me(db, user, org.id if org else None)


@router.post("/delete-account")
async def delete_account(
    body: DeleteAccountRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Hard-delete the current user. Requires re-supplying the password
    so a hijacked-but-active session can't quietly destroy the account.
    Clears the session cookie. Cascades any orgs the user was the sole
    owner of."""
    settings = request.app.state.settings
    deleted_orgs = await svc.delete_account(
        db, user=user, current_password=body.current_password
    )
    # Drop any per-org simulation engines that no longer have an owner.
    registry = getattr(request.app.state, "registry", None)
    if registry is not None:
        for org_id in deleted_orgs:
            registry.discard(org_id)
    clear_session_cookie(response, settings)
    return {"status": "deleted", "orgs_deleted": deleted_orgs}


@router.post("/change-password")
async def change_password(
    body: ChangePasswordRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    session: AuthSession = Depends(get_current_session),
):
    await svc.change_password(
        db,
        user=user,
        current=body.current,
        new_password=body.password,
        current_session_id=session.id,
    )
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Sessions list + revoke
# ---------------------------------------------------------------------------


@router.get("/sessions")
async def list_sessions(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    current: AuthSession = Depends(get_current_session),
):
    result = await db.execute(
        select(AuthSession)
        .where(AuthSession.user_id == user.id)
        .where(AuthSession.revoked_at.is_(None))
        .order_by(AuthSession.last_seen_at.desc())
    )
    rows = result.scalars().all()
    return [
        {
            "id": s.id,
            "user_agent": s.user_agent,
            "ip": s.ip,
            "created_at": s.created_at.isoformat(),
            "last_seen_at": s.last_seen_at.isoformat(),
            "expires_at": s.expires_at.isoformat(),
            "current": s.id == current.id,
        }
        for s in rows
    ]


@router.post("/sessions/{session_id}/revoke")
async def revoke_one(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    target = await db.get(AuthSession, session_id)
    if target is None or target.user_id != user.id:
        raise ApiError(404, "session_not_found", "Session not found.")
    await revoke_session(db, session_id)
    return {"status": "ok"}


@router.post("/sessions/revoke-all")
async def revoke_all_other(
    response: Response,
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    current: AuthSession = Depends(get_current_session),
):
    settings = request.app.state.settings
    n = await revoke_all_for_user(db, user.id)
    # Re-issue a fresh session for the current device so the user stays
    # signed in here. n includes the just-revoked current session.
    _, token = await create_session(
        db,
        user_id=user.id,
        org_id=current.current_org_id,
        user_agent=request.headers.get("user-agent", ""),
        ip=_client_ip(request),
        lifetime_days=settings.session_lifetime_days,
    )
    set_session_cookie(response, settings, token, settings.session_lifetime_days)
    return {"status": "ok", "revoked": n}
