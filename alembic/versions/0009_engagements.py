"""Engagement workspace: group a period's work (datasets + packs + findings + reviewer).

Revision ID: 0009
Revises: 0008
Create Date: 2026-04-24
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None


ENGAGEMENT_STATUS_VALUES = [
    "PLANNING", "IN_PROGRESS", "REVIEW", "FINALISED", "ARCHIVED",
]


def upgrade() -> None:
    status_enum = postgresql.ENUM(*ENGAGEMENT_STATUS_VALUES, name="engagement_status", create_type=False)
    status_enum.create(op.get_bind(), checkfirst=True)

    op.execute("ALTER TYPE audit_action ADD VALUE IF NOT EXISTS 'ENGAGEMENT_FINALISE'")

    op.create_table(
        "engagements",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("code", sa.String(32), unique=True, nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("period_start", sa.Date()),
        sa.Column("period_end", sa.Date()),
        sa.Column("scope", sa.Text()),
        sa.Column("status",
                  postgresql.ENUM(*ENGAGEMENT_STATUS_VALUES, name="engagement_status", create_type=False),
                  server_default="PLANNING"),
        sa.Column("lead_auditor_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id")),
        sa.Column("reviewer_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id")),
        sa.Column("dataset_ids", postgresql.ARRAY(postgresql.UUID(as_uuid=True)), server_default="{}"),
        sa.Column("pack_run_ids", postgresql.ARRAY(postgresql.UUID(as_uuid=True)), server_default="{}"),
        sa.Column("finding_ids", postgresql.ARRAY(postgresql.UUID(as_uuid=True)), server_default="{}"),
        sa.Column("executive_summary", sa.Text()),
        sa.Column("finalised_at", sa.DateTime(timezone=True)),
        sa.Column("finalised_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id")),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
    )
    op.create_index("ix_engagements_project", "engagements", ["project_id"])
    op.create_index("ix_engagements_status", "engagements", ["status"])


def downgrade() -> None:
    op.drop_table("engagements")
    op.execute("DROP TYPE IF EXISTS engagement_status")
