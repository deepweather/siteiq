"""Pluggable email sender — Protocol + two implementations.

Every sender persists the message to the `email_outbox` table first, then
attempts delivery and updates `status` accordingly. This means:
- The dev story (`ConsoleSender`) needs no SMTP setup; messages are
  visible at /dev/outbox.
- The prod story (`ResendSender`) keeps a durable audit trail of every
  email we ever sent, and tests can assert against it without mocking
  HTTP.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Protocol, runtime_checkable

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import EmailOutbox, EmailStatus


logger = logging.getLogger("siteiq.auth.email")


@runtime_checkable
class EmailSender(Protocol):
    """Send a transactional email. Persists to outbox before delivery."""

    async def send(
        self,
        db: AsyncSession,
        *,
        to: str,
        subject: str,
        html: str,
        text: str,
    ) -> str:
        """Returns the outbox row id."""
        ...


class ConsoleSender:
    """Dev/test sender: writes to outbox, logs the message, marks as sent.

    Tests use the outbox row to discover the verification/reset token
    (the URL is included in both `text` and `html`).
    """

    async def send(
        self,
        db: AsyncSession,
        *,
        to: str,
        subject: str,
        html: str,
        text: str,
    ) -> str:
        row = EmailOutbox(
            id=str(uuid.uuid4()),
            to_email=to,
            subject=subject,
            html=html,
            text=text,
            status=EmailStatus.SENT.value,
            sent_at=datetime.now(timezone.utc),
        )
        db.add(row)
        await db.flush()
        logger.info(
            "email_console_sent",
            extra={"to": to, "subject": subject, "outbox_id": row.id},
        )
        return row.id


class ResendSender:
    """Prod sender via the Resend HTTPS API.

    Persists to outbox, posts to api.resend.com, updates status. Errors
    are surfaced to the caller (signup/reset flow) so the user sees a
    real failure rather than a silent one.
    """

    BASE_URL = "https://api.resend.com/emails"

    def __init__(self, api_key: str, from_address: str, http: httpx.AsyncClient | None = None) -> None:
        if not api_key:
            raise ValueError("ResendSender requires a non-empty api_key")
        self._api_key = api_key
        self._from = from_address
        self._http = http or httpx.AsyncClient(timeout=10.0)
        self._owns_http = http is None

    async def send(
        self,
        db: AsyncSession,
        *,
        to: str,
        subject: str,
        html: str,
        text: str,
    ) -> str:
        row = EmailOutbox(
            id=str(uuid.uuid4()),
            to_email=to,
            subject=subject,
            html=html,
            text=text,
            status=EmailStatus.PENDING.value,
        )
        db.add(row)
        await db.flush()

        try:
            resp = await self._http.post(
                self.BASE_URL,
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "from": self._from,
                    "to": [to],
                    "subject": subject,
                    "html": html,
                    "text": text,
                },
            )
            resp.raise_for_status()
        except Exception as e:
            row.status = EmailStatus.FAILED.value
            row.error = str(e)
            await db.flush()
            logger.exception("email_resend_failed", extra={"outbox_id": row.id, "to": to})
            raise

        row.status = EmailStatus.SENT.value
        row.sent_at = datetime.now(timezone.utc)
        await db.flush()
        logger.info(
            "email_resend_sent",
            extra={"to": to, "subject": subject, "outbox_id": row.id},
        )
        return row.id

    async def aclose(self) -> None:
        if self._owns_http:
            await self._http.aclose()


def build_sender_from_settings(settings) -> EmailSender:
    """Factory used at app startup. `settings` is a Settings instance —
    typed loosely to avoid an import cycle with the email module."""
    provider = settings.email_provider.lower()
    if provider == "resend":
        return ResendSender(api_key=settings.resend_api_key, from_address=settings.email_from)
    return ConsoleSender()
