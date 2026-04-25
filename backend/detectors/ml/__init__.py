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


@dataclass
class GroupedOutliersDetector:
    """Group-aware outliers — flags rows whose value is N std-dev from the
    *group* mean (e.g. per vendor, per GL account). Replicates ACL's OUTLIERS
    command more faithfully than the global zscore_outlier."""
    name: str = "grouped_outliers"
    category: DetectorCategory = DetectorCategory.ML
    description: str = "Outliers within groups (per vendor / GL account / cost-centre)"
    default_weight: float = 0.7
    default_params: dict[str, Any] = field(
        default_factory=lambda: {
            "field": "amount",
            "grouping_field": "vendor_id",
            "threshold": 3.0,
            "min_group_size": 5,
        }
    )
    supported_subledgers: list[SubledgerType] | None = None

    def run(self, df: pl.DataFrame, params: dict[str, Any]) -> DetectorResult:
        f = params.get("field", "amount")
        g = params.get("grouping_field", "")
        threshold = float(params.get("threshold", 3.0))
        min_group_size = int(params.get("min_group_size", 5))
        if f not in df.columns or g not in df.columns:
            return DetectorResult(flagged=df.head(0), summary={"flagged_count": 0, "reason": "field_not_found"})
        df2 = add_key_column(df).with_columns(
            pl.col(f).cast(pl.Float64, strict=False).alias(f)
        )
        stats = (
            df2.group_by(g)
            .agg(
                pl.col(f).mean().alias("_grp_mean"),
                pl.col(f).std().alias("_grp_std"),
                pl.len().alias("_grp_n"),
            )
        )
        df3 = df2.join(stats, on=g, how="left")
        df3 = df3.with_columns(
            ((pl.col(f) - pl.col("_grp_mean")).abs()
             / pl.when(pl.col("_grp_std") > 0).then(pl.col("_grp_std")).otherwise(1.0)
             ).alias("_grp_z")
        )
        flagged = df3.filter(
            (pl.col("_grp_n") >= min_group_size) & (pl.col("_grp_z") > threshold)
        )
        keys = flagged["_record_key"].to_list()
        zs = flagged["_grp_z"].to_list()
        groups = flagged[g].to_list()
        vals = flagged[f].to_list()
        scores = [
            PerRecordScore(
                keys[i], min(1.0, float(zs[i]) / max(threshold * 2, 1)),
                f"{f}={vals[i]} is {zs[i]:.1f} std-devs from {g}={groups[i]} group mean",
            )
            for i in range(len(keys))
        ]
        return DetectorResult(
            flagged=flagged.drop("_grp_mean", "_grp_std", "_grp_n", "_grp_z"),
            summary={"flagged_count": flagged.height, "field": f,
                     "grouping_field": g, "threshold": threshold},
            per_record_scores=scores,
        )


