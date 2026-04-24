"""Continuous monitoring: project-level watchers that auto-run on new dataset arrivals.

Revision ID: 0011
Revises: 0010
Create Date: 2026-04-24
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE audit_action ADD VALUE IF NOT EXISTS 'MONITOR_TRIGGERED'")

    op.create_table(
        "monitors",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("subledger_type", sa.String(32), nullable=False),
        sa.Column("pack_code", sa.String(64), nullable=False),
        sa.Column("auto_ensemble", sa.Boolean(), server_default=sa.text("TRUE")),
        sa.Column("auto_create_finding_min_score", sa.Float(), server_default="90"),
        sa.Column("alert_recipients", postgresql.ARRAY(sa.String()), server_default="{}"),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("TRUE")),
        sa.Column("last_triggered_at", sa.DateTime(timezone=True)),
        sa.Column("last_dataset_id", postgresql.UUID(as_uuid=True)),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
    )
    op.create_index("ix_monitors_project", "monitors", ["project_id"])
    op.create_index("ix_monitors_subledger", "monitors", ["subledger_type"])


def downgrade() -> None:
    op.drop_table("monitors")
