"""Findings Register + maker-checker workflow.

Revision ID: 0007
Revises: 0006
Create Date: 2026-04-24
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


FINDING_STATUS_VALUES = [
    "DRAFT", "UNDER_REVIEW", "CONFIRMED", "FALSE_POSITIVE",
    "REMEDIATED", "ACCEPTED_RISK", "CARRIED_FORWARD",
]
FINDING_SEVERITY_VALUES = ["LOW", "MEDIUM", "HIGH", "CRITICAL"]


def upgrade() -> None:
    status_enum = postgresql.ENUM(*FINDING_STATUS_VALUES, name="finding_status", create_type=False)
    severity_enum = postgresql.ENUM(*FINDING_SEVERITY_VALUES, name="finding_severity", create_type=False)
    status_enum.create(op.get_bind(), checkfirst=True)
    severity_enum.create(op.get_bind(), checkfirst=True)

    op.execute("ALTER TYPE audit_action ADD VALUE IF NOT EXISTS 'FINDING_CREATE'")
    op.execute("ALTER TYPE audit_action ADD VALUE IF NOT EXISTS 'FINDING_UPDATE'")
    op.execute("ALTER TYPE audit_action ADD VALUE IF NOT EXISTS 'FINDING_REVIEW'")
    op.execute("ALTER TYPE audit_action ADD VALUE IF NOT EXISTS 'FINDING_CLOSE'")

    op.create_table(
        "findings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("code", sa.String(32), unique=True, nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("project_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("dataset_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("datasets.id")),
        sa.Column("ensemble_run_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("ensemble_runs.id")),
        sa.Column("record_keys", postgresql.ARRAY(sa.String()), server_default="{}"),
        sa.Column("risk_score", sa.Float()),
        sa.Column("severity",
                  postgresql.ENUM(*FINDING_SEVERITY_VALUES, name="finding_severity", create_type=False),
                  server_default="MEDIUM"),
        sa.Column("status",
                  postgresql.ENUM(*FINDING_STATUS_VALUES, name="finding_status", create_type=False),
                  server_default="DRAFT"),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id")),
        sa.Column("reviewer_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id")),
        sa.Column("due_date", sa.Date()),
        sa.Column("management_response", sa.Text()),
        sa.Column("remediation_plan", sa.Text()),
        sa.Column("tags", postgresql.ARRAY(sa.String()), server_default="{}"),
        sa.Column("linked_template_codes", postgresql.ARRAY(sa.String()), server_default="{}"),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id")),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        sa.Column("closed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
    )
    op.create_index("ix_findings_project", "findings", ["project_id"])
    op.create_index("ix_findings_status", "findings", ["status"])
    op.create_index("ix_findings_severity", "findings", ["severity"])

    op.create_table(
        "finding_comments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("finding_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("findings.id", ondelete="CASCADE"), nullable=False),
        sa.Column("author_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id")),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("is_review_signoff", sa.Boolean(), server_default=sa.text("FALSE")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
    )
    op.create_index("ix_finding_comments_finding", "finding_comments", ["finding_id"])


def downgrade() -> None:
    op.drop_table("finding_comments")
    op.drop_table("findings")
    op.execute("DROP TYPE IF EXISTS finding_status")
    op.execute("DROP TYPE IF EXISTS finding_severity")
