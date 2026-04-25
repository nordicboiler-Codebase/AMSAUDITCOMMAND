"""Embedding-style similarity detectors using rapidfuzz token-set scorer."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import polars as pl
from rapidfuzz import fuzz, process

from backend.detectors.base import Detector, DetectorResult, PerRecordScore, add_key_column
from backend.detectors.catalog import register
from backend.models.enums import DetectorCategory, SubledgerType


@dataclass
class NameEmbeddingDetector:
    name: str = "name_embedding"
    category: DetectorCategory = DetectorCategory.TEXT
    description: str = "Token-set fuzzy match — catches reorderings and abbreviations"
    default_weight: float = 0.7
    default_params: dict[str, Any] = field(
        default_factory=lambda: {"name_field": "vendor_name", "threshold": 88, "max_compare": 5000}
    )
    supported_subledgers: list[SubledgerType] | None = None

    def run(self, df: pl.DataFrame, params: dict[str, Any]) -> DetectorResult:
        f = params.get("name_field", "")
        thr = int(params.get("threshold", 88))
        max_compare = int(params.get("max_compare", 5000))
        if f not in df.columns:
            return DetectorResult(flagged=df.head(0), summary={"flagged_count": 0, "reason": "missing_field"})
        df2 = add_key_column(df)
        names = df2[f].cast(pl.Utf8, strict=False).fill_null("").to_list()
        keys = df2["_record_key"].to_list()
        n = min(len(names), max_compare)
        groups: list[set[int]] = []
        for i in range(n):
            if not names[i]:
                continue
            matches = process.extract(
                names[i], names[:n], scorer=fuzz.token_set_ratio,
                score_cutoff=thr, limit=20,
            )
            members = {i}
            for _, score, idx in matches:
                if idx != i:
                    members.add(idx)
            if len(members) > 1:
                merged = False
                for g in groups:
                    if g & members:
                        g.update(members)
                        merged = True
                        break
                if not merged:
                    groups.append(members)
        flagged_keys: list[str] = []
        reasons: dict[str, str] = {}
        for g in groups:
            sample_name = names[next(iter(g))]
            for idx in g:
                k = keys[idx]
                flagged_keys.append(k)
                reasons[k] = f"in name-similarity group of {len(g)} (~'{sample_name}')"
        flagged = df2.filter(pl.col("_record_key").is_in(flagged_keys))
        scores = [PerRecordScore(k, 1.0, reasons[k]) for k in flagged_keys]
        return DetectorResult(
            flagged=flagged,
            summary={"flagged_count": flagged.height, "groups": len(groups), "threshold": thr},
            per_record_scores=scores,
        )


register(NameEmbeddingDetector())
