from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.core.db import get_db
from backend.core.security import get_current_user
from backend.models import Dataset, Pack, PackRun, TestRun, User
from backend.models.enums import SubledgerType
from backend.services import acl, packs as pack_svc
from sqlalchemy import select

router = APIRouter()


class PackRunIn(BaseModel):
    dataset_id: uuid.UUID
    pack_code: str
    template_overrides: dict[str, dict] = {}


@router.get("")
def list_packs(subledger: SubledgerType | None = None, db: Session = Depends(get_db),
               _u: User = Depends(get_current_user)) -> list[dict]:
    return [_out(p) for p in pack_svc.list_packs(db, subledger=subledger)]


@router.get("/{code}")
def get_pack(code: str, db: Session = Depends(get_db),
             _u: User = Depends(get_current_user)) -> dict:
    try:
        return _out(pack_svc.get_pack(db, code))
    except pack_svc.PackError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.get("/runs")
def list_pack_runs(
    project_id: uuid.UUID | None = None,
    dataset_id: uuid.UUID | None = None,
    pack_code: str | None = None,
    limit: int = 100,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> list[dict]:
    visible = acl.visible_project_ids(db, user=user)
    if not visible:
        return []
    q = (
        select(PackRun, Dataset)
        .join(Dataset, PackRun.dataset_id == Dataset.id)
        .where(Dataset.project_id.in_(visible))
        .order_by(PackRun.started_at.desc())
        .limit(min(limit, 500))
    )
    if project_id:
        q = q.where(Dataset.project_id == project_id)
    if dataset_id:
        q = q.where(PackRun.dataset_id == dataset_id)
    if pack_code:
        q = q.where(PackRun.pack_code == pack_code)
    out = []
    for pr, ds in db.execute(q).all():
        out.append({
            "id": str(pr.id), "dataset_id": str(pr.dataset_id), "dataset_name": ds.name,
            "pack_code": pr.pack_code, "status": pr.status.value,
            "started_at": pr.started_at.isoformat() if pr.started_at else None,
            "finished_at": pr.finished_at.isoformat() if pr.finished_at else None,
            "summary": pr.summary or {},
            "ensemble_run_id": str(pr.ensemble_run_id) if pr.ensemble_run_id else None,
        })
    return out


@router.get("/runs/{pack_run_id}")
def get_pack_run(
    pack_run_id: uuid.UUID, db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> dict:
    pr = db.get(PackRun, pack_run_id)
    if not pr:
        raise HTTPException(status_code=404, detail="Pack run not found")
    ds = db.get(Dataset, pr.dataset_id)
    if not ds:
        raise HTTPException(status_code=404, detail="Dataset missing")
    acl.assert_permission(db, project_id=ds.project_id, user=user, permission=acl.Permission.VIEW)

    summary = pr.summary or {}
    test_run_ids = summary.get("test_run_ids") or []
    test_runs: list[dict] = []
    if test_run_ids:
        rows = db.execute(
            select(TestRun).where(TestRun.id.in_([uuid.UUID(t) for t in test_run_ids]))
        ).scalars().all()
        test_runs = [
            {
                "id": str(t.id), "template_code": t.template_code,
                "detector_name": t.detector_name, "status": t.status.value,
                "findings_count": t.findings_count or 0,
                "started_at": t.started_at.isoformat() if t.started_at else None,
                "finished_at": t.finished_at.isoformat() if t.finished_at else None,
            }
            for t in rows
        ]

    return {
        "id": str(pr.id), "pack_code": pr.pack_code, "status": pr.status.value,
        "dataset_id": str(pr.dataset_id), "dataset_name": ds.name,
        "subledger_type": ds.subledger_type.value if ds.subledger_type else None,
        "started_at": pr.started_at.isoformat() if pr.started_at else None,
        "finished_at": pr.finished_at.isoformat() if pr.finished_at else None,
        "summary": summary,
        "ensemble_run_id": str(pr.ensemble_run_id) if pr.ensemble_run_id else None,
        "test_runs": test_runs,
        "template_overrides": pr.template_overrides or {},
    }


@router.post("/run")
def run_pack(body: PackRunIn, db: Session = Depends(get_db),
             user: User = Depends(get_current_user)) -> dict:
    ds = db.get(Dataset, body.dataset_id)
    if not ds:
        raise HTTPException(status_code=404, detail="Dataset not found")
    acl.assert_permission(db, project_id=ds.project_id, user=user, permission=acl.Permission.EDIT)
    try:
        run = pack_svc.run_pack(db, dataset_id=body.dataset_id, pack_code=body.pack_code,
                                template_overrides=body.template_overrides, user_id=user.id)
    except pack_svc.PackError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return {"pack_run_id": str(run.id), "summary": run.summary, "status": run.status.value}


def _out(p: Pack) -> dict:
    return {
        "id": str(p.id),
        "code": p.code,
        "name": p.name,
        "description": p.description,
        "subledger_type": p.subledger_type.value if p.subledger_type else None,
        "template_codes": list(p.template_codes or []),
        "is_system": p.is_system,
    }
