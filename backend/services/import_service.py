from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

import polars as pl
from charset_normalizer import from_bytes
from sqlalchemy.orm import Session

from backend.core.config import get_settings
from backend.models import AuditAction, Dataset, SubledgerType
from backend.services import audit_log

settings = get_settings()


@dataclass
class ImportResult:
    dataset_id: uuid.UUID
    record_count: int
    source_hash: str
    parquet_path: str
    control_totals: dict
    schema: dict


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _detect_encoding(sample: bytes) -> str:
    guess = from_bytes(sample).best()
    return guess.encoding if guess else "utf-8"


def _sniff_delimiter(sample: str) -> str:
    candidates = [",", ";", "\t", "|"]
    first_line = sample.splitlines()[0] if sample else ""
    return max(candidates, key=first_line.count)


def _load_dataframe(path: Path) -> pl.DataFrame:
    suffix = path.suffix.lower()
    if suffix in (".xlsx", ".xls"):
        import pandas as pd

        pdf = pd.read_excel(path)
        return pl.from_pandas(pdf)
    if suffix == ".parquet":
        return pl.read_parquet(path)
    with open(path, "rb") as f:
        head = f.read(8192)
    encoding = _detect_encoding(head)
    try:
        text_head = head.decode(encoding, errors="replace")
    except LookupError:
        text_head = head.decode("utf-8", errors="replace")
    delim = _sniff_delimiter(text_head)
    return pl.read_csv(path, separator=delim, encoding=encoding, infer_schema_length=5000, try_parse_dates=True)


def _control_totals(df: pl.DataFrame) -> dict[str, Any]:
    totals: dict[str, Any] = {"record_count": df.height, "fields": {}}
    for col, dtype in df.schema.items():
        field: dict[str, Any] = {"dtype": str(dtype)}
        if dtype.is_numeric():
            field["sum"] = float(df[col].fill_null(0).sum() or 0)
            field["min"] = float(df[col].min() or 0) if df.height else None
            field["max"] = float(df[col].max() or 0) if df.height else None
            field["null_count"] = int(df[col].null_count())
        elif dtype in (pl.Date, pl.Datetime):
            mn = df[col].min()
            mx = df[col].max()
            field["min"] = mn.isoformat() if isinstance(mn, (date, datetime)) else str(mn) if mn else None
            field["max"] = mx.isoformat() if isinstance(mx, (date, datetime)) else str(mx) if mx else None
        else:
            field["null_count"] = int(df[col].null_count())
            field["unique_count"] = int(df[col].n_unique())
        totals["fields"][col] = field
    return totals


def import_dataset(
    db: Session,
    *,
    file_path: Path,
    source_filename: str,
    project_id: uuid.UUID,
    name: str,
    subledger_type: SubledgerType,
    user_id: uuid.UUID,
    description: str | None = None,
) -> ImportResult:
    settings.ensure_dirs()
    source_hash = _sha256(file_path)

    df = _load_dataframe(file_path)
    record_count = df.height
    schema_json = {c: str(dt) for c, dt in df.schema.items()}
    totals = _control_totals(df)

    parquet_name = f"{uuid.uuid4()}.parquet"
    parquet_path = settings.parquet_dir / parquet_name
    df.write_parquet(parquet_path)

    dataset = Dataset(
        project_id=project_id,
        name=name,
        source_filename=source_filename,
        source_hash_sha256=source_hash,
        record_count=record_count,
        control_totals=totals,
        schema_json=schema_json,
        subledger_type=subledger_type,
        parquet_path=str(parquet_path),
        imported_by=user_id,
        description=description,
    )
    db.add(dataset)
    db.flush()

    audit_log.log_action(
        db,
        user_id=user_id,
        action=AuditAction.IMPORT,
        entity_type="dataset",
        entity_id=str(dataset.id),
        project_id=project_id,
        details={
            "source_filename": source_filename,
            "source_hash": source_hash,
            "record_count": record_count,
            "subledger_type": subledger_type.value,
        },
    )
    db.commit()

    try:
        from backend.services import monitors

        monitors.trigger_on_import(db, dataset=dataset, user_id=user_id)
    except Exception:
        import logging

        logging.getLogger(__name__).exception("Monitor trigger failed; import already committed")

    return ImportResult(
        dataset_id=dataset.id,
        record_count=record_count,
        source_hash=source_hash,
        parquet_path=str(parquet_path),
        control_totals=totals,
        schema=schema_json,
    )


def load_dataset_df(parquet_path: str | Path) -> pl.DataFrame:
    return pl.read_parquet(parquet_path)
