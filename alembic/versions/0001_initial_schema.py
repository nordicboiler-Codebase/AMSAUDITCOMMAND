"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-04-24
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


SUBLEDGER_VALUES = [
    "GENERAL_LEDGER", "ACCOUNTS_PAYABLE", "ACCOUNTS_RECEIVABLE", "PAYROLL",
    "FIXED_ASSETS", "INVENTORY", "BANK", "PROCUREMENT", "TE", "SALES", "OTHER",
]
USER_ROLE_VALUES = ["ADMIN", "AUDITOR", "VIEWER"]
TEMPLATE_CATEGORY_VALUES = ["DATA_QUALITY", "FRAUD", "COMPLIANCE", "ANALYTICAL"]
TEMPLATE_VISIBILITY_VALUES = ["PRIVATE", "PROJECT", "SHARED"]
AUDIT_ACTION_VALUES = [
    "LOGIN", "LOGOUT", "IMPORT", "TEST_RUN", "PACK_RUN", "ENSEMBLE_RUN",
    "EXPORT", "NLQ", "TEMPLATE_CREATE", "TEMPLATE_UPDATE", "TEMPLATE_FORK",
    "TEMPLATE_PUBLISH",
]
RUN_STATUS_VALUES = ["PENDING", "RUNNING", "COMPLETED", "FAILED"]


