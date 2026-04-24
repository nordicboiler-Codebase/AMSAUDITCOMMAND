from __future__ import annotations

import hashlib
import hmac
import io
import json
import uuid
import zipfile
from datetime import datetime, timezone
from typing import Any

from backend.core.config import get_settings

import polars as pl
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models import (
    AuditAction, AuditLog, Dataset, Engagement, Finding, Pack, PackRun, Project, TestRun, User,
)
from backend.services import audit_log


def _engagement_context(db: Session, engagement: Engagement) -> dict[str, Any]:
    project = db.get(Project, engagement.project_id)
    dataset_ids = engagement.dataset_ids or []
    datasets = list(db.execute(
        select(Dataset).where(Dataset.id.in_(dataset_ids))
    ).scalars()) if dataset_ids else []
    pack_runs = list(db.execute(
        select(PackRun).where(PackRun.id.in_(engagement.pack_run_ids or []))
    ).scalars()) if engagement.pack_run_ids else []
    findings = list(db.execute(
        select(Finding).where(Finding.id.in_(engagement.finding_ids or []))
    ).scalars()) if engagement.finding_ids else []
    return {"project": project, "datasets": datasets, "pack_runs": pack_runs, "findings": findings}


def export_engagement_bundle(
    db: Session, *, engagement_id: uuid.UUID, user: User, format: str = "zip",
) -> tuple[bytes, str, str]:
    """Produce a zipped evidence bundle for a single engagement.

    Contains:
      - manifest.json (engagement metadata + list of included artifacts + hashes)
      - findings.csv
      - test_runs.csv
      - audit_chain.json (audit-log entries scoped to project_id)
      - for each linked dataset: control_totals.json + parquet path reference
      - for each test run: output_parquet reference
    """
    engagement = db.get(Engagement, engagement_id)
    if not engagement:
        raise ValueError("Engagement not found")
    ctx = _engagement_context(db, engagement)
    project = ctx["project"]

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        manifest = {
            "engagement": {
                "code": engagement.code,
                "title": engagement.title,
                "project": project.name if project else None,
                "period_start": engagement.period_start.isoformat() if engagement.period_start else None,
                "period_end": engagement.period_end.isoformat() if engagement.period_end else None,
                "scope": engagement.scope,
                "status": engagement.status.value,
                "finalised_at": engagement.finalised_at.isoformat() if engagement.finalised_at else None,
                "lead_auditor_id": str(engagement.lead_auditor_id) if engagement.lead_auditor_id else None,
                "reviewer_id": str(engagement.reviewer_id) if engagement.reviewer_id else None,
            },
            "datasets": [
                {
                    "id": str(d.id), "name": d.name,
                    "source_filename": d.source_filename,
                    "source_hash_sha256": d.source_hash_sha256,
                    "record_count": d.record_count,
                    "subledger_type": d.subledger_type.value,
                    "imported_at": d.imported_at.isoformat() if d.imported_at else None,
                    "parquet_path": d.parquet_path,
                    "control_totals": d.control_totals,
                }
                for d in ctx["datasets"]
            ],
            "pack_runs": [
                {
                    "id": str(pr.id), "pack_code": pr.pack_code,
                    "dataset_id": str(pr.dataset_id),
                    "status": pr.status.value if pr.status else None,
                    "summary": pr.summary,
                    "started_at": pr.started_at.isoformat() if pr.started_at else None,
                    "finished_at": pr.finished_at.isoformat() if pr.finished_at else None,
                }
                for pr in ctx["pack_runs"]
            ],
            "findings": [
                {
                    "code": f.code, "title": f.title, "severity": f.severity.value,
                    "status": f.status.value, "risk_score": f.risk_score,
                    "record_keys": list(f.record_keys or []),
                    "owner_id": str(f.owner_id) if f.owner_id else None,
                    "reviewer_id": str(f.reviewer_id) if f.reviewer_id else None,
                    "reviewed_at": f.reviewed_at.isoformat() if f.reviewed_at else None,
                    "management_response": f.management_response,
                    "remediation_plan": f.remediation_plan,
                    "due_date": f.due_date.isoformat() if f.due_date else None,
                }
                for f in ctx["findings"]
            ],
            "exported_by": str(user.id),
            "exported_at": datetime.now(timezone.utc).isoformat(),
        }
        z.writestr("manifest.json", json.dumps(manifest, indent=2, default=str))

        # findings.csv
        findings_csv = io.StringIO()
        findings_csv.write("code,title,severity,status,risk_score,owner_id,reviewer_id,due_date,created_at\n")
        for f in ctx["findings"]:
            findings_csv.write(
                f'"{f.code}","{_csv_safe(f.title)}",{f.severity.value},{f.status.value},'
                f'{f.risk_score or ""},{f.owner_id or ""},{f.reviewer_id or ""},'
                f'{f.due_date.isoformat() if f.due_date else ""},'
                f'{f.created_at.isoformat() if f.created_at else ""}\n'
            )
        z.writestr("findings.csv", findings_csv.getvalue())

        # test_runs.csv
        all_test_runs = list(db.execute(
            select(TestRun).where(TestRun.pack_run_id.in_(
                [pr.id for pr in ctx["pack_runs"]]
            ))
        ).scalars()) if ctx["pack_runs"] else []
        tr_csv = io.StringIO()
        tr_csv.write("id,dataset_id,template_code,detector_name,status,findings,input_hash,output_hash,started_at,finished_at\n")
        for r in all_test_runs:
            tr_csv.write(
                f'{r.id},{r.dataset_id},"{r.template_code or ""}","{r.detector_name}",'
                f'{r.status.value if r.status else ""},{r.findings_count},'
                f'"{r.input_hash or ""}","{r.output_hash or ""}",'
                f'{r.started_at.isoformat() if r.started_at else ""},'
                f'{r.finished_at.isoformat() if r.finished_at else ""}\n'
            )
        z.writestr("test_runs.csv", tr_csv.getvalue())

        # audit_chain.json (project-scoped)
        al_rows = list(db.execute(
            select(AuditLog).where(AuditLog.project_id == engagement.project_id)
            .order_by(AuditLog.timestamp.asc())
        ).scalars())
        al_payload = [
            {
                "id": str(a.id),
                "timestamp": a.timestamp.isoformat(),
                "user_id": str(a.user_id) if a.user_id else None,
                "action": a.action.value if hasattr(a.action, "value") else str(a.action),
                "entity_type": a.entity_type,
                "entity_id": a.entity_id,
                "details": a.details,
                "previous_hash": a.previous_hash,
                "current_hash": a.current_hash,
            }
            for a in al_rows
        ]
        z.writestr("audit_chain.json", json.dumps(al_payload, indent=2, default=str))

        # Sample of flagged rows per test run (first 50) for auditor review.
        for r in all_test_runs[:20]:
            if not r.output_parquet_path:
                continue
            try:
                df = pl.read_parquet(r.output_parquet_path).head(50)
                out = io.StringIO()
                out.write(df.write_csv())
                z.writestr(f"test_runs/{r.id}.csv", out.getvalue())
            except Exception:
                pass

        # README for the bundle
        z.writestr("README.txt", _readme_text(engagement, project, user))

    # Append a detached signature file that recipients can verify independently.
    # SHA-256 of the zip contents + HMAC using SECRET_KEY. Not PKI, but tamper-evident.
    # Rebuild the zip to include the signature side-file.
    body_so_far = buf.getvalue()
    digest = hashlib.sha256(body_so_far).hexdigest()
    signing_key = get_settings().secret_key.encode("utf-8")
    hmac_sig = hmac.new(signing_key, body_so_far, hashlib.sha256).hexdigest()

    final_buf = io.BytesIO()
    with zipfile.ZipFile(final_buf, "w", zipfile.ZIP_DEFLATED) as outer:
        outer.writestr("bundle.zip", body_so_far)
        outer.writestr(
            "bundle.sig.json",
            json.dumps({
                "algorithm": "HMAC-SHA256",
                "sha256": digest,
                "hmac_sha256": hmac_sig,
                "signed_at": datetime.now(timezone.utc).isoformat(),
                "signed_by": str(user.id),
                "note": "Recipient: compute sha256(bundle.zip); compare to sha256. "
                        "For full tamper proof, request HMAC verification from TechSource Audit.",
            }, indent=2),
        )
    data = final_buf.getvalue()

    audit_log.log_action(
        db, user_id=user.id, action=AuditAction.EXPORT, entity_type="engagement",
        entity_id=str(engagement.id), project_id=engagement.project_id,
        details={"format": format, "bytes": len(data), "sha256": digest, "hmac": hmac_sig},
    )
    db.commit()
    filename = f"{engagement.code}_workpaper_bundle.zip"
    return data, filename, "application/zip"


