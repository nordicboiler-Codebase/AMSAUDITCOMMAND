"""AML / KYC detectors — sanctions screening, PEP, cash structuring, vendor anomaly, lapping."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any

import polars as pl
from rapidfuzz import fuzz

from backend.detectors.base import Detector, DetectorResult, PerRecordScore, add_key_column
from backend.detectors.catalog import register
from backend.models.enums import DetectorCategory, SubledgerType


# Tiny seed list — production deployments inject real OFAC/UN/EU lists via the
# `watchlist` parameter. Names from public OFAC SDN sample, kept short here.
_DEFAULT_SANCTIONS = [
    "Vladimir Putin", "Bashar al-Assad", "Kim Jong-Un",
    "Hezbollah", "Al-Qaeda", "Wagner Group",
    "Tornado Cash", "Lazarus Group",
]
_DEFAULT_PEP = [
    "Mohammed bin Salman", "Recep Tayyip Erdogan", "Xi Jinping",
    "Joe Biden", "Emmanuel Macron",
]


def _fuzzy_match_any(value: str, watchlist: list[str], threshold: int) -> tuple[str, int] | None:
    if not value:
        return None
    best: tuple[str, int] | None = None
    for entry in watchlist:
        score = fuzz.token_set_ratio(value.lower(), entry.lower())
        if score >= threshold and (best is None or score > best[1]):
            best = (entry, score)
    return best


@dataclass
class SanctionsScreenDetector:
    name: str = "sanctions_screen"
    category: DetectorCategory = DetectorCategory.RELATIONAL
    description: str = "Fuzzy-match a name field against a sanctions watchlist"
    default_weight: float = 1.5
    default_params: dict[str, Any] = field(
        default_factory=lambda: {
            "name_field": "vendor_name",
            "watchlist": [],
            "threshold": 88,
            "use_default_list": True,
        }
    )
    supported_subledgers: list[SubledgerType] | None = None

    def run(self, df: pl.DataFrame, params: dict[str, Any]) -> DetectorResult:
        f = params.get("name_field", "")
        if f not in df.columns:
            return DetectorResult(flagged=df.head(0),
                                  summary={"flagged_count": 0, "reason": "missing_field"})
        watchlist = list(params.get("watchlist") or [])
        if params.get("use_default_list", True):
            watchlist = watchlist + _DEFAULT_SANCTIONS
        threshold = int(params.get("threshold", 88))
        df2 = add_key_column(df)
        flagged_keys: list[str] = []
        reasons: dict[str, str] = {}
        for r in df2.iter_rows(named=True):
            value = str(r.get(f, "") or "")
            hit = _fuzzy_match_any(value, watchlist, threshold)
            if hit:
                flagged_keys.append(r["_record_key"])
                reasons[r["_record_key"]] = f"matches '{hit[0]}' ({hit[1]}%)"
        flagged = df2.filter(pl.col("_record_key").is_in(flagged_keys))
        scores = [PerRecordScore(k, 1.0, reasons[k]) for k in flagged_keys]
        return DetectorResult(
            flagged=flagged,
            summary={"flagged_count": flagged.height, "watchlist_size": len(watchlist),
                     "threshold": threshold},
            per_record_scores=scores,
        )


@dataclass
class PepScreenDetector:
    name: str = "pep_screen"
    category: DetectorCategory = DetectorCategory.RELATIONAL
    description: str = "Match a name field against a Politically Exposed Persons list"
    default_weight: float = 1.3
    default_params: dict[str, Any] = field(
        default_factory=lambda: {
            "name_field": "customer_name",
            "watchlist": [],
            "threshold": 88,
            "use_default_list": True,
        }
    )
    supported_subledgers: list[SubledgerType] | None = None

    def run(self, df: pl.DataFrame, params: dict[str, Any]) -> DetectorResult:
        f = params.get("name_field", "")
        if f not in df.columns:
            return DetectorResult(flagged=df.head(0),
                                  summary={"flagged_count": 0, "reason": "missing_field"})
        watchlist = list(params.get("watchlist") or [])
        if params.get("use_default_list", True):
            watchlist = watchlist + _DEFAULT_PEP
        threshold = int(params.get("threshold", 88))
        df2 = add_key_column(df)
        flagged_keys: list[str] = []
        reasons: dict[str, str] = {}
        for r in df2.iter_rows(named=True):
            value = str(r.get(f, "") or "")
            hit = _fuzzy_match_any(value, watchlist, threshold)
            if hit:
                flagged_keys.append(r["_record_key"])
                reasons[r["_record_key"]] = f"PEP match: '{hit[0]}' ({hit[1]}%)"
        flagged = df2.filter(pl.col("_record_key").is_in(flagged_keys))
        scores = [PerRecordScore(k, 1.0, reasons[k]) for k in flagged_keys]
        return DetectorResult(
            flagged=flagged,
            summary={"flagged_count": flagged.height, "watchlist_size": len(watchlist),
                     "threshold": threshold},
            per_record_scores=scores,
        )


@dataclass
class CashStructuringDetector:
    """Detect transactions structured to evade reporting thresholds (smurfing).

    Looks for patterns where the same actor (account/person) splits a large
    transaction into multiple smaller ones over a short window, each just below
    a reporting threshold (default $10,000).
    """
    name: str = "cash_structuring"
    category: DetectorCategory = DetectorCategory.BENFORD_FRAUD
    description: str = "Multiple sub-threshold transactions by same actor in a short window"
    default_weight: float = 1.4
    default_params: dict[str, Any] = field(
        default_factory=lambda: {
            "actor_field": "account_id",
            "amount_field": "amount",
            "date_field": "date",
            "threshold": 10000.0,
            "lower_band_pct": 0.85,
            "window_days": 7,
            "min_count": 3,
        }
    )
    supported_subledgers: list[SubledgerType] | None = None

    def run(self, df: pl.DataFrame, params: dict[str, Any]) -> DetectorResult:
        af, amf, dfld = params["actor_field"], params["amount_field"], params["date_field"]
        thr = float(params["threshold"])
        band = float(params.get("lower_band_pct", 0.85))
        window = int(params.get("window_days", 7))
        min_n = int(params.get("min_count", 3))
        for c in (af, amf, dfld):
            if c not in df.columns:
                return DetectorResult(flagged=df.head(0),
                                      summary={"flagged_count": 0, "reason": f"missing:{c}"})
        df2 = add_key_column(df).with_columns([
            pl.col(amf).cast(pl.Float64, strict=False).alias("_amt"),
            pl.col(dfld).cast(pl.Date, strict=False).alias("_d"),
        ])
        # Filter to suspicious band
        suspect = df2.filter(
            (pl.col("_amt") >= thr * band) & (pl.col("_amt") < thr)
        )
        # Per actor, look for ≥ min_n events within window_days
        flagged_keys: list[str] = []
        reasons: dict[str, str] = {}
        for actor, sub in suspect.sort("_d").group_by(af):
            actor_val = actor[0] if isinstance(actor, tuple) else actor
            rows = sub.to_dicts()
            for i, r in enumerate(rows):
                cluster = [r]
                for j in range(i + 1, len(rows)):
                    if not rows[j]["_d"]:
                        continue
                    days = (rows[j]["_d"] - r["_d"]).days
                    if days <= window:
                        cluster.append(rows[j])
                    else:
                        break
                if len(cluster) >= min_n:
                    total = sum(c["_amt"] for c in cluster)
                    for c in cluster:
                        k = c["_record_key"]
                        flagged_keys.append(k)
                        reasons[k] = (f"actor {actor_val}: {len(cluster)} sub-threshold txns "
                                     f"in {window}d totalling {total:.2f}")
                    break
        unique_keys = list(set(flagged_keys))
        flagged = df2.filter(pl.col("_record_key").is_in(unique_keys))
        scores = [PerRecordScore(k, 1.0, reasons[k]) for k in unique_keys]
        return DetectorResult(
            flagged=flagged.drop(["_amt", "_d"]),
            summary={"flagged_count": flagged.height, "threshold": thr,
                     "lower_band_pct": band * 100, "window_days": window, "min_count": min_n},
            per_record_scores=scores,
        )


@dataclass
class VendorMasterAnomalyDetector:
    """Newly-onboarded vendors with disproportionate invoice volume in their first month."""
    name: str = "vendor_master_anomaly"
    category: DetectorCategory = DetectorCategory.RELATIONAL
    description: str = "New vendors with high invoice volume in their first 30 days"
    default_weight: float = 1.2
    default_params: dict[str, Any] = field(
        default_factory=lambda: {
            "vendor_field": "vendor_id",
            "amount_field": "amount",
            "date_field": "payment_date",
            "first_seen_threshold_days": 30,
            "min_invoices": 5,
            "min_value": 50000.0,
        }
    )
    supported_subledgers: list[SubledgerType] | None = field(
        default_factory=lambda: [SubledgerType.ACCOUNTS_PAYABLE, SubledgerType.PROCUREMENT]
    )

    def run(self, df: pl.DataFrame, params: dict[str, Any]) -> DetectorResult:
        vf, amf, dfld = params["vendor_field"], params["amount_field"], params["date_field"]
        first_window = int(params.get("first_seen_threshold_days", 30))
        min_n = int(params.get("min_invoices", 5))
        min_val = float(params.get("min_value", 50000.0))
        for c in (vf, amf, dfld):
            if c not in df.columns:
                return DetectorResult(flagged=df.head(0),
                                      summary={"flagged_count": 0, "reason": f"missing:{c}"})
        df2 = add_key_column(df).with_columns([
            pl.col(amf).cast(pl.Float64, strict=False).alias("_amt"),
            pl.col(dfld).cast(pl.Date, strict=False).alias("_d"),
        ]).filter(pl.col("_d").is_not_null())
        flagged_keys: list[str] = []
        reasons: dict[str, str] = {}
        for vid, sub in df2.group_by(vf):
            vendor_val = vid[0] if isinstance(vid, tuple) else vid
            sub = sub.sort("_d")
            first_d = sub["_d"].min()
            if first_d is None:
                continue
            cutoff = first_d + timedelta(days=first_window)
            early = sub.filter(pl.col("_d") <= cutoff)
            total = float(early["_amt"].sum() or 0)
            n = early.height
            if n >= min_n and total >= min_val:
                for k in early["_record_key"].to_list():
                    flagged_keys.append(k)
                    reasons[k] = (f"new vendor {vendor_val}: {n} invoices, "
                                 f"{total:.0f} in first {first_window}d")
        flagged = df2.filter(pl.col("_record_key").is_in(flagged_keys))
        scores = [PerRecordScore(k, 1.0, reasons[k]) for k in flagged_keys]
        return DetectorResult(
            flagged=flagged.drop(["_amt", "_d"]),
            summary={"flagged_count": flagged.height, "first_window_days": first_window,
                     "min_invoices": min_n, "min_value": min_val},
            per_record_scores=scores,
        )


@dataclass
class LappingDetectionDetector:
    """Lapping fraud: payments received from one customer used to cover prior fraud
    against another customer.

    Pattern: invoice receivable date and payment date diverge by >X days, and
    payment amounts cross customer boundaries to cover gaps.
    """
    name: str = "lapping_detection"
    category: DetectorCategory = DetectorCategory.BENFORD_FRAUD
    description: str = "AR lapping: payments arriving late + applied across customer boundaries"
    default_weight: float = 1.3
    default_params: dict[str, Any] = field(
        default_factory=lambda: {
            "customer_field": "customer_id",
            "invoice_date_field": "invoice_date",
            "payment_date_field": "payment_date",
            "amount_field": "invoice_amount",
            "applied_to_field": "ref_invoice_no",
            "lag_days_threshold": 45,
        }
    )
    supported_subledgers: list[SubledgerType] | None = field(
        default_factory=lambda: [SubledgerType.ACCOUNTS_RECEIVABLE]
    )

    def run(self, df: pl.DataFrame, params: dict[str, Any]) -> DetectorResult:
        cf, idf, pdf = params["customer_field"], params["invoice_date_field"], params["payment_date_field"]
        atf = params.get("applied_to_field", "")
        amf = params.get("amount_field", "invoice_amount")
        lag = int(params.get("lag_days_threshold", 45))
        for c in (cf, idf, pdf, amf):
            if c not in df.columns:
                return DetectorResult(flagged=df.head(0),
                                      summary={"flagged_count": 0, "reason": f"missing:{c}"})
        df2 = add_key_column(df).with_columns([
            pl.col(idf).cast(pl.Date, strict=False).alias("_inv_d"),
            pl.col(pdf).cast(pl.Date, strict=False).alias("_pay_d"),
            pl.col(amf).cast(pl.Float64, strict=False).alias("_amt"),
        ])
        df2 = df2.with_columns(
            (pl.col("_pay_d") - pl.col("_inv_d")).dt.total_days().alias("_lag")
        )
        # Pattern A: payment received but applied to a different customer's invoice.
        per_customer_lagged: dict[str, int] = defaultdict(int)
        flagged_keys: list[str] = []
        reasons: dict[str, str] = {}
        for r in df2.iter_rows(named=True):
            l = r.get("_lag")
            if l is None or l < lag:
                continue
            applied_to = r.get(atf) if atf else None
            same_customer = True
            if applied_to:
                # Look up the original invoice
                orig = df2.filter(pl.col(atf) == applied_to).head(1).to_dicts()
                if orig:
                    same_customer = orig[0].get(cf) == r.get(cf)
            per_customer_lagged[str(r.get(cf, ""))] += 1
            flagged_keys.append(r["_record_key"])
            reasons[r["_record_key"]] = (
                f"payment {l}d after invoice"
                + ("; cross-customer application" if not same_customer else "")
            )
        # Filter to customers with multiple lagged payments (signal vs noise)
        suspect_customers = {c for c, n in per_customer_lagged.items() if n >= 2}
        keys_in_suspect = [
            k for k in flagged_keys
            if str(df2.filter(pl.col("_record_key") == k)[cf][0]) in suspect_customers
        ] if suspect_customers else flagged_keys
        flagged = df2.filter(pl.col("_record_key").is_in(keys_in_suspect))
        scores = [PerRecordScore(k, 1.0, reasons[k]) for k in keys_in_suspect]
        return DetectorResult(
            flagged=flagged.drop(["_inv_d", "_pay_d", "_amt", "_lag"]),
            summary={"flagged_count": flagged.height, "lag_days_threshold": lag,
                     "suspect_customers": len(suspect_customers)},
            per_record_scores=scores,
        )


register(SanctionsScreenDetector())
register(PepScreenDetector())
register(CashStructuringDetector())
register(VendorMasterAnomalyDetector())
register(LappingDetectionDetector())
