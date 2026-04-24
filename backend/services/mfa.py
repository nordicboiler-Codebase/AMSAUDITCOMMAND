from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import pyotp
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from backend.core.config import get_settings
from backend.models import AuditAction, User
from backend.services import audit_log

ISSUER = "TechSource Audit Analytics"
MFA_CHALLENGE_EXPIRE_MINUTES = 5


def generate_secret() -> str:
    return pyotp.random_base32()


def provisioning_uri(user: User, secret: str) -> str:
    return pyotp.TOTP(secret).provisioning_uri(name=user.email, issuer_name=ISSUER)


def verify_totp(secret: str, token: str) -> bool:
    if not secret or not token:
        return False
    return pyotp.TOTP(secret).verify(token.strip(), valid_window=1)


def start_setup(db: Session, user: User) -> dict[str, Any]:
    secret = generate_secret()
    user.totp_secret = secret
    user.mfa_enabled = False
    db.flush()
    db.commit()
    return {
        "secret": secret,
        "provisioning_uri": provisioning_uri(user, secret),
        "issuer": ISSUER,
        "account": user.email,
    }


def enable(db: Session, user: User, token: str) -> dict[str, Any]:
    if not user.totp_secret:
        raise ValueError("No secret staged. Call /api/auth/mfa/setup first.")
    if not verify_totp(user.totp_secret, token):
        raise PermissionError("Invalid TOTP code")
    user.mfa_enabled = True
    audit_log.log_action(
        db, user_id=user.id, action=AuditAction.TEMPLATE_UPDATE,
        entity_type="user_mfa", entity_id=str(user.id),
        details={"mfa_enabled": True},
    )
    db.commit()
    return {"enabled": True}


def disable(db: Session, user: User, token: str) -> dict[str, Any]:
    if not user.mfa_enabled or not user.totp_secret:
        return {"enabled": False}
    if not verify_totp(user.totp_secret, token):
        raise PermissionError("Invalid TOTP code")
    user.mfa_enabled = False
    user.totp_secret = None
    audit_log.log_action(
        db, user_id=user.id, action=AuditAction.TEMPLATE_UPDATE,
        entity_type="user_mfa", entity_id=str(user.id),
        details={"mfa_enabled": False},
    )
    db.commit()
    return {"enabled": False}


def create_challenge_token(user_id: uuid.UUID) -> str:
    s = get_settings()
    exp = datetime.now(timezone.utc) + timedelta(minutes=MFA_CHALLENGE_EXPIRE_MINUTES)
    payload = {"sub": str(user_id), "exp": exp, "type": "mfa_challenge"}
    return jwt.encode(payload, s.secret_key, algorithm=s.jwt_algorithm)


def decode_challenge_token(token: str) -> uuid.UUID:
    s = get_settings()
    try:
        payload = jwt.decode(token, s.secret_key, algorithms=[s.jwt_algorithm])
    except JWTError as e:
        raise PermissionError(f"Invalid challenge token: {e}") from e
    if payload.get("type") != "mfa_challenge":
        raise PermissionError("Token is not an MFA challenge")
    return uuid.UUID(payload["sub"])
