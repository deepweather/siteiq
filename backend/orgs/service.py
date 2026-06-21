"""Org membership, invites, and role changes.

Pure functions on AsyncSession. Routes layer is thin.

Authorization rule of thumb (enforced at route layer via require_role):
- View members:        member+
- Invite / change role / remove: admin+
- Transfer ownership / delete org: owner only

Audit events are written for every mutation.
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from auth import email_templates
from auth.email_sender import EmailSender
from auth.errors import ApiError
from auth.timeutil import as_utc, utc_now
from auth.tokens import generate_token, hash_token
from db.models import (
    AuditEvent,
    AuthSession,
    Org,
    OrgInvite,
    OrgMembership,
    Plan,
    Role,
    User,
)


INVITE_TTL_DAYS = 7


_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slugify(name: str) -> str:
    s = _SLUG_RE.sub("-", name.strip().lower()).strip("-")
    return s or "org"


async def _audit(
    db: AsyncSession,
    *,
    kind: str,
    org_id: Optional[str],
    actor_user_id: Optional[str],
    payload: Optional[dict] = None,
) -> None:
    db.add(
        AuditEvent(
            id=str(uuid.uuid4()),
            org_id=org_id,
            actor_user_id=actor_user_id,
            kind=kind,
            payload=payload or {},
        )
    )


async def list_members(db: AsyncSession, *, org_id: str) -> list[dict]:
    result = await db.execute(
        select(OrgMembership, User)
        .join(User, User.id == OrgMembership.user_id)
        .where(OrgMembership.org_id == org_id)
        .order_by(OrgMembership.created_at.asc())
    )
    return [
        {
            "user_id": user.id,
            "email": user.email_display,
            "name": user.name,
            "role": m.role,
            "joined_at": m.created_at.isoformat(),
        }
        for (m, user) in result.all()
    ]


async def list_pending_invites(db: AsyncSession, *, org_id: str) -> list[dict]:
    result = await db.execute(
        select(OrgInvite)
        .where(OrgInvite.org_id == org_id)
        .where(OrgInvite.accepted_at.is_(None))
        .order_by(OrgInvite.created_at.desc())
    )
    rows = result.scalars().all()
    now = utc_now()
    return [
        {
            "id": i.id,
            "email": i.email_lower,
            "role": i.role,
            "expires_at": (as_utc(i.expires_at) or now).isoformat(),
            "expired": (as_utc(i.expires_at) or now) <= now,
        }
        for i in rows
    ]


async def invite_member(
    db: AsyncSession,
    *,
    org: Org,
    actor: User,
    email: str,
    role: Role,
    sender: EmailSender,
    frontend_origin: str,
) -> dict:
    email_lower = email.strip().lower()
    if not email_lower or "@" not in email_lower:
        raise ApiError(400, "invalid_email", "Enter a valid email address.", field="email")
    if role == Role.OWNER:
        raise ApiError(
            400,
            "cannot_invite_as_owner",
            "Owners are appointed via ownership transfer, not invites.",
            field="role",
        )

    # Already a member?
    result = await db.execute(
        select(OrgMembership)
        .join(User, User.id == OrgMembership.user_id)
        .where(User.email_lower == email_lower, OrgMembership.org_id == org.id)
    )
    if result.scalar_one_or_none() is not None:
        raise ApiError(409, "already_member", "That person is already on the team.", field="email")

    # Outstanding invite? Re-issue with a fresh token.
    existing = await db.execute(
        select(OrgInvite)
        .where(OrgInvite.org_id == org.id, OrgInvite.email_lower == email_lower)
        .where(OrgInvite.accepted_at.is_(None))
    )
    invite = existing.scalar_one_or_none()
    plain = generate_token()
    if invite is None:
        invite = OrgInvite(
            id=str(uuid.uuid4()),
            org_id=org.id,
            email_lower=email_lower,
            role=role.value,
            token_hash=hash_token(plain),
            invited_by_user_id=actor.id,
            expires_at=utc_now() + timedelta(days=INVITE_TTL_DAYS),
        )
        db.add(invite)
    else:
        invite.role = role.value
        invite.token_hash = hash_token(plain)
        invite.invited_by_user_id = actor.id
        invite.expires_at = utc_now() + timedelta(days=INVITE_TTL_DAYS)
    await db.flush()

    subject, html, text = email_templates.org_invite(
        actor.name, org.name, frontend_origin, plain, role.value
    )
    await sender.send(db, to=email_lower, subject=subject, html=html, text=text)
    expires_iso = (as_utc(invite.expires_at) or utc_now()).isoformat()
    await _audit(
        db,
        kind="org.invite_sent",
        org_id=org.id,
        actor_user_id=actor.id,
        payload={"email": email_lower, "role": role.value},
    )
    return {
        "id": invite.id,
        "email": invite.email_lower,
        "role": invite.role,
        "expires_at": expires_iso,
    }


async def accept_invite(
    db: AsyncSession, *, token: str, user: User
) -> Org:
    h = hash_token(token)
    result = await db.execute(select(OrgInvite).where(OrgInvite.token_hash == h))
    invite = result.scalar_one_or_none()
    if invite is None:
        raise ApiError(400, "invite_invalid", "This invite link is invalid.")
    if invite.accepted_at is not None:
        raise ApiError(400, "invite_used", "This invite has already been used.")
    if (as_utc(invite.expires_at) or utc_now()) <= utc_now():
        raise ApiError(400, "invite_expired", "This invite has expired.")
    if invite.email_lower != user.email_lower:
        raise ApiError(
            403,
            "invite_email_mismatch",
            "This invite is for a different email address.",
        )

    org = await db.get(Org, invite.org_id)
    if org is None:
        raise ApiError(404, "org_not_found", "Workspace not found.")

    existing = await db.execute(
        select(OrgMembership).where(
            OrgMembership.org_id == org.id, OrgMembership.user_id == user.id
        )
    )
    if existing.scalar_one_or_none() is None:
        db.add(
            OrgMembership(
                user_id=user.id,
                org_id=org.id,
                role=invite.role,
            )
        )
    invite.accepted_at = utc_now()
    await _audit(
        db,
        kind="org.invite_accepted",
        org_id=org.id,
        actor_user_id=user.id,
        payload={"role": invite.role},
    )
    return org


async def change_role(
    db: AsyncSession,
    *,
    org: Org,
    actor: OrgMembership,
    target_user_id: str,
    new_role: Role,
) -> None:
    if actor.user_id == target_user_id:
        raise ApiError(400, "cannot_change_own_role", "You cannot change your own role.")
    result = await db.execute(
        select(OrgMembership).where(
            OrgMembership.org_id == org.id, OrgMembership.user_id == target_user_id
        )
    )
    target = result.scalar_one_or_none()
    if target is None:
        raise ApiError(404, "member_not_found", "Member not found.")
    # Only an owner can promote/demote another owner.
    if (target.role == Role.OWNER.value or new_role == Role.OWNER) and actor.role != Role.OWNER.value:
        raise ApiError(403, "owner_only", "Only owners can change owner roles.")
    target.role = new_role.value
    await _audit(
        db,
        kind="org.role_changed",
        org_id=org.id,
        actor_user_id=actor.user_id,
        payload={"target_user_id": target_user_id, "new_role": new_role.value},
    )


async def remove_member(
    db: AsyncSession,
    *,
    org: Org,
    actor: OrgMembership,
    target_user_id: str,
) -> None:
    if actor.user_id == target_user_id:
        raise ApiError(
            400,
            "cannot_remove_self",
            "Use 'Leave workspace' to remove yourself.",
        )
    result = await db.execute(
        select(OrgMembership).where(
            OrgMembership.org_id == org.id, OrgMembership.user_id == target_user_id
        )
    )
    target = result.scalar_one_or_none()
    if target is None:
        raise ApiError(404, "member_not_found", "Member not found.")
    if target.role == Role.OWNER.value and actor.role != Role.OWNER.value:
        raise ApiError(403, "owner_only", "Only owners can remove other owners.")

    await db.delete(target)
    # Sessions whose active org was this org get their active org cleared
    # so they fall back to another membership on next request.
    await db.execute(
        update(AuthSession)
        .where(AuthSession.user_id == target_user_id)
        .where(AuthSession.current_org_id == org.id)
        .values(current_org_id=None)
    )
    await _audit(
        db,
        kind="org.member_removed",
        org_id=org.id,
        actor_user_id=actor.user_id,
        payload={"target_user_id": target_user_id},
    )


async def delete_org(db: AsyncSession, *, org: Org, actor: User) -> None:
    """Owner-only. Wipes the org and everything that cascades from it
    (memberships, invites, audit events). Sessions whose `current_org_id`
    pointed at this org get the column cleared so they fall back to
    another membership next request — they don't get logged out.
    """
    # Authorization is enforced at the route layer via require_role(Role.OWNER).
    await _audit(
        db,
        kind="org.deleted",
        org_id=None,  # the org will be gone, so we attach the event to no org
        actor_user_id=actor.id,
        payload={"deleted_org_id": org.id, "deleted_org_name": org.name},
    )
    # Sessions pointing at this org get nulled so they fall back gracefully.
    from db.models import AuthSession  # local import — avoid cycles
    await db.execute(
        update(AuthSession)
        .where(AuthSession.current_org_id == org.id)
        .values(current_org_id=None)
    )
    await db.delete(org)


async def leave_org(db: AsyncSession, *, org: Org, user: User) -> None:
    """User removes their own membership. Last owner cannot leave; must
    transfer ownership first."""
    result = await db.execute(
        select(OrgMembership).where(
            OrgMembership.org_id == org.id, OrgMembership.user_id == user.id
        )
    )
    m = result.scalar_one_or_none()
    if m is None:
        raise ApiError(404, "not_a_member", "You're not a member of this workspace.")
    if m.role == Role.OWNER.value:
        # Make sure another owner exists.
        owners = await db.execute(
            select(OrgMembership).where(
                OrgMembership.org_id == org.id,
                OrgMembership.role == Role.OWNER.value,
            )
        )
        owner_count = len(owners.scalars().all())
        if owner_count <= 1:
            raise ApiError(
                400,
                "last_owner",
                "Promote another member to owner before leaving.",
            )
    await db.delete(m)
    await db.execute(
        update(AuthSession)
        .where(AuthSession.user_id == user.id)
        .where(AuthSession.current_org_id == org.id)
        .values(current_org_id=None)
    )
    await _audit(
        db,
        kind="org.member_left",
        org_id=org.id,
        actor_user_id=user.id,
    )


async def switch_active_org(
    db: AsyncSession, *, session: AuthSession, target_org_id: str, user: User
) -> Org:
    result = await db.execute(
        select(OrgMembership).where(
            OrgMembership.org_id == target_org_id, OrgMembership.user_id == user.id
        )
    )
    if result.scalar_one_or_none() is None:
        raise ApiError(403, "not_a_member", "You don't have access to that workspace.")
    org = await db.get(Org, target_org_id)
    if org is None:
        raise ApiError(404, "org_not_found", "Workspace not found.")
    session.current_org_id = org.id
    return org


async def list_audit_events(
    db: AsyncSession,
    *,
    org_id: str,
    limit: int = 50,
    since: "datetime | None" = None,
    until: "datetime | None" = None,
) -> list[dict]:
    from sqlalchemy import and_

    conds = [AuditEvent.org_id == org_id]
    if since is not None:
        conds.append(AuditEvent.created_at >= since)
    if until is not None:
        conds.append(AuditEvent.created_at <= until)
    result = await db.execute(
        select(AuditEvent)
        .where(and_(*conds))
        .order_by(AuditEvent.created_at.desc())
        .limit(limit)
    )
    rows = result.scalars().all()
    return [
        {
            "id": e.id,
            "kind": e.kind,
            "actor_user_id": e.actor_user_id,
            "payload": e.payload,
            "created_at": e.created_at.isoformat(),
        }
        for e in rows
    ]
