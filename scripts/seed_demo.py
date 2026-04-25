"""Full demo seed — populates a multi-subsidiary group audit scenario.

Idempotent: running twice does nothing harmful (skips existing entities).

Creates:
  - 4 subsidiaries (DI-100..DI-103)
  - 4 projects (one per subsidiary, mixed subledgers)
  - Imports 6 sample datasets across them
  - Runs the matching standard packs
  - Computes ensembles
  - Creates ~12 findings in mixed statuses (DRAFT / UNDER_REVIEW / CONFIRMED / REMEDIATED / FALSE_POSITIVE)
  - Creates an engagement linking artifacts in the AP project
  - Registers a monitor on AP_STANDARD for the AP project
  - Registers a monthly schedule for the GL project
"""
from __future__ import annotations

import logging
import random
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import select

from backend.core.db import SessionLocal
from backend.models import (
    Engagement, EngagementStatus, Finding, FindingSeverity, FindingStatus, Monitor,
    Project, ProjectMember, ProjectRole, RiskScore, Schedule, ScheduleKind,
    ScheduleStatus, Subsidiary, SubledgerType, User,
)
from backend.services import ensemble as ens_svc, import_service, packs as pack_svc

logging.getLogger().setLevel(logging.INFO)
log = logging.getLogger("seed_demo")

SAMPLES_DIR = Path(__file__).resolve().parent.parent / "samples"

SUBSIDIARIES = [
    {"code": "DI-100", "name": "DI Holdings PJSC", "country": "ARE",
     "industry": "Holdings", "segment": "Diversified", "risk_rating": "MEDIUM"},
    {"code": "DI-101", "name": "DI Real Estate", "country": "ARE",
     "industry": "Real Estate", "segment": "Property", "risk_rating": "HIGH"},
    {"code": "DI-102", "name": "DI Manufacturing", "country": "ARE",
     "industry": "Manufacturing", "segment": "Industrial", "risk_rating": "MEDIUM"},
    {"code": "DI-103", "name": "DI Education", "country": "ARE",
     "industry": "Education", "segment": "Services", "risk_rating": "LOW"},
]

PROJECTS = [
    ("Q1 2026 AP Audit — DI Holdings", "DI-100", "ACCOUNTS_PAYABLE",
     "accounts_payable_sample.csv", "AP_STANDARD"),
    ("Q1 2026 GL Review — DI Holdings", "DI-100", "GENERAL_LEDGER",
     "general_ledger_sample.csv", "GL_STANDARD"),
    ("Q1 2026 Payroll — DI Real Estate", "DI-101", "PAYROLL",
     "payroll_sample.csv", "PAYROLL_STANDARD"),
    ("Q1 2026 Inventory — DI Manufacturing", "DI-102", "INVENTORY",
     "inventory_sample.csv", "INVENTORY_STANDARD"),
    ("Q1 2026 AR — DI Education", "DI-103", "ACCOUNTS_RECEIVABLE",
     "accounts_receivable_sample.csv", "AR_STANDARD"),
    ("Q1 2026 Bank Recon — DI Holdings", "DI-100", "BANK",
     "bank_sample.csv", "BANK_RECON"),
]


def _ensure_admin(db) -> User:
    admin = db.execute(select(User).where(User.username == "admin")).scalar_one_or_none()
    if not admin:
        from backend.core.security import hash_password
        from backend.models.enums import UserRole

        admin = User(username="admin", email="admin@test.local",
                     password_hash=hash_password("admin123"), role=UserRole.ADMIN)
        db.add(admin)
        db.commit()
    return admin


def _ensure_subsidiaries(db) -> dict[str, Subsidiary]:
    out: dict[str, Subsidiary] = {}
    for spec in SUBSIDIARIES:
        existing = db.execute(
            select(Subsidiary).where(Subsidiary.code == spec["code"])
        ).scalar_one_or_none()
        if existing:
            out[spec["code"]] = existing
            continue
        s = Subsidiary(**spec, is_active=True)
        db.add(s)
        log.info("subsidiary created: %s", spec["code"])
        out[spec["code"]] = s
    db.commit()
    return out


def _ensure_project(db, *, name: str, subsidiary_code: str, owner: User) -> Project:
    existing = db.execute(select(Project).where(Project.name == name)).scalar_one_or_none()
    if existing:
        return existing
    p = Project(name=name, description=f"Auto-seeded demo project for {subsidiary_code}",
                subsidiary_code=subsidiary_code, owner_id=owner.id)
    db.add(p)
    db.flush()
    db.add(ProjectMember(project_id=p.id, user_id=owner.id,
                         project_role=ProjectRole.OWNER, added_by=owner.id))
    db.commit()
    log.info("project created: %s (%s)", name, subsidiary_code)
    return p


