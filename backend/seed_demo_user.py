"""Seed (or refresh) a demo user for local development.

Idempotent. Creates `demo@siteiq.local` with a known password, marks the
email verified, and ensures the user owns a `Demo Construction` org so
the dashboard has a workspace to load. Re-running the script just resets
the password and confirms verification — handy when you've forgotten
the demo password or wiped your local DB.

Usage:

    cd siteiq/backend
    uv run python seed_demo_user.py

Override the defaults via env vars:

    SITEIQ_DEMO_EMAIL=foo@bar.com SITEIQ_DEMO_PASSWORD=hunter2hunter2 \
        uv run python seed_demo_user.py

This writes directly via the ORM, bypassing /auth/signup — no email
verification token is generated and the IP rate limiter never sees it.
"""

from __future__ import annotations

import asyncio
import os
import sys
import uuid
from pathlib import Path

# Make the script runnable from anywhere (`python backend/seed_demo_user.py`
# or `cd backend && python seed_demo_user.py`) by ensuring the backend
# package directory is on sys.path.
_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from sqlalchemy import select  # noqa: E402

from auth.passwords import hash_password  # noqa: E402
from auth.timeutil import utc_now  # noqa: E402
from db.engine import create_db_engine  # noqa: E402
from db.models import Org, OrgMembership, Plan, Role, User  # noqa: E402
from settings import get_settings  # noqa: E402


DEFAULT_EMAIL = "demo@siteiq.dev"
DEFAULT_PASSWORD = "DemoPassword123!"
DEFAULT_NAME = "Demo User"
DEFAULT_COMPANY = "Demo Construction"
DEFAULT_ORG_SLUG = "demo-construction"


async def seed() -> None:
    settings = get_settings()
    email = os.environ.get("SITEIQ_DEMO_EMAIL", DEFAULT_EMAIL).strip()
    password = os.environ.get("SITEIQ_DEMO_PASSWORD", DEFAULT_PASSWORD)
    name = os.environ.get("SITEIQ_DEMO_NAME", DEFAULT_NAME).strip()
    company = os.environ.get("SITEIQ_DEMO_COMPANY", DEFAULT_COMPANY).strip()

    if len(password) < 12:
        raise SystemExit(
            "SITEIQ_DEMO_PASSWORD must be at least 12 characters "
            "(matches the /auth/signup validator)."
        )

    engine, session_factory = create_db_engine(settings.database_url)
    try:
        async with session_factory() as db:
            email_lower = email.lower()
            user = (
                await db.execute(select(User).where(User.email_lower == email_lower))
            ).scalar_one_or_none()

            if user is None:
                user = User(
                    id=str(uuid.uuid4()),
                    email_lower=email_lower,
                    email_display=email,
                    name=name,
                    password_hash=hash_password(password),
                    email_verified_at=utc_now(),
                )
                db.add(user)
                action_user = "created"
            else:
                user.password_hash = hash_password(password)
                if user.email_verified_at is None:
                    user.email_verified_at = utc_now()
                action_user = "refreshed"

            await db.flush()

            org = (
                await db.execute(select(Org).where(Org.slug == DEFAULT_ORG_SLUG))
            ).scalar_one_or_none()
            if org is None:
                org = Org(
                    id=str(uuid.uuid4()),
                    name=company,
                    slug=DEFAULT_ORG_SLUG,
                    plan=Plan.TRIAL.value,
                )
                db.add(org)
                action_org = "created"
            else:
                action_org = "reused"

            await db.flush()

            membership = (
                await db.execute(
                    select(OrgMembership).where(
                        OrgMembership.user_id == user.id,
                        OrgMembership.org_id == org.id,
                    )
                )
            ).scalar_one_or_none()
            if membership is None:
                db.add(
                    OrgMembership(
                        user_id=user.id,
                        org_id=org.id,
                        role=Role.OWNER.value,
                    )
                )
                action_membership = "created (owner)"
            else:
                if membership.role != Role.OWNER.value:
                    membership.role = Role.OWNER.value
                    action_membership = "promoted to owner"
                else:
                    action_membership = "reused (owner)"

            await db.commit()

        print(
            "\n  SiteIQ demo user ready\n"
            f"    email:    {email}\n"
            f"    password: {password}\n"
            f"    org:      {company} ({DEFAULT_ORG_SLUG})\n"
            f"    user:     {action_user}\n"
            f"    org row:  {action_org}\n"
            f"    membership: {action_membership}\n"
            f"    db url:   {settings.database_url}\n"
            "  → log in at the frontend (http://localhost:5173/login by default).\n"
        )
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(seed())
