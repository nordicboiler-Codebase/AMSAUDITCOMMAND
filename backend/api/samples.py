"""Sample CSV downloads — exposes the files under ./samples/ as a small read-only API.

Auditors get a list at GET /api/samples and individual files at GET /api/samples/{name}.
Each sample has planted fraud signals so the matching pack lights up immediately.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Response

from backend.core.security import get_current_user
from backend.models import User

router = APIRouter()

SAMPLES_DIR = Path(__file__).resolve().parents[2] / "samples"

DESCRIPTIONS: dict[str, dict] = {
    "accounts_payable_sample.csv": {
        "subledger_type": "ACCOUNTS_PAYABLE",
        "title": "Accounts Payable",
        "description": "5 rows — duplicate payment, threshold avoidance, late-night reversal",
        "suggested_pack": "AP_STANDARD",
    },
    "accounts_receivable_sample.csv": {
        "subledger_type": "ACCOUNTS_RECEIVABLE",
        "title": "Accounts Receivable",
        "description": "7 rows — credit-limit breach, aged invoice, large write-off",
        "suggested_pack": "AR_STANDARD",
    },
    "general_ledger_sample.csv": {
        "subledger_type": "GENERAL_LEDGER",
        "title": "General Ledger",
        "description": "6 rows — backdated entry, 'test plug' keyword, unbalanced entry",
        "suggested_pack": "GL_STANDARD",
    },
    "payroll_sample.csv": {
        "subledger_type": "PAYROLL",
        "title": "Payroll",
        "description": "6 rows — shared bank account, ghost employee, 50% pay raise",
        "suggested_pack": "PAYROLL_STANDARD",
    },
    "fixed_assets_sample.csv": {
        "subledger_type": "FIXED_ASSETS",
        "title": "Fixed Assets",
        "description": "7 rows — negative NBV, unapproved addition, unusual disposal gain",
        "suggested_pack": "FA_STANDARD",
    },
    "inventory_sample.csv": {
        "subledger_type": "INVENTORY",
        "title": "Inventory",
        "description": "8 rows — negative quantity, obsolete stock, cycle-count variance",
        "suggested_pack": "INVENTORY_STANDARD",
    },
    "bank_sample.csv": {
        "subledger_type": "BANK",
        "title": "Bank",
        "description": "9 rows — long-uncleared cheque, voided cheque, round-trip transfer",
        "suggested_pack": "BANK_RECON",
    },
    "procurement_sample.csv": {
        "subledger_type": "PROCUREMENT",
        "title": "Procurement",
        "description": "8 rows — split POs, sole-source justification, duplicate PO number",
        "suggested_pack": "PROCUREMENT_STANDARD",
    },
    "travel_expense_sample.csv": {
        "subledger_type": "TE",
        "title": "Travel & Expense",
        "description": "8 rows — duplicate claim, policy-limit violation, missing receipt",
        "suggested_pack": "TE_STANDARD",
    },
    "sales_sample.csv": {
        "subledger_type": "SALES",
        "title": "Sales",
        "description": "8 rows — backdated sales, large discount, period-end spike",
        "suggested_pack": "REVENUE_STANDARD",
    },
    "email_jsmith.mbox": {
        "subledger_type": "EMAIL",
        "title": "Mailbox — J. Smith",
        "description": "6 messages — price list to own gmail, kickback contact, "
                       "after-hours mail to competitor. Import together with A. Khan "
                       "via 'Import mailboxes (PST)'.",
        "suggested_pack": "EMAIL_INVESTIGATION",
    },
    "email_akhan.mbox": {
        "subledger_type": "EMAIL",
        "title": "Mailbox — A. Khan",
        "description": "5 messages — payroll extract to personal yahoo, shares the "
                       "same external gmail contact as J. Smith (collusion signal).",
        "suggested_pack": "EMAIL_INVESTIGATION",
    },
}


@router.get("")
def list_samples(_u: User = Depends(get_current_user)) -> list[dict]:
    out = []
    for name, meta in DESCRIPTIONS.items():
        path = SAMPLES_DIR / name
        if not path.exists():
            continue
        out.append({
            "filename": name,
            "title": meta["title"],
            "description": meta["description"],
            "subledger_type": meta["subledger_type"],
            "suggested_pack": meta["suggested_pack"],
            "size_bytes": path.stat().st_size,
        })
    return out


@router.get("/{filename}")
def download_sample(filename: str, _u: User = Depends(get_current_user)) -> Response:
    if filename not in DESCRIPTIONS:
        raise HTTPException(status_code=404, detail="Unknown sample")
    path = SAMPLES_DIR / filename
    if not path.exists():
        raise HTTPException(status_code=410, detail="Sample missing on disk")
    media = "text/csv" if filename.endswith(".csv") else "application/octet-stream"
    return Response(
        content=path.read_bytes(),
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
