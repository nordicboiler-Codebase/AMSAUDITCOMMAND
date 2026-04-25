from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.core.db import get_db
from backend.core.rate_limit import nlq_rate_limit
from backend.core.security import get_current_user
from backend.models import User
from backend.services import nlq

router = APIRouter()


class NLQIn(BaseModel):
    question: str


@router.get("/ai/status")
def ai_status(_u: User = Depends(get_current_user)) -> dict:
    return nlq.ai_status()


@router.post("/datasets/{dataset_id}/nlq")
def nl_query(dataset_id: uuid.UUID, body: NLQIn, db: Session = Depends(get_db),
             user: User = Depends(get_current_user),
             _rl: None = Depends(nlq_rate_limit)) -> dict:
    return nlq.nl_to_template(db, dataset_id=dataset_id, question=body.question, user_id=user.id)


@router.post("/datasets/{dataset_id}/suggest-templates")
def suggest(dataset_id: uuid.UUID, db: Session = Depends(get_db),
            user: User = Depends(get_current_user),
            _rl: None = Depends(nlq_rate_limit)) -> list[dict]:
    return nlq.suggest_templates(db, dataset_id=dataset_id, user_id=user.id)


@router.post("/test-runs/{run_id}/narrative")
def narrative(run_id: uuid.UUID, db: Session = Depends(get_db),
              user: User = Depends(get_current_user),
              _rl: None = Depends(nlq_rate_limit)) -> dict:
    text = nlq.generate_narrative(db, test_run_id=run_id, user_id=user.id)
    return {"narrative": text}


@router.post("/findings/{finding_id}/narrative")
def finding_narrative(finding_id: uuid.UUID, db: Session = Depends(get_db),
                      user: User = Depends(get_current_user),
                      _rl: None = Depends(nlq_rate_limit)) -> dict:
    text = nlq.generate_finding_narrative(db, finding_id=finding_id, user_id=user.id)
    return {"narrative": text}
