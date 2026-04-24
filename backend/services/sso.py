from __future__ import annotations

import secrets
import uuid
from typing import Any
from urllib.parse import urlencode

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.core.security import create_token, hash_password
from backend.models import AuditAction, User
from backend.models.enums import UserRole
from backend.services import audit_log, settings_store

CATEGORY = "sso"
CONFIG_KEY = "provider"

SECRET_FIELDS = {"client_secret"}

DEFAULT_CONFIG: dict[str, Any] = {
    "enabled": False,
    "provider": "azure_ad",
    "tenant_id": "",
    "client_id": "",
    "client_secret": "",
    "redirect_uri": "",
    "authorize_url": "",
    "token_url": "",
    "userinfo_url": "",
    "scopes": ["openid", "email", "profile"],
    "allowed_domains": [],
    "auto_provision": True,
    "default_role": "AUDITOR",
}


def _fill_azure_urls(cfg: dict[str, Any]) -> dict[str, Any]:
    if cfg.get("provider") == "azure_ad" and cfg.get("tenant_id"):
        tid = cfg["tenant_id"]
        cfg.setdefault("authorize_url", f"https://login.microsoftonline.com/{tid}/oauth2/v2.0/authorize")
        cfg.setdefault("token_url", f"https://login.microsoftonline.com/{tid}/oauth2/v2.0/token")
        cfg.setdefault("userinfo_url", "https://graph.microsoft.com/oidc/userinfo")
    return cfg


def get_config(db: Session, *, decrypt: bool = False) -> dict[str, Any]:
    stored = settings_store.get_setting(db, CATEGORY, CONFIG_KEY) or {}
    cfg = {**DEFAULT_CONFIG, **stored}
    if decrypt and cfg.get("client_secret"):
        cfg["client_secret"] = settings_store.decrypt_secret(cfg["client_secret"])
    return _fill_azure_urls(cfg)


def get_public_config(db: Session) -> dict[str, Any]:
    cfg = get_config(db, decrypt=False)
    return {
        "enabled": cfg["enabled"],
        "provider": cfg["provider"],
        "tenant_id": cfg["tenant_id"],
        "client_id": cfg["client_id"],
        "redirect_uri": cfg["redirect_uri"],
        "scopes": cfg["scopes"],
        "allowed_domains": cfg["allowed_domains"],
        "auto_provision": cfg["auto_provision"],
        "default_role": cfg["default_role"],
    }


def save_config(db: Session, *, new_values: dict[str, Any], user_id: uuid.UUID) -> dict[str, Any]:
    existing = get_config(db, decrypt=True)
    merged = {**existing, **new_values}
    if "client_secret" in new_values and new_values["client_secret"]:
        if new_values["client_secret"] != settings_store.SECRET_SENTINEL:
            merged["client_secret"] = settings_store.encrypt_secret(new_values["client_secret"])
        else:
            merged["client_secret"] = existing.get("client_secret") or ""
    else:
        merged["client_secret"] = settings_store.encrypt_secret(existing.get("client_secret", "")) \
            if existing.get("client_secret") and not existing["client_secret"].startswith("gAAAAA") \
            else existing.get("client_secret", "")
    merged = _fill_azure_urls(merged)
    settings_store.upsert_setting(
        db, category=CATEGORY, key=CONFIG_KEY, value=merged, is_secret=True, updated_by=user_id
    )
    audit_log.log_action(
        db, user_id=user_id, action=AuditAction.TEMPLATE_UPDATE,
        entity_type="app_settings", entity_id="sso.provider",
        details={"enabled": merged.get("enabled"), "provider": merged.get("provider")},
    )
    db.commit()
    return get_public_config(db)


def build_authorize_url(db: Session, *, state: str | None = None) -> tuple[str, str]:
    cfg = get_config(db, decrypt=False)
    if not cfg["enabled"]:
        raise ValueError("SSO is not enabled")
    for field in ("client_id", "redirect_uri", "authorize_url"):
        if not cfg.get(field):
            raise ValueError(f"SSO config missing: {field}")
    state = state or secrets.token_urlsafe(24)
    params = {
        "client_id": cfg["client_id"],
        "response_type": "code",
        "redirect_uri": cfg["redirect_uri"],
        "response_mode": "query",
        "scope": " ".join(cfg["scopes"]),
        "state": state,
    }
    return f"{cfg['authorize_url']}?{urlencode(params)}", state


def _provision_or_get_user(db: Session, email: str, name: str | None, cfg: dict) -> User:
    email = (email or "").lower().strip()
    if not email:
        raise ValueError("ID token has no email claim")

    allowed = cfg.get("allowed_domains") or []
    if allowed:
        domain = email.split("@")[-1]
        if domain not in allowed:
            raise PermissionError(f"Domain '{domain}' is not in allowed_domains")

    user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if user:
        return user
    if not cfg.get("auto_provision", True):
        raise PermissionError("Auto-provisioning is disabled and user is not pre-registered")

    default_role = UserRole(cfg.get("default_role", "AUDITOR"))
    username = email.split("@")[0]
    suffix = 1
    base = username
    while db.execute(select(User).where(User.username == username)).scalar_one_or_none():
        username = f"{base}{suffix}"
        suffix += 1
    user = User(
        username=username,
        email=email,
        password_hash=hash_password(secrets.token_urlsafe(32)),
        role=default_role,
        is_active=True,
    )
    db.add(user)
    db.flush()
    return user


def complete_sso(db: Session, *, code: str) -> tuple[User, str]:
    cfg = get_config(db, decrypt=True)
    if not cfg["enabled"]:
        raise ValueError("SSO is not enabled")

    token_payload = {
        "client_id": cfg["client_id"],
        "client_secret": cfg["client_secret"],
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": cfg["redirect_uri"],
        "scope": " ".join(cfg["scopes"]),
    }
    with httpx.Client(timeout=20.0) as client:
        token_resp = client.post(cfg["token_url"], data=token_payload)
        token_resp.raise_for_status()
        token_data = token_resp.json()
        access_token = token_data.get("access_token")
        if not access_token:
            raise ValueError(f"No access_token in response: {token_data}")

        userinfo_resp = client.get(
            cfg["userinfo_url"], headers={"Authorization": f"Bearer {access_token}"}
        )
        userinfo_resp.raise_for_status()
        userinfo = userinfo_resp.json()

    email = userinfo.get("email") or userinfo.get("preferred_username") or userinfo.get("upn")
    name = userinfo.get("name") or userinfo.get("displayName")
    user = _provision_or_get_user(db, email, name, cfg)

    audit_log.log_action(
        db, user_id=user.id, action=AuditAction.LOGIN, entity_type="user", entity_id=str(user.id),
        details={"sso": True, "provider": cfg.get("provider"), "email": email},
    )
    db.commit()
    jwt = create_token(str(user.id), {"username": user.username, "role": user.role.value, "sso": True})
    return user, jwt
