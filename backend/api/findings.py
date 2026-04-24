from __future__ import annotations

import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.core.db import get_db
from backend.core.security import get_current_user
from backend.models import Finding, FindingComment, FindingSeverity, FindingStatus, User
from backend.services import findings as svc

router = APIRouter()


class FindingIn(BaseModel):
    project_id: uuid.UUID
    title: str
    description: str | None = None
    dataset_id: uuid.UUID | None = None
    ensemble_run_id: uuid.UUID | None = None
    record_keys: list[str] = []
    risk_score: float | None = None
    severity: FindingSeverity = FindingSeverity.MEDIUM
    due_date: date | None = None
    linked_template_codes: list[str] = []
    tags: list[str] = []


class FindingUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    severity: FindingSeverity | None = None
    due_date: date | None = None
    management_response: str | None = None
    remediation_plan: str | None = None
    tags: list[str] | None = None


class TransitionIn(BaseModel):
    status: FindingStatus
    comment: str | None = None


class CommentIn(BaseModel):
    body: str


@router.get("")
def list_findings(
    project_id: uuid.UUID | None = None,
    status: FindingStatus | None = None,
    severity: FindingSeverity | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[dict]:
    rows = svc.list_findings(db, user=user, project_id=project_id, status=status, severity=severity)
    return [_out(f) for f in rows]


@router.post("")
def create_finding(body: FindingIn, db: Session = Depends(get_db),
                   user: User = Depends(get_current_user)) -> dict:
    try:
        f = svc.create_finding(
            db, project_id=body.project_id, title=body.title, description=body.description,
            dataset_id=body.dataset_id, ensemble_run_id=body.ensemble_run_id,
            record_keys=body.record_keys, risk_score=body.risk_score,
            severity=body.severity, due_date=body.due_date,
            linked_template_codes=body.linked_template_codes, tags=body.tags, user=user,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return _out(f)


@router.get("/{finding_id}")
def get_finding(finding_id: uuid.UUID, db: Session = Depends(get_db),
                user: User = Depends(get_current_user)) -> dict:
    try:
        f = svc.get_finding(db, finding_id=finding_id, user=user)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    return _out(f)


@router.patch("/{finding_id}")
def update_finding(finding_id: uuid.UUID, body: FindingUpdate, db: Session = Depends(get_db),
                   user: User = Depends(get_current_user)) -> dict:
    changes = {k: v for k, v in body.model_dump().items() if v is not None}
    try:
        f = svc.update_finding(db, finding_id=finding_id, user=user, changes=changes)
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    return _out(f)


@router.post("/{finding_id}/transition")
def transition(finding_id: uuid.UUID, body: TransitionIn, db: Session = Depends(get_db),
               user: User = Depends(get_current_user)) -> dict:
    try:
        f = svc.transition_status(
            db, finding_id=finding_id, new_status=body.status, user=user, comment=body.comment
        )
    except (ValueError, PermissionError) as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    return _out(f)


@router.get("/{finding_id}/comments")
def list_comments(finding_id: uuid.UUID, db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)) -> list[dict]:
    rows = svc.list_comments(db, finding_id=finding_id, user=user)
    return [_comment_out(c) for c in rows]


@router.post("/{finding_id}/comments")
def add_comment(finding_id: uuid.UUID, body: CommentIn, db: Session = Depends(get_db),
                user: User = Depends(get_current_user)) -> dict:
    c = svc.add_comment(db, finding_id=finding_id, body=body.body, user=user)
    return _comment_out(c)


def _out(f: Finding) -> dict:
    return {
        "id": str(f.id),
        "code": f.code,
        "title": f.title,
        "description": f.description,
        "project_id": str(f.project_id),
        "dataset_id": str(f.dataset_id) if f.dataset_id else None,
        "ensemble_run_id": str(f.ensemble_run_id) if f.ensemble_run_id else None,
        "record_keys": list(f.record_keys or []),
        "risk_score": f.risk_score,
        "severity": f.severity.value,
        "status": f.status.value,
        "owner_id": str(f.owner_id) if f.owner_id else None,
        "reviewer_id": str(f.reviewer_id) if f.reviewer_id else None,
        "due_date": f.due_date.isoformat() if f.due_date else None,
        "management_response": f.management_response,
        "remediation_plan": f.remediation_plan,
        "tags": list(f.tags or []),
        "linked_template_codes": list(f.linked_template_codes or []),
        "reviewed_at": f.reviewed_at.isoformat() if f.reviewed_at else None,
        "closed_at": f.closed_at.isoformat() if f.closed_at else None,
        "created_at": f.created_at.isoformat() if f.created_at else None,
    }


def _comment_out(c: FindingComment) -> dict:
    return {
        "id": str(c.id),
        "finding_id": str(c.finding_id),
        "author_id": str(c.author_id) if c.author_id else None,
        "body": c.body,
        "is_review_signoff": c.is_review_signoff,
        "created_at": c.created_at.isoformat() if c.created_at else None,
    }
