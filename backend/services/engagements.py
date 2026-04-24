from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.models import (
    AuditAction, Engagement, EngagementStatus, Finding, FindingStatus, User,
)
from backend.services import acl, audit_log


ALLOWED_TRANSITIONS: dict[EngagementStatus, set[EngagementStatus]] = {
    EngagementStatus.PLANNING: {EngagementStatus.IN_PROGRESS, EngagementStatus.ARCHIVED},
    EngagementStatus.IN_PROGRESS: {EngagementStatus.REVIEW, EngagementStatus.PLANNING},
    EngagementStatus.REVIEW: {EngagementStatus.FINALISED, EngagementStatus.IN_PROGRESS},
    EngagementStatus.FINALISED: {EngagementStatus.ARCHIVED},
    EngagementStatus.ARCHIVED: set(),
}


def _next_code(db: Session, project_id: uuid.UUID) -> str:
    year = date.today().year
    prefix = f"E-{year}-"
    n = db.execute(
        select(func.count()).select_from(Engagement).where(Engagement.code.like(f"{prefix}%"))
    ).scalar_one()
    return f"{prefix}{n + 1:04d}"


def create_engagement(
    db: Session, *, project_id: uuid.UUID, title: str, period_start: date | None,
    period_end: date | None, scope: str | None, lead_auditor_id: uuid.UUID | None,
    reviewer_id: uuid.UUID | None, user: User,
) -> Engagement:
    acl.assert_permission(db, project_id=project_id, user=user, permission=acl.Permission.EDIT)
    e = Engagement(
        code=_next_code(db, project_id),
        title=title,
        project_id=project_id,
        period_start=period_start,
        period_end=period_end,
        scope=scope,
        status=EngagementStatus.PLANNING,
        lead_auditor_id=lead_auditor_id or user.id,
        reviewer_id=reviewer_id,
        created_by=user.id,
    )
    db.add(e)
    db.flush()
    audit_log.log_action(
        db, user_id=user.id, action=AuditAction.FINDING_CREATE, entity_type="engagement",
        entity_id=str(e.id), project_id=project_id,
        details={"code": e.code, "title": title},
    )
    db.commit()
    return e


def list_engagements(
    db: Session, *, user: User, project_id: uuid.UUID | None = None,
    status: EngagementStatus | None = None,
) -> list[Engagement]:
    q = select(Engagement)
    if project_id is not None:
        acl.assert_permission(db, project_id=project_id, user=user, permission=acl.Permission.VIEW)
        q = q.where(Engagement.project_id == project_id)
    else:
        visible = acl.visible_project_ids(db, user=user)
        if not visible:
            return []
        q = q.where(Engagement.project_id.in_(visible))
    if status:
        q = q.where(Engagement.status == status)
    q = q.order_by(Engagement.created_at.desc())
    return list(db.execute(q).scalars())


def get_engagement(db: Session, *, engagement_id: uuid.UUID, user: User) -> Engagement:
    e = db.get(Engagement, engagement_id)
    if not e:
        raise LookupError("Engagement not found")
    acl.assert_permission(db, project_id=e.project_id, user=user, permission=acl.Permission.VIEW)
    return e


def update_engagement(
    db: Session, *, engagement_id: uuid.UUID, user: User, changes: dict[str, Any],
) -> Engagement:
    e = get_engagement(db, engagement_id=engagement_id, user=user)
    acl.assert_permission(db, project_id=e.project_id, user=user, permission=acl.Permission.EDIT)
    editable = {
        "title", "period_start", "period_end", "scope", "lead_auditor_id", "reviewer_id",
        "executive_summary", "dataset_ids", "pack_run_ids", "finding_ids",
    }
    for k, v in changes.items():
        if k in editable and v is not None:
            setattr(e, k, v)
    db.commit()
    return e


def transition(
    db: Session, *, engagement_id: uuid.UUID, new_status: EngagementStatus, user: User,
) -> Engagement:
    e = get_engagement(db, engagement_id=engagement_id, user=user)
    if new_status not in ALLOWED_TRANSITIONS.get(e.status, set()):
        raise ValueError(f"Cannot transition {e.status.value} → {new_status.value}")

    if new_status == EngagementStatus.FINALISED:
        acl.assert_permission(db, project_id=e.project_id, user=user, permission=acl.Permission.REVIEW)
        if e.lead_auditor_id and e.lead_auditor_id == user.id:
            raise PermissionError(
                "Maker-checker: the engagement lead cannot finalise their own engagement"
            )
        unresolved = []
        for fid in e.finding_ids or []:
            f = db.get(Finding, fid)
            if f and f.status in {FindingStatus.DRAFT, FindingStatus.UNDER_REVIEW}:
                unresolved.append(f.code)
        if unresolved:
            raise ValueError(f"Cannot finalise: unresolved findings {unresolved}")
        e.finalised_at = datetime.now(timezone.utc)
        e.finalised_by = user.id
        audit_log.log_action(
            db, user_id=user.id, action=AuditAction.ENGAGEMENT_FINALISE,
            entity_type="engagement", entity_id=str(e.id), project_id=e.project_id,
            details={"code": e.code, "findings_count": len(e.finding_ids or [])},
        )
    else:
        acl.assert_permission(db, project_id=e.project_id, user=user, permission=acl.Permission.EDIT)

    e.status = new_status
    db.commit()
    return e


def add_artifact(
    db: Session, *, engagement_id: uuid.UUID, kind: str, ref_id: uuid.UUID, user: User,
) -> Engagement:
    e = get_engagement(db, engagement_id=engagement_id, user=user)
    acl.assert_permission(db, project_id=e.project_id, user=user, permission=acl.Permission.EDIT)
    target_attr = {
        "dataset": "dataset_ids",
        "pack_run": "pack_run_ids",
        "finding": "finding_ids",
    }.get(kind)
    if not target_attr:
        raise ValueError(f"Unknown artifact kind: {kind}")
    current: list[uuid.UUID] = list(getattr(e, target_attr) or [])
    if ref_id not in current:
        current.append(ref_id)
        setattr(e, target_attr, current)
    db.commit()
    return e