def upgrade() -> None:
    subledger = postgresql.ENUM(*SUBLEDGER_VALUES, name="subledger_type", create_type=False)
    user_role = postgresql.ENUM(*USER_ROLE_VALUES, name="user_role", create_type=False)
    template_category = postgresql.ENUM(*TEMPLATE_CATEGORY_VALUES, name="template_category", create_type=False)
    template_visibility = postgresql.ENUM(*TEMPLATE_VISIBILITY_VALUES, name="template_visibility", create_type=False)
    audit_action = postgresql.ENUM(*AUDIT_ACTION_VALUES, name="audit_action", create_type=False)
    run_status = postgresql.ENUM(*RUN_STATUS_VALUES, name="run_status", create_type=False)

    for e in (subledger, user_role, template_category, template_visibility, audit_action, run_status):
        e.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("username", sa.String(64), unique=True, nullable=False),
        sa.Column("email", sa.String(255), unique=True, nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("role", sa.Enum(*USER_ROLE_VALUES, name="user_role", create_type=False), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("TRUE")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
    )
    op.create_index("ix_users_username", "users", ["username"])

    op.create_table(
        "projects",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("subsidiary_code", sa.String(50)),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id")),
        sa.Column("status", sa.String(32), server_default="ACTIVE"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
    )
    op.create_index("ix_projects_name", "projects", ["name"])
    op.create_index("ix_projects_subsidiary_code", "projects", ["subsidiary_code"])

    op.create_table(
        "datasets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id")),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("source_filename", sa.String(512), nullable=False),
        sa.Column("source_hash_sha256", sa.String(64), nullable=False),
        sa.Column("record_count", sa.Integer(), server_default="0"),
        sa.Column("control_totals", postgresql.JSONB(), server_default="{}"),
        sa.Column("schema_json", postgresql.JSONB(), server_default="{}"),
        sa.Column("subledger_type", sa.Enum(*SUBLEDGER_VALUES, name="subledger_type", create_type=False), nullable=False),
        sa.Column("parquet_path", sa.String(1024), nullable=False),
        sa.Column("imported_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id")),
        sa.Column("imported_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("description", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
    )
    op.create_index("ix_datasets_source_hash", "datasets", ["source_hash_sha256"])
    op.create_index("ix_datasets_subledger_type", "datasets", ["subledger_type"])

    op.create_table(
        "test_templates",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("code", sa.String(32), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("detector_name", sa.String(100), nullable=False),
        sa.Column("default_params", postgresql.JSONB(), nullable=False, server_default="{}"),
        sa.Column("subledger_type", sa.Enum(*SUBLEDGER_VALUES, name="subledger_type", create_type=False)),
        sa.Column("category", sa.Enum(*TEMPLATE_CATEGORY_VALUES, name="template_category", create_type=False)),
        sa.Column("default_weight", sa.Float(), server_default="1.0"),
        sa.Column("tags", postgresql.ARRAY(sa.String()), server_default="{}"),
        sa.Column("is_system", sa.Boolean(), server_default=sa.text("FALSE")),
        sa.Column("version", sa.Integer(), server_default="1"),
        sa.Column(
            "visibility",
            sa.Enum(*TEMPLATE_VISIBILITY_VALUES, name="template_visibility", create_type=False),
            server_default="SHARED",
        ),
        sa.Column("parent_template_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("test_templates.id")),
        sa.Column("owner_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id")),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.UniqueConstraint("code", "version", name="uq_template_code_version"),
    )
    op.create_index("ix_templates_code", "test_templates", ["code"])
    op.create_index("ix_templates_detector", "test_templates", ["detector_name"])
    op.create_index("ix_templates_subledger", "test_templates", ["subledger_type"])
    op.create_index("ix_templates_tags", "test_templates", ["tags"], postgresql_using="gin")

    op.create_table(
        "packs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("code", sa.String(64), unique=True, nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("subledger_type", sa.Enum(*SUBLEDGER_VALUES, name="subledger_type", create_type=False)),
        sa.Column("template_codes", postgresql.ARRAY(sa.String()), server_default="{}"),
        sa.Column("is_system", sa.Boolean(), server_default=sa.text("TRUE")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
    )
    op.create_index("ix_packs_code", "packs", ["code"])

    op.create_table(
        "pack_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("dataset_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("datasets.id")),
        sa.Column("pack_code", sa.String(64), nullable=False),
        sa.Column("run_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id")),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("status", sa.Enum(*RUN_STATUS_VALUES, name="run_status", create_type=False), server_default="PENDING"),
        sa.Column("template_overrides", postgresql.JSONB(), server_default="{}"),
        sa.Column("summary", postgresql.JSONB(), server_default="{}"),
        sa.Column("ensemble_run_id", postgresql.UUID(as_uuid=True)),
    )

    op.create_table(
        "test_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("dataset_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("datasets.id")),
        sa.Column("template_code", sa.String(32)),
        sa.Column("detector_name", sa.String(100), nullable=False),
        sa.Column("params", postgresql.JSONB(), server_default="{}"),
        sa.Column("run_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id")),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("status", sa.Enum(*RUN_STATUS_VALUES, name="run_status", create_type=False), server_default="PENDING"),
        sa.Column("input_hash", sa.String(64)),
        sa.Column("output_hash", sa.String(64)),
        sa.Column("output_parquet_path", sa.String(1024)),
        sa.Column("findings_count", sa.Integer(), server_default="0"),
        sa.Column("summary", postgresql.JSONB(), server_default="{}"),
        sa.Column("pack_run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("pack_runs.id")),
        sa.Column("error_message", sa.Text()),
    )
    op.create_index("ix_test_runs_dataset", "test_runs", ["dataset_id"])
    op.create_index("ix_test_runs_template", "test_runs", ["template_code"])

    op.create_table(
        "ensemble_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("dataset_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("datasets.id")),
        sa.Column("test_run_ids", postgresql.ARRAY(sa.String()), server_default="{}"),
        sa.Column("run_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id")),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("status", sa.Enum(*RUN_STATUS_VALUES, name="run_status", create_type=False), server_default="PENDING"),
        sa.Column("summary", postgresql.JSONB(), server_default="{}"),
    )

    op.create_table(
        "risk_scores",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("dataset_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("datasets.id")),
        sa.Column("ensemble_run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("ensemble_runs.id")),
        sa.Column("record_key", sa.String(255), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("contributing_detectors", postgresql.JSONB(), server_default="[]"),
        sa.Column("computed_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()")),
        sa.CheckConstraint("score >= 0 AND score <= 100", name="ck_score_range"),
    )
    op.create_index("ix_risk_dataset", "risk_scores", ["dataset_id"])
    op.create_index("ix_risk_ensemble", "risk_scores", ["ensemble_run_id"])
    op.create_index("ix_risk_key", "risk_scores", ["record_key"])
    op.create_index("ix_risk_score", "risk_scores", ["score"])

    op.create_table(
        "audit_log",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("NOW()")),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id")),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("projects.id")),
        sa.Column("action", sa.Enum(*AUDIT_ACTION_VALUES, name="audit_action", create_type=False), nullable=False),
        sa.Column("entity_type", sa.String(64), nullable=False),
        sa.Column("entity_id", sa.String(64)),
        sa.Column("details", postgresql.JSONB(), server_default="{}"),
        sa.Column("previous_hash", sa.String(64), nullable=False),
        sa.Column("current_hash", sa.String(64), unique=True, nullable=False),
    )
    op.create_index("ix_audit_log_timestamp", "audit_log", ["timestamp"])
    op.create_index("ix_audit_log_project", "audit_log", ["project_id"])

    op.execute(
        """
        CREATE OR REPLACE FUNCTION prevent_audit_log_mutation()
        RETURNS TRIGGER AS $$
        BEGIN
            RAISE EXCEPTION 'audit_log is append-only: % is not permitted', TG_OP;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_audit_log_no_update
        BEFORE UPDATE ON audit_log
        FOR EACH ROW EXECUTE FUNCTION prevent_audit_log_mutation();
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_audit_log_no_delete
        BEFORE DELETE ON audit_log
        FOR EACH ROW EXECUTE FUNCTION prevent_audit_log_mutation();
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_audit_log_no_delete ON audit_log")
    op.execute("DROP TRIGGER IF EXISTS trg_audit_log_no_update ON audit_log")
    op.execute("DROP FUNCTION IF EXISTS prevent_audit_log_mutation()")

    op.drop_table("audit_log")
    op.drop_table("risk_scores")
    op.drop_table("ensemble_runs")
    op.drop_table("test_runs")
    op.drop_table("pack_runs")
    op.drop_table("packs")
    op.drop_table("test_templates")
    op.drop_table("datasets")
    op.drop_table("projects")
    op.drop_table("users")

    for name in ("run_status", "audit_action", "template_visibility", "template_category", "user_role", "subledger_type"):
        op.execute(f"DROP TYPE IF EXISTS {name}")
