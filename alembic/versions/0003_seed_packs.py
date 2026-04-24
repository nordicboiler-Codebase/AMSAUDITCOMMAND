"""Seed 10 system domain packs.

Revision ID: 0003
Revises: 0002
Create Date: 2026-04-24
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def _ap_codes() -> list[str]:
    return [f"AP{i:02d}" for i in range(1, 26)]


def _ar_codes() -> list[str]:
    return [f"AR{i:02d}" for i in range(1, 16)]


def _gl_codes() -> list[str]:
    return [f"GL{i:02d}" for i in range(1, 21)]


def _pr_codes() -> list[str]:
    return [f"PR{i:02d}" for i in range(1, 16)]


def _fa_codes() -> list[str]:
    return [f"FA{i:02d}" for i in range(1, 11)]


def _in_codes() -> list[str]:
    return [f"IN{i:02d}" for i in range(1, 9)]


def _bk_codes() -> list[str]:
    return [f"BK{i:02d}" for i in range(1, 9)]


def _po_codes() -> list[str]:
    return [f"PO{i:02d}" for i in range(1, 9)]


def _te_codes() -> list[str]:
    return [f"TE{i:02d}" for i in range(1, 8)]


def _sl_codes() -> list[str]:
    return [f"SL{i:02d}" for i in range(1, 6)]


PACKS = [
    ("AP_STANDARD", "Accounts Payable Standard Pack", "ACCOUNTS_PAYABLE",
     "Core AP fraud + quality tests for payments and invoices",
     _ap_codes() + ["U01", "U02", "U10", "U11"]),
    ("AR_STANDARD", "Accounts Receivable Standard Pack", "ACCOUNTS_RECEIVABLE",
     "Core AR aging, credit, and revenue tests",
     _ar_codes() + ["U01", "U10"]),
    ("GL_STANDARD", "General Ledger Standard Pack", "GENERAL_LEDGER",
     "Manual JE, period-end, and account activity tests",
     _gl_codes() + ["U10", "U11", "U12"]),
    ("PAYROLL_STANDARD", "Payroll Standard Pack", "PAYROLL",
     "Ghost employee, duplicate bank, overtime and bonus tests",
     _pr_codes() + ["U01", "U06", "U07"]),
    ("FA_STANDARD", "Fixed Assets Standard Pack", "FIXED_ASSETS",
     "Asset master, depreciation, disposal integrity tests",
     _fa_codes() + ["U01", "U10"]),
    ("INVENTORY_STANDARD", "Inventory Standard Pack", "INVENTORY",
     "Inventory aging, cycle count, and valuation tests",
     _in_codes() + ["U01"]),
    ("BANK_RECON", "Bank Reconciliation Pack", "BANK",
     "Uncleared items, cheque sequence, and deposits in transit",
     _bk_codes() + ["U10"]),
    ("PROCUREMENT_STANDARD", "Procurement Standard Pack", "PROCUREMENT",
     "Three-way match, split POs, and vendor conflict tests",
     _po_codes() + ["AP17", "AP18"]),
    ("TE_STANDARD", "Travel & Expense Standard Pack", "TE",
     "Expense policy, duplicate, and outlier tests",
     _te_codes()),
    ("REVENUE_STANDARD", "Revenue Standard Pack", "SALES",
     "Revenue cutoff, discount, and sales-shipment tests",
     _sl_codes() + ["AR01", "AR07"]),
]


def upgrade() -> None:
    packs_table = sa.table(
        "packs",
        sa.column("id", postgresql.UUID(as_uuid=True)),
        sa.column("code", sa.String),
        sa.column("name", sa.String),
        sa.column("description", sa.Text),
        sa.column("subledger_type", sa.String),
        sa.column("template_codes", postgresql.ARRAY(sa.String)),
        sa.column("is_system", sa.Boolean),
        sa.column("created_at", sa.DateTime(timezone=True)),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    now = datetime.now(timezone.utc)
    rows = []
    for code, name, subledger, description, template_codes in PACKS:
        rows.append({
            "id": uuid.uuid4(),
            "code": code,
            "name": name,
            "description": description,
            "subledger_type": subledger,
            "template_codes": template_codes,
            "is_system": True,
            "created_at": now,
            "updated_at": now,
        })
    op.bulk_insert(packs_table, rows)


def downgrade() -> None:
    codes = [p[0] for p in PACKS]
    op.execute(
        sa.text("DELETE FROM packs WHERE code = ANY(:codes) AND is_system = TRUE")
        .bindparams(sa.bindparam("codes", codes, expanding=True))
    )
