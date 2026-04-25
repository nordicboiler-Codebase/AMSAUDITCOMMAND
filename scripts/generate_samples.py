"""Generate richer sample CSVs with planted fraud signals across every subledger.

Each file gets ~150-300 rows with multiple overlapping signals so the standard
packs produce a varied risk distribution, not all-or-nothing scores.
"""
from __future__ import annotations

import csv
import random
from datetime import date, datetime, timedelta
from pathlib import Path

OUT_DIR = Path(__file__).resolve().parent.parent / "samples"
OUT_DIR.mkdir(exist_ok=True)
BASE = date(2025, 9, 1)


def _date(offset: int) -> date:
    return BASE + timedelta(days=offset)


def _datetime(offset: int, hour: int = 12) -> str:
    return f"{_date(offset).isoformat()}T{hour:02d}:{random.randint(0,59):02d}:00"


def _weekend(offset: int) -> int:
    """Return offset shifted forward to land on a Friday (weekend day in UAE schema)."""
    d = _date(offset)
    while d.weekday() != 5:
        d += timedelta(days=1)
    return (d - BASE).days


def _benford_amount(rng: random.Random) -> float:
    """Power-law distributed amount that follows Benford's Law naturally."""
    return round(10 ** rng.uniform(2, 5.5), 2)


def write_ap(path: Path, n: int = 220) -> None:
    rng = random.Random(42)
    fields = ["record_id","vendor_id","vendor_name","vendor_iban","vendor_address",
              "vendor_phone","invoice_no","amount","payment_date","payment_datetime",
              "description","gl_account","employee_id","employee_iban","po_number"]
    rows = []
    vendors = [(f"V{i:03d}", f"Vendor {i:03d} LLC") for i in range(1, 36)]
    employees = [(f"E{i:03d}", f"Employee {i:03d}") for i in range(1, 18)]
    for i in range(n):
        v_idx = rng.randint(0, len(vendors)-1)
        vid, vname = vendors[v_idx]
        e = employees[rng.randint(0, len(employees)-1)]
        d = rng.randint(0, 90)
        amt = _benford_amount(rng)
        # planted signals
        if i % 19 == 0:                    # threshold-just-below
            amt = 9500.0 + rng.randint(0, 499)
        elif i % 23 == 0:                  # round-dollar
            amt = round(amt / 1000) * 1000
        weekend = (i % 17 == 0)
        late_night = (i % 29 == 0)
        keyword_inv = (i % 31 == 0)
        vendor_employee_match = (i % 41 == 0)
        po_box_only = (i % 53 == 0)
        if weekend: d = _weekend(d)
        hour = 23 if late_night else rng.randint(8, 18)
        addr = "PO Box 1234" if po_box_only else f"Street {i}, Dubai"
        emp_iban = f"AE07033{vid[1:]:>017s}" if vendor_employee_match else f"AE99999{rng.randint(0, 10**16):016d}"
        # duplicate-payment plant: same vendor + amount on adjacent rows for some i
        if i % 37 == 0 and i > 0:
            amt = float(rows[-1]["amount"])
            vid, vname = vendors[int(rows[-1]["vendor_id"][1:])-1]
        rows.append({
            "record_id": f"R{i:04d}",
            "vendor_id": vid,
            "vendor_name": vname,
            "vendor_iban": f"AE07033{v_idx:020d}"[:22],
            "vendor_address": addr,
            "vendor_phone": f"+9715{rng.randint(0, 10**7):07d}",
            "invoice_no": f"INV-{2000+i}",
            "amount": round(amt, 2),
            "payment_date": _date(d).isoformat(),
            "payment_datetime": _datetime(d, hour),
            "description": "test reversal correction" if keyword_inv else "supplier payment",
            "gl_account": f"GL-{(i%9):04d}",
            "employee_id": e[0],
            "employee_iban": emp_iban,
            "po_number": f"PO-{3000+i}" if i % 3 else "",
        })
    _write(path, fields, rows)