def _import_dataset(db, *, project: Project, sample_filename: str,
                    subledger: str, owner: User) -> "tuple":
    name = f"{sample_filename.removesuffix('_sample.csv').upper()} demo — {project.subsidiary_code}"
    from backend.models import Dataset
    existing = db.execute(
        select(Dataset).where(Dataset.project_id == project.id, Dataset.name == name)
    ).scalar_one_or_none()
    if existing:
        return existing, False
    src = SAMPLES_DIR / sample_filename
    if not src.exists():
        raise FileNotFoundError(f"Sample missing: {src}")
    result = import_service.import_dataset(
        db, file_path=src, source_filename=sample_filename,
        project_id=project.id, name=name,
        subledger_type=SubledgerType(subledger), user_id=owner.id,
        description=f"Auto-imported demo sample {sample_filename}",
    )
    log.info("imported %s (%s rows)", name, result.record_count)
    ds = db.get(Dataset, result.dataset_id)
    return ds, True


def _run_pack_and_ensemble(db, *, dataset, pack_code: str, owner: User) -> "tuple":
    from backend.models import EnsembleRun
    pr = pack_svc.run_pack(db, dataset_id=dataset.id, pack_code=pack_code,
                           template_overrides={}, user_id=owner.id)
    test_run_ids = [uuid.UUID(i) for i in (pr.summary.get("test_run_ids") or [])]
    if not test_run_ids:
        return pr, None
    er = ens_svc.compute_ensemble(db, dataset_id=dataset.id,
                                  test_run_ids=test_run_ids, user_id=owner.id)
    log.info("pack %s: %s templates, ensemble max=%.1f mean=%.1f",
             pack_code, pr.summary.get("templates_run", 0),
             er.summary.get("max_score") or 0, er.summary.get("mean_score") or 0)
    return pr, er


def _create_findings(db, *, project: Project, dataset, ensemble_run, owner: User) -> int:
    """Create a mix of finding statuses for visual variety on the demo dashboard."""
    if ensemble_run is None:
        return 0
    top = list(db.execute(
        select(RiskScore).where(RiskScore.ensemble_run_id == ensemble_run.id)
        .order_by(RiskScore.score.desc()).limit(15)
    ).scalars())
    if not top:
        return 0

    # Cycle through statuses for demo variety. CONFIRMED / FALSE_POSITIVE / REMEDIATED
    # in the seed bypass the maker-checker rule (we set reviewer_id != owner_id).
    rng = random.Random(hash(project.id) & 0xFFFF)
    pattern = [
        FindingStatus.DRAFT, FindingStatus.UNDER_REVIEW, FindingStatus.CONFIRMED,
        FindingStatus.REMEDIATED, FindingStatus.FALSE_POSITIVE, FindingStatus.DRAFT,
    ]
    year = date.today().year
    base_n = db.execute(
        select(Finding).where(Finding.code.like(f"F-{year}-%"))
    ).scalars().all()
    code_counter = len(base_n)

    created = 0
    for i, r in enumerate(top[:6]):
        sev = (FindingSeverity.CRITICAL if r.score >= 90 else
               FindingSeverity.HIGH if r.score >= 70 else
               FindingSeverity.MEDIUM if r.score >= 40 else FindingSeverity.LOW)
        status = pattern[i % len(pattern)]
        detector_names = sorted({c.get("detector_name", "") for c in r.contributing_detectors or []})
        code_counter += 1
        f = Finding(
            code=f"F-{year}-{code_counter:05d}",
            title=f"{sev.value} on {r.record_key} — {detector_names[0] if detector_names else 'risk'}",
            description=(f"Auto-flagged by detectors: {', '.join(detector_names) or '—'}.\n"
                         f"Score {r.score:.1f}."),
            project_id=project.id,
            dataset_id=dataset.id,
            ensemble_run_id=ensemble_run.id,
            record_keys=[r.record_key],
            risk_score=r.score,
            severity=sev,
            status=status,
            owner_id=owner.id,
            created_by=owner.id,
            tags=["demo", "auto-seed"],
            management_response=("Investigated and remediated by 31-Mar." if status == FindingStatus.REMEDIATED else None),
            remediation_plan=("Vendor invoice voided; system control updated."
                              if status == FindingStatus.REMEDIATED else None),
        )
        # Closed states need a closed_at + reviewer
        if status in {FindingStatus.REMEDIATED, FindingStatus.FALSE_POSITIVE}:
            f.reviewer_id = owner.id  # demo bypass — UI enforces creator≠reviewer
            f.reviewed_at = datetime.now(timezone.utc)
            if status == FindingStatus.REMEDIATED:
                f.closed_at = datetime.now(timezone.utc)
        db.add(f)
        created += 1
    db.commit()
    log.info("created %d findings for project %s", created, project.name)
    return created


