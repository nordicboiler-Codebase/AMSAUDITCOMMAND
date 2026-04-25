"""Admin endpoints for managing the AI provider configuration."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.core.db import get_db
from backend.core.security import get_current_user
from backend.models import AuditAction, User, UserRole
from backend.services import audit_log, llm, settings_store

router = APIRouter()


class ProviderUpdate(BaseModel):
    enabled: bool = False
    api_key: str | None = None  # None means "leave unchanged"
    model: str | None = None


class AiSettingsUpdate(BaseModel):
    active: str | None = None
    providers: dict[str, ProviderUpdate] | None = None


def _require_admin(user: User) -> None:
    if user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="ADMIN role required")


@router.get("/settings/ai")
def get_ai_settings(db: Session = Depends(get_db),
                    user: User = Depends(get_current_user)) -> dict:
    """Returns redacted provider config for the admin UI."""
    _require_admin(user)
    status = llm.get_status(db)
    # Include redacted state for display: api_key shown as sentinel only.
    redacted_providers = []
    for p in status["providers"]:
        cfg = settings_store.get_setting(db, llm.CATEGORY, p["provider"]) or {}
        redacted_providers.append({
            **p,
            "api_key": settings_store.SECRET_SENTINEL if cfg.get("api_key") else "",
        })
    return {
        "active": status["active"],
        "enabled": status["enabled"],
        "reason": status["reason"],
        "model": status["model"],
        "legacy_env_active": status["legacy_env_active"],
        "providers": redacted_providers,
    }


@router.put("/settings/ai")
def update_ai_settings(body: AiSettingsUpdate, db: Session = Depends(get_db),
                       user: User = Depends(get_current_user)) -> dict:
    _require_admin(user)
    if body.providers:
        for prov, upd in body.providers.items():
            if prov not in llm.PROVIDERS:
                raise HTTPException(status_code=400, detail=f"Unknown provider: {prov}")
            llm.save_provider(
                db, provider=prov, enabled=upd.enabled,
                api_key=upd.api_key,
                model=upd.model or llm.DEFAULT_MODEL[prov],
                updated_by=user.id,
            )
    if body.active is not None:
        # Allow clearing active by passing empty string.
        active_val: str | None = body.active or None
        if active_val is not None and active_val not in llm.PROVIDERS:
            raise HTTPException(status_code=400, detail=f"Unknown provider: {active_val}")
        llm.set_active(db, active_val, updated_by=user.id)

    audit_log.log_action(
        db, user_id=user.id, action=AuditAction.TEMPLATE_UPDATE,
        entity_type="ai_settings", entity_id=None,
        details={
            "providers_updated": list((body.providers or {}).keys()),
            "active": body.active,
        },
    )
    db.commit()
    return get_ai_settings(db=db, user=user)


@router.post("/settings/ai/{provider}/test")
def test_provider(provider: str, db: Session = Depends(get_db),
                  user: User = Depends(get_current_user)) -> dict:
    _require_admin(user)
    if provider not in llm.PROVIDERS:
        raise HTTPException(status_code=400, detail=f"Unknown provider: {provider}")
    result = llm.test_provider(db, provider)
    audit_log.log_action(
        db, user_id=user.id, action=AuditAction.TEMPLATE_UPDATE,
        entity_type="ai_settings", entity_id=None,
        details={"action": "test_provider", "provider": provider, "ok": result.get("ok")},
    )
    db.commit()
    return result
