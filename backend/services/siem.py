"""Outbound SIEM / syslog webhook for audit_log events.

Config stored in app_settings under category 'siem', key 'webhook':
  {
    "enabled": true,
    "url": "https://collector.example.com/audit-sink",
    "auth_header": "Bearer xxxx",   # optional
    "format": "json"                 # future: "splunk_hec", "cef"
  }

Non-blocking: fire-and-forget with a short timeout so a slow collector doesn't stall API.
"""
from __future__ import annotations

import logging
from threading import Thread
from typing import Any

from sqlalchemy.orm import Session

from backend.services import settings_store

log = logging.getLogger(__name__)

CATEGORY = "siem"
KEY = "webhook"


def get_config(db: Session) -> dict[str, Any]:
    return settings_store.get_setting(db, CATEGORY, KEY) or {"enabled": False}


def save_config(db: Session, *, new_values: dict[str, Any], user_id=None) -> dict[str, Any]:
    current = get_config(db)
    merged = {**current, **{k: v for k, v in new_values.items() if v is not None}}
    settings_store.upsert_setting(
        db, category=CATEGORY, key=KEY, value=merged, is_secret=True, updated_by=user_id,
    )
    db.commit()
    return {k: ("***" if k == "auth_header" and v else v) for k, v in merged.items()}


def forward_event(db: Session, entry: dict[str, Any]) -> None:
    cfg = get_config(db)
    if not cfg.get("enabled") or not cfg.get("url"):
        return
    url = cfg["url"]
    headers = {"Content-Type": "application/json"}
    if cfg.get("auth_header"):
        headers["Authorization"] = cfg["auth_header"]
    payload = {
        "source": "techsource-audit-analytics",
        "event": entry,
    }

    def _send() -> None:
        try:
            import httpx

            httpx.post(url, json=payload, headers=headers, timeout=3.0)
        except Exception:
            log.exception("SIEM forward failed (non-fatal)")

    Thread(target=_send, daemon=True).start()
