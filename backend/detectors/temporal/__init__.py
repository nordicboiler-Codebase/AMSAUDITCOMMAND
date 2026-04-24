from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import Any

import polars as pl

from backend.detectors.base import Detector, DetectorResult, PerRecordScore, add_key_column
from backend.detectors.catalog import register
from backend.models.enums import DetectorCategory, SubledgerType

UAE_HOLIDAYS: set[date] = {
    date(2025, 1, 1),
    date(2025, 3, 31), date(2025, 4, 1), date(2025, 4, 2),
    date(2025, 6, 5), date(2025, 6, 6), date(2025, 6, 7), date(2025, 6, 8),
    date(2025, 6, 26),
    date(2025, 9, 4),
    date(2025, 12, 2), date(2025, 12, 3),
    date(2026, 1, 1),
    date(2026, 3, 20), date(2026, 3, 21), date(2026, 3, 22),
    date(2026, 5, 26),
    date(2026, 12, 2), date(2026, 12, 3),
}

HOLIDAY_SETS: dict[str, set[date]] = {"uae": UAE_HOLIDAYS}


@dataclass
class WeekendTransactionsDetector:
    name: str = "weekend_transactions"
    category: DetectorCategory = DetectorCategory.TEMPORAL
    description: str = "Friday/Saturday or holiday posting"
    default_weight: float = 1.0
    default_params: dict[str, Any] = field(
        default_factory=lambda: {"date_field": "", "weekend_days": [5, 6], "holidays_ref": "uae",
                                 "include_holidays": False, "filter_field": None, "filter_value": None}
    )
    supported_subledgers: list[SubledgerType] | None = None

    def run(self, df: pl.DataFrame, params: dict[str, Any]) -> DetectorResult:
        dfield = params["date_field"]
        if dfield not in df.columns:
            return DetectorResult(flagged=df.head(0), summary={"flagged_count": 0, "reason": "field_not_found"})
        weekend_days = set(params.get("weekend_days") or [5, 6])
        holidays_ref = params.get("holidays_ref")
        holidays = HOLIDAY_SETS.get(holidays_ref, set()) if params.get("include_holidays") else set()
        df2 = add_key_column(df)
        filter_field = params.get("filter_field")
        filter_value = params.get("filter_value")
        if filter_field and filter_field in df.columns and filter_value is not None:
            df2 = df2.filter(pl.col(filter_field) == filter_value)
        date_col = df2[dfield].cast(pl.Date, strict=False)
        dates = date_col.to_list()
        keys = df2["_record_key"].to_list()
        flagged_keys: list[str] = []
        reasons: dict[str, str] = {}
        for k, d in zip(keys, dates):
            if d is None:
                continue
            wd = d.weekday() if hasattr(d, "weekday") else None
            if wd is not None and wd in weekend_days:
                flagged_keys.append(k)
                reasons[k] = f"weekend posting ({d.strftime('%A') if hasattr(d, 'strftime') else d})"
            elif d in holidays:
                flagged_keys.append(k)
                reasons[k] = f"holiday posting ({d})"
        flagged = df2.filter(pl.col("_record_key").is_in(flagged_keys))
        scores = [PerRecordScore(k, 1.0, reasons[k]) for k in flagged_keys]
        return DetectorResult(
            flagged=flagged,
            summary={"flagged_count": flagged.height, "date_field": dfield, "holidays_checked": bool(holidays)},
            per_record_scores=scores,
        )


@dataclass
class AfterHoursDetector:
    name: str = "after_hours"
    category: DetectorCategory = DetectorCategory.TEMPORAL
    description: str = "Outside business hours"
    default_weight: float = 0.8
    default_params: dict[str, Any] = field(
        default_factory=lambda: {"datetime_field": "", "business_start": "08:00", "business_end": "18:00"}
    )
    supported_subledgers: list[SubledgerType] | None = None

    def run(self, df: pl.DataFrame, params: dict[str, Any]) -> DetectorResult:
        f = params["datetime_field"]
        if f not in df.columns:
            return DetectorResult(flagged=df.head(0), summary={"flagged_count": 0, "reason": "field_not_found"})
        start = time.fromisoformat(params.get("business_start", "08:00"))
        end = time.fromisoformat(params.get("business_end", "18:00"))
        df2 = add_key_column(df)
        col = df2[f].cast(pl.Datetime, strict=False)
        times = col.to_list()
        keys = df2["_record_key"].to_list()
        flagged_keys: list[str] = []
        reasons: dict[str, str] = {}
        for k, t in zip(keys, times):
            if t is None:
                continue
            tm = t.time() if hasattr(t, "time") else None
            if tm is None:
                continue
            if tm < start or tm > end:
                flagged_keys.append(k)
                reasons[k] = f"posted at {tm.isoformat()} (outside {start}-{end})"
        flagged = df2.filter(pl.col("_record_key").is_in(flagged_keys))
        scores = [PerRecordScore(k, 1.0, reasons[k]) for k in flagged_keys]
        return DetectorResult(
            flagged=flagged,
            summary={"flagged_count": flagged.height, "business_start": str(start), "business_end": str(end)},
            per_record_scores=scores,
        )


