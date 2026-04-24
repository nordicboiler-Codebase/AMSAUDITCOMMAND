from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.core.db import get_db
from backend.core.security import get_current_user
from backend.models import User
from backend.services import feedback

router = APIRouter()


@router.get("/precision")
def precision(db: Session = Depends(get_db),
              _u: User = Depends(get_current_user)) -> dict:
    """Precision per detector and per template, computed from finding_labels."""
    return feedback.precision_report(db)
