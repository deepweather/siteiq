"""Backfill demo system-of-record history for an org's active project.

Since there's no live construction site yet, this populates the event
ledger with a realistic multi-week operational history so the Record UI
(timeline, inbox, costs, ledger, ask) has something real to show. Uses the
same `EventLedger` the live simulation feeds, so the data is genuine, not a
UI mock — when real camera feeds arrive they append to the same stream.

Usage:

    cd siteiq/backend
    uv run python seed_demo_record.py                 # demo-construction org
    SITEIQ_DEMO_ORG_SLUG=acme uv run python seed_demo_record.py
    SITEIQ_RECORD_DAYS=30 uv run python seed_demo_record.py

Idempotent: clears the org's existing stream and regenerates from a fixed
seed, so re-running yields the same ledger.
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

_HERE = Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from sqlalchemy import select  # noqa: E402

from db.engine import create_db_engine  # noqa: E402
from db.models import Org  # noqa: E402
from db.project_repository import ProjectRepository  # noqa: E402
from models.project_document import ProjectDocument  # noqa: E402
from seeds.loader import load_seed_document  # noqa: E402
from services.demo_record_generator import (  # noqa: E402
    RECORD_BACKFILL_DAYS,
    generate_demo_history,
)
from settings import get_settings  # noqa: E402


DEFAULT_ORG_SLUG = "demo-construction"


async def _resolve_document(db, org: Org, default_project_id: str) -> ProjectDocument | None:
    """Resolve the org's active project document the same way `get_source`
    does: pinned version first, then active seed slug, then default seed."""
    if org.active_project_version_id:
        repo = ProjectRepository(db)
        version = await repo.get_version(org.active_project_version_id)
        if version is not None:
            return ProjectDocument.model_validate(version.document)
    slug = org.active_project_id or default_project_id
    return load_seed_document(slug)


async def run() -> None:
    settings = get_settings()
    org_slug = os.environ.get("SITEIQ_DEMO_ORG_SLUG", DEFAULT_ORG_SLUG).strip()
    days = int(os.environ.get("SITEIQ_RECORD_DAYS", str(RECORD_BACKFILL_DAYS)))

    engine, session_factory = create_db_engine(settings.database_url)
    try:
        async with session_factory() as db:
            org = (
                await db.execute(select(Org).where(Org.slug == org_slug))
            ).scalar_one_or_none()
            if org is None:
                raise SystemExit(
                    f"Org with slug {org_slug!r} not found. Run seed_demo_user.py first "
                    "or set SITEIQ_DEMO_ORG_SLUG."
                )
            doc = await _resolve_document(db, org, settings.default_project_id)
            if doc is None:
                raise SystemExit(
                    "Could not resolve an active project document for this org."
                )
            summary = await generate_demo_history(
                db, org_id=org.id, document=doc, days=days
            )
            await db.commit()

        print(
            "\n  SiteIQ demo record backfilled\n"
            f"    org:      {org_slug}\n"
            f"    project:  {summary['project_id']}\n"
            f"    days:     {summary['days']}\n"
            f"    events:   {summary['event_count']}\n"
            f"    proposed: {summary['proposed_count']} (awaiting confirmation)\n"
            f"    kinds:    {summary['kinds']}\n"
            f"    db url:   {settings.database_url}\n"
            "  → open the Record section in the app to explore it.\n"
        )
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(run())
