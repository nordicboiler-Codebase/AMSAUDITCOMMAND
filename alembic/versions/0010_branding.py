"""Per-project branding for PDF reports.

Revision ID: 0010
Revises: 0009
Create Date: 2026-04-24
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("projects", sa.Column("logo_data_uri", sa.Text(), nullable=True))
    op.add_column("projects", sa.Column("brand_primary", sa.String(16),
                                        nullable=False, server_default="#0b2a4a"))
    op.add_column("projects", sa.Column("brand_accent", sa.String(16),
                                        nullable=False, server_default="#15a8a8"))
    op.add_column("projects", sa.Column("legal_footer", sa.Text(), nullable=True))
    op.add_column("projects", sa.Column("report_language", sa.String(8),
                                        nullable=False, server_default="en"))


def downgrade() -> None:
    op.drop_column("projects", "report_language")
    op.drop_column("projects", "legal_footer")
    op.drop_column("projects", "brand_accent")
    op.drop_column("projects", "brand_primary")
    op.drop_column("projects", "logo_data_uri")
