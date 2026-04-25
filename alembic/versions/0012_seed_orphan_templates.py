"""Seed templates for the 5 detectors previously without a named test.

Revision ID: 0012
Revises: 0011
Create Date: 2026-04-24
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


NEW_TEMPLATES = [
    ("AN08", "Sequence Order Violations", "sequence_order",
     {"key_field": "invoice_no", "ascending": True}, None, "ANALYTICAL", 0.5,
     ["sequence"], "Records out of expected ascending order"),
    ("AN09", "Stratify Amount Bands", "stratify",
     {"field": "amount", "auto_intervals": 10}, None, "ANALYTICAL", 0.2,
     ["stratify"], "Bucket amounts into 10 equal-width bands"),
    ("AN10", "Histogram of Amount", "histogram",
     {"field": "amount", "bins": 20}, None, "ANALYTICAL", 0.2,
     ["histogram"], "Frequency distribution of amount field"),
    ("AN11", "Cross-Tabulate Vendor vs GL Account", "cross_tabulate",
     {"row_field": "vendor_id", "column_field": "gl_account"}, None,
     "ANALYTICAL", 0.2, ["pivot"], "Two-field pivot of vendor against GL account"),
    ("U16", "Unusual Text Patterns in Description", "text_anomaly",
     {"text_field": "description", "checks": ["all_caps", "too_short", "excessive_symbols"]},
     None, "DATA_QUALITY", 0.5, ["quality", "text"],
     "Flag rows with all-caps, extremely short, or symbol-heavy text"),
]


def upgrade() -> None:
    # NOTE: these template codes were later folded into seed_data.py (and so are
    # already inserted by migration 0002). On a fresh DB, this migration would
    # duplicate them. Use ON CONFLICT DO NOTHING so this migration is idempotent
    # whether or not 0002 already inserted them.
    import json
    import uuid
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)
    bind = op.get_bind()
    for (code, name, det, params, sub, cat, w, tags, desc) in NEW_TEMPLATES:
        bind.execute(
            sa.text("""
                INSERT INTO test_templates
                  (id, code, name, description, detector_name, default_params,
                   subledger_type, category, default_weight, tags, is_system, version,
                   visibility, created_at, updated_at)
                VALUES
                  (:id, :code, :name, :description, :detector_name,
                   CAST(:default_params AS jsonb),
                   :subledger_type, :category, :default_weight,
                   CAST(:tags AS varchar[]), TRUE, 1, 'SHARED', :now, :now)
                ON CONFLICT (code, version) DO NOTHING
            """),
            {
                "id": uuid.uuid4(),
                "code": code, "name": name, "description": desc,
                "detector_name": det, "default_params": json.dumps(params),
                "subledger_type": sub, "category": cat, "default_weight": w,
                "tags": "{" + ",".join(f'"{t}"' for t in tags) + "}",
                "now": now,
            },
        )
    return

    # Old code path retained below (unreachable) for downgrade reference.
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
    op.bulk_insert(test_templates, [
        {
            "id": uuid.uuid4(), "code": c, "name": n, "description": desc,
            "detector_name": det, "default_params": params,
            "subledger_type": sub, "category": cat, "default_weight": w,
            "tags": list(tags), "is_system": True, "version": 1,
            "visibility": "SHARED", "created_at": now, "updated_at": now,
        }
        for (c, n, det, params, sub, cat, w, tags, desc) in NEW_TEMPLATES
    ])


def downgrade() -> None:
    codes = [t[0] for t in NEW_TEMPLATES]
    op.execute(
        sa.text("DELETE FROM test_templates WHERE code = ANY(:codes) AND is_system = TRUE")
        .bindparams(sa.bindparam("codes", codes, expanding=True))
    )
