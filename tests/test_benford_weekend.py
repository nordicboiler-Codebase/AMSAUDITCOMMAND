from __future__ import annotations

import math
from datetime import date, timedelta

import numpy as np
import polars as pl


def test_benford_conforming_distribution(detector_catalog):
    rng = np.random.default_rng(42)
    values = 10 ** rng.uniform(0, 5, 2000)
    df = pl.DataFrame({"record_id": [f"R{i}" for i in range(len(values))], "amount": values})
    detector = detector_catalog.get("benford")
    result = detector.run(df, {"numeric_field": "amount", "digit_mode": "first"})
    summary = result.summary
    assert summary["n_values"] == 2000
    assert "distribution" in summary
    dist = {d["digit"]: d["observed_pct"] for d in summary["distribution"]}
    expected_1 = math.log10(2)
    assert abs(dist[1] - expected_1) < 0.05, f"Digit 1 pct {dist[1]} far from Benford"
    assert summary["conformity"] in {"close", "acceptable", "marginal", "nonconformity"}


def test_benford_nonconforming_invented_data(detector_catalog):
    values = [round(v, -2) for v in np.random.default_rng(1).uniform(5000, 9999, 1000)]
    df = pl.DataFrame({"record_id": [f"R{i}" for i in range(len(values))], "amount": values})
    detector = detector_catalog.get("benford")
    result = detector.run(df, {"numeric_field": "amount", "digit_mode": "first"})
    assert result.summary["conformity"] == "nonconformity"


def test_weekend_only_flags_weekend_rows(detector_catalog):
    base = date(2025, 1, 6)
    rows = []
    for i in range(14):
        d = base + timedelta(days=i)
        rows.append({"record_id": f"R{i}", "payment_date": d, "amount": 100.0})
    df = pl.DataFrame(rows)
    detector = detector_catalog.get("weekend_transactions")
    result = detector.run(df, {"date_field": "payment_date", "weekend_days": [5, 6]})
    flagged_keys = set(result.flagged["_record_key"].to_list())
    for i in range(14):
        d = base + timedelta(days=i)
        should = d.weekday() in (5, 6)
        was = f"R{i}" in flagged_keys
        assert was == should, f"R{i} ({d}) flagged={was} expected={should}"


def test_weekend_flags_uae_holiday(detector_catalog):
    rows = [
        {"record_id": "R1", "payment_date": date(2025, 1, 1), "amount": 100.0},
        {"record_id": "R2", "payment_date": date(2025, 1, 15), "amount": 100.0},
    ]
    df = pl.DataFrame(rows)
    detector = detector_catalog.get("weekend_transactions")
    result = detector.run(df, {
        "date_field": "payment_date",
        "weekend_days": [5, 6],
        "include_holidays": True,
        "holidays_ref": "uae",
    })
    flagged = set(result.flagged["_record_key"].to_list())
    assert "R1" in flagged
