"""Reconciliation detectors — three-way match, GL/subledger recon, bank, intercompany."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import polars as pl

from backend.detectors.base import Detector, DetectorResult, PerRecordScore, add_key_column
from backend.detectors.catalog import register
from backend.models.enums import DetectorCategory, SubledgerType


@dataclass
class ThreeWayMatchDetector:
    """Validate PO + GR + Invoice agree within tolerance."""
    name: str = "three_way_match"
    category: DetectorCategory = DetectorCategory.RELATIONAL
    description: str = "PO + GR + invoice amounts agree within tolerance"
    default_weight: float = 1.4
    default_params: dict[str, Any] = field(
        default_factory=lambda: {
            "po_amount_field": "po_amount",
            "gr_amount_field": "gr_amount",
            "invoice_amount_field": "invoice_amount",
            "tolerance_pct": 2.0,
        }
    )
    supported_subledgers: list[SubledgerType] | None = None

    def run(self, df: pl.DataFrame, params: dict[str, Any]) -> DetectorResult:
        po, gr, inv = params["po_amount_field"], params["gr_amount_field"], params["invoice_amount_field"]
        tol = float(params.get("tolerance_pct", 2.0)) / 100.0
        for c in (po, gr, inv):
            if c not in df.columns:
                return DetectorResult(flagged=df.head(0),
                                      summary={"flagged_count": 0, "reason": f"missing:{c}"})
        df2 = add_key_column(df).with_columns([
            pl.col(po).cast(pl.Float64, strict=False).alias("_po"),
            pl.col(gr).cast(pl.Float64, strict=False).alias("_gr"),
            pl.col(inv).cast(pl.Float64, strict=False).alias("_inv"),
        ])
        df2 = df2.with_columns([
            ((pl.col("_po") - pl.col("_gr")).abs() /
             pl.col("_po").abs().clip(lower_bound=0.01)).alias("_d1"),
            ((pl.col("_gr") - pl.col("_inv")).abs() /
             pl.col("_gr").abs().clip(lower_bound=0.01)).alias("_d2"),
            ((pl.col("_po") - pl.col("_inv")).abs() /
             pl.col("_po").abs().clip(lower_bound=0.01)).alias("_d3"),
        ])
        flagged = df2.filter(
            (pl.col("_d1") > tol) | (pl.col("_d2") > tol) | (pl.col("_d3") > tol)
        )
        scores = [
            PerRecordScore(r["_record_key"], 1.0, f"PO/GR/Inv mismatch >{tol*100:.0f}%")
            for r in flagged.iter_rows(named=True)
        ]
        return DetectorResult(
            flagged=flagged.drop(["_po", "_gr", "_inv", "_d1", "_d2", "_d3"]),
            summary={"flagged_count": flagged.height, "tolerance_pct": tol * 100},
            per_record_scores=scores,
        )


@dataclass
class GlSubledgerReconDetector:
    name: str = "gl_subledger_recon"
    category: DetectorCategory = DetectorCategory.RELATIONAL
    description: str = "Sub-ledger total per GL account vs GL balance"
    default_weight: float = 1.0
    default_params: dict[str, Any] = field(
        default_factory=lambda: {
            "gl_account_field": "gl_account",
            "amount_field": "amount",
            "gl_balances": [],
            "tolerance_abs": 1.0,
        }
    )
    supported_subledgers: list[SubledgerType] | None = None

    def run(self, df: pl.DataFrame, params: dict[str, Any]) -> DetectorResult:
        ga, amt = params["gl_account_field"], params["amount_field"]
        balances = params.get("gl_balances") or []
        tol = float(params.get("tolerance_abs", 1.0))
        if ga not in df.columns or amt not in df.columns or not balances:
            return DetectorResult(flagged=df.head(0),
                                  summary={"flagged_count": 0, "reason": "missing_config"})
        sub = (df.with_columns(pl.col(amt).cast(pl.Float64, strict=False))
                 .group_by(ga).agg(pl.sum(amt).alias("_total")))
        bal_map = {b["gl_account"]: float(b["balance"]) for b in balances}
        breaches: list[dict] = []
        for row in sub.to_dicts():
            ledger_total = float(row.get("_total") or 0)
            book = float(bal_map.get(row[ga], 0))
            if abs(ledger_total - book) > tol:
                breaches.append({
                    "gl_account": row[ga],
                    "subledger_total": ledger_total,
                    "gl_balance": book,
                    "diff": ledger_total - book,
                })
        return DetectorResult(
            flagged=df.head(0),
            summary={"flagged_count": len(breaches), "tolerance_abs": tol,
                     "breaches": breaches[:50]},
        )


@dataclass
class BankReconciliationDetector:
    name: str = "bank_reconciliation"
    category: DetectorCategory = DetectorCategory.RELATIONAL
    description: str = "Bank statement vs GL cash account reconciliation"
    default_weight: float = 1.0
    default_params: dict[str, Any] = field(
        default_factory=lambda: {
            "bank_side": [],
            "amount_field": "amount",
            "ref_field": "reference",
            "tolerance_abs": 0.01,
        }
    )
    supported_subledgers: list[SubledgerType] | None = None

    def run(self, df: pl.DataFrame, params: dict[str, Any]) -> DetectorResult:
        amt_f, ref_f = params["amount_field"], params.get("ref_field", "reference")
        tol = float(params.get("tolerance_abs", 0.01))
        bank = params.get("bank_side") or []
        if amt_f not in df.columns or ref_f not in df.columns or not bank:
            return DetectorResult(flagged=df.head(0),
                                  summary={"flagged_count": 0, "reason": "missing_config"})
        df2 = add_key_column(df)
        book_keys: dict[tuple, str] = {}
        for r in df2.iter_rows(named=True):
            ref = str(r.get(ref_f, ""))
            amt = float(r.get(amt_f) or 0)
            book_keys[(ref, round(amt, 2))] = r["_record_key"]
        bank_keys = {(str(b.get("ref", "")), round(float(b.get("amount", 0)), 2)) for b in bank}
        unmatched_book = [book_keys[k] for k in book_keys if k not in bank_keys]
        unmatched_bank = list(bank_keys - set(book_keys.keys()))
        flagged = df2.filter(pl.col("_record_key").is_in(unmatched_book))
        scores = [PerRecordScore(k, 1.0, "no matching bank entry") for k in unmatched_book]
        return DetectorResult(
            flagged=flagged,
            summary={
                "flagged_count": flagged.height,
                "unmatched_book": len(unmatched_book),
                "unmatched_bank": len(unmatched_bank),
                "unmatched_bank_sample": [{"ref": r, "amount": a} for r, a in unmatched_bank[:20]],
            },
            per_record_scores=scores,
        )


@dataclass
class IntercompanyMatchingDetector:
    name: str = "intercompany_matching"
    category: DetectorCategory = DetectorCategory.RELATIONAL
    description: str = "Intercompany payables match receivables"
    default_weight: float = 1.1
    default_params: dict[str, Any] = field(
        default_factory=lambda: {
            "from_entity_field": "from_entity",
            "to_entity_field": "to_entity",
            "amount_field": "amount",
            "tolerance_pct": 0.5,
        }
    )
    supported_subledgers: list[SubledgerType] | None = None

    def run(self, df: pl.DataFrame, params: dict[str, Any]) -> DetectorResult:
        fe, te, amt = params["from_entity_field"], params["to_entity_field"], params["amount_field"]
        tol = float(params.get("tolerance_pct", 0.5)) / 100.0
        for c in (fe, te, amt):
            if c not in df.columns:
                return DetectorResult(flagged=df.head(0),
                                      summary={"flagged_count": 0, "reason": f"missing:{c}"})
        agg = (df.with_columns(pl.col(amt).cast(pl.Float64, strict=False))
                 .group_by([fe, te]).agg(pl.sum(amt).alias("_total")))
        totals = {(str(r[fe]), str(r[te])): float(r["_total"] or 0) for r in agg.to_dicts()}
        breaches: list[dict] = []
        checked: set[tuple] = set()
        for (a, b), val in totals.items():
            if (a, b) in checked or (b, a) in checked:
                continue
            checked.add((a, b))
            recip = totals.get((b, a), 0.0)
            denom = max(abs(val), abs(recip), 1e-3)
            if abs(abs(val) - abs(recip)) / denom > tol:
                breaches.append({
                    "from": a, "to": b, "outgoing": val, "incoming": recip,
                    "imbalance": abs(val) - abs(recip),
                })
        return DetectorResult(
            flagged=df.head(0),
            summary={"flagged_count": len(breaches), "tolerance_pct": tol * 100,
                     "imbalances": breaches[:50]},
        )


register(ThreeWayMatchDetector())
register(GlSubledgerReconDetector())
register(BankReconciliationDetector())
register(IntercompanyMatchingDetector())
