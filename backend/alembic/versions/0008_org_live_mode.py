"""Add orgs.live_mode — drive the dashboard from a LiveSource (device feed)
instead of the simulation.

Revision ID: 0008_org_live_mode
Revises: 0007_devices
Create Date: 2026-06-28
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0008_org_live_mode"
down_revision: Union[str, None] = "0007_devices"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("orgs", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "live_mode", sa.Boolean(), nullable=False, server_default=sa.false()
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("orgs", schema=None) as batch_op:
        batch_op.drop_column("live_mode")
