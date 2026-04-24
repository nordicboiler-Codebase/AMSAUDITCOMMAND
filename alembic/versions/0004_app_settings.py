"""Add app_settings table for runtime configuration (SSO, email, etc.).

Revision ID: 0004
Revises: 0003
Create Date: 2026-04-24
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "app_settings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("category", sa.String(64), nullable=False),
        sa.Column("key", sa.String(128), nullable=False),
        sa.Column("value_json", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("is_secret", sa.Boolean(), server_default=sa.text("FALSE")),
        sa.Column("updated_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.UniqueConstraint("category", "key", name="uq_app_settings_category_key"),
    )
    op.create_index("ix_app_settings_category", "app_settings", ["category"])


def downgrade() -> None:
    op.drop_table("app_settings")
