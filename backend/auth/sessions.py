"""Server-side session management + cookie helpers.

Sessions are opaque tokens persisted in the auth_sessions table. The
plaintext token is stored only in the user's HttpOnly cookie; the DB
holds sha256(token). This makes:

- Revocation trivial (delete or mark revoked_at).
- "Sign out everywhere" trivial (revoke all sessions for a user).
- Theft of the DB unable to forge cookies.

Cookie name: in prod we use the `__Host-` prefix (browser enforces
Path=/, Secure, no Domain attribute). In dev we use the plain name so
http://localhost works.
"""
from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Optional

from fastapi import Response
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from auth.timeutil import as_utc, utc_now
from auth.tokens import generate_token, hash_token
from db.models import AuthSession


def cookie_name(settings) -> str:
    base = settings.session_cookie_name
    if settings.effective_cookie_secure and not settings.cookie_domain:
        return f"__Host-{base}"
    return base


async def create_session(
    db: AsyncSession,
    *,
    user_id: str,
    org_id: Optional[str],
    user_agent: str,
    ip: str,
    lifetime_days: int,
) -> tuple[AuthSession, str]:
    """Persists a fresh session and returns (row, plaintext_token)."""
    token = generate_token()
    now = utc_now()
    row = AuthSession(
        id=str(uuid.uuid4()),
        user_id=user_id,
        current_org_id=org_id,
        token_hash=hash_token(token),
        user_agent=(user_agent or "")[:512],
        ip=(ip or "")[:64],
        created_at=now,
        last_seen_at=now,
        expires_at=now + timedelta(days=lifetime_days),
    )
    db.add(row)
    await db.flush()
    return row, token


async def get_session(db: AsyncSession, token: str) -> Optional[AuthSession]:
    """Look up a live (non-revoked, non-expired) session by plaintext token."""
    h = hash_token(token)
    result = await db.execute(select(AuthSession).where(AuthSession.token_hash == h))
    row = result.scalar_one_or_none()
    if row is None:
        return None
    now = utc_now()
    expires_at = as_utc(row.expires_at)
    if row.revoked_at is not None or (expires_at is not None and expires_at <= now):
        return None
    return row


async def touch_session(db: AsyncSession, session: AuthSession, idle_days: int) -> None:
    """Sliding window — bumps last_seen_at and extends expires_at by idle_days
    if it's about to lapse. Cheap: a single UPDATE per request that already
    has the session row."""
    now = utc_now()
    session.last_seen_at = now
    new_exp = now + timedelta(days=idle_days)
    current_exp = as_utc(session.expires_at) or now
    if new_exp > current_exp:
        session.expires_at = new_exp


async def revoke_session(db: AsyncSession, session_id: str) -> None:
    await db.execute(
        update(AuthSession)
        .where(AuthSession.id == session_id)
        .values(revoked_at=utc_now())
    )


async def revoke_all_for_user(db: AsyncSession, user_id: str) -> int:
    result = await db.execute(
        update(AuthSession)
        .where(AuthSession.user_id == user_id)
        .where(AuthSession.revoked_at.is_(None))
        .values(revoked_at=utc_now())
    )
    return result.rowcount or 0


def set_session_cookie(response: Response, settings, token: str, lifetime_days: int) -> None:
    response.set_cookie(
        key=cookie_name(settings),
        value=token,
        max_age=lifetime_days * 24 * 3600,
        httponly=True,
        secure=settings.effective_cookie_secure,
        samesite="lax",
        path="/",
        domain=settings.cookie_domain,
    )


def clear_session_cookie(response: Response, settings) -> None:
    response.delete_cookie(
        key=cookie_name(settings),
        path="/",
        domain=settings.cookie_domain,
    )
