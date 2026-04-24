"""Project-level access control: project_members join table.

Revision ID: 0006
Revises: 0005
Create Date: 2026-04-24
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


PROJECT_ROLE_VALUES = ["OWNER", "EDITOR", "REVIEWER", "VIEWER"]


def upgrade() -> None:
    project_role = postgresql.ENUM(*PROJECT_ROLE_VALUES, name="project_role", create_type=False)
    project_role.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "project_members",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("project_role",
                  postgresql.ENUM(*PROJECT_ROLE_VALUES, name="project_role", create_type=False),
                  nullable=False),
        sa.Column("added_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id")),
        sa.Column("added_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.UniqueConstraint("project_id", "user_id", name="uq_project_user"),
    )
    op.create_index("ix_project_members_project", "project_members", ["project_id"])
    op.create_index("ix_project_members_user", "project_members", ["user_id"])

    # Back-fill existing project owners as OWNER members (and ADMINs get OWNER on all projects).
    op.execute(
        """
        INSERT INTO project_members (id, project_id, user_id, project_role, added_by, added_at)
        SELECT gen_random_uuid(), p.id, p.owner_id, 'OWNER', p.owner_id, NOW()
        FROM projects p
        WHERE p.owner_id IS NOT NULL
        ON CONFLICT (project_id, user_id) DO NOTHING
        """
    )


def downgrade() -> None:
    op.drop_table("project_members")
    op.execute("DROP TYPE IF EXISTS project_role")
