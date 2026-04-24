from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.core.db import get_db
from backend.core.security import get_current_user, require_role
from backend.models import (
    Dataset, Finding, FindingStatus, Project, RiskScore, Subsidiary, TestRun, User,
)
from backend.services import acl

router = APIRouter()


class SubsidiaryIn(BaseModel):
    code: str
    name: str
    country: str | None = None
    industry: str | None = None
    risk_rating: str | None = None
    parent_code: str | None = None
    segment: str | None = None
    logo_data_uri: str | None = None
    brand_primary: str | None = None
    is_active: bool = True


class SubsidiaryUpdate(BaseModel):
    name: str | None = None
    country: str | None = None
    industry: str | None = None
    risk_rating: str | None = None
    parent_code: str | None = None
    segment: str | None = None
    logo_data_uri: str | None = None
    brand_primary: str | None = None
    is_active: bool | None = None


def _out(s: Subsidiary) -> dict:
    return {
        "id": str(s.id), "code": s.code, "name": s.name,
        "country": s.country, "industry": s.industry,
        "risk_rating": s.risk_rating, "parent_code": s.parent_code,
        "segment": s.segment, "brand_primary": s.brand_primary,
        "logo_data_uri": s.logo_data_uri, "is_active": s.is_active,
    }


@router.get("")
def list_subsidiaries(
    db: Session = Depends(get_db), _u: User = Depends(get_current_user),
) -> list[dict]:
    rows = list(db.execute(select(Subsidiary).order_by(Subsidiary.code)).scalars())
    return [_out(s) for s in rows]


@router.post("")
def create_subsidiary(body: SubsidiaryIn, db: Session = Depends(get_db),
                      _admin=Depends(require_role("ADMIN"))) -> dict:
    if db.execute(select(Subsidiary).where(Subsidiary.code == body.code)).scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Subsidiary code exists")
    s = Subsidiary(**body.model_dump())
    db.add(s)
    db.commit()
    return _out(s)


@router.patch("/{subsidiary_id}")
def update_subsidiary(subsidiary_id: uuid.UUID, body: SubsidiaryUpdate,
                      db: Session = Depends(get_db),
                      _admin=Depends(require_role("ADMIN"))) -> dict:
    s = db.get(Subsidiary, subsidiary_id)
    if not s:
        raise HTTPException(status_code=404, detail="Not found")
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(s, k, v)
    db.commit()
    return _out(s)


@router.get("/rollup")
def rollup(db: Session = Depends(get_db), user: User = Depends(get_current_user)) -> list[dict]:
    """Per-subsidiary rollup of findings, datasets, test runs. Respects ACL."""
    visible = acl.visible_project_ids(db, user=user)
    subs = list(db.execute(select(Subsidiary).where(Subsidiary.is_active.is_(True))).scalars())
    projects_by_sub: dict[uuid.UUID | None, list[uuid.UUID]] = {}
    for p in db.execute(select(Project.id, Project.subsidiary_id, Project.subsidiary_code)).all():
        if p.id not in visible and user.role.value != "ADMIN":
            continue
        projects_by_sub.setdefault(p.subsidiary_id, []).append(p.id)

    out: list[dict] = []
    for sub in subs:
        pids = projects_by_sub.get(sub.id, [])
        if not pids:
            out.append({
                "code": sub.code, "name": sub.name, "risk_rating": sub.risk_rating,
                "projects": 0, "datasets": 0, "findings_open": 0,
                "findings_high_critical": 0, "max_risk_score": 0, "test_runs": 0,
            })
            continue
        datasets = db.execute(
            select(func.count()).select_from(Dataset).where(Dataset.project_id.in_(pids))
        ).scalar_one()
        open_findings = db.execute(
            select(func.count()).select_from(Finding).where(
                Finding.project_id.in_(pids),
                Finding.status.in_([FindingStatus.DRAFT, FindingStatus.UNDER_REVIEW,
                                    FindingStatus.CONFIRMED]),
            )
        ).scalar_one()
        hc_findings = db.execute(
            select(func.count()).select_from(Finding).where(
                Finding.project_id.in_(pids),
                Finding.severity.in_(["HIGH", "CRITICAL"]),
                Finding.status.in_([FindingStatus.DRAFT, FindingStatus.UNDER_REVIEW,
                                    FindingStatus.CONFIRMED]),
            )
        ).scalar_one()
        max_score = db.execute(
            select(func.max(RiskScore.score)).select_from(RiskScore)
            .join(Dataset, Dataset.id == RiskScore.dataset_id)
            .where(Dataset.project_id.in_(pids))
        ).scalar_one()
        runs = db.execute(
            select(func.count()).select_from(TestRun)
            .join(Dataset, Dataset.id == TestRun.dataset_id)
            .where(Dataset.project_id.in_(pids))
        ).scalar_one()
        out.append({
            "code": sub.code, "name": sub.name, "risk_rating": sub.risk_rating,
            "country": sub.country, "segment": sub.segment,
            "projects": len(pids), "datasets": datasets, "findings_open": open_findings,
            "findings_high_critical": hc_findings,
            "max_risk_score": float(max_score or 0), "test_runs": runs,
        })
    out.sort(key=lambda r: (-r["findings_high_critical"], -r["max_risk_score"]))
    return out
