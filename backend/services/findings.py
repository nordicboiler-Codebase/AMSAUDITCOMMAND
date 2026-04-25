from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.models import (
    AuditAction, Finding, FindingComment, FindingSeverity, FindingStatus, Project, User,
)
from backend.services import acl, audit_log


ALLOWED_TRANSITIONS: dict[FindingStatus, set[FindingStatus]] = {
    FindingStatus.DRAFT: {FindingStatus.UNDER_REVIEW, FindingStatus.FALSE_POSITIVE},
    FindingStatus.UNDER_REVIEW: {FindingStatus.CONFIRMED, FindingStatus.FALSE_POSITIVE, FindingStatus.DRAFT},
    FindingStatus.CONFIRMED: {FindingStatus.REMEDIATED, FindingStatus.ACCEPTED_RISK, FindingStatus.CARRIED_FORWARD},
    FindingStatus.FALSE_POSITIVE: {FindingStatus.DRAFT},
    FindingStatus.REMEDIATED: set(),
    FindingStatus.ACCEPTED_RISK: set(),
    FindingStatus.CARRIED_FORWARD: {FindingStatus.CONFIRMED, FindingStatus.REMEDIATED},
}


def _next_code(db: Session) -> str:
    year = date.today().year
    prefix = f"F-{year}-"
    n = db.execute(
        select(func.count()).select_from(Finding).where(Finding.code.like(f"{prefix}%"))
    ).scalar_one()
    return f"{prefix}{n + 1:05d}"


def create_finding(
    db: Session,
    *,
    project_id: uuid.UUID,
    title: str,
    description: str | None,
    dataset_id: uuid.UUID | None,
    ensemble_run_id: uuid.UUID | None,
    record_keys: list[str],
    risk_score: float | None,
    severity: FindingSeverity,
    due_date: date | None,
    linked_template_codes: list[str],
    tags: list[str],
    user: User,
) -> Finding:
    acl.assert_permission(db, project_id=project_id, user=user, permission=acl.Permission.EDIT)
    finding = Finding(
        code=_next_code(db),
        title=title,
        description=description,
        project_id=project_id,
        dataset_id=dataset_id,
        ensemble_run_id=ensemble_run_id,
        record_keys=record_keys,
        risk_score=risk_score,
        severity=severity,
        status=FindingStatus.DRAFT,
        owner_id=user.id,
        due_date=due_date,
        linked_template_codes=linked_template_codes,
        tags=tags,
        created_by=user.id,
    )
    db.add(finding)
    db.flush()
    audit_log.log_action(
        db, user_id=user.id, action=AuditAction.FINDING_CREATE, entity_type="finding",
        entity_id=str(finding.id), project_id=project_id,
        details={"code": finding.code, "severity": severity.value, "record_count": len(record_keys)},
    )
    db.commit()
    return finding


def list_findings(
    db: Session, *, user: User, project_id: uuid.UUID | None = None,
    status: FindingStatus | None = None, severity: FindingSeverity | None = None,
    subsidiary_code: str | None = None, tag: str | None = None,
    dataset_id: uuid.UUID | None = None,
) -> list[Finding]:
    q = select(Finding)
    if project_id is not None:
        acl.assert_permission(db, project_id=project_id, user=user, permission=acl.Permission.VIEW)
        q = q.where(Finding.project_id == project_id)
    else:
        visible = acl.visible_project_ids(db, user=user)
        if not visible:
            return []
        q = q.where(Finding.project_id.in_(visible))
    if status:
        q = q.where(Finding.status == status)
    if severity:
        q = q.where(Finding.severity == severity)
    if dataset_id is not None:
        q = q.where(Finding.dataset_id == dataset_id)
    if subsidiary_code:
        sub_project_ids = db.execute(
            select(Project.id).where(Project.subsidiary_code == subsidiary_code)
        ).scalars().all()
        if not sub_project_ids:
            return []
        q = q.where(Finding.project_id.in_(sub_project_ids))
    rows = list(db.execute(q.order_by(Finding.created_at.desc())).scalars())
    if tag:
        rows = [f for f in rows if tag in (f.tags or [])]
    return rows


