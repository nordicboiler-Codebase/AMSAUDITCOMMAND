"""Seed 143 system test templates.

Revision ID: 0002
Revises: 0001
Create Date: 2026-04-24
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from backend.templates.seed_data import TEMPLATES

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    test_templates = sa.table(
        "test_templates",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("code", sa.String),
        sa.column("name", sa.String),
        sa.column("description", sa.Text),
        sa.column("detector_name", sa.String),
        sa.column("default_params", postgresql.JSONB),
        sa.column("subledger_type", sa.String),
        sa.column("category", sa.String),
        sa.column("default_weight", sa.Float),
        sa.column("tags", postgresql.ARRAY(sa.String)),
        sa.column("is_system", sa.Boolean),
        sa.column("version", sa.Integer),
        sa.column("visibility", sa.String),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )

    now = datetime.now(timezone.utc)
    rows = []
    for (code, name, detector, params, subledger, category, weight, tags, description) in TEMPLATES:
        rows.append({
            "id": uuid.uuid4(),
            "code": code,
            "name": name,
            "description": description,
            "detector_name": detector,
            "default_params": params,
            "subledger_type": subledger,
            "category": category,
            "default_weight": weight,
            "tags": list(tags),
            "is_system": True,
            "version": 1,
            "visibility": "SHARED",
            "created_at": now,
            "updated_at": now,
        })

    op.bulk_insert(test_templates, rows)


def downgrade() -> None:
    codes = [t[0] for t in TEMPLATES]
    op.execute(
        sa.text("DELETE FROM test_templates WHERE code = ANY(:codes) AND is_system = TRUE")
        .bindparams(sa.bindparam("codes", codes, expanding=True))
    )