def write_ar(path: Path, n: int = 180) -> None:
    rng = random.Random(7)
    fields = ["record_id","customer_id","customer_name","invoice_no","invoice_amount",
              "invoice_date","due_date","payment_date","balance","credit_limit",
              "writeoff_amount","type","ref_invoice_no","shipment_id"]
    rows = []
    for i in range(n):
        cid = f"C{rng.randint(1, 28):03d}"
        amt = _benford_amount(rng)
        d = rng.randint(0, 90)
        # planted signals
        type_ = "sale"
        ref = ""
        wo = 0.0
        bal = amt
        cl = rng.choice([10000.0, 25000.0, 50000.0, 100000.0])
        if i % 13 == 0:                    # credit-limit breach
            bal = cl + rng.randint(2000, 8000)
        if i % 19 == 0:                    # negative balance / refund
            bal = -abs(amt)
            type_ = "refund"
            ref = f"INV-{2000+(i-1)}"
        if i % 23 == 0:                    # large write-off
            wo = round(amt * rng.uniform(0.4, 0.8), 2)
            type_ = "writeoff"
        aged = i % 37 == 0                  # aged
        invoice_date = _date(d - 95) if aged else _date(d)
        due = invoice_date + timedelta(days=30)
        paid = "" if (aged or rng.random() < 0.4) else _date(d + 15).isoformat()
        backdated = (i % 41 == 0)
        if backdated:
            paid = _date(d - 5).isoformat()
        rows.append({
            "record_id": f"R{i:04d}",
            "customer_id": cid,
            "customer_name": f"Customer {cid[1:]} {'Trading' if i%2 else 'LLC'}",
            "invoice_no": f"INV-{2000+i}",
            "invoice_amount": round(amt, 2),
            "invoice_date": invoice_date.isoformat(),
            "due_date": due.isoformat(),
            "payment_date": paid,
            "balance": round(bal, 2),
            "credit_limit": cl,
            "writeoff_amount": wo,
            "type": type_,
            "ref_invoice_no": ref,
            "shipment_id": f"SHIP-{3000+i}" if i % 5 else "",
        })
    _write(path, fields, rows)


def write_gl(path: Path, n: int = 250) -> None:
    rng = random.Random(11)
    fields = ["record_id","journal_id","posting_date","posting_datetime","entry_date",
              "entry_type","entered_by","debit_account","credit_account","amount",
              "debit_amount","credit_amount","description","period_close_date","reverses_journal_id"]
    users = ["sarah.k","ahmed.r","priya.s","john.c","maria.s","fatima.a"]
    period_close = _date(60)
    rows = []
    for i in range(n):
        d = rng.randint(0, 90)
        amt = _benford_amount(rng)
        is_manual = rng.random() < 0.45
        weekend = (i % 21 == 0)
        late_night = (i % 19 == 0)
        post_close = (i % 47 == 0)
        backdated = (i % 53 == 0)
        plug_keyword = (i % 31 == 0)
        unbalanced = (i % 41 == 0)
        amt_d, amt_c = amt, amt - (rng.uniform(1, 50) if unbalanced else 0)
        if weekend: d = _weekend(d)
        if post_close: d = 65
        hour = 23 if late_night else rng.randint(8, 18)
        entry_date = _date(d + (5 if backdated else 0))
        rows.append({
            "record_id": f"R{i:04d}",
            "journal_id": f"JE-{4000+i}",
            "posting_date": _date(d).isoformat(),
            "posting_datetime": _datetime(d, hour),
            "entry_date": entry_date.isoformat(),
            "entry_type": "manual" if is_manual else "auto",
            "entered_by": rng.choice(users),
            "debit_account": f"GL-{rng.randint(1000, 9999)}",
            "credit_account": f"GL-{rng.randint(1000, 9999)}",
            "amount": round(amt, 2),
            "debit_amount": round(amt_d, 2),
            "credit_amount": round(amt_c, 2),
            "description": "test plug adjustment" if plug_keyword else (
                "" if i % 23 == 0 else "monthly accrual"
            ),
            "period_close_date": period_close.isoformat(),
            "reverses_journal_id": f"JE-{4000+(i-1)}" if (i > 0 and i % 29 == 0) else "",
        })
    _write(path, fields, rows)


