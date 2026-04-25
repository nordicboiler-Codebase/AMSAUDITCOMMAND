from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
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


def _friendly_error(e: Exception) -> str:
    """Surface the model/provider error string to the UI without a stack."""
    msg = str(e)
    name = type(e).__name__
    # Trim verbose google.genai / openai / anthropic exception payloads
    if len(msg) > 400:
        msg = msg[:400] + "…"
    if "NOT_FOUND" in msg or "not found" in msg.lower() or "404" in msg:
        return (
            f"{name}: model not available. "
            "The selected model may have been retired by the provider. "
            "Open Settings → AI Providers and pick a current model. "
            f"Details: {msg}"
        )
    if "401" in msg or "unauthorized" in msg.lower() or "invalid_api_key" in msg.lower():
        return f"{name}: API key rejected. Open Settings → AI Providers and re-enter the key. Details: {msg}"
    if "429" in msg or "rate" in msg.lower() and "limit" in msg.lower():
        return f"{name}: provider rate-limit. Wait a moment and retry. Details: {msg}"
    if "402" in msg or "billing" in msg.lower() or "credit" in msg.lower():
        return f"{name}: billing / credits issue with the provider. Details: {msg}"
    return f"{name}: {msg}"


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
