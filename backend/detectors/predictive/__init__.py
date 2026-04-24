from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import polars as pl

from backend.detectors.base import Detector, DetectorResult, PerRecordScore, add_key_column
from backend.detectors.catalog import register
from backend.models.enums import DetectorCategory, SubledgerType


def _linear_fit(xs: np.ndarray, ys: np.ndarray) -> tuple[float, float]:
    if len(xs) < 2:
        return 0.0, float(ys.mean() if len(ys) else 0)
    slope, intercept = np.polyfit(xs, ys, 1)
    return float(slope), float(intercept)


@dataclass
class TrendDeviationDetector:
    name: str = "trend_deviation"
    category: DetectorCategory = DetectorCategory.PREDICTIVE
    description: str = "Actual vs. fitted trend line residuals"
    default_weight: float = 0.7
    default_params: dict[str, Any] = field(
        default_factory=lambda: {"numeric_field": "", "date_field": "", "residual_threshold": 2.0,
                                 "grouping_field": None}
    )
    supported_subledgers: list[SubledgerType] | None = None

    def run(self, df: pl.DataFrame, params: dict[str, Any]) -> DetectorResult:
        nf = params["numeric_field"]
        dfield = params["date_field"]
        threshold = float(params.get("residual_threshold", 2.0))
        gfield = params.get("grouping_field")
        if nf not in df.columns or dfield not in df.columns:
            return DetectorResult(flagged=df.head(0), summary={"flagged_count": 0, "reason": "fields_missing"})
        df2 = add_key_column(df)
        flagged_keys: list[str] = []
        reasons: dict[str, str] = {}
        iters = df2.group_by(gfield) if gfield and gfield in df.columns else [((None,), df2)]
        for gval, sub in iters:
            sub = sub.sort(dfield)
            dates = sub[dfield].cast(pl.Date, strict=False)
            vals = sub[nf].cast(pl.Float64, strict=False)
            keys = sub["_record_key"].to_list()
            x_arr = np.arange(sub.height, dtype=float)
            y_arr = np.array([v if v is not None else np.nan for v in vals.to_list()], dtype=float)
            mask = ~np.isnan(y_arr)
            if mask.sum() < 5:
                continue
            slope, intercept = _linear_fit(x_arr[mask], y_arr[mask])
            fitted = slope * x_arr + intercept
            residuals = y_arr - fitted
            resid_std = np.nanstd(residuals) or 1.0
            for i in range(len(keys)):
                if np.isnan(y_arr[i]):
                    continue
                z = abs(residuals[i]) / resid_std
                if z > threshold:
                    flagged_keys.append(keys[i])
                    reasons[keys[i]] = f"residual z={z:.2f}"
        flagged = df2.filter(pl.col("_record_key").is_in(flagged_keys))
        scores = [PerRecordScore(k, 1.0, reasons[k]) for k in flagged_keys]
        return DetectorResult(
            flagged=flagged,
            summary={"flagged_count": flagged.height, "threshold": threshold, "field": nf},
            per_record_scores=scores,
        )


@dataclass
class ForecastVarianceDetector:
    name: str = "forecast_variance"
    category: DetectorCategory = DetectorCategory.PREDICTIVE
    description: str = "Actual vs. forecast confidence interval variance"
    default_weight: float = 0.7
    default_params: dict[str, Any] = field(
        default_factory=lambda: {"numeric_field": "", "date_field": "", "horizon_periods": 3,
                                 "ci_level": 0.95}
    )
    supported_subledgers: list[SubledgerType] | None = None

    def run(self, df: pl.DataFrame, params: dict[str, Any]) -> DetectorResult:
        nf = params["numeric_field"]
        dfield = params["date_field"]
        horizon = int(params.get("horizon_periods", 3))
        ci = float(params.get("ci_level", 0.95))
        if nf not in df.columns or dfield not in df.columns:
            return DetectorResult(flagged=df.head(0), summary={"flagged_count": 0, "reason": "fields_missing"})
        df2 = add_key_column(df).sort(dfield)
        vals = df2[nf].cast(pl.Float64, strict=False)
        series = np.array([v for v in vals.to_list() if v is not None], dtype=float)
        if len(series) < 12:
            return DetectorResult(flagged=df.head(0), summary={"flagged_count": 0, "reason": "too_few_points"})
        train = series[:-horizon]
        actual = series[-horizon:]
        mean = float(train.mean())
        std = float(train.std() or 1.0)
        z = 1.96 if abs(ci - 0.95) < 0.01 else 2.58 if ci >= 0.99 else 1.645
        lo = mean - z * std
        hi = mean + z * std
        breaches = []
        for i, a in enumerate(actual):
            if a < lo or a > hi:
                breaches.append({"period": int(len(train) + i), "actual": float(a), "lo": lo, "hi": hi})
        return DetectorResult(
            flagged=df.head(0),
            summary={
                "flagged_count": len(breaches),
                "train_mean": mean,
                "train_std": std,
                "forecast_lo": lo,
                "forecast_hi": hi,
                "breaches": breaches,
            },
        )


@dataclass
class SeasonalDecompositionDetector:
    name: str = "seasonal_decomp"
    category: DetectorCategory = DetectorCategory.PREDICTIVE
    description: str = "Seasonal decomposition residuals flagged as outliers"
    default_weight: float = 0.7
    default_params: dict[str, Any] = field(
        default_factory=lambda: {"numeric_field": "", "date_field": "", "period": 12,
                                 "residual_threshold": 2.5}
    )
    supported_subledgers: list[SubledgerType] | None = None

    def run(self, df: pl.DataFrame, params: dict[str, Any]) -> DetectorResult:
        nf = params["numeric_field"]
        dfield = params["date_field"]
        period = int(params.get("period", 12))
        threshold = float(params.get("residual_threshold", 2.5))
        if nf not in df.columns or dfield not in df.columns:
            return DetectorResult(flagged=df.head(0), summary={"flagged_count": 0, "reason": "fields_missing"})
        df2 = add_key_column(df).sort(dfield)
        vals = df2[nf].cast(pl.Float64, strict=False).to_list()
        if len(vals) < period * 2:
            return DetectorResult(flagged=df.head(0), summary={"flagged_count": 0, "reason": "too_few_periods"})
        try:
            from statsmodels.tsa.seasonal import seasonal_decompose

            arr = np.array([v if v is not None else np.nan for v in vals], dtype=float)
            arr = np.nan_to_num(arr, nan=float(np.nanmean(arr)))
            result = seasonal_decompose(arr, period=period, model="additive", extrapolate_trend="freq")
            residuals = result.resid
            std = float(np.nanstd(residuals) or 1.0)
            mask = np.abs(residuals) > threshold * std
        except Exception as e:
            return DetectorResult(flagged=df.head(0), summary={"flagged_count": 0, "error": str(e)})
        keys = df2["_record_key"].to_list()
        flagged_keys = [keys[i] for i in range(len(keys)) if i < len(mask) and mask[i]]
        flagged = df2.filter(pl.col("_record_key").is_in(flagged_keys))
        scores = [PerRecordScore(k, 1.0, "seasonal residual outlier") for k in flagged_keys]
        return DetectorResult(
            flagged=flagged,
            summary={"flagged_count": flagged.height, "period": period, "threshold": threshold},
            per_record_scores=scores,
        )


register(TrendDeviationDetector())
register(ForecastVarianceDetector())
register(SeasonalDecompositionDetector())
