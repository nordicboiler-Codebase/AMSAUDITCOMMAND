from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.core.db import get_db
from backend.core.security import get_current_user
from backend.models import (
    Dataset, Engagement, Finding, FindingSeverity, FindingStatus, PackRun, Project,
    RiskScore, Schedule, TestRun, User,
)
from backend.services import acl

router = APIRouter()


@router.get("/dashboard")
def dashboard(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> dict:
    visible = acl.visible_project_ids(db, user=user)

    def count(q):
        return db.execute(q).scalar_one()

    now = datetime.now(timezone.utc)
    month_ago = now - timedelta(days=30)
    week_ago = now - timedelta(days=7)

    if not visible:
        return {"projects": 0, "datasets": 0, "findings_open": 0}

    projects = len(visible)
    datasets = count(
        select(func.count()).select_from(Dataset).where(Dataset.project_id.in_(visible))
    )
    engagements_in_progress = count(
        select(func.count()).select_from(Engagement).where(
            Engagement.project_id.in_(visible),
            Engagement.status.in_(["IN_PROGRESS", "REVIEW"]),
        )
    )

    findings_open = count(
        select(func.count()).select_from(Finding).where(
            Finding.project_id.in_(visible),
            Finding.status.in_(["DRAFT", "UNDER_REVIEW", "CONFIRMED"]),
        )
    )
    findings_high = count(
        select(func.count()).select_from(Finding).where(
            Finding.project_id.in_(visible),
            Finding.severity.in_(["HIGH", "CRITICAL"]),
            Finding.status.in_(["DRAFT", "UNDER_REVIEW", "CONFIRMED"]),
        )
    )
    findings_this_month = count(
        select(func.count()).select_from(Finding).where(
            Finding.project_id.in_(visible), Finding.created_at >= month_ago,
        )
    )

    runs_this_week = count(
        select(func.count()).select_from(TestRun)
        .join(Dataset, Dataset.id == TestRun.dataset_id)
        .where(Dataset.project_id.in_(visible), TestRun.started_at >= week_ago)
    )

    schedules_active = count(
        select(func.count()).select_from(Schedule).where(
            Schedule.project_id.in_(visible), Schedule.status == "ACTIVE",
        )
    )

    severity_rows = db.execute(
        select(Finding.severity, func.count()).where(
            Finding.project_id.in_(visible),
            Finding.status.in_(["DRAFT", "UNDER_REVIEW", "CONFIRMED"]),
        ).group_by(Finding.severity)
    ).all()
    by_severity = {s.value if hasattr(s, "value") else str(s): c for s, c in severity_rows}

    status_rows = db.execute(
        select(Finding.status, func.count()).where(Finding.project_id.in_(visible))
        .group_by(Finding.status)
    ).all()
    by_status = {s.value if hasattr(s, "value") else str(s): c for s, c in status_rows}

    top_risk_rows = db.execute(
        select(RiskScore).join(Dataset, Dataset.id == RiskScore.dataset_id)
        .where(Dataset.project_id.in_(visible))
        .order_by(RiskScore.score.desc()).limit(10)
    ).scalars()
    top_risk = [
        {"record_key": r.record_key, "score": r.score,
         "detectors": sorted({c.get("detector_name", "") for c in r.contributing_detectors or []})}
        for r in top_risk_rows
    ]

    trend_rows = db.execute(
        select(
            func.date_trunc("week", Finding.created_at).label("week"),
            func.count().label("n"),
        ).where(
            Finding.project_id.in_(visible),
            Finding.created_at >= now - timedelta(days=84),
        ).group_by("week").order_by("week")
    ).all()
    finding_trend = [
        {"week": (w.isoformat() if hasattr(w, "isoformat") else str(w)), "count": int(n)}
        for w, n in trend_rows
    ]

    return {
        "projects": projects,
        "datasets": datasets,
        "engagements_in_progress": engagements_in_progress,
        "findings_open": findings_open,
        "findings_high_or_critical": findings_high,
        "findings_this_month": findings_this_month,
        "runs_this_week": runs_this_week,
        "schedules_active": schedules_active,
        "findings_by_severity": by_severity,
        "findings_by_status": by_status,
        "top_risk_records": top_risk,
        "finding_trend_last_84d": finding_trend,
    }
