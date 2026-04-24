from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.core.db import get_db
from backend.core.security import get_current_user
from backend.models import Dataset, FieldSensitivity, User
from backend.services import acl

router = APIRouter()

VALID_CLASSES = {"PUBLIC", "INTERNAL", "CONFIDENTIAL", "RESTRICTED", "PII", "FINANCIAL"}


class FieldIn(BaseModel):
    field_name: str
    classification: str
    notes: str | None = None


def _out(f: FieldSensitivity) -> dict:
    return {
        "id": str(f.id), "dataset_id": str(f.dataset_id),
        "field_name": f.field_name, "classification": f.classification,
        "notes": f.notes,
        "set_at": f.set_at.isoformat() if f.set_at else None,
        "set_by": str(f.set_by) if f.set_by else None,
    }


@router.get("/datasets/{dataset_id}/field-sensitivity")
def list_fields(dataset_id: uuid.UUID, db: Session = Depends(get_db),
                user: User = Depends(get_current_user)) -> list[dict]:
    ds = db.get(Dataset, dataset_id)
    if not ds:
        raise HTTPException(status_code=404, detail="Dataset not found")
    acl.assert_permission(db, project_id=ds.project_id, user=user, permission=acl.Permission.VIEW)
    rows = list(db.execute(
        select(FieldSensitivity).where(FieldSensitivity.dataset_id == dataset_id)
        .order_by(FieldSensitivity.field_name)
    ).scalars())
    return [_out(f) for f in rows]


@router.put("/datasets/{dataset_id}/field-sensitivity")
def set_field(dataset_id: uuid.UUID, body: FieldIn, db: Session = Depends(get_db),
              user: User = Depends(get_current_user)) -> dict:
    if body.classification not in VALID_CLASSES:
        raise HTTPException(
            status_code=400,
            detail=f"classification must be one of {sorted(VALID_CLASSES)}",
        )
    ds = db.get(Dataset, dataset_id)
    if not ds:
        raise HTTPException(status_code=404, detail="Dataset not found")
    acl.assert_permission(db, project_id=ds.project_id, user=user, permission=acl.Permission.EDIT)
    existing = db.execute(
        select(FieldSensitivity).where(
            FieldSensitivity.dataset_id == dataset_id,
            FieldSensitivity.field_name == body.field_name,
        )
    ).scalar_one_or_none()
    if existing:
        existing.classification = body.classification
        existing.notes = body.notes
        existing.set_by = user.id
        row = existing
    else:
        row = FieldSensitivity(
            dataset_id=dataset_id, field_name=body.field_name,
            classification=body.classification, notes=body.notes, set_by=user.id,
        )
        db.add(row)
    db.commit()
    return _out(row)
