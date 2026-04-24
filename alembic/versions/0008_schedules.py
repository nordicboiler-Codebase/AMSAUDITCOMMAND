"""Scheduled runs + email alert rules.

Revision ID: 0008
Revises: 0007
Create Date: 2026-04-24
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


SCHEDULE_KIND_VALUES = ["PACK", "TEMPLATE"]
SCHEDULE_STATUS_VALUES = ["ACTIVE", "PAUSED"]


def upgrade() -> None:
    kind_enum = postgresql.ENUM(*SCHEDULE_KIND_VALUES, name="schedule_kind", create_type=False)
    status_enum = postgresql.ENUM(*SCHEDULE_STATUS_VALUES, name="schedule_status", create_type=False)
    kind_enum.create(op.get_bind(), checkfirst=True)
    status_enum.create(op.get_bind(), checkfirst=True)

    op.execute("ALTER TYPE audit_action ADD VALUE IF NOT EXISTS 'SCHEDULE_RUN'")
    op.execute("ALTER TYPE audit_action ADD VALUE IF NOT EXISTS 'ALERT_SENT'")

    op.create_table(
        "schedules",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("project_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("dataset_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("datasets.id")),
        sa.Column("kind",
                  postgresql.ENUM(*SCHEDULE_KIND_VALUES, name="schedule_kind", create_type=False),
                  nullable=False),
        sa.Column("pack_code", sa.String(64)),
        sa.Column("template_code", sa.String(32)),
        sa.Column("param_overrides", postgresql.JSONB(), server_default="{}"),
        sa.Column("cron_expr", sa.String(64), nullable=False),
        sa.Column("timezone", sa.String(64), server_default="UTC"),
        sa.Column("status",
                  postgresql.ENUM(*SCHEDULE_STATUS_VALUES, name="schedule_status", create_type=False),
                  server_default="ACTIVE"),
        sa.Column("alert_enabled", sa.Boolean(), server_default=sa.text("FALSE")),
        sa.Column("alert_min_score", sa.Float(), server_default="80"),
        sa.Column("alert_recipients", postgresql.ARRAY(sa.String()), server_default="{}"),
        sa.Column("autoensemble", sa.Boolean(), server_default=sa.text("TRUE")),
        sa.Column("last_run_at", sa.DateTime(timezone=True)),
        sa.Column("last_run_status", sa.String(32)),
        sa.Column("last_run_summary", postgresql.JSONB()),
        sa.Column("next_run_at", sa.DateTime(timezone=True)),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
    )
    op.create_index("ix_schedules_project", "schedules", ["project_id"])
    op.create_index("ix_schedules_status", "schedules", ["status"])
    op.create_index("ix_schedules_next_run", "schedules", ["next_run_at"])

    op.create_table(
        "schedule_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("schedule_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("schedules.id", ondelete="CASCADE"), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("status", sa.String(32), server_default="RUNNING"),
        sa.Column("summary", postgresql.JSONB(), server_default="{}"),
        sa.Column("alert_sent", sa.Boolean(), server_default=sa.text("FALSE")),
        sa.Column("alert_error", sa.Text()),
    )
    op.create_index("ix_schedule_runs_schedule", "schedule_runs", ["schedule_id"])


def downgrade() -> None:
    op.drop_table("schedule_runs")
    op.drop_table("schedules")
    op.execute("DROP TYPE IF EXISTS schedule_kind")
    op.execute("DROP TYPE IF EXISTS schedule_status")
