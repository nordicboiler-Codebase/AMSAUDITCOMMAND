from __future__ import annotations

import uuid
from enum import Enum

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models import Project, ProjectMember, ProjectRole, User
from backend.models.enums import UserRole


class Permission(str, Enum):
    VIEW = "VIEW"
    EDIT = "EDIT"
    REVIEW = "REVIEW"
    ADMIN = "ADMIN"


ROLE_PERMISSIONS: dict[ProjectRole, set[Permission]] = {
    ProjectRole.OWNER: {Permission.VIEW, Permission.EDIT, Permission.REVIEW, Permission.ADMIN},
    ProjectRole.EDITOR: {Permission.VIEW, Permission.EDIT},
    ProjectRole.REVIEWER: {Permission.VIEW, Permission.REVIEW},
    ProjectRole.VIEWER: {Permission.VIEW},
}


def get_membership(db: Session, *, project_id: uuid.UUID, user: User) -> ProjectMember | None:
    if user.role == UserRole.ADMIN:
        return None
    return db.execute(
        select(ProjectMember).where(
            ProjectMember.project_id == project_id,
            ProjectMember.user_id == user.id,
        )
    ).scalar_one_or_none()


def user_can(db: Session, *, project_id: uuid.UUID, user: User, permission: Permission) -> bool:
    if user.role == UserRole.ADMIN:
        return True
    member = get_membership(db, project_id=project_id, user=user)
    if member is None:
        return False
    return permission in ROLE_PERMISSIONS.get(member.project_role, set())


def assert_permission(db: Session, *, project_id: uuid.UUID, user: User,
                      permission: Permission) -> None:
    if not user_can(db, project_id=project_id, user=user, permission=permission):
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail=f"Missing {permission.value} on project {project_id}")


def visible_project_ids(db: Session, *, user: User) -> list[uuid.UUID]:
    if user.role == UserRole.ADMIN:
        return [row.id for row in db.execute(select(Project)).scalars()]
    rows = db.execute(
        select(ProjectMember.project_id).where(ProjectMember.user_id == user.id)
    ).all()
    return [r[0] for r in rows]


def list_members(db: Session, project_id: uuid.UUID) -> list[dict]:
    rows = db.execute(
        select(ProjectMember, User).join(User, User.id == ProjectMember.user_id)
        .where(ProjectMember.project_id == project_id)
    ).all()
    return [
        {
            "user_id": str(u.id), "username": u.username, "email": u.email,
            "project_role": m.project_role.value,
            "added_at": m.added_at.isoformat() if m.added_at else None,
        }
        for m, u in rows
    ]


def add_or_update_member(
    db: Session, *, project_id: uuid.UUID, user_id: uuid.UUID,
    project_role: ProjectRole, added_by: uuid.UUID,
) -> ProjectMember:
    existing = db.execute(
        select(ProjectMember).where(
            ProjectMember.project_id == project_id, ProjectMember.user_id == user_id,
        )
    ).scalar_one_or_none()
    if existing:
        existing.project_role = project_role
        db.flush()
        return existing
    m = ProjectMember(
        project_id=project_id, user_id=user_id,
        project_role=project_role, added_by=added_by,
    )
    db.add(m)
    db.flush()
    return m


def remove_member(db: Session, *, project_id: uuid.UUID, user_id: uuid.UUID) -> bool:
    row = db.execute(
        select(ProjectMember).where(
            ProjectMember.project_id == project_id, ProjectMember.user_id == user_id,
        )
    ).scalar_one_or_none()
    if not row:
        return False
    db.delete(row)
    db.flush()
    return True
