"""Pure-function business logic for auth.

Routes call into here. Each function takes an AsyncSession and returns
data; no FastAPI types leak into this module. This makes the logic
trivially testable and the routes paper-thin.
"""
from __future__ import annotations

import logging
import re
import uuid
from datetime import timedelta
from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from auth import email_templates
from auth.email_sender import EmailSender
from auth.errors import ApiError
from auth.passwords import hash_password, verify_password
from auth.timeutil import as_utc, utc_now
from auth.tokens import generate_token, hash_token
from db.models import (
    AuditEvent,
    AuthSession,
    Org,
    OrgMembership,
    Plan,
    Role,
    TokenKind,
    User,
    VerificationToken,
)


logger = logging.getLogger("siteiq.auth.service")


PASSWORD_MIN_LEN = 12
EMAIL_VERIFY_TTL_HOURS = 24
PASSWORD_RESET_TTL_MINUTES = 30
MAGIC_LINK_TTL_MINUTES = 15
INVITE_TTL_DAYS = 7

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def _slugify(name: str) -> str:
    s = _SLUG_RE.sub("-", name.strip().lower()).strip("-")
    return s or "org"


async def _unique_slug(db: AsyncSession, base: str) -> str:
    """Append -2, -3, ... until the slug is free. Linear in collisions;
    fine for org creation traffic."""
    candidate = base
    n = 1
    while True:
        result = await db.execute(select(Org.id).where(Org.slug == candidate))
        if result.scalar_one_or_none() is None:
            return candidate
        n += 1
        candidate = f"{base}-{n}"


def _validate_password(password: str) -> None:
    if len(password) < PASSWORD_MIN_LEN:
        raise ApiError(
            status_code=400,
            code="password_too_short",
            message=f"Password must be at least {PASSWORD_MIN_LEN} characters.",
            field="password",
        )


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


# ---------------------------------------------------------------------------
# Signup + initial org
# ---------------------------------------------------------------------------


async def signup_user(
    db: AsyncSession,
    *,
    email: str,
    name: str,
    password: str,
    company: str,
    sender: EmailSender,
    frontend_origin: str,
) -> tuple[User, Org]:
    """Create a User, an Org named after `company`, owner membership, and
    queue an email-verification token. The user lands logged-in immediately
    (verification is non-blocking for 7 days)."""
    email_lower = _normalize_email(email)
    name = name.strip()
    company = company.strip()

    if not name:
        raise ApiError(400, "name_required", "Name is required.", field="name")
    if not company:
        raise ApiError(400, "company_required", "Company name is required.", field="company")
    if "@" not in email_lower or "." not in email_lower:
        raise ApiError(400, "invalid_email", "Enter a valid email address.", field="email")
    _validate_password(password)

    existing = await db.execute(select(User.id).where(User.email_lower == email_lower))
    if existing.scalar_one_or_none() is not None:
        raise ApiError(
            409,
            "email_taken",
            "An account with this email already exists.",
            field="email",
        )

    user = User(
        id=str(uuid.uuid4()),
        email_lower=email_lower,
        email_display=email.strip(),
        name=name,
        password_hash=hash_password(password),
    )
    db.add(user)

    slug = await _unique_slug(db, _slugify(company))
    org = Org(
        id=str(uuid.uuid4()),
        name=company,
        slug=slug,
        plan=Plan.TRIAL.value,
    )
    db.add(org)
    db.add(
        OrgMembership(
            user_id=user.id,
            org_id=org.id,
            role=Role.OWNER.value,
        )
    )
    await db.flush()

    await _send_verification_email(db, user=user, sender=sender, frontend_origin=frontend_origin)
    await _audit(db, kind="user.signup", org_id=org.id, actor_user_id=user.id, payload={"email": email_lower})
    await _audit(db, kind="org.created", org_id=org.id, actor_user_id=user.id, payload={"name": company})

    return user, org


async def _send_verification_email(
    db: AsyncSession,
    *,
    user: User,
    sender: EmailSender,
    frontend_origin: str,
) -> None:
    token = generate_token()
    db.add(
        VerificationToken(
            id=str(uuid.uuid4()),
            user_id=user.id,
            kind=TokenKind.EMAIL_VERIFY.value,
            token_hash=hash_token(token),
            expires_at=utc_now() + timedelta(hours=EMAIL_VERIFY_TTL_HOURS),
        )
    )
    await db.flush()
    subject, html, text = email_templates.verify_email(user.name, frontend_origin, token)
    await sender.send(db, to=user.email_display, subject=subject, html=html, text=text)


async def resend_verification_email(
    db: AsyncSession, *, user: User, sender: EmailSender, frontend_origin: str
) -> None:
    if user.email_verified_at is not None:
        return
    await _send_verification_email(db, user=user, sender=sender, frontend_origin=frontend_origin)


