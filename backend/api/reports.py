from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from backend.core.db import get_db
from backend.core.security import get_current_user
from backend.models import AuditAction, User
from backend.services import audit_log, reporting

router = APIRouter()


@router.get("/test-runs/{run_id}/report.pdf")
def run_pdf(run_id: uuid.UUID, db: Session = Depends(get_db),
            user: User = Depends(get_current_user)) -> Response:
    data = reporting.generate_template_report(db, run_id)
    audit_log.log_action(db, user_id=user.id, action=AuditAction.EXPORT,
                         entity_type="test_run", entity_id=str(run_id),
                         details={"format": "pdf"})
    db.commit()
    return Response(content=data, media_type="application/pdf")


@router.get("/pack-runs/{pack_run_id}/report.pdf")
def pack_pdf(pack_run_id: uuid.UUID, db: Session = Depends(get_db),
             user: User = Depends(get_current_user)) -> Response:
    data = reporting.generate_pack_report(db, pack_run_id)
    audit_log.log_action(db, user_id=user.id, action=AuditAction.EXPORT,
                         entity_type="pack_run", entity_id=str(pack_run_id),
                         details={"format": "pdf"})
    db.commit()
    return Response(content=data, media_type="application/pdf")


@router.get("/projects/{project_id}/report.pdf")
def project_pdf(project_id: uuid.UUID, db: Session = Depends(get_db),
                user: User = Depends(get_current_user)) -> Response:
    data = reporting.generate_project_report(db, project_id)
    return Response(content=data, media_type="application/pdf")


@router.get("/test-runs/{run_id}/findings.xlsx")
def run_excel(run_id: uuid.UUID, db: Session = Depends(get_db),
              user: User = Depends(get_current_user)) -> Response:
    data = reporting.generate_excel(db, run_id)
    return Response(content=data,
                    media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