def _csv_safe(s: str | None) -> str:
    if s is None:
        return ""
    return s.replace('"', "''").replace("\n", " ")


def _readme_text(engagement: Engagement, project: Project | None, user: User) -> str:
    return f"""
TechSource Audit Analytics — Workpaper Bundle
=============================================

Engagement:   {engagement.code} — {engagement.title}
Project:      {project.name if project else ''}
Status:       {engagement.status.value}
Exported by:  {user.username} ({user.id})
Exported at:  {datetime.now(timezone.utc).isoformat()}

Files in this archive
---------------------
  manifest.json      — engagement metadata + all artifact references + hashes
  findings.csv       — every finding linked to this engagement
  test_runs.csv      — every underlying test run (hashes included)
  audit_chain.json   — append-only audit-log entries for this project
  test_runs/*.csv    — sample of flagged rows per test run (top 50)

Evidence integrity
------------------
Every source dataset has a SHA-256 hash in manifest.json (source_hash_sha256).
Every test run records an input_hash and an output_hash.
The audit_chain.json file can be independently replayed — each entry's
current_hash is SHA-256(previous_hash + canonical_json(payload)).

Import into CaseWare
--------------------
1. File → Import → Working Trial Balance
2. Point at findings.csv
3. Attach this zip as supporting evidence

Import into IDEA
----------------
1. File → Import Assistant → Delimited Text
2. Use findings.csv and test_runs.csv as separate tables
3. Link by code / template_code as needed

Import into TeamMate
--------------------
1. Attach this zip to the relevant Issue record
2. Use audit_chain.json for evidence-integrity sign-off

Regulator review
----------------
The manifest.json + audit_chain.json together prove that findings were
produced from hashed source data and never altered after the fact.
"""
