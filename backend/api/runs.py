from __future__ import annotations

import uuid
from pathlib import Path

import polars as pl
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.core.db import get_db
from backend.core.security import get_current_user
from backend.models import Dataset, TestRun, User
from backend.services import acl, test_runner

router = APIRouter()


class DetectorRunIn(BaseModel):
    dataset_id: uuid.UUID
    detector_name: str
    params: dict = {}


class TemplateRunIn(BaseModel):
    dataset_id: uuid.UUID
    template_code: str
    param_overrides: dict = {}


def _assert_dataset_permission(db, dataset_id, user, permission):
    ds = db.get(Dataset, dataset_id)
    if not ds:
        raise HTTPException(status_code=404, detail="Dataset not found")
    acl.assert_permission(db, project_id=ds.project_id, user=user, permission=permission)
    return ds


@router.post("/runs/detector")
def run_detector(body: DetectorRunIn, db: Session = Depends(get_db),
                 user: User = Depends(get_current_user)) -> dict:
    _assert_dataset_permission(db, body.dataset_id, user, acl.Permission.EDIT)
    run = test_runner.run_detector(
        db, dataset_id=body.dataset_id, detector_name=body.detector_name,
        params=body.params, user_id=user.id,
    )
    return _out(run)


@router.post("/runs/template")
def run_template(body: TemplateRunIn, db: Session = Depends(get_db),
                 user: User = Depends(get_current_user)) -> dict:
    _assert_dataset_permission(db, body.dataset_id, user, acl.Permission.EDIT)
    run = test_runner.run_template(
        db, dataset_id=body.dataset_id, template_code=body.template_code,
        param_overrides=body.param_overrides, user_id=user.id,
    )
    return _out(run)


@router.get("/runs/{run_id}")
def get_run(run_id: uuid.UUID, db: Session = Depends(get_db),
            user: User = Depends(get_current_user)) -> dict:
    run = db.get(TestRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Not found")
    _assert_dataset_permission(db, run.dataset_id, user, acl.Permission.VIEW)
    return _out(run)


@router.get("/runs/{run_id}/flagged")
def get_flagged_records(
    run_id: uuid.UUID,
    limit: int = 200,
    offset: int = 0,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    """Return the rows the detector flagged plus per-record reasons."""
    run = db.get(TestRun, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    _assert_dataset_permission(db, run.dataset_id, user, acl.Permission.VIEW)
    if not run.output_parquet_path:
        return {"columns": [], "rows": [], "scores": [], "total": 0}
    try:
        flagged = pl.read_parquet(run.output_parquet_path)
    except Exception:
        flagged = pl.DataFrame()
    scores_df = test_runner.load_scores(run)
    score_map: dict[str, dict] = {}
    if scores_df.height > 0:
        for r in scores_df.iter_rows(named=True):
            score_map[str(r["record_key"])] = {
                "score": r.get("score"), "reason": r.get("reason"),
            }
    rows: list[dict] = []
    if flagged.height > 0:
        sliced = flagged.slice(offset, limit)
        cols = [c for c in sliced.columns if c != "_record_key"]
        for r in sliced.iter_rows(named=True):
            key = str(r.get("_record_key", ""))
            row_data = {c: r.get(c) for c in cols}
            row_data["_record_key"] = key
            row_data["_reason"] = score_map.get(key, {}).get("reason")
            row_data["_score"] = score_map.get(key, {}).get("score")
            rows.append(row_data)
        columns = ["_record_key", "_score", "_reason"] + cols
    else:
        columns = []
    return {
        "columns": columns,
        "rows": rows,
        "total": flagged.height,
        "limit": limit,
        "offset": offset,
        "summary": run.summary,
    }


@router.get("/datasets/{dataset_id}/runs")
def list_runs(dataset_id: uuid.UUID, db: Session = Depends(get_db),
              user: User = Depends(get_current_user)) -> list[dict]:
    _assert_dataset_permission(db, dataset_id, user, acl.Permission.VIEW)
    q = select(TestRun).where(TestRun.dataset_id == dataset_id).order_by(TestRun.started_at.desc())
    return [_out(r) for r in db.execute(q).scalars()]


def _out(r: TestRun) -> dict:
    return {
        "id": str(r.id),
        "dataset_id": str(r.dataset_id),
        "template_code": r.template_code,
        "detector_name": r.detector_name,
        "params": r.params,
        "status": r.status.value if r.status else None,
        "started_at": r.started_at.isoformat() if r.started_at else None,
        "finished_at": r.finished_at.isoformat() if r.finished_at else None,
        "findings_count": r.findings_count,
        "input_hash": r.input_hash,
        "output_hash": r.output_hash,
        "summary": r.summary,
        "error_message": r.error_message,
    }