def write_payroll(path: Path, n: int = 140) -> None:
    rng = random.Random(13)
    fields = ["record_id","employee_id","full_name","pay_period","gross_pay","bonus_amount",
              "base_salary","bonus_ratio","grade","bank_account","emirates_id","address",
              "hire_date","posting_date","overtime_hours","pay_rate_change_pct","status_change"]
    rows = []
    shared_bank_idx = [3, 19, 47]  # employees who'll share a bank account
    for i in range(n):
        eid = f"E{i+1:03d}"
        base = rng.choice([8000, 12000, 18000, 25000, 35000, 50000])
        bonus = rng.choice([0, 500, 1000, 2000, 5000])
        ot = rng.randint(0, 12)
        rate_change = rng.uniform(0, 8)
        # planted signals
        ghost = (i % 29 == 0)
        shared_bank = i in shared_bank_idx
        big_raise = (i % 31 == 0)
        big_overtime = (i % 23 == 0)
        if big_raise: rate_change = rng.uniform(40, 60)
        if big_overtime: ot = rng.randint(38, 60)
        if (i % 19 == 0):  # bonus ratio anomaly
            bonus = base * rng.randint(2, 4)
        bank = "BA-0001" if shared_bank else f"BA-{i:04d}"
        rows.append({
            "record_id": f"R{i:04d}",
            "employee_id": eid,
            "full_name": f"Employee {eid[1:]}",
            "pay_period": _date(60).isoformat(),
            "gross_pay": round(base + bonus + ot * 200, 2),
            "bonus_amount": bonus,
            "base_salary": base,
            "bonus_ratio": round(bonus / max(base, 1), 3),
            "grade": f"G{rng.randint(2, 6)}",
            "bank_account": bank,
            "emirates_id": "000-0000-0000000-0" if ghost else
                           f"784-{rng.randint(1980, 2000)}-{rng.randint(0, 9999999):07d}-{rng.randint(0,9)}",
            "address": "Unknown" if ghost else f"Tower {rng.randint(1, 80)}, Dubai",
            "hire_date": _date(-rng.randint(30, 1500)).isoformat(),
            "posting_date": _date(rng.randint(0, 30)).isoformat(),
            "overtime_hours": ot,
            "pay_rate_change_pct": round(rate_change, 2),
            "status_change": "reactivation" if i % 41 == 0 else "none",
        })
    _write(path, fields, rows)


def write_fa(path: Path, n: int = 160) -> None:
    rng = random.Random(17)
    fields = ["record_id","asset_id","asset_name","category","acquisition_cost","acquisition_date",
              "depreciation_method","accumulated_depreciation","nbv","status","subsidiary_code",
              "disposal_gain","addition_id","approval_id","transfer_type","change_type",
              "last_physical_count_date"]
    cats = ["Equipment", "Vehicle", "Furniture", "IT", "Building"]
    rows = []
    for i in range(n):
        cost = round(_benford_amount(rng) * 10, 2)
        accum = round(cost * rng.uniform(0, 1.05), 2)
        nbv = round(cost - accum, 2)
        # planted: negative NBV
        if i % 23 == 0: nbv = round(-rng.uniform(100, 5000), 2)
        # planted: cost outliers
        if i % 31 == 0: cost = round(cost * rng.uniform(8, 15), 2)
        no_approval = (i % 19 == 0)
        ghost = (i % 41 == 0)
        rows.append({
            "record_id": f"R{i:04d}",
            "asset_id": f"A{i:04d}" if not (i and i % 47 == 0) else f"A{(i-1):04d}",  # dup
            "asset_name": f"Asset {i:03d}",
            "category": rng.choice(cats),
            "acquisition_cost": cost,
            "acquisition_date": _date(-rng.randint(100, 2500)).isoformat(),
            "depreciation_method": rng.choice(["straight_line", "declining_balance", "units_of_production"]),
            "accumulated_depreciation": accum,
            "nbv": nbv,
            "status": "disposed" if i % 37 == 0 else "active",
            "subsidiary_code": f"SUB-{rng.randint(1, 4)}",
            "disposal_gain": round(rng.uniform(0, 50000), 2) if i % 37 == 0 else 0,
            "addition_id": f"ADD-{i:04d}",
            "approval_id": "" if no_approval else f"APP-{i:04d}",
            "transfer_type": rng.choice(["internal", "internal", "internal", "subsidiary"]),
            "change_type": "depreciation_method" if i % 53 == 0 else "none",
            "last_physical_count_date": "" if ghost else _date(-rng.randint(0, 90)).isoformat(),
        })
    _write(path, fields, rows)


