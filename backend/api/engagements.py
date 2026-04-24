from __future__ import annotations

import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from fastapi import Response

from backend.core.db import get_db
from backend.core.security import get_current_user
from backend.models import Engagement, EngagementStatus, User
from backend.services import acl, engagements as svc, workpapers

router = APIRouter()


class EngagementIn(BaseModel):
    project_id: uuid.UUID
    title: str
    period_start: date | None = None
    period_end: date | None = None
    scope: str | None = None
    lead_auditor_id: uuid.UUID | None = None
    reviewer_id: uuid.UUID | None = None


class EngagementUpdate(BaseModel):
    title: str | None = None
    period_start: date | None = None
    period_end: date | None = None
    scope: str | None = None
    lead_auditor_id: uuid.UUID | None = None
    reviewer_id: uuid.UUID | None = None
    executive_summary: str | None = None
    dataset_ids: list[uuid.UUID] | None = None
    pack_run_ids: list[uuid.UUID] | None = None
    finding_ids: list[uuid.UUID] | None = None


class TransitionIn(BaseModel):
    status: EngagementStatus


class ArtifactIn(BaseModel):
    kind: str
    ref_id: uuid.UUID


@router.get("")
def list_engagements(
    project_id: uuid.UUID | None = None, status: EngagementStatus | None = None,
    db: Session = Depends(get_db), user: User = Depends(get_current_user),
) -> list[dict]:
    rows = svc.list_engagements(db, user=user, project_id=project_id, status=status)
    return [_out(e) for e in rows]


@router.post("")
def create_engagement(body: EngagementIn, db: Session = Depends(get_db),
                      user: User = Depends(get_current_user)) -> dict:
    try:
        e = svc.create_engagement(
            db, project_id=body.project_id, title=body.title,
            period_start=body.period_start, period_end=body.period_end,
            scope=body.scope, lead_auditor_id=body.lead_auditor_id,
            reviewer_id=body.reviewer_id, user=user,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _out(e)


@router.get("/{engagement_id}")
def get_engagement(engagement_id: uuid.UUID, db: Session = Depends(get_db),
                   user: User = Depends(get_current_user)) -> dict:
    try:
        return _out(svc.get_engagement(db, engagement_id=engagement_id, user=user))
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.patch("/{engagement_id}")
def update_engagement(engagement_id: uuid.UUID, body: EngagementUpdate,
                      db: Session = Depends(get_db),
                      user: User = Depends(get_current_user)) -> dict:
    changes = body.model_dump(exclude_none=True)
    try:
        return _out(svc.update_engagement(db, engagement_id=engagement_id, user=user, changes=changes))
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.post("/{engagement_id}/transition")
def transition(engagement_id: uuid.UUID, body: TransitionIn, db: Session = Depends(get_db),
               user: User = Depends(get_current_user)) -> dict:
    try:
        return _out(svc.transition(db, engagement_id=engagement_id, new_status=body.status, user=user))
    except (ValueError, PermissionError) as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.get("/{engagement_id}/workpaper.zip")
def workpaper_bundle(engagement_id: uuid.UUID, db: Session = Depends(get_db),
                     user: User = Depends(get_current_user)) -> Response:
    e = db.get(Engagement, engagement_id)
    if not e:
        raise HTTPException(status_code=404, detail="Not found")
    acl.assert_permission(db, project_id=e.project_id, user=user, permission=acl.Permission.VIEW)
    data, filename, media = workpapers.export_engagement_bundle(
        db, engagement_id=engagement_id, user=user,
    )
    return Response(
        content=data, media_type=media,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/{engagement_id}/artifact")
def add_artifact(engagement_id: uuid.UUID, body: ArtifactIn, db: Session = Depends(get_db),
                 user: User = Depends(get_current_user)) -> dict:
    try:
        return _out(svc.add_artifact(
            db, engagement_id=engagement_id, kind=body.kind, ref_id=body.ref_id, user=user
        ))
    except (ValueError, LookupError) as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


def _out(e: Engagement) -> dict:
    return {
        "id": str(e.id), "code": e.code, "title": e.title,
        "project_id": str(e.project_id),
        "period_start": e.period_start.isoformat() if e.period_start else None,
        "period_end": e.period_end.isoformat() if e.period_end else None,
        "scope": e.scope, "status": e.status.value,
        "lead_auditor_id": str(e.lead_auditor_id) if e.lead_auditor_id else None,
        "reviewer_id": str(e.reviewer_id) if e.reviewer_id else None,
        "dataset_ids": [str(x) for x in (e.dataset_ids or [])],
        "pack_run_ids": [str(x) for x in (e.pack_run_ids or [])],
        "finding_ids": [str(x) for x in (e.finding_ids or [])],
        "executive_summary": e.executive_summary,
        "finalised_at": e.finalised_at.isoformat() if e.finalised_at else None,
        "finalised_by": str(e.finalised_by) if e.finalised_by else None,
        "created_at": e.created_at.isoformat() if e.created_at else None,
    }
