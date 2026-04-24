from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.core.db import get_db
from backend.core.security import get_current_user
from backend.models import User
from backend.services import ensemble as ens_svc

router = APIRouter()


class EnsembleIn(BaseModel):
    dataset_id: uuid.UUID
    test_run_ids: list[uuid.UUID]


@router.post("/ensemble")
def run_ensemble(body: EnsembleIn, db: Session = Depends(get_db),
                 user: User = Depends(get_current_user)) -> dict:
    er = ens_svc.compute_ensemble(db, dataset_id=body.dataset_id,
                                  test_run_ids=body.test_run_ids, user_id=user.id)
    return {"ensemble_run_id": str(er.id), "summary": er.summary, "status": er.status.value}
