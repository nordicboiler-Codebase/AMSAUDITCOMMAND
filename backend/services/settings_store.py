from __future__ import annotations

import base64
import hashlib
import uuid
from typing import Any

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.core.config import get_settings
from backend.models import AppSetting

SECRET_SENTINEL = "__secret__"


def _fernet() -> Fernet:
    s = get_settings()
    digest = hashlib.sha256(s.secret_key.encode("utf-8")).digest()
    key = base64.urlsafe_b64encode(digest)
    return Fernet(key)


def encrypt_secret(value: str) -> str:
    if not value:
        return ""
    return _fernet().encrypt(value.encode("utf-8")).decode("ascii")


def decrypt_secret(token: str) -> str:
    if not token:
        return ""
    try:
        return _fernet().decrypt(token.encode("ascii")).decode("utf-8")
    except InvalidToken:
        return ""


def get_setting(db: Session, category: str, key: str) -> dict[str, Any] | None:
    row = db.execute(
        select(AppSetting).where(AppSetting.category == category, AppSetting.key == key)
    ).scalar_one_or_none()
    if not row:
        return None
    return dict(row.value_json or {})


def get_category(db: Session, category: str) -> dict[str, dict[str, Any]]:
    rows = db.execute(select(AppSetting).where(AppSetting.category == category)).scalars()
    return {r.key: dict(r.value_json or {}) for r in rows}


def upsert_setting(
    db: Session,
    *,
    category: str,
    key: str,
    value: dict[str, Any],
    is_secret: bool = False,
    updated_by: uuid.UUID | None = None,
) -> AppSetting:
    row = db.execute(
        select(AppSetting).where(AppSetting.category == category, AppSetting.key == key)
    ).scalar_one_or_none()
    if row:
        row.value_json = value
        row.is_secret = is_secret
        row.updated_by = updated_by
    else:
        row = AppSetting(
            category=category, key=key, value_json=value, is_secret=is_secret, updated_by=updated_by
        )
        db.add(row)
    db.flush()
    return row


def redact_secrets(payload: dict[str, Any], secret_fields: set[str]) -> dict[str, Any]:
    out = dict(payload)
    for f in secret_fields:
        if out.get(f):
            out[f] = SECRET_SENTINEL
    return out
