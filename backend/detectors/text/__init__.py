from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

import polars as pl

from backend.detectors.base import Detector, DetectorResult, PerRecordScore, add_key_column
from backend.detectors.catalog import register
from backend.models.enums import DetectorCategory, SubledgerType


@dataclass
class KeywordScanDetector:
    name: str = "keyword_scan"
    category: DetectorCategory = DetectorCategory.TEXT
    description: str = "Flag records containing flagged keywords in text fields"
    default_weight: float = 0.7
    default_params: dict[str, Any] = field(
        default_factory=lambda: {"text_field": "", "keywords": [], "case_sensitive": False}
    )
    supported_subledgers: list[SubledgerType] | None = None

    def run(self, df: pl.DataFrame, params: dict[str, Any]) -> DetectorResult:
        f = params["text_field"]
        keywords = params.get("keywords") or []
        case_sensitive = bool(params.get("case_sensitive", False))
        if f not in df.columns or not keywords:
            return DetectorResult(flagged=df.head(0), summary={"flagged_count": 0, "reason": "missing_config"})
        df2 = add_key_column(df)
        series = df2[f].cast(pl.Utf8, strict=False).fill_null("")
        if not case_sensitive:
            series = series.str.to_lowercase()
            check_keywords = [k.lower() for k in keywords]
        else:
            check_keywords = list(keywords)
        pattern = "|".join(re.escape(k) for k in check_keywords)
        mask = series.str.contains(pattern)
        flagged = df2.filter(mask)
        reasons: dict[str, str] = {}
        flagged_series = flagged[f].cast(pl.Utf8, strict=False).fill_null("").to_list()
        flagged_keys = flagged["_record_key"].to_list()
        for k, s in zip(flagged_keys, flagged_series):
            sl = s if case_sensitive else s.lower()
            hit = next((kw for kw in check_keywords if kw in sl), None)
            reasons[k] = f"contains '{hit}'"
        scores = [PerRecordScore(k, 1.0, reasons.get(k, "keyword hit")) for k in flagged_keys]
        return DetectorResult(
            flagged=flagged,
            summary={"flagged_count": flagged.height, "keywords": keywords, "field": f},
            per_record_scores=scores,
        )


@dataclass
class TextAnomalyDetector:
    name: str = "text_anomaly"
    category: DetectorCategory = DetectorCategory.TEXT
    description: str = "Unusual text patterns (all caps, excessive symbols, very short/long)"
    default_weight: float = 0.4
    default_params: dict[str, Any] = field(
        default_factory=lambda: {"text_field": "", "checks": ["all_caps", "too_short", "too_long"],
                                 "min_len": 3, "max_len": 500, "symbol_threshold": 0.3}
    )
    supported_subledgers: list[SubledgerType] | None = None

    def run(self, df: pl.DataFrame, params: dict[str, Any]) -> DetectorResult:
        f = params["text_field"]
        checks = set(params.get("checks") or [])
        min_len = int(params.get("min_len", 3))
        max_len = int(params.get("max_len", 500))
        sym_thr = float(params.get("symbol_threshold", 0.3))
        if f not in df.columns:
            return DetectorResult(flagged=df.head(0), summary={"flagged_count": 0, "reason": "field_not_found"})
        df2 = add_key_column(df)
        texts = df2[f].cast(pl.Utf8, strict=False).fill_null("").to_list()
        keys = df2["_record_key"].to_list()
        flagged_keys: list[str] = []
        reasons: dict[str, str] = {}
        for k, t in zip(keys, texts):
            t = t.strip()
            if not t:
                continue
            reason = None
            if "all_caps" in checks and t.isupper() and len(t) >= 5:
                reason = "all-caps"
            elif "too_short" in checks and len(t) < min_len:
                reason = f"too short ({len(t)})"
            elif "too_long" in checks and len(t) > max_len:
                reason = f"too long ({len(t)})"
            elif "excessive_symbols" in checks:
                non_alnum = sum(1 for c in t if not c.isalnum() and not c.isspace())
                if len(t) and non_alnum / len(t) > sym_thr:
                    reason = f"symbol ratio {non_alnum/len(t):.2f}"
            if reason:
                flagged_keys.append(k)
                reasons[k] = reason
        flagged = df2.filter(pl.col("_record_key").is_in(flagged_keys))
        scores = [PerRecordScore(k, 1.0, reasons[k]) for k in flagged_keys]
        return DetectorResult(
            flagged=flagged,
            summary={"flagged_count": flagged.height, "checks": list(checks)},
            per_record_scores=scores,
        )


register(KeywordScanDetector())
register(TextAnomalyDetector())
