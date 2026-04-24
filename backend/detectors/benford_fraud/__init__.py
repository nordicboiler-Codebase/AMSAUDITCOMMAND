from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

import polars as pl

from backend.detectors.base import Detector, DetectorResult, PerRecordScore, add_key_column
from backend.detectors.catalog import register
from backend.models.enums import DetectorCategory, SubledgerType


def _benford_first_expected(d: int) -> float:
    return math.log10(1 + 1 / d)


def _benford_expected(digit_mode: str) -> list[float]:
    if digit_mode == "first":
        return [_benford_first_expected(d) for d in range(1, 10)]
    if digit_mode == "second":
        out = []
        for second in range(0, 10):
            p = sum(math.log10(1 + 1 / (10 * first + second)) for first in range(1, 10))
            out.append(p)
        return out
    if digit_mode == "first_two":
        return [math.log10(1 + 1 / d) for d in range(10, 100)]
    if digit_mode == "last_two":
        return [0.01] * 100
    raise ValueError(digit_mode)


def _extract_digits(v: float, digit_mode: str) -> int | None:
    if v is None:
        return None
    a = abs(float(v))
    if a == 0:
        return None
    if digit_mode == "first":
        while a >= 10:
            a /= 10
        while a < 1:
            a *= 10
        return int(a)
    if digit_mode == "second":
        s = f"{a:.10f}".replace(".", "").lstrip("0")
        return int(s[1]) if len(s) >= 2 else None
    if digit_mode == "first_two":
        while a >= 100:
            a /= 10
        while a < 10:
            a *= 10
        return int(a)
    if digit_mode == "last_two":
        n = int(round(a * 100))
        return n % 100
    return None


@dataclass
class BenfordDetector:
    name: str = "benford"
    category: DetectorCategory = DetectorCategory.BENFORD_FRAUD
    description: str = "Benford's Law analysis"
    default_weight: float = 0.5
    default_params: dict[str, Any] = field(
        default_factory=lambda: {"numeric_field": "", "digit_mode": "first"}
    )
    supported_subledgers: list[SubledgerType] | None = None

    def run(self, df: pl.DataFrame, params: dict[str, Any]) -> DetectorResult:
        f = params["numeric_field"]
        mode = params.get("digit_mode", "first")
        if f not in df.columns:
            return DetectorResult(flagged=df.head(0), summary={"flagged_count": 0, "reason": "field_not_found"})
        df2 = add_key_column(df)
        vals = df2[f].cast(pl.Float64, strict=False).drop_nulls()
        if vals.len() < 50:
            return DetectorResult(flagged=df.head(0), summary={"flagged_count": 0, "reason": "too_few_values",
                                                               "n": vals.len()})
        digits = [_extract_digits(v, mode) for v in vals.to_list()]
        digits = [d for d in digits if d is not None]
        total = len(digits)
        if total == 0:
            return DetectorResult(flagged=df.head(0), summary={"flagged_count": 0, "reason": "no_digits"})
        expected = _benford_expected(mode)
        start = {"first": 1, "second": 0, "first_two": 10, "last_two": 0}[mode]
        observed = [0] * len(expected)
        for d in digits:
            idx = d - start
            if 0 <= idx < len(expected):
                observed[idx] += 1
        chi_sq = 0.0
        mad_sum = 0.0
        for o, ex in zip(observed, expected):
            e_count = ex * total
            if e_count > 0:
                chi_sq += (o - e_count) ** 2 / e_count
            mad_sum += abs(o / total - ex)
        mad = mad_sum / len(expected)
        if mad < 0.0012:
            conformity = "close"
        elif mad < 0.0018:
            conformity = "acceptable"
        elif mad < 0.0022:
            conformity = "marginal"
        else:
            conformity = "nonconformity"
        dist = [
            {"digit": start + i, "observed": observed[i], "expected": expected[i] * total,
             "observed_pct": observed[i] / total, "expected_pct": expected[i]}
            for i in range(len(expected))
        ]
        suspect_digits = {d["digit"] for d in dist if d["observed_pct"] > d["expected_pct"] * 1.3
                          and d["observed"] > 30}
        flagged = df2.filter(
            pl.col(f).cast(pl.Float64, strict=False).map_elements(
                lambda v: _extract_digits(v, mode) in suspect_digits, return_dtype=pl.Boolean
            )
        )
        scores = [PerRecordScore(k, 0.5, f"Benford overweight {mode}") for k in flagged["_record_key"].to_list()]
        return DetectorResult(
            flagged=flagged,
            summary={
                "flagged_count": flagged.height,
                "n_values": total,
                "digit_mode": mode,
                "chi_square": chi_sq,
                "mad": mad,
                "conformity": conformity,
                "distribution": dist,
            },
            per_record_scores=scores,
        )


