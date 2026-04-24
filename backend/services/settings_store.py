from __future__ import annotations

import base64
import hashlib
import os
import uuid
from typing import Any

from cryptography.fernet import Fernet, InvalidToken, MultiFernet
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.core.config import get_settings
from backend.models import AppSetting

SECRET_SENTINEL = "__secret__"


def _derive(secret: str) -> bytes:
    digest = hashlib.sha256(secret.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


def _keychain() -> MultiFernet:
    """Return a MultiFernet keychain.

    Reads:
      - SECRET_KEY (current)
      - SECRET_KEY_PREVIOUS (comma-separated old keys, decrypt-only)

    The current key encrypts new ciphertext; previous keys decrypt old ciphertext
    so rotation is transparent. Re-encrypt in place by calling `rotate_bytes()`.
    """
    s = get_settings()
    keys = [Fernet(_derive(s.secret_key))]
    prev = os.environ.get("SECRET_KEY_PREVIOUS", "").strip()
    if prev:
        for p in prev.split(","):
            p = p.strip()
            if p:
                keys.append(Fernet(_derive(p)))
    return MultiFernet(keys)


def encrypt_secret(value: str) -> str:
    if not value:
        return ""
    return _keychain().encrypt(value.encode("utf-8")).decode("ascii")


def decrypt_secret(token: str) -> str:
    if not token:
        return ""
    try:
        return _keychain().decrypt(token.encode("ascii")).decode("utf-8")
    except InvalidToken:
        return ""


def rotate_bytes(token: bytes) -> bytes:
    """Re-encrypt ciphertext with the current primary key (used by key-rotation job)."""
    return _keychain().rotate(token)


def rotate_secret(token: str) -> str:
    if not token:
        return ""
    try:
        return _keychain().rotate(token.encode("ascii")).decode("ascii")
    except InvalidToken:
        return token


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


def encrypt_bytes(data: bytes) -> bytes:
    return _keychain().encrypt(data)


def decrypt_bytes(token: bytes) -> bytes:
    return _keychain().decrypt(token)
