from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.core.db import get_db
from backend.core.security import get_current_user, require_role
from backend.models import User
from backend.services import sso

router = APIRouter()


class SsoConfigIn(BaseModel):
    enabled: bool | None = None
    provider: str | None = None
    tenant_id: str | None = None
    client_id: str | None = None
    client_secret: str | None = None
    redirect_uri: str | None = None
    authorize_url: str | None = None
    token_url: str | None = None
    userinfo_url: str | None = None
    scopes: list[str] | None = None
    allowed_domains: list[str] | None = None
    auto_provision: bool | None = None
    default_role: str | None = None


@router.get("/sso")
def get_sso(db: Session = Depends(get_db), _u: User = Depends(get_current_user)) -> dict:
    return sso.get_public_config(db)


@router.put("/sso")
def update_sso(
    body: SsoConfigIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("ADMIN")),
) -> dict:
    new_values = {k: v for k, v in body.model_dump().items() if v is not None}
    try:
        return sso.save_config(db, new_values=new_values, user_id=user.id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get("/sso/status")
def sso_status(db: Session = Depends(get_db)) -> dict:
    cfg = sso.get_public_config(db)
    return {"enabled": cfg["enabled"], "provider": cfg["provider"]}
