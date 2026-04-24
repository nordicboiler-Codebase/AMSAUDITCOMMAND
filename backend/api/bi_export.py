"""Simple BI/OData-style feeds for Power BI Web, Tableau Web Data Connector, and Excel.

Any of these tools can consume a plain JSON or CSV URL over HTTP Basic-like auth.
Endpoints return CSV for maximum compatibility. Filter by project_id if provided.
"""
from __future__ import annotations

import csv
import io
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.core.db import get_db
from backend.core.security import get_current_user
from backend.models import (
    AuditAction, Dataset, Finding, RiskScore, TestRun, User,
)
from backend.services import acl, audit_log

router = APIRouter()


def _csv_response(headers: list[str], rows: list[list]) -> Response:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(headers)
    for r in rows:
        w.writerow(r)
    return Response(content=buf.getvalue(), media_type="text/csv")


@router.get("/findings.csv")
def findings_csv(
    project_id: uuid.UUID | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    q = select(Finding)
    if project_id is not None:
        acl.assert_permission(db, project_id=project_id, user=user, permission=acl.Permission.VIEW)
        q = q.where(Finding.project_id == project_id)
    else:
        visible = acl.visible_project_ids(db, user=user)
        if not visible:
            return _csv_response([], [])
        q = q.where(Finding.project_id.in_(visible))

    rows = list(db.execute(q.order_by(Finding.created_at.desc())).scalars())
    headers = [
        "code", "title", "project_id", "severity", "status", "risk_score",
        "owner_id", "reviewer_id", "due_date", "created_at", "reviewed_at",
        "closed_at", "tags", "linked_template_codes",
    ]
    body = [
        [
            f.code, f.title, str(f.project_id), f.severity.value, f.status.value,
            f.risk_score, str(f.owner_id) if f.owner_id else "",
            str(f.reviewer_id) if f.reviewer_id else "",
            f.due_date.isoformat() if f.due_date else "",
            f.created_at.isoformat() if f.created_at else "",
            f.reviewed_at.isoformat() if f.reviewed_at else "",
            f.closed_at.isoformat() if f.closed_at else "",
            ";".join(f.tags or []),
            ";".join(f.linked_template_codes or []),
        ]
        for f in rows
    ]
    audit_log.log_action(
        db, user_id=user.id, action=AuditAction.EXPORT, entity_type="bi_feed",
        entity_id="findings.csv", details={"project_id": str(project_id) if project_id else None,
                                            "rows": len(body)},
    )
    db.commit()
    return _csv_response(headers, body)


@router.get("/risk_scores.csv")
def risk_scores_csv(
    project_id: uuid.UUID | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    q = select(RiskScore).join(Dataset, Dataset.id == RiskScore.dataset_id)
    if project_id is not None:
        acl.assert_permission(db, project_id=project_id, user=user, permission=acl.Permission.VIEW)
        q = q.where(Dataset.project_id == project_id)
    else:
        visible = acl.visible_project_ids(db, user=user)
        if not visible:
            return _csv_response([], [])
        q = q.where(Dataset.project_id.in_(visible))
    q = q.order_by(RiskScore.computed_at.desc()).limit(50000)
    rows = list(db.execute(q).scalars())
    headers = [
        "dataset_id", "ensemble_run_id", "record_key", "score",
        "contributing_detector_count", "contributing_detector_names", "computed_at",
    ]
    body = []
    for r in rows:
        det_names = sorted({c.get("detector_name", "") for c in (r.contributing_detectors or [])})
        body.append([
            str(r.dataset_id), str(r.ensemble_run_id), r.record_key, r.score,
            len(det_names), ";".join(det_names),
            r.computed_at.isoformat() if r.computed_at else "",
        ])
    audit_log.log_action(
        db, user_id=user.id, action=AuditAction.EXPORT, entity_type="bi_feed",
        entity_id="risk_scores.csv", details={"rows": len(body)},
    )
    db.commit()
    return _csv_response(headers, body)


@router.get("/test_runs.csv")
def test_runs_csv(
    project_id: uuid.UUID | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Response:
    q = select(TestRun).join(Dataset, Dataset.id == TestRun.dataset_id)
    if project_id is not None:
        acl.assert_permission(db, project_id=project_id, user=user, permission=acl.Permission.VIEW)
        q = q.where(Dataset.project_id == project_id)
    else:
        visible = acl.visible_project_ids(db, user=user)
        if not visible:
            return _csv_response([], [])
        q = q.where(Dataset.project_id.in_(visible))
    q = q.order_by(TestRun.started_at.desc()).limit(50000)
    rows = list(db.execute(q).scalars())
    headers = [
        "id", "dataset_id", "template_code", "detector_name", "status",
        "findings_count", "started_at", "finished_at", "input_hash", "output_hash",
    ]
    body = [
        [
            str(r.id), str(r.dataset_id), r.template_code or "", r.detector_name,
            r.status.value if r.status else "", r.findings_count,
            r.started_at.isoformat() if r.started_at else "",
            r.finished_at.isoformat() if r.finished_at else "",
            r.input_hash or "", r.output_hash or "",
        ]
        for r in rows
    ]
    return _csv_response(headers, body)


@router.get("/manifest.json")
def manifest(user: User = Depends(get_current_user)) -> dict:
    """Lists the BI feeds Power BI / Tableau can hook into."""
    return {
        "service": "TechSource Audit Analytics — BI feeds",
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "feeds": [
            {"name": "findings", "url": "/api/bi/findings.csv",
             "params": ["project_id"], "format": "csv"},
            {"name": "risk_scores", "url": "/api/bi/risk_scores.csv",
             "params": ["project_id"], "format": "csv"},
            {"name": "test_runs", "url": "/api/bi/test_runs.csv",
             "params": ["project_id"], "format": "csv"},
        ],
        "note": "Authenticate via bearer token in Authorization header. "
                "In Power BI, use Web connector → Advanced → add Authorization header. "
                "In Tableau, use Web Data Connector with bearer token.",
    }
