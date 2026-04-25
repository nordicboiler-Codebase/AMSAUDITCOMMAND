from __future__ import annotations

import hashlib
import uuid
from datetime import date
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.core.config import get_settings
from backend.core.db import get_db
from backend.core.security import get_current_user
from backend.models import (
    Finding, FindingAttachment, FindingComment, FindingSeverity, FindingStatus, User,
)
from backend.services import acl, findings as svc, settings_store

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
    subsidiary_code: str | None = None,
    offset: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[dict]:
    rows = svc.list_findings(
        db, user=user, project_id=project_id, status=status, severity=severity,
        subsidiary_code=subsidiary_code,
    )
    limit = min(limit, 500)
    return [_out(f) for f in rows[offset: offset + limit]]


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


@router.post("/{finding_id}/attachments")
async def upload_attachment(
    finding_id: uuid.UUID, file: UploadFile = File(...),
    db: Session = Depends(get_db), user: User = Depends(get_current_user),
) -> dict:
    f = svc.get_finding(db, finding_id=finding_id, user=user)
    acl.assert_permission(db, project_id=f.project_id, user=user, permission=acl.Permission.EDIT)
    raw = await file.read()
    digest = hashlib.sha256(raw).hexdigest()
    st = get_settings()
    st.ensure_dirs()
    target = st.upload_dir / f"attach_{uuid.uuid4()}_{file.filename}.enc"
    target.write_bytes(settings_store.encrypt_bytes(raw))
    att = FindingAttachment(
        finding_id=f.id, filename=file.filename or "unnamed",
        content_type=file.content_type, storage_path=str(target),
        sha256=digest, bytes=len(raw), uploaded_by=user.id,
    )
    db.add(att)
    db.commit()
    return {
        "id": str(att.id), "filename": att.filename, "sha256": digest, "bytes": len(raw),
    }


@router.get("/{finding_id}/attachments")
def list_attachments(finding_id: uuid.UUID, db: Session = Depends(get_db),
                     user: User = Depends(get_current_user)) -> list[dict]:
    svc.get_finding(db, finding_id=finding_id, user=user)
    rows = list(db.execute(
        select(FindingAttachment).where(FindingAttachment.finding_id == finding_id)
        .order_by(FindingAttachment.uploaded_at.desc())
    ).scalars())
    return [
        {"id": str(a.id), "filename": a.filename, "content_type": a.content_type,
         "sha256": a.sha256, "bytes": a.bytes,
         "uploaded_at": a.uploaded_at.isoformat() if a.uploaded_at else None,
         "uploaded_by": str(a.uploaded_by) if a.uploaded_by else None}
        for a in rows
    ]


@router.get("/{finding_id}/attachments/{attachment_id}")
def download_attachment(
    finding_id: uuid.UUID, attachment_id: uuid.UUID,
    db: Session = Depends(get_db), user: User = Depends(get_current_user),
) -> Response:
    svc.get_finding(db, finding_id=finding_id, user=user)
    att = db.get(FindingAttachment, attachment_id)
    if not att or att.finding_id != finding_id:
        raise HTTPException(status_code=404, detail="Attachment not found")
    path = Path(att.storage_path)
    if not path.exists():
        raise HTTPException(status_code=410, detail="File no longer on disk")
    try:
        plaintext = settings_store.decrypt_bytes(path.read_bytes())
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Decrypt failed: {e}") from e
    if hashlib.sha256(plaintext).hexdigest() != att.sha256:
        raise HTTPException(status_code=500, detail="INTEGRITY VIOLATION")
    return Response(
        content=plaintext,
        media_type=att.content_type or "application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{att.filename}"',
                 "X-SHA256": att.sha256},
    )


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
