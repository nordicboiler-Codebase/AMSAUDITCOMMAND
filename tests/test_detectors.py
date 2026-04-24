from __future__ import annotations

from datetime import date, datetime, timedelta

import polars as pl
import pytest

SAMPLE_SIZE = 100


def _build_sample_df() -> pl.DataFrame:
    start = date(2025, 1, 1)
    rows = []
    for i in range(SAMPLE_SIZE):
        amt = 100.0 + (i * 37) % 8000
        rows.append({
            "record_id": f"R{i:04d}",
            "vendor_id": f"V{(i % 10):02d}",
            "employee_id": f"E{(i % 20):02d}",
            "customer_id": f"C{(i % 15):02d}",
            "invoice_no": f"INV-{1000 + i}",
            "journal_id": f"JE-{2000 + i}",
            "asset_id": f"A{(i % 25):03d}",
            "sku": f"SKU-{(i % 30):03d}",
            "check_number": 5000 + i if i % 4 else None,
            "po_number": f"PO-{3000 + i}",
            "amount": amt,
            "debit_amount": amt,
            "credit_amount": amt,
            "po_amount": amt,
            "invoice_amount": amt,
            "sale_amount": amt,
            "gross_pay": 3000.0 + (i * 11) % 5000,
            "bonus_amount": (i % 7) * 1000,
            "bonus_ratio": 0.1 + (i % 5) * 0.02,
            "nbv": 5000.0 - i * 10,
            "acquisition_cost": 10000.0 + i * 30,
            "unit_cost": 10.0 + (i % 20),
            "unit_price": 25.0 + (i % 15),
            "quantity": -5 + (i % 50),
            "overtime_hours": (i % 12) * 2,
            "pay_rate_change_pct": 1.0 + (i % 30) * 0.5,
            "mileage_km": 50 + (i * 3) % 500,
            "balance": (i - 50) * 100.0,
            "balance_diff": 0.0 if i % 10 else 5.0,
            "disposal_gain": (i % 20) * 100.0,
            "writeoff_amount": (i % 15) * 250.0,
            "discount_pct": (i % 30) * 0.5,
            "charge_amount": (i % 25) * 10.0,
            "revenue": 10000 + i * 100,
            "credit_limit": 20000.0,
            "category_limit": 1000.0,
            "description": "payment" if i % 3 else "test correction",
            "vendor_name": f"Vendor {i % 10}",
            "employee_name": f"Employee {i % 20}",
            "customer_name": f"Customer {i % 15}",
            "vendor_address": "PO Box 123" if i % 5 == 0 else f"Street {i}",
            "employee_address": f"Street {i}",
            "vendor_iban": f"AE{i:020d}",
            "employee_iban": f"AE{i:020d}",
            "vendor_phone": f"+9715{i:07d}",
            "employee_phone": f"+9715{i:07d}",
            "full_name": f"Person {i}",
            "address": f"Addr {i % 40}",
            "bank_account": f"BA-{i % 18:04d}",
            "emirates_id": f"784-1990-{i:07d}-1",
            "email": f"user{i}@example.com" if i % 7 else "bad-email",
            "phone": "+971501234567" if i % 6 else "123",
            "iban": f"AE070331234567890123{i:03d}" if i % 8 else "BAD",
            "trn": f"{i:015d}" if i % 9 else "123",
            "po_notes": "emergency urgent" if i % 11 == 0 else "standard",
            "justification": "sole source" if i % 13 == 0 else "competitive",
            "gl_account": f"GL-{(i % 8):04d}",
            "debit_account": f"GL-{(i % 8):04d}",
            "credit_account": f"GL-{(i + 1) % 8:04d}",
            "date": start + timedelta(days=i),
            "due_date": start + timedelta(days=i + 30),
            "posting_date": start + timedelta(days=i),
            "payment_date": start + timedelta(days=i),
            "invoice_date": start + timedelta(days=i),
            "entry_date": start + timedelta(days=i + 1),
            "sale_date": start + timedelta(days=i),
            "expense_date": start + timedelta(days=i),
            "transaction_date": start + timedelta(days=i),
            "issue_date": start + timedelta(days=i - 100),
            "deposit_date": start + timedelta(days=i - 20),
            "last_movement_date": start + timedelta(days=i - 200),
            "hire_date": start + timedelta(days=i),
            "month": start + timedelta(days=i * 30),
            "pay_period": start + timedelta(days=i * 15),
            "payment_datetime": datetime(2025, 1, 1, (i % 24), 0, 0),
            "posting_datetime": datetime(2025, 1, 1, (i % 24), 0, 0),
            "type": "refund" if i % 20 == 0 else "sale",
            "status": "uncleared" if i % 3 == 0 else "cleared",
            "entered_by": f"user{i % 5}",
            "entry_type": "manual" if i % 2 == 0 else "auto",
            "category": f"cat_{i % 4}",
            "grade": f"G{i % 5}",
            "period_close_date": start + timedelta(days=90),
            "shipment_id": f"SHIP-{i}",
            "addition_id": f"ADD-{i}",
            "approval_id": f"APP-{i}" if i % 5 else None,
            "change_type": "value_increase" if i % 12 == 0 else "note",
            "status_change": "reactivation" if i % 17 == 0 else "none",
            "user_id": f"U{i % 8}",
            "transfer_type": "subsidiary" if i % 14 == 0 else "internal",
            "sale_id": f"S-{i}",
            "from_account": f"ACC-{i % 5}",
            "to_account": f"ACC-{(i + 1) % 5}",
            "subsidiary_code": f"SUB{i % 3}",
            "executive_username": "user0",
            "reverses_journal_id": f"JE-{2000 + (i - 1)}" if i > 0 and i % 10 == 0 else None,
            "ref_id": f"R{i:04d}",
            "ref_invoice_no": f"INV-{1000 + i}" if i % 6 else None,
            "receipt_path": None if i % 9 == 0 else f"rcp_{i}.pdf",
            "change_count": i % 3,
        })
    return pl.DataFrame(rows)


