"""Dev-only routes. Mounted only when settings.env == 'dev'.

The /dev/outbox UI is the substitute for SMTP in development — magic
links and reset tokens land here instead of an inbox.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import EmailOutbox
from db.session import get_db


router = APIRouter()


@router.get("/dev/outbox")
async def dev_outbox(db: AsyncSession = Depends(get_db)):
    """List the most recent 100 emails in human-readable form."""
    result = await db.execute(
        select(EmailOutbox).order_by(EmailOutbox.created_at.desc()).limit(100)
    )
    rows = result.scalars().all()
    return [
        {
            "id": r.id,
            "to": r.to_email,
            "subject": r.subject,
            "status": r.status,
            "created_at": r.created_at.isoformat(),
            "sent_at": r.sent_at.isoformat() if r.sent_at else None,
            "text": r.text,
            "html": r.html,
            "error": r.error,
        }
        for r in rows
    ]


@router.get("/dev/outbox/{outbox_id}/html", response_class=None)
async def dev_outbox_html(outbox_id: str, db: AsyncSession = Depends(get_db)):
    from fastapi.responses import HTMLResponse, PlainTextResponse
    row = await db.get(EmailOutbox, outbox_id)
    if row is None:
        return PlainTextResponse("not found", status_code=404)
    return HTMLResponse(row.html)
