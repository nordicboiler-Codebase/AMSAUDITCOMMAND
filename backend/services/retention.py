from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from backend.models import AuditAction, Dataset, EnsembleRun, PackRun, RiskScore, TestRun, User
from backend.services import audit_log, settings_store

CATEGORY = "retention"
KEY = "policy"

DEFAULT_POLICY: dict[str, Any] = {
    "enabled": False,
    "default_days": 2555,
    "per_subledger_days": {},
    "preserve_findings_referenced": True,
}


def get_policy(db: Session) -> dict[str, Any]:
    return settings_store.get_setting(db, CATEGORY, KEY) or dict(DEFAULT_POLICY)


def save_policy(db: Session, *, new_values: dict[str, Any], user_id: uuid.UUID | None) -> dict[str, Any]:
    current = get_policy(db)
    merged = {**current, **new_values}
    allowed = set(DEFAULT_POLICY.keys())
    merged = {k: v for k, v in merged.items() if k in allowed}
    settings_store.upsert_setting(
        db, category=CATEGORY, key=KEY, value=merged, is_secret=False, updated_by=user_id,
    )
    db.commit()
    return merged


def candidates(db: Session, *, as_of: datetime | None = None) -> list[Dataset]:
    policy = get_policy(db)
    if not policy.get("enabled"):
        return []
    as_of = as_of or datetime.now(timezone.utc)
    per_sub: dict[str, int] = policy.get("per_subledger_days") or {}
    default_days = int(policy.get("default_days", 2555))

    rows = list(db.execute(select(Dataset)).scalars())
    stale: list[Dataset] = []
    for ds in rows:
        days = int(per_sub.get(ds.subledger_type.value, default_days))
        if ds.imported_at and ds.imported_at < as_of - timedelta(days=days):
            stale.append(ds)
    return stale


def _delete_parquet(path: str | None) -> None:
    if not path:
        return
    p = Path(path)
    if p.exists() and p.is_file():
        try:
            p.unlink()
        except OSError:
            pass


def purge(
    db: Session, *, user_id: uuid.UUID | None = None, dry_run: bool = True,
    as_of: datetime | None = None,
) -> dict[str, Any]:
    policy = get_policy(db)
    if not policy.get("enabled"):
        return {"enabled": False, "purged_datasets": 0, "dry_run": dry_run}

    preserve_fk = bool(policy.get("preserve_findings_referenced", True))
    stale = candidates(db, as_of=as_of)

    summary: dict[str, Any] = {
        "enabled": True, "dry_run": dry_run,
        "examined": len(stale),
        "purged_datasets": 0,
        "preserved_datasets": 0,
        "details": [],
    }

    for ds in stale:
        if preserve_fk:
            from backend.models import Finding
            has_finding = db.execute(
                select(Finding.id).where(Finding.dataset_id == ds.id).limit(1)
            ).scalar_one_or_none()
            if has_finding:
                summary["preserved_datasets"] += 1
                summary["details"].append({"dataset_id": str(ds.id), "action": "preserved_finding_link"})
                continue

        if dry_run:
            summary["details"].append({
                "dataset_id": str(ds.id), "name": ds.name,
                "imported_at": ds.imported_at.isoformat() if ds.imported_at else None,
                "action": "would_purge",
            })
            continue

        run_ids = [
            rid for (rid,) in db.execute(
                select(TestRun.id).where(TestRun.dataset_id == ds.id)
            ).all()
        ]
        for rid in run_ids:
            run = db.get(TestRun, rid)
            if run and run.output_parquet_path:
                _delete_parquet(run.output_parquet_path)
                scores_path = Path(run.output_parquet_path).with_name(f"run_{rid}_scores.parquet")
                _delete_parquet(str(scores_path))
        _delete_parquet(ds.parquet_path)

        db.execute(delete(RiskScore).where(RiskScore.dataset_id == ds.id))
        db.execute(delete(EnsembleRun).where(EnsembleRun.dataset_id == ds.id))
        db.execute(delete(TestRun).where(TestRun.dataset_id == ds.id))
        db.execute(delete(PackRun).where(PackRun.dataset_id == ds.id))
        db.delete(ds)

        audit_log.log_action(
            db, user_id=user_id, action=AuditAction.EXPORT, entity_type="dataset",
            entity_id=str(ds.id), project_id=ds.project_id,
            details={
                "retention_purge": True, "name": ds.name,
                "imported_at": ds.imported_at.isoformat() if ds.imported_at else None,
                "subledger_type": ds.subledger_type.value,
            },
        )
        summary["purged_datasets"] += 1
        summary["details"].append({"dataset_id": str(ds.id), "name": ds.name, "action": "purged"})

    if not dry_run:
        db.commit()
    return summary
