from __future__ import annotations

import base64
import smtplib
import uuid
from email.message import EmailMessage
from typing import Any

import httpx
from sqlalchemy.orm import Session

from backend.models import AuditAction
from backend.services import audit_log, settings_store

CATEGORY = "email"
CONFIG_KEY = "provider"

SECRET_FIELDS = {"smtp_password", "oauth_client_secret"}

DEFAULT_CONFIG: dict[str, Any] = {
    "enabled": False,
    "provider": "smtp",
    "from_address": "",
    "from_name": "TechSource Audit Analytics",

    "smtp_host": "",
    "smtp_port": 587,
    "smtp_user": "",
    "smtp_password": "",
    "smtp_use_tls": True,
    "smtp_use_ssl": False,

    "use_oauth2": False,
    "oauth_tenant_id": "",
    "oauth_client_id": "",
    "oauth_client_secret": "",
    "oauth_scope": "https://outlook.office365.com/.default",

    "graph_tenant_id": "",
    "graph_client_id": "",
    "graph_client_secret": "",
    "graph_sender_upn": "",
}


def get_config(db: Session, *, decrypt: bool = False) -> dict[str, Any]:
    stored = settings_store.get_setting(db, CATEGORY, CONFIG_KEY) or {}
    cfg = {**DEFAULT_CONFIG, **stored}
    if decrypt:
        for f in SECRET_FIELDS | {"graph_client_secret"}:
            if cfg.get(f):
                cfg[f] = settings_store.decrypt_secret(cfg[f])
    return cfg


def get_public_config(db: Session) -> dict[str, Any]:
    cfg = get_config(db, decrypt=False)
    return settings_store.redact_secrets(cfg, SECRET_FIELDS | {"graph_client_secret"})


def save_config(db: Session, *, new_values: dict[str, Any], user_id: uuid.UUID) -> dict[str, Any]:
    existing = get_config(db, decrypt=True)
    merged = {**existing, **new_values}
    for f in SECRET_FIELDS | {"graph_client_secret"}:
        incoming = new_values.get(f)
        if incoming and incoming != settings_store.SECRET_SENTINEL:
            merged[f] = settings_store.encrypt_secret(incoming)
        elif existing.get(f):
            merged[f] = settings_store.encrypt_secret(existing[f])
        else:
            merged[f] = ""
    settings_store.upsert_setting(
        db, category=CATEGORY, key=CONFIG_KEY, value=merged, is_secret=True, updated_by=user_id
    )
    audit_log.log_action(
        db, user_id=user_id, action=AuditAction.TEMPLATE_UPDATE,
        entity_type="app_settings", entity_id="email.provider",
        details={"enabled": merged.get("enabled"), "provider": merged.get("provider")},
    )
    db.commit()
    return get_public_config(db)


def _acquire_oauth_token(tenant_id: str, client_id: str, client_secret: str, scope: str) -> str:
    url = f"https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
    with httpx.Client(timeout=15.0) as client:
        r = client.post(url, data={
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret,
            "scope": scope,
        })
        r.raise_for_status()
        return r.json()["access_token"]


def _send_via_smtp(cfg: dict, msg: EmailMessage) -> None:
    if cfg["smtp_use_ssl"]:
        server = smtplib.SMTP_SSL(cfg["smtp_host"], cfg["smtp_port"], timeout=20)
    else:
        server = smtplib.SMTP(cfg["smtp_host"], cfg["smtp_port"], timeout=20)
    try:
        if cfg["smtp_use_tls"] and not cfg["smtp_use_ssl"]:
            server.starttls()
        if cfg.get("use_oauth2") and cfg.get("oauth_tenant_id"):
            token = _acquire_oauth_token(
                cfg["oauth_tenant_id"], cfg["oauth_client_id"],
                cfg["oauth_client_secret"], cfg["oauth_scope"],
            )
            auth_str = f"user={cfg['smtp_user']}\x01auth=Bearer {token}\x01\x01"
            server.docmd("AUTH", "XOAUTH2 " + base64.b64encode(auth_str.encode()).decode())
        elif cfg.get("smtp_password"):
            server.login(cfg["smtp_user"], cfg["smtp_password"])
        server.send_message(msg)
    finally:
        server.quit()


def _send_via_graph(cfg: dict, to: list[str], subject: str, body_html: str) -> None:
    token = _acquire_oauth_token(
        cfg["graph_tenant_id"], cfg["graph_client_id"],
        cfg["graph_client_secret"], "https://graph.microsoft.com/.default",
    )
    sender = cfg.get("graph_sender_upn") or cfg.get("from_address")
    payload = {
        "message": {
            "subject": subject,
            "body": {"contentType": "HTML", "content": body_html},
            "toRecipients": [{"emailAddress": {"address": a}} for a in to],
            "from": {"emailAddress": {"address": sender}},
        },
        "saveToSentItems": "true",
    }
    with httpx.Client(timeout=20.0) as client:
        r = client.post(
            f"https://graph.microsoft.com/v1.0/users/{sender}/sendMail",
            json=payload, headers={"Authorization": f"Bearer {token}"},
        )
        if r.status_code >= 300:
            raise RuntimeError(f"Graph sendMail failed: {r.status_code} {r.text}")


def send_email(db: Session, *, to: list[str], subject: str, body_html: str,
               body_text: str | None = None) -> dict:
    cfg = get_config(db, decrypt=True)
    if not cfg["enabled"]:
        raise RuntimeError("Email is not enabled")
    if not cfg.get("from_address"):
        raise RuntimeError("Email from_address not configured")

    if cfg["provider"] == "graph":
        _send_via_graph(cfg, to, subject, body_html)
    else:
        msg = EmailMessage()
        msg["From"] = f"{cfg.get('from_name','')} <{cfg['from_address']}>".strip()
        msg["To"] = ", ".join(to)
        msg["Subject"] = subject
        if body_text:
            msg.set_content(body_text)
        msg.add_alternative(body_html, subtype="html")
        _send_via_smtp(cfg, msg)

    return {"sent": True, "to": to, "provider": cfg["provider"]}


def send_test_email(db: Session, *, to: str, user_id: uuid.UUID) -> dict:
    result = send_email(
        db, to=[to],
        subject="TechSource Audit Analytics — test email",
        body_html="<p>This is a test email from TechSource Audit Analytics.</p>"
                  "<p>If you received this, outbound email is configured correctly.</p>",
        body_text="This is a test email from TechSource Audit Analytics.",
    )
    audit_log.log_action(
        db, user_id=user_id, action=AuditAction.EXPORT, entity_type="email",
        entity_id="test", details={"to": to, "provider": result["provider"]},
    )
    db.commit()
    return result
