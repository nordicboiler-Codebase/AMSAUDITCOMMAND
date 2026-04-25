"""Sampling detectors — random, stratified, monetary unit, sample-size calculator.

These don't "find fraud" themselves; they produce a tagged subset of a population
that auditors then test substantively. Output `flagged` is the sample.
"""
from __future__ import annotations

import math
import random as _rnd
from dataclasses import dataclass, field
from typing import Any

import polars as pl

from backend.detectors.base import Detector, DetectorResult, PerRecordScore, add_key_column
from backend.detectors.catalog import register
from backend.models.enums import DetectorCategory, SubledgerType


@dataclass
class RandomSampleDetector:
    name: str = "random_sample"
    category: DetectorCategory = DetectorCategory.STATISTICAL
    description: str = "Simple random sample of N records"
    default_weight: float = 0.0  # sample is not a finding
    default_params: dict[str, Any] = field(default_factory=lambda: {"n": 50, "seed": 42})
    supported_subledgers: list[SubledgerType] | None = None

    def run(self, df: pl.DataFrame, params: dict[str, Any]) -> DetectorResult:
        n = min(int(params.get("n", 50)), df.height)
        seed = int(params.get("seed", 42))
        df2 = add_key_column(df)
        sample = df2.sample(n=n, seed=seed)
        scores = [PerRecordScore(k, 1.0, "sampled (random)") for k in sample["_record_key"].to_list()]
        return DetectorResult(
            flagged=sample,
            summary={"flagged_count": sample.height, "method": "simple_random",
                     "population": df.height, "n": n, "seed": seed},
            per_record_scores=scores,
        )


@dataclass
class StratifiedSampleDetector:
    name: str = "stratified_sample"
    category: DetectorCategory = DetectorCategory.STATISTICAL
    description: str = "Stratified random sample — k records per group_field value"
    default_weight: float = 0.0
    default_params: dict[str, Any] = field(
        default_factory=lambda: {"group_field": "", "per_stratum": 5, "seed": 42}
    )
    supported_subledgers: list[SubledgerType] | None = None

    def run(self, df: pl.DataFrame, params: dict[str, Any]) -> DetectorResult:
        gf = params.get("group_field", "")
        per = int(params.get("per_stratum", 5))
        seed = int(params.get("seed", 42))
        if gf not in df.columns:
            return DetectorResult(flagged=df.head(0),
                                  summary={"flagged_count": 0, "reason": "group_field_missing"})
        df2 = add_key_column(df)
        rng = _rnd.Random(seed)
        keys: list[str] = []
        strata = df2.group_by(gf)
        stratum_summary: list[dict] = []
        for gval, sub in strata:
            v = gval[0] if isinstance(gval, tuple) else gval
            picks = sub["_record_key"].to_list()
            rng.shuffle(picks)
            picked = picks[:per]
            keys.extend(picked)
            stratum_summary.append({"stratum": str(v), "size": sub.height, "sampled": len(picked)})
        sample = df2.filter(pl.col("_record_key").is_in(keys))
        scores = [PerRecordScore(k, 1.0, f"sampled (stratified by {gf})") for k in keys]
        return DetectorResult(
            flagged=sample,
            summary={"flagged_count": sample.height, "method": "stratified",
                     "group_field": gf, "per_stratum": per, "strata": stratum_summary},
            per_record_scores=scores,
        )


@dataclass
class MonetaryUnitSampleDetector:
    """Probability-Proportional-to-Size (PPS) sample weighted by an amount column.

    Each record's selection probability is proportional to its absolute amount.
    The gold-standard substantive test for AP/AR populations under ISA 530.
    """
    name: str = "monetary_unit_sample"
    category: DetectorCategory = DetectorCategory.STATISTICAL
    description: str = "Monetary Unit Sample (PPS) — sample weighted by amount"
    default_weight: float = 0.0
    default_params: dict[str, Any] = field(
        default_factory=lambda: {"amount_field": "amount", "n": 50, "seed": 42}
    )
    supported_subledgers: list[SubledgerType] | None = None

    def run(self, df: pl.DataFrame, params: dict[str, Any]) -> DetectorResult:
        f = params.get("amount_field", "amount")
        n = int(params.get("n", 50))
        seed = int(params.get("seed", 42))
        if f not in df.columns:
            return DetectorResult(flagged=df.head(0),
                                  summary={"flagged_count": 0, "reason": "amount_field_missing"})
        df2 = add_key_column(df)
        amounts = df2[f].cast(pl.Float64, strict=False).abs().fill_null(0).to_list()
        keys = df2["_record_key"].to_list()
        total = sum(amounts) or 1.0
        rng = _rnd.Random(seed)
        # Systematic PPS: pick interval = total/n, random start in [0, interval)
        interval = total / max(n, 1)
        cursor = rng.uniform(0, interval)
        cum = 0.0
        sampled_keys: list[str] = []
        for k, a in zip(keys, amounts):
            cum += a
            while cum >= cursor and len(sampled_keys) < n:
                sampled_keys.append(k)
                cursor += interval
        sample = df2.filter(pl.col("_record_key").is_in(sampled_keys))
        coverage = sum(amounts[i] for i in range(len(keys)) if keys[i] in set(sampled_keys))
        scores = [PerRecordScore(k, 1.0, "MUS-selected (PPS)") for k in sampled_keys]
        return DetectorResult(
            flagged=sample,
            summary={"flagged_count": sample.height, "method": "monetary_unit",
                     "n": n, "population": df.height, "total_value": total,
                     "sample_value": coverage, "coverage_pct": (coverage / total) if total else 0},
            per_record_scores=scores,
        )


@dataclass
class SampleSizeCalculatorDetector:
    """Computes required sample size given population, confidence, expected error.

    Uses the standard attributes-sampling formula:
        n = (z^2 * p * (1-p)) / e^2 , finite-pop corrected.
    For substantive testing we expose this as a helper — `flagged` is empty.
    """
    name: str = "sample_size_calculator"
    category: DetectorCategory = DetectorCategory.STATISTICAL
    description: str = "Compute required sample size for substantive testing"
    default_weight: float = 0.0
    default_params: dict[str, Any] = field(
        default_factory=lambda: {"confidence": 0.95, "tolerable_error_pct": 5.0,
                                 "expected_error_pct": 1.0}
    )
    supported_subledgers: list[SubledgerType] | None = None

    def run(self, df: pl.DataFrame, params: dict[str, Any]) -> DetectorResult:
        conf = float(params.get("confidence", 0.95))
        tol = float(params.get("tolerable_error_pct", 5.0)) / 100.0
        exp = float(params.get("expected_error_pct", 1.0)) / 100.0
        z = {0.90: 1.645, 0.95: 1.96, 0.99: 2.576}.get(round(conf, 2), 1.96)
        n0 = (z * z * exp * (1 - exp)) / max(tol * tol, 1e-9)
        N = df.height or 1
        n = math.ceil(n0 / (1 + n0 / N))
        return DetectorResult(
            flagged=df.head(0),
            summary={
                "flagged_count": 0,
                "population": N,
                "confidence_level": conf,
                "tolerable_error_pct": tol * 100,
                "expected_error_pct": exp * 100,
                "z_score": z,
                "infinite_pop_size": math.ceil(n0),
                "required_sample_size": n,
            },
        )


register(RandomSampleDetector())
register(StratifiedSampleDetector())
register(MonetaryUnitSampleDetector())
register(SampleSizeCalculatorDetector())
