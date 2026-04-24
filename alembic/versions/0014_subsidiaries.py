"""Group-audit semantics: first-class Subsidiary / Entity.

Revision ID: 0014
Revises: 0013
Create Date: 2026-04-24
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "subsidiaries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("code", sa.String(32), unique=True, nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("country", sa.String(4)),
        sa.Column("industry", sa.String(64)),
        sa.Column("risk_rating", sa.String(16)),   # LOW / MEDIUM / HIGH / CRITICAL
        sa.Column("parent_code", sa.String(32)),
        sa.Column("segment", sa.String(64)),
        sa.Column("logo_data_uri", sa.Text()),
        sa.Column("brand_primary", sa.String(16), server_default="#0b2a4a"),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("TRUE")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
    )
    op.create_index("ix_subs_code", "subsidiaries", ["code"])

    op.add_column(
        "projects",
        sa.Column("subsidiary_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("subsidiaries.id"), nullable=True),
    )
    op.create_index("ix_projects_subsidiary_id", "projects", ["subsidiary_id"])


def downgrade() -> None:
    op.drop_column("projects", "subsidiary_id")
    op.drop_table("subsidiaries")
