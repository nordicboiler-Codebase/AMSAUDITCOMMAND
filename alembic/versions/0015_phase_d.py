"""Phase D: ML feedback labels, SCIM external IDs, per-field sensitivity map.

Revision ID: 0015
Revises: 0014
Create Date: 2026-04-24
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ML feedback: when a finding closes, capture the labelled outcome (true positive /
    # false positive) keyed to the record + contributing detectors so we can retrain later.
    op.create_table(
        "finding_labels",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("finding_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("findings.id", ondelete="CASCADE"), nullable=False),
        sa.Column("dataset_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("datasets.id")),
        sa.Column("record_key", sa.String(255)),
        sa.Column("label", sa.String(32), nullable=False),   # TRUE_POSITIVE / FALSE_POSITIVE
        sa.Column("severity", sa.String(16)),
        sa.Column("detector_names", postgresql.ARRAY(sa.String()), server_default="{}"),
        sa.Column("template_codes", postgresql.ARRAY(sa.String()), server_default="{}"),
        sa.Column("risk_score", sa.Float()),
        sa.Column("labelled_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id")),
        sa.Column("labelled_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
    )
    op.create_index("ix_finding_labels_finding", "finding_labels", ["finding_id"])
    op.create_index("ix_finding_labels_record", "finding_labels", ["dataset_id", "record_key"])

    # SCIM external provisioning — link our user to an external IdP user id.
    op.add_column(
        "users",
        sa.Column("external_id", sa.String(255), nullable=True, unique=True),
    )
    op.add_column(
        "users",
        sa.Column("scim_source", sa.String(64), nullable=True),
    )

    # Per-field sensitivity map: stores field_name → classification at the dataset level,
    # so auditors can tag PII/Financial/Confidential columns.
    op.create_table(
        "field_sensitivities",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("dataset_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("datasets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("field_name", sa.String(255), nullable=False),
        sa.Column("classification", sa.String(32), nullable=False),
        sa.Column("notes", sa.Text()),
        sa.Column("set_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id")),
        sa.Column("set_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.UniqueConstraint("dataset_id", "field_name", name="uq_field_sensitivity"),
    )
    op.create_index("ix_field_sens_dataset", "field_sensitivities", ["dataset_id"])


def downgrade() -> None:
    op.drop_table("field_sensitivities")
    op.drop_column("users", "scim_source")
    op.drop_column("users", "external_id")
    op.drop_table("finding_labels")
