"""Recalculation detectors — recompute totals, tax, depreciation, payroll."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

import polars as pl

from backend.detectors.base import Detector, DetectorResult, PerRecordScore, add_key_column
from backend.detectors.catalog import register
from backend.models.enums import DetectorCategory, SubledgerType


@dataclass
class RecomputeTotalsDetector:
    name: str = "recompute_totals"
    category: DetectorCategory = DetectorCategory.STATISTICAL
    description: str = "Sum line items per header, compare to header total"
    default_weight: float = 1.1
    default_params: dict[str, Any] = field(
        default_factory=lambda: {
            "header_key_field": "invoice_no",
            "line_amount_field": "line_amount",
            "header_total_field": "invoice_total",
            "tolerance_abs": 0.01,
        }
    )
    supported_subledgers: list[SubledgerType] | None = None

    def run(self, df: pl.DataFrame, params: dict[str, Any]) -> DetectorResult:
        hk, la, ht = params["header_key_field"], params["line_amount_field"], params["header_total_field"]
        tol = float(params.get("tolerance_abs", 0.01))
        for c in (hk, la, ht):
            if c not in df.columns:
                return DetectorResult(flagged=df.head(0),
                                      summary={"flagged_count": 0, "reason": f"missing:{c}"})
        df2 = add_key_column(df)
        grouped = (df2.with_columns([
            pl.col(la).cast(pl.Float64, strict=False),
            pl.col(ht).cast(pl.Float64, strict=False),
        ]).group_by(hk).agg([
            pl.col(la).sum().alias("_line_sum"),
            pl.col(ht).max().alias("_header_total"),
            pl.col("_record_key").alias("_keys"),
        ]).with_columns(
            (pl.col("_line_sum") - pl.col("_header_total")).abs().alias("_diff")
        ))
        bad = grouped.filter(pl.col("_diff") > tol)
        flagged_keys: list[str] = []
        reasons: dict[str, str] = {}
        for r in bad.iter_rows(named=True):
            for k in r["_keys"]:
                flagged_keys.append(k)
                reasons[k] = (f"sum(line)={r['_line_sum']:.2f} vs header={r['_header_total']:.2f}")
        flagged = df2.filter(pl.col("_record_key").is_in(flagged_keys))
        scores = [PerRecordScore(k, 1.0, reasons[k]) for k in flagged_keys]
        return DetectorResult(
            flagged=flagged,
            summary={"flagged_count": flagged.height, "headers_with_mismatch": bad.height},
            per_record_scores=scores,
        )


@dataclass
class TaxRecomputeDetector:
    name: str = "tax_recompute"
    category: DetectorCategory = DetectorCategory.STATISTICAL
    description: str = "Verify tax = base × rate within tolerance"
    default_weight: float = 1.0
    default_params: dict[str, Any] = field(
        default_factory=lambda: {
            "base_field": "net_amount",
            "tax_field": "tax_amount",
            "rate_field": "tax_rate_pct",
            "tolerance_abs": 0.5,
        }
    )
    supported_subledgers: list[SubledgerType] | None = None

    def run(self, df: pl.DataFrame, params: dict[str, Any]) -> DetectorResult:
        b, t, r = params["base_field"], params["tax_field"], params["rate_field"]
        tol = float(params.get("tolerance_abs", 0.5))
        for c in (b, t, r):
            if c not in df.columns:
                return DetectorResult(flagged=df.head(0),
                                      summary={"flagged_count": 0, "reason": f"missing:{c}"})
        df2 = add_key_column(df).with_columns([
            pl.col(b).cast(pl.Float64, strict=False).alias("_base"),
            pl.col(t).cast(pl.Float64, strict=False).alias("_tax"),
            (pl.col(r).cast(pl.Float64, strict=False) / 100.0).alias("_rate"),
        ]).with_columns(
            (pl.col("_base") * pl.col("_rate") - pl.col("_tax")).abs().alias("_diff")
        )
        flagged = df2.filter(pl.col("_diff") > tol)
        scores = [
            PerRecordScore(row["_record_key"], 1.0,
                          f"expected {row['_base']*row['_rate']:.2f} got {row['_tax']:.2f}")
            for row in flagged.iter_rows(named=True)
        ]
        return DetectorResult(
            flagged=flagged.drop(["_base", "_tax", "_rate", "_diff"]),
            summary={"flagged_count": flagged.height, "tolerance_abs": tol},
            per_record_scores=scores,
        )


@dataclass
class DepreciationRecomputeDetector:
    name: str = "depreciation_recompute"
    category: DetectorCategory = DetectorCategory.STATISTICAL
    description: str = "Recompute straight-line depreciation; flag mismatches"
    default_weight: float = 1.0
    default_params: dict[str, Any] = field(
        default_factory=lambda: {
            "cost_field": "acquisition_cost",
            "salvage_field": "salvage_value",
            "useful_life_years_field": "useful_life",
            "acquisition_date_field": "acquisition_date",
            "accumulated_field": "accumulated_depreciation",
            "as_of_date": None,
            "tolerance_pct": 5.0,
        }
    )
    supported_subledgers: list[SubledgerType] | None = field(
        default_factory=lambda: [SubledgerType.FIXED_ASSETS]
    )

    def run(self, df: pl.DataFrame, params: dict[str, Any]) -> DetectorResult:
        cost, salv, life = params["cost_field"], params["salvage_field"], params["useful_life_years_field"]
        ad, accum = params["acquisition_date_field"], params["accumulated_field"]
        tol = float(params.get("tolerance_pct", 5.0)) / 100.0
        as_of = params.get("as_of_date")
        as_of_date = (datetime.fromisoformat(as_of).date() if isinstance(as_of, str)
                      else as_of) or date.today()
        for c in (cost, salv, life, ad, accum):
            if c not in df.columns:
                return DetectorResult(flagged=df.head(0),
                                      summary={"flagged_count": 0, "reason": f"missing:{c}"})
        df2 = add_key_column(df)
        flagged_keys: list[str] = []
        reasons: dict[str, str] = {}
        for row in df2.iter_rows(named=True):
            try:
                c_val = float(row[cost] or 0)
                s_val = float(row[salv] or 0)
                l_val = float(row[life] or 0)
                a_val = float(row[accum] or 0)
                acq = row[ad]
                if isinstance(acq, str):
                    acq = datetime.fromisoformat(acq).date()
                if not (l_val and acq):
                    continue
                years = (as_of_date - acq).days / 365.25
                expected = max(0, min((c_val - s_val) * years / l_val, c_val - s_val))
                if c_val > 0 and abs(expected - a_val) / max(c_val, 1) > tol:
                    flagged_keys.append(row["_record_key"])
                    reasons[row["_record_key"]] = (
                        f"expected accum {expected:.2f} vs booked {a_val:.2f}"
                    )
            except Exception:
                continue
        flagged = df2.filter(pl.col("_record_key").is_in(flagged_keys))
        scores = [PerRecordScore(k, 1.0, reasons[k]) for k in flagged_keys]
        return DetectorResult(
            flagged=flagged,
            summary={"flagged_count": flagged.height, "tolerance_pct": tol * 100,
                     "as_of_date": as_of_date.isoformat()},
            per_record_scores=scores,
        )


@dataclass
class PayrollGrossToNetDetector:
    name: str = "payroll_gross_to_net"
    category: DetectorCategory = DetectorCategory.STATISTICAL
    description: str = "Recompute payroll: net = gross − Σ deductions"
    default_weight: float = 1.0
    default_params: dict[str, Any] = field(
        default_factory=lambda: {
            "gross_field": "gross_pay",
            "net_field": "net_pay",
            "deduction_fields": [],
            "tolerance_abs": 1.0,
        }
    )
    supported_subledgers: list[SubledgerType] | None = field(
        default_factory=lambda: [SubledgerType.PAYROLL]
    )

    def run(self, df: pl.DataFrame, params: dict[str, Any]) -> DetectorResult:
        g, n = params["gross_field"], params["net_field"]
        deds = [d for d in (params.get("deduction_fields") or []) if d in df.columns]
        tol = float(params.get("tolerance_abs", 1.0))
        if g not in df.columns or n not in df.columns:
            return DetectorResult(flagged=df.head(0),
                                  summary={"flagged_count": 0, "reason": "missing_config"})
        df2 = add_key_column(df).with_columns([
            pl.col(g).cast(pl.Float64, strict=False).alias("_g"),
            pl.col(n).cast(pl.Float64, strict=False).alias("_n"),
        ])
        if deds:
            ded_expr = sum(
                (pl.col(d).cast(pl.Float64, strict=False).fill_null(0) for d in deds),
                pl.lit(0.0),
            )
            df2 = df2.with_columns(ded_expr.alias("_d"))
        else:
            df2 = df2.with_columns(pl.lit(0.0).alias("_d"))
        df2 = df2.with_columns(
            (pl.col("_g") - pl.col("_d") - pl.col("_n")).abs().alias("_diff")
        )
        flagged = df2.filter(pl.col("_diff") > tol)
        scores = [
            PerRecordScore(r["_record_key"], 1.0,
                          f"gross−deductions={r['_g']-r['_d']:.2f} vs net={r['_n']:.2f}")
            for r in flagged.iter_rows(named=True)
        ]
        return DetectorResult(
            flagged=flagged.drop(["_g", "_n", "_d", "_diff"]),
            summary={"flagged_count": flagged.height, "tolerance_abs": tol},
            per_record_scores=scores,
        )


register(RecomputeTotalsDetector())
register(TaxRecomputeDetector())
register(DepreciationRecomputeDetector())
register(PayrollGrossToNetDetector())
