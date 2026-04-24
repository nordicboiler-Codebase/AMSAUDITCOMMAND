from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.core.db import get_db
from backend.core.security import get_current_user
from backend.models import Monitor, SubledgerType, User
from backend.services import acl, monitors as svc

router = APIRouter()


class MonitorIn(BaseModel):
    project_id: uuid.UUID
    name: str
    subledger_type: SubledgerType
    pack_code: str
    auto_ensemble: bool = True
    auto_create_finding_min_score: float = 90.0
    alert_recipients: list[str] = []


class MonitorUpdate(BaseModel):
    name: str | None = None
    pack_code: str | None = None
    auto_ensemble: bool | None = None
    auto_create_finding_min_score: float | None = None
    alert_recipients: list[str] | None = None
    enabled: bool | None = None


@router.get("")
def list_monitors(project_id: uuid.UUID | None = None, db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)) -> list[dict]:
    rows = svc.list_monitors(db, user=user, project_id=project_id)
    return [_out(m) for m in rows]


@router.post("")
def create_monitor(body: MonitorIn, db: Session = Depends(get_db),
                   user: User = Depends(get_current_user)) -> dict:
    try:
        m = svc.create_monitor(
            db, project_id=body.project_id, name=body.name,
            subledger_type=body.subledger_type.value, pack_code=body.pack_code,
            auto_ensemble=body.auto_ensemble,
            auto_create_finding_min_score=body.auto_create_finding_min_score,
            alert_recipients=body.alert_recipients, user=user,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return _out(m)


@router.patch("/{monitor_id}")
def update_monitor(monitor_id: uuid.UUID, body: MonitorUpdate, db: Session = Depends(get_db),
                   user: User = Depends(get_current_user)) -> dict:
    m = db.get(Monitor, monitor_id)
    if not m:
        raise HTTPException(status_code=404, detail="Not found")
    acl.assert_permission(db, project_id=m.project_id, user=user, permission=acl.Permission.EDIT)
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(m, k, v)
    db.commit()
    return _out(m)


@router.delete("/{monitor_id}")
def delete_monitor(monitor_id: uuid.UUID, db: Session = Depends(get_db),
                   user: User = Depends(get_current_user)) -> dict:
    m = db.get(Monitor, monitor_id)
    if not m:
        raise HTTPException(status_code=404, detail="Not found")
    acl.assert_permission(db, project_id=m.project_id, user=user, permission=acl.Permission.ADMIN)
    db.delete(m)
    db.commit()
    return {"deleted": True}


def _out(m: Monitor) -> dict:
    return {
        "id": str(m.id), "project_id": str(m.project_id), "name": m.name,
        "subledger_type": m.subledger_type, "pack_code": m.pack_code,
        "auto_ensemble": m.auto_ensemble,
        "auto_create_finding_min_score": m.auto_create_finding_min_score,
        "alert_recipients": list(m.alert_recipients or []),
        "enabled": m.enabled,
        "last_triggered_at": m.last_triggered_at.isoformat() if m.last_triggered_at else None,
        "last_dataset_id": str(m.last_dataset_id) if m.last_dataset_id else None,
    }
