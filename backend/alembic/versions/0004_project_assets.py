"""Add project_assets table for binary blobs (level background images).

Originally toyed with using the filesystem, but that fights the
"single-row-cascade on org delete" + "content-addressed everything"
shape the rest of the editor uses. A small `LargeBinary` row inside the
existing DB cascades cleanly via the project FK and dedupes naturally
via the SHA-256 hash recorded on each row.

Revision ID: 0004_project_assets
Revises: 0003_projects
Create Date: 2026-06-22
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0004_project_assets"
down_revision: Union[str, None] = "0003_projects"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "project_assets",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("content_type", sa.String(length=64), nullable=False),
        sa.Column("data", sa.LargeBinary(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"],
            name="fk_project_assets_project_id_projects",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_project_assets"),
    )
    op.create_index(
        "ix_project_assets_project_id", "project_assets", ["project_id"], unique=False,
    )
    op.create_index(
        "ix_project_assets_content_hash", "project_assets", ["content_hash"], unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_project_assets_content_hash", table_name="project_assets")
    op.drop_index("ix_project_assets_project_id", table_name="project_assets")
    op.drop_table("project_assets")
