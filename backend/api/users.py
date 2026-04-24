from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.core.db import get_db
from backend.core.security import require_role
from backend.models import User

router = APIRouter()


@router.get("")
def list_users(db: Session = Depends(get_db), _admin=Depends(require_role("ADMIN"))) -> list[dict]:
    users = db.execute(select(User)).scalars().all()
    return [
        {"id": str(u.id), "username": u.username, "email": u.email, "role": u.role.value, "is_active": u.is_active}
        for u in users
    ]