def get_finding(db: Session, *, finding_id: uuid.UUID, user: User) -> Finding:
    f = db.get(Finding, finding_id)
    if not f:
        raise LookupError("Finding not found")
    acl.assert_permission(db, project_id=f.project_id, user=user, permission=acl.Permission.VIEW)
    return f


def transition_status(
    db: Session, *, finding_id: uuid.UUID, new_status: FindingStatus, user: User,
    comment: str | None = None,
) -> Finding:
    finding = get_finding(db, finding_id=finding_id, user=user)
    current = finding.status
    if new_status not in ALLOWED_TRANSITIONS.get(current, set()):
        raise ValueError(f"Cannot transition {current.value} → {new_status.value}")

    is_review = new_status in {
        FindingStatus.CONFIRMED, FindingStatus.FALSE_POSITIVE,
        FindingStatus.REMEDIATED, FindingStatus.ACCEPTED_RISK,
    }
    if is_review:
        acl.assert_permission(db, project_id=finding.project_id, user=user,
                              permission=acl.Permission.REVIEW)
        if finding.owner_id and finding.owner_id == user.id:
            raise PermissionError(
                "Maker-checker: the creator/owner of a finding cannot be the reviewer"
            )
        finding.reviewer_id = user.id
        finding.reviewed_at = datetime.now(timezone.utc)
    else:
        acl.assert_permission(db, project_id=finding.project_id, user=user,
                              permission=acl.Permission.EDIT)

    previous = finding.status
    finding.status = new_status
    if new_status in {FindingStatus.REMEDIATED, FindingStatus.ACCEPTED_RISK}:
        finding.closed_at = datetime.now(timezone.utc)

    # ML feedback loop: record labelled outcomes on human decisions.
    if new_status in {FindingStatus.CONFIRMED, FindingStatus.FALSE_POSITIVE}:
        try:
            from backend.services import feedback

            feedback.record_label_on_status_change(db, finding=finding, user_id=user.id)
        except Exception:
            pass  # feedback is advisory — never block a valid transition

    if comment:
        db.add(FindingComment(
            finding_id=finding.id, author_id=user.id, body=comment,
            is_review_signoff=is_review,
        ))

    action = AuditAction.FINDING_REVIEW if is_review else AuditAction.FINDING_UPDATE
    audit_log.log_action(
        db, user_id=user.id, action=action, entity_type="finding",
        entity_id=str(finding.id), project_id=finding.project_id,
        details={"from": previous.value, "to": new_status.value, "comment": bool(comment)},
    )
    db.commit()
    return finding


def add_comment(
    db: Session, *, finding_id: uuid.UUID, body: str, user: User,
) -> FindingComment:
    finding = get_finding(db, finding_id=finding_id, user=user)
    comment = FindingComment(finding_id=finding.id, author_id=user.id, body=body)
    db.add(comment)
    db.flush()
    audit_log.log_action(
        db, user_id=user.id, action=AuditAction.FINDING_UPDATE, entity_type="finding_comment",
        entity_id=str(comment.id), project_id=finding.project_id,
        details={"finding_code": finding.code},
    )
    db.commit()
    return comment


def list_comments(db: Session, *, finding_id: uuid.UUID, user: User) -> list[FindingComment]:
    get_finding(db, finding_id=finding_id, user=user)
    q = select(FindingComment).where(FindingComment.finding_id == finding_id).order_by(
        FindingComment.created_at.asc()
    )
    return list(db.execute(q).scalars())


def update_finding(
    db: Session, *, finding_id: uuid.UUID, user: User, changes: dict[str, Any],
) -> Finding:
    finding = get_finding(db, finding_id=finding_id, user=user)
    acl.assert_permission(db, project_id=finding.project_id, user=user,
                          permission=acl.Permission.EDIT)
    editable = {
        "title", "description", "severity", "due_date",
        "management_response", "remediation_plan", "tags",
    }
    for k, v in changes.items():
        if k not in editable or v is None:
            continue
        setattr(finding, k, v)
    audit_log.log_action(
        db, user_id=user.id, action=AuditAction.FINDING_UPDATE, entity_type="finding",
        entity_id=str(finding.id), project_id=finding.project_id,
        details={"fields": list(changes.keys())},
    )
    db.commit()
    return finding
