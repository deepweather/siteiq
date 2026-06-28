"""Org membership + invite routes.

Mounted under `/api/orgs`. All routes require an authenticated session;
mutating routes additionally require admin or owner role.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, EmailStr
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import (
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


class DeleteOrgRequest(BaseModel):
    confirm_name: str
    current_password: str


@router.delete("/current")
async def delete_current_org(
    body: DeleteOrgRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    org: Org = Depends(get_current_org),
    user: User = Depends(get_current_user),
    _: OrgMembership = Depends(require_role(Role.OWNER)),
):
    """Owner-only workspace deletion. Two confirmations:
      1. The user re-supplies their password (live-session hijack guard).
      2. The user types the workspace's exact name (typo guard).
    """
    from auth.passwords import verify_password
    from auth.errors import ApiError as _ApiError  # already imported above

    if body.confirm_name.strip() != org.name:
        raise _ApiError(
            400,
            "name_mismatch",
            "Type the exact workspace name to confirm.",
            field="confirm_name",
        )
    if not verify_password(body.current_password, user.password_hash):
        raise _ApiError(
            400,
            "invalid_password",
            "Password is incorrect.",
            field="current_password",
        )
    org_id = org.id
    await svc.delete_org(db, org=org, actor=user)
    registry = getattr(request.app.state, "registry", None)
    if registry is not None:
        registry.discard(org_id)
    return {"status": "deleted", "org_id": org_id}


@router.get("/current/audit")
async def audit(
    db: AsyncSession = Depends(get_db),
    org: Org = Depends(get_current_org),
    _: OrgMembership = Depends(require_role(Role.OWNER)),
):
    return await svc.list_audit_events(db, org_id=org.id)


@router.get("/current/audit.csv")
async def audit_csv(
    since: str | None = None,
    until: str | None = None,
    db: AsyncSession = Depends(get_db),
    org: Org = Depends(get_current_org),
    _: OrgMembership = Depends(require_role(Role.OWNER)),
):
    """Stream the audit log as RFC 4180 CSV. Owner-only.

    Query params: `since` and `until` are ISO-8601 timestamps. We cap
    the export at 10_000 rows; for anything bigger you'd want a real
    background job + signed-URL flow.
    """
    from datetime import datetime
    from fastapi.responses import StreamingResponse
    import csv
    import io
    import json

    def _parse(ts: str | None):
        if ts is None:
            return None
        try:
            return datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except ValueError:
            raise ApiError(
                400,
                "invalid_timestamp",
                f"'{ts}' is not a valid ISO-8601 timestamp.",
                field="since" if since == ts else "until",
            )

    rows = await svc.list_audit_events(
        db,
        org_id=org.id,
        limit=10_000,
        since=_parse(since),
        until=_parse(until),
    )

    def _stream():
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["created_at", "kind", "actor_user_id", "payload_json"])
        yield buf.getvalue()
        buf.seek(0)
        buf.truncate()
        for r in rows:
            w.writerow(
                [
                    r["created_at"],
                    r["kind"],
                    r["actor_user_id"] or "",
                    json.dumps(r["payload"], separators=(",", ":")),
                ]
            )
            yield buf.getvalue()
            buf.seek(0)
            buf.truncate()

    filename = f"siteiq-audit-{org.slug}.csv"
    return StreamingResponse(
        _stream(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
