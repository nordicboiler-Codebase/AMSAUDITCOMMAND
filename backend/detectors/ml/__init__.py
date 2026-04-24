from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import polars as pl

from backend.detectors.base import Detector, DetectorResult, PerRecordScore, add_key_column
from backend.detectors.catalog import register
from backend.models.enums import DetectorCategory, SubledgerType


@dataclass
class IsolationForestDetector:
    name: str = "isolation_forest"
    category: DetectorCategory = DetectorCategory.ML
    description: str = "Multivariate anomaly detection via isolation forest"
    default_weight: float = 0.8
    default_params: dict[str, Any] = field(
        default_factory=lambda: {"feature_fields": [], "contamination": 0.05, "random_state": 42}
    )
    supported_subledgers: list[SubledgerType] | None = None

    def run(self, df: pl.DataFrame, params: dict[str, Any]) -> DetectorResult:
        from sklearn.ensemble import IsolationForest

        features = [f for f in (params.get("feature_fields") or []) if f in df.columns]
        contamination = float(params.get("contamination", 0.05))
        if not features or df.height < 20:
            return DetectorResult(flagged=df.head(0), summary={"flagged_count": 0,
                                                               "reason": "insufficient_data"})
        df2 = add_key_column(df)
        X_df = df2.select(features).with_columns(
            [pl.col(c).cast(pl.Float64, strict=False).fill_null(0) for c in features]
        )
        X = X_df.to_numpy()
        model = IsolationForest(contamination=contamination, random_state=int(params.get("random_state", 42)))
        preds = model.fit_predict(X)
        raw_scores = -model.score_samples(X)
        mask = preds == -1
        mask_pl = pl.Series(values=mask.tolist())
        flagged = df2.filter(mask_pl)
        normalized = (raw_scores - raw_scores.min()) / max((raw_scores.max() - raw_scores.min()), 1e-9)
        keys = df2["_record_key"].to_list()
        scores = [
            PerRecordScore(keys[i], float(normalized[i]), "multivariate anomaly")
            for i in range(len(keys))
            if mask[i]
        ]
        return DetectorResult(
            flagged=flagged,
            summary={"flagged_count": flagged.height, "features": features, "contamination": contamination},
            per_record_scores=scores,
        )


@dataclass
class ZScoreOutlierDetector:
    name: str = "zscore_outlier"
    category: DetectorCategory = DetectorCategory.ML
    description: str = "Univariate z-score outliers"
    default_weight: float = 0.6
    default_params: dict[str, Any] = field(
        default_factory=lambda: {"field": "", "threshold": 3.0, "grouping_field": None}
    )
    supported_subledgers: list[SubledgerType] | None = None

    def run(self, df: pl.DataFrame, params: dict[str, Any]) -> DetectorResult:
        f = params["field"]
        threshold = float(params.get("threshold", 3.0))
        g = params.get("grouping_field")
        if f not in df.columns:
            return DetectorResult(flagged=df.head(0), summary={"flagged_count": 0, "reason": "field_not_found"})
        df2 = add_key_column(df)
        flagged_keys: list[str] = []
        reasons: dict[str, str] = {}
        if g and g in df.columns:
            for gval, sub in df2.group_by(g):
                gv = gval[0] if isinstance(gval, tuple) else gval
                vals = sub[f].cast(pl.Float64, strict=False)
                mean = float(vals.mean() or 0)
                std = float(vals.std() or 0)
                if std == 0 or vals.drop_nulls().len() < 3:
                    continue
                zs = (vals - mean) / std
                m = zs.abs() > threshold
                out = sub.filter(m)
                z_vals = zs.to_list()
                for i, key in enumerate(sub["_record_key"].to_list()):
                    if m[i]:
                        flagged_keys.append(key)
                        reasons[key] = f"z={z_vals[i]:.2f} in group {gv}"
        else:
            vals = df2[f].cast(pl.Float64, strict=False)
            mean = float(vals.mean() or 0)
            std = float(vals.std() or 0)
            if std == 0:
                return DetectorResult(flagged=df.head(0), summary={"flagged_count": 0, "reason": "zero_stddev"})
            zs = (vals - mean) / std
            m = zs.abs() > threshold
            keys = df2["_record_key"].to_list()
            z_vals = zs.to_list()
            for i, k in enumerate(keys):
                if m[i]:
                    flagged_keys.append(k)
                    reasons[k] = f"z={z_vals[i]:.2f}"
        flagged = df2.filter(pl.col("_record_key").is_in(flagged_keys))
        scores = [PerRecordScore(k, 1.0, reasons[k]) for k in flagged_keys]
        return DetectorResult(
            flagged=flagged,
            summary={"flagged_count": flagged.height, "threshold": threshold, "field": f},
            per_record_scores=scores,
        )


register(IsolationForestDetector())
register(ZScoreOutlierDetector())
