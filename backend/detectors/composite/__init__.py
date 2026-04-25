"""Composite detectors — combine multiple detectors logically; change-point detection."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import polars as pl

from backend.detectors.base import Detector, DetectorResult, PerRecordScore, add_key_column
from backend.detectors.catalog import get, register
from backend.models.enums import DetectorCategory, SubledgerType


@dataclass
class CompoundDetector:
    """Run a list of child detectors and combine their flagged record sets with AND/OR/NOT.

    Each child is `{"detector": "<name>", "params": {...}}`.
    `combine` is "AND" (intersection of flagged sets), "OR" (union), or
    "NOT_LAST" (records flagged by all-but-last detector, minus last detector's flags).
    """
    name: str = "compound_detector"
    category: DetectorCategory = DetectorCategory.RELATIONAL
    description: str = "Combine multiple detectors with AND / OR / NOT_LAST logic"
    default_weight: float = 1.5
    default_params: dict[str, Any] = field(
        default_factory=lambda: {"children": [], "combine": "AND"}
    )
    supported_subledgers: list[SubledgerType] | None = None

    def run(self, df: pl.DataFrame, params: dict[str, Any]) -> DetectorResult:
        children = params.get("children") or []
        combine = (params.get("combine") or "AND").upper()
        if not children:
            return DetectorResult(flagged=df.head(0),
                                  summary={"flagged_count": 0, "reason": "no_children"})
        df2 = add_key_column(df)
        sets: list[set[str]] = []
        per_child_summary: list[dict] = []
        per_child_reasons: dict[str, list[str]] = {}
        for ch in children:
            try:
                det = get(ch["detector"])
            except KeyError as e:
                return DetectorResult(flagged=df.head(0),
                                      summary={"flagged_count": 0, "reason": str(e)})
            res = det.run(df2, {**(det.default_params or {}), **(ch.get("params") or {})})
            ks: set[str] = set()
            for s in res.per_record_scores:
                ks.add(s.record_key)
                per_child_reasons.setdefault(s.record_key, []).append(
                    f"{ch['detector']}: {s.reason}"
                )
            sets.append(ks)
            per_child_summary.append({
                "detector": ch["detector"],
                "flagged": res.summary.get("flagged_count", 0),
            })
        if combine == "AND":
            keys = set.intersection(*sets) if sets else set()
        elif combine == "OR":
            keys = set.union(*sets) if sets else set()
        elif combine == "NOT_LAST":
            head = set.intersection(*sets[:-1]) if len(sets) > 1 else sets[0]
            keys = head - sets[-1]
        else:
            return DetectorResult(flagged=df.head(0),
                                  summary={"flagged_count": 0, "reason": f"bad_combine:{combine}"})
        flagged = df2.filter(pl.col("_record_key").is_in(list(keys)))
        scores = [PerRecordScore(k, 1.0, " ⋂ ".join(per_child_reasons.get(k, []))) for k in keys]
        return DetectorResult(
            flagged=flagged,
            summary={"flagged_count": flagged.height, "combine": combine,
                     "children": per_child_summary},
            per_record_scores=scores,
        )


@dataclass
class ChangePointDetector:
    """Detect abrupt changes in a time-series via CUSUM."""
    name: str = "change_point_detection"
    category: DetectorCategory = DetectorCategory.PREDICTIVE
    description: str = "CUSUM change-point detection on a numeric time series"
    default_weight: float = 0.7
    default_params: dict[str, Any] = field(
        default_factory=lambda: {
            "numeric_field": "amount",
            "date_field": "date",
            "grouping_field": "",
            "threshold_sigma": 3.0,
            "drift_pct": 0.5,
        }
    )
    supported_subledgers: list[SubledgerType] | None = None

    def run(self, df: pl.DataFrame, params: dict[str, Any]) -> DetectorResult:
        nf, dfld = params["numeric_field"], params["date_field"]
        gf = params.get("grouping_field") or ""
        thr_sigma = float(params.get("threshold_sigma", 3.0))
        drift_pct = float(params.get("drift_pct", 0.5))
        if nf not in df.columns or dfld not in df.columns:
            return DetectorResult(flagged=df.head(0), summary={"flagged_count": 0, "reason": "missing_field"})
        df2 = add_key_column(df).sort(dfld)
        change_points: list[dict] = []

        def _cusum(series: list[float]) -> list[int]:
            if len(series) < 10:
                return []
            arr = np.array(series, dtype=float)
            mean = float(np.nanmean(arr))
            std = float(np.nanstd(arr) or 1.0)
            drift = drift_pct * std
            threshold = thr_sigma * std
            cum_pos = cum_neg = 0.0
            cps: list[int] = []
            for i, v in enumerate(arr):
                if np.isnan(v):
                    continue
                cum_pos = max(0, cum_pos + (v - mean) - drift)
                cum_neg = min(0, cum_neg + (v - mean) + drift)
                if cum_pos > threshold or cum_neg < -threshold:
                    cps.append(i)
                    cum_pos = cum_neg = 0.0
            return cps

        keys = df2["_record_key"].to_list()
        if gf and gf in df2.columns:
            for gval, sub in df2.group_by(gf):
                gv = gval[0] if isinstance(gval, tuple) else gval
                vals = sub[nf].cast(pl.Float64, strict=False).to_list()
                sub_keys = sub["_record_key"].to_list()
                for cp in _cusum(vals):
                    if cp < len(sub_keys):
                        change_points.append({"group": str(gv),
                                              "record_key": sub_keys[cp],
                                              "value": vals[cp]})
        else:
            vals = df2[nf].cast(pl.Float64, strict=False).to_list()
            for cp in _cusum(vals):
                if cp < len(keys):
                    change_points.append({"record_key": keys[cp], "value": vals[cp]})
        flagged_keys = [c["record_key"] for c in change_points]
        flagged = df2.filter(pl.col("_record_key").is_in(flagged_keys))
        scores = [PerRecordScore(c["record_key"], 1.0,
                                f"CUSUM change-point (group={c.get('group','global')})")
                  for c in change_points]
        return DetectorResult(
            flagged=flagged,
            summary={"flagged_count": flagged.height,
                     "threshold_sigma": thr_sigma, "drift_pct": drift_pct,
                     "change_points": change_points[:200]},
            per_record_scores=scores,
        )


register(CompoundDetector())
register(ChangePointDetector())
