from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.core.db import get_db
from backend.core.security import get_current_user
from backend.models import Dataset, RiskScore, User
from backend.services import acl

router = APIRouter()


@router.get("/{dataset_id}/risk-scores")
def list_scores(
    dataset_id: uuid.UUID,
    min_score: float = 0.0,
    offset: int = 0,
    limit: int = 100,
    sort: str = "desc",
    ensemble_run_id: uuid.UUID | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[dict]:
    ds = db.get(Dataset, dataset_id)
    if not ds:
        raise HTTPException(status_code=404, detail="Dataset not found")
    acl.assert_permission(db, project_id=ds.project_id, user=user, permission=acl.Permission.VIEW)
    q = select(RiskScore).where(
        RiskScore.dataset_id == dataset_id, RiskScore.score >= min_score
    )
    if ensemble_run_id is not None:
        q = q.where(RiskScore.ensemble_run_id == ensemble_run_id)
    limit = min(limit, 500)
    q = q.order_by(
        RiskScore.score.desc() if sort == "desc" else RiskScore.score.asc()
    ).offset(offset).limit(limit)
    return [
        {
            "record_key": r.record_key,
            "score": r.score,
            "contributing_detectors": r.contributing_detectors,
            "ensemble_run_id": str(r.ensemble_run_id),
        }
        for r in db.execute(q).scalars()
    ]


@router.get("/{dataset_id}/risk-scores/{record_key}")
def score_detail(
    dataset_id: uuid.UUID,
    record_key: str,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    ds = db.get(Dataset, dataset_id)
    if not ds:
        raise HTTPException(status_code=404, detail="Dataset not found")
    acl.assert_permission(db, project_id=ds.project_id, user=user, permission=acl.Permission.VIEW)
    q = select(RiskScore).where(
        RiskScore.dataset_id == dataset_id, RiskScore.record_key == record_key
    ).order_by(RiskScore.computed_at.desc()).limit(1)
    row = db.execute(q).scalars().first()
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    return {
        "record_key": row.record_key,
        "score": row.score,
        "contributing_detectors": row.contributing_detectors,
        "ensemble_run_id": str(row.ensemble_run_id),
        "computed_at": row.computed_at.isoformat() if row.computed_at else None,
    }
