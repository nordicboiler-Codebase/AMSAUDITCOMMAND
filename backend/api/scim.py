"""SCIM 2.0 endpoints for external identity provider provisioning.

Minimal RFC-7644 subset: /scim/v2/Users (GET list, GET one, POST create, PATCH, DELETE).
Requires ADMIN bearer token. Maps IdP users to our `users` table via `external_id`.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.core.db import get_db
from backend.core.security import hash_password, require_role
from backend.models import User
from backend.models.enums import UserRole

router = APIRouter()


SCIM_USER_SCHEMA = "urn:ietf:params:scim:schemas:core:2.0:User"


def _to_scim(u: User) -> dict[str, Any]:
    return {
        "schemas": [SCIM_USER_SCHEMA],
        "id": str(u.id),
        "externalId": u.external_id,
        "userName": u.username,
        "active": u.is_active,
        "emails": [{"value": u.email, "primary": True}] if u.email else [],
        "meta": {
            "resourceType": "User",
            "created": u.created_at.isoformat() if u.created_at else None,
            "lastModified": u.updated_at.isoformat() if u.updated_at else None,
        },
        "urn:techsource:audit:role": u.role.value,
    }


class ScimUserIn(BaseModel):
    schemas: list[str] | None = None
    userName: str
    externalId: str | None = None
    active: bool = True
    emails: list[dict] | None = None
    password: str | None = None


class ScimPatchOp(BaseModel):
    op: str   # "replace" / "add" / "remove"
    path: str | None = None
    value: Any = None


class ScimPatch(BaseModel):
    schemas: list[str] | None = None
    Operations: list[ScimPatchOp]


@router.get("/Users")
def list_users(count: int = 100, startIndex: int = 1, filter: str | None = None,
               db: Session = Depends(get_db),
               _admin=Depends(require_role("ADMIN"))) -> dict:
    q = select(User)
    if filter:
        # minimal filter support: 'userName eq "alice"' or 'externalId eq "x"'
        try:
            field, _, value = filter.partition(" eq ")
            value = value.strip().strip('"')
            if field == "userName":
                q = q.where(User.username == value)
            elif field == "externalId":
                q = q.where(User.external_id == value)
        except Exception:
            pass
    rows = list(db.execute(q.offset(max(startIndex - 1, 0)).limit(count)).scalars())
    return {
        "schemas": ["urn:ietf:params:scim:api:messages:2.0:ListResponse"],
        "totalResults": len(rows),
        "itemsPerPage": count,
        "startIndex": startIndex,
        "Resources": [_to_scim(u) for u in rows],
    }


@router.get("/Users/{user_id}")
def get_user(user_id: uuid.UUID, db: Session = Depends(get_db),
             _admin=Depends(require_role("ADMIN"))) -> dict:
    u = db.get(User, user_id)
    if not u:
        raise HTTPException(status_code=404, detail="Not found")
    return _to_scim(u)


@router.post("/Users", status_code=201)
def create_user(body: ScimUserIn, db: Session = Depends(get_db),
                _admin=Depends(require_role("ADMIN"))) -> dict:
    if db.execute(select(User).where(User.username == body.userName)).scalar_one_or_none():
        raise HTTPException(status_code=409, detail="userName exists")
    email = (body.emails[0]["value"] if body.emails else f"{body.userName}@example.local")
    password = body.password or ("ScimProvisioned!" + str(uuid.uuid4())[:8] + "A1")
    u = User(
        username=body.userName, email=email, role=UserRole.AUDITOR,
        password_hash=hash_password(password),
        is_active=body.active, external_id=body.externalId, scim_source="scim",
    )
    db.add(u)
    db.commit()
    return _to_scim(u)


@router.patch("/Users/{user_id}")
def patch_user(user_id: uuid.UUID, body: ScimPatch, db: Session = Depends(get_db),
               _admin=Depends(require_role("ADMIN"))) -> dict:
    u = db.get(User, user_id)
    if not u:
        raise HTTPException(status_code=404, detail="Not found")
    for op in body.Operations:
        if op.path == "active" and op.op in ("replace", "add"):
            u.is_active = bool(op.value)
        elif op.path == "userName" and op.op == "replace":
            u.username = str(op.value)
        elif op.path == "externalId" and op.op == "replace":
            u.external_id = str(op.value)
        elif op.path in ("password",) and op.op == "replace" and op.value:
            u.password_hash = hash_password(str(op.value))
    u.updated_at = datetime.now(timezone.utc)
    db.commit()
    return _to_scim(u)


@router.delete("/Users/{user_id}", status_code=204)
def delete_user(user_id: uuid.UUID, db: Session = Depends(get_db),
                _admin=Depends(require_role("ADMIN"))) -> None:
    u = db.get(User, user_id)
    if not u:
        raise HTTPException(status_code=404, detail="Not found")
    u.is_active = False  # SCIM deprovision = deactivate, not hard-delete
    db.commit()
