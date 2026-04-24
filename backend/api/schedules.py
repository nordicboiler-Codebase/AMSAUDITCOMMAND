from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.core.db import get_db
from backend.core.security import get_current_user
from backend.models import Dataset, Schedule, ScheduleKind, ScheduleRun, ScheduleStatus, User
from backend.services import acl, scheduler as sched_svc

router = APIRouter()


class ScheduleIn(BaseModel):
    name: str
    description: str | None = None
    project_id: uuid.UUID
    dataset_id: uuid.UUID
    kind: ScheduleKind
    pack_code: str | None = None
    template_code: str | None = None
    param_overrides: dict = {}
    cron_expr: str
    timezone: str = "UTC"
    alert_enabled: bool = False
    alert_min_score: float = 80.0
    alert_recipients: list[str] = []
    autoensemble: bool = True


class ScheduleUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    cron_expr: str | None = None
    alert_enabled: bool | None = None
    alert_min_score: float | None = None
    alert_recipients: list[str] | None = None
    status: ScheduleStatus | None = None
    param_overrides: dict | None = None
    autoensemble: bool | None = None


@router.get("")
def list_schedules(
    project_id: uuid.UUID | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[dict]:
    q = select(Schedule)
    if project_id is not None:
        acl.assert_permission(db, project_id=project_id, user=user, permission=acl.Permission.VIEW)
        q = q.where(Schedule.project_id == project_id)
    else:
        visible = acl.visible_project_ids(db, user=user)
        if not visible:
            return []
        q = q.where(Schedule.project_id.in_(visible))
    q = q.order_by(Schedule.name.asc())
    return [_out(s) for s in db.execute(q).scalars()]


@router.post("")
def create_schedule(body: ScheduleIn, db: Session = Depends(get_db),
                    user: User = Depends(get_current_user)) -> dict:
    acl.assert_permission(db, project_id=body.project_id, user=user, permission=acl.Permission.EDIT)
    ds = db.get(Dataset, body.dataset_id)
    if not ds or ds.project_id != body.project_id:
        raise HTTPException(status_code=400, detail="Dataset does not belong to this project")
    if body.kind == ScheduleKind.PACK and not body.pack_code:
        raise HTTPException(status_code=400, detail="pack_code required for PACK kind")
    if body.kind == ScheduleKind.TEMPLATE and not body.template_code:
        raise HTTPException(status_code=400, detail="template_code required for TEMPLATE kind")
    next_fire = sched_svc.next_fire_time(body.cron_expr)
    if next_fire is None:
        raise HTTPException(status_code=400, detail=f"Invalid cron expression: {body.cron_expr}")
    s = Schedule(
        name=body.name, description=body.description, project_id=body.project_id,
        dataset_id=body.dataset_id, kind=body.kind,
        pack_code=body.pack_code, template_code=body.template_code,
        param_overrides=body.param_overrides, cron_expr=body.cron_expr, timezone=body.timezone,
        alert_enabled=body.alert_enabled, alert_min_score=body.alert_min_score,
        alert_recipients=body.alert_recipients, autoensemble=body.autoensemble,
        next_run_at=next_fire, created_by=user.id,
    )
    db.add(s)
    db.commit()
    return _out(s)


@router.get("/{schedule_id}")
def get_schedule(schedule_id: uuid.UUID, db: Session = Depends(get_db),
                 user: User = Depends(get_current_user)) -> dict:
    s = db.get(Schedule, schedule_id)
    if not s:
        raise HTTPException(status_code=404, detail="Not found")
    acl.assert_permission(db, project_id=s.project_id, user=user, permission=acl.Permission.VIEW)
    return _out(s)


@router.patch("/{schedule_id}")
def update_schedule(schedule_id: uuid.UUID, body: ScheduleUpdate,
                    db: Session = Depends(get_db),
                    user: User = Depends(get_current_user)) -> dict:
    s = db.get(Schedule, schedule_id)
    if not s:
        raise HTTPException(status_code=404, detail="Not found")
    acl.assert_permission(db, project_id=s.project_id, user=user, permission=acl.Permission.EDIT)
    changes = body.model_dump(exclude_none=True)
    if "cron_expr" in changes:
        next_fire = sched_svc.next_fire_time(changes["cron_expr"])
        if next_fire is None:
            raise HTTPException(status_code=400, detail=f"Invalid cron expression: {changes['cron_expr']}")
        s.next_run_at = next_fire
    for k, v in changes.items():
        setattr(s, k, v)
    db.commit()
    return _out(s)


@router.delete("/{schedule_id}")
def delete_schedule(schedule_id: uuid.UUID, db: Session = Depends(get_db),
                    user: User = Depends(get_current_user)) -> dict:
    s = db.get(Schedule, schedule_id)
    if not s:
        raise HTTPException(status_code=404, detail="Not found")
    acl.assert_permission(db, project_id=s.project_id, user=user, permission=acl.Permission.ADMIN)
    db.delete(s)
    db.commit()
    return {"deleted": True}


@router.post("/{schedule_id}/run-now")
def run_now(schedule_id: uuid.UUID, db: Session = Depends(get_db),
            user: User = Depends(get_current_user)) -> dict:
    s = db.get(Schedule, schedule_id)
    if not s:
        raise HTTPException(status_code=404, detail="Not found")
    acl.assert_permission(db, project_id=s.project_id, user=user, permission=acl.Permission.EDIT)
    run = sched_svc.run_schedule_once(db, s)
    return {"schedule_run_id": str(run.id), "status": run.status, "summary": run.summary}


@router.get("/{schedule_id}/runs")
def list_runs(schedule_id: uuid.UUID, db: Session = Depends(get_db),
              user: User = Depends(get_current_user)) -> list[dict]:
    s = db.get(Schedule, schedule_id)
    if not s:
        raise HTTPException(status_code=404, detail="Not found")
    acl.assert_permission(db, project_id=s.project_id, user=user, permission=acl.Permission.VIEW)
    rows = db.execute(
        select(ScheduleRun).where(ScheduleRun.schedule_id == schedule_id)
        .order_by(ScheduleRun.started_at.desc()).limit(200)
    ).scalars()
    return [
        {
            "id": str(r.id),
            "started_at": r.started_at.isoformat() if r.started_at else None,
            "finished_at": r.finished_at.isoformat() if r.finished_at else None,
            "status": r.status,
            "summary": r.summary,
            "alert_sent": r.alert_sent,
            "alert_error": r.alert_error,
        }
        for r in rows
    ]


@router.post("/preview-cron")
def preview_cron(body: dict, _u: User = Depends(get_current_user)) -> dict:
    cron_expr = body.get("cron_expr", "")
    count = int(body.get("count", 5))
    times = sched_svc.preview_next_fire(cron_expr, count=count)
    return {"valid": bool(times), "next_runs": times}


def _out(s: Schedule) -> dict:
    return {
        "id": str(s.id),
        "name": s.name,
        "description": s.description,
        "project_id": str(s.project_id),
        "dataset_id": str(s.dataset_id) if s.dataset_id else None,
        "kind": s.kind.value,
        "pack_code": s.pack_code,
        "template_code": s.template_code,
        "param_overrides": s.param_overrides,
        "cron_expr": s.cron_expr,
        "timezone": s.timezone,
        "status": s.status.value,
        "alert_enabled": s.alert_enabled,
        "alert_min_score": s.alert_min_score,
        "alert_recipients": list(s.alert_recipients or []),
        "autoensemble": s.autoensemble,
        "last_run_at": s.last_run_at.isoformat() if s.last_run_at else None,
        "last_run_status": s.last_run_status,
        "last_run_summary": s.last_run_summary,
        "next_run_at": s.next_run_at.isoformat() if s.next_run_at else None,
    }