def write_inventory(path: Path, n: int = 180) -> None:
    rng = random.Random(19)
    fields = ["record_id","sku","item_name","category","quantity","unit_cost","unit_price",
              "value","last_movement_date","movement_count","book_qty","physical_qty"]
    cats = ["Electronics", "Tools", "Consumables", "Luxury", "Spare parts"]
    rows = []
    for i in range(n):
        qty = rng.randint(-3, 200)
        cost = round(rng.uniform(0.5, 500), 2)
        if i % 29 == 0: cost = 0           # zero-cost
        if i % 17 == 0: qty = -rng.randint(1, 15)  # negative qty
        last_move = _date(rng.randint(-400, 0))
        if i % 23 == 0: last_move = _date(-rng.randint(400, 800))  # obsolete
        book = qty
        phys = qty if rng.random() > 0.18 else qty - rng.randint(1, 8)  # variance
        rows.append({
            "record_id": f"R{i:04d}",
            "sku": f"SKU-{i:04d}" if not (i and i % 39 == 0) else f"SKU-{i-1:04d}",
            "item_name": f"Item {i:03d}",
            "category": rng.choice(cats),
            "quantity": qty,
            "unit_cost": cost,
            "unit_price": round(cost * rng.uniform(1.4, 3.5), 2),
            "value": round(qty * cost, 2),
            "last_movement_date": last_move.isoformat(),
            "movement_count": rng.randint(0, 200),
            "book_qty": book,
            "physical_qty": phys,
        })
    _write(path, fields, rows)


def write_bank(path: Path, n: int = 200) -> None:
    rng = random.Random(23)
    fields = ["record_id","bank_account","check_number","transaction_date","deposit_date",
              "issue_date","amount","charge_amount","status","user_id","from_account",
              "to_account","description"]
    accounts = [f"ACC-{i:03d}" for i in range(1, 6)]
    users = ["user01", "user02", "user03"]
    rows = []
    for i in range(n):
        d = rng.randint(0, 90)
        amt = round(_benford_amount(rng), 2)
        chk = 5000 + i if i % 4 else None
        status = rng.choices(
            ["cleared","cleared","cleared","uncleared","voided","in_transit"],
            weights=[6,6,6,2,1,1])[0]
        if i % 31 == 0:
            status = "uncleared"
            d = 5  # very old uncleared
        weekend = (i % 19 == 0)
        if weekend: d = _weekend(d)
        roundtrip = (i > 0 and i % 23 == 0)
        from_a = rng.choice(accounts)
        to_a = (rows[-1]["from_account"] if roundtrip else rng.choice([a for a in accounts if a != from_a]))
        rows.append({
            "record_id": f"R{i:04d}",
            "bank_account": rng.choice(accounts),
            "check_number": chk if chk is not None else "",
            "transaction_date": _date(d).isoformat(),
            "deposit_date": _date(d - 10).isoformat() if status == "in_transit" else "",
            "issue_date": _date(d).isoformat(),
            "amount": amt,
            "charge_amount": round(rng.uniform(0, 50), 2),
            "status": status,
            "user_id": rng.choice(users),
            "from_account": from_a,
            "to_account": to_a,
            "description": "transfer" if i % 3 else "supplier payment",
        })
    _write(path, fields, rows)


def write_procurement(path: Path, n: int = 140) -> None:
    rng = random.Random(29)
    fields = ["record_id","po_number","vendor_id","vendor_name","po_amount","po_date",
              "po_type","po_notes","justification","change_type","amendment_count",
              "gr_amount","invoice_amount","has_invoice","has_quotes"]
    rows = []
    for i in range(n):
        amt = _benford_amount(rng)
        # planted: split POs
        if i % 13 == 0: amt = 9000 + rng.randint(0, 999)
        amendments = rng.randint(0, 4) if i % 19 == 0 else rng.randint(0, 1)
        emergency = (i % 23 == 0)
        sole = (i % 29 == 0)
        no_invoice = (i % 17 == 0)
        rows.append({
            "record_id": f"R{i:04d}",
            "po_number": f"PO-{5000+i}" if not (i and i % 53 == 0) else f"PO-{5000+(i-1)}",
            "vendor_id": f"V{rng.randint(1, 30):03d}",
            "vendor_name": f"Vendor {rng.randint(1, 30):03d}",
            "po_amount": round(amt, 2),
            "po_date": _date(rng.randint(0, 90)).isoformat(),
            "po_type": "emergency" if emergency else "standard",
            "po_notes": "urgent emergency single source" if emergency else "regular order",
            "justification": "sole source — exclusive partner" if sole else "competitive bid",
            "change_type": "value_increase" if amendments > 1 else "none",
            "amendment_count": amendments,
            "gr_amount": "" if no_invoice else round(amt, 2),
            "invoice_amount": "" if no_invoice else round(amt + rng.uniform(-200, 500), 2),
            "has_invoice": not no_invoice,
            "has_quotes": not (emergency or sole),
        })
    _write(path, fields, rows)


