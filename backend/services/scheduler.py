from __future__ import annotations

import logging
import threading
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.core.db import SessionLocal
from backend.models import (
    AuditAction, Dataset, Finding, FindingSeverity, RiskScore, Schedule, ScheduleKind,
    ScheduleRun, ScheduleStatus, User,
)
from backend.services import audit_log, email as email_svc, ensemble as ens_svc, packs as pack_svc, test_runner

log = logging.getLogger(__name__)


def next_fire_time(cron_expr: str, now: datetime | None = None) -> datetime | None:
    try:
        from croniter import croniter
    except ImportError:
        return None
    base = now or datetime.now(timezone.utc)
    try:
        it = croniter(cron_expr, base)
        return it.get_next(datetime).replace(tzinfo=timezone.utc)
    except Exception as e:
        log.warning("Invalid cron expression %r: %s", cron_expr, e)
        return None


def run_schedule_once(db: Session, schedule: Schedule) -> ScheduleRun:
    sr = ScheduleRun(schedule_id=schedule.id, status="RUNNING")
    db.add(sr)
    db.flush()

    summary: dict[str, Any] = {"kind": schedule.kind.value}
    try:
        if not schedule.dataset_id:
            raise ValueError("Schedule has no dataset_id bound")

        dataset = db.get(Dataset, schedule.dataset_id)
        if not dataset:
            raise ValueError(f"Dataset {schedule.dataset_id} not found")
        user = db.get(User, schedule.created_by) if schedule.created_by else None
        user_id = user.id if user else None

        if schedule.kind == ScheduleKind.PACK:
            if not schedule.pack_code:
                raise ValueError("PACK schedule missing pack_code")
            pack_run = pack_svc.run_pack(
                db, dataset_id=dataset.id, pack_code=schedule.pack_code,
                template_overrides=schedule.param_overrides or {}, user_id=user_id,
            )
            test_run_ids = pack_run.summary.get("test_run_ids", [])
            summary["pack_run_id"] = str(pack_run.id)
            summary["templates_run"] = pack_run.summary.get("templates_run", 0)

            ensemble_id: uuid.UUID | None = None
            max_score = 0.0
            scored = 0
            if schedule.autoensemble and test_run_ids:
                er = ens_svc.compute_ensemble(
                    db, dataset_id=dataset.id,
                    test_run_ids=[uuid.UUID(i) for i in test_run_ids], user_id=user_id,
                )
                ensemble_id = er.id
                summary["ensemble_run_id"] = str(er.id)
                max_score = float(er.summary.get("max_score", 0) or 0)
                scored = int(er.summary.get("records_scored", 0) or 0)
                summary["max_score"] = max_score
                summary["records_scored"] = scored

            if schedule.alert_enabled and schedule.alert_recipients:
                sr.alert_sent, sr.alert_error = _maybe_send_alert(
                    db, schedule=schedule, pack_code=schedule.pack_code,
                    max_score=max_score, records_scored=scored,
                    ensemble_id=ensemble_id,
                )
        else:
            if not schedule.template_code:
                raise ValueError("TEMPLATE schedule missing template_code")
            run = test_runner.run_template(
                db, dataset_id=dataset.id, template_code=schedule.template_code,
                param_overrides=schedule.param_overrides or {}, user_id=user_id,
            )
            summary["test_run_id"] = str(run.id)
            summary["findings"] = run.findings_count

        sr.status = "COMPLETED"
        schedule.last_run_status = "COMPLETED"
    except Exception as e:
        log.exception("Schedule %s failed", schedule.id)
        sr.status = "FAILED"
        summary["error"] = str(e)
        schedule.last_run_status = "FAILED"

    sr.finished_at = datetime.now(timezone.utc)
    sr.summary = summary
    schedule.last_run_at = sr.finished_at
    schedule.last_run_summary = summary
    schedule.next_run_at = next_fire_time(schedule.cron_expr, now=sr.finished_at)

    audit_log.log_action(
        db, user_id=schedule.created_by, action=AuditAction.SCHEDULE_RUN,
        entity_type="schedule", entity_id=str(schedule.id),
        project_id=schedule.project_id,
        details={"status": sr.status, "summary": summary},
    )
    db.commit()
    return sr


