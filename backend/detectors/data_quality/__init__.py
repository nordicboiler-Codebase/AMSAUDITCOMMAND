from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

import polars as pl

from backend.detectors.base import Detector, DetectorResult, PerRecordScore, add_key_column
from backend.detectors.catalog import register
from backend.models.enums import DetectorCategory, SubledgerType

BUILTIN_PATTERNS = {
    "email": r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$",
    "phone": r"^\+?[0-9\- ()]{7,20}$",
    "iban": r"^[A-Z]{2}[0-9A-Z]{13,32}$",
    "uae_trn": r"^[0-9]{15}$",
    "emirates_id": r"^784-[0-9]{4}-[0-9]{7}-[0-9]$",
    "url": r"^https?://[^\s/$.?#].[^\s]*$",
}


def _flag(df: pl.DataFrame, mask: pl.Series | pl.Expr, reason: str) -> DetectorResult:
    df = add_key_column(df)
    if isinstance(mask, pl.Expr):
        flagged = df.filter(mask)
    else:
        flagged = df.filter(mask)
    scores = [PerRecordScore(k, 1.0, reason) for k in flagged["_record_key"].to_list()]
    return DetectorResult(
        flagged=flagged,
        summary={"flagged_count": flagged.height, "total_records": df.height, "reason": reason},
        per_record_scores=scores,
    )


@dataclass
class NullCheckDetector:
    name: str = "null_check"
    category: DetectorCategory = DetectorCategory.DATA_QUALITY
    description: str = "Flag records with NULL/blank values in required fields"
    default_weight: float = 1.0
    default_params: dict[str, Any] = field(default_factory=lambda: {"required_fields": []})
    supported_subledgers: list[SubledgerType] | None = None

    def run(self, df: pl.DataFrame, params: dict[str, Any]) -> DetectorResult:
        fields = params.get("required_fields") or []
        present = [f for f in fields if f in df.columns]
        if not present:
            return DetectorResult(flagged=df.head(0), summary={"flagged_count": 0, "reason": "no_fields_checked"})
        df2 = add_key_column(df)
        expr = None
        for f in present:
            e = pl.col(f).is_null() | (pl.col(f).cast(pl.Utf8, strict=False).str.strip_chars() == "")
            expr = e if expr is None else (expr | e)
        flagged = df2.filter(expr)
        scores = [PerRecordScore(k, 1.0, f"null in {present}") for k in flagged["_record_key"].to_list()]
        return DetectorResult(
            flagged=flagged,
            summary={"flagged_count": flagged.height, "fields_checked": present, "total_records": df.height},
            per_record_scores=scores,
        )


@dataclass
class TypeValidationDetector:
    name: str = "type_validation"
    category: DetectorCategory = DetectorCategory.DATA_QUALITY
    description: str = "Flag records where a field value doesn't match expected type"
    default_weight: float = 0.8
    default_params: dict[str, Any] = field(default_factory=lambda: {"field": "", "expected_type": "numeric"})
    supported_subledgers: list[SubledgerType] | None = None

    def run(self, df: pl.DataFrame, params: dict[str, Any]) -> DetectorResult:
        field_name = params["field"]
        expected = params.get("expected_type", "numeric")
        if field_name not in df.columns:
            return DetectorResult(flagged=df.head(0), summary={"flagged_count": 0, "reason": "field_not_found"})
        df2 = add_key_column(df)
        series = df2[field_name].cast(pl.Utf8, strict=False)
        if expected == "numeric":
            parsed = series.str.strip_chars().cast(pl.Float64, strict=False)
            mask = parsed.is_null() & series.is_not_null() & (series.str.strip_chars() != "")
        elif expected == "date":
            parsed = series.str.strip_chars().str.to_date(strict=False)
            mask = parsed.is_null() & series.is_not_null() & (series.str.strip_chars() != "")
        elif expected == "integer":
            parsed = series.str.strip_chars().cast(pl.Int64, strict=False)
            mask = parsed.is_null() & series.is_not_null() & (series.str.strip_chars() != "")
        else:
            return DetectorResult(flagged=df.head(0), summary={"flagged_count": 0, "reason": "unknown_type"})
        flagged = df2.filter(mask)
        scores = [PerRecordScore(k, 1.0, f"{field_name} not {expected}") for k in flagged["_record_key"].to_list()]
        return DetectorResult(
            flagged=flagged,
            summary={"flagged_count": flagged.height, "field": field_name, "expected_type": expected},
            per_record_scores=scores,
        )


