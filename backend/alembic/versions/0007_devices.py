"""Devices: registry, claim codes, durable ingestion staging, evidence blobs.

Physical producers (cameras, gateways, sensors) authenticate with a bearer
token (hashed at rest) scoped to one (org, project) stream and append into
the ledger. They write to `device_inbound` (cheap, idempotent); a single
per-stream chain-writer folds those into the hash-chained `site_events`,
keeping `seq` gap-free without locking the device-facing path. `site_events`
gains a nullable `device_id` provenance column (NOT part of the hash chain).

Revision ID: 0007_devices
Revises: 0006_worker_event_idempotency
Create Date: 2026-06-28
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0007_devices"
down_revision: Union[str, None] = "0006_worker_event_idempotency"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "devices",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("org_id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=80), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("capabilities", sa.JSON(), nullable=False),
        sa.Column("token_hash", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("agent_version", sa.String(length=64), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("queue_depth", sa.Integer(), nullable=False),
        sa.Column("calibration", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["org_id"], ["orgs.id"], name="fk_devices_org_id_orgs", ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_devices"),
        sa.UniqueConstraint("token_hash", name="uq_devices_token_hash"),
    )
    op.create_index("ix_devices_org_id", "devices", ["org_id"])
    op.create_index("ix_devices_token_hash", "devices", ["token_hash"])

    op.create_table(
        "device_claims",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("org_id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=80), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("token_hash", sa.String(length=128), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["org_id"], ["orgs.id"],
            name="fk_device_claims_org_id_orgs", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["users.id"],
            name="fk_device_claims_created_by_user_id_users", ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_device_claims"),
    )
    op.create_index("ix_device_claims_org_id", "device_claims", ["org_id"])
    op.create_index("ix_device_claims_token_hash", "device_claims", ["token_hash"])

    op.create_table(
        "device_inbound",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("org_id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=80), nullable=False),
        sa.Column("device_id", sa.String(length=36), nullable=False),
        sa.Column("client_event_id", sa.String(length=64), nullable=False),
        sa.Column("envelope", sa.JSON(), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["org_id"], ["orgs.id"],
            name="fk_device_inbound_org_id_orgs", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["device_id"], ["devices.id"],
            name="fk_device_inbound_device_id_devices", ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_device_inbound"),
        sa.UniqueConstraint(
            "org_id", "project_id", "client_event_id",
            name="uq_device_inbound_client_event_id",
        ),
    )
    op.create_index(
        "ix_device_inbound_unprocessed", "device_inbound", ["processed_at"]
    )
    op.create_index(
        "ix_device_inbound_stream", "device_inbound", ["org_id", "project_id"]
    )

    op.create_table(
        "device_blobs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("org_id", sa.String(length=36), nullable=False),
        sa.Column("device_id", sa.String(length=36), nullable=True),
        sa.Column("content_type", sa.String(length=64), nullable=False),
        sa.Column("data", sa.LargeBinary(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["org_id"], ["orgs.id"],
            name="fk_device_blobs_org_id_orgs", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["device_id"], ["devices.id"],
            name="fk_device_blobs_device_id_devices", ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_device_blobs"),
    )
    op.create_index("ix_device_blobs_org_id", "device_blobs", ["org_id"])
    op.create_index("ix_device_blobs_created_at", "device_blobs", ["created_at"])

    # Provenance column on the ledger (nullable; not part of the hash chain).
    with op.batch_alter_table("site_events", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("device_id", sa.String(length=36), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("site_events", schema=None) as batch_op:
        batch_op.drop_column("device_id")
    op.drop_index("ix_device_blobs_created_at", table_name="device_blobs")
    op.drop_index("ix_device_blobs_org_id", table_name="device_blobs")
    op.drop_table("device_blobs")
    op.drop_index("ix_device_inbound_stream", table_name="device_inbound")
    op.drop_index("ix_device_inbound_unprocessed", table_name="device_inbound")
    op.drop_table("device_inbound")
    op.drop_index("ix_device_claims_token_hash", table_name="device_claims")
    op.drop_index("ix_device_claims_org_id", table_name="device_claims")
    op.drop_table("device_claims")
    op.drop_index("ix_devices_token_hash", table_name="devices")
    op.drop_index("ix_devices_org_id", table_name="devices")
    op.drop_table("devices")
