"""Add client_event_id to site_events for offline-safe worker entries.

The worker PWA buffers entries in an IndexedDB outbox while offline and
replays them when connectivity returns. A client-generated idempotency
key lets the same POST be retried without creating a duplicate ledger
event. NULL for every machine source (simulation, generator, camera), so
the unique constraint only constrains human-submitted entries — NULLs are
allowed-multiple in both SQLite and Postgres.

Revision ID: 0006_worker_event_idempotency
Revises: 0005_site_events
Create Date: 2026-06-28
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0006_worker_event_idempotency"
down_revision: Union[str, None] = "0005_site_events"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Batch mode so SQLite (which can't ALTER-ADD a column inside a unique
    # constraint in one step) recreates the table transparently; Postgres
    # runs the equivalent ALTERs directly.
    with op.batch_alter_table("site_events", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("client_event_id", sa.String(length=64), nullable=True)
        )
        batch_op.create_unique_constraint(
            "uq_site_events_client_event_id",
            ["org_id", "project_id", "client_event_id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("site_events", schema=None) as batch_op:
        batch_op.drop_constraint(
            "uq_site_events_client_event_id", type_="unique"
        )
        batch_op.drop_column("client_event_id")
