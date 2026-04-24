from __future__ import annotations

import re

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.core.db import get_db
from backend.core.rate_limit import login_rate_limit
from backend.core.security import create_token, get_current_user, hash_password, verify_password
from backend.models import AuditAction, User
from backend.models.enums import UserRole
from backend.services import audit_log, mfa, sso

router = APIRouter()


def _check_password_strength(pwd: str) -> None:
    if len(pwd) < 10:
        raise HTTPException(status_code=400, detail="Password must be ≥ 10 characters")
    classes = sum([
        bool(re.search(r"[a-z]", pwd)),
        bool(re.search(r"[A-Z]", pwd)),
        bool(re.search(r"\d", pwd)),
        bool(re.search(r"[^A-Za-z0-9]", pwd)),
    ])
    if classes < 3:
        raise HTTPException(
            status_code=400,
            detail="Password must contain at least 3 of: lowercase, uppercase, digit, symbol",
        )


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class RegisterIn(BaseModel):
    username: str
    email: str
    password: str
    role: UserRole = UserRole.AUDITOR


@router.post("/register", response_model=dict)
def register(body: RegisterIn, db: Session = Depends(get_db),
             _rl: None = Depends(login_rate_limit)) -> dict:
    if db.execute(select(User).where(User.username == body.username)).scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Username exists")
    _check_password_strength(body.password)
    user = User(
        username=body.username,
        email=body.email,
        password_hash=hash_password(body.password),
        role=body.role,
    )
    db.add(user)
    db.commit()
    return {"id": str(user.id), "username": user.username}


@router.post("/token")
def token(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db),
          _rl: None = Depends(login_rate_limit)) -> dict:
    user = db.execute(select(User).where(User.username == form.username)).scalar_one_or_none()
    if not user or not verify_password(form.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if user.mfa_enabled:
        challenge = mfa.create_challenge_token(user.id)
        return {"mfa_required": True, "challenge_token": challenge}
    audit_log.log_action(db, user_id=user.id, action=AuditAction.LOGIN,
                         entity_type="user", entity_id=str(user.id))
    db.commit()
    return {
        "access_token": create_token(str(user.id), {"username": user.username, "role": user.role.value}),
        "token_type": "bearer",
        "mfa_required": False,
    }


class MfaVerifyIn(BaseModel):
    challenge_token: str
    token: str


@router.post("/mfa/verify")
def mfa_verify(body: MfaVerifyIn, db: Session = Depends(get_db)) -> dict:
    try:
        user_id = mfa.decode_challenge_token(body.challenge_token)
    except PermissionError as e:
        raise HTTPException(status_code=401, detail=str(e)) from e
    user = db.get(User, user_id)
    if not user or not user.mfa_enabled or not user.totp_secret:
        raise HTTPException(status_code=400, detail="MFA not configured for this user")
    if not mfa.verify_totp(user.totp_secret, body.token):
        raise HTTPException(status_code=401, detail="Invalid TOTP code")
    audit_log.log_action(db, user_id=user.id, action=AuditAction.LOGIN,
                         entity_type="user", entity_id=str(user.id),
                         details={"mfa": True})
    db.commit()
    return {
        "access_token": create_token(str(user.id), {"username": user.username, "role": user.role.value, "mfa": True}),
        "token_type": "bearer",
    }


class MfaTokenIn(BaseModel):
    token: str


@router.post("/mfa/setup")
def mfa_setup(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> dict:
    return mfa.start_setup(db, user)


@router.post("/mfa/enable")
def mfa_enable(body: MfaTokenIn, user: User = Depends(get_current_user),
               db: Session = Depends(get_db)) -> dict:
    try:
        return mfa.enable(db, user, body.token)
    except PermissionError as e:
        raise HTTPException(status_code=401, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/mfa/disable")
def mfa_disable(body: MfaTokenIn, user: User = Depends(get_current_user),
                db: Session = Depends(get_db)) -> dict:
    try:
        return mfa.disable(db, user, body.token)
    except PermissionError as e:
        raise HTTPException(status_code=401, detail=str(e)) from e


@router.get("/me")
def me(user: User = Depends(get_current_user)) -> dict:
    return {
        "id": str(user.id), "username": user.username, "email": user.email,
        "role": user.role.value, "mfa_enabled": user.mfa_enabled,
    }


@router.get("/sso/login")
def sso_login(db: Session = Depends(get_db)):
    try:
        url, _state = sso.build_authorize_url(db)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return RedirectResponse(url=url, status_code=302)


@router.get("/sso/callback")
def sso_callback(request: Request, code: str | None = None, error: str | None = None,
                 db: Session = Depends(get_db)):
    if error or not code:
        raise HTTPException(status_code=400, detail=f"SSO error: {error or 'no code'}")
    try:
        _user, jwt = sso.complete_sso(db, code=code)
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e)) from e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    ui_base = str(request.url).split("/api/")[0]
    return RedirectResponse(url=f"{ui_base}/?sso_token={jwt}", status_code=302)
