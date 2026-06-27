"""Add site_events table — the append-only operational system of record.

Every action, material, worker and piece on the site becomes one immutable,
hash-chained, bitemporal event. Current state and costs are projections
(folds) over these rows. The simulation, demo generator, manual capture,
and a future camera LiveSource all append through the same ledger service.

Revision ID: 0005_site_events
Revises: 0004_project_assets
Create Date: 2026-06-27
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0005_site_events"
down_revision: Union[str, None] = "0004_project_assets"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "site_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("org_id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=80), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("subject_type", sa.String(length=32), nullable=False),
        sa.Column("subject_id", sa.String(length=80), nullable=False),
        sa.Column("kind", sa.String(length=64), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("evidence_ref", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("supersedes_event_id", sa.String(length=36), nullable=True),
        sa.Column("actor_user_id", sa.String(length=36), nullable=True),
        sa.Column("prev_hash", sa.String(length=64), nullable=False),
        sa.Column("hash", sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(
            ["org_id"], ["orgs.id"],
            name="fk_site_events_org_id_orgs", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["actor_user_id"], ["users.id"],
            name="fk_site_events_actor_user_id_users", ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_site_events"),
        sa.UniqueConstraint(
            "org_id", "project_id", "seq", name="uq_site_events_stream_seq"
        ),
    )
    op.create_index(
        "ix_site_events_stream_occurred",
        "site_events",
        ["org_id", "project_id", "occurred_at"],
        unique=False,
    )
    op.create_index(
        "ix_site_events_stream_status",
        "site_events",
        ["org_id", "project_id", "status"],
        unique=False,
    )
    op.create_index(
        "ix_site_events_subject",
        "site_events",
        ["subject_type", "subject_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_site_events_subject", table_name="site_events")
    op.drop_index("ix_site_events_stream_status", table_name="site_events")
    op.drop_index("ix_site_events_stream_occurred", table_name="site_events")
    op.drop_table("site_events")
