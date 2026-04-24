from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

import polars as pl

from backend.detectors.base import Detector, DetectorResult, PerRecordScore, add_key_column
from backend.detectors.catalog import register
from backend.models.enums import DetectorCategory, SubledgerType


@dataclass
class StatisticsDetector:
    name: str = "statistics"
    category: DetectorCategory = DetectorCategory.STATISTICAL
    description: str = "Descriptive statistics per numeric field"
    default_weight: float = 0.2
    default_params: dict[str, Any] = field(default_factory=lambda: {"numeric_fields": []})
    supported_subledgers: list[SubledgerType] | None = None

    def run(self, df: pl.DataFrame, params: dict[str, Any]) -> DetectorResult:
        fields = params.get("numeric_fields") or [
            c for c, dt in df.schema.items() if dt.is_numeric()
        ]
        stats: dict[str, dict] = {}
        for f in fields:
            if f not in df.columns:
                continue
            col = df[f].cast(pl.Float64, strict=False)
            h = df.height
            non_null = col.drop_nulls()
            stats[f] = {
                "count": int(non_null.len()),
                "null_count": int(h - non_null.len()),
                "zero_count": int((col == 0).sum() or 0),
                "negative_count": int((col < 0).sum() or 0),
                "sum": float(col.sum() or 0),
                "mean": float(col.mean() or 0),
                "median": float(col.median() or 0),
                "stddev": float(col.std() or 0),
                "min": float(col.min() or 0) if non_null.len() else None,
                "max": float(col.max() or 0) if non_null.len() else None,
                "q1": float(col.quantile(0.25) or 0) if non_null.len() else None,
                "q3": float(col.quantile(0.75) or 0) if non_null.len() else None,
            }
        return DetectorResult(flagged=df.head(0), summary={"flagged_count": 0, "statistics": stats})


@dataclass
class StratifyDetector:
    name: str = "stratify"
    category: DetectorCategory = DetectorCategory.STATISTICAL
    description: str = "Bucket numeric field into value bands"
    default_weight: float = 0.2
    default_params: dict[str, Any] = field(
        default_factory=lambda: {"field": "", "intervals": None, "auto_intervals": 10}
    )
    supported_subledgers: list[SubledgerType] | None = None

    def run(self, df: pl.DataFrame, params: dict[str, Any]) -> DetectorResult:
        f = params["field"]
        if f not in df.columns:
            return DetectorResult(flagged=df.head(0), summary={"flagged_count": 0, "reason": "field_not_found"})
        col = df[f].cast(pl.Float64, strict=False).drop_nulls()
        if col.len() == 0:
            return DetectorResult(flagged=df.head(0), summary={"flagged_count": 0, "reason": "empty"})
        intervals = params.get("intervals")
        if not intervals:
            n = int(params.get("auto_intervals", 10))
            mn = float(col.min())
            mx = float(col.max())
            step = (mx - mn) / max(n, 1) if mx > mn else 1.0
            intervals = [[mn + i * step, mn + (i + 1) * step] for i in range(n)]
        buckets = []
        for lo, hi in intervals:
            c = int(col.filter((col >= lo) & (col < hi)).len())
            s = float(col.filter((col >= lo) & (col < hi)).sum() or 0)
            buckets.append({"from": lo, "to": hi, "count": c, "sum": s})
        return DetectorResult(flagged=df.head(0), summary={"flagged_count": 0, "buckets": buckets})


@dataclass
class ClassifyDetector:
    name: str = "classify"
    category: DetectorCategory = DetectorCategory.STATISTICAL
    description: str = "Group by category field with counts and subtotals"
    default_weight: float = 0.2
    default_params: dict[str, Any] = field(
        default_factory=lambda: {"category_field": "", "subtotal_fields": [], "top_n": 50}
    )
    supported_subledgers: list[SubledgerType] | None = None

    def run(self, df: pl.DataFrame, params: dict[str, Any]) -> DetectorResult:
        cat = params["category_field"]
        sub_fields = params.get("subtotal_fields") or []
        top_n = int(params.get("top_n", 50))
        if cat not in df.columns:
            return DetectorResult(flagged=df.head(0), summary={"flagged_count": 0, "reason": "field_not_found"})
        aggs = [pl.len().alias("count")]
        for sf in sub_fields:
            if sf in df.columns:
                aggs.append(pl.col(sf).cast(pl.Float64, strict=False).sum().alias(f"sum_{sf}"))
        grouped = df.group_by(cat).agg(aggs).sort("count", descending=True).head(top_n)
        return DetectorResult(flagged=df.head(0), summary={"flagged_count": 0,
                                                           "groups": grouped.to_dicts()})


@dataclass
class HistogramDetector:
    name: str = "histogram"
    category: DetectorCategory = DetectorCategory.STATISTICAL
    description: str = "Frequency distribution"
    default_weight: float = 0.2
    default_params: dict[str, Any] = field(
        default_factory=lambda: {"field": "", "bins": 20}
    )
    supported_subledgers: list[SubledgerType] | None = None

    def run(self, df: pl.DataFrame, params: dict[str, Any]) -> DetectorResult:
        f = params["field"]
        bins = int(params.get("bins", 20))
        if f not in df.columns:
            return DetectorResult(flagged=df.head(0), summary={"flagged_count": 0, "reason": "field_not_found"})
        col = df[f].cast(pl.Float64, strict=False).drop_nulls()
        if col.len() == 0:
            return DetectorResult(flagged=df.head(0), summary={"flagged_count": 0, "reason": "empty"})
        mn, mx = float(col.min()), float(col.max())
        step = (mx - mn) / max(bins, 1) if mx > mn else 1.0
        histogram = []
        for i in range(bins):
            lo = mn + i * step
            hi = mn + (i + 1) * step
            c = int(col.filter((col >= lo) & (col < hi)).len())
            histogram.append({"from": lo, "to": hi, "count": c})
        return DetectorResult(flagged=df.head(0), summary={"flagged_count": 0, "histogram": histogram})


