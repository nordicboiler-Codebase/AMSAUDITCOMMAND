from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.core.db import get_db
from backend.core.security import get_current_user
from backend.models import TestTemplate, User
from backend.models.enums import SubledgerType, TemplateCategory, TemplateVisibility
from backend.templates import catalog as tpl_catalog

router = APIRouter()


class TemplateIn(BaseModel):
    code: str
    name: str
    detector_name: str
    default_params: dict
    description: str = ""
    subledger: SubledgerType | None = None
    category: TemplateCategory = TemplateCategory.ANALYTICAL
    default_weight: float = 1.0
    tags: list[str] = []
    visibility: TemplateVisibility = TemplateVisibility.PRIVATE


class CloneIn(BaseModel):
    target_project_id: uuid.UUID
    overrides: dict | None = None
    new_code: str | None = None


@router.get("")
def list_templates(
    subledger: SubledgerType | None = None,
    category: TemplateCategory | None = None,
    search: str | None = None,
    db: Session = Depends(get_db),
    _u: User = Depends(get_current_user),
) -> list[dict]:
    rows = tpl_catalog.list_templates(db, subledger=subledger, category=category, search=search)
    return [_out(t) for t in rows]


@router.get("/{code}")
def get_template(code: str, db: Session = Depends(get_db),
                 _u: User = Depends(get_current_user)) -> dict:
    return _out(tpl_catalog.get_template(db, code))


@router.post("")
def create_template(body: TemplateIn, db: Session = Depends(get_db),
                    user: User = Depends(get_current_user)) -> dict:
    try:
        tpl = tpl_catalog.create_template(
            db, code=body.code, name=body.name, detector_name=body.detector_name,
            default_params=body.default_params, description=body.description,
            subledger=body.subledger, category=body.category, default_weight=body.default_weight,
            tags=body.tags, owner_id=user.id, visibility=body.visibility, user_id=user.id,
        )
    except tpl_catalog.TemplateError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    db.commit()
    return _out(tpl)


@router.post("/{code}/clone")
def clone_template(code: str, body: CloneIn, db: Session = Depends(get_db),
                   user: User = Depends(get_current_user)) -> dict:
    tpl = tpl_catalog.clone_template(db, code, body.target_project_id, user.id,
                                     overrides=body.overrides, new_code=body.new_code)
    db.commit()
    return _out(tpl)


def _out(t: TestTemplate) -> dict:
    return {
        "id": str(t.id),
        "code": t.code,
        "name": t.name,
        "description": t.description,
        "detector_name": t.detector_name,
        "default_params": t.default_params,
        "subledger_type": t.subledger_type.value if t.subledger_type else None,
        "category": t.category.value if t.category else None,
        "default_weight": t.default_weight,
        "tags": list(t.tags or []),
        "is_system": t.is_system,
        "version": t.version,
        "visibility": t.visibility.value if t.visibility else None,
    }
