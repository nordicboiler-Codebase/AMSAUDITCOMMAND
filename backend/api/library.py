from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.core.db import get_db
from backend.core.security import get_current_user
from backend.models import TestTemplate, User
from backend.models.enums import SubledgerType, TemplateVisibility
from backend.services import library
from backend.templates import catalog as tpl_catalog

router = APIRouter()


class PublishIn(BaseModel):
    template_id: uuid.UUID
    visibility: TemplateVisibility


class ForkIn(BaseModel):
    code: str
    target_project_id: uuid.UUID
    overrides: dict | None = None
    new_code: str | None = None


@router.get("/shared")
def list_shared(
    subledger: SubledgerType | None = None,
    search: str | None = None,
    db: Session = Depends(get_db),
    _u: User = Depends(get_current_user),
) -> list[dict]:
    rows = library.list_shared_templates(db, subledger=subledger, search=search)
    return [_out(t) for t in rows]


@router.post("/publish")
def publish(body: PublishIn, db: Session = Depends(get_db),
            user: User = Depends(get_current_user)) -> dict:
    try:
        tpl = library.publish_template(db, template_id=body.template_id,
                                       visibility=body.visibility, user_id=user.id)
    except tpl_catalog.TemplateError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return _out(tpl)


@router.post("/fork")
def fork(body: ForkIn, db: Session = Depends(get_db),
         user: User = Depends(get_current_user)) -> dict:
    try:
        tpl = library.fork_template(db, code=body.code, target_project_id=body.target_project_id,
                                    user_id=user.id, overrides=body.overrides, new_code=body.new_code)
    except tpl_catalog.TemplateError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return _out(tpl)


@router.get("/{code}/versions")
def versions(code: str, db: Session = Depends(get_db),
             _u: User = Depends(get_current_user)) -> list[dict]:
    rows = library.get_template_versions(db, code)
    return [_out(t) for t in rows]


@router.get("/{code}/diff")
def diff(code: str, v1: int, v2: int, db: Session = Depends(get_db),
         _u: User = Depends(get_current_user)) -> dict:
    try:
        return library.diff_template_versions(db, code, v1, v2)
    except tpl_catalog.TemplateError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


def _out(t: TestTemplate) -> dict:
    return {
        "id": str(t.id),
        "code": t.code,
        "name": t.name,
        "version": t.version,
        "detector_name": t.detector_name,
        "default_params": t.default_params,
        "subledger_type": t.subledger_type.value if t.subledger_type else None,
        "visibility": t.visibility.value if t.visibility else None,
        "tags": list(t.tags or []),
    }
