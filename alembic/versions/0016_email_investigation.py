"""Email investigation — EMAIL subledger, EM* templates, EMAIL_INVESTIGATION pack.

Revision ID: 0016
Revises: 0015
Create Date: 2026-06-09
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


# (code, name, detector, params, subledger, category, weight, tags, description)
NEW_TEMPLATES = [
    ("EM01", "Leakage to Personal Email Accounts", "email_dlp",
     {}, "EMAIL", "FRAUD", 2.0, ["email", "dlp", "exfiltration"],
     "Messages sent to gmail/yahoo/hotmail-style personal accounts, scored "
     "higher when attachments or sensitive keywords are present, and highest "
     "when the recipient looks like the sender's own private address."),
    ("EM02", "Attachments Sent to Personal Accounts", "email_dlp",
     {"require_attachment": True}, "EMAIL", "FRAUD", 2.5,
     ["email", "dlp", "attachments"],
     "Only messages carrying attachments to personal/free email providers — "
     "the strongest data-exfiltration signal."),
    ("EM03", "Sensitive Content Leaving the Organisation", "email_dlp",
     {"require_keyword": True}, "EMAIL", "FRAUD", 2.0,
     ["email", "dlp", "keywords"],
     "Messages to personal accounts whose subject/body/attachment names hit "
     "sensitive keywords (confidential, salary, customer list, password, ...)."),
    ("EM04", "Shared External Contacts Across Employees", "email_cross_custodian",
     {}, "EMAIL", "FRAUD", 2.0, ["email", "collusion", "multi-mailbox"],
     "Needs 2+ imported mailboxes. Flags external personal addresses that "
     "multiple employees communicate with — collusion / shared-conduit signal."),
    ("EM05", "Mailbox Search", "email_search",
     {}, "EMAIL", "ANALYTICAL", 0.5, ["email", "search"],
     "Parameterised search across senders, recipients, keywords, dates, "
     "attachments. The Ask-AI tab fills these parameters from plain English."),
    ("EM06", "After-hours External Email", "email_search",
     {"external_only": True, "after_hours_only": True}, "EMAIL", "ANALYTICAL",
     1.0, ["email", "after-hours"],
     "Messages sent outside 07:00–20:00 to recipients on a different domain "
     "than the sender."),
]

PACK = (
    "EMAIL_INVESTIGATION", "Email Investigation",
    "DLP + collusion sweep over imported PST/mbox mailboxes: leakage to "
    "personal accounts, attachment exfiltration, sensitive keywords, shared "
    "external contacts, after-hours external traffic.",
    "EMAIL", ["EM01", "EM02", "EM03", "EM04", "EM06"],
)


def upgrade() -> None:
    # New enum label must be committed before any row can use it.
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE subledger_type ADD VALUE IF NOT EXISTS 'EMAIL'")

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

    code, name, desc, sub, tpl_codes = PACK
    bind.execute(
        sa.text("""
            INSERT INTO packs
              (id, code, name, description, subledger_type, template_codes,
               is_system, created_at, updated_at)
            VALUES
              (:id, :code, :name, :description, :subledger_type,
               CAST(:template_codes AS varchar[]), TRUE, :now, :now)
            ON CONFLICT (code) DO NOTHING
        """),
        {
            "id": uuid.uuid4(), "code": code, "name": name, "description": desc,
            "subledger_type": sub,
            "template_codes": "{" + ",".join(f'"{c}"' for c in tpl_codes) + "}",
            "now": now,
        },
    )


def downgrade() -> None:
    op.execute(sa.text("DELETE FROM packs WHERE code = 'EMAIL_INVESTIGATION'"))
    codes = [t[0] for t in NEW_TEMPLATES]
    op.execute(
        sa.text("DELETE FROM test_templates WHERE code = ANY(:codes) AND is_system = TRUE")
        .bindparams(sa.bindparam("codes", codes, expanding=True))
    )
    # Postgres cannot drop a single enum label; leaving 'EMAIL' in place is harmless.