def write_te(path: Path, n: int = 130) -> None:
    rng = random.Random(31)
    fields = ["record_id","claim_id","employee_id","employee_name","category","amount",
              "category_limit","expense_date","description","receipt_path","mileage_km"]
    cats = [("meals", 200), ("travel", 5000), ("transport", 500), ("office", 1500), ("mileage", 600)]
    rows = []
    for i in range(n):
        cat, lim = rng.choice(cats)
        amt = round(rng.uniform(20, lim * 1.4), 2)
        # planted: policy violation
        if i % 17 == 0: amt = lim * rng.uniform(1.4, 2.5)
        if i % 23 == 0: amt = round(amt / 100) * 100  # round-dollar
        no_receipt = (i % 19 == 0)
        weekend = (i % 13 == 0)
        d = rng.randint(0, 90)
        if weekend: d = _weekend(d)
        rows.append({
            "record_id": f"R{i:04d}",
            "claim_id": f"EXP-{6000+i}" if not (i and i % 41 == 0) else f"EXP-{6000+(i-1)}",
            "employee_id": f"E{rng.randint(1, 60):03d}",
            "employee_name": f"Employee {rng.randint(1, 60):03d}",
            "category": cat,
            "amount": round(amt, 2),
            "category_limit": lim,
            "expense_date": _date(d).isoformat(),
            "description": ("client lunch" if cat == "meals" else
                           "flight" if cat == "travel" else
                           "site visit"),
            "receipt_path": "" if no_receipt else f"rcp_{i:04d}.pdf",
            "mileage_km": rng.randint(50, 1500) if cat == "mileage" else 0,
        })
    _write(path, fields, rows)


def write_sales(path: Path, n: int = 200) -> None:
    rng = random.Random(37)
    fields = ["record_id","sale_id","customer_id","customer_name","sale_amount","sale_date",
              "entry_date","shipment_id","discount_pct","period_close_date","product"]
    products = ["Product A", "Product B", "Product C", "Product D", "Product E"]
    period_close = _date(60)
    rows = []
    for i in range(n):
        amt = _benford_amount(rng)
        d = rng.randint(0, 90)
        # planted: large pre-period-end sale
        if i % 23 == 0:
            amt *= rng.uniform(3, 6)
            d = 58  # 2 days before close
        # planted: backdated
        backdated = (i % 31 == 0)
        entry_offset = -5 if backdated else 0
        # planted: large discount
        disc = rng.uniform(0, 12)
        if i % 19 == 0: disc = rng.uniform(35, 55)
        # planted: missing shipment
        no_ship = (i % 29 == 0)
        rows.append({
            "record_id": f"R{i:04d}",
            "sale_id": f"SL-{7000+i}",
            "customer_id": f"C{rng.randint(1, 30):03d}",
            "customer_name": f"Customer {rng.randint(1, 30):03d}",
            "sale_amount": round(amt, 2),
            "sale_date": _date(d).isoformat(),
            "entry_date": _date(d - entry_offset).isoformat(),
            "shipment_id": "" if no_ship else f"SHIP-{8000+i}",
            "discount_pct": round(disc, 1),
            "period_close_date": period_close.isoformat(),
            "product": rng.choice(products),
        })
    _write(path, fields, rows)


def _write(path: Path, fields: list[str], rows: list[dict]) -> None:
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
    print(f"  {path.name}: {len(rows)} rows")


def main() -> None:
    print(f"Writing samples to {OUT_DIR}")
    write_ap(OUT_DIR / "accounts_payable_sample.csv")
    write_ar(OUT_DIR / "accounts_receivable_sample.csv")
    write_gl(OUT_DIR / "general_ledger_sample.csv")
    write_payroll(OUT_DIR / "payroll_sample.csv")
    write_fa(OUT_DIR / "fixed_assets_sample.csv")
    write_inventory(OUT_DIR / "inventory_sample.csv")
    write_bank(OUT_DIR / "bank_sample.csv")
    write_procurement(OUT_DIR / "procurement_sample.csv")
    write_te(OUT_DIR / "travel_expense_sample.csv")
    write_sales(OUT_DIR / "sales_sample.csv")
    print("Done.")


if __name__ == "__main__":
    main()