def _maybe_send_alert(
    db: Session, *, schedule: Schedule, pack_code: str | None,
    max_score: float, records_scored: int, ensemble_id: uuid.UUID | None,
) -> tuple[bool, str | None]:
    if max_score < schedule.alert_min_score:
        return False, None
    top_rows = []
    if ensemble_id:
        top_rows = list(db.execute(
            select(RiskScore)
            .where(RiskScore.ensemble_run_id == ensemble_id)
            .order_by(RiskScore.score.desc()).limit(10)
        ).scalars())
    body_lines = [
        f"Schedule: {schedule.name}",
        f"Pack: {pack_code or schedule.template_code}",
        f"Records scored: {records_scored}",
        f"Max risk score: {max_score:.1f} (alert threshold {schedule.alert_min_score:.0f})",
        "",
        "Top 10 records:",
    ]
    for r in top_rows:
        detectors = sorted({c.get("detector_name", "") for c in (r.contributing_detectors or [])})
        body_lines.append(f"  - {r.record_key}: score={r.score:.1f} detectors={detectors}")
    body = "\n".join(body_lines)
    try:
        email_svc.send_message(
            db,
            to=schedule.alert_recipients,
            subject=f"[Audit Alert] {schedule.name} — max score {max_score:.1f}",
            body_text=body,
        )
        audit_log.log_action(
            db, user_id=schedule.created_by, action=AuditAction.ALERT_SENT,
            entity_type="schedule", entity_id=str(schedule.id),
            project_id=schedule.project_id,
            details={"recipients": schedule.alert_recipients, "max_score": max_score},
        )
        return True, None
    except Exception as e:
        log.exception("Alert email failed for schedule %s", schedule.id)
        return False, str(e)


_started = False
_lock = threading.Lock()


def start(poll_seconds: int = 30) -> None:
    global _started
    with _lock:
        if _started:
            return
        try:
            from apscheduler.schedulers.background import BackgroundScheduler
        except ImportError:
            log.warning("APScheduler not installed; scheduler disabled")
            return
        sched = BackgroundScheduler(timezone="UTC")
        sched.add_job(_tick, "interval", seconds=poll_seconds, id="tick", replace_existing=True)
        sched.start()
        _started = True
        log.info("Scheduler started (poll every %ss)", poll_seconds)


_TICK_LOCK_KEY = 91347294837  # arbitrary stable int used by Postgres advisory lock


def _tick() -> None:
    from sqlalchemy import text

    db = SessionLocal()
    try:
        # Postgres advisory lock: only one worker runs the tick at a time across
        # all uvicorn workers / all processes sharing this DB. Non-blocking:
        # if another worker holds the lock, we skip this cycle.
        try:
            acquired = db.execute(
                text("SELECT pg_try_advisory_lock(:k)"), {"k": _TICK_LOCK_KEY}
            ).scalar()
        except Exception:
            acquired = True  # non-Postgres DB (sqlite test) — just proceed
        if not acquired:
            return
        try:
            now = datetime.now(timezone.utc)
            due = list(db.execute(
                select(Schedule).where(
                    Schedule.status == ScheduleStatus.ACTIVE,
                    Schedule.next_run_at.is_not(None),
                    Schedule.next_run_at <= now,
                )
            ).scalars())
            for schedule in due:
                try:
                    run_schedule_once(db, schedule)
                except Exception:
                    log.exception("Schedule %s tick failed", schedule.id)
        finally:
            try:
                db.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": _TICK_LOCK_KEY})
                db.commit()
            except Exception:
                pass
    finally:
        db.close()


def preview_next_fire(cron_expr: str, count: int = 5) -> list[str]:
    try:
        from croniter import croniter
    except ImportError:
        return []
    base = datetime.now(timezone.utc)
    try:
        it = croniter(cron_expr, base)
        return [it.get_next(datetime).replace(tzinfo=timezone.utc).isoformat() for _ in range(count)]
    except Exception:
        return []
