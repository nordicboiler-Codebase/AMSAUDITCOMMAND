from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import polars as pl
from rapidfuzz import fuzz

from backend.detectors.base import Detector, DetectorResult, PerRecordScore, add_key_column
from backend.detectors.catalog import register
from backend.models.enums import DetectorCategory, SubledgerType


@dataclass
class CrossMatchDetector:
    name: str = "cross_match"
    category: DetectorCategory = DetectorCategory.RELATIONAL
    description: str = "Fuzzy + exact field matching between two datasets"
    default_weight: float = 1.0
    default_params: dict[str, Any] = field(
        default_factory=lambda: {"right_dataset": [], "match_rules": [], "return": "matched"}
    )
    supported_subledgers: list[SubledgerType] | None = None

    def run(self, df: pl.DataFrame, params: dict[str, Any]) -> DetectorResult:
        right = params.get("right_dataset") or []
        rules = params.get("match_rules") or []
        mode = params.get("return", "matched")
        if not right or not rules:
            return DetectorResult(flagged=df.head(0), summary={"flagged_count": 0, "reason": "missing_config"})
        try:
            rdf = pl.DataFrame(right)
        except Exception:
            rdf = pl.from_dicts(list(right))
        df2 = add_key_column(df)
        left_rows = df2.to_dicts()
        right_rows = rdf.to_dicts()
        matched_keys: set[str] = set()
        reasons: dict[str, str] = {}
        for lrow in left_rows:
            for rrow in right_rows:
                all_ok = True
                snippets: list[str] = []
                for rule in rules:
                    lf = rule.get("field_left")
                    rf = rule.get("field_right")
                    method = rule.get("method", "exact")
                    threshold = int(rule.get("threshold", 85))
                    lv = str(lrow.get(lf, "") or "").strip()
                    rv = str(rrow.get(rf, "") or "").strip()
                    if not lv or not rv:
                        all_ok = False
                        break
                    if method == "exact":
                        ok = lv.lower() == rv.lower()
                    else:
                        ok = fuzz.ratio(lv, rv) >= threshold
                    if not ok:
                        all_ok = False
                        break
                    snippets.append(f"{lf}≈{rf}")
                if all_ok:
                    key = lrow["_record_key"]
                    matched_keys.add(key)
                    reasons[key] = "matched on " + ", ".join(snippets)
                    break
        all_keys = {r["_record_key"] for r in left_rows}
        if mode == "matched":
            flagged_keys = matched_keys
        elif mode == "unmatched_left":
            flagged_keys = all_keys - matched_keys
        else:
            flagged_keys = matched_keys
        flagged = df2.filter(pl.col("_record_key").is_in(list(flagged_keys)))
        scores = [PerRecordScore(k, 1.0, reasons.get(k, mode)) for k in flagged_keys]
        return DetectorResult(
            flagged=flagged,
            summary={"flagged_count": flagged.height, "mode": mode, "match_rules": rules},
            per_record_scores=scores,
        )


@dataclass
class RareCombinationDetector:
    name: str = "rare_combination"
    category: DetectorCategory = DetectorCategory.RELATIONAL
    description: str = "Rare value pairs within a dataset"
    default_weight: float = 0.7
    default_params: dict[str, Any] = field(
        default_factory=lambda: {"field_a": "", "field_b": "", "rarity_threshold_pct": 5.0}
    )
    supported_subledgers: list[SubledgerType] | None = None

    def run(self, df: pl.DataFrame, params: dict[str, Any]) -> DetectorResult:
        a = params["field_a"]
        b = params["field_b"]
        rarity = float(params.get("rarity_threshold_pct", 5.0))
        if a not in df.columns or b not in df.columns:
            return DetectorResult(flagged=df.head(0), summary={"flagged_count": 0, "reason": "fields_missing"})
        df2 = add_key_column(df)
        total = df2.height
        counts = df2.group_by([a, b]).len().rename({"len": "_count"})
        counts = counts.with_columns((pl.col("_count") / total * 100).alias("_pct"))
        rare = counts.filter(pl.col("_pct") < rarity)
        flagged = df2.join(rare, on=[a, b], how="inner").drop(["_count", "_pct"])
        scores = [PerRecordScore(k, 1.0, f"rare {a}+{b} pair") for k in flagged["_record_key"].to_list()]
        return DetectorResult(
            flagged=flagged,
            summary={"flagged_count": flagged.height, "rare_pair_count": rare.height, "rarity_pct": rarity},
            per_record_scores=scores,
        )


@dataclass
class PatternFrequencyDetector:
    name: str = "pattern_frequency"
    category: DetectorCategory = DetectorCategory.RELATIONAL
    description: str = "Flag rare patterns in categorical interactions"
    default_weight: float = 0.6
    default_params: dict[str, Any] = field(
        default_factory=lambda: {"group_field": "", "metric": "count", "threshold": 1,
                                 "threshold_direction": "below", "value_field": None,
                                 "filter_field": None, "filter_value": None}
    )
    supported_subledgers: list[SubledgerType] | None = None

    def run(self, df: pl.DataFrame, params: dict[str, Any]) -> DetectorResult:
        g = params["group_field"]
        metric = params.get("metric", "count")
        threshold = params.get("threshold", 1)
        direction = params.get("threshold_direction", "below")
        value_field = params.get("value_field")
        filter_field = params.get("filter_field")
        filter_value = params.get("filter_value")
        if g not in df.columns:
            return DetectorResult(flagged=df.head(0), summary={"flagged_count": 0, "reason": "field_not_found"})
        df2 = add_key_column(df)
        if filter_field and filter_field in df.columns and filter_value is not None:
            df2 = df2.filter(pl.col(filter_field) == filter_value)
        if metric == "count":
            agg = pl.len().alias("_metric")
        elif metric == "sum" and value_field and value_field in df.columns:
            agg = pl.col(value_field).cast(pl.Float64, strict=False).sum().alias("_metric")
        elif metric == "max" and value_field and value_field in df.columns:
            agg = pl.col(value_field).cast(pl.Float64, strict=False).max().alias("_metric")
        else:
            agg = pl.len().alias("_metric")
        grouped = df2.group_by(g).agg(agg)
        if direction == "below":
            suspects = grouped.filter(pl.col("_metric") <= threshold)
        else:
            suspects = grouped.filter(pl.col("_metric") >= threshold)
        flagged = df2.join(suspects, on=g, how="inner").drop("_metric")
        scores = [PerRecordScore(k, 1.0, f"{g} {metric} {direction} {threshold}") for k in flagged["_record_key"].to_list()]
        return DetectorResult(
            flagged=flagged,
            summary={"flagged_count": flagged.height, "suspect_groups": suspects.height,
                     "metric": metric, "threshold": threshold, "direction": direction},
            per_record_scores=scores,
        )


register(CrossMatchDetector())
register(RareCombinationDetector())
register(PatternFrequencyDetector())
