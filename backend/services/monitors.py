from __future__ import annotations

import logging
import uuid
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.models import (
    AuditAction, Dataset, Finding, FindingSeverity, FindingStatus, Monitor, RiskScore, User,
)
from backend.services import acl, audit_log, email as email_svc, ensemble as ens_svc, packs as pack_svc

log = logging.getLogger(__name__)


def list_monitors(db: Session, *, user: User, project_id: uuid.UUID | None = None) -> list[Monitor]:
    q = select(Monitor)
    if project_id is not None:
        acl.assert_permission(db, project_id=project_id, user=user, permission=acl.Permission.VIEW)
        q = q.where(Monitor.project_id == project_id)
    else:
        visible = acl.visible_project_ids(db, user=user)
        if not visible:
            return []
        q = q.where(Monitor.project_id.in_(visible))
    q = q.order_by(Monitor.name.asc())
    return list(db.execute(q).scalars())


def create_monitor(
    db: Session, *, project_id: uuid.UUID, name: str, subledger_type: str,
    pack_code: str, auto_ensemble: bool, auto_create_finding_min_score: float,
    alert_recipients: list[str], user: User,
) -> Monitor:
    acl.assert_permission(db, project_id=project_id, user=user, permission=acl.Permission.EDIT)
    m = Monitor(
        project_id=project_id, name=name, subledger_type=subledger_type,
        pack_code=pack_code, auto_ensemble=auto_ensemble,
        auto_create_finding_min_score=auto_create_finding_min_score,
        alert_recipients=alert_recipients, created_by=user.id,
    )
    db.add(m)
    db.commit()
    return m


def trigger_on_import(db: Session, *, dataset: Dataset, user_id: uuid.UUID | None) -> list[dict]:
    """Called after a dataset import completes. Fires any enabled monitors that match."""
    matches = list(db.execute(
        select(Monitor).where(
            Monitor.enabled.is_(True),
            Monitor.project_id == dataset.project_id,
            Monitor.subledger_type == dataset.subledger_type.value,
        )
    ).scalars())
    results: list[dict] = []
    for monitor in matches:
        try:
            summary = _fire_monitor(db, monitor=monitor, dataset=dataset, user_id=user_id)
            results.append(summary)
        except Exception as e:
            log.exception("Monitor %s failed for dataset %s", monitor.id, dataset.id)
            results.append({"monitor_id": str(monitor.id), "error": str(e)})
    return results


def _fire_monitor(db: Session, *, monitor: Monitor, dataset: Dataset,
                  user_id: uuid.UUID | None) -> dict[str, Any]:
    pack_run = pack_svc.run_pack(
        db, dataset_id=dataset.id, pack_code=monitor.pack_code,
        template_overrides={}, user_id=user_id,
    )
    summary: dict[str, Any] = {
        "monitor_id": str(monitor.id), "monitor_name": monitor.name,
        "pack_run_id": str(pack_run.id),
        "templates_run": pack_run.summary.get("templates_run", 0),
    }

    high_risk_records: list[dict] = []
    if monitor.auto_ensemble:
        test_run_ids = pack_run.summary.get("test_run_ids", [])
        er = ens_svc.compute_ensemble(
            db, dataset_id=dataset.id,
            test_run_ids=[uuid.UUID(i) for i in test_run_ids], user_id=user_id,
        )
        summary["ensemble_run_id"] = str(er.id)
        summary["records_scored"] = int(er.summary.get("records_scored", 0) or 0)
        summary["max_score"] = float(er.summary.get("max_score", 0) or 0)

        high_risk = list(db.execute(
            select(RiskScore).where(
                RiskScore.ensemble_run_id == er.id,
                RiskScore.score >= monitor.auto_create_finding_min_score,
            ).order_by(RiskScore.score.desc()).limit(5)
        ).scalars())
        for r in high_risk:
            finding = Finding(
                code=_auto_finding_code(db),
                title=f"[AUTO] Monitor {monitor.name}: record {r.record_key} scored {r.score:.1f}",
                description=f"Auto-created by continuous monitor {monitor.name} after dataset import.",
                project_id=monitor.project_id,
                dataset_id=dataset.id,
                ensemble_run_id=er.id,
                record_keys=[r.record_key],
                risk_score=r.score,
                severity=(FindingSeverity.CRITICAL if r.score >= 95 else FindingSeverity.HIGH),
                status=FindingStatus.DRAFT,
                owner_id=user_id,
                created_by=user_id,
                tags=["auto", "monitor"],
            )
            db.add(finding)
            high_risk_records.append({"record_key": r.record_key, "score": r.score})
        summary["auto_findings_created"] = len(high_risk_records)

    monitor.last_triggered_at = datetime.now(timezone.utc)
    monitor.last_dataset_id = dataset.id
    audit_log.log_action(
        db, user_id=user_id, action=AuditAction.MONITOR_TRIGGERED, entity_type="monitor",
        entity_id=str(monitor.id), project_id=monitor.project_id,
        details={"dataset_id": str(dataset.id), "summary": summary},
    )
    db.commit()

    if monitor.alert_recipients and summary.get("max_score", 0) >= monitor.auto_create_finding_min_score:
        try:
            _send_alert(db, monitor=monitor, dataset=dataset, summary=summary,
                        high_risk=high_risk_records)
            summary["alert_sent"] = True
        except Exception as e:
            summary["alert_error"] = str(e)

    return summary


def _auto_finding_code(db: Session) -> str:
    year = date.today().year
    prefix = f"AUTO-{year}-"
    n = db.execute(
        select(func.count()).select_from(Finding).where(Finding.code.like(f"{prefix}%"))
    ).scalar_one()
    return f"{prefix}{n + 1:05d}"


def _send_alert(db: Session, *, monitor: Monitor, dataset: Dataset,
                summary: dict, high_risk: list[dict]) -> None:
    lines = [
        f"Monitor: {monitor.name}",
        f"Project: {monitor.project_id}",
        f"Dataset: {dataset.name} ({dataset.record_count} records)",
        f"Pack: {monitor.pack_code}",
        f"Max risk score: {summary.get('max_score', 0):.1f}",
        f"Auto-findings created: {summary.get('auto_findings_created', 0)}",
        "",
        "Top records (≥ threshold):",
    ]
    for r in high_risk:
        lines.append(f"  - {r['record_key']}: score={r['score']:.1f}")
    email_svc.send_message(
        db, to=monitor.alert_recipients,
        subject=f"[Audit Monitor] {monitor.name} — new dataset flagged",
        body_text="\n".join(lines),
    )