def _ensure_engagement(db, *, project: Project, datasets, owner: User) -> Engagement:
    code = f"E-{date.today().year}-9{int(project.id.int) % 10000:04d}"
    existing = db.execute(select(Engagement).where(Engagement.code == code)).scalar_one_or_none()
    if existing:
        return existing
    findings = list(db.execute(
        select(Finding).where(Finding.project_id == project.id).limit(6)
    ).scalars())
    e = Engagement(
        code=code,
        title=f"Q1 2026 Audit — {project.subsidiary_code}",
        project_id=project.id,
        period_start=date(2026, 1, 1),
        period_end=date(2026, 3, 31),
        scope=("Q1 2026 transactional audit across "
               f"{', '.join(d.subledger_type.value for d in datasets)}."),
        status=EngagementStatus.IN_PROGRESS,
        lead_auditor_id=owner.id,
        dataset_ids=[d.id for d in datasets],
        finding_ids=[f.id for f in findings],
        executive_summary=(f"{len(findings)} findings raised across {len(datasets)} datasets. "
                          "High-risk patterns include weekend payments, threshold avoidance, "
                          "and vendor-employee bank account matches."),
        created_by=owner.id,
    )
    db.add(e)
    db.commit()
    log.info("engagement created: %s", code)
    return e


def _ensure_monitor(db, *, project: Project, owner: User) -> None:
    name = f"AP auto-screen — {project.subsidiary_code}"
    existing = db.execute(
        select(Monitor).where(Monitor.project_id == project.id, Monitor.name == name)
    ).scalar_one_or_none()
    if existing:
        return
    m = Monitor(project_id=project.id, name=name,
                subledger_type="ACCOUNTS_PAYABLE", pack_code="AP_STANDARD",
                auto_ensemble=True, auto_create_finding_min_score=85.0,
                alert_recipients=["audit-alerts@example.com"], enabled=True,
                created_by=owner.id)
    db.add(m)
    db.commit()
    log.info("monitor created: %s", name)


def _ensure_schedule(db, *, project: Project, dataset, owner: User) -> None:
    name = f"Monthly GL pack — {project.subsidiary_code}"
    existing = db.execute(
        select(Schedule).where(Schedule.project_id == project.id, Schedule.name == name)
    ).scalar_one_or_none()
    if existing:
        return
    from backend.services import scheduler as sched_svc
    next_fire = sched_svc.next_fire_time("0 2 1 * *")
    s = Schedule(
        project_id=project.id, dataset_id=dataset.id, name=name,
        kind=ScheduleKind.PACK, pack_code="GL_STANDARD",
        cron_expr="0 2 1 * *", timezone="UTC", status=ScheduleStatus.ACTIVE,
        autoensemble=True, alert_enabled=True, alert_min_score=80.0,
        alert_recipients=["audit-alerts@example.com"],
        next_run_at=next_fire, created_by=owner.id,
    )
    db.add(s)
    db.commit()
    log.info("schedule created: %s (next %s)", name, next_fire)


def main() -> None:
    db = SessionLocal()
    try:
        admin = _ensure_admin(db)
        _ensure_subsidiaries(db)

        project_to_datasets: dict[str, list] = {}
        for proj_name, sub_code, subledger, sample, pack_code in PROJECTS:
            project = _ensure_project(db, name=proj_name, subsidiary_code=sub_code, owner=admin)
            ds, fresh = _import_dataset(db, project=project, sample_filename=sample,
                                        subledger=subledger, owner=admin)
            project_to_datasets.setdefault(project.id, []).append(ds)
            if fresh:
                pr, er = _run_pack_and_ensemble(db, dataset=ds, pack_code=pack_code, owner=admin)
                if er is not None:
                    _create_findings(db, project=project, dataset=ds,
                                     ensemble_run=er, owner=admin)

        # Engagement on first project (AP)
        for proj in db.execute(select(Project).where(Project.name == PROJECTS[0][0])).scalars():
            _ensure_engagement(db, project=proj,
                               datasets=project_to_datasets.get(proj.id, []), owner=admin)
            _ensure_monitor(db, project=proj, owner=admin)
        # Schedule on the GL project
        for proj in db.execute(select(Project).where(Project.name == PROJECTS[1][0])).scalars():
            ds = project_to_datasets.get(proj.id, [])
            if ds:
                _ensure_schedule(db, project=proj, dataset=ds[0], owner=admin)

        log.info("Demo seed complete.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
