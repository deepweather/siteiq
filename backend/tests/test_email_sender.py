"""Tests for the EmailSender Protocol implementations."""
from __future__ import annotations

import asyncio

import httpx
import pytest

from auth.email_sender import ConsoleSender, EmailSender, ResendSender
from db.engine import create_db_engine
from db.models import EmailOutbox, EmailStatus


def _make_db(tmp_path):
    from alembic import command
    from alembic.config import Config
    from pathlib import Path

    db = tmp_path / "email.db"
    url = f"sqlite+aiosqlite:///{db}"
    cfg = Config(str(Path(__file__).resolve().parent.parent / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", url)
    cfg.set_main_option(
        "script_location",
        str(Path(__file__).resolve().parent.parent / "alembic"),
    )
    command.upgrade(cfg, "head")
    return create_db_engine(url)


def test_console_sender_implements_protocol():
    assert isinstance(ConsoleSender(), EmailSender)


def test_console_sender_writes_outbox(tmp_path):
    engine, factory = _make_db(tmp_path)
    sender = ConsoleSender()

    async def _go():
        async with factory() as db:
            outbox_id = await sender.send(
                db, to="x@y.test", subject="Hi", html="<p>hi</p>", text="hi"
            )
            await db.commit()
        async with factory() as db:
            row = await db.get(EmailOutbox, outbox_id)
            assert row is not None
            assert row.to_email == "x@y.test"
            assert row.subject == "Hi"
            assert row.status == EmailStatus.SENT.value
        await engine.dispose()

    asyncio.run(_go())


def test_resend_sender_posts_and_marks_sent(tmp_path):
    engine, factory = _make_db(tmp_path)

    captured = {}

    def _handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["json"] = request.read().decode("utf-8")
        captured["auth"] = request.headers.get("authorization", "")
        return httpx.Response(200, json={"id": "evt_123"})

    transport = httpx.MockTransport(_handler)
    http = httpx.AsyncClient(transport=transport)
    sender = ResendSender(api_key="k_test", from_address="SiteIQ <n@s>", http=http)

    async def _go():
        async with factory() as db:
            outbox_id = await sender.send(
                db, to="x@y.test", subject="Reset", html="<p/>", text="t"
            )
            await db.commit()
        async with factory() as db:
            row = await db.get(EmailOutbox, outbox_id)
            assert row.status == EmailStatus.SENT.value
        assert captured["url"] == ResendSender.BASE_URL
        assert "k_test" in captured["auth"]
        await sender.aclose()
        await engine.dispose()

    asyncio.run(_go())


def test_resend_sender_marks_failed_on_5xx(tmp_path):
    engine, factory = _make_db(tmp_path)

    transport = httpx.MockTransport(lambda r: httpx.Response(500, text="boom"))
    http = httpx.AsyncClient(transport=transport)
    sender = ResendSender(api_key="k_test", from_address="from@s", http=http)

    async def _go():
        async with factory() as db:
            with pytest.raises(httpx.HTTPStatusError):
                await sender.send(db, to="x@y.test", subject="s", html="", text="")
            await db.commit()
        async with factory() as db:
            from sqlalchemy import select
            rows = (await db.execute(select(EmailOutbox))).scalars().all()
            assert len(rows) == 1
            assert rows[0].status == EmailStatus.FAILED.value
            assert "500" in (rows[0].error or "")
        await sender.aclose()
        await engine.dispose()

    asyncio.run(_go())
