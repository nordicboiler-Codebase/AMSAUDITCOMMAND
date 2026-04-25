"""Comparative detectors — concentration, Pareto, variance, period compare, distribution KS, DSO/DPO."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import polars as pl

from backend.detectors.base import Detector, DetectorResult, PerRecordScore, add_key_column
from backend.detectors.catalog import register
from backend.models.enums import DetectorCategory, SubledgerType


@dataclass
class ConcentrationAnalysisDetector:
    name: str = "concentration_analysis"
    category: DetectorCategory = DetectorCategory.STATISTICAL
    description: str = "Top-N entities' share of total amount"
    default_weight: float = 0.4
    default_params: dict[str, Any] = field(
        default_factory=lambda: {"entity_field": "vendor_id", "amount_field": "amount", "top_n": 10}
    )
    supported_subledgers: list[SubledgerType] | None = None

    def run(self, df: pl.DataFrame, params: dict[str, Any]) -> DetectorResult:
        e, a = params["entity_field"], params["amount_field"]
        n = int(params.get("top_n", 10))
        if e not in df.columns or a not in df.columns:
            return DetectorResult(flagged=df.head(0), summary={"flagged_count": 0, "reason": "missing_field"})
        agg = (df.with_columns(pl.col(a).cast(pl.Float64, strict=False))
                 .group_by(e).agg(pl.sum(a).alias("_total"))
                 .sort("_total", descending=True))
        total = float(agg["_total"].sum() or 0)
        top = agg.head(n)
        top_total = float(top["_total"].sum() or 0)
        return DetectorResult(
            flagged=df.head(0),
            summary={"flagged_count": 0, "top_n": n, "total_entities": agg.height,
                     "grand_total": total, "top_n_total": top_total,
                     "top_n_share_pct": (top_total / total * 100) if total else 0,
                     "rows": top.to_dicts()},
        )


@dataclass
class ParetoDetector:
    name: str = "pareto"
    category: DetectorCategory = DetectorCategory.STATISTICAL
    description: str = "80/20 Pareto on a grouping field"
    default_weight: float = 0.4
    default_params: dict[str, Any] = field(
        default_factory=lambda: {"entity_field": "vendor_id", "amount_field": "amount",
                                 "cumulative_threshold_pct": 80.0}
    )
    supported_subledgers: list[SubledgerType] | None = None

    def run(self, df: pl.DataFrame, params: dict[str, Any]) -> DetectorResult:
        e, a = params["entity_field"], params["amount_field"]
        thr = float(params.get("cumulative_threshold_pct", 80.0)) / 100.0
        if e not in df.columns or a not in df.columns:
            return DetectorResult(flagged=df.head(0), summary={"flagged_count": 0, "reason": "missing_field"})
        agg = (df.with_columns(pl.col(a).cast(pl.Float64, strict=False))
                 .group_by(e).agg(pl.sum(a).alias("_total"))
                 .sort("_total", descending=True))
        total = float(agg["_total"].sum() or 0) or 1.0
        cum, kept = 0.0, []
        for r in agg.iter_rows(named=True):
            cum += float(r["_total"] or 0)
            kept.append({"entity": r[e], "amount": r["_total"], "cumulative_pct": cum / total * 100})
            if cum / total >= thr:
                break
        return DetectorResult(
            flagged=df.head(0),
            summary={"flagged_count": 0, "threshold_pct": thr * 100,
                     "vital_few_count": len(kept),
                     "vital_few_pct_of_total": (len(kept) / agg.height * 100) if agg.height else 0,
                     "rows": kept},
        )


@dataclass
class VarianceAnalysisDetector:
    name: str = "variance_analysis"
    category: DetectorCategory = DetectorCategory.STATISTICAL
    description: str = "Actual vs budget variance with % threshold flag"
    default_weight: float = 0.6
    default_params: dict[str, Any] = field(
        default_factory=lambda: {"actual_field": "actual", "budget_field": "budget",
                                 "label_field": "account", "variance_threshold_pct": 10.0}
    )
    supported_subledgers: list[SubledgerType] | None = None

    def run(self, df: pl.DataFrame, params: dict[str, Any]) -> DetectorResult:
        a, b = params["actual_field"], params["budget_field"]
        thr = float(params.get("variance_threshold_pct", 10.0)) / 100.0
        if a not in df.columns or b not in df.columns:
            return DetectorResult(flagged=df.head(0), summary={"flagged_count": 0, "reason": "missing_field"})
        df2 = add_key_column(df).with_columns([
            pl.col(a).cast(pl.Float64, strict=False).alias("_a"),
            pl.col(b).cast(pl.Float64, strict=False).alias("_b"),
        ]).with_columns(
            ((pl.col("_a") - pl.col("_b")).abs() /
             pl.col("_b").abs().clip(lower_bound=0.01)).alias("_var")
        )
        flagged = df2.filter(pl.col("_var") > thr)
        scores = [
            PerRecordScore(r["_record_key"], 1.0,
                          f"variance {r['_var']*100:.1f}% (actual {r['_a']:.0f} vs budget {r['_b']:.0f})")
            for r in flagged.iter_rows(named=True)
        ]
        return DetectorResult(
            flagged=flagged.drop(["_a", "_b", "_var"]),
            summary={"flagged_count": flagged.height, "threshold_pct": thr * 100},
            per_record_scores=scores,
        )


@dataclass
class PeriodComparisonDetector:
    name: str = "period_comparison"
    category: DetectorCategory = DetectorCategory.STATISTICAL
    description: str = "Compare entity totals across two periods, flag large changes"
    default_weight: float = 0.5
    default_params: dict[str, Any] = field(
        default_factory=lambda: {"entity_field": "vendor_id", "amount_field": "amount",
                                 "period_field": "period", "period_a": "", "period_b": "",
                                 "change_threshold_pct": 50.0}
    )
    supported_subledgers: list[SubledgerType] | None = None

    def run(self, df: pl.DataFrame, params: dict[str, Any]) -> DetectorResult:
        e, a, p = params["entity_field"], params["amount_field"], params["period_field"]
        pa, pb = str(params.get("period_a") or ""), str(params.get("period_b") or "")
        thr = float(params.get("change_threshold_pct", 50.0)) / 100.0
        for c in (e, a, p):
            if c not in df.columns:
                return DetectorResult(flagged=df.head(0), summary={"flagged_count": 0, "reason": f"missing:{c}"})
        df2 = df.with_columns([pl.col(a).cast(pl.Float64, strict=False).alias("_a"),
                               pl.col(p).cast(pl.Utf8, strict=False).alias("_p")])
        agg = df2.group_by([e, "_p"]).agg(pl.sum("_a").alias("_total"))
        per: dict[str, dict[str, float]] = {}
        for r in agg.iter_rows(named=True):
            per.setdefault(str(r[e]), {})[str(r["_p"])] = float(r["_total"] or 0)
        all_periods = sorted({p_ for ent in per.values() for p_ in ent.keys()})
        if not pa or not pb:
            if len(all_periods) >= 2:
                pa, pb = all_periods[-2], all_periods[-1]
            else:
                return DetectorResult(flagged=df.head(0), summary={"flagged_count": 0, "reason": "need_two_periods"})
        rows: list[dict] = []
        for ent, vals in per.items():
            va, vb = vals.get(pa, 0.0), vals.get(pb, 0.0)
            denom = max(abs(va), 1e-3)
            change = (vb - va) / denom
            if abs(change) >= thr:
                rows.append({"entity": ent, pa: va, pb: vb, "change_pct": change * 100})
        rows.sort(key=lambda r: -abs(r["change_pct"]))
        return DetectorResult(
            flagged=df.head(0),
            summary={"flagged_count": len(rows), "period_a": pa, "period_b": pb,
                     "threshold_pct": thr * 100, "rows": rows[:200]},
        )


@dataclass
class DistributionCompareDetector:
    name: str = "distribution_compare"
    category: DetectorCategory = DetectorCategory.STATISTICAL
    description: str = "KS-test compare numeric distribution across two groups"
    default_weight: float = 0.5
    default_params: dict[str, Any] = field(
        default_factory=lambda: {"numeric_field": "amount", "split_field": "period",
                                 "group_a_value": "", "group_b_value": "", "alpha": 0.05}
    )
    supported_subledgers: list[SubledgerType] | None = None

    def run(self, df: pl.DataFrame, params: dict[str, Any]) -> DetectorResult:
        try:
            from scipy.stats import ks_2samp
        except ImportError:
            return DetectorResult(flagged=df.head(0),
                                  summary={"flagged_count": 0, "reason": "scipy_missing"})
        nf, sf = params["numeric_field"], params["split_field"]
        ga, gb = str(params.get("group_a_value", "")), str(params.get("group_b_value", ""))
        alpha = float(params.get("alpha", 0.05))
        if nf not in df.columns or sf not in df.columns:
            return DetectorResult(flagged=df.head(0), summary={"flagged_count": 0, "reason": "missing_field"})
        df2 = df.with_columns([pl.col(nf).cast(pl.Float64, strict=False).alias("_n"),
                               pl.col(sf).cast(pl.Utf8, strict=False).alias("_s")])
        groups = df2["_s"].drop_nulls().unique().to_list()
        if not ga or not gb:
            if len(groups) >= 2:
                ga, gb = groups[0], groups[1]
            else:
                return DetectorResult(flagged=df.head(0),
                                      summary={"flagged_count": 0, "reason": "need_two_groups"})
        sample_a = df2.filter(pl.col("_s") == ga)["_n"].drop_nulls().to_list()
        sample_b = df2.filter(pl.col("_s") == gb)["_n"].drop_nulls().to_list()
        if len(sample_a) < 5 or len(sample_b) < 5:
            return DetectorResult(flagged=df.head(0),
                                  summary={"flagged_count": 0, "reason": "too_few_samples",
                                           "n_a": len(sample_a), "n_b": len(sample_b)})
        stat, p = ks_2samp(sample_a, sample_b)
        return DetectorResult(
            flagged=df.head(0),
            summary={"flagged_count": 1 if p < alpha else 0,
                     "ks_statistic": float(stat), "p_value": float(p), "alpha": alpha,
                     "verdict": "distributions_differ" if p < alpha else "no_significant_difference",
                     "group_a": ga, "n_a": len(sample_a),
                     "group_b": gb, "n_b": len(sample_b)},
        )


@dataclass
class DsoDetector:
    name: str = "dso"
    category: DetectorCategory = DetectorCategory.STATISTICAL
    description: str = "Days Sales Outstanding per customer"
    default_weight: float = 0.4
    default_params: dict[str, Any] = field(
        default_factory=lambda: {"customer_field": "customer_id",
                                 "invoice_amount_field": "invoice_amount",
                                 "invoice_date_field": "invoice_date",
                                 "payment_date_field": "payment_date",
                                 "warning_dso": 60}
    )
    supported_subledgers: list[SubledgerType] | None = field(
        default_factory=lambda: [SubledgerType.ACCOUNTS_RECEIVABLE]
    )

    def run(self, df: pl.DataFrame, params: dict[str, Any]) -> DetectorResult:
        cf, idf, pdf = params["customer_field"], params["invoice_date_field"], params["payment_date_field"]
        warn = int(params.get("warning_dso", 60))
        for c in (cf, idf, pdf):
            if c not in df.columns:
                return DetectorResult(flagged=df.head(0), summary={"flagged_count": 0, "reason": f"missing:{c}"})
        df2 = df.with_columns([
            pl.col(idf).cast(pl.Date, strict=False).alias("_inv"),
            pl.col(pdf).cast(pl.Date, strict=False).alias("_pay"),
        ]).with_columns(
            (pl.col("_pay") - pl.col("_inv")).dt.total_days().alias("_dso")
        )
        per = (df2.filter(pl.col("_dso").is_not_null())
                  .group_by(cf).agg(pl.mean("_dso").alias("_avg_dso"),
                                    pl.len().alias("_count"))
                  .sort("_avg_dso", descending=True))
        rows = per.to_dicts()
        warnings = [r for r in rows if r["_avg_dso"] > warn]
        return DetectorResult(
            flagged=df.head(0),
            summary={"flagged_count": len(warnings), "warning_dso": warn,
                     "rows": rows[:100], "warning_customers": warnings[:50]},
        )


@dataclass
class DpoDetector:
    name: str = "dpo"
    category: DetectorCategory = DetectorCategory.STATISTICAL
    description: str = "Days Payable Outstanding per vendor"
    default_weight: float = 0.4
    default_params: dict[str, Any] = field(
        default_factory=lambda: {"vendor_field": "vendor_id",
                                 "invoice_date_field": "invoice_date",
                                 "payment_date_field": "payment_date",
                                 "warning_dpo": 90}
    )
    supported_subledgers: list[SubledgerType] | None = field(
        default_factory=lambda: [SubledgerType.ACCOUNTS_PAYABLE]
    )

    def run(self, df: pl.DataFrame, params: dict[str, Any]) -> DetectorResult:
        vf, idf, pdf = params["vendor_field"], params["invoice_date_field"], params["payment_date_field"]
        warn = int(params.get("warning_dpo", 90))
        for c in (vf, idf, pdf):
            if c not in df.columns:
                return DetectorResult(flagged=df.head(0), summary={"flagged_count": 0, "reason": f"missing:{c}"})
        df2 = df.with_columns([
            pl.col(idf).cast(pl.Date, strict=False).alias("_inv"),
            pl.col(pdf).cast(pl.Date, strict=False).alias("_pay"),
        ]).with_columns(
            (pl.col("_pay") - pl.col("_inv")).dt.total_days().alias("_dpo")
        )
        per = (df2.filter(pl.col("_dpo").is_not_null())
                  .group_by(vf).agg(pl.mean("_dpo").alias("_avg_dpo"),
                                    pl.len().alias("_count"))
                  .sort("_avg_dpo", descending=True))
        rows = per.to_dicts()
        warnings = [r for r in rows if r["_avg_dpo"] > warn]
        return DetectorResult(
            flagged=df.head(0),
            summary={"flagged_count": len(warnings), "warning_dpo": warn,
                     "rows": rows[:100], "warning_vendors": warnings[:50]},
        )


register(ConcentrationAnalysisDetector())
register(ParetoDetector())
register(VarianceAnalysisDetector())
register(PeriodComparisonDetector())
register(DistributionCompareDetector())
register(DsoDetector())
register(DpoDetector())
