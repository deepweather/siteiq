"""Auth garbage collection — expired sessions + tokens get pruned."""
from __future__ import annotations

import asyncio
import uuid
from datetime import timedelta
from pathlib import Path


def _make_db(tmp_path):
    from alembic import command
    from alembic.config import Config
    from db.engine import create_db_engine

    db = tmp_path / "auth_gc.db"
    url = f"sqlite+aiosqlite:///{db}"
    cfg = Config(str(Path(__file__).resolve().parent.parent / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", url)
    cfg.set_main_option(
        "script_location",
        str(Path(__file__).resolve().parent.parent / "alembic"),
    )
    command.upgrade(cfg, "head")
    return create_db_engine(url)


def test_cleanup_drops_old_revoked_sessions_and_keeps_live_ones(tmp_path):
    from auth.auth_cleanup import cleanup_once
    from auth.timeutil import utc_now
    from db.models import AuthSession
    from sqlalchemy import select

    engine, factory = _make_db(tmp_path)

    async def _go():
        # Seed: a live session, a recently-revoked one, and an old revoked one.
        async with factory() as db:
            now = utc_now()
            db.add(
                AuthSession(
                    id="live",
                    user_id="u-live",
                    token_hash="h-live",
                    user_agent="",
                    ip="",
                    created_at=now,
                    last_seen_at=now,
                    expires_at=now + timedelta(days=14),
                )
            )
            db.add(
                AuthSession(
                    id="recent-revoked",
                    user_id="u-r",
                    token_hash="h-r",
                    user_agent="",
                    ip="",
                    created_at=now - timedelta(days=1),
                    last_seen_at=now - timedelta(days=1),
                    expires_at=now + timedelta(days=14),
                    revoked_at=now - timedelta(hours=2),
                )
            )
            db.add(
                AuthSession(
                    id="old-revoked",
                    user_id="u-o",
                    token_hash="h-o",
                    user_agent="",
                    ip="",
                    created_at=now - timedelta(days=120),
                    last_seen_at=now - timedelta(days=120),
                    expires_at=now - timedelta(days=100),
                    revoked_at=now - timedelta(days=100),
                )
            )
            await db.commit()

        out = await cleanup_once(
            factory, session_retention_days=30, token_retention_days=7
        )
        assert out["auth_sessions"] == 1

        async with factory() as db:
            ids = {
                s.id for s in (await db.execute(select(AuthSession))).scalars().all()
            }
        assert ids == {"live", "recent-revoked"}
        await engine.dispose()

    asyncio.run(_go())


def test_cleanup_drops_consumed_old_tokens(tmp_path):
    from auth.auth_cleanup import cleanup_once
    from auth.timeutil import utc_now
    from db.models import VerificationToken
    from sqlalchemy import select

    engine, factory = _make_db(tmp_path)

    async def _go():
        now = utc_now()
        async with factory() as db:
            db.add(
                VerificationToken(
                    id=str(uuid.uuid4()),
                    user_id="u",
                    kind="email_verify",
                    token_hash="t-fresh",
                    expires_at=now + timedelta(hours=1),
                    created_at=now,
                )
            )
            db.add(
                VerificationToken(
                    id=str(uuid.uuid4()),
                    user_id="u",
                    kind="email_verify",
                    token_hash="t-stale",
                    expires_at=now - timedelta(days=30),
                    consumed_at=now - timedelta(days=30),
                    created_at=now - timedelta(days=30),
                )
            )
            await db.commit()

        out = await cleanup_once(
            factory, session_retention_days=30, token_retention_days=7
        )
        assert out["verification_tokens"] == 1

        async with factory() as db:
            hashes = {
                t.token_hash
                for t in (await db.execute(select(VerificationToken))).scalars().all()
            }
        assert hashes == {"t-fresh"}
        await engine.dispose()

    asyncio.run(_go())


def test_zero_retention_disables_cleanup(tmp_path):
    from auth.auth_cleanup import cleanup_once
    from auth.timeutil import utc_now
    from db.models import AuthSession

    engine, factory = _make_db(tmp_path)

    async def _go():
        now = utc_now()
        async with factory() as db:
            db.add(
                AuthSession(
                    id="ancient",
                    user_id="u",
                    token_hash="h",
                    user_agent="",
                    ip="",
                    created_at=now - timedelta(days=999),
                    last_seen_at=now - timedelta(days=999),
                    expires_at=now - timedelta(days=999),
                    revoked_at=now - timedelta(days=999),
                )
            )
            await db.commit()
        out = await cleanup_once(factory, session_retention_days=0, token_retention_days=0)
        assert out == {"auth_sessions": 0, "verification_tokens": 0}
        await engine.dispose()

    asyncio.run(_go())
