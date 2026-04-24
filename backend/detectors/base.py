from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

import polars as pl

from backend.models.enums import DetectorCategory, SubledgerType


@dataclass
class PerRecordScore:
    record_key: str
    score: float
    reason: str


@dataclass
class DetectorResult:
    flagged: pl.DataFrame
    summary: dict[str, Any] = field(default_factory=dict)
    per_record_scores: list[PerRecordScore] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class Detector(Protocol):
    name: str
    category: DetectorCategory
    description: str
    default_weight: float
    default_params: dict[str, Any]
    supported_subledgers: list[SubledgerType] | None

    def run(self, df: pl.DataFrame, params: dict[str, Any]) -> DetectorResult: ...


def canonicalise_params(params: dict[str, Any]) -> str:
    return json.dumps(params, sort_keys=True, separators=(",", ":"), default=str)


def hash_dataframe(df: pl.DataFrame) -> str:
    rows = df.height
    cols = ",".join(df.columns)
    sample = df.head(100).write_csv() if rows else ""
    schema = ",".join(f"{c}:{dt}" for c, dt in df.schema.items())
    h = hashlib.sha256()
    h.update(f"{rows}|{cols}|{schema}|{sample}".encode("utf-8"))
    return h.hexdigest()


def record_key(df: pl.DataFrame, idx: int) -> str:
    for candidate in ("record_id", "id", "row_id", "uuid"):
        if candidate in df.columns:
            v = df[candidate][idx]
            return str(v)
    return f"row:{idx}"


def add_key_column(df: pl.DataFrame) -> pl.DataFrame:
    if "_record_key" in df.columns:
        return df
    for candidate in ("record_id", "id", "row_id", "uuid"):
        if candidate in df.columns:
            return df.with_columns(pl.col(candidate).cast(pl.Utf8).alias("_record_key"))
    return df.with_row_index(name="_record_key").with_columns(
        ("row:" + pl.col("_record_key").cast(pl.Utf8)).alias("_record_key")
    )


class DetectorError(Exception):
    pass