@dataclass
class PeriodEndSpikeDetector:
    name: str = "period_end_spike"
    category: DetectorCategory = DetectorCategory.TEMPORAL
    description: str = "Activity spike near period close"
    default_weight: float = 0.9
    default_params: dict[str, Any] = field(
        default_factory=lambda: {"date_field": "", "period_close_date": None, "window_days": 2}
    )
    supported_subledgers: list[SubledgerType] | None = None

    def run(self, df: pl.DataFrame, params: dict[str, Any]) -> DetectorResult:
        f = params["date_field"]
        close = params.get("period_close_date")
        window = int(params.get("window_days", 2))
        if f not in df.columns:
            return DetectorResult(flagged=df.head(0), summary={"flagged_count": 0, "reason": "field_not_found"})
        df2 = add_key_column(df)
        if close is None:
            close_date = df2[f].cast(pl.Date, strict=False).max()
            if close_date is None:
                return DetectorResult(flagged=df.head(0), summary={"flagged_count": 0, "reason": "no_dates"})
        else:
            close_date = datetime.fromisoformat(close).date() if isinstance(close, str) else close
        lo = close_date - timedelta(days=window)
        mask = (df2[f].cast(pl.Date, strict=False) >= lo) & (df2[f].cast(pl.Date, strict=False) <= close_date)
        flagged = df2.filter(mask)
        scores = [
            PerRecordScore(k, 1.0, f"within {window}d of period close {close_date}")
            for k in flagged["_record_key"].to_list()
        ]
        return DetectorResult(
            flagged=flagged,
            summary={"flagged_count": flagged.height, "close_date": close_date.isoformat(), "window_days": window},
            per_record_scores=scores,
        )


@dataclass
class DateAnomalyDetector:
    name: str = "date_anomaly"
    category: DetectorCategory = DetectorCategory.TEMPORAL
    description: str = "Backdated, future-dated, or impossible-date records"
    default_weight: float = 1.0
    default_params: dict[str, Any] = field(
        default_factory=lambda: {"date_field": "", "check_type": "future", "compare_field": None,
                                 "reference_date": None}
    )
    supported_subledgers: list[SubledgerType] | None = None

    def run(self, df: pl.DataFrame, params: dict[str, Any]) -> DetectorResult:
        f = params["date_field"]
        check = params.get("check_type", "future")
        compare = params.get("compare_field")
        ref = params.get("reference_date")
        if f not in df.columns:
            return DetectorResult(flagged=df.head(0), summary={"flagged_count": 0, "reason": "field_not_found"})
        df2 = add_key_column(df)
        today = date.today()
        ref_date = datetime.fromisoformat(ref).date() if isinstance(ref, str) else (ref or today)
        col = df2[f].cast(pl.Date, strict=False)
        if check == "future":
            mask = col > ref_date
            reason = f"future-dated beyond {ref_date}"
        elif check == "backdated":
            if compare and compare in df.columns:
                cmp_col = df2[compare].cast(pl.Date, strict=False)
                mask = col < cmp_col
                reason = f"{f} < {compare}"
            else:
                mask = col < ref_date - timedelta(days=365)
                reason = "backdated > 1y"
        elif check == "impossible":
            mask = col.is_null()
            reason = "invalid date"
        else:
            return DetectorResult(flagged=df.head(0), summary={"flagged_count": 0, "reason": "unknown_check"})
        flagged = df2.filter(mask)
        scores = [PerRecordScore(k, 1.0, reason) for k in flagged["_record_key"].to_list()]
        return DetectorResult(
            flagged=flagged,
            summary={"flagged_count": flagged.height, "check_type": check, "reference_date": ref_date.isoformat()},
            per_record_scores=scores,
        )


register(WeekendTransactionsDetector())
register(AfterHoursDetector())
register(PeriodEndSpikeDetector())
register(DateAnomalyDetector())
