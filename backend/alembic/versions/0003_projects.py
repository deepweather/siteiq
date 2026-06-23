"""Projects + project_versions + orgs.active_project_version_id.

Introduces the persisted, content-addressed `ProjectDocument` storage
model that Phase 1 of the editor + multi-level plan depends on.

Revision ID: 0003_projects
Revises: 0002_orgs_active_project
Create Date: 2026-06-21
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0003_projects"
down_revision: Union[str, None] = "0002_orgs_active_project"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "projects",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("org_id", sa.String(length=36), nullable=True),
        sa.Column("slug", sa.String(length=80), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("type", sa.String(length=64), nullable=False),
        sa.Column("discipline", sa.String(length=32), nullable=False),
        sa.Column("visibility", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("current_version_id", sa.String(length=64), nullable=True),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["org_id"], ["orgs.id"],
            name="fk_projects_org_id_orgs", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["users.id"],
            name="fk_projects_created_by_user_id_users", ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_projects"),
        sa.UniqueConstraint("org_id", "slug", name="uq_projects_org_slug"),
    )
    op.create_index("ix_projects_org_id", "projects", ["org_id"], unique=False)

    op.create_table(
        "project_versions",
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("parent_version_id", sa.String(length=64), nullable=True),
        sa.Column("document", sa.JSON(), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("created_by_user_id", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["project_id"], ["projects.id"],
            name="fk_project_versions_project_id_projects",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["users.id"],
            name="fk_project_versions_created_by_user_id_users",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_project_versions"),
    )
    op.create_index(
        "ix_project_versions_project_id_created_at",
        "project_versions",
        ["project_id", "created_at"],
        unique=False,
    )

    with op.batch_alter_table("orgs") as batch:
        batch.add_column(
            sa.Column("active_project_version_id", sa.String(length=64), nullable=True)
        )


def downgrade() -> None:
    with op.batch_alter_table("orgs") as batch:
        batch.drop_column("active_project_version_id")
    op.drop_index("ix_project_versions_project_id_created_at", table_name="project_versions")
    op.drop_table("project_versions")
    op.drop_index("ix_projects_org_id", table_name="projects")
    op.drop_table("projects")
