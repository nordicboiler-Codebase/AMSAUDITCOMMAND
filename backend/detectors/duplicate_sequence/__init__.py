from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import polars as pl
from rapidfuzz import fuzz

from backend.detectors.base import Detector, DetectorResult, PerRecordScore, add_key_column
from backend.detectors.catalog import register
from backend.models.enums import DetectorCategory, SubledgerType


@dataclass
class DuplicatesDetector:
    name: str = "duplicates"
    category: DetectorCategory = DetectorCategory.DUPLICATE_SEQUENCE
    description: str = "Exact duplicates on one or more key fields"
    default_weight: float = 1.0
    default_params: dict[str, Any] = field(default_factory=lambda: {"key_fields": []})
    supported_subledgers: list[SubledgerType] | None = None

    def run(self, df: pl.DataFrame, params: dict[str, Any]) -> DetectorResult:
        keys = [k for k in (params.get("key_fields") or []) if k in df.columns]
        if not keys:
            return DetectorResult(flagged=df.head(0), summary={"flagged_count": 0, "reason": "no_keys"})
        df2 = add_key_column(df)
        counts = df2.group_by(keys).len().rename({"len": "_dup_count"})
        dups = counts.filter(pl.col("_dup_count") > 1)
        flagged = df2.join(dups, on=keys, how="inner")
        scores = [
            PerRecordScore(k, 1.0, f"duplicate on {keys}") for k in flagged["_record_key"].to_list()
        ]
        return DetectorResult(
            flagged=flagged.drop("_dup_count"),
            summary={
                "flagged_count": flagged.height,
                "duplicate_groups": dups.height,
                "key_fields": keys,
            },
            per_record_scores=scores,
        )


@dataclass
class FuzzyDuplicatesDetector:
    name: str = "fuzzy_dup"
    category: DetectorCategory = DetectorCategory.DUPLICATE_SEQUENCE
    description: str = "Near-duplicate detection via Levenshtein distance"
    default_weight: float = 0.7
    default_params: dict[str, Any] = field(
        default_factory=lambda: {"field": "", "threshold": 85, "max_compare": 5000}
    )
    supported_subledgers: list[SubledgerType] | None = None

    def run(self, df: pl.DataFrame, params: dict[str, Any]) -> DetectorResult:
        col = params["field"]
        threshold = int(params.get("threshold", 85))
        max_compare = int(params.get("max_compare", 5000))
        if col not in df.columns:
            return DetectorResult(flagged=df.head(0), summary={"flagged_count": 0, "reason": "field_not_found"})
        df2 = add_key_column(df).with_row_index(name="_idx")
        values = df2[col].cast(pl.Utf8, strict=False).fill_null("").to_list()
        keys = df2["_record_key"].to_list()
        n = min(len(values), max_compare)
        flagged_keys: set[str] = set()
        reasons: dict[str, str] = {}
        for i in range(n):
            for j in range(i + 1, n):
                if not values[i] or not values[j]:
                    continue
                score = fuzz.ratio(values[i], values[j])
                if score >= threshold:
                    flagged_keys.add(keys[i])
                    flagged_keys.add(keys[j])
                    reasons[keys[i]] = f"fuzzy match with '{values[j]}' ({score})"
                    reasons[keys[j]] = f"fuzzy match with '{values[i]}' ({score})"
        flagged = df2.filter(pl.col("_record_key").is_in(list(flagged_keys))).drop("_idx")
        scores = [
            PerRecordScore(k, 1.0, reasons.get(k, "fuzzy duplicate")) for k in flagged["_record_key"].to_list()
        ]
        return DetectorResult(
            flagged=flagged,
            summary={"flagged_count": flagged.height, "threshold": threshold, "field": col},
            per_record_scores=scores,
        )