@dataclass
class SummarizeDetector:
    name: str = "summarize"
    category: DetectorCategory = DetectorCategory.STATISTICAL
    description: str = "SQL-style GROUP BY with subtotals"
    default_weight: float = 0.2
    default_params: dict[str, Any] = field(
        default_factory=lambda: {"group_by_fields": [], "subtotal_fields": [], "top_n": 100,
                                 "filter_expr": None}
    )
    supported_subledgers: list[SubledgerType] | None = None

    def run(self, df: pl.DataFrame, params: dict[str, Any]) -> DetectorResult:
        groups = [g for g in (params.get("group_by_fields") or []) if g in df.columns]
        subs = [s for s in (params.get("subtotal_fields") or []) if s in df.columns]
        top_n = int(params.get("top_n", 100))
        if not groups:
            return DetectorResult(flagged=df.head(0), summary={"flagged_count": 0, "reason": "no_groups"})
        aggs = [pl.len().alias("count")]
        for s in subs:
            aggs.append(pl.col(s).cast(pl.Float64, strict=False).sum().alias(f"sum_{s}"))
        sort_col = f"sum_{subs[0]}" if subs else "count"
        grouped = df.group_by(groups).agg(aggs).sort(sort_col, descending=True).head(top_n)
        return DetectorResult(flagged=df.head(0), summary={"flagged_count": 0, "rows": grouped.to_dicts()})


@dataclass
class CrossTabulateDetector:
    name: str = "cross_tabulate"
    category: DetectorCategory = DetectorCategory.STATISTICAL
    description: str = "Two-field pivot"
    default_weight: float = 0.2
    default_params: dict[str, Any] = field(
        default_factory=lambda: {"row_field": "", "column_field": ""}
    )
    supported_subledgers: list[SubledgerType] | None = None

    def run(self, df: pl.DataFrame, params: dict[str, Any]) -> DetectorResult:
        rf = params["row_field"]
        cf = params["column_field"]
        if rf not in df.columns or cf not in df.columns:
            return DetectorResult(flagged=df.head(0), summary={"flagged_count": 0, "reason": "fields_missing"})
        try:
            pivot = df.pivot(values=df.columns[0] if df.columns else rf, index=rf, columns=cf,
                             aggregate_function="count")
            return DetectorResult(flagged=df.head(0), summary={"flagged_count": 0, "pivot": pivot.to_dicts()})
        except Exception as e:
            return DetectorResult(flagged=df.head(0), summary={"flagged_count": 0, "error": str(e)})


@dataclass
class AgeDetector:
    name: str = "age"
    category: DetectorCategory = DetectorCategory.STATISTICAL
    description: str = "Aging analysis by date"
    default_weight: float = 0.7
    default_params: dict[str, Any] = field(
        default_factory=lambda: {
            "date_field": "",
            "cutoff_date": None,
            "buckets": [[0, 30], [31, 60], [61, 90], [91, None]],
            "filter_field": None,
            "filter_value": None,
        }
    )
    supported_subledgers: list[SubledgerType] | None = None

    def run(self, df: pl.DataFrame, params: dict[str, Any]) -> DetectorResult:
        dfield = params["date_field"]
        if dfield not in df.columns:
            return DetectorResult(flagged=df.head(0), summary={"flagged_count": 0, "reason": "field_not_found"})
        cutoff = params.get("cutoff_date")
        if isinstance(cutoff, str):
            cutoff = datetime.fromisoformat(cutoff).date()
        if cutoff is None:
            cutoff = date.today()
        df2 = add_key_column(df)
        filter_field = params.get("filter_field")
        filter_value = params.get("filter_value")
        if filter_field and filter_field in df.columns and filter_value is not None:
            df2 = df2.filter(pl.col(filter_field) == filter_value)
        date_col = df2[dfield].cast(pl.Date, strict=False)
        ages = (pl.lit(cutoff) - date_col).dt.total_days()
        df2 = df2.with_columns(ages.alias("_age_days"))
        buckets = params.get("buckets") or [[0, 30], [31, 60], [61, 90], [91, None]]
        bucket_rows = []
        for b in buckets:
            lo = b[0]
            hi = b[1]
            m = pl.col("_age_days") >= lo
            if hi is not None:
                m = m & (pl.col("_age_days") <= hi)
            sub = df2.filter(m)
            bucket_rows.append({
                "from": lo,
                "to": hi,
                "count": sub.height,
            })
        oldest_bucket = buckets[-1]
        oldest_lo = oldest_bucket[0]
        oldest_hi = oldest_bucket[1]
        oldest_mask = pl.col("_age_days") >= oldest_lo
        if oldest_hi is not None:
            oldest_mask = oldest_mask & (pl.col("_age_days") <= oldest_hi)
        flagged = df2.filter(oldest_mask).drop("_age_days")
        scores = [
            PerRecordScore(k, 1.0, f"aged beyond {oldest_lo}") for k in flagged["_record_key"].to_list()
        ]
        return DetectorResult(
            flagged=flagged,
            summary={
                "flagged_count": flagged.height,
                "cutoff": cutoff.isoformat(),
                "buckets": bucket_rows,
            },
            per_record_scores=scores,
        )


register(StatisticsDetector())
register(StratifyDetector())
register(ClassifyDetector())
register(HistogramDetector())
register(SummarizeDetector())
register(CrossTabulateDetector())
register(AgeDetector())
