from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.core.db import get_db
from backend.core.security import create_token, get_current_user, hash_password, verify_password
from backend.models import AuditAction, User
from backend.models.enums import UserRole
from backend.services import audit_log

router = APIRouter()


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class RegisterIn(BaseModel):
    username: str
    email: str
    password: str
    role: UserRole = UserRole.AUDITOR


@router.post("/register", response_model=dict)
def register(body: RegisterIn, db: Session = Depends(get_db)) -> dict:
    if db.execute(select(User).where(User.username == body.username)).scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Username exists")
    user = User(
        username=body.username,
        email=body.email,
        password_hash=hash_password(body.password),
        role=body.role,
    )
    db.add(user)
    db.commit()
    return {"id": str(user.id), "username": user.username}


@router.post("/token", response_model=TokenOut)
def token(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)) -> TokenOut:
    user = db.execute(select(User).where(User.username == form.username)).scalar_one_or_none()
    if not user or not verify_password(form.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    audit_log.log_action(db, user_id=user.id, action=AuditAction.LOGIN,
                         entity_type="user", entity_id=str(user.id))
    db.commit()
    return TokenOut(access_token=create_token(str(user.id), {"username": user.username,
                                                             "role": user.role.value}))


@router.get("/me")
def me(user: User = Depends(get_current_user)) -> dict:
    return {"id": str(user.id), "username": user.username, "email": user.email, "role": user.role.value}
