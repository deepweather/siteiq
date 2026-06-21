"""Org membership + invite routes.

Mounted under `/api/orgs`. All routes require an authenticated session;
mutating routes additionally require admin or owner role.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, EmailStr
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import (
    get_current_membership,
    get_current_org,
    get_current_session,
    get_current_user,
    get_email_sender,
    require_role,
)
from auth.email_sender import EmailSender
from auth.errors import ApiError
from db.models import AuthSession, Org, OrgMembership, Role, User
from db.session import get_db
from orgs import service as svc


router = APIRouter(prefix="/api/orgs", tags=["orgs"])


class InviteRequest(BaseModel):
    email: EmailStr
    role: str  # admin | member | viewer


class ChangeRoleRequest(BaseModel):
    role: str


class AcceptInviteRequest(BaseModel):
    token: str


class SwitchOrgRequest(BaseModel):
    org_id: str


def _parse_role(value: str) -> Role:
    try:
        return Role(value)
    except ValueError:
        raise ApiError(400, "invalid_role", f"Unknown role '{value}'.", field="role")


@router.get("")
async def list_my_orgs(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    from sqlalchemy import select
    result = await db.execute(
        select(OrgMembership, Org)
        .join(Org, Org.id == OrgMembership.org_id)
        .where(OrgMembership.user_id == user.id)
        .order_by(OrgMembership.created_at.desc())
    )
    return [
        {
            "id": org.id,
            "name": org.name,
            "slug": org.slug,
            "role": m.role,
            "plan": org.plan,
        }
        for (m, org) in result.all()
    ]


@router.post("/switch")
async def switch_org(
    body: SwitchOrgRequest,
    db: AsyncSession = Depends(get_db),
    session: AuthSession = Depends(get_current_session),
    user: User = Depends(get_current_user),
):
    org = await svc.switch_active_org(db, session=session, target_org_id=body.org_id, user=user)
    return {"id": org.id, "name": org.name, "slug": org.slug}


@router.get("/current/members")
async def members(
    db: AsyncSession = Depends(get_db),
    org: Org = Depends(get_current_org),
    _: OrgMembership = Depends(require_role(Role.MEMBER)),
):
    return await svc.list_members(db, org_id=org.id)


@router.get("/current/invites")
async def invites(
    db: AsyncSession = Depends(get_db),
    org: Org = Depends(get_current_org),
    _: OrgMembership = Depends(require_role(Role.ADMIN)),
):
    return await svc.list_pending_invites(db, org_id=org.id)


@router.post("/current/invites")
async def create_invite(
    body: InviteRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    org: Org = Depends(get_current_org),
    user: User = Depends(get_current_user),
    sender: EmailSender = Depends(get_email_sender),
    _: OrgMembership = Depends(require_role(Role.ADMIN)),
):
    settings = request.app.state.settings
    return await svc.invite_member(
        db,
        org=org,
        actor=user,
        email=body.email,
        role=_parse_role(body.role),
        sender=sender,
        frontend_origin=settings.frontend_origin,
    )


@router.post("/accept-invite")
async def accept_invite(
    body: AcceptInviteRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    org = await svc.accept_invite(db, token=body.token, user=user)
    return {"id": org.id, "name": org.name, "slug": org.slug}


@router.patch("/current/members/{user_id}")
async def change_role(
    user_id: str,
    body: ChangeRoleRequest,
    db: AsyncSession = Depends(get_db),
    org: Org = Depends(get_current_org),
    actor: OrgMembership = Depends(require_role(Role.ADMIN)),
):
    await svc.change_role(
        db, org=org, actor=actor, target_user_id=user_id, new_role=_parse_role(body.role)
    )
    return {"status": "ok"}


@router.delete("/current/members/{user_id}")
async def remove_member(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    org: Org = Depends(get_current_org),
    actor: OrgMembership = Depends(require_role(Role.ADMIN)),
):
    await svc.remove_member(db, org=org, actor=actor, target_user_id=user_id)
    return {"status": "ok"}


@router.post("/current/leave")
async def leave(
    db: AsyncSession = Depends(get_db),
    org: Org = Depends(get_current_org),
    user: User = Depends(get_current_user),
):
    await svc.leave_org(db, org=org, user=user)
    return {"status": "ok"}


@router.get("/current/audit")
async def audit(
    db: AsyncSession = Depends(get_db),
    org: Org = Depends(get_current_org),
    _: OrgMembership = Depends(require_role(Role.OWNER)),
):
    return await svc.list_audit_events(db, org_id=org.id)
