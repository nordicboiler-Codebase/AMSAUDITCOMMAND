from __future__ import annotations

import uuid
from pathlib import Path

import polars as pl
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from backend.core.config import get_settings
from backend.core.db import get_db
from backend.core.security import get_current_user
from backend.models import Dataset, SubledgerType, User
from backend.services import import_service

router = APIRouter()
settings = get_settings()


@router.post("/import")
async def import_dataset(
    file: UploadFile = File(...),
    project_id: uuid.UUID = Form(...),
    name: str = Form(...),
    subledger_type: SubledgerType = Form(...),
    description: str | None = Form(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    settings.ensure_dirs()
    dest = settings.upload_dir / f"{uuid.uuid4()}_{file.filename}"
    with open(dest, "wb") as f:
        f.write(await file.read())
    result = import_service.import_dataset(
        db,
        file_path=dest,
        source_filename=file.filename,
        project_id=project_id,
        name=name,
        subledger_type=subledger_type,
        user_id=user.id,
        description=description,
    )
    return {
        "dataset_id": str(result.dataset_id),
        "record_count": result.record_count,
        "source_hash": result.source_hash,
        "control_totals": result.control_totals,
        "schema": result.schema,
    }


@router.get("/{dataset_id}")
def get_dataset(dataset_id: uuid.UUID, db: Session = Depends(get_db),
                _u: User = Depends(get_current_user)) -> dict:
    ds = db.get(Dataset, dataset_id)
    if not ds:
        raise HTTPException(status_code=404, detail="Not found")
    return _ds_out(ds)


@router.get("/{dataset_id}/preview")
def preview(dataset_id: uuid.UUID, rows: int = 100, db: Session = Depends(get_db),
            _u: User = Depends(get_current_user)) -> dict:
    ds = db.get(Dataset, dataset_id)
    if not ds:
        raise HTTPException(status_code=404, detail="Not found")
    df = pl.read_parquet(ds.parquet_path).head(rows)
    return {"columns": df.columns, "rows": df.to_dicts()}


@router.get("/{dataset_id}/schema")
def schema(dataset_id: uuid.UUID, db: Session = Depends(get_db),
           _u: User = Depends(get_current_user)) -> dict:
    ds = db.get(Dataset, dataset_id)
    if not ds:
        raise HTTPException(status_code=404, detail="Not found")
    return ds.schema_json


@router.get("/{dataset_id}/control-totals")
def control_totals(dataset_id: uuid.UUID, db: Session = Depends(get_db),
                   _u: User = Depends(get_current_user)) -> dict:
    ds = db.get(Dataset, dataset_id)
    if not ds:
        raise HTTPException(status_code=404, detail="Not found")
    return ds.control_totals


def _ds_out(ds: Dataset) -> dict:
    return {
        "id": str(ds.id),
        "project_id": str(ds.project_id),
        "name": ds.name,
        "source_filename": ds.source_filename,
        "source_hash": ds.source_hash_sha256,
        "subledger_type": ds.subledger_type.value,
        "record_count": ds.record_count,
        "schema": ds.schema_json,
        "control_totals": ds.control_totals,
    }