@dataclass
class KMeansClusterDetector:
    """K-means clustering — flags records that sit far from their assigned
    centroid (top X% by distance). Complements isolation_forest. Mirrors ACL's
    CLUSTER command."""
    name: str = "kmeans_cluster"
    category: DetectorCategory = DetectorCategory.ML
    description: str = "K-means clustering — flags records far from their cluster centroid"
    default_weight: float = 0.7
    default_params: dict[str, Any] = field(
        default_factory=lambda: {
            "feature_fields": [],
            "n_clusters": 5,
            "top_pct_to_flag": 0.05,
            "random_state": 42,
        }
    )
    supported_subledgers: list[SubledgerType] | None = None

    def run(self, df: pl.DataFrame, params: dict[str, Any]) -> DetectorResult:
        from sklearn.cluster import KMeans
        from sklearn.preprocessing import StandardScaler

        features = [f for f in (params.get("feature_fields") or []) if f in df.columns]
        n_clusters = int(params.get("n_clusters", 5))
        top_pct = float(params.get("top_pct_to_flag", 0.05))
        if not features or df.height < max(20, n_clusters * 3):
            return DetectorResult(flagged=df.head(0),
                                  summary={"flagged_count": 0, "reason": "insufficient_data"})
        df2 = add_key_column(df)
        X_df = df2.select(features).with_columns(
            [pl.col(c).cast(pl.Float64, strict=False).fill_null(0) for c in features]
        )
        X = StandardScaler().fit_transform(X_df.to_numpy())
        n_clusters = max(2, min(n_clusters, max(2, df.height // 5)))
        model = KMeans(n_clusters=n_clusters, random_state=int(params.get("random_state", 42)), n_init=10)
        labels = model.fit_predict(X)
        centroids = model.cluster_centers_
        dists = np.linalg.norm(X - centroids[labels], axis=1)
        cutoff_idx = max(1, int(df.height * top_pct))
        threshold = float(np.partition(dists, -cutoff_idx)[-cutoff_idx])
        mask = dists >= threshold
        mask_pl = pl.Series(values=mask.tolist())
        flagged = df2.filter(mask_pl)
        norm = (dists - dists.min()) / max((dists.max() - dists.min()), 1e-9)
        keys = df2["_record_key"].to_list()
        scores = [
            PerRecordScore(keys[i], float(norm[i]),
                           f"cluster {int(labels[i])} outlier (distance={dists[i]:.2f})")
            for i in range(len(keys)) if mask[i]
        ]
        return DetectorResult(
            flagged=flagged,
            summary={
                "flagged_count": flagged.height, "n_clusters": int(n_clusters),
                "features": features, "top_pct": top_pct,
                "cluster_sizes": {int(k): int(v)
                                  for k, v in zip(*np.unique(labels, return_counts=True))},
            },
            per_record_scores=scores,
        )


@dataclass
class SupervisedClassifierDetector:
    """Supervised gradient-boosted classifier — trains on labelled rows in the
    dataset and scores the unlabelled remainder. Mirrors ACL's TRAIN+PREDICT
    pair. Auditors typically prepare a staging view with a label column
    derived from finding_labels: 1 = previously confirmed TP, 0 = confirmed
    FP, null = unlabelled.

    The detector returns the unlabelled rows that score in the top X% by
    P(TP). Labelled rows are excluded from the output (they're already known)
    but their counts appear in the summary.
    """
    name: str = "supervised_classifier"
    category: DetectorCategory = DetectorCategory.ML
    description: str = "Gradient-boosted classifier trained on prior TP/FP labels"
    default_weight: float = 0.9
    default_params: dict[str, Any] = field(
        default_factory=lambda: {
            "label_field": "label",
            "feature_fields": [],
            "top_pct_to_flag": 0.05,
            "min_labels": 20,
            "random_state": 42,
        }
    )
    supported_subledgers: list[SubledgerType] | None = None

    def run(self, df: pl.DataFrame, params: dict[str, Any]) -> DetectorResult:
        from sklearn.ensemble import GradientBoostingClassifier
        from sklearn.preprocessing import StandardScaler

        lf = params.get("label_field", "label")
        features = [f for f in (params.get("feature_fields") or []) if f in df.columns]
        top_pct = float(params.get("top_pct_to_flag", 0.05))
        min_labels = int(params.get("min_labels", 20))
        if lf not in df.columns or not features:
            return DetectorResult(flagged=df.head(0),
                                  summary={"flagged_count": 0,
                                           "reason": "missing label_field or features"})
        df2 = add_key_column(df).with_columns(
            pl.col(lf).cast(pl.Int64, strict=False).alias("_lbl")
        )
        labelled = df2.filter(pl.col("_lbl").is_not_null())
        unlabelled = df2.filter(pl.col("_lbl").is_null())
        n_pos = int((labelled["_lbl"] == 1).sum() or 0)
        n_neg = int((labelled["_lbl"] == 0).sum() or 0)
        if labelled.height < min_labels or n_pos < 2 or n_neg < 2:
            return DetectorResult(
                flagged=df.head(0),
                summary={
                    "flagged_count": 0,
                    "reason": "insufficient_labels",
                    "n_positive_labels": n_pos,
                    "n_negative_labels": n_neg,
                    "min_labels_required": min_labels,
                },
            )
        if unlabelled.height == 0:
            return DetectorResult(
                flagged=df.head(0),
                summary={"flagged_count": 0, "reason": "no_unlabelled_rows",
                         "n_positive_labels": n_pos, "n_negative_labels": n_neg},
            )

        X_train_df = labelled.select(features).with_columns(
            [pl.col(c).cast(pl.Float64, strict=False).fill_null(0) for c in features]
        )
        X_test_df = unlabelled.select(features).with_columns(
            [pl.col(c).cast(pl.Float64, strict=False).fill_null(0) for c in features]
        )
        scaler = StandardScaler()
        X_train = scaler.fit_transform(X_train_df.to_numpy())
        X_test = scaler.transform(X_test_df.to_numpy())
        y_train = labelled["_lbl"].to_numpy()

        model = GradientBoostingClassifier(
            n_estimators=80, max_depth=3,
            random_state=int(params.get("random_state", 42)),
        )
        model.fit(X_train, y_train)
        proba = model.predict_proba(X_test)[:, 1]
        cutoff_idx = max(1, int(unlabelled.height * top_pct))
        threshold = float(np.partition(proba, -cutoff_idx)[-cutoff_idx])
        mask = proba >= threshold
        mask_pl = pl.Series(values=mask.tolist())
        flagged = unlabelled.filter(mask_pl)
        keys = unlabelled["_record_key"].to_list()
        scores = [
            PerRecordScore(keys[i], float(proba[i]),
                           f"P(TP)={proba[i]:.2f} from {n_pos}+{n_neg} prior labels")
            for i in range(len(keys)) if mask[i]
        ]
        # Feature importances for explainability
        feat_imp = sorted(
            zip(features, [float(v) for v in model.feature_importances_]),
            key=lambda x: -x[1],
        )[:5]
        return DetectorResult(
            flagged=flagged.drop("_lbl"),
            summary={
                "flagged_count": flagged.height,
                "n_positive_labels": n_pos,
                "n_negative_labels": n_neg,
                "n_unlabelled_scored": unlabelled.height,
                "top_pct": top_pct,
                "threshold_proba": round(threshold, 4),
                "top_features": feat_imp,
            },
            per_record_scores=scores,
        )


register(IsolationForestDetector())
register(ZScoreOutlierDetector())
register(GroupedOutliersDetector())
register(KMeansClusterDetector())
register(SupervisedClassifierDetector())