@dataclass
class GapsDetector:
    name: str = "gaps"
    category: DetectorCategory = DetectorCategory.DUPLICATE_SEQUENCE
    description: str = "Missing values in numeric or date sequences"
    default_weight: float = 0.6
    default_params: dict[str, Any] = field(
        default_factory=lambda: {"key_field": "", "group_by": None}
    )
    supported_subledgers: list[SubledgerType] | None = None

    def run(self, df: pl.DataFrame, params: dict[str, Any]) -> DetectorResult:
        key = params["key_field"]
        group = params.get("group_by")
        if key not in df.columns:
            return DetectorResult(flagged=df.head(0), summary={"flagged_count": 0, "reason": "field_not_found"})
        df2 = add_key_column(df)
        gaps: list[dict] = []
        if group and group in df.columns:
            for gval, sub in df2.group_by(group):
                vals = sub[key].cast(pl.Int64, strict=False).drop_nulls().sort().to_list()
                if len(vals) < 2:
                    continue
                for a, b in zip(vals, vals[1:]):
                    if b - a > 1:
                        gaps.append({"group": gval[0] if isinstance(gval, tuple) else gval,
                                     "gap_start": a + 1, "gap_end": b - 1, "size": b - a - 1})
        else:
            vals = df2[key].cast(pl.Int64, strict=False).drop_nulls().sort().to_list()
            for a, b in zip(vals, vals[1:]):
                if b - a > 1:
                    gaps.append({"gap_start": a + 1, "gap_end": b - 1, "size": b - a - 1})
        total = sum(g["size"] for g in gaps)
        return DetectorResult(
            flagged=df.head(0),
            summary={"flagged_count": total, "gap_count": len(gaps), "gaps": gaps[:200]},
        )


@dataclass
class SequenceOrderDetector:
    name: str = "sequence_order"
    category: DetectorCategory = DetectorCategory.DUPLICATE_SEQUENCE
    description: str = "Out-of-order records in expected sequence"
    default_weight: float = 0.5
    default_params: dict[str, Any] = field(
        default_factory=lambda: {"key_field": "", "ascending": True}
    )
    supported_subledgers: list[SubledgerType] | None = None

    def run(self, df: pl.DataFrame, params: dict[str, Any]) -> DetectorResult:
        key = params["key_field"]
        ascending = bool(params.get("ascending", True))
        if key not in df.columns:
            return DetectorResult(flagged=df.head(0), summary={"flagged_count": 0, "reason": "field_not_found"})
        df2 = add_key_column(df)
        prev = df2[key].shift(1)
        cur = df2[key]
        if ascending:
            mask = (cur < prev).fill_null(False)
        else:
            mask = (cur > prev).fill_null(False)
        flagged = df2.filter(mask)
        scores = [PerRecordScore(k, 1.0, "out-of-order") for k in flagged["_record_key"].to_list()]
        return DetectorResult(
            flagged=flagged,
            summary={"flagged_count": flagged.height, "key_field": key},
            per_record_scores=scores,
        )


@dataclass
class SameSameDifferentDetector:
    name: str = "same_same_different"
    category: DetectorCategory = DetectorCategory.DUPLICATE_SEQUENCE
    description: str = "Records with same values in X fields but different in Y field"
    default_weight: float = 0.9
    default_params: dict[str, Any] = field(
        default_factory=lambda: {"same_fields": [], "different_field": ""}
    )
    supported_subledgers: list[SubledgerType] | None = None

    def run(self, df: pl.DataFrame, params: dict[str, Any]) -> DetectorResult:
        same = [f for f in (params.get("same_fields") or []) if f in df.columns]
        diff = params.get("different_field")
        if not same or not diff or diff not in df.columns:
            return DetectorResult(flagged=df.head(0), summary={"flagged_count": 0, "reason": "missing_config"})
        df2 = add_key_column(df)
        grouped = df2.group_by(same).agg(pl.col(diff).n_unique().alias("_diff_n"),
                                         pl.col("_record_key").alias("_keys"))
        suspects = grouped.filter(pl.col("_diff_n") > 1)
        flagged_keys: list[str] = []
        for keys in suspects["_keys"].to_list():
            flagged_keys.extend(keys)
        flagged = df2.filter(pl.col("_record_key").is_in(flagged_keys))
        scores = [PerRecordScore(k, 1.0, f"same {same}, different {diff}") for k in flagged_keys]
        return DetectorResult(
            flagged=flagged,
            summary={"flagged_count": flagged.height, "same_fields": same, "different_field": diff,
                     "groups": suspects.height},
            per_record_scores=scores,
        )


register(DuplicatesDetector())
register(FuzzyDuplicatesDetector())
register(GapsDetector())
register(SequenceOrderDetector())
register(SameSameDifferentDetector())