@dataclass
class RoundNumberDetector:
    name: str = "round_number"
    category: DetectorCategory = DetectorCategory.BENFORD_FRAUD
    description: str = "Amounts ending in zeros"
    default_weight: float = 0.4
    default_params: dict[str, Any] = field(
        default_factory=lambda: {"amount_field": "", "round_pattern": "000"}
    )
    supported_subledgers: list[SubledgerType] | None = None

    def run(self, df: pl.DataFrame, params: dict[str, Any]) -> DetectorResult:
        f = params["amount_field"]
        pattern = params.get("round_pattern", "000")
        if f not in df.columns:
            return DetectorResult(flagged=df.head(0), summary={"flagged_count": 0, "reason": "field_not_found"})
        df2 = add_key_column(df)
        if pattern.isdigit() and all(ch == "0" for ch in pattern):
            n = len(pattern)
            divisor = 10 ** n
            mask = (pl.col(f).cast(pl.Float64, strict=False).abs() > 0) & (
                (pl.col(f).cast(pl.Int64, strict=False) % divisor) == 0
            )
        else:
            try:
                divisor = float(pattern)
                mask = (pl.col(f).cast(pl.Float64, strict=False) % divisor) == 0
            except ValueError:
                return DetectorResult(flagged=df.head(0), summary={"flagged_count": 0, "reason": "bad_pattern"})
        flagged = df2.filter(mask)
        scores = [PerRecordScore(k, 1.0, f"round pattern {pattern}") for k in flagged["_record_key"].to_list()]
        return DetectorResult(
            flagged=flagged,
            summary={"flagged_count": flagged.height, "pattern": pattern, "field": f},
            per_record_scores=scores,
        )


@dataclass
class ThresholdAvoidanceDetector:
    name: str = "threshold_avoidance"
    category: DetectorCategory = DetectorCategory.BENFORD_FRAUD
    description: str = "Amounts just below approval thresholds"
    default_weight: float = 1.2
    default_params: dict[str, Any] = field(
        default_factory=lambda: {"amount_field": "", "thresholds": [10000], "lower_band_pct": 0.9}
    )
    supported_subledgers: list[SubledgerType] | None = None

    def run(self, df: pl.DataFrame, params: dict[str, Any]) -> DetectorResult:
        f = params["amount_field"]
        thresholds = params.get("thresholds") or []
        band = float(params.get("lower_band_pct", 0.9))
        if f not in df.columns or not thresholds:
            return DetectorResult(flagged=df.head(0), summary={"flagged_count": 0, "reason": "missing_config"})
        df2 = add_key_column(df)
        col = pl.col(f).cast(pl.Float64, strict=False)
        mask = None
        reasons: dict[str, str] = {}
        matched_threshold: dict[str, float] = {}
        for t in thresholds:
            lo = t * band
            m = (col >= lo) & (col < t)
            mask = m if mask is None else mask | m
        flagged = df2.filter(mask) if mask is not None else df.head(0)
        # annotate reason per row (post-filter)
        if mask is not None:
            amt_vals = flagged[f].cast(pl.Float64, strict=False).to_list()
            keys = flagged["_record_key"].to_list()
            for k, a in zip(keys, amt_vals):
                for t in thresholds:
                    if t * band <= a < t:
                        reasons[k] = f"amount {a} just below threshold {t}"
                        matched_threshold[k] = t
                        break
        scores = [PerRecordScore(k, 1.0, reasons.get(k, "below threshold")) for k in reasons]
        return DetectorResult(
            flagged=flagged,
            summary={"flagged_count": flagged.height, "thresholds": thresholds, "band": band},
            per_record_scores=scores,
        )


@dataclass
class AmountDistributionAnomalyDetector:
    name: str = "amount_distribution_anomaly"
    category: DetectorCategory = DetectorCategory.BENFORD_FRAUD
    description: str = "Per-group outlier detection on amount distributions"
    default_weight: float = 0.7
    default_params: dict[str, Any] = field(
        default_factory=lambda: {"amount_field": "", "grouping_field": "", "method": "iqr", "threshold": 3.0}
    )
    supported_subledgers: list[SubledgerType] | None = None

    def run(self, df: pl.DataFrame, params: dict[str, Any]) -> DetectorResult:
        f = params["amount_field"]
        g = params["grouping_field"]
        method = params.get("method", "iqr")
        threshold = float(params.get("threshold", 3.0))
        if f not in df.columns or g not in df.columns:
            return DetectorResult(flagged=df.head(0), summary={"flagged_count": 0, "reason": "fields_missing"})
        df2 = add_key_column(df)
        flagged_keys: list[str] = []
        reasons: dict[str, str] = {}
        for gval, sub in df2.group_by(g):
            gv = gval[0] if isinstance(gval, tuple) else gval
            vals = sub[f].cast(pl.Float64, strict=False).drop_nulls()
            if vals.len() < 5:
                continue
            if method == "iqr":
                q1 = float(vals.quantile(0.25))
                q3 = float(vals.quantile(0.75))
                iqr = q3 - q1
                lo = q1 - threshold * iqr
                hi = q3 + threshold * iqr
                mask = (sub[f].cast(pl.Float64, strict=False) < lo) | (sub[f].cast(pl.Float64, strict=False) > hi)
            else:
                mean = float(vals.mean())
                std = float(vals.std() or 0)
                if std == 0:
                    continue
                z = (sub[f].cast(pl.Float64, strict=False) - mean) / std
                mask = z.abs() > threshold
            outliers = sub.filter(mask)
            for k in outliers["_record_key"].to_list():
                flagged_keys.append(k)
                reasons[k] = f"outlier in group {gv}"
        flagged = df2.filter(pl.col("_record_key").is_in(flagged_keys))
        scores = [PerRecordScore(k, 1.0, reasons.get(k, "distribution outlier")) for k in flagged_keys]
        return DetectorResult(
            flagged=flagged,
            summary={"flagged_count": flagged.height, "method": method, "threshold": threshold,
                     "grouping_field": g},
            per_record_scores=scores,
        )


register(BenfordDetector())
register(RoundNumberDetector())
register(ThresholdAvoidanceDetector())
register(AmountDistributionAnomalyDetector())
