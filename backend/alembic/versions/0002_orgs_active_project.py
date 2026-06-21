"""Add orgs.active_project_id.

Persists each org's chosen PROJECT_TEMPLATES key so a backend restart
doesn't dump every workspace back to the default. SQLite + Postgres
both support nullable column adds without a rewrite, so this is safe
to run online.

Revision ID: 0002_orgs_active_project
Revises: 0001_init_auth
Create Date: 2026-06-21
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0002_orgs_active_project"
down_revision: Union[str, None] = "0001_init_auth"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("orgs") as batch:
        batch.add_column(sa.Column("active_project_id", sa.String(length=80), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("orgs") as batch:
        batch.drop_column("active_project_id")
