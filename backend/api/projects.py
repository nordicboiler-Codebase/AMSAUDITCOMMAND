from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.core.db import get_db
from backend.core.security import get_current_user
from backend.models import Project, User

router = APIRouter()


class ProjectIn(BaseModel):
    name: str
    description: str | None = None
    subsidiary_code: str | None = None


@router.get("")
def list_projects(db: Session = Depends(get_db), _u: User = Depends(get_current_user)) -> list[dict]:
    rows = db.execute(select(Project)).scalars().all()
    return [_project_out(p) for p in rows]


@router.post("")
def create_project(body: ProjectIn, db: Session = Depends(get_db),
                   user: User = Depends(get_current_user)) -> dict:
    p = Project(name=body.name, description=body.description,
                subsidiary_code=body.subsidiary_code, owner_id=user.id)
    db.add(p)
    db.commit()
    return _project_out(p)


@router.get("/{project_id}")
def get_project(project_id: uuid.UUID, db: Session = Depends(get_db),
                _u: User = Depends(get_current_user)) -> dict:
    p = db.get(Project, project_id)
    if not p:
        raise HTTPException(status_code=404, detail="Not found")
    return _project_out(p)


def _project_out(p: Project) -> dict:
    return {
        "id": str(p.id),
        "name": p.name,
        "description": p.description,
        "subsidiary_code": p.subsidiary_code,
        "status": p.status,
        "owner_id": str(p.owner_id) if p.owner_id else None,
    }
