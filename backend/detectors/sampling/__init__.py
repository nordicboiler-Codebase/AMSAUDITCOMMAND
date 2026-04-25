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


@dataclass
class SampleEvaluatorDetector:
    """Project errors from a sample to the population (upper-error-limit /
    projected misstatement). Closes the sampling loop — auditors draw a
    sample, mark errors, and need to project. Mirrors ACL's EVALUATE.

    Two modes via `method`:
      - `attribute` (default): Clopper-Pearson upper bound on error rate;
        suitable for control testing.
      - `mus`: Stringer (cell-bound) projected misstatement for monetary-unit
        samples — sums tainting × sampling interval with conservative bounds.

    Inputs (one row per sampled record):
      - `error_field` — boolean / 0-1 flag
      - `book_value_field` (MUS only) — recorded amount
      - `audit_value_field` (MUS only) — auditor-determined correct amount
      - `population_size` (records)
      - `population_value` (MUS only) — sum of book values across population
      - `confidence` — 0.90 / 0.95 / 0.99
    Flags every error row + emits population-level numbers in the summary.
    """
    name: str = "sample_evaluator"
    category: DetectorCategory = DetectorCategory.STATISTICAL
    description: str = "Evaluate a sample — projects errors / misstatement to the population"
    default_weight: float = 0.0  # informational, doesn't push into ensemble
    default_params: dict[str, Any] = field(
        default_factory=lambda: {
            "method": "attribute",
            "error_field": "is_error",
            "book_value_field": "book_value",
            "audit_value_field": "audit_value",
            "population_size": 0,
            "population_value": 0.0,
            "confidence": 0.95,
        }
    )
    supported_subledgers: list[SubledgerType] | None = None

    def run(self, df: pl.DataFrame, params: dict[str, Any]) -> DetectorResult:
        from scipy import stats as sci_stats

        method = (params.get("method") or "attribute").lower()
        ef = params.get("error_field", "is_error")
        confidence = float(params.get("confidence", 0.95))
        alpha = 1.0 - confidence
        N = int(params.get("population_size", 0)) or df.height
        if ef not in df.columns:
            return DetectorResult(
                flagged=df.head(0),
                summary={"flagged_count": 0, "reason": f"missing:{ef}"},
            )
        df2 = add_key_column(df).with_columns(
            pl.col(ef).cast(pl.Int64, strict=False).fill_null(0).alias("_err")
        )
        n = df2.height
        x = int(df2["_err"].sum() or 0)
        flagged = df2.filter(pl.col("_err") > 0)

        if method == "mus":
            bf = params.get("book_value_field", "book_value")
            af = params.get("audit_value_field", "audit_value")
            pop_value = float(params.get("population_value", 0.0)) or 1.0
            if bf not in df.columns or af not in df.columns:
                return DetectorResult(
                    flagged=flagged,
                    summary={"flagged_count": flagged.height,
                             "reason": f"missing:{bf} or {af}"},
                )
            df3 = df2.with_columns([
                pl.col(bf).cast(pl.Float64, strict=False).fill_null(0).alias("_book"),
                pl.col(af).cast(pl.Float64, strict=False).fill_null(0).alias("_audit"),
            ]).with_columns(
                ((pl.col("_book") - pl.col("_audit"))
                 / pl.when(pl.col("_book") != 0)
                       .then(pl.col("_book")).otherwise(1.0)
                 ).alias("_taint")
            )
            sampling_interval = pop_value / max(n, 1)
            tained = df3.filter(pl.col("_err") > 0)["_taint"].to_list()
            tained_capped = [min(max(float(t), 0.0), 1.0) for t in tained]
            mle = sum(tained_capped) * sampling_interval
            precision = -math.log(max(alpha, 1e-9)) * sampling_interval
            sorted_taints = sorted(tained_capped, reverse=True)
            ual = mle + precision
            for k, t in enumerate(sorted_taints, start=1):
                u_k = sci_stats.gamma.ppf(confidence, k + 1)
                u_km1 = sci_stats.gamma.ppf(confidence, k)
                incr = max(float(u_k) - float(u_km1) - 1.0, 0.0)
                ual += incr * sampling_interval * t
            scores = [PerRecordScore(k, 1.0, "sampled error")
                      for k in flagged["_record_key"].to_list()]
            return DetectorResult(
                flagged=flagged,
                summary={
                    "method": "mus",
                    "flagged_count": flagged.height,
                    "sample_size": n,
                    "errors_in_sample": x,
                    "population_value": pop_value,
                    "sampling_interval": round(sampling_interval, 4),
                    "most_likely_error": round(mle, 2),
                    "upper_error_limit": round(ual, 2),
                    "confidence": confidence,
                },
                per_record_scores=scores,
            )

        # Attribute sampling — Clopper-Pearson upper bound, one-sided
        if x == 0:
            uel_rate = 1.0 - alpha ** (1.0 / max(n, 1))
        else:
            uel_rate = float(sci_stats.beta.ppf(1 - alpha, x + 1, n - x))
        projected_errors = uel_rate * N
        scores = [PerRecordScore(k, 1.0, "sampled error")
                  for k in flagged["_record_key"].to_list()]
        return DetectorResult(
            flagged=flagged,
            summary={
                "method": "attribute",
                "flagged_count": flagged.height,
                "sample_size": n,
                "errors_in_sample": x,
                "observed_rate": round(x / max(n, 1), 4),
                "upper_error_limit_rate": round(uel_rate, 4),
                "projected_errors_in_population": round(projected_errors, 2),
                "population_size": N,
                "confidence": confidence,
            },
            per_record_scores=scores,
        )


register(RandomSampleDetector())
register(StratifiedSampleDetector())
register(MonetaryUnitSampleDetector())
register(SampleSizeCalculatorDetector())
register(SampleEvaluatorDetector())
