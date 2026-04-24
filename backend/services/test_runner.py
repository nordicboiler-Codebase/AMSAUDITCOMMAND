from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import polars as pl
from sqlalchemy.orm import Session

from backend.core.config import get_settings
from backend.detectors import catalog as det_catalog
from backend.detectors.base import hash_dataframe
from backend.models import AuditAction, Dataset, TestRun
from backend.models.enums import RunStatus
from backend.services import audit_log
from backend.templates import catalog as tpl_catalog

settings = get_settings()


def run_detector(
    db: Session,
    *,
    dataset_id: uuid.UUID,
    detector_name: str,
    params: dict[str, Any],
    user_id: uuid.UUID,
    template_code: str | None = None,
    pack_run_id: uuid.UUID | None = None,
) -> TestRun:
    det_catalog.load_all()
    dataset = db.get(Dataset, dataset_id)
    if not dataset:
        raise ValueError(f"Dataset not found: {dataset_id}")
    detector = det_catalog.get(detector_name)

    df = pl.read_parquet(dataset.parquet_path)
    input_hash = hash_dataframe(df)

    # Integrity check: the Parquet we ingest must still match the manifest hash
    # captured at import time (control totals include it). If source_hash_sha256 is
    # present, ensure the current parquet file still produces a consistent fingerprint.
    # We don't re-hash the raw upload (only dataset.source_hash_sha256 captures that);
    # instead we ensure the parquet row count matches what we stored on import.
    if dataset.record_count and df.height != dataset.record_count:
        raise RuntimeError(
            f"Dataset integrity check failed: parquet has {df.height} rows but "
            f"import recorded {dataset.record_count}. Possible tampering — refusing to run."
        )

    run = TestRun(
        dataset_id=dataset_id,
        template_code=template_code,
        detector_name=detector_name,
        params=params,
        run_by=user_id,
        status=RunStatus.RUNNING,
        started_at=datetime.now(timezone.utc),
        input_hash=input_hash,
        pack_run_id=pack_run_id,
    )
    db.add(run)
    db.flush()

    try:
        merged = {**(detector.default_params or {}), **params}
        result = detector.run(df, merged)
    except Exception as e:
        run.status = RunStatus.FAILED
        run.error_message = str(e)
        run.finished_at = datetime.now(timezone.utc)
        db.commit()
        raise

    settings.ensure_dirs()
    output_path = settings.parquet_dir / f"run_{run.id}.parquet"
    if result.flagged.height > 0 or "_record_key" in result.flagged.columns:
        result.flagged.write_parquet(output_path)
        output_hash = hash_dataframe(result.flagged)
    else:
        pl.DataFrame({"_record_key": []}).write_parquet(output_path)
        output_hash = hash_dataframe(pl.DataFrame({"_record_key": []}))

    scores_path = settings.parquet_dir / f"run_{run.id}_scores.parquet"
    if result.per_record_scores:
        scores_df = pl.DataFrame({
            "record_key": [s.record_key for s in result.per_record_scores],
            "score": [s.score for s in result.per_record_scores],
            "reason": [s.reason for s in result.per_record_scores],
        })
    else:
        scores_df = pl.DataFrame({"record_key": [], "score": [], "reason": []})
    scores_df.write_parquet(scores_path)

    run.status = RunStatus.COMPLETED
    run.finished_at = datetime.now(timezone.utc)
    run.output_hash = output_hash
    run.output_parquet_path = str(output_path)
    run.findings_count = result.flagged.height
    run.summary = result.summary
    audit_log.log_action(
        db, user_id=user_id, action=AuditAction.TEST_RUN, entity_type="test_run",
        entity_id=str(run.id), project_id=dataset.project_id,
        details={
            "detector": detector_name,
            "template_code": template_code,
            "findings": result.flagged.height,
            "input_hash": input_hash,
            "output_hash": output_hash,
        },
    )
    db.commit()
    return run


def run_template(
    db: Session,
    *,
    dataset_id: uuid.UUID,
    template_code: str,
    param_overrides: dict[str, Any] | None = None,
    user_id: uuid.UUID,
    pack_run_id: uuid.UUID | None = None,
) -> TestRun:
    tpl = tpl_catalog.get_template(db, template_code)
    merged = {**(tpl.default_params or {}), **(param_overrides or {})}
    return run_detector(
        db,
        dataset_id=dataset_id,
        detector_name=tpl.detector_name,
        params=merged,
        user_id=user_id,
        template_code=template_code,
        pack_run_id=pack_run_id,
    )


def load_scores(run: TestRun) -> pl.DataFrame:
    if not run.output_parquet_path:
        return pl.DataFrame({"record_key": [], "score": [], "reason": []})
    path = Path(run.output_parquet_path).with_name(f"run_{run.id}_scores.parquet")
    if path.exists():
        return pl.read_parquet(path)
    return pl.DataFrame({"record_key": [], "score": [], "reason": []})
