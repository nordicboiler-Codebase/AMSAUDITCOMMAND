from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.core.db import get_db
from backend.core.security import hash_password, require_role
from backend.models import User
from backend.models.enums import UserRole

router = APIRouter()


class UserIn(BaseModel):
    username: str
    email: str
    password: str
    role: UserRole = UserRole.AUDITOR


class UserUpdate(BaseModel):
    email: str | None = None
    role: UserRole | None = None
    is_active: bool | None = None
    password: str | None = None


def _out(u: User) -> dict:
    return {
        "id": str(u.id), "username": u.username, "email": u.email,
        "role": u.role.value, "is_active": u.is_active,
        "mfa_enabled": u.mfa_enabled,
    }


@router.get("")
def list_users(db: Session = Depends(get_db), _admin=Depends(require_role("ADMIN"))) -> list[dict]:
    return [_out(u) for u in db.execute(select(User)).scalars()]


@router.post("")
def create_user(body: UserIn, db: Session = Depends(get_db),
                _admin=Depends(require_role("ADMIN"))) -> dict:
    if db.execute(select(User).where(User.username == body.username)).scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Username exists")
    u = User(username=body.username, email=body.email, role=body.role,
             password_hash=hash_password(body.password))
    db.add(u)
    db.commit()
    return _out(u)


@router.patch("/{user_id}")
def update_user(user_id: uuid.UUID, body: UserUpdate, db: Session = Depends(get_db),
                _admin=Depends(require_role("ADMIN"))) -> dict:
    u = db.get(User, user_id)
    if not u:
        raise HTTPException(status_code=404, detail="Not found")
    if body.email is not None:
        u.email = body.email
    if body.role is not None:
        u.role = body.role
    if body.is_active is not None:
        u.is_active = body.is_active
    if body.password is not None:
        u.password_hash = hash_password(body.password)
    db.commit()
    return _out(u)


@router.post("/{user_id}/deactivate")
def deactivate_user(user_id: uuid.UUID, db: Session = Depends(get_db),
                    _admin=Depends(require_role("ADMIN"))) -> dict:
    u = db.get(User, user_id)
    if not u:
        raise HTTPException(status_code=404, detail="Not found")
    u.is_active = False
    db.commit()
    return {"deactivated": True}
