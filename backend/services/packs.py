from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models import AuditAction, Dataset, Pack, PackRun
from backend.models.enums import RunStatus
from backend.services import audit_log, test_runner


class PackError(Exception):
    pass


def list_packs(db: Session, subledger=None) -> list[Pack]:
    q = select(Pack)
    if subledger is not None:
        q = q.where((Pack.subledger_type == subledger) | (Pack.subledger_type.is_(None)))
    return list(db.execute(q.order_by(Pack.code)).scalars())


def get_pack(db: Session, code: str) -> Pack:
    pack = db.execute(select(Pack).where(Pack.code == code)).scalars().first()
    if not pack:
        raise PackError(f"Pack not found: {code}")
    return pack


def run_pack(
    db: Session,
    *,
    dataset_id: uuid.UUID,
    pack_code: str,
    template_overrides: dict[str, dict] | None = None,
    user_id: uuid.UUID,
) -> PackRun:
    pack = get_pack(db, pack_code)
    dataset = db.get(Dataset, dataset_id)
    if not dataset:
        raise PackError(f"Dataset not found: {dataset_id}")

    pack_run = PackRun(
        dataset_id=dataset_id,
        pack_code=pack_code,
        run_by=user_id,
        status=RunStatus.RUNNING,
        template_overrides=template_overrides or {},
    )
    db.add(pack_run)
    db.flush()

    results: list[dict] = []
    test_run_ids: list[str] = []
    for code in pack.template_codes or []:
        overrides = (template_overrides or {}).get(code, {})
        try:
            run = test_runner.run_template(
                db,
                dataset_id=dataset_id,
                template_code=code,
                param_overrides=overrides,
                user_id=user_id,
                pack_run_id=pack_run.id,
            )
            results.append({
                "template_code": code,
                "test_run_id": str(run.id),
                "findings": run.findings_count,
                "status": run.status.value,
            })
            test_run_ids.append(str(run.id))
        except Exception as e:
            results.append({"template_code": code, "error": str(e), "status": "FAILED"})

    pack_run.status = RunStatus.COMPLETED
    pack_run.finished_at = datetime.now(timezone.utc)
    pack_run.summary = {"templates_run": len(results), "test_run_ids": test_run_ids, "results": results}

    audit_log.log_action(
        db, user_id=user_id, action=AuditAction.PACK_RUN, entity_type="pack_run",
        entity_id=str(pack_run.id), project_id=dataset.project_id,
        details={"pack_code": pack_code, "templates_run": len(results)},
    )
    db.commit()
    return pack_run