# ---------------------------------------------------------------------------
# Login + sessions
# ---------------------------------------------------------------------------


async def authenticate(db: AsyncSession, *, email: str, password: str) -> User:
    """Returns the User row on success or raises ApiError(401)."""
    email_lower = _normalize_email(email)
    result = await db.execute(select(User).where(User.email_lower == email_lower))
    user = result.scalar_one_or_none()
    if user is None:
        # Do not leak whether the email exists.
        raise ApiError(401, "invalid_credentials", "Email or password is incorrect.")
    if not verify_password(password, user.password_hash):
        raise ApiError(401, "invalid_credentials", "Email or password is incorrect.")
    user.last_login_at = utc_now()
    return user


async def primary_org_for(db: AsyncSession, user_id: str) -> Optional[Org]:
    """Pick the most-recently-joined org for the user (used as the active
    org of a fresh session). For a new signup this is their auto-created
    org; for invitees, it'll be the inviting org once they accept."""
    result = await db.execute(
        select(Org)
        .join(OrgMembership, OrgMembership.org_id == Org.id)
        .where(OrgMembership.user_id == user_id)
        .order_by(OrgMembership.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


# ---------------------------------------------------------------------------
# Email verification
# ---------------------------------------------------------------------------


async def verify_email(db: AsyncSession, *, token: str) -> User:
    record = await _consume_token(db, token=token, kind=TokenKind.EMAIL_VERIFY)
    user = await db.get(User, record.user_id)
    if user is None:
        raise ApiError(404, "user_not_found", "Account not found.")
    if user.email_verified_at is None:
        user.email_verified_at = utc_now()
    await _audit(db, kind="user.email_verified", org_id=None, actor_user_id=user.id)
    return user


# ---------------------------------------------------------------------------
# Password reset
# ---------------------------------------------------------------------------


# Landing paths a magic-link email is allowed to point at. Constrained to
# prevent the optional `path` from becoming an open-redirect vector.
MAGIC_LINK_PATHS = {"/magic-link", "/worker/login"}


async def request_magic_link(
    db: AsyncSession,
    *,
    email: str,
    sender: EmailSender,
    frontend_origin: str,
    path: str = "/magic-link",
) -> None:
    """Sends a one-time sign-in link to the given email if the account
    exists. Always returns silently — same external behavior whether
    or not the email is registered, so we never leak account
    existence.

    `path` selects the landing route (e.g. `/worker/login` for the worker
    PWA) and is validated against an allow-list. The token is single-use
    and expires in MAGIC_LINK_TTL_MINUTES; consuming it logs the user in
    without their password.
    """
    if path not in MAGIC_LINK_PATHS:
        path = "/magic-link"
    email_lower = _normalize_email(email)
    result = await db.execute(select(User).where(User.email_lower == email_lower))
    user = result.scalar_one_or_none()
    if user is None:
        return

    token = generate_token()
    db.add(
        VerificationToken(
            id=str(uuid.uuid4()),
            user_id=user.id,
            kind=TokenKind.MAGIC_LINK.value,
            token_hash=hash_token(token),
            expires_at=utc_now() + timedelta(minutes=MAGIC_LINK_TTL_MINUTES),
        )
    )
    await db.flush()
    subject, html, text = email_templates.magic_link(user.name, frontend_origin, token, path)
    await sender.send(db, to=user.email_display, subject=subject, html=html, text=text)
    await _audit(db, kind="user.magic_link_requested", org_id=None, actor_user_id=user.id)


async def login_with_magic_link(db: AsyncSession, *, token: str) -> User:
    """Consumes a magic-link token and returns the matching user.
    Caller is responsible for issuing the session cookie."""
    record = await _consume_token(db, token=token, kind=TokenKind.MAGIC_LINK)
    user = await db.get(User, record.user_id)
    if user is None:
        raise ApiError(404, "user_not_found", "Account not found.")
    user.last_login_at = utc_now()
    await _audit(db, kind="user.magic_link_login", org_id=None, actor_user_id=user.id)
    return user


async def request_password_reset(
    db: AsyncSession, *, email: str, sender: EmailSender, frontend_origin: str
) -> None:
    """Always returns success (we never reveal whether an account exists)."""
    email_lower = _normalize_email(email)
    result = await db.execute(select(User).where(User.email_lower == email_lower))
    user = result.scalar_one_or_none()
    if user is None:
        return  # Silent — same behavior as if the email existed.

    token = generate_token()
    db.add(
        VerificationToken(
            id=str(uuid.uuid4()),
            user_id=user.id,
            kind=TokenKind.PASSWORD_RESET.value,
            token_hash=hash_token(token),
            expires_at=utc_now() + timedelta(minutes=PASSWORD_RESET_TTL_MINUTES),
        )
    )
    await db.flush()
    subject, html, text = email_templates.password_reset(user.name, frontend_origin, token)
    await sender.send(db, to=user.email_display, subject=subject, html=html, text=text)
    await _audit(db, kind="user.password_reset_requested", org_id=None, actor_user_id=user.id)


async def reset_password(db: AsyncSession, *, token: str, new_password: str) -> User:
    _validate_password(new_password)
    record = await _consume_token(db, token=token, kind=TokenKind.PASSWORD_RESET)
    user = await db.get(User, record.user_id)
    if user is None:
        raise ApiError(404, "user_not_found", "Account not found.")
    user.password_hash = hash_password(new_password)
    # Revoke all existing sessions — a reset implies prior sessions may be
    # compromised. The current request will be issued a new session.
    await db.execute(
        update(AuthSession)
        .where(AuthSession.user_id == user.id)
        .where(AuthSession.revoked_at.is_(None))
        .values(revoked_at=utc_now())
    )
    await _audit(db, kind="user.password_reset", org_id=None, actor_user_id=user.id)
    return user


async def delete_account(
    db: AsyncSession, *, user: User, current_password: str
) -> list[str]:
    """Deletes the user. Returns a list of org ids that became
    member-less (empty owners) and were also deleted.

    The user must re-supply their password — deletion is destructive
    and the password gate prevents an attacker who hijacks an active
    session from quietly nuking the account.

    For each org the user OWNED:
      - if there's another owner left → the org survives, only the
        membership disappears.
      - if the deleted user was the *last* owner → the org is deleted
        entirely (cascade drops memberships, invites, audit_events).
    Other roles (admin/member/viewer) just lose their membership.
    """
    if not verify_password(current_password, user.password_hash):
        raise ApiError(400, "invalid_password", "Password is incorrect.", field="current_password")

    # Find every org the user is a member of, and how many owners each has.
    memberships = (
        await db.execute(
            select(OrgMembership).where(OrgMembership.user_id == user.id)
        )
    ).scalars().all()
    deleted_orgs: list[str] = []
    for m in memberships:
        if m.role == Role.OWNER.value:
            other_owners = await db.execute(
                select(OrgMembership).where(
                    OrgMembership.org_id == m.org_id,
                    OrgMembership.user_id != user.id,
                    OrgMembership.role == Role.OWNER.value,
                )
            )
            if other_owners.scalar_one_or_none() is None:
                # Last owner — wipe the org entirely.
                org = await db.get(Org, m.org_id)
                if org is not None:
                    await _audit(
                        db,
                        kind="org.deleted",
                        org_id=None,
                        actor_user_id=user.id,
                        payload={"reason": "owner_account_deletion", "org_id": m.org_id, "org_name": org.name},
                    )
                    await db.delete(org)
                    deleted_orgs.append(m.org_id)

    await _audit(
        db,
        kind="user.deleted",
        org_id=None,
        actor_user_id=None,
        payload={"deleted_user_id": user.id, "email": user.email_lower},
    )
    await db.delete(user)
    return deleted_orgs


async def change_password(
    db: AsyncSession, *, user: User, current: str, new_password: str, current_session_id: str
) -> None:
    if not verify_password(current, user.password_hash):
        raise ApiError(400, "invalid_password", "Current password is incorrect.", field="current")
    _validate_password(new_password)
    user.password_hash = hash_password(new_password)
    # Revoke every other session except the one that initiated the change.
    await db.execute(
        update(AuthSession)
        .where(AuthSession.user_id == user.id)
        .where(AuthSession.id != current_session_id)
        .where(AuthSession.revoked_at.is_(None))
        .values(revoked_at=utc_now())
    )
    await _audit(db, kind="user.password_changed", org_id=None, actor_user_id=user.id)


# ---------------------------------------------------------------------------
# Token consumption (shared)
# ---------------------------------------------------------------------------


async def _consume_token(
    db: AsyncSession, *, token: str, kind: TokenKind
) -> VerificationToken:
    h = hash_token(token)
    result = await db.execute(
        select(VerificationToken).where(VerificationToken.token_hash == h)
    )
    record = result.scalar_one_or_none()
    if record is None or record.kind != kind.value:
        raise ApiError(400, "token_invalid", "This link is invalid.")
    if record.consumed_at is not None:
        raise ApiError(400, "token_used", "This link has already been used.")
    expires_at = as_utc(record.expires_at) or utc_now()
    if expires_at <= utc_now():
        raise ApiError(400, "token_expired", "This link has expired.")
    record.consumed_at = utc_now()
    return record