@dataclass
class FormatValidationDetector:
    name: str = "format_validation"
    category: DetectorCategory = DetectorCategory.DATA_QUALITY
    description: str = "Regex/pattern validation (emails, phones, tax IDs, IBAN)"
    default_weight: float = 0.7
    default_params: dict[str, Any] = field(default_factory=lambda: {"field": "", "pattern": "email"})
    supported_subledgers: list[SubledgerType] | None = None

    def run(self, df: pl.DataFrame, params: dict[str, Any]) -> DetectorResult:
        field_name = params["field"]
        pat_spec = params.get("pattern", "email")
        if field_name not in df.columns:
            return DetectorResult(flagged=df.head(0), summary={"flagged_count": 0, "reason": "field_not_found"})
        pattern = BUILTIN_PATTERNS.get(pat_spec, pat_spec)
        try:
            re.compile(pattern)
        except re.error as e:
            return DetectorResult(flagged=df.head(0), summary={"flagged_count": 0, "reason": f"bad regex: {e}"})
        df2 = add_key_column(df)
        series = df2[field_name].cast(pl.Utf8, strict=False).str.strip_chars()
        mask = series.is_not_null() & (series != "") & ~series.str.contains(pattern)
        flagged = df2.filter(mask)
        scores = [PerRecordScore(k, 1.0, f"{field_name} fails {pat_spec}") for k in flagged["_record_key"].to_list()]
        return DetectorResult(
            flagged=flagged,
            summary={"flagged_count": flagged.height, "field": field_name, "pattern": pat_spec},
            per_record_scores=scores,
        )


@dataclass
class RangeValidationDetector:
    name: str = "range_validation"
    category: DetectorCategory = DetectorCategory.DATA_QUALITY
    description: str = "Flag numeric values outside expected range"
    default_weight: float = 0.8
    default_params: dict[str, Any] = field(default_factory=lambda: {"field": "", "min": None, "max": None})
    supported_subledgers: list[SubledgerType] | None = None

    def run(self, df: pl.DataFrame, params: dict[str, Any]) -> DetectorResult:
        field_name = params["field"]
        lo = params.get("min")
        hi = params.get("max")
        compare_field = params.get("compare_to_field")
        if field_name not in df.columns:
            return DetectorResult(flagged=df.head(0), summary={"flagged_count": 0, "reason": "field_not_found"})
        df2 = add_key_column(df)
        col = pl.col(field_name).cast(pl.Float64, strict=False)
        masks = []
        if lo is not None:
            masks.append(col < lo)
        if hi is not None:
            masks.append(col > hi)
        if compare_field and compare_field in df.columns:
            masks.append(col > pl.col(compare_field).cast(pl.Float64, strict=False))
        if not masks:
            return DetectorResult(flagged=df.head(0), summary={"flagged_count": 0, "reason": "no_bounds"})
        combined = masks[0]
        for m in masks[1:]:
            combined = combined | m
        flagged = df2.filter(combined)
        scores = [PerRecordScore(k, 1.0, f"{field_name} out of range") for k in flagged["_record_key"].to_list()]
        return DetectorResult(
            flagged=flagged,
            summary={"flagged_count": flagged.height, "field": field_name, "min": lo, "max": hi},
            per_record_scores=scores,
        )


@dataclass
class ReferentialIntegrityDetector:
    name: str = "referential_integrity"
    category: DetectorCategory = DetectorCategory.DATA_QUALITY
    description: str = "Flag records where FK value doesn't exist in parent dataset"
    default_weight: float = 0.9
    default_params: dict[str, Any] = field(default_factory=lambda: {"child_field": "", "parent_values": []})
    supported_subledgers: list[SubledgerType] | None = None

    def run(self, df: pl.DataFrame, params: dict[str, Any]) -> DetectorResult:
        child_field = params["child_field"]
        parent_values = set(params.get("parent_values") or [])
        if child_field not in df.columns or not parent_values:
            return DetectorResult(flagged=df.head(0), summary={"flagged_count": 0, "reason": "missing_config"})
        df2 = add_key_column(df)
        mask = ~df2[child_field].cast(pl.Utf8, strict=False).is_in(list(map(str, parent_values)))
        mask = mask & df2[child_field].is_not_null()
        flagged = df2.filter(mask)
        scores = [PerRecordScore(k, 1.0, f"{child_field} missing in parent") for k in flagged["_record_key"].to_list()]
        return DetectorResult(
            flagged=flagged,
            summary={"flagged_count": flagged.height, "child_field": child_field, "parent_count": len(parent_values)},
            per_record_scores=scores,
        )


@dataclass
class BlankRowsDetector:
    name: str = "blank_rows"
    category: DetectorCategory = DetectorCategory.DATA_QUALITY
    description: str = "Detect and flag entirely blank or header-only rows"
    default_weight: float = 0.5
    default_params: dict[str, Any] = field(default_factory=dict)
    supported_subledgers: list[SubledgerType] | None = None

    def run(self, df: pl.DataFrame, params: dict[str, Any]) -> DetectorResult:
        df2 = add_key_column(df)
        non_key_cols = [c for c in df2.columns if c != "_record_key"]
        if not non_key_cols:
            return DetectorResult(flagged=df.head(0), summary={"flagged_count": 0})
        mask = None
        for c in non_key_cols:
            e = df2[c].is_null() | (df2[c].cast(pl.Utf8, strict=False).str.strip_chars() == "")
            mask = e if mask is None else (mask & e)
        flagged = df2.filter(mask)
        scores = [PerRecordScore(k, 1.0, "entirely blank row") for k in flagged["_record_key"].to_list()]
        return DetectorResult(
            flagged=flagged, summary={"flagged_count": flagged.height}, per_record_scores=scores
        )


register(NullCheckDetector())
register(TypeValidationDetector())
register(FormatValidationDetector())
register(RangeValidationDetector())
register(ReferentialIntegrityDetector())
register(BlankRowsDetector())
