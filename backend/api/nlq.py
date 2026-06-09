from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.core.db import get_db
from backend.core.rate_limit import nlq_rate_limit
from backend.core.security import get_current_user
from backend.models import User
from backend.services import llm, nlq

router = APIRouter()


class NLQIn(BaseModel):
    question: str


class TemplateGenIn(BaseModel):
    description: str
    dataset_id: uuid.UUID | None = None


class EmailSearchIn(BaseModel):
    prompt: str
    limit: int = 500


def _friendly_error(e: Exception) -> str:
    return llm.humanise_provider_error(e)


@router.get("/ai/status")
def ai_status(db: Session = Depends(get_db),
              _u: User = Depends(get_current_user)) -> dict:
    return nlq.ai_status(db)


@router.post("/datasets/{dataset_id}/nlq")
def nl_query(dataset_id: uuid.UUID, body: NLQIn, db: Session = Depends(get_db),
             user: User = Depends(get_current_user),
             _rl: None = Depends(nlq_rate_limit)) -> dict:
    try:
        return nlq.nl_to_template(db, dataset_id=dataset_id, question=body.question, user_id=user.id)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=_friendly_error(e)) from e


@router.post("/datasets/{dataset_id}/email-search")
def email_search(dataset_id: uuid.UUID, body: EmailSearchIn,
                 db: Session = Depends(get_db),
                 user: User = Depends(get_current_user),
                 _rl: None = Depends(nlq_rate_limit)) -> dict:
    """Natural-language deep search over a mailbox dataset.

    The prompt is compiled by the active AI provider into a multi-clause
    email_search plan, every clause is executed, and the matching messages are
    returned directly (prompt in → emails out).
    """
    try:
        return nlq.compile_and_run_email_search(
            db, dataset_id=dataset_id, prompt=body.prompt, user_id=user.id,
            limit=body.limit,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=_friendly_error(e)) from e


@router.post("/datasets/{dataset_id}/suggest-templates")
def suggest(dataset_id: uuid.UUID, db: Session = Depends(get_db),
            user: User = Depends(get_current_user),
            _rl: None = Depends(nlq_rate_limit)) -> list[dict]:
    try:
        return nlq.suggest_templates(db, dataset_id=dataset_id, user_id=user.id)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=_friendly_error(e)) from e


@router.post("/test-runs/{run_id}/narrative")
def narrative(run_id: uuid.UUID, db: Session = Depends(get_db),
              user: User = Depends(get_current_user),
              _rl: None = Depends(nlq_rate_limit)) -> dict:
    try:
        text = nlq.generate_narrative(db, test_run_id=run_id, user_id=user.id)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=_friendly_error(e)) from e
    return {"narrative": text}


@router.post("/findings/{finding_id}/narrative")
def finding_narrative(finding_id: uuid.UUID, db: Session = Depends(get_db),
                      user: User = Depends(get_current_user),
                      _rl: None = Depends(nlq_rate_limit)) -> dict:
    try:
        text = nlq.generate_finding_narrative(db, finding_id=finding_id, user_id=user.id)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=_friendly_error(e)) from e
    return {"narrative": text}


@router.post("/templates/from-description")
def template_from_description(
    body: TemplateGenIn, db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    _rl: None = Depends(nlq_rate_limit),
) -> dict:
    """AI proposes a template (DB row) given an auditor's description.

    Returns a proposal the user reviews and saves via POST /api/templates.
    Does NOT create the template here — keeps maker-checker-style review.
    """
    try:
        return nlq.generate_template_from_description(
            db, description=body.description, dataset_id=body.dataset_id,
            user_id=user.id,
        )
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=_friendly_error(e)) from e
