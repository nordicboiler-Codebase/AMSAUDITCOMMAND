from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.core.db import get_db
from backend.core.security import get_current_user, require_role
from backend.models import User
from backend.services import email as email_svc, retention, sso

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


class EmailConfigIn(BaseModel):
    enabled: bool | None = None
    provider: str | None = None
    from_address: str | None = None
    from_name: str | None = None

    smtp_host: str | None = None
    smtp_port: int | None = None
    smtp_user: str | None = None
    smtp_password: str | None = None
    smtp_use_tls: bool | None = None
    smtp_use_ssl: bool | None = None

    use_oauth2: bool | None = None
    oauth_tenant_id: str | None = None
    oauth_client_id: str | None = None
    oauth_client_secret: str | None = None
    oauth_scope: str | None = None

    graph_tenant_id: str | None = None
    graph_client_id: str | None = None
    graph_client_secret: str | None = None
    graph_sender_upn: str | None = None


class TestEmailIn(BaseModel):
    to: str


@router.get("/email")
def get_email(db: Session = Depends(get_db), _u: User = Depends(get_current_user)) -> dict:
    return email_svc.get_public_config(db)


@router.put("/email")
def update_email(
    body: EmailConfigIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("ADMIN")),
) -> dict:
    new_values = {k: v for k, v in body.model_dump().items() if v is not None}
    return email_svc.save_config(db, new_values=new_values, user_id=user.id)


@router.post("/email/test")
def test_email(
    body: TestEmailIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("ADMIN")),
) -> dict:
    try:
        return email_svc.send_test_email(db, to=body.to, user_id=user.id)
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Send failed: {e}") from e


class RetentionIn(BaseModel):
    enabled: bool | None = None
    default_days: int | None = None
    per_subledger_days: dict[str, int] | None = None
    preserve_findings_referenced: bool | None = None


@router.get("/retention")
def get_retention(db: Session = Depends(get_db), _u: User = Depends(get_current_user)) -> dict:
    return retention.get_policy(db)


@router.put("/retention")
def update_retention(
    body: RetentionIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_role("ADMIN")),
) -> dict:
    new_values = {k: v for k, v in body.model_dump().items() if v is not None}
    return retention.save_policy(db, new_values=new_values, user_id=user.id)


@router.post("/retention/scan")
def scan_retention(
    db: Session = Depends(get_db), _u: User = Depends(require_role("ADMIN"))
) -> dict:
    return retention.purge(db, dry_run=True)


@router.post("/retention/purge")
def purge_retention(
    db: Session = Depends(get_db), user: User = Depends(require_role("ADMIN"))
) -> dict:
    return retention.purge(db, user_id=user.id, dry_run=False)
