from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.core.db import get_db
from backend.core.security import get_current_user
from backend.models import Dataset, Pack, User
from backend.models.enums import SubledgerType
from backend.services import acl, packs as pack_svc

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
