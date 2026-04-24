"""Generate a small AP CSV with planted fraud signals and import it into the Pilot project."""
from __future__ import annotations

import csv
import random
import tempfile
from datetime import date, timedelta
from pathlib import Path

from sqlalchemy import select

from backend.core.db import SessionLocal
from backend.models import Dataset, Project, User
from backend.models.enums import SubledgerType
from backend.services import import_service


DATASET_NAME = "AP Sample (seeded)"


def _build_csv(path: Path, rows: int = 200) -> None:
    random.seed(42)
    fieldnames = [
        "record_id", "vendor_id", "employee_id", "invoice_no",
        "amount", "payment_date", "payment_datetime",
        "vendor_name", "vendor_iban", "employee_iban",
        "description", "gl_account",
    ]
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for i in range(rows):
            d = date(2025, 1, 1) + timedelta(days=i % 90)
            # Planted signals
            amt = round(random.expovariate(1 / 5000), 2)
            if i % 17 == 0:
                amt = 9500.00 + (i % 100)  # threshold avoidance (9000-9999)
            if i % 23 == 0:
                while d.weekday() not in (5, 6):
                    d = d + timedelta(days=1)
            vendor_iban = f"AE07033{i%3:03d}{i:017d}"[:22]
            employee_iban = vendor_iban if i % 50 == 0 else f"AE99999{i:015d}"
            w.writerow({
                "record_id": f"R{i:04d}",
                "vendor_id": f"V{i % 20:02d}",
                "employee_id": f"E{i % 15:02d}",
                "invoice_no": f"INV-{1000 + i}",
                "amount": amt,
                "payment_date": d.isoformat(),
                "payment_datetime": f"{d.isoformat()}T{(i % 24):02d}:00:00",
                "vendor_name": f"Vendor {i % 20}",
                "vendor_iban": vendor_iban,
                "employee_iban": employee_iban,
                "description": "test reversal correction" if i % 7 == 0 else "payment",
                "gl_account": f"GL-{(i % 8):04d}",
            })


def main() -> None:
    db = SessionLocal()
    try:
        admin = db.execute(select(User).where(User.username == "admin")).scalar_one_or_none()
        project = db.execute(select(Project).where(Project.name == "Pilot")).scalar_one_or_none()
        if not admin or not project:
            raise SystemExit("Run scripts/seed_admin.py first")

        existing = db.execute(
            select(Dataset).where(Dataset.project_id == project.id, Dataset.name == DATASET_NAME)
        ).scalar_one_or_none()
        if existing:
            print(f"[dataset] already exists: id={existing.id} records={existing.record_count}")
            return

        with tempfile.TemporaryDirectory() as tmp:
            csv_path = Path(tmp) / "ap_sample.csv"
            _build_csv(csv_path)
            result = import_service.import_dataset(
                db,
                file_path=csv_path,
                source_filename="ap_sample.csv",
                project_id=project.id,
                name=DATASET_NAME,
                subledger_type=SubledgerType.ACCOUNTS_PAYABLE,
                user_id=admin.id,
                description="Auto-generated AP sample with planted fraud signals",
            )
            print(f"[dataset] created id={result.dataset_id} records={result.record_count}")
            print(f"          hash={result.source_hash}")
    finally:
        db.close()


if __name__ == "__main__":
    main()
