from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from backend.core.db import get_db
from backend.core.security import get_current_user
from backend.models import User
from backend.services import audit_log as svc

router = APIRouter()


@router.get("/verify")
def verify(project_id: uuid.UUID | None = None, db: Session = Depends(get_db),
           _u: User = Depends(get_current_user)) -> dict:
    status = svc.verify_chain(db, project_id=project_id)
    return {"ok": status.ok, "total_entries": status.total_entries,
            "broken_at": status.broken_at, "reason": status.reason}


@router.get("/entries")
def entries(project_id: uuid.UUID | None = None, db: Session = Depends(get_db),
            _u: User = Depends(get_current_user)) -> list[dict]:
    return svc.export_log(db, project_id=project_id)


@router.get("/pdf")
def pdf(project_id: uuid.UUID | None = None, db: Session = Depends(get_db),
        _u: User = Depends(get_current_user)) -> Response:
    data = svc.export_log_pdf(db, project_id=project_id)
    return Response(content=data, media_type="application/pdf")