@pytest.fixture(scope="module")
def sample_df() -> pl.DataFrame:
    return _build_sample_df()


def test_catalog_registers_all_detectors(detector_catalog):
    rows = detector_catalog.list_all()
    assert len(rows) >= 35, f"Expected ≥35 detectors, got {len(rows)}"
    names = {d.name for d in rows}
    expected = {
        "null_check", "type_validation", "format_validation", "range_validation",
        "referential_integrity", "blank_rows",
        "duplicates", "fuzzy_dup", "gaps", "sequence_order", "same_same_different",
        "statistics", "stratify", "classify", "histogram", "summarize",
        "cross_tabulate", "age",
        "benford", "round_number", "threshold_avoidance", "amount_distribution_anomaly",
        "weekend_transactions", "after_hours", "period_end_spike", "date_anomaly",
        "cross_match", "rare_combination", "pattern_frequency",
        "keyword_scan", "text_anomaly",
        "isolation_forest", "zscore_outlier",
        "trend_deviation", "forecast_variance", "seasonal_decomp",
    }
    missing = expected - names
    assert not missing, f"Missing detectors: {missing}"


@pytest.mark.parametrize("detector_name", [
    "null_check", "type_validation", "format_validation", "range_validation",
    "blank_rows", "duplicates", "fuzzy_dup", "gaps", "sequence_order",
    "same_same_different", "statistics", "stratify", "classify", "histogram",
    "summarize", "age", "benford", "round_number", "threshold_avoidance",
    "amount_distribution_anomaly", "weekend_transactions", "after_hours",
    "period_end_spike", "date_anomaly", "rare_combination", "pattern_frequency",
    "keyword_scan", "text_anomaly", "isolation_forest", "zscore_outlier",
    "trend_deviation", "forecast_variance",
])
def test_detector_runs_without_error(detector_catalog, sample_df, detector_name):
    detector = detector_catalog.get(detector_name)
    params = dict(detector.default_params)
    overrides = {
        "required_fields": ["description"],
        "numeric_fields": ["amount"],
        "numeric_field": "amount",
        "amount_field": "amount",
        "date_field": "date",
        "datetime_field": "payment_datetime",
        "grouping_field": "vendor_id",
        "group_field": "vendor_id",
        "key_fields": ["vendor_id", "invoice_no"],
        "key_field": "invoice_no",
        "category_field": "category",
        "text_field": "description",
        "keywords": ["test"],
        "feature_fields": ["amount"],
        "field_a": "vendor_id",
        "field_b": "gl_account",
        "same_fields": ["invoice_no"],
        "different_field": "vendor_id",
        "child_field": "ref_invoice_no",
        "parent_values": sample_df["invoice_no"].to_list(),
        "field": "amount",
    }
    for k, v in list(params.items()):
        if v in ("", None) or (isinstance(v, list) and not v):
            if k in overrides:
                params[k] = overrides[k]
    result = detector.run(sample_df, params)
    assert result is not None
    assert isinstance(result.summary, dict)
    assert "flagged_count" in result.summary
