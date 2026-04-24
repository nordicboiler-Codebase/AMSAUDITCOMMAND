from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.core.db import get_db
from backend.core.security import get_current_user
from backend.models import Project, ProjectMember, ProjectRole, User
from backend.models.enums import UserRole
from backend.services import acl

router = APIRouter()


class ProjectIn(BaseModel):
    name: str
    description: str | None = None
    subsidiary_code: str | None = None


class MemberIn(BaseModel):
    user_id: uuid.UUID
    project_role: ProjectRole


@router.get("")
def list_projects(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> list[dict]:
    visible = acl.visible_project_ids(db, user=user)
    if user.role == UserRole.ADMIN:
        rows = db.execute(select(Project)).scalars().all()
    else:
        if not visible:
            return []
        rows = db.execute(select(Project).where(Project.id.in_(visible))).scalars().all()
    return [_project_out(p) for p in rows]


@router.post("")
def create_project(body: ProjectIn, db: Session = Depends(get_db),
                   user: User = Depends(get_current_user)) -> dict:
    if user.role not in (UserRole.ADMIN, UserRole.AUDITOR):
        raise HTTPException(status_code=403, detail="Only ADMIN/AUDITOR can create projects")
    p = Project(name=body.name, description=body.description,
                subsidiary_code=body.subsidiary_code, owner_id=user.id)
    db.add(p)
    db.flush()
    acl.add_or_update_member(
        db, project_id=p.id, user_id=user.id,
        project_role=ProjectRole.OWNER, added_by=user.id,
    )
    db.commit()
    return _project_out(p)


@router.get("/{project_id}")
def get_project(project_id: uuid.UUID, db: Session = Depends(get_db),
                user: User = Depends(get_current_user)) -> dict:
    acl.assert_permission(db, project_id=project_id, user=user, permission=acl.Permission.VIEW)
    p = db.get(Project, project_id)
    if not p:
        raise HTTPException(status_code=404, detail="Not found")
    return _project_out(p)


@router.get("/{project_id}/members")
def list_members(project_id: uuid.UUID, db: Session = Depends(get_db),
                 user: User = Depends(get_current_user)) -> list[dict]:
    acl.assert_permission(db, project_id=project_id, user=user, permission=acl.Permission.VIEW)
    return acl.list_members(db, project_id)


@router.post("/{project_id}/members")
def add_member(project_id: uuid.UUID, body: MemberIn, db: Session = Depends(get_db),
               user: User = Depends(get_current_user)) -> dict:
    acl.assert_permission(db, project_id=project_id, user=user, permission=acl.Permission.ADMIN)
    target = db.get(User, body.user_id)
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    acl.add_or_update_member(db, project_id=project_id, user_id=body.user_id,
                             project_role=body.project_role, added_by=user.id)
    db.commit()
    return {"ok": True}


@router.delete("/{project_id}/members/{user_id}")
def remove_member(project_id: uuid.UUID, user_id: uuid.UUID, db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)) -> dict:
    acl.assert_permission(db, project_id=project_id, user=user, permission=acl.Permission.ADMIN)
    if acl.remove_member(db, project_id=project_id, user_id=user_id):
        db.commit()
        return {"removed": True}
    return {"removed": False}


def _project_out(p: Project) -> dict:
    return {
        "id": str(p.id),
        "name": p.name,
        "description": p.description,
        "subsidiary_code": p.subsidiary_code,
        "status": p.status,
        "owner_id": str(p.owner_id) if p.owner_id else None,
    }
